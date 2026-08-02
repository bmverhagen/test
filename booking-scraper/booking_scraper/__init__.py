"""Booking.com scraper for Black Forest (Zwarte Woud) stays."""

from .capla import GRAPHQL_ENDPOINT, extract_capla_store, parse_capla_store
from .models import PropertyResult, SearchQuery, SearchReport
from .scraper import BookingScraper

__all__ = [
    "BookingScraper",
    "GRAPHQL_ENDPOINT",
    "PropertyResult",
    "SearchQuery",
    "SearchReport",
    "extract_capla_store",
    "parse_capla_store",
]

__version__ = "1.0.0"
