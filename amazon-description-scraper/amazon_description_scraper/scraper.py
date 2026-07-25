"""Concurrent / soft-bulk product-description scraper."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from .fetcher import Fetcher
from .models import Marketplace, ProductDescription, ProviderName, resolve_marketplace
from .parser import extract_asin
from .providers import (
    GenericJsonProvider,
    HtmlProvider,
    KeepaProvider,
    PaapiProvider,
    Provider,
    RainforestProvider,
    TwisterProvider,
)
from .providers.generic_json import parse_json_map
from .providers.soft import SoftProvider

logger = logging.getLogger(__name__)


class DescriptionScraper:
    """Fetch product descriptions for many ASINs via a chosen provider."""

    def __init__(
        self,
        marketplace: str | Marketplace = "nl",
        provider: str | ProviderName = ProviderName.HTML,
        workers: int | None = None,
        delay: float | None = None,
        api_key: str | None = None,
        endpoint_url: str | None = None,
        json_map: str | None = None,
        fetcher: Fetcher | None = None,
        paapi_access_key: str | None = None,
        paapi_secret_key: str | None = None,
        paapi_partner_tag: str | None = None,
        no_cache: bool = False,
        warm_session: bool = True,
    ) -> None:
        self.marketplace = (
            marketplace
            if isinstance(marketplace, Marketplace)
            else resolve_marketplace(marketplace)
        )
        self.provider_name = (
            provider if isinstance(provider, ProviderName) else ProviderName(provider)
        )
        # Soft mode defaults: sequential + polite delay (validated 100/100 no captcha).
        if self.provider_name is ProviderName.SOFT:
            self.workers = 1 if workers is None else max(1, workers)
            self.delay = 0.55 if delay is None else max(0.0, delay)
            self.no_cache = True
        else:
            self.workers = 8 if workers is None else max(1, workers)
            self.delay = 0.0 if delay is None else max(0.0, delay)
            self.no_cache = no_cache

        self.warm_session = warm_session
        language = f"{self.marketplace.language},en;q=0.8"
        self.fetcher = fetcher or Fetcher(language=language)
        self.provider = self._build_provider(
            api_key=api_key,
            endpoint_url=endpoint_url,
            json_map=json_map,
            paapi_access_key=paapi_access_key,
            paapi_secret_key=paapi_secret_key,
            paapi_partner_tag=paapi_partner_tag,
        )
        self._warmed = False

    def _build_provider(
        self,
        *,
        api_key: str | None,
        endpoint_url: str | None,
        json_map: str | None,
        paapi_access_key: str | None,
        paapi_secret_key: str | None,
        paapi_partner_tag: str | None,
    ) -> Provider:
        name = self.provider_name
        if name is ProviderName.HTML:
            return HtmlProvider(fetcher=self.fetcher, no_cache=self.no_cache)
        if name is ProviderName.TWISTER:
            return TwisterProvider(fetcher=self.fetcher, no_cache=self.no_cache)
        if name is ProviderName.SOFT:
            return SoftProvider(fetcher=self.fetcher, no_cache=True)
        if name is ProviderName.RAINFOREST:
            return RainforestProvider(api_key=api_key, fetcher=self.fetcher)
        if name is ProviderName.KEEPA:
            return KeepaProvider(api_key=api_key, fetcher=self.fetcher)
        if name is ProviderName.PAAPI:
            return PaapiProvider(
                access_key=paapi_access_key,
                secret_key=paapi_secret_key,
                partner_tag=paapi_partner_tag,
            )
        if name is ProviderName.GENERIC_JSON:
            return GenericJsonProvider(
                endpoint_url=endpoint_url or "",
                json_map=parse_json_map(json_map),
                api_key=api_key,
                fetcher=self.fetcher,
            )
        raise ValueError(f"Unsupported provider: {name}")

    def normalize_asins(self, values: Iterable[str]) -> list[str]:
        asins: list[str] = []
        seen: set[str] = set()
        for value in values:
            asin = extract_asin(value)
            if not asin or asin in seen:
                continue
            seen.add(asin)
            asins.append(asin)
        return asins

    def _ensure_warm(self) -> None:
        if self._warmed or not self.warm_session:
            return
        if isinstance(self.provider, SoftProvider):
            self.provider.warm(self.marketplace)
        else:
            try:
                self.fetcher.get(self.marketplace.base_url + "/", check_robot=False)
            except Exception:  # noqa: BLE001
                pass
        self._warmed = True

    def fetch_one(self, asin: str) -> ProductDescription:
        asin = extract_asin(asin) or asin
        self._ensure_warm()
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.provider.fetch(asin, self.marketplace)
        except Exception as exc:  # noqa: BLE001 - surface per-ASIN errors
            logger.exception("Failed %s via %s", asin, self.provider_name.value)
            return ProductDescription(
                asin=asin,
                marketplace=self.marketplace.domain,
                url=self.marketplace.product_url(asin),
                provider=self.provider_name.value,
                error=str(exc),
            )

    def fetch_many(self, asins: Iterable[str]) -> list[ProductDescription]:
        normalized = self.normalize_asins(asins)
        if not normalized:
            return []
        self._ensure_warm()
        if self.workers == 1 or len(normalized) == 1:
            return [self.fetch_one(asin) for asin in normalized]

        results: dict[str, ProductDescription] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self.fetch_one, asin): asin for asin in normalized}
            for future in as_completed(futures):
                asin = futures[future]
                results[asin] = future.result()
        return [results[asin] for asin in normalized]
