"""Amazon /gp/twister/dimension streaming-JSON provider.

Returns feature-div HTML fragments (title, bullets, description, A+) wrapped
as `application/amazonui-streaming-json`. One ASIN per request — multi-ASIN
`asinList` returns 404 on amazon.nl.
"""

from __future__ import annotations

import time
from urllib.parse import urlencode

from ..fetcher import Fetcher
from ..models import Marketplace, ProductDescription, ProviderName
from ..parser import parse_product_html
from ..twister_parse import parse_twister_stream, stitch_feature_html
from .base import Provider


class TwisterProvider(Provider):
    name = ProviderName.TWISTER.value

    def __init__(self, fetcher: Fetcher | None = None, no_cache: bool = True) -> None:
        self.fetcher = fetcher or Fetcher()
        self.no_cache = no_cache

    def url_for(self, asin: str, marketplace: Marketplace) -> str:
        params = {
            "isDimensionSlotsAjax": "1",
            "asinList": asin,
            "vs": "1",
        }
        if self.no_cache:
            params["_"] = f"{time.time_ns()}"
        return f"{marketplace.base_url}/gp/twister/dimension?{urlencode(params)}"

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        url = self.url_for(asin, marketplace)
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": marketplace.product_url(asin),
        }
        if self.no_cache:
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            headers["Pragma"] = "no-cache"
        response = self.fetcher.get(url, headers=headers, check_robot=True)
        raw = response.text or ""
        features = parse_twister_stream(raw)
        if "featurebullets_feature_div" not in features and "title_feature_div" not in features:
            return ProductDescription(
                asin=asin,
                marketplace=marketplace.domain,
                url=marketplace.product_url(asin),
                provider=self.name,
                source_bytes=len(response.content or b""),
                error="Twister response missing title/feature bullets",
            )
        html = stitch_feature_html(features, asin=asin)
        product = parse_product_html(
            html,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=self.name,
        )
        product.source_bytes = len(response.content or b"")
        return product
