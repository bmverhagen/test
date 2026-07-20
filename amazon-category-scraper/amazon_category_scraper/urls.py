"""URL classification helpers.

The scraper only ever downloads Amazon *category* pages (search result
listings, browse nodes, best-seller lists). Product detail pages are
explicitly rejected so the tool cannot be pointed at them, by accident or
otherwise.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

__all__ = [
    "NotACategoryPageError",
    "ensure_category_url",
    "is_category_url",
    "is_product_url",
    "sibling_search_listing",
    "with_full_store",
    "with_page",
]


class NotACategoryPageError(ValueError):
    """Raised when a URL is not an Amazon category/listing page."""


# Path markers that identify a product detail page. These are never scraped.
_PRODUCT_PATH_MARKERS = (
    "/dp/",
    "/gp/product/",
    "/gp/aw/d/",
    "/exec/obidos/asin/",
    "/product-reviews/",
    "/ask/questions/",
)

# Second path segment values that mark a category-style listing under /gp/.
_GP_CATEGORY_SEGMENTS = {
    "browse.html",
    "bestsellers",
    "new-releases",
    "movers-and-shakers",
    "most-wished-for",
    "most-gifted",
}

# Markers that can appear anywhere in the path of a category-style listing,
# e.g. /Best-Sellers-Electronics-Televisions/zgbs/electronics/172282
_CATEGORY_PATH_MARKERS = (
    "/zgbs",
    "/bestsellers",
    "/new-releases",
    "/movers-and-shakers",
    "/most-wished-for",
)


def _normalized_path(raw_path: str) -> str:
    """Strip locale prefixes such as ``/-/en`` used on some marketplaces."""
    path = raw_path or "/"
    if path.startswith("/-/"):
        parts = path.split("/", 3)
        path = "/" + (parts[3] if len(parts) > 3 else "")
    return path


def _is_amazon_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    return "amazon" in hostname.lower().split(".")


def is_product_url(url: str) -> bool:
    """Return True when *url* points at a product detail page."""
    path = _normalized_path(urlparse(url).path).lower()
    if not path.endswith("/"):
        path += "/"
    return any(marker in path for marker in _PRODUCT_PATH_MARKERS)


def is_category_url(url: str) -> bool:
    """Return True when *url* is an Amazon category/listing page."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not _is_amazon_host(parsed.hostname):
        return False
    if is_product_url(url):
        return False

    path = _normalized_path(parsed.path)
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    first = segments[0].lower()
    if first in {"s", "b"}:
        return True
    if first == "gp" and len(segments) >= 2 and segments[1].lower() in _GP_CATEGORY_SEGMENTS:
        return True

    lowered = path.lower()
    return any(marker in lowered for marker in _CATEGORY_PATH_MARKERS)


def ensure_category_url(url: str) -> str:
    """Validate that *url* is an Amazon category page, else raise.

    Raises:
        NotACategoryPageError: for product pages and anything else that is
            not a recognized Amazon category/listing page.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise NotACategoryPageError(f"Not a valid http(s) URL: {url!r}")
    if not _is_amazon_host(parsed.hostname):
        raise NotACategoryPageError(f"Not an Amazon URL: {url!r}")
    if is_product_url(url):
        raise NotACategoryPageError(
            f"Refusing to scrape a product page: {url!r}. "
            "This tool only scrapes category pages (e.g. https://www.amazon.com/s?rh=n%3A172282 "
            "or https://www.amazon.com/b?node=172282)."
        )
    if not is_category_url(url):
        raise NotACategoryPageError(
            f"Not an Amazon category page: {url!r}. Supported pages are search/category "
            "listings (/s?...), browse nodes (/b?node=...), and best-seller style lists "
            "(/gp/bestsellers/..., .../zgbs/...)."
        )
    return url


def with_page(url: str, page: int) -> str:
    """Return *url* with its ``page`` query parameter set to *page*."""
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "page"]
    if page > 1:
        query.append(("page", str(page)))
    return urlunparse(parsed._replace(query=urlencode(query)))


def sibling_search_listing(url: str) -> str | None:
    """Return the search listing URL for the node of a best-seller page.

    Best-seller pages (``.../zgbs/<group>/<node>``, ``/gp/bestsellers/...``)
    carry no brand data, but the same browse node has a regular search
    listing (``/s?rh=n%3A<node>&fs=true``) — also a category page — whose
    sidebar and product cards do list brands. Returns None when the URL
    contains no numeric node id.
    """
    parsed = urlparse(url)
    lowered = _normalized_path(parsed.path).lower()
    if not any(marker in lowered for marker in _CATEGORY_PATH_MARKERS + ("/bestsellers",)):
        return None
    node = None
    for segment in _normalized_path(parsed.path).split("/"):
        if segment.isdigit():
            node = segment
    if node is None:
        return None
    return urlunparse(parsed._replace(path="/s", query=f"rh=n%3A{node}&fs=true", fragment=""))


def with_full_store(url: str) -> str:
    """Add ``fs=true`` to node-only ``/s`` searches so they render server-side.

    A ``/s?rh=n%3A<node>`` URL without a keyword (``k``) returns an empty HTML
    shell that Amazon fills in client-side. Adding ``fs=true`` — exactly what
    Amazon's own "See all results" category links carry — returns the fully
    rendered listing. URLs with a keyword, an existing ``fs``, or non-search
    paths are returned unchanged.
    """
    parsed = urlparse(url)
    segments = [segment for segment in _normalized_path(parsed.path).split("/") if segment]
    if segments != ["s"]:
        return url
    query = parse_qsl(parsed.query, keep_blank_values=True)
    keys = {key for key, _ in query}
    if "k" in keys or "fs" in keys:
        return url
    if not any(key == "rh" and value.startswith("n:") for key, value in query):
        return url
    query.append(("fs", "true"))
    return urlunparse(parsed._replace(query=urlencode(query)))
