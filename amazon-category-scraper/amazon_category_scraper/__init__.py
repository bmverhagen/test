"""Scrape brand names from Amazon category pages (never product pages)."""

from .fetcher import BlockedError, FetchError, Fetcher
from .models import BrandRecord, PageResult, ScrapeReport
from .parser import parse_category_page
from .scraper import CategoryBrandScraper, merge_pages
from .urls import NotACategoryPageError, ensure_category_url, is_category_url, is_product_url

__version__ = "1.0.0"

__all__ = [
    "BlockedError",
    "BrandRecord",
    "CategoryBrandScraper",
    "FetchError",
    "Fetcher",
    "NotACategoryPageError",
    "PageResult",
    "ScrapeReport",
    "ensure_category_url",
    "is_category_url",
    "is_product_url",
    "merge_pages",
    "parse_category_page",
]
