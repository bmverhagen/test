"""Parse product description fields from Amazon DP HTML."""

from __future__ import annotations

import json
import re
from html import unescape

from bs4 import BeautifulSoup, Tag

from .models import ASIN_RE, ProductDescription

__all__ = ["extract_asin", "parse_product_html"]

_NOISE_BULLET = re.compile(
    r"(make sure this fits|zie dat dit past|garantiert|garantisce|"
    r"javascript|click here|klik hier)",
    re.I,
)


def extract_asin(value: str) -> str | None:
    """Pull a 10-char ASIN from a bare ASIN or product URL."""
    value = value.strip()
    if re.fullmatch(ASIN_RE, value):
        return value.upper()
    match = re.search(rf"/(?:dp|gp/product|gp/aw/d)/({ASIN_RE})", value, re.I)
    if match:
        return match.group(1).upper()
    match = re.search(rf"\b({ASIN_RE})\b", value)
    return match.group(1).upper() if match else None


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _tag_text(node: Tag | None) -> str | None:
    if node is None:
        return None
    return _clean_text(node.get_text(" ", strip=True))


def _feature_bullets(soup: BeautifulSoup) -> list[str]:
    root = soup.select_one("#feature-bullets") or soup.select_one("#featurebullets_feature_div")
    if root is None:
        return []
    bullets: list[str] = []
    for li in root.select("li"):
        if li.select_one(".aok-hidden, .a-declarative"):
            # Keep list items that still have visible text.
            pass
        span = li.select_one("span.a-list-item") or li
        text = _tag_text(span)
        if not text or _NOISE_BULLET.search(text):
            continue
        if text not in bullets:
            bullets.append(text)
    return bullets


def _product_description(soup: BeautifulSoup) -> str | None:
    for selector in (
        "#productDescription",
        "#productDescription_feature_div #productDescription",
        "#productDescription_feature_div",
        "#bookDescription_feature_div .a-expander-content",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        for junk in node.select("script, style, noscript"):
            junk.decompose()
        text = _tag_text(node)
        if text and len(text) > 20:
            return text
    return None


def _aplus_text(soup: BeautifulSoup) -> str | None:
    for selector in (
        "#aplus_feature_div",
        "#aplus3p_feature_div",
        "#dpx-aplus-product-description_feature_div",
        "#dpx-aplus-3p-product-description_feature_div",
        "#aplus",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        for junk in node.select("script, style, noscript"):
            junk.decompose()
        text = _tag_text(node)
        if text and len(text) > 40:
            return text
    return None


def _overview(soup: BeautifulSoup) -> dict[str, str]:
    root = soup.select_one("#productOverview_feature_div")
    if root is None:
        return {}
    out: dict[str, str] = {}
    for row in root.select("tr"):
        cells = row.select("td, th")
        if len(cells) < 2:
            continue
        key = _tag_text(cells[0])
        value = _tag_text(cells[1])
        if key and value:
            out[key] = value
    return out


def _brand(soup: BeautifulSoup) -> str | None:
    byline = soup.select_one("#bylineInfo")
    text = _tag_text(byline)
    if text:
        # "Merk: Oral-B" / "Brand: Acme"
        m = re.match(r"^(?:merk|brand)\s*:\s*(.+)$", text, re.I)
        if m:
            return m.group(1).strip() or None
        # "De Oral-B Store openen" / "Visit the Oral-B Store"
        m = re.search(
            r"(?:visite(?:er)?|visit|open(?:en)?)\s+(?:the\s+|de\s+|la\s+|l['’])?"
            r"(.+?)\s+store",
            text,
            re.I,
        )
        if m:
            return m.group(1).strip(" :") or None
        m = re.search(r"^(.+?)\s+store\b", text, re.I)
        if m:
            brand = re.sub(r"^(de|the|la|l['’])\s+", "", m.group(1), flags=re.I)
            return brand.strip() or None
        return text
    overview = _overview(soup)
    for key in ("Merk", "Brand", "Manufacturer", "Fabrikant"):
        if key in overview:
            return overview[key]
    return None


def _meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return _clean_text(str(tag["content"]))
    return None


def _ld_json_description(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    title = None
    description = None
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            type_list = types if isinstance(types, list) else [types]
            if not any(t in ("Product", "ProductGroup") for t in type_list):
                continue
            title = title or _clean_text(item.get("name"))
            description = description or _clean_text(item.get("description"))
            brand = item.get("brand")
            if isinstance(brand, dict):
                title = title  # keep
    return title, description


def parse_product_html(
    html: str,
    *,
    asin: str,
    marketplace: str,
    url: str,
    provider: str = "html",
) -> ProductDescription:
    """Extract description-related fields from a product detail page."""
    soup = BeautifulSoup(html, "lxml")

    title = _tag_text(soup.select_one("#productTitle"))
    ld_title, ld_description = _ld_json_description(soup)
    title = title or ld_title

    description = _product_description(soup) or ld_description
    bullets = _feature_bullets(soup)
    aplus = _aplus_text(soup)
    overview = _overview(soup)

    return ProductDescription(
        asin=asin,
        marketplace=marketplace,
        url=url,
        title=title,
        brand=_brand(soup),
        feature_bullets=bullets,
        description=description,
        aplus_text=aplus,
        overview=overview,
        meta_description=_meta_description(soup),
        provider=provider,
        source_bytes=len(html.encode("utf-8", errors="replace")),
    )
