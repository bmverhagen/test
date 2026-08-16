"""Direct backend/API fetchers for shops that expose JSON/GraphQL search."""

from __future__ import annotations

import html
import time
import uuid
from typing import Callable
from urllib.parse import urljoin

import requests

try:
    from .brands import product
except ImportError:
    from brands import product

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
QUERY = "conditioner"
PAGE_SIZE = 24


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


API_FETCHERS: dict[str, Callable[..., list[dict]]] = {
    "jumbo.com": fetch_jumbo_api,
    "da.nl": fetch_da_api,
    "koopjesdrogisterij.nl": fetch_koopjes_api,
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
