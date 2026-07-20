"""Extract brand names from Amazon *category* page HTML.

Brands appear in three places on category/listing pages, and all three are
harvested:

1. The "Brands" refinement sidebar (``#brandsRefinements``, ``p_89``/``p_123``
   filter entries and their filter links).
2. The brand line shown on each search-result card, across the several page
   layouts Amazon serves (a dedicated ``h2.a-size-mini``/``h5`` row, or the
   legacy ``by <brand>`` row). On the newest layout there is no separate brand
   row, so as a fallback a card counts as a brand mention when its title
   starts with a brand the page itself lists (sidebar/structured data).
3. ``application/ld+json`` structured data embedded in the page.

Only the HTML is inspected; no product detail pages are ever requested.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup, FeatureNotFound, Tag

from .models import PageResult, ProductEntry

__all__ = [
    "AMAZON_HOUSE_BRANDS",
    "clean_brand_name",
    "guess_brand_from_title",
    "match_known_brand",
    "parse_category_page",
    "resolve_product_brands",
]

# Amazon's own well-known house/private-label brands. These frequently top
# best-seller lists but rarely appear in the brand filter sidebar.
AMAZON_HOUSE_BRANDS = (
    "Amazon Basics",
    "Amazon Essentials",
    "Amazon Fire",
    "AmazonCommercial",
    "Whole Foods Market",
    "Happy Belly",
    "Solimo",
    "Pinzon",
    "Goodthreads",
)

# Sidebar/expander strings that are not brand names.
_NOISE = frozenset(
    {
        "all brands",
        "brand",
        "brands",
        "clear",
        "featured brands",
        "our brands",
        "premium brands",
        "see all",
        "see all results",
        "see less",
        "see more",
        "show less",
        "show more",
        "sponsored",
        "top brands",
    }
)

_MAX_BRAND_LENGTH = 60
_COUNT_SUFFIX_RE = re.compile(r"\s*\(\d[\d.,\s]*\)\s*$")
_WHITESPACE_RE = re.compile(r"\s+")
# Expander labels that get concatenated onto the last sidebar entry.
_TRAILING_NOISE_RE = re.compile(r"\s+(?:see|show)\s+(?:more|less|all)$", re.IGNORECASE)

# li elements belonging to the brand refinement filter, across layouts.
_REFINEMENT_LI_SELECTORS = (
    "#brandsRefinements li",
    'ul[aria-labelledby^="p_89"] li',
    'ul[aria-labelledby^="p_123"] li',
    'li[id^="p_89/"]',
    'li[id^="p_123/"]',
)

_CARD_SELECTOR = 'div[data-component-type="s-search-result"]'


def _make_soup(html: str) -> BeautifulSoup:
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except FeatureNotFound:
            continue
    raise RuntimeError("No usable HTML parser found for BeautifulSoup")


# Classes Amazon uses for visually hidden (screen-reader only) text, which
# would otherwise duplicate the visible label ("Samsung Samsung").
_OFFSCREEN_CLASSES = {"a-offscreen", "aok-offscreen", "aok-offscreen-text"}

_NON_TEXT_TAGS = {"style", "script", "noscript", "template"}


def _visible_text(element: Tag) -> str:
    def hidden(string) -> bool:
        for parent in string.parents:
            if not isinstance(parent, Tag):
                break
            if parent.name in _NON_TEXT_TAGS:
                return True
            if _OFFSCREEN_CLASSES.intersection(parent.get("class") or ()):
                return True
        return False

    parts = (string.strip() for string in element.find_all(string=True) if not hidden(string))
    return " ".join(part for part in parts if part)


def clean_brand_name(raw: str) -> str:
    """Normalize raw extracted text into a brand name."""
    text = _WHITESPACE_RE.sub(" ", raw).strip()
    text = _COUNT_SUFFIX_RE.sub("", text)
    text = _TRAILING_NOISE_RE.sub("", text)
    if text.casefold().startswith("by "):
        text = text[3:].strip()
    return text


def _is_valid_brand(text: str) -> bool:
    if not text or len(text) > _MAX_BRAND_LENGTH:
        return False
    if text.casefold() in _NOISE:
        return False
    return any(char.isalnum() for char in text)


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


def _brands_from_refinements(soup: BeautifulSoup) -> list[str]:
    brands: list[str] = []

    for selector in _REFINEMENT_LI_SELECTORS:
        for li in soup.select(selector):
            name = clean_brand_name(_visible_text(li))
            if _is_valid_brand(name):
                brands.append(name)

    # Fallback: brand filter links encode the brand in the `rh` query
    # parameter as `p_89:<Brand>` (multiple values separated by `|`).
    for anchor in soup.select('a[href*="p_89"]'):
        query = urlparse(anchor.get("href", "")).query
        rh_value = dict(parse_qsl(query)).get("rh", "")
        for part in rh_value.split(","):
            if part.startswith("p_89:"):
                for name in part[len("p_89:") :].split("|"):
                    name = clean_brand_name(name)
                    if _is_valid_brand(name):
                        brands.append(name)

    return _dedupe(brands)


def _anchor_href(element: Tag) -> str:
    anchor = element if element.name == "a" else element.find_parent("a")
    if anchor is None:
        return ""
    return anchor.get("href") or ""


def _card_title_text(card: Tag) -> str:
    element = (
        card.select_one("a h2 span")
        or card.select_one("h2 a span")
        or card.select_one("h2 span")
        # Best-seller faceout: title is a clamped div inside the product link.
        or card.select_one('a[href*="/dp/"] div[class*="line-clamp"]')
    )
    if element is not None:
        return _visible_text(element)
    image = card.select_one("img[alt]")
    return (image.get("alt") or "").strip() if image is not None else ""


def _brand_from_card(card: Tag) -> str | None:
    """Extract the brand shown on a single search-result card, if any."""
    title = _card_title_text(card)

    def accept(text: str) -> bool:
        return _is_valid_brand(text) and text != title

    # Current layout: dedicated brand row in an `h2.a-size-mini` that does not
    # wrap the product link (older layouts put the *title* in such an h2).
    for h2 in card.select("h2.a-size-mini"):
        if h2.find("a"):
            continue
        name = clean_brand_name(_visible_text(h2))
        if accept(name):
            return name

    # Mid-era layout: brand row in an `h5` element.
    for span in card.select("h5 span"):
        if "/dp/" in _anchor_href(span):
            continue
        name = clean_brand_name(_visible_text(span))
        if accept(name):
            return name

    # Legacy layout: a "by <brand>" byline row.
    for row in card.select(".a-row"):
        text = _visible_text(row)
        if text.casefold().startswith("by "):
            name = clean_brand_name(text)
            if accept(name):
                return name

    # Newest layout variant: standalone brand span in the title block, never
    # inside the product (/dp/) link.
    for span in card.select('[data-cy="title-recipe"] span.a-size-base-plus.a-color-base'):
        if "/dp/" in _anchor_href(span):
            continue
        name = clean_brand_name(_visible_text(span))
        if accept(name):
            return name

    return None


def match_known_brand(title: str, known_brands: list[str]) -> str | None:
    """Match *title* against a list of brands Amazon itself advertises.

    Only exact, word-bounded prefix matches count, so this cannot invent
    brands that Amazon did not list on a category page. The longest match
    wins (e.g. "Sony Electronics" beats "Sony").
    """
    folded = title.casefold()
    if not folded:
        return None
    best: str | None = None
    for brand in known_brands:
        key = brand.casefold()
        if not folded.startswith(key):
            continue
        if len(folded) > len(key) and folded[len(key)].isalnum():
            continue
        if best is None or len(brand) > len(best):
            best = brand
    return best


_GUESS_STRIP_CHARS = "\u00ae\u2122\u00a9:;,.-\u2013\u2014"
_GUESS_MIN_LENGTH = 3


def guess_brand_from_title(title: str) -> str | None:
    """Conservatively guess a brand from the first word of a product title.

    Amazon product titles virtually always start with the brand. Only the
    single leading token is used, and anything with digits, too short, or
    noise-like is rejected — so "BELLA 12 Cup Programmable..." yields "BELLA"
    while "12-Cup Coffee Maker" yields nothing. Results should be labeled as
    guesses (``title_guess``); they are never mixed into exact matches.
    """
    parts = title.split(maxsplit=1)
    if not parts:
        return None
    token = parts[0].strip(_GUESS_STRIP_CHARS)
    if len(token) < _GUESS_MIN_LENGTH:
        return None
    if any(char.isdigit() for char in token) or not any(char.isalpha() for char in token):
        return None
    if token.casefold() in _NOISE:
        return None
    return token


def _collect_structured_brands(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        brand = node.get("brand")
        if isinstance(brand, str):
            out.append(brand)
        elif isinstance(brand, dict) and isinstance(brand.get("name"), str):
            out.append(brand["name"])
        for value in node.values():
            _collect_structured_brands(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_structured_brands(item, out)


def _brands_from_structured_data(soup: BeautifulSoup) -> list[str]:
    brands: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        found: list[str] = []
        _collect_structured_brands(data, found)
        brands.extend(name for name in map(clean_brand_name, found) if _is_valid_brand(name))
    return _dedupe(brands)


_RANK_BADGE_RE = re.compile(r"#\s*(\d+)")


def _bsr_ranks_by_asin(soup: BeautifulSoup) -> dict[str, int]:
    """Read ASIN -> sales rank from the best-seller page's embedded JSON."""
    ranks: dict[str, int] = {}
    for container in soup.select("div[data-client-recs-list]"):
        try:
            data = json.loads(container["data-client-recs-list"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            asin = item.get("id")
            rank = (item.get("metadataMap") or {}).get("render.zg.rank", "")
            if isinstance(asin, str) and isinstance(rank, str) and rank.isdigit():
                ranks[asin] = int(rank)
    return ranks


def _card_rank(card: Tag, ranks_by_asin: dict[str, int], asin: str | None) -> int | None:
    if asin and asin in ranks_by_asin:
        return ranks_by_asin[asin]
    root = card.find_parent(id="gridItemRoot") or card
    badge = root.select_one(".zg-bdg-text")
    if badge is not None:
        match = _RANK_BADGE_RE.search(badge.get_text(strip=True))
        if match:
            return int(match.group(1))
    return None


def _card_asin(card: Tag) -> str | None:
    asin = card.get("data-asin") or card.get("id")
    if asin and len(asin) == 10 and asin.isalnum():
        return asin
    inner = card.select_one("div.p13n-sc-uncoverable-faceout[id]")
    if inner is not None:
        candidate = inner.get("id", "")
        if len(candidate) == 10 and candidate.isalnum():
            return candidate
    return None


def resolve_product_brands(
    page: "PageResult", known_brands: list[str], guess_missing: bool = True
) -> int:
    """Fill in missing product brands by title-matching against *known_brands*.

    Used for best-seller pages, whose cards carry no brand row: the caller
    supplies brands harvested from the same node's search listing; Amazon's
    house brands (e.g. "Amazon Basics") are always part of the vocabulary.
    Titles that still don't match get a conservative first-word guess, marked
    ``title_guess``, unless *guess_missing* is False. Returns the number of
    products resolved and keeps ``product_brands``/counters in sync.
    """
    seen = {name.casefold() for name in known_brands}
    vocabulary = known_brands + [
        name for name in AMAZON_HOUSE_BRANDS if name.casefold() not in seen
    ]

    resolved = 0
    for index, product in enumerate(page.products):
        if product.brand is not None:
            continue
        brand = match_known_brand(product.title, vocabulary)
        source = "known_brand"
        if brand is None and guess_missing:
            brand = guess_brand_from_title(product.title)
            source = "title_guess"
        if brand is None:
            continue
        page.products[index] = ProductEntry(
            rank=product.rank,
            title=product.title,
            brand=brand,
            brand_source=source,
            asin=product.asin,
        )
        resolved += 1
    page.product_brands = [p.brand for p in page.products if p.brand is not None]
    page.cards_with_brand = len(page.product_brands)
    return resolved


def _next_page_url(soup: BeautifulSoup, base_url: str) -> str | None:
    anchor = soup.select_one("a.s-pagination-next:not(.s-pagination-disabled)")
    if anchor is None:
        # Best-seller style pagination.
        anchor = soup.select_one("ul.a-pagination li.a-last:not(.a-disabled) a")
    if anchor is None:
        return None
    href = anchor.get("href")
    if not href:
        return None
    return urljoin(base_url, href) if base_url else href


def parse_category_page(html: str, url: str = "", page: int = 1) -> PageResult:
    """Parse one category page and return the brands and products found on it."""
    soup = _make_soup(html)

    refinement_brands = _brands_from_refinements(soup)
    structured_data_brands = _brands_from_structured_data(soup)
    known_brands = _dedupe(refinement_brands + structured_data_brands)

    cards = soup.select(_CARD_SELECTOR)
    is_best_seller_list = False
    if not cards:
        # Best-seller style list. The two faceout classes nest, so take
        # whichever matches first to avoid counting cards twice.
        cards = soup.select("div.p13n-sc-uncoverable-faceout") or soup.select(
            "div.zg-grid-general-faceout"
        )
        is_best_seller_list = bool(cards)

    ranks_by_asin = _bsr_ranks_by_asin(soup) if is_best_seller_list else {}

    products: list[ProductEntry] = []
    for position, card in enumerate(cards, start=1):
        title = _card_title_text(card)
        brand = _brand_from_card(card)
        brand_source = "brand_row" if brand is not None else None
        if brand is None:
            # Newest layout: no brand row on the card, so fall back to
            # matching the title against brands listed on this very page.
            brand = match_known_brand(title, known_brands)
            brand_source = "known_brand" if brand is not None else None
        asin = _card_asin(card)
        rank = _card_rank(card, ranks_by_asin, asin) if is_best_seller_list else position
        products.append(
            ProductEntry(rank=rank, title=title, brand=brand, brand_source=brand_source, asin=asin)
        )

    product_brands = [product.brand for product in products if product.brand is not None]

    return PageResult(
        url=url,
        page=page,
        refinement_brands=refinement_brands,
        product_brands=product_brands,
        structured_data_brands=structured_data_brands,
        products=products,
        is_best_seller_list=is_best_seller_list,
        total_cards=len(cards),
        cards_with_brand=len(product_brands),
        next_page_url=_next_page_url(soup, url),
    )
