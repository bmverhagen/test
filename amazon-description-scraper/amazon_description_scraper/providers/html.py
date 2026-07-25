"""Direct Amazon DP HTML provider (fast concurrent scrape)."""

from __future__ import annotations

import time
from urllib.parse import urlencode

from ..fetcher import Fetcher
from ..models import Marketplace, ProductDescription, ProviderName
from ..parser import parse_product_html
from .base import Provider


class HtmlProvider(Provider):
    name = ProviderName.HTML.value

    def __init__(self, fetcher: Fetcher | None = None, no_cache: bool = False) -> None:
        self.fetcher = fetcher or Fetcher()
        self.no_cache = no_cache

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        url = marketplace.product_url(asin)
        headers = None
        if self.no_cache:
            url = f"{url}?{urlencode({'th': '1', 'psc': '1', '_': str(time.time_ns())})}"
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
            }
        html = self.fetcher.fetch_text(url, headers=headers)
        return parse_product_html(
            html,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=self.name,
        )
