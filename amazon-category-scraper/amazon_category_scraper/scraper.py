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
from datetime import datetime, timezone

from .fetcher import Fetcher, FetchError
from .models import BrandRecord, PageResult, ScrapeReport
from .parser import parse_category_page
from .urls import ensure_category_url, is_category_url, with_full_store

__all__ = ["CategoryBrandScraper", "merge_pages"]

logger = logging.getLogger(__name__)

DEFAULT_DELAY = 2.5


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

    return ScrapeReport(
        category_urls=category_urls,
        pages_scraped=len(pages),
        product_cards_seen=sum(page_result.total_cards for page_result in pages),
        brands=brands,
        scraped_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

    def _iter_category_pages(self, category_url: str, errors: list[str]) -> list[PageResult]:
        """Fetch up to ``max_pages`` listing pages for one category URL."""
        results: list[PageResult] = []
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
            if (
                result.total_cards
                and not result.cards_with_brand
                and not result.refinement_brands
                and not result.structured_data_brands
            ):
                logger.warning(
                    "%s exposes no brand information (best-seller style pages "
                    "don't include brand names). Try the category's search "
                    "listing instead, e.g. https://www.amazon.com/s?rh=n%%3A<node-id>",
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
