"""Rainforest API product endpoint adapter.

Docs: https://www.rainforestapi.com/docs/product-data-api/results/product

Env / CLI:
  RAINFOREST_API_KEY
"""

from __future__ import annotations

import os
from typing import Any

from ..fetcher import Fetcher
from ..models import Marketplace, ProductDescription, ProviderName
from .base import Provider


class RainforestProvider(Provider):
    name = ProviderName.RAINFOREST.value

    def __init__(
        self,
        api_key: str | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("RAINFOREST_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Rainforest provider needs --api-key or RAINFOREST_API_KEY"
            )
        self.fetcher = fetcher or Fetcher()

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        url = "https://api.rainforestapi.com/request"
        data = self.fetcher.fetch_json(
            url,
            params={
                "api_key": self.api_key,
                "type": "product",
                "amazon_domain": f"amazon.{marketplace.domain}",
                "asin": asin,
            },
        )
        return self._parse(data, asin=asin, marketplace=marketplace)

    def _parse(
        self, data: dict[str, Any], *, asin: str, marketplace: Marketplace
    ) -> ProductDescription:
        product = data.get("product") or {}
        bullets = product.get("feature_bullets") or product.get("feature_bullets_flat")
        if isinstance(bullets, str):
            bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
        bullets = list(bullets or [])

        description = product.get("description") or product.get("product_description")
        aplus = None
        aplus_obj = product.get("a_plus_content") or product.get("aplus")
        if isinstance(aplus_obj, dict):
            aplus = aplus_obj.get("plain_text") or aplus_obj.get("body")
        elif isinstance(aplus_obj, str):
            aplus = aplus_obj

        overview = {}
        specs = product.get("specifications") or product.get("product_information") or []
        if isinstance(specs, list):
            for item in specs:
                if isinstance(item, dict) and item.get("name") and item.get("value"):
                    overview[str(item["name"])] = str(item["value"])
        elif isinstance(specs, dict):
            overview = {str(k): str(v) for k, v in specs.items()}

        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=product.get("link") or marketplace.product_url(asin),
            title=product.get("title"),
            brand=product.get("brand"),
            feature_bullets=bullets,
            description=description,
            aplus_text=aplus,
            overview=overview,
            provider=self.name,
        )
