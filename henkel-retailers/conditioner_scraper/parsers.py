"""Shop-specific parsers for conditioner search / category listings."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, unquote

from bs4 import BeautifulSoup

try:
    from .brands import product
except ImportError:  # script execution
    from brands import product


def parse_amazon(html: str, base: str = "https://www.amazon.nl") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select('div[data-component-type="s-search-result"]')
    out: list[dict] = []
    seen: set[str] = set()
    for card in cards:
        asin = card.get("data-asin") or ""
        if not asin or asin in seen:
            continue
        seen.add(asin)
        h2 = card.select_one("h2")
        title = h2.get_text(" ", strip=True) if h2 else None
        if not title:
            span = card.select_one("h2 span")
            title = span.get_text(" ", strip=True) if span else None
        if not title:
            continue
        price_el = card.select_one("span.a-offscreen")
        price = price_el.get_text(strip=True).replace("\xa0", " ") if price_el else None
        href_el = card.select_one(f'a[href*="/dp/{asin}"]')
        url = urljoin(base, href_el["href"].split("?")[0]) if href_el else f"{base}/dp/{asin}"
        out.append(
            product(
                rank=len(out) + 1,
                title=title,
                url=url,
                price=price,
                extra={"sku": asin},
            )
        )
    return out


def parse_deonlinedrogist(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("@type") != "CollectionPage":
            continue
        items = (data.get("mainEntity") or {}).get("itemListElement") or []
        for item in items:
            title = item.get("name") or ""
            if not title:
                continue
            out.append(
                product(
                    rank=int(item.get("position") or len(out) + 1),
                    title=title,
                    url=item.get("url"),
                )
            )
        if out:
            return out
    return out


def parse_notino(html: str, base: str = "https://www.notino.nl") -> list[dict]:
    # Prefer embedded products JSON
    match = re.search(r'"products"\s*:\s*(\[)', html)
    if match:
        start = match.start(1)
        depth = 0
        end = None
        for idx, ch in enumerate(html[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end:
            try:
                items = json.loads(html[start:end])
                out = []
                for item in items:
                    name = item.get("name") or ""
                    brand = item.get("brandName")
                    annotation = item.get("annotation") or ""
                    title = f"{brand} {name} {annotation}".strip()
                    price_info = item.get("priceInformation") or {}
                    price = price_info.get("price")
                    price_s = f"€{price:.2f}".replace(".", ",") if isinstance(price, (int, float)) else None
                    out.append(
                        product(
                            rank=len(out) + 1,
                            title=title,
                            brand=brand,
                            url=urljoin(base, item.get("url") or ""),
                            price=price_s,
                            extra={"sku": str(item.get("id") or "")},
                        )
                    )
                if out:
                    return out
            except Exception:
                pass

    soup = BeautifulSoup(html, "lxml")
    tiles = [
        tag
        for tag in soup.find_all(True)
        if any("StyledProductTile" in c for c in (tag.get("class") or []))
    ]
    out = []
    for tile in tiles:
        a = tile.find("a", href=True)
        if not a:
            continue
        text = tile.get_text(" ", strip=True)
        title = a.get_text(" ", strip=True) or text
        price_m = re.search(r"(\d+[.,]\d{2})\s*€|€\s*(\d+[.,]\d{2})", text)
        price = None
        if price_m:
            price = "€" + (price_m.group(1) or price_m.group(2))
        out.append(
            product(
                rank=len(out) + 1,
                title=title,
                url=urljoin(base, a["href"]),
                price=price,
            )
        )
    return out


def parse_koopjes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for h in soup.select("h2, h3"):
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue
        # skip nav-ish
        if title.lower() in {"filteren op", "sorteer op"}:
            continue
        a = h.find("a", href=True) or h.find_parent("a", href=True)
        url = a["href"] if a else None
        if url and url.startswith("/"):
            url = urljoin("https://www.koopjesdrogisterij.nl", url)
        out.append(product(rank=len(out) + 1, title=title, url=url))
    return out


def parse_kruidvat_markdown(md: str) -> list[dict]:
    """Parse WebFetch-style markdown from Kruidvat conditioner category."""
    out = []
    # Pattern: ### Brand\n\nTitle
    blocks = re.split(r"\n###\s+", md)
    for block in blocks[1:]:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        brand = lines[0]
        # find product title line (usually next non-meta line)
        title = None
        for line in lines[1:]:
            if line.lower().startswith("voeg toe"):
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if "conditioner" in line.lower() or "crèmespoeling" in line.lower() or "2-in-1" in line.lower():
                title = line
                break
            if brand.lower() in line.lower() or len(line) > 12:
                title = line
                break
        if not title:
            continue
        out.append(product(rank=len(out) + 1, title=title, brand=brand if brand != title else None))
    return out


def parse_trekpleister_markdown(md: str) -> list[dict]:
    """Parse Trekpleister conditioner category markdown (price split across lines)."""
    # Collect product title lines: non-price lines that look like product names
    lines = [ln.strip() for ln in md.splitlines()]
    titles: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # price fragments like "7" then "." then "49"
        if re.fullmatch(r"\d+", line) and i + 2 < len(lines) and lines[i + 1] == "." and re.fullmatch(r"\d{2}", lines[i + 2]):
            # next meaningful title often after size lines
            j = i + 3
            while j < len(lines):
                cand = lines[j]
                if not cand:
                    j += 1
                    continue
                if re.fullmatch(r"\d+", cand) or cand in {".", "ml", "Filter"}:
                    j += 1
                    continue
                if cand.endswith("ml") or "haartype" in cand.lower() or cand.startswith("Producten"):
                    j += 1
                    continue
                if len(cand) > 8 and not cand.startswith("Sorteer") and "gevonden" not in cand:
                    if cand not in titles:
                        titles.append(cand)
                    break
                j += 1
            i = j + 1
            continue
        i += 1
    # Fallback: lines containing Conditioner
    if len(titles) < 5:
        titles = [
            ln.strip()
            for ln in lines
            if "conditioner" in ln.lower() and len(ln.strip()) > 10 and not ln.strip().startswith("#")
        ]
    return [product(rank=i, title=t) for i, t in enumerate(titles, start=1)]


def parse_ddg_fallback(html: str, domain: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for a in soup.select("a.result__a"):
        title = unescape(a.get_text(" ", strip=True))
        href = a.get("href") or ""
        # DDG redirect links
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            href = unquote(m.group(1))
        if domain not in href:
            continue
        # filter airco noise
        low = title.lower()
        if "airco" in low or "aircondition" in low:
            continue
        if "conditioner" not in low and "crèmespoeling" not in low and "haarbalsem" not in low:
            # still allow Syoss product pages etc.
            if not any(b.lower() in low for b in ("syoss", "gliss", "schwarzkopf", "schauma")):
                continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=len(out) + 1, title=title, url=href))
    return out


def parse_bing_fallback(html: str, domain: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for li in soup.select("li.b_algo"):
        h2 = li.select_one("h2")
        a = h2.find("a", href=True) if h2 else None
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = a["href"]
        if domain not in href:
            continue
        low = title.lower()
        if "airco" in low or "aircondition" in low:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(product(rank=len(out) + 1, title=title, url=href))
    return out


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
