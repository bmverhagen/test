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

from .models import PageResult

__all__ = ["clean_brand_name", "parse_category_page"]

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


def _brand_from_title(title: str, known_brands: list[str]) -> str | None:
    """Match *title* against brands the page itself advertises.

    Only exact, word-bounded prefix matches count, so this cannot invent
    brands that Amazon did not list on the category page. The longest match
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
    """Parse one category page and return the brands found on it."""
    soup = _make_soup(html)

    refinement_brands = _brands_from_refinements(soup)
    structured_data_brands = _brands_from_structured_data(soup)
    known_brands = _dedupe(refinement_brands + structured_data_brands)

    cards = soup.select(_CARD_SELECTOR)
    if not cards:
        # Best-seller style list. The two faceout classes nest, so take
        # whichever matches first to avoid counting cards twice.
        cards = soup.select("div.p13n-sc-uncoverable-faceout") or soup.select(
            "div.zg-grid-general-faceout"
        )

    product_brands: list[str] = []
    for card in cards:
        brand = _brand_from_card(card)
        if brand is None:
            # Newest layout: no brand row on the card, so fall back to
            # matching the title against brands listed on this very page.
            brand = _brand_from_title(_card_title_text(card), known_brands)
        if brand is not None:
            product_brands.append(brand)

    return PageResult(
        url=url,
        page=page,
        refinement_brands=refinement_brands,
        product_brands=product_brands,
        structured_data_brands=structured_data_brands,
        total_cards=len(cards),
        cards_with_brand=len(product_brands),
        next_page_url=_next_page_url(soup, url),
    )
