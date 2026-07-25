"""Ultra-fast Amazon description client.

Winning knobs from 55+ experiments + endpoint hunt (amazon.nl, no cache):
- shared Session + large HTTPAdapter pool
- free path: ajaxv2 → (skip dimension on structural 404) → aw → dp
- remember ASINs without twister payload → aw-first on retries
- urllib3 retries off for soft 5xx (retries only amplify latency)
- regex-first parse (`fast_parse`)
"""

from __future__ import annotations

import hashlib
import random
import threading
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

# Amazon "Pagina niet gevonden" shells — not a throttle / soft-5xx.
_STRUCTURAL_404_MARKERS = (
    "pagina niet gevonden",
    "page not found",
    "dogs of amazon",
    "looking for something",
)

# Global /gp/aw/d failover hosts (locale may differ from marketplace).
_GLOBAL_AW_HOSTS = (
    "www.amazon.de",
    "www.amazon.fr",
    "www.amazon.es",
    "www.amazon.it",
    "www.amazon.co.uk",
    "www.amazon.com",  # US
    "www.amazon.ca",
    "www.amazon.com.be",
    "www.amazon.com.au",
    "www.amazon.co.jp",
    "www.amazon.com.mx",
    "www.amazon.in",
)

_HOST_LABELS = {
    "www.amazon.com": "us",
    "www.amazon.co.uk": "uk",
    "www.amazon.com.au": "au",
    "www.amazon.co.jp": "jp",
    "www.amazon.com.mx": "mx",
    "www.amazon.com.be": "be",
    "www.amazon.de": "de",
    "www.amazon.fr": "fr",
    "www.amazon.es": "es",
    "www.amazon.it": "it",
    "www.amazon.ca": "ca",
    "www.amazon.in": "in",
    "www.amazon.nl": "nl",
}


def _host_label(host: str) -> str:
    host = host.lower()
    if host in _HOST_LABELS:
        return _HOST_LABELS[host]
    # www.amazon.X -> X
    if host.startswith("www.amazon."):
        return host.removeprefix("www.amazon.").replace(".", "")
    return host.split(".")[-1]


def _bust() -> str:
    return hashlib.md5(f"{time.time_ns()}{random.random()}".encode()).hexdigest()[:10]


def _captcha(text: str) -> bool:
    lowered = text.casefold()
    return any(m in lowered for m in _CAPTCHA_MARKERS)


def _structural_404(status: int, text: str) -> bool:
    """True for hard Amazon 404/gone pages (not soft 500/503 throttle shells)."""
    if status == 404:
        return True
    if status != 200:
        return False
    low = text.casefold()
    if any(m in low for m in _STRUCTURAL_404_MARKERS) and len(text) < 20000:
        return True
    return False


class TurboClient:
    """High-throughput twister→dp client with connection pooling."""

    def __init__(
        self,
        *,
        pool_size: int = 120,
        retries: int = 0,
        timeout: float = 8.0,
        twister_timeout: float | None = None,
        no_cache: bool = True,
    ) -> None:
        self.timeout = timeout
        self.twister_timeout = twister_timeout if twister_timeout is not None else min(5.0, timeout)
        self.no_cache = no_cache
        self.session = self._build_session(pool_size=pool_size, retries=retries)
        # ASINs where ajaxv2/dimension returned a structural 404 — skip twister next time.
        self._no_twister: set[str] = set()
        self._no_twister_lock = threading.Lock()

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

    def remember_no_twister(self, asin: str) -> None:
        with self._no_twister_lock:
            self._no_twister.add(asin)

    def knows_no_twister(self, asin: str) -> bool:
        with self._no_twister_lock:
            return asin in self._no_twister

    def fetch(
        self,
        asin: str,
        marketplace: Marketplace,
        *,
        prefer_html: bool = False,
        confirm_unavailable: bool = False,
        skip_dp: bool = False,
        multi_host: bool = False,
    ) -> ProductDescription:
        # Endpoint hunt (2026-07): no free light JSON without captcha/tokens.
        # Fast path: ajaxv2 → [dimension only if not structural 404] → aw → [dp]
        # Known no-twister / prefer_html: aw → [dp] (skip burned twister RTTs)
        # multi_host: after local miss, probe global aw hosts (EU/US/etc.)
        # skip_dp: omit heavy /dp on hot first pass (cuts load + latency)
        captcha_hit: ProductDescription | None = None
        aw_first = prefer_html or self.knows_no_twister(asin)
        html_getters = (self._aw,) if skip_dp else (self._aw, self._dp)

        if not aw_first:
            product, reason = self._twister_like(
                asin,
                marketplace,
                path="/gp/twister/ajaxv2",
                provider="turbo/ajaxv2",
            )
            if product and (product.title or product.feature_bullets):
                return product
            if product and product.error and "captcha" in product.error:
                captcha_hit = product
            if reason == "structural_404":
                self.remember_no_twister(asin)
            else:
                # Dimension only when ajaxv2 looked like a soft miss (5xx/empty), not 404.
                product, reason = self._twister_like(
                    asin,
                    marketplace,
                    path="/gp/twister/dimension",
                    provider="turbo/twister",
                )
                if product and (product.title or product.feature_bullets):
                    return product
                if product and product.error and "captcha" in product.error:
                    captcha_hit = product
                if reason == "structural_404":
                    self.remember_no_twister(asin)

            for getter in html_getters:
                product = getter(asin, marketplace)
                if product and (product.title or product.feature_bullets):
                    return product
                if product and product.error and "captcha" in product.error:
                    captcha_hit = product
        else:
            # Known no-twister / aw-first: never re-hit ajaxv2 (structural 404s).
            for getter in html_getters:
                product = getter(asin, marketplace)
                if product and (product.title or product.feature_bullets):
                    return product
                if product and product.error and "captcha" in product.error:
                    captcha_hit = product

        # Global aw failover (EU/US/…): only after local chain missed.
        structural_404s = 0
        if prefer_html or multi_host:
            seen: set[str] = set()
            hosts: list[str] = [marketplace.host, *_GLOBAL_AW_HOSTS]
            for host in hosts:
                if host in seen:
                    continue
                seen.add(host)
                label = _host_label(host)
                product, reason = self._aw_host_ex(
                    asin, host, marketplace, provider=f"turbo/aw/{label}"
                )
                if product and (
                    product.title or product.feature_bullets or product.description
                ):
                    return product
                if product and product.error and "captcha" in product.error:
                    captcha_hit = product
                if reason == "structural_404":
                    structural_404s += 1

        if captcha_hit is not None and not confirm_unavailable:
            return captcha_hit

        # Only confirm delist on hard 404s across storefronts — never on soft 5xx.
        if confirm_unavailable and structural_404s >= 3:
            return self._unavailable_product(asin, marketplace)

        if captcha_hit is not None:
            return captcha_hit

        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider="turbo",
            error="turbo fetch failed (ajaxv2+aw+dp+global)",
        )

    def _unavailable_product(
        self, asin: str, marketplace: Marketplace
    ) -> ProductDescription:
        return ProductDescription(
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider="turbo/unavailable",
            unavailable=True,
            description="Product page unavailable / delisted on Amazon",
        )

    def probe_delisted(
        self, asin: str, marketplace: Marketplace, *, min_404s: int = 3
    ) -> ProductDescription | None:
        """Cheap multi-host 404 check. Returns unavailable product or None.

        Soft 5xx / empty responses do NOT count — avoids false delist under load.
        """
        hosts = (
            marketplace.host,
            "www.amazon.de",
            "www.amazon.fr",
            "www.amazon.co.uk",
            "www.amazon.com",
        )
        hits = 0
        for host in hosts:
            product, reason = self._aw_host_ex(
                asin, host, marketplace, provider=f"turbo/aw/{_host_label(host)}"
            )
            if product and (product.title or product.feature_bullets):
                return None
            if reason == "structural_404":
                hits += 1
                if hits >= min_404s:
                    self.remember_no_twister(asin)
                    return self._unavailable_product(asin, marketplace)
        return None

    def _twister_like(
        self,
        asin: str,
        marketplace: Marketplace,
        *,
        path: str,
        provider: str,
    ) -> tuple[ProductDescription | None, str]:
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
                timeout=self.twister_timeout,
            )
        except requests.RequestException:
            return None, "network"
        raw = response.text or ""
        if _captcha(raw):
            return (
                ProductDescription(
                    asin=asin,
                    marketplace=marketplace.domain,
                    url=marketplace.product_url(asin),
                    provider=provider,
                    error="robot/captcha page",
                ),
                "captcha",
            )
        if _structural_404(response.status_code, raw):
            return None, "structural_404"
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        if "featurebullets_feature_div" not in raw and "title_feature_div" not in raw:
            return None, "empty_payload"
        html = stitch_feature_html(parse_twister_stream(raw), asin=asin)
        product = fast_parse_html(
            html,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=provider,
        )
        product.source_bytes = len(response.content or b"")
        return product, "ok"

    def _ajaxv2(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        product, reason = self._twister_like(
            asin,
            marketplace,
            path="/gp/twister/ajaxv2",
            provider="turbo/ajaxv2",
        )
        if reason == "structural_404":
            self.remember_no_twister(asin)
        return product

    def _twister(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        """Legacy twister/dimension path (kept for soft provider / experiments)."""
        product, reason = self._twister_like(
            asin,
            marketplace,
            path="/gp/twister/dimension",
            provider="turbo/twister",
        )
        if reason == "structural_404":
            self.remember_no_twister(asin)
        return product

    def _aw(self, asin: str, marketplace: Marketplace) -> ProductDescription | None:
        """Mobile product page — often lighter than /dp and higher hit-rate than twister."""
        product, _reason = self._aw_host_ex(
            asin, marketplace.host, marketplace, provider="turbo/aw"
        )
        return product

    def _aw_host(
        self,
        asin: str,
        host: str,
        marketplace: Marketplace,
        *,
        provider: str | None = None,
    ) -> ProductDescription | None:
        product, _reason = self._aw_host_ex(
            asin, host, marketplace, provider=provider
        )
        return product

    def _aw_host_ex(
        self,
        asin: str,
        host: str,
        marketplace: Marketplace,
        *,
        provider: str | None = None,
    ) -> tuple[ProductDescription | None, str]:
        bust = f"&_={_bust()}" if self.no_cache else ""
        url = f"https://{host}/gp/aw/d/{asin}?psc=1&th=1{bust}"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException:
            return None, "network"
        raw = response.text or ""
        if _captcha(raw):
            return (
                ProductDescription(
                    asin=asin,
                    marketplace=marketplace.domain,
                    url=marketplace.product_url(asin),
                    provider=provider or f"turbo/aw/{host}",
                    error="robot/captcha page",
                ),
                "captcha",
            )
        if _structural_404(response.status_code, raw):
            return None, "structural_404"
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        if len(raw) < 5000:
            return None, "tiny_html"
        product = fast_parse_html(
            raw,
            asin=asin,
            marketplace=marketplace.domain,
            url=marketplace.product_url(asin),
            provider=provider or f"turbo/aw/{host.split('.')[-1]}",
        )
        product.source_bytes = len(response.content or b"")
        if not (product.title or product.feature_bullets):
            # Title-only pages (e.g. some Prime Video) may still have description.
            if product.description or product.best_description:
                return product, "ok"
            return None, "empty_parse"
        return product, "ok"

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
