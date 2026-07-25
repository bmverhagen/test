"""Block-resistant bulk strategy: warm session → twister → DP fallback.

Validated on amazon.nl (100 ASINs, no captcha, no HTTP cache):
  twister-first + DP fallback, workers=1, ~0.55s delay → 100/100 OK in ~196s
  (74 via twister, 26 via /dp).

Concurrent workers>=3 trigger captchas/404s from this environment's IP.
"""

from __future__ import annotations

import logging
import time

from ..fetcher import BlockedError, FetchError, Fetcher, looks_like_robot_check
from ..models import Marketplace, ProductDescription, ProviderName
from .base import Provider
from .html import HtmlProvider
from .twister import TwisterProvider

logger = logging.getLogger(__name__)


class SoftProvider(Provider):
    """Try twister first, fall back to full DP HTML, with captcha retries."""

    name = ProviderName.SOFT.value

    def __init__(
        self,
        fetcher: Fetcher | None = None,
        no_cache: bool = True,
        max_attempts: int = 3,
    ) -> None:
        self.fetcher = fetcher or Fetcher()
        self.no_cache = no_cache
        self.max_attempts = max_attempts
        self.twister = TwisterProvider(fetcher=self.fetcher, no_cache=no_cache)
        self.html = HtmlProvider(fetcher=self.fetcher, no_cache=no_cache)

    def warm(self, marketplace: Marketplace) -> None:
        """Hit the storefront once so the session has cookies."""
        try:
            self.fetcher.get(
                marketplace.base_url + "/",
                check_robot=False,
                headers={"Cache-Control": "no-cache"} if self.no_cache else None,
            )
        except FetchError as exc:
            logger.warning("Session warm failed: %s", exc)

    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            order = [self.twister, self.html]
            if attempt == 2:
                order = [self.html, self.twister]
            for provider in order:
                try:
                    product = provider.fetch(asin, marketplace)
                except BlockedError as exc:
                    last_error = str(exc)
                    logger.warning("Blocked on %s for %s (attempt %s)", provider.name, asin, attempt)
                    time.sleep(2.0 * attempt)
                    continue
                except FetchError as exc:
                    last_error = str(exc)
                    continue
                if product.error:
                    last_error = product.error
                    continue
                if not (
                    product.feature_bullets
                    or product.description
                    or product.aplus_text
                    or product.title
                ):
                    last_error = "empty product payload"
                    continue
                product.provider = f"soft/{provider.name}"
                return product
            time.sleep(1.0 * attempt)
        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=self.name,
            error=last_error or "soft provider exhausted retries",
        )


def is_captcha_response(body: str) -> bool:
    return looks_like_robot_check(body)
