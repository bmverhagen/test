"""Orchestrate Booking.com search scraping and post-filtering."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import replace
from datetime import datetime, timezone

from .fetcher import FetchError, PlaywrightFetcher
from .models import PropertyResult, SearchQuery, SearchReport
from .parser import parse_search_results
from .urls import build_search_url

logger = logging.getLogger(__name__)

PAGE_SIZE = 25
DEFAULT_DELAY = 2.0
DEFAULT_MAX_PAGES = 10


def matches_query(prop: PropertyResult, query: SearchQuery) -> bool:
    """Apply client-side filters on top of Booking's nflt chips."""
    if prop.price_total is None:
        return False
    if prop.price_total > query.max_total_price:
        return False
    if prop.review_score is not None and prop.review_score < query.min_review_score:
        return False
    if query.breakfast and not prop.breakfast_included:
        return False
    return True


class BookingScraper:
    """Scrape Booking.com search results for a configured stay."""

    def __init__(
        self,
        query: SearchQuery | None = None,
        *,
        fetcher: PlaywrightFetcher | None = None,
        delay: float = DEFAULT_DELAY,
        max_pages: int = DEFAULT_MAX_PAGES,
        require_room_balcony_text: bool = False,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        self.query = query or SearchQuery()
        self.fetcher = fetcher
        self.delay = delay
        self.max_pages = max_pages
        self.require_room_balcony_text = require_room_balcony_text

    def _sleep(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay + random.uniform(0, self.delay / 2))

    def _filter(self, properties: list[PropertyResult]) -> list[PropertyResult]:
        matched = [prop for prop in properties if matches_query(prop, self.query)]
        if self.require_room_balcony_text:
            matched = [prop for prop in matched if prop.room_mentions_balcony]
        matched.sort(
            key=lambda prop: (
                prop.price_total if prop.price_total is not None else 1e12,
                -(prop.review_score or 0),
                prop.name.casefold(),
            )
        )
        return matched

    def scrape_html(self, html: str, *, search_url: str | None = None) -> SearchReport:
        """Parse already-fetched HTML (useful for tests / offline runs)."""
        properties, header = parse_search_results(html)
        matched = self._filter(properties)
        return SearchReport(
            query=self.query,
            search_url=search_url or build_search_url(self.query),
            properties=matched,
            pages_scraped=1,
            cards_seen=len(properties),
            scraped_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            result_header=header,
        )

    def scrape(self) -> SearchReport:
        """Fetch live Booking.com pages and return filtered matches."""
        owns_fetcher = self.fetcher is None
        fetcher = self.fetcher or PlaywrightFetcher(locale="nl-NL")
        errors: list[str] = []
        all_cards: list[PropertyResult] = []
        header: str | None = None
        pages = 0
        first_url = build_search_url(self.query)

        try:
            context_mgr = fetcher if owns_fetcher else _NullContext(fetcher)
            with context_mgr as active:
                for page_index in range(self.max_pages):
                    offset = page_index * PAGE_SIZE
                    url = build_search_url(self.query, offset=offset)
                    try:
                        html = active.fetch_html(url)
                    except FetchError as exc:
                        errors.append(str(exc))
                        logger.error("Fetch failed at offset %s: %s", offset, exc)
                        break

                    properties, page_header = parse_search_results(html)
                    pages += 1
                    if page_header:
                        header = page_header
                    if not properties:
                        break

                    # Keep absolute rank across pages.
                    for prop in properties:
                        all_cards.append(
                            replace(prop, rank=offset + (prop.rank or 0))
                        )

                    if len(properties) < PAGE_SIZE:
                        break
                    if page_index + 1 < self.max_pages:
                        self._sleep()
        except FetchError as exc:
            errors.append(str(exc))

        matched = self._filter(all_cards)
        return SearchReport(
            query=self.query,
            search_url=first_url,
            properties=matched,
            pages_scraped=pages,
            cards_seen=len(all_cards),
            scraped_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            result_header=header,
            errors=errors,
        )


class _NullContext:
    """No-op context manager when the caller owns the fetcher lifecycle."""

    def __init__(self, fetcher: PlaywrightFetcher) -> None:
        self.fetcher = fetcher

    def __enter__(self) -> PlaywrightFetcher:
        return self.fetcher

    def __exit__(self, *exc: object) -> None:
        return None
