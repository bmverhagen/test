"""Ultra-fast Amazon description client.

Winning knobs from 55+ experiments + endpoint hunt (amazon.nl, no cache):
- shared Session + large HTTPAdapter pool
- workers ≈ 20–24
- global spacing ≈ 0.02–0.025s (adaptive)
- free path: ajaxv2 → mobile `/gp/aw/d` → `/dp` (no captcha-free light JSON found)
- urllib3 Retry only for 429/5xx
- regex-first parse (`fast_parse`), BS4 fallback
- gzip/br accept-encoding, keep-alive
"""

from __future__ import annotations

import hashlib
import random
import time
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .fast_parse import fast_parse_html
from .models import Marketplace, ProductDescription
from .twister_parse import parse_twister_stream, stitch_feature_html

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_CAPTCHA_MARKERS = (
    "/errors/validatecaptcha",
    "enter the characters you see below",
    "sorry, we just need to make sure you're not a robot",
)


def _bust() -> str:
    return hashlib.md5(f"{time.time_ns()}{random.random()}".encode()).hexdigest()[:10]


def _captcha(text: str) -> bool:
    lowered = text.casefold()
    return any(m in lowered for m in _CAPTCHA_MARKERS)


class TurboClient:
    """High-throughput twister→dp client with connection pooling."""

    def __init__(
        self,
        *,
        pool_size: int = 120,
        retries: int = 1,
        timeout: float = 8.0,
        no_cache: bool = True,
    ) -> None:
        self.timeout = timeout
        self.no_cache = no_cache
        self.session = self._build_session(pool_size=pool_size, retries=retries)

    @staticmethod
    def _build_session(*, pool_size: int, retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.15,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            max_retries=retry,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": _UA,
                "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )
        return session

    def warm(self, marketplace: Marketplace) -> None:
        try:
            self.session.get(marketplace.base_url + "/", timeout=self.timeout)
        except requests.RequestException:
            pass

    def fetch(
        self,
        asin: str,
        marketplace: Marketplace,
        *,
        prefer_html: bool = False,
    ) -> ProductDescription:
        # Endpoint hunt (2026-07): no free light JSON without captcha/tokens.
        # Fast path: ajaxv2 → dimension → aw → dp
        # Retry path (prefer_html): aw → dp → ajaxv2 → dimension — recovers
        # soft-throttled ASINs that fail the ajax-first chain under load.
        captcha_hit: ProductDescription | None = None
        getters = (
            (self._aw, self._dp, self._ajaxv2, self._twister)
            if prefer_html
            else (self._ajaxv2, self._twister, self._aw, self._dp)
        )
        for getter in getters:
            product = getter(asin, marketplace)
            if product and (product.title or product.feature_bullets):
                return product
            if product and product.error and "captcha" in product.error:
                captcha_hit = product

        # Last resort for hard NL throttles: sibling EU storefronts (aw HTML).
        if prefer_html:
            for host in ("www.amazon.de", "www.amazon.fr", "www.amazon.es", "www.amazon.it"):
                if host == marketplace.host:
                    continue
                product = self._aw_host(asin, host, marketplace)
                if product and (product.title or product.feature_bullets):
                    return product

        if captcha_hit is not None:
            return captcha_hit
        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider="turbo",
            error="turbo fetch failed (ajaxv2+dimension+aw+dp+eu)",
        )

    def _twister_like(
        self,
        asin: str,
        marketplace: Marketplace,
        *,
        path: str,
        provider: str,
    ) -> ProductDescription | None:
        params = {
            "isDimensionSlotsAjax": "1",
            "asinList": asin,
            "vs": "1",
        }
        if self.no_cache:
            params["_"] = _bust()
        url = f"{marketplace.base_url}{path}?{urlencode(params)}"
        try:
            response = self.session.get(
                url,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": marketplace.product_url(asin),
                },
                timeout=self.timeout,
            )
        except requests.RequestException:
            return None
        raw = response.text or ""
        if response.status_code != 200 or _captcha(raw):
            return None
        if "featurebullets_feature_div" not in raw and "title_feature_div" not in raw:
            return None
        html = stitch_feature_html(parse_twister_stream(raw), asin=asin)
        product = fast_parse_html(
            html,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=provider,
        )
        product.source_bytes = len(response.content or b"")
        return product

    def _ajaxv2(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        return self._twister_like(
            asin,
            marketplace,
            path="/gp/twister/ajaxv2",
            provider="turbo/ajaxv2",
        )

    def _twister(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        """Legacy twister/dimension path (kept for soft provider / experiments)."""
        return self._twister_like(
            asin,
            marketplace,
            path="/gp/twister/dimension",
            provider="turbo/twister",
        )

    def _aw(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        """Mobile product page — often lighter than /dp and higher hit-rate than twister."""
        return self._aw_host(asin, marketplace.host, marketplace, provider="turbo/aw")

    def _aw_host(
        self,
        asin: str,
        host: str,
        marketplace: Marketplace,
        *,
        provider: str | None = None,
    ) -> ProductDescription | None:
        bust = f"&_={_bust()}" if self.no_cache else ""
        url = f"https://{host}/gp/aw/d/{asin}?psc=1&th=1{bust}"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException:
            return None
        raw = response.text or ""
        if response.status_code != 200 or _captcha(raw) or len(raw) < 5000:
            if _captcha(raw):
                return ProductDescription(
                    asin=asin,
                    marketplace=marketplace.domain,
                    url=marketplace.product_url(asin),
                    provider=provider or f"turbo/aw/{host}",
                    error="robot/captcha page",
                )
            return None
        product = fast_parse_html(
            raw,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=provider or f"turbo/aw/{host.split('.')[-1]}",
        )
        product.source_bytes = len(response.content or b"")
        if not (product.title or product.feature_bullets):
            return None
        return product

    def _dp(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        suffix = f"?th=1&psc=1&_={_bust()}" if self.no_cache else "?th=1&psc=1"
        url = marketplace.product_url(asin) + suffix
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException:
            return None
        raw = response.text or ""
        if response.status_code != 200 or _captcha(raw):
            if _captcha(raw):
                return ProductDescription(
                    asin=asin,
                    marketplace=marketplace.domain,
                    url=marketplace.product_url(asin),
                    provider="turbo/html",
                    error="robot/captcha page",
                )
            return None
        product = fast_parse_html(
            raw,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider="turbo/html",
        )
        product.source_bytes = len(response.content or b"")
        return product
