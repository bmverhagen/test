"""Data structures shared across the scraper."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrandRecord:
    """A brand discovered on one or more category pages."""

    name: str
    product_mentions: int
    sources: tuple[str, ...]


@dataclass
class PageResult:
    """Everything extracted from a single category page."""

    url: str
    page: int
    refinement_brands: list[str] = field(default_factory=list)
    product_brands: list[str] = field(default_factory=list)
    structured_data_brands: list[str] = field(default_factory=list)
    total_cards: int = 0
    cards_with_brand: int = 0
    next_page_url: str | None = None


@dataclass
class ScrapeReport:
    """Aggregated result of a scraping run."""

    category_urls: list[str]
    pages_scraped: int
    product_cards_seen: int
    brands: list[BrandRecord]
    scraped_at: str
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category_urls": self.category_urls,
            "scraped_at": self.scraped_at,
            "pages_scraped": self.pages_scraped,
            "product_cards_seen": self.product_cards_seen,
            "unique_brands": len(self.brands),
            "errors": self.errors,
            "brands": [
                {
                    "name": record.name,
                    "product_mentions": record.product_mentions,
                    "sources": list(record.sources),
                }
                for record in self.brands
            ],
        }
