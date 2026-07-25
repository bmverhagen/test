"""HTTP fetching with retries and bot-check detection."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

__all__ = ["BlockedError", "FetchError", "Fetcher", "looks_like_robot_check"]

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 1.5

_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
)

_ROBOT_CHECK_MARKERS = (
    "/errors/validatecaptcha",
    "enter the characters you see below",
    "to discuss automated access to amazon data",
    "api-services-support@amazon.com",
    "sorry, we just need to make sure you're not a robot",
)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """A URL could not be downloaded after all retries."""


class BlockedError(FetchError):
    """Amazon answered with its robot-check page on every attempt."""


def looks_like_robot_check(body: str) -> bool:
    lowered = body.casefold()
    return any(marker in lowered for marker in _ROBOT_CHECK_MARKERS)


class Fetcher:
    """Polite HTTP client for Amazon pages and JSON APIs."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        user_agent: str | None = None,
        language: str = "nl-NL,nl;q=0.9,en;q=0.8",
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.user_agent = user_agent
        self.language = language
        self._session = session or requests.Session()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent or random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": self.language,
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
        }
        if extra:
            headers.update(extra)
        return headers

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        check_robot: bool = True,
    ) -> requests.Response:
        last_error = "unknown error"
        blocked = False

        for attempt in range(self.max_retries + 1):
            if attempt:
                pause = self.backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.4)
                logger.warning("Retrying %s in %.1fs (%s)", url, pause, last_error)
                time.sleep(pause)

            try:
                response = self._session.get(
                    url,
                    headers=self._headers(headers),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                blocked = False
                last_error = f"network error: {exc}"
                continue

            if response.status_code == 200:
                if check_robot and looks_like_robot_check(response.text):
                    blocked = True
                    last_error = "robot check page"
                    continue
                return response

            last_error = f"HTTP {response.status_code}"
            if response.status_code in _RETRYABLE_STATUS:
                blocked = response.status_code == 503 and looks_like_robot_check(response.text)
                continue
            raise FetchError(f"Failed to fetch {url}: {last_error}")

        if blocked:
            raise BlockedError(
                f"Amazon is blocking requests for {url} (robot check). "
                "Slow down (--delay / lower --workers), try later, or use a "
                "JSON provider (paapi / rainforest / keepa) instead of HTML."
            )
        raise FetchError(
            f"Failed to fetch {url} after {self.max_retries + 1} attempts: {last_error}"
        )

    def fetch_text(self, url: str, **kwargs: Any) -> str:
        return self.get(url, **kwargs).text

    def fetch_json(self, url: str, **kwargs: Any) -> Any:
        response = self.get(url, check_robot=False, **kwargs)
        return response.json()
