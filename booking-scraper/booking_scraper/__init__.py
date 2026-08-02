"""Booking.com scraper for Black Forest (Zwarte Woud) stays."""

from .models import PropertyResult, SearchQuery, SearchReport
from .scraper import BookingScraper

__all__ = [
    "BookingScraper",
    "PropertyResult",
    "SearchQuery",
    "SearchReport",
]

__version__ = "1.0.0"
