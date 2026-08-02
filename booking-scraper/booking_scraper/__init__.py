"""Booking.com scraper for Black Forest (Zwarte Woud) stays."""

from .capla import GRAPHQL_ENDPOINT, extract_capla_store, parse_capla_store
from .filters import FILTER_ALIASES, load_filter_catalog, resolve_alias
from .models import PropertyResult, SearchQuery, SearchReport
from .scraper import BookingScraper

__all__ = [
    "BookingScraper",
    "FILTER_ALIASES",
    "GRAPHQL_ENDPOINT",
    "PropertyResult",
    "SearchQuery",
    "SearchReport",
    "extract_capla_store",
    "load_filter_catalog",
    "parse_capla_store",
    "resolve_alias",
]

__version__ = "1.0.0"
