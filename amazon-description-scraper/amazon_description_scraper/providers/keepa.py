"""Keepa product API adapter.

Docs: https://keepa.com/#!discuss/t/product-object/116

Env / CLI:
  KEEPA_API_KEY
"""

from __future__ import annotations

import os
from typing import Any

from ..endpoints import KEEPA_DOMAIN_CODES
from ..fetcher import Fetcher
from ..models import Marketplace, ProductDescription, ProviderName
from .base import Provider


class KeepaProvider(Provider):
    name = ProviderName.KEEPA.value

    def __init__(
        self,
        api_key: str | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY")
        if not self.api_key:
            raise ValueError("Keepa provider needs --api-key or KEEPA_API_KEY")
        self.fetcher = fetcher or Fetcher()

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        domain = KEEPA_DOMAIN_CODES.get(marketplace.domain)
        if domain is None:
            raise ValueError(
                f"Keepa domain code unknown for marketplace {marketplace.domain!r}"
            )
        data = self.fetcher.fetch_json(
            "https://api.keepa.com/product",
            params={
                "key": self.api_key,
                "domain": domain,
                "asin": asin,
                "stats": 0,
            },
        )
        return self._parse(data, asin=asin, marketplace=marketplace)

    def _parse(
        self, data: dict[str, Any], *, asin: str, marketplace: Marketplace
    ) -> ProductDescription:
        products = data.get("products") or []
        if not products:
            return ProductDescription(
                asin=asin,
                marketplace=marketplace.domain,
                url=marketplace.product_url(asin),
                provider=self.name,
                error="Keepa returned no products",
            )
        product = products[0]
        bullets = product.get("features") or []
        if isinstance(bullets, str):
            bullets = [bullets]
        description = product.get("description")
        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            title=product.get("title"),
            brand=product.get("brand") or product.get("manufacturer"),
            feature_bullets=[str(b).strip() for b in bullets if str(b).strip()],
            description=description,
            provider=self.name,
        )
