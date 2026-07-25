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


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def fast_parse_html(
    html: str,
    *,
    asin: str,
    marketplace: str,
    url: str,
    provider: str,
) -> ProductDescription:
    """Parse title/bullets/brand with regex; BS4 fallback if incomplete."""
    title = _clean(_TITLE_RE.search(html).group(1) if _TITLE_RE.search(html) else None)
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

    if title and bullets:
        return ProductDescription(
            asin=asin,
            marketplace=marketplace,
            url=url,
            title=title,
            brand=brand,
            feature_bullets=bullets,
            description=None,
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
    return product
