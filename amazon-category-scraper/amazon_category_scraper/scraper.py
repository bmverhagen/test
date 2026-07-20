"""Orchestrates fetching and parsing of category pages.

Pagination only ever follows the category listing's own "next page" link, so
the scraper never leaves listing pages and product detail pages are never
requested.
"""

from __future__ import annotations

import logging
import random
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone

from .fetcher import Fetcher, FetchError
from .models import BrandRecord, PageResult, ProductEntry, ScrapeReport
from .parser import parse_category_page, resolve_product_brands
from .urls import ensure_category_url, is_category_url, sibling_search_listing, with_full_store

__all__ = ["CategoryBrandScraper", "merge_pages"]

logger = logging.getLogger(__name__)

DEFAULT_DELAY = 2.5


def _renumber_listing_ranks(results: list[PageResult]) -> None:
    """Make listing positions continue across pages of one category chain.

    Search listings restart the position count on every page; best-seller
    pages already carry global ranks (#31 on page 2) and are left untouched.
    """
    offset = 0
    for result in results:
        if not result.is_best_seller_list:
            result.products = [
                replace(product, rank=offset + position)
                for position, product in enumerate(result.products, start=1)
            ]
        offset += result.total_cards


def merge_pages(
    pages: list[PageResult],
    category_urls: list[str],
    errors: list[str] | None = None,
) -> ScrapeReport:
    """Aggregate per-page results into a single deduplicated brand report."""
    mentions: Counter[str] = Counter()
    display_name: dict[str, str] = {}
    sources: dict[str, set[str]] = {}

    def register(name: str, source: str, count: int = 0) -> None:
        key = name.casefold()
        display_name.setdefault(key, name)
        sources.setdefault(key, set()).add(source)
        mentions[key] += count

    for page_result in pages:
        for name in page_result.refinement_brands:
            register(name, "brand_filter")
        for name in page_result.product_brands:
            register(name, "product_card", count=1)
        for name in page_result.structured_data_brands:
            register(name, "structured_data")

    brands = [
        BrandRecord(
            name=display_name[key],
            product_mentions=mentions[key],
            sources=tuple(sorted(sources[key])),
        )
        for key in display_name
    ]
    brands.sort(key=lambda record: (-record.product_mentions, record.name.casefold()))

    products: list[ProductEntry] = []
    for page_result in pages:
        products.extend(page_result.products)

    return ScrapeReport(
        category_urls=category_urls,
        pages_scraped=len(pages),
        product_cards_seen=sum(page_result.total_cards for page_result in pages),
        brands=brands,
        scraped_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        products=products,
        errors=list(errors or []),
    )


class CategoryBrandScraper:
    """Scrape brand names from one or more Amazon category pages."""

    def __init__(
        self,
        fetcher: Fetcher | None = None,
        delay: float = DEFAULT_DELAY,
        max_pages: int = 1,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        self.fetcher = fetcher or Fetcher()
        self.delay = delay
        self.max_pages = max_pages

    def _sleep(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay + random.uniform(0, self.delay / 2))

    # Listing pages fetched to build the brand vocabulary for one BSR chain.
    VOCABULARY_PAGES = 2

    def _known_brands_for_node(self, category_url: str, errors: list[str]) -> list[str]:
        """Harvest brand names from the search listing of the same node.

        Best-seller pages carry no brand data, so brands are collected from
        the sibling ``/s?rh=n%3A<node>`` listing — itself a category page —
        and later matched against best-seller product titles. A couple of
        listing pages are read because the brand sidebar varies per request.
        """
        url = sibling_search_listing(category_url)
        if url is None:
            return []

        brands: list[str] = []
        seen: set[str] = set()
        for _ in range(self.VOCABULARY_PAGES):
            self._sleep()
            logger.info("Fetching brand vocabulary from the node's search listing: %s", url)
            try:
                html = self.fetcher.fetch(url)
            except FetchError as exc:
                logger.warning("Could not fetch %s (%s); best-seller brands may be missing", url, exc)
                errors.append(str(exc))
                break
            listing = parse_category_page(html, url=url)
            for name in (
                listing.refinement_brands + listing.product_brands + listing.structured_data_brands
            ):
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    brands.append(name)
            next_url = listing.next_page_url
            if next_url is None or not is_category_url(next_url):
                break
            url = next_url

        logger.info("Learned %d brand names from the node's search listing", len(brands))
        return brands

    def _iter_category_pages(self, category_url: str, errors: list[str]) -> list[PageResult]:
        """Fetch up to ``max_pages`` listing pages for one category URL."""
        results: list[PageResult] = []
        known_brands: list[str] | None = None
        # Node-only searches (/s?rh=n%3A...) without fs=true come back as an
        # empty shell that renders client-side; fs=true ("full store", what
        # Amazon's own "See all results" links use) returns full markup.
        url = with_full_store(category_url)
        if url != category_url:
            logger.info("Using full-store variant of the category URL: %s", url)

        for page in range(1, self.max_pages + 1):
            if page > 1:
                self._sleep()
            logger.info("Fetching category page %d: %s", page, url)
            try:
                html = self.fetcher.fetch(url)
            except FetchError as exc:
                logger.error("%s", exc)
                errors.append(str(exc))
                break

            result = parse_category_page(html, url=url, page=page)
            logger.info(
                "Page %d: %d product cards, %d with a brand, %d sidebar brands",
                page,
                result.total_cards,
                result.cards_with_brand,
                len(result.refinement_brands),
            )

            if result.is_best_seller_list and result.cards_with_brand < result.total_cards:
                if known_brands is None:
                    known_brands = self._known_brands_for_node(category_url, errors)
                resolved = resolve_product_brands(result, known_brands)
                logger.info(
                    "Resolved %d/%d best-seller brands (vocabulary of %d + guesses)",
                    resolved,
                    result.total_cards,
                    len(known_brands),
                )
            if result.total_cards and not result.cards_with_brand and not result.refinement_brands:
                logger.warning(
                    "%s exposes no brand information and no brands could be "
                    "matched from the node's search listing.",
                    url,
                )
            results.append(result)

            if page == self.max_pages:
                break
            # Only follow the listing's own "next page" link; never guess
            # URLs, so the scraper cannot walk past the last page.
            next_url = result.next_page_url
            if next_url is None:
                logger.info("No next-page link; reached the last listing page.")
                break
            # Never follow a link that leads off the category listing.
            if not is_category_url(next_url):
                logger.info("Next-page link is not a category page, stopping: %s", next_url)
                break
            url = next_url

        _renumber_listing_ranks(results)
        return results

    def collect_pages(self, category_urls: list[str]) -> tuple[list[PageResult], list[str]]:
        """Fetch and parse all pages; returns (page results, error messages).

        Every URL is validated first: product pages raise
        :class:`~amazon_category_scraper.urls.NotACategoryPageError`.
        """
        validated = [ensure_category_url(url) for url in category_urls]
        errors: list[str] = []
        pages: list[PageResult] = []
        for index, url in enumerate(validated):
            if index:
                self._sleep()
            pages.extend(self._iter_category_pages(url, errors))
        return pages, errors

    def scrape(self, category_urls: list[str]) -> ScrapeReport:
        """Scrape every URL (each must be a category page) and merge brands."""
        validated = [ensure_category_url(url) for url in category_urls]
        pages, errors = self.collect_pages(validated)
        return merge_pages(pages, validated, errors)
