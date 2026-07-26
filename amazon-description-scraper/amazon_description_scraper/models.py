"""Shared data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProviderName(str, Enum):
    """How product data is retrieved."""

    HTML = "html"
    TWISTER = "twister"
    SOFT = "soft"  # twister-first, DP fallback, sequential-safe bulk
    PAAPI = "paapi"
    RAINFOREST = "rainforest"
    KEEPA = "keepa"
    GENERIC_JSON = "generic_json"


@dataclass(frozen=True)
class Marketplace:
    """Amazon marketplace host + locale hints."""

    domain: str
    host: str
    language: str
    currency: str
    marketplace_id: str | None = None

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"

    def product_url(self, asin: str) -> str:
        return f"{self.base_url}/dp/{asin}"


# Common marketplaces. `nl` is first-class for this repo's Dutch use cases.
MARKETPLACES: dict[str, Marketplace] = {
    "nl": Marketplace(
        domain="nl",
        host="www.amazon.nl",
        language="nl-NL",
        currency="EUR",
        marketplace_id="A17E79C6D8DWNP",
    ),
    "com": Marketplace(
        domain="com",
        host="www.amazon.com",
        language="en-US",
        currency="USD",
        marketplace_id="ATVPDKIKX0DER",
    ),
    "co.uk": Marketplace(
        domain="co.uk",
        host="www.amazon.co.uk",
        language="en-GB",
        currency="GBP",
        marketplace_id="A1F83G8C2ARO7P",
    ),
    "de": Marketplace(
        domain="de",
        host="www.amazon.de",
        language="de-DE",
        currency="EUR",
        marketplace_id="A1PA6795UKMFR9",
    ),
    "fr": Marketplace(
        domain="fr",
        host="www.amazon.fr",
        language="fr-FR",
        currency="EUR",
        marketplace_id="A13V1IB3VIYZZH",
    ),
    "it": Marketplace(
        domain="it",
        host="www.amazon.it",
        language="it-IT",
        currency="EUR",
        marketplace_id="APJ6JRA9NG5V4",
    ),
    "es": Marketplace(
        domain="es",
        host="www.amazon.es",
        language="es-ES",
        currency="EUR",
        marketplace_id="A1RKKUPIHCS9HS",
    ),
    "com.be": Marketplace(
        domain="com.be",
        host="www.amazon.com.be",
        language="nl-BE",
        currency="EUR",
        marketplace_id="AMEN7PMS3EDWL",
    ),
}


def resolve_marketplace(domain: str) -> Marketplace:
    key = domain.lower().lstrip(".").removeprefix("amazon.")
    if key.startswith("www.amazon."):
        key = key.removeprefix("www.amazon.")
    if key not in MARKETPLACES:
        known = ", ".join(sorted(MARKETPLACES))
        raise ValueError(f"Unknown marketplace {domain!r}. Known: {known}")
    return MARKETPLACES[key]


@dataclass
class ProductDescription:
    """Structured product description payload."""

    asin: str
    marketplace: str
    url: str
    title: str | None = None
    brand: str | None = None
    feature_bullets: list[str] = field(default_factory=list)
    description: str | None = None
    aplus_text: str | None = None
    overview: dict[str, str] = field(default_factory=dict)
    meta_description: str | None = None
    provider: str = ProviderName.HTML.value
    source_bytes: int | None = None
    error: str | None = None
    unavailable: bool = False

    @property
    def best_description(self) -> str | None:
        """Longest useful plain-text description available."""
        if self.unavailable:
            return None
        candidates = [
            self.description,
            self.aplus_text,
            "\n".join(self.feature_bullets) if self.feature_bullets else None,
            self.meta_description,
        ]
        texts = [c.strip() for c in candidates if c and c.strip()]
        if not texts:
            return None
        return max(texts, key=len)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["best_description"] = self.best_description
        return data


ASIN_RE = r"[A-Z0-9]{10}"
