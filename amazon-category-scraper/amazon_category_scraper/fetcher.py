"""HTTP fetching with retries, exponential backoff and bot-check detection."""

from __future__ import annotations

import logging
import random
import time

import requests

__all__ = ["BlockedError", "FetchError", "Fetcher", "looks_like_robot_check"]

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 2.0

# Desktop browser user agents; Amazon serves full desktop markup to these.
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
)

# Strings that only appear on Amazon's captcha / automated-access interstitial.
_ROBOT_CHECK_MARKERS = (
    "/errors/validatecaptcha",
    "enter the characters you see below",
    "to discuss automated access to amazon data",
    "api-services-support@amazon.com",
)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """A page could not be downloaded after all retries."""


class BlockedError(FetchError):
    """Amazon answered with its robot-check (captcha) page on every attempt."""


def looks_like_robot_check(html: str) -> bool:
    """Return True when *html* is Amazon's captcha / bot interstitial."""
    lowered = html.casefold()
    return any(marker in lowered for marker in _ROBOT_CHECK_MARKERS)


class Fetcher:
    """Small polite HTTP client for category pages.

    Rotates desktop user agents, retries transient failures (HTTP 429/5xx,
    network errors, robot checks) with exponential backoff, and raises
    :class:`BlockedError` when Amazon keeps serving its captcha page.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        user_agent: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.user_agent = user_agent
        self._session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent or random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        }

    def fetch(self, url: str) -> str:
        """Download *url* and return its HTML body."""
        last_error: str = "unknown error"
        blocked = False

        for attempt in range(self.max_retries + 1):
            if attempt:
                pause = self.backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning("Retrying %s in %.1fs (%s)", url, pause, last_error)
                time.sleep(pause)

            try:
                response = self._session.get(url, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as exc:
                blocked = False
                last_error = f"network error: {exc}"
                continue

            if response.status_code == 200:
                if looks_like_robot_check(response.text):
                    blocked = True
                    last_error = "robot check page"
                    continue
                return response.text

            last_error = f"HTTP {response.status_code}"
            if response.status_code in _RETRYABLE_STATUS:
                # Amazon serves 503 both for overload and for bot blocking.
                blocked = response.status_code == 503 and looks_like_robot_check(response.text)
                continue
            raise FetchError(f"Failed to fetch {url}: {last_error}")

        if blocked:
            raise BlockedError(
                f"Amazon is blocking requests for {url} (robot check). "
                "Slow down (--delay), try again later, or route traffic through a "
                "residential/proxy connection you are allowed to use."
            )
        raise FetchError(f"Failed to fetch {url} after {self.max_retries + 1} attempts: {last_error}")
