"""Data structures shared across the scraper."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrandRecord:
    """A brand discovered on one or more category pages."""

    name: str
    product_mentions: int
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ProductEntry:
    """A single product as shown on a category page (never fetched itself).

    ``brand_source`` records how the brand was determined:
    - ``brand_row``: an explicit brand element on the product card
    - ``known_brand``: title matched a brand listed on a category page
    - ``title_guess``: heuristic guess from the leading word of the title
    """

    rank: int | None
    title: str
    brand: str | None
    brand_source: str | None
    asin: str | None = None


@dataclass
class PageResult:
    """Everything extracted from a single category page."""

    url: str
    page: int
    refinement_brands: list[str] = field(default_factory=list)
    product_brands: list[str] = field(default_factory=list)
    structured_data_brands: list[str] = field(default_factory=list)
    products: list[ProductEntry] = field(default_factory=list)
    is_best_seller_list: bool = False
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
    products: list[ProductEntry] = field(default_factory=list)
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
            "products": [
                {
                    "rank": product.rank,
                    "brand": product.brand,
                    "brand_source": product.brand_source,
                    "title": product.title,
                    "asin": product.asin,
                }
                for product in self.products
            ],
        }
