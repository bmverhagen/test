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


# --- curl_cffi / SPA backends (TLS fingerprint bypass) ---

def _curl_session():
    from curl_cffi import requests as crequests

    return crequests.Session(impersonate="chrome124")


def _jina_fetch(url: str, *, html: bool = False, timeout: int = 120, retries: int = 6) -> str:
    headers = {"User-Agent": UA}
    if html:
        headers["X-Return-Format"] = "html"
    cache_name = (
        "jina_"
        + ("html_" if html else "md_")
        + re.sub(r"[^a-z0-9]+", "_", url.casefold())[:120]
        + ".txt"
    )
    cached = _load_json_cache(cache_name.replace(".txt", ".json"), max_age_sec=6 * 3600)
    if isinstance(cached, dict) and cached.get("body"):
        return cached["body"]
    # Also try raw text cache
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < 6 * 3600:
        body = cache_path.read_text(encoding="utf-8", errors="ignore")
        if len(body) > 1000 and "Just a moment" not in body[:2000]:
            return body

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=timeout)
            if r.status_code in {403, 429, 503}:
                time.sleep(3.0 * (attempt + 1))
                last_err = RuntimeError(f"jina {r.status_code}")
                continue
            r.raise_for_status()
            if len(r.text) < 500 or "Just a moment" in r.text[:2000]:
                time.sleep(3.0 * (attempt + 1))
                last_err = RuntimeError("jina challenge/short")
                continue
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(r.text, encoding="utf-8")
            return r.text
        except Exception as exc:
            last_err = exc
            time.sleep(3.0 * (attempt + 1))
    raise RuntimeError(f"Jina failed for {url}: {last_err}")


def _jina_html(url: str, timeout: int = 120) -> str:
    return _jina_fetch(url, html=True, timeout=timeout)


def _jina_md(url: str, timeout: int = 120) -> str:
    return _jina_fetch(url, html=False, timeout=timeout)


def _playwright_html(url: str, wait_ms: int = 8000) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(locale="nl-NL")
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(wait_ms)
        html = page.content()
        browser.close()
    if "Just a moment" in html[:3000] or len(html) < 2000:
        raise RuntimeError(f"Cloudflare challenge for {url}")
    return html


def _fetch_html_resilient(url: str) -> str:
    """Prefer Jina HTML; fall back to Playwright when blocked."""
    try:
        return _jina_html(url)
    except Exception as jina_err:
        try:
            return _playwright_html(url)
        except Exception as pw_err:
            raise RuntimeError(f"html fetch failed jina={jina_err}; playwright={pw_err}") from pw_err


def fetch_etos_api(page: int, *, query: str = QUERY, page_size: int = 48) -> list[dict]:
    """Etos Demandware Search-UpdateGrid (cumulative start/sz; slice per page)."""
    from bs4 import BeautifulSoup

    # Responses are cumulative: start=N returns items 0..(N+sz-1)
    start = (page - 1) * page_size
    url = (
        "https://www.etos.nl/on/demandware.store/Sites-etos-nl-Site/nl_NL/"
        f"Search-UpdateGrid?q={query}&start={start}&sz={page_size}"
    )
    s = _curl_session()
    r = s.get(url, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("a.name-link, a.pdp-link, .pdp-link a, .product-name a"):
        href = a.get("href") or ""
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if not title or "/producten/" not in href:
            continue
        full = urljoin("https://www.etos.nl", href.split("?")[0])
        if full in seen:
            continue
        seen.add(full)
        # Price near tile
        price = None
        tile = a.find_parent(attrs={"data-pid": True}) or a.find_parent(class_=re.compile("product"))
        if tile:
            m = re.search(r"€\s*[\d.,]+", tile.get_text(" ", strip=True))
            if m:
                price = m.group(0).replace(" ", "")
        out.append(
            product(
                rank=0,
                title=title,
                url=full,
                price=price,
                extra={"api": "etos_demandware_grid"},
            )
        )
    # Grid returns cumulative set; keep only this page's slice
    return out[:page_size] if start == 0 else out[-page_size:] if len(out) > page_size else out


def _hybris_products_from_payload(data: dict | object, *, host: str, page: int) -> list[dict]:
    """Normalize Hybris productCategorySearchPage (JSON dict or XML Element)."""
    import xml.etree.ElementTree as ET

    out: list[dict] = []
    if isinstance(data, dict):
        pag = data.get("pagination") or {}
        if pag.get("totalPages") is not None and (page - 1) >= int(pag["totalPages"]):
            return []
        items = data.get("products") or []
        for item in items:
            title = item.get("name") or ""
            if not title:
                continue
            path = item.get("url") or ""
            url = urljoin(host, path) if path else None
            brand = (item.get("masterBrand") or {}).get("name")
            price = (item.get("price") or {}).get("formattedValue")
            out.append(
                product(
                    rank=0,
                    title=title,
                    brand=brand,
                    url=url,
                    price=price,
                    extra={"sku": str(item.get("code") or ""), "api": "hybris_spa"},
                )
            )
        return out

    # XML ElementTree root
    root = data
    pag = root.find("pagination")
    if pag is not None:
        total_pages = int(pag.findtext("totalPages") or "0")
        if page - 1 >= total_pages:
            return []
    for p in root.findall("products"):
        title = p.findtext("name") or ""
        if not title:
            continue
        path = p.findtext("url") or ""
        url = urljoin(host, path) if path else None
        out.append(
            product(
                rank=0,
                title=title,
                brand=p.findtext("masterBrand/name") or None,
                url=url,
                price=p.findtext("price/formattedValue"),
                extra={"sku": p.findtext("code") or "", "api": "hybris_spa"},
            )
        )
    return out


def fetch_kruidvat_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Kruidvat Hybris SPA search (JSON or XML) — conditioner category 30266695."""
    import xml.etree.ElementTree as ET

    s = _curl_session()
    r = s.get(
        "https://api.kruidvat.nl/api/v2/kvn-spa/search",
        params={
            "fields": "FULL",
            "searchType": "PRODUCT",
            "currentPage": page - 1,
            "pageSize": page_size,
            "categoryCode": "30266695",
            "lang": "nl",
            "curr": "EUR",
        },
        headers={"Referer": "https://www.kruidvat.nl/", "Accept": "*/*"},
        timeout=45,
    )
    r.raise_for_status()
    text = r.text.lstrip()
    if text.startswith("{") or text.startswith("["):
        return _hybris_products_from_payload(
            r.json(), host="https://www.kruidvat.nl", page=page
        )
    return _hybris_products_from_payload(
        ET.fromstring(r.text), host="https://www.kruidvat.nl", page=page
    )


def fetch_trekpleister_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Trekpleister Hybris SPA search (JSON) — conditioner category 30267252."""
    s = _curl_session()
    r = s.get(
        "https://api.trekpleister.nl/api/v2/kvtp/search",
        params={
            "fields": "FULL",
            "searchType": "PRODUCT",
            "currentPage": page - 1,
            "pageSize": page_size,
            "categoryCode": "30267252",
            "lang": "nl",
            "curr": "EUR",
        },
        headers={
            "Referer": "https://www.trekpleister.nl/",
            "Accept": "application/json",
        },
        timeout=45,
    )
    r.raise_for_status()
    rows = _hybris_products_from_payload(r.json(), host="https://www.trekpleister.nl", page=page)
    for row in rows:
        row.setdefault("extra", {})["api"] = "trekpleister_hybris"
    return rows


def fetch_douglas_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Douglas BE jsapi product search (NL domain is blocked; map URLs to douglas.nl)."""
    s = _curl_session()
    r = s.get(
        "https://www.douglas.be/jsapi/v2/products/search",
        params={
            "query": query,
            "currentPage": page - 1,
            "pageSize": page_size,
            "fields": "FULL",
            "lang": "nl_BE",
            "curr": "EUR",
        },
        headers={"Accept": "application/json", "Referer": "https://www.douglas.be/"},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    pag = data.get("pagination") or {}
    if pag.get("totalPages") is not None and (page - 1) >= int(pag["totalPages"]):
        return []
    out: list[dict] = []
    for item in data.get("products") or []:
        brand = ((item.get("brand") or {}).get("name") or "").strip()
        line = ((item.get("brandLine") or {}).get("name") or "").strip()
        base = (item.get("baseProductName") or "").strip()
        raw_name = (item.get("name") or "").strip()
        title = " ".join(x for x in (brand, line, base) if x).strip() or raw_name
        if not title or re.fullmatch(r"\d+\s*ml", title, re.I):
            title = " ".join(x for x in (brand, base or raw_name) if x).strip()
        if not title:
            continue
        path = item.get("url") or item.get("baseProductUrl") or ""
        url = urljoin("https://www.douglas.nl", path) if path else None
        if url:
            url = url.replace("https://www.douglas.be", "https://www.douglas.nl")
        price = (item.get("price") or {}).get("formattedValue")
        out.append(
            product(
                rank=0,
                title=title,
                brand=brand or None,
                url=url,
                price=price,
                extra={"sku": str(item.get("code") or ""), "api": "douglas_be_jsapi"},
            )
        )
    return out


def fetch_zalando_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Zalando beauty search HTML via curl_cffi."""
    from bs4 import BeautifulSoup

    s = _curl_session()
    r = s.get(
        "https://www.zalando.nl/beauty/",
        params={"q": query, "p": page},
        timeout=45,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("article a[href$='.html'], a[href*='conditioner'][href$='.html']"):
        href = a.get("href") or ""
        if not href.endswith(".html"):
            continue
        full = urljoin("https://www.zalando.nl", href.split("?")[0])
        if full in seen:
            continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        title = re.sub(
            r"^(Deal|Luxury|Reisformaat|Perfecte combinaties|#OnTrend|K-Beauty|heart_outlined)\s*",
            "",
            title,
            flags=re.I,
        ).strip()
        # Prefer longer text nodes inside article
        art = a.find_parent("article")
        if art:
            texts = [
                re.sub(r"\s+", " ", t.strip())
                for t in art.stripped_strings
                if len(t.strip()) > 12
                and "heart_" not in t
                and t.strip() not in {"Deal", "Luxury", "Meest getoond"}
            ]
            for t in texts:
                if "conditioner" in t.casefold() or len(t) > len(title):
                    title = re.sub(r"€\s*[\d.,]+.*$", "", t).strip()
                    break
        if not title or len(title) < 8:
            continue
        if "conditioner" not in title.casefold() and "conditioner" not in full.casefold():
            continue
        seen.add(full)
        price = None
        m = re.search(r"€\s*[\d.,]+", (art or a).get_text(" ", strip=True))
        if m:
            price = m.group(0).replace(" ", "")
        out.append(
            product(
                rank=0,
                title=title[:200],
                url=full,
                price=price,
                extra={"api": "zalando_beauty_html"},
            )
        )
        if len(out) >= page_size:
            break
    return out


def fetch_ici_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """ICI Paris XL conditioner category PLP (0-based currentPage)."""
    from bs4 import BeautifulSoup

    s = _curl_session()
    s.get("https://www.iciparisxl.nl/", timeout=30)
    r = s.get(
        "https://www.iciparisxl.nl/haar/haarverzorging/conditioner/c/050103",
        params={"currentPage": page - 1},
        timeout=45,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/p/"]'):
        href = a.get("href") or ""
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        title = re.sub(r"^(Only Online)\s+", "", title, flags=re.I)
        if len(title) < 8:
            continue
        full = urljoin("https://www.iciparisxl.nl", href.split("?")[0])
        if full in seen:
            continue
        seen.add(full)
        out.append(
            product(
                rank=0,
                title=title[:200],
                url=full,
                extra={"api": "ici_category_html"},
            )
        )
        if len(out) >= page_size:
            break
    return out


_plus_session = None
_plus_api_version: str | None = None
_plus_module_version: str | None = None


def _plus_bootstrap():
    """Anonymous OutSystems session + version tokens for Plus PLP DataAction."""
    global _plus_session, _plus_api_version, _plus_module_version
    if _plus_session and _plus_api_version and _plus_module_version:
        return _plus_session, _plus_module_version, _plus_api_version

    s = _curl_session()
    s.get("https://www.plus.nl/zoekresultaten?SearchTerm=conditioner", timeout=45)
    mv = requests.get(
        "https://www.plus.nl/moduleservices/moduleversioninfo",
        headers={"User-Agent": UA},
        timeout=30,
    ).json()["versionToken"]
    # apiVersion is embedded next to the DataAction name in the PLP MVC script
    html = s.get("https://www.plus.nl/zoekresultaten?SearchTerm=conditioner", timeout=45).text
    m = re.search(
        r"ECP_Composition_CW\.ProductLists\.PLP_Content\.mvc\.js\?([^\"'\s]+)",
        html,
    )
    script_url = (
        "https://www.plus.nl/scripts/ECP_Composition_CW.ProductLists.PLP_Content.mvc.js"
        + (f"?{m.group(1)}" if m else "")
    )
    js = s.get(script_url, timeout=60).text
    am = re.search(
        r'callDataAction\("DataActionGetProductListAndCategoryInfo"[^,]*,[^,]*,\s*"([^"]+)"',
        js,
    )
    if not am:
        am = re.search(
            r"DataActionGetProductListAndCategoryInfo\",\s*\"[^\"]+\",\s*\"([^\"]+)\"",
            js,
        )
    av = am.group(1) if am else "cafT+CKg7ockKx+9Kx_BsQ"
    # Bootstrap anonymous CSRF cookie
    csrf = "T6C+9iB49TLra4jEsMeSckDMNhQ="
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-CSRFToken": csrf,
        "Referer": "https://www.plus.nl/zoekresultaten?SearchTerm=conditioner",
        "Origin": "https://www.plus.nl",
        "Accept": "application/json",
    }
    ready = {
        "versionInfo": {"moduleVersion": mv, "apiVersion": "rz5rJWRik75W_E181ghbKQ"},
        "viewName": "*",
        "inputParameters": {
            "OWGUID": "",
            "FeatureToggle_DataVersion": {
                "Convert_SyncDataVersion": "1900-01-01T00:00:00",
                "Attract_SyncDataVersion": "1900-01-01T00:00:00",
            },
        },
    }
    s.post(
        "https://www.plus.nl/screenservices/ECOP/ActionOnApplicationReady_Server",
        json=ready,
        headers=headers,
        timeout=45,
    )
    _plus_session = s
    _plus_module_version = mv
    _plus_api_version = av
    return s, mv, av


def fetch_plus_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Plus OutSystems ScreenServices PLP DataAction."""
    s, mv, av = _plus_bootstrap()
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-CSRFToken": "T6C+9iB49TLra4jEsMeSckDMNhQ=",
        "Referer": f"https://www.plus.nl/zoekresultaten?SearchTerm={query}&PageNumber={page}",
        "Origin": "https://www.plus.nl",
        "Accept": "application/json",
    }
    body = {
        "versionInfo": {"moduleVersion": mv, "apiVersion": av},
        "viewName": "MainFlow.SearchPage",
        "screenData": {
            "variables": {
                "SearchKeyword": query,
                "PageNumber": page,
                "URLPageNumber": page,
                "IsSearch": True,
                "StoreNumber": 0,
                "StoreChannel": "",
                "SelectedSort": "",
                "FilterQueryURL": "",
                "CategorySlug": "",
                "LocalCategoryID": 0,
            }
        },
    }
    r = s.post(
        "https://www.plus.nl/screenservices/ECP_Composition_CW/ProductLists/"
        "PLP_Content/DataActionGetProductListAndCategoryInfo",
        json=body,
        headers=headers,
        timeout=45,
    )
    r.raise_for_status()
    data = (r.json() or {}).get("data") or {}
    total_pages = int(data.get("TotalPages") or 0)
    if total_pages and page > total_pages:
        return []
    out: list[dict] = []
    for row in ((data.get("ProductList") or {}).get("List") or []):
        item = row.get("PLP_Str") or row
        title = item.get("Name") or ""
        if not title:
            continue
        slug = item.get("Slug") or ""
        url = f"https://www.plus.nl/product/{slug}" if slug else None
        raw_price = item.get("OriginalPrice") or item.get("NewPrice")
        price = None
        try:
            if raw_price is not None and float(raw_price) > 0:
                price = _euro(float(raw_price))
        except (TypeError, ValueError):
            price = None
        out.append(
            product(
                rank=0,
                title=title,
                brand=item.get("Brand") or None,
                url=url,
                price=price,
                extra={"sku": str(item.get("SKU") or ""), "api": "plus_outsystems"},
            )
        )
    return out


def _ddg_site_products(
    domain: str,
    page: int,
    *,
    query: str = QUERY,
    page_size: int = PAGE_SIZE,
    path_hint: str | None = None,
) -> list[dict]:
    """DuckDuckGo site: search for product URLs when origin/Jina are blocked."""
    from bs4 import BeautifulSoup
    from urllib.parse import unquote

    brands = [
        query,
        f"{query} syoss",
        f"{query} gliss",
        f"{query} schwarzkopf",
        f"{query} olaplex",
        f"{query} kerastase",
        f"{query} elvive",
        f"{query} klorane",
        f"{query} andrelon",
        f"{query} guhl",
    ]
    # Rotate brand queries across pages so pagination stays useful
    q = brands[(page - 1) % len(brands)] + f" site:{domain}"
    start = ((page - 1) // len(brands)) * 30
    s = _curl_session()
    r = s.get(
        "https://html.duckduckgo.com/html/",
        params={"q": q, "s": str(start)},
        timeout=45,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("a.result__a"):
        title = a.get_text(strip=True)
        href = a.get("href") or ""
        if "uddg=" in href:
            href = unquote(href.split("uddg=")[1].split("&")[0])
        if domain not in href:
            continue
        if any(x in href for x in ("/merk/", "/cat/", "/search", "y.js", "duckduckgo.com")):
            continue
        if path_hint and path_hint not in href and query not in href.casefold():
            # keep product-looking paths
            if href.rstrip("/").count("/") < 3:
                continue
        title = re.sub(rf"\s*[\|\-–]\s*{re.escape(domain.split('.')[0])}.*$", "", title, flags=re.I)
        title = re.sub(r"\s*\|\s*.*$", "", title).strip()
        if len(title) < 5:
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(
            product(
                rank=0,
                title=title[:200],
                url=href,
                extra={"api": f"ddg_site_{domain}"},
            )
        )
        if len(out) >= page_size:
            break
    return out


def fetch_notino_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Notino search via Jina reader (direct/CF blocked); DDG site fallback."""
    if page == 1:
        url = f"https://www.notino.nl/search.asp?exps={query}"
    else:
        url = f"https://www.notino.nl/search.asp?exps={query}&f=1-{page}-3649"
    text = None
    try:
        text = _jina_md(url)
    except Exception:
        # Reuse previously scraped page cache when available
        legacy = Path(__file__).resolve().parents[1] / "data" / "raw" / "pages" / "notino.nl" / f"page_{page:02d}.txt"
        if legacy.exists():
            text = legacy.read_text(encoding="utf-8", errors="ignore")
    out: list[dict] = []
    seen: set[str] = set()
    if text:
        for m in re.finditer(
            r"##\s+([^\n#]+)\s+###\s+([^\n\[]+).*?\]\((https://www\.notino\.nl/[^)]+)\)",
            text,
            re.S,
        ):
            brand = m.group(1).strip()
            name = re.sub(r"\s+\d[,\d]*€.*$", "", m.group(2)).strip()
            name = re.sub(r"\s+\d,\d\(\d+\).*$", "", name).strip()
            name = re.split(r"\s+van\s+€|\s+Dit product", name)[0].strip()
            title = f"{brand} {name}".strip()
            link = m.group(3).split("?")[0]
            if link in seen:
                continue
            if "wimper" in title.casefold() or "lash" in title.casefold():
                continue
            seen.add(link)
            out.append(
                product(
                    rank=0,
                    title=title[:200],
                    brand=brand,
                    url=link,
                    extra={"api": "notino_jina_search"},
                )
            )
        if not out:
            for link in re.findall(
                r"\]\((https://www\.notino\.nl/[a-z0-9-]+/[a-z0-9-]+(?:/p-\d+)?/)\)",
                text,
            ):
                if link in seen or "/search" in link:
                    continue
                seen.add(link)
                out.append(
                    product(
                        rank=0,
                        title=_slug_title(link),
                        url=link,
                        extra={"api": "notino_jina_search"},
                    )
                )
    if out:
        return out[:page_size]
    return _ddg_site_products("notino.nl", page, query=query, page_size=page_size)


def fetch_newpharma_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Newpharma conditioner category via Jina HTML; DDG site fallback."""
    from bs4 import BeautifulSoup

    base = (
        "https://www.newpharma.nl/cat/schoonheids-en-cosmetica/haarverzorging/"
        "conditioner-verzorging/12-172-1705.html"
    )
    url = base if page == 1 else f"{base}?page={page}"
    out: list[dict] = []
    seen: set[str] = set()
    try:
        soup = BeautifulSoup(_fetch_html_resilient(url), "html.parser")
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").split("#")[0]
            m = re.match(
                r"https://www\.newpharma\.nl/([a-z0-9-]+)/(\d+)/([a-z0-9-]+)\.html$",
                href,
            )
            if not m:
                continue
            title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if len(title) < 8:
                title = m.group(3).replace("-", " ").title()
            low = title.casefold()
            if not (
                "conditioner" in low
                or "crèmespoeling" in low
                or "cremespoeling" in low
                or "spoeling" in low
                or "balsem" in low
            ):
                continue
            if href in seen:
                continue
            seen.add(href)
            out.append(
                product(
                    rank=0,
                    title=title[:200],
                    brand=m.group(1).replace("-", " ").title(),
                    url=href,
                    extra={"sku": m.group(2), "api": "newpharma_jina_category"},
                )
            )
            if len(out) >= page_size:
                break
    except Exception:
        out = []
    if out:
        return out
    return _ddg_site_products("newpharma.nl", page, query=query, page_size=page_size)


def fetch_drogeriedepot_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Drogeriedepot conditioner category via Jina HTML; DDG site fallback."""
    from bs4 import BeautifulSoup

    url = f"https://www.drogeriedepot.nl/c/Haarverzorging-Kleuren/Conditioner/?p={page}"
    out: list[dict] = []
    seen: set[str] = set()
    try:
        soup = BeautifulSoup(_fetch_html_resilient(url), "html.parser")
        for a in soup.select('a[href*="/haarverzorging-kleuren/conditioner/"]'):
            href = (a.get("href") or "").split("?")[0]
            title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if len(title) < 5:
                continue
            if href.rstrip("/").endswith("conditioner"):
                continue
            full = urljoin("https://www.drogeriedepot.nl", href)
            if full in seen:
                continue
            seen.add(full)
            out.append(
                product(
                    rank=0,
                    title=title[:200],
                    url=full,
                    extra={"api": "drogeriedepot_jina_category"},
                )
            )
            if len(out) >= page_size:
                break
    except Exception:
        out = []
    if out:
        return out
    return _ddg_site_products(
        "drogeriedepot.nl",
        page,
        query="spülung OR conditioner",
        page_size=page_size,
    )


def fetch_parfumselect_api(page: int, *, query: str = QUERY, page_size: int = PAGE_SIZE) -> list[dict]:
    """Parfumselect is origin-down (522); DuckDuckGo site index for product URLs."""
    return _ddg_site_products("parfumselect.nl", page, query=query, page_size=page_size)


API_FETCHERS: dict[str, Callable[..., list[dict]]] = {
    "jumbo.com": fetch_jumbo_api,
    "da.nl": fetch_da_api,
    "koopjesdrogisterij.nl": fetch_koopjes_api,
    "ah.nl": fetch_ah_api,
    "bol.com": fetch_bol_sitemap,
    "dirk.nl": fetch_dirk_sitemap,
    "plein.nl": fetch_plein_sitemap,
    "etos.nl": fetch_etos_api,
    "kruidvat.nl": fetch_kruidvat_api,
    "trekpleister.nl": fetch_trekpleister_api,
    "douglas.nl": fetch_douglas_api,
    "zalando.nl": fetch_zalando_api,
    "iciparisxl.nl": fetch_ici_api,
    "plus.nl": fetch_plus_api,
    "notino.nl": fetch_notino_api,
    "newpharma.nl": fetch_newpharma_api,
    "drogeriedepot.nl": fetch_drogeriedepot_api,
    "parfumselect.nl": fetch_parfumselect_api,
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