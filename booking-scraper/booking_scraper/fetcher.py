"""Fetch Booking.com pages with Playwright (needed for AWS WAF)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT_MS = 60_000
COOKIE_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button#onetrust-accept-btn-handler",
    "button:has-text('Alles accepteren')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
)


class FetchError(RuntimeError):
    """Raised when a Booking.com page cannot be loaded or parsed."""


class PlaywrightFetcher:
    """Headless Chromium fetcher that waits for property cards."""

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        user_agent: str = DEFAULT_USER_AGENT,
        locale: str = "nl-NL",
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent
        self.locale = locale
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    def __enter__(self) -> PlaywrightFetcher:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - import guard
            raise FetchError(
                "playwright is required. Install with: pip install playwright "
                "&& playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            locale=self.locale,
            user_agent=self.user_agent,
            viewport={"width": 1400, "height": 900},
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = self._browser = self._playwright = None

    def _accept_cookies(self, page: Any) -> None:
        for selector in COOKIE_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=1500):
                    button.click(timeout=2000)
                    time.sleep(0.5)
                    logger.info("Accepted cookie banner via %s", selector)
                    return
            except Exception:
                continue

    def _looks_like_waf(self, html: str) -> bool:
        markers = (
            "awsWafCookieDomainList",
            "captcha-container",
            "challenge-container",
            "Human Verification",
        )
        has_marker = any(marker in html for marker in markers)
        has_cards = 'data-testid="property-card"' in html
        return has_marker and not has_cards

    def fetch_html(self, url: str, *, retries: int = 1) -> str:
        """Load ``url`` and return the rendered HTML."""
        if self._context is None:
            raise FetchError("Fetcher is not started; use as a context manager")

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            page = self._context.new_page()
            try:
                logger.info("Fetching %s (attempt %s)", url, attempt + 1)
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                self._accept_cookies(page)
                try:
                    page.wait_for_selector(
                        '[data-testid="property-card"], [data-testid="header-title"]',
                        timeout=self.timeout_ms,
                    )
                except Exception as exc:
                    html = page.content()
                    if self._looks_like_waf(html):
                        last_error = FetchError(
                            "Blocked by Booking.com AWS WAF challenge; try again later"
                        )
                        last_error.__cause__ = exc
                        time.sleep(2 + attempt * 2)
                        continue
                    raise FetchError("Timed out waiting for search results") from exc

                # Let lazy price blocks settle.
                time.sleep(1.5)
                html = page.content()
                if self._looks_like_waf(html):
                    last_error = FetchError(
                        "Blocked by Booking.com AWS WAF challenge; try again later"
                    )
                    time.sleep(2 + attempt * 2)
                    continue
                if 'data-testid="property-card"' not in html:
                    # Zero results is valid when header confirms the empty set.
                    if 'data-testid="header-title"' in html or "<h1" in html:
                        return html
                    header = page.title()
                    raise FetchError(f"No property cards found (title={header!r})")
                return html
            finally:
                page.close()

        assert last_error is not None
        raise last_error
