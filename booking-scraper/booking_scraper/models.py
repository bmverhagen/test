"""Data structures for Booking.com search results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchQuery:
    """Parameters for a Booking.com searchresults query."""

    destination: str = "Zwarte Woud"
    dest_id: str = "1477"
    dest_type: str = "region"
    checkin: str = "2026-08-26"
    checkout: str = "2026-08-29"
    adults: int = 2
    children: int = 0
    rooms: int = 1
    currency: str = "EUR"
    lang: str = "nl"
    max_total_price: float | None = 500.0
    min_total_price: float | None = None
    min_review_score: float = 9.0
    breakfast: bool = True
    swimming_pool: bool = True
    balcony: bool = True
    terrace: bool = False
    balcony_or_terrace: bool = False
    free_cancellation: bool = False
    parking: bool = False
    spa: bool = False
    sauna: bool = False
    pets_allowed: bool = False
    good_breakfast: bool = False
    stars: tuple[int, ...] = ()
    property_types: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    extra_filters: tuple[str, ...] = ()
    raw_nflt: tuple[str, ...] = ()
    order: str = "price"
    # When False, skip the approximate per-night price chip (client filter only).
    apply_price_chip: bool = True

    @property
    def nights(self) -> int:
        from datetime import date

        start = date.fromisoformat(self.checkin)
        end = date.fromisoformat(self.checkout)
        return (end - start).days


@dataclass(frozen=True)
class PropertyResult:
    """One accommodation card from the search results page."""

    name: str
    url: str
    location: str | None
    review_score: float | None
    review_count: int | None
    room_name: str | None
    price_per_night: float | None
    price_total: float | None
    currency: str
    breakfast_included: bool
    room_mentions_balcony: bool
    rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchReport:
    """Aggregated result of a scraping run."""

    query: SearchQuery
    search_url: str
    properties: list[PropertyResult]
    pages_scraped: int
    cards_seen: int
    scraped_at: str
    result_header: str | None = None
    nflt: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": asdict(self.query),
            "search_url": self.search_url,
            "nflt": self.nflt,
            "scraped_at": self.scraped_at,
            "result_header": self.result_header,
            "pages_scraped": self.pages_scraped,
            "cards_seen": self.cards_seen,
            "matches": len(self.properties),
            "errors": self.errors,
            "properties": [prop.to_dict() for prop in self.properties],
        }
