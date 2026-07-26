"""Regex-first parser for speed-critical bulk paths.

Falls back to BeautifulSoup (`parser.parse_product_html`) only when the fast
path cannot extract title or bullets.
"""

from __future__ import annotations

import re
from html import unescape

from .models import ProductDescription
from .parser import parse_product_html

_TITLE_RE = re.compile(
    r'id="productTitle"[^>]*>\s*([^<]+)',
    re.I,
)
_TITLE_TAG_RE = re.compile(r"<title>([^<]+)</title>", re.I)
_OG_TITLE_RE = re.compile(
    r'property="og:title"\s+content="([^"]+)"',
    re.I,
)
_BULLET_RE = re.compile(
    r'class="a-list-item">\s*([^<]{8,})',
    re.I,
)
_BRAND_RE = re.compile(
    r'id="bylineInfo"[^>]*>\s*([^<]+)',
    re.I,
)
_META_RE = re.compile(
    r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
    re.I,
)
_NOISE = re.compile(
    r"(make sure this fits|zie dat dit past|javascript|click here|klik hier)",
    re.I,
)
# Only match real Amazon error-page titles — NOT product names like
# "Sonicare 5500" or "Shampoo 500 ml" (bare `500\b` falsely rejected those).
_BAD_TITLE = re.compile(
    r"(service niet beschikbaar|something went wrong|"
    r"er is iets misgegaan|page not found|robot check|validatecaptcha|"
    r"^(503|500)\b|"
    r"\b(503|500)\s*-\s*fout\b|"
    r"^error\b|"
    r"^fout:)",
    re.I,
)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _usable_title(text: str | None) -> str | None:
    title = _clean(text)
    if not title or _BAD_TITLE.search(title):
        return None
    # Strip trailing Amazon marketplace suffix from <title> tags.
    title = re.sub(r"\s*:?\s*Amazon\.[^:]*:.*$", "", title, flags=re.I).strip(" :-")
    return title or None


def fast_parse_html(
    html: str,
    *,
    asin: str,
    marketplace: str,
    url: str,
    provider: str,
) -> ProductDescription:
    """Parse title/bullets/brand with regex; BS4 fallback if incomplete."""
    title = _usable_title(_TITLE_RE.search(html).group(1) if _TITLE_RE.search(html) else None)
    if not title:
        og = _OG_TITLE_RE.search(html)
        title = _usable_title(og.group(1) if og else None)
    if not title:
        tag = _TITLE_TAG_RE.search(html)
        title = _usable_title(tag.group(1) if tag else None)

    brand_raw = _clean(_BRAND_RE.search(html).group(1) if _BRAND_RE.search(html) else None)
    brand = None
    if brand_raw:
        m = re.match(r"^(?:merk|brand)\s*:\s*(.+)$", brand_raw, re.I)
        if m:
            brand = m.group(1).strip()
        else:
            m = re.search(
                r"(?:visite(?:er)?|visit|open(?:en)?)\s+(?:the\s+|de\s+)?"
                r"(.+?)\s+store",
                brand_raw,
                re.I,
            )
            brand = (m.group(1).strip(" :") if m else brand_raw) or None

    bullets: list[str] = []
    for match in _BULLET_RE.finditer(html):
        text = _clean(match.group(1))
        if not text or _NOISE.search(text):
            continue
        if text not in bullets:
            bullets.append(text)

    meta = _clean(_META_RE.search(html).group(1) if _META_RE.search(html) else None)
    if meta and _BAD_TITLE.search(meta):
        meta = None

    # Title alone is enough for success (Prime Video / sparse mobile pages).
    if title:
        return ProductDescription(
            asin=asin,
            marketplace=marketplace,
            url=url,
            title=title,
            brand=brand,
            feature_bullets=bullets,
            description=meta if not bullets else None,
            aplus_text=None,
            meta_description=meta,
            provider=provider,
            source_bytes=len(html.encode("utf-8", errors="replace")),
        )

    # Incomplete — full parser
    product = parse_product_html(
        html,
        asin=asin,
        marketplace=marketplace,
        url=url,
        provider=provider,
    )
    if product.title and _BAD_TITLE.search(product.title):
        product.title = None
        product.error = product.error or "error page title rejected"
    return product
