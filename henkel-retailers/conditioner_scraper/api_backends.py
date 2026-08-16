"""Direct backend/API fetchers for shops that expose JSON/GraphQL/sitemaps."""

from __future__ import annotations

import html
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests

try:
    from .brands import HENKEL_BRANDS, product
except ImportError:
    from brands import HENKEL_BRANDS, product

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
QUERY = "conditioner"
PAGE_SIZE = 24
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "api_cache"

_AIRCO_RE = re.compile(
    r"airco|air.?condition|privacyomheining|uitlaatslang|beschermhoes|"
    r"buitenunit|afvoerslang|reisflessen|leerreiniger|hond|katten",
    re.I,
)
_HAIR_COND_RE = re.compile(
    r"(?<![a-z])conditioner(?![a-z])|cremespoeling|crèmespoeling|"
    r"haarconditioner|leave-in-conditioner|leave.in.conditioner",
    re.I,
)


def _euro_cents(cents: int | float | None) -> str | None:
    if cents is None:
        return None
    try:
        value = float(cents) / 100.0
    except (TypeError, ValueError):
        return None
    return f"€{value:.2f}".replace(".", ",")


def _euro(value: int | float | None) -> str | None:
    if value is None:
        return None
    try:
        return f"€{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return None


def fetch_jumbo_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Jumbo GraphQL product search (requires jmb-device-id client header)."""
    offset = (page - 1) * page_size
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://www.jumbo.com",
        "Referer": (
            "https://www.jumbo.com/producten/"
            f"?searchTerms={query}&searchType=keyword"
        ),
        "apollographql-client-name": "jumbo-web",
        "apollographql-client-version": "1.0.0",
        "x-jumbo-backend-service": "products",
        "x-apollo-operation-name": "GetProductListSearchResult",
        "apollo-require-preflight": "true",
        "jmb-device-id": str(uuid.uuid4()),
        "x-source": "jumbo-web",
    }
    gql = """
    query GetProductListSearchResult($input: ProductSearchInput!) {
      searchProducts(input: $input) {
        count
        products {
          id
          title
          brand
          link
          price { price }
        }
      }
    }
    """
    payload = {
        "operationName": "GetProductListSearchResult",
        "variables": {
            "input": {
                "searchTerms": query,
                "searchType": "keyword",
                "offSet": offset,
                "limit": page_size,
            }
        },
        "query": gql,
    }
    r = requests.post(
        "https://www.jumbo.com/api/graphql",
        json=payload,
        headers=headers,
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors") and not ((data.get("data") or {}).get("searchProducts")):
        raise RuntimeError(data["errors"][0].get("message") or "Jumbo GraphQL error")
    products = ((data.get("data") or {}).get("searchProducts") or {}).get("products") or []
    out: list[dict] = []
    for item in products:
        title = item.get("title") or ""
        if not title:
            continue
        link = item.get("link") or ""
        url = urljoin("https://www.jumbo.com", link) if link else None
        price = _euro_cents((item.get("price") or {}).get("price"))
        out.append(
            product(
                rank=0,
                title=title,
                brand=item.get("brand") or None,
                url=url,
                price=price,
                extra={"sku": item.get("id") or item.get("sku"), "api": "jumbo_graphql"},
            )
        )
    return out


def fetch_da_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """DA Magento GraphQL search at /api/graphql."""
    gql = """
    query SearchConditioner($search: String!, $pageSize: Int!, $currentPage: Int!) {
      products(search: $search, pageSize: $pageSize, currentPage: $currentPage) {
        total_count
        page_info { current_page total_pages }
        items {
          name
          sku
          url_key
          price_range {
            minimum_price {
              final_price { value currency }
            }
          }
        }
      }
    }
    """
    payload = {
        "operationName": "SearchConditioner",
        "query": gql,
        "variables": {
            "search": query,
            "pageSize": page_size,
            "currentPage": page,
        },
    }
    r = requests.post(
        "https://www.da.nl/api/graphql",
        json=payload,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Store": "da_nl",
            "Origin": "https://www.da.nl",
            "Referer": f"https://www.da.nl/search?query={query}",
        },
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors") and not ((data.get("data") or {}).get("products")):
        raise RuntimeError(data["errors"][0].get("message") or "DA GraphQL error")
    items = ((data.get("data") or {}).get("products") or {}).get("items") or []
    out: list[dict] = []
    for item in items:
        title = item.get("name") or ""
        if not title:
            continue
        url_key = item.get("url_key") or ""
        url = f"https://www.da.nl/product/{url_key}" if url_key else None
        price_val = (
            ((item.get("price_range") or {}).get("minimum_price") or {})
            .get("final_price", {})
            .get("value")
        )
        out.append(
            product(
                rank=0,
                title=title,
                url=url,
                price=_euro(price_val),
                extra={"sku": item.get("sku"), "api": "da_magento_graphql"},
            )
        )
    return out


def fetch_koopjes_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """KoopjesDrogisterij WooCommerce Store API."""
    r = requests.get(
        "https://www.koopjesdrogisterij.nl/wp-json/wc/store/v1/products",
        params={"search": query, "page": page, "per_page": page_size},
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "nl-NL,nl;q=0.9",
        },
        timeout=45,
    )
    r.raise_for_status()
    items = r.json()
    if not isinstance(items, list):
        raise RuntimeError("Koopjes WC API returned non-list payload")
    out: list[dict] = []
    for item in items:
        title = html.unescape(item.get("name") or "")
        if not title:
            continue
        prices = item.get("prices") or {}
        price = None
        raw = prices.get("price") or prices.get("regular_price")
        if raw is not None:
            try:
                # Woo store API prices are minor units (cents) as strings
                price = _euro_cents(int(raw))
            except (TypeError, ValueError):
                price = None
        out.append(
            product(
                rank=0,
                title=title,
                url=item.get("permalink"),
                price=price,
                extra={"sku": str(item.get("id") or ""), "api": "koopjes_wc_store"},
            )
        )
    return out


# --- Albert Heijn mobile search API (anonymous token) ---

_ah_token: str | None = None
_ah_token_expires = 0.0


def _ah_access_token() -> str:
    global _ah_token, _ah_token_expires
    if _ah_token and time.time() < _ah_token_expires - 60:
        return _ah_token
    r = requests.post(
        "https://api.ah.nl/mobile-auth/v1/auth/token/anonymous",
        json={"clientId": "appie"},
        headers={
            "User-Agent": "Appie/8.22.3",
            "Content-Type": "application/json",
            "X-Application": "AHWEBSHOP",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    _ah_token = data["access_token"]
    _ah_token_expires = time.time() + float(data.get("expires_in") or 3600)
    return _ah_token


def fetch_ah_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """AH mobile product search (anonymous bearer token). page is 1-based."""
    token = _ah_access_token()
    r = requests.get(
        "https://api.ah.nl/mobile-services/product/search/v2",
        params={
            "query": query,
            "page": page - 1,
            "size": page_size,
            "sortOn": "RELEVANCE",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Appie/8.22.3",
            "X-Application": "AHWEBSHOP",
            "Accept": "application/json",
        },
        timeout=45,
    )
    if r.status_code in {403, 404}:
        return []
    r.raise_for_status()
    payload = r.json()
    page_meta = payload.get("page") or {}
    # Beyond last page
    if page_meta.get("totalPages") is not None and (page - 1) >= int(page_meta["totalPages"]):
        return []
    items = payload.get("products") or []
    out: list[dict] = []
    for item in items:
        title = item.get("title") or ""
        size = item.get("salesUnitSize") or ""
        if size and size.lower() not in title.lower():
            title = f"{title} {size}".strip()
        if not title:
            continue
        wid = item.get("webshopId")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"https://www.ah.nl/producten/product/wi{wid}/{slug}" if wid else None
        raw_price = item.get("currentPrice")
        if isinstance(raw_price, dict):
            raw_price = raw_price.get("amount")
        if raw_price is None:
            raw_price = item.get("priceBeforeBonus")
        out.append(
            product(
                rank=0,
                title=title,
                brand=item.get("brand") or None,
                url=url,
                price=_euro(raw_price),
                extra={"sku": str(wid or ""), "api": "ah_mobile_search"},
            )
        )
    return out


# --- Sitemap catalog backends (Bol HTML is IP-blocked; sitemaps remain open) ---

def _slug_title(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    # bol: .../slug/id -> use previous segment
    if path.isdigit() or re.fullmatch(r"\d+", path):
        parts = url.rstrip("/").split("/")
        path = parts[-2] if len(parts) >= 2 else path
    title = html.unescape(path.replace("-", " ")).strip()
    return re.sub(r"\s+", " ", title).title()


def _is_hair_conditioner_url(url: str) -> bool:
    u = html.unescape(url).lower()
    if _AIRCO_RE.search(u):
        return False
    # Must look like hair conditioner / crème spoeling, not soap pumps etc.
    if not _HAIR_COND_RE.search(u):
        return False
    noise = (
        "zeepdispenser",
        "afwasvloeistof",
        "reisflessen",
        "leerreiniger",
        "shower-gel",
        "douchegel",
        "handzeep",
        "airco",
    )
    if any(n in u for n in noise):
        return False
    return True


def _henkel_score(title: str) -> int:
    low = title.casefold()
    for i, brand in enumerate(sorted(HENKEL_BRANDS, key=len, reverse=True)):
        if brand.casefold() in low:
            return 100 - i
    return 0


def _paginate(rows: list[dict], page: int, page_size: int) -> list[dict]:
    start = (page - 1) * page_size
    return rows[start : start + page_size]


def _load_json_cache(name: str, max_age_sec: int = 86400) -> list | None:
    path = CACHE_DIR / name
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_sec:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json_cache(name: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _bol_conditioner_catalog(limit: int = 320) -> list[dict]:
    cached = _load_json_cache("bol_conditioner_sitemap.json")
    if cached:
        return cached

    index = requests.get("https://www.bol.com/sitemap/nl-nl/", headers={"User-Agent": UA}, timeout=45)
    index.raise_for_status()
    locs = re.findall(r"<loc>([^<]+)</loc>", index.text)
    found: list[str] = []

    def scan(loc: str) -> list[str]:
        try:
            r = requests.get(loc, headers={"User-Agent": UA}, timeout=90)
            if r.status_code != 200:
                return []
            return [u for u in re.findall(r"<loc>([^<]+)</loc>", r.text) if _is_hair_conditioner_url(u)]
        except Exception:
            return []

    # Scan product sitemap shards (full index is ~1000 files / ~10MB each).
    with ThreadPoolExecutor(max_workers=12) as pool:
        for hits in pool.map(scan, locs[:500]):
            found.extend(hits)

    seen: set[str] = set()
    rows: list[dict] = []
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        title = _slug_title(url)
        if _AIRCO_RE.search(title) or len(title) < 8:
            continue
        rows.append({"title": title, "url": url})

    rows.sort(key=lambda r: (-_henkel_score(r["title"]), r["title"].casefold()))
    rows = rows[:limit]
    _save_json_cache("bol_conditioner_sitemap.json", rows)
    return rows


def fetch_bol_sitemap(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Bol.com conditioner catalog via public product sitemaps (HTML search is IP-blocked)."""
    catalog = _bol_conditioner_catalog()
    chunk = _paginate(catalog, page, page_size)
    return [
        product(
            rank=0,
            title=row["title"],
            url=row["url"],
            extra={"api": "bol_sitemap_catalog"},
        )
        for row in chunk
    ]


def _dirk_conditioner_catalog() -> list[dict]:
    cached = _load_json_cache("dirk_conditioner_sitemap.json")
    if cached:
        return cached
    r = requests.get(
        "https://www.dirk.nl/products-sitemap.xml",
        headers={"User-Agent": UA},
        timeout=60,
    )
    r.raise_for_status()
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    rows: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        if "haarverzorging" not in url:
            continue
        if not re.search(r"cremespoeling|conditioner|syoss|gliss", url, re.I):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = _slug_title(url)
        # Fix mojibake Andrélon
        title = title.replace("Andrã©Lon", "Andrélon").replace("AndrÃ©lon", "Andrélon")
        rows.append({"title": title, "url": url})
    rows.sort(key=lambda r: (-_henkel_score(r["title"]), r["title"].casefold()))
    _save_json_cache("dirk_conditioner_sitemap.json", rows)
    return rows


def fetch_dirk_sitemap(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    catalog = _dirk_conditioner_catalog()
    chunk = _paginate(catalog, page, page_size)
    return [
        product(rank=0, title=row["title"], url=row["url"], extra={"api": "dirk_sitemap"})
        for row in chunk
    ]


def _plein_conditioner_catalog() -> list[dict]:
    cached = _load_json_cache("plein_conditioner_sitemap.json")
    if cached:
        return cached
    r = requests.get(
        "https://www.plein.nl/sitemaps/plein-nl-verzorging.xml",
        headers={"User-Agent": UA},
        timeout=90,
    )
    r.raise_for_status()
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    rows: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        if not _is_hair_conditioner_url(url) and "conditioner" not in url.lower():
            continue
        if _AIRCO_RE.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append({"title": _slug_title(url), "url": url})
    rows.sort(key=lambda r: (-_henkel_score(r["title"]), r["title"].casefold()))
    _save_json_cache("plein_conditioner_sitemap.json", rows)
    return rows


def fetch_plein_sitemap(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    catalog = _plein_conditioner_catalog()
    chunk = _paginate(catalog, page, page_size)
    return [
        product(rank=0, title=row["title"], url=row["url"], extra={"api": "plein_sitemap"})
        for row in chunk
    ]


API_FETCHERS: dict[str, Callable[..., list[dict]]] = {
    "jumbo.com": fetch_jumbo_api,
    "da.nl": fetch_da_api,
    "koopjesdrogisterij.nl": fetch_koopjes_api,
    "ah.nl": fetch_ah_api,
    "bol.com": fetch_bol_sitemap,
    "dirk.nl": fetch_dirk_sitemap,
    "plein.nl": fetch_plein_sitemap,
}


def fetch_api_page(domain: str, page: int, *, sleep: float = 0.4) -> list[dict] | None:
    """Fetch one page via backend API. Returns None if no API backend is registered."""
    fn = API_FETCHERS.get(domain)
    if fn is None:
        return None
    products = fn(page)
    if sleep:
        time.sleep(sleep)
    return products