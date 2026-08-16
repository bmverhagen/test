"""Fetch HTML/Markdown for shop pages (direct, then Jina reader proxy)."""

from __future__ import annotations

import time
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_direct(url: str, timeout: int = 45) -> tuple[int, str]:
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "nl-NL,nl;q=0.9"},
        timeout=timeout,
        allow_redirects=True,
    )
    return r.status_code, r.text


def fetch_jina(url: str, timeout: int = 90) -> tuple[int, str]:
    # Prefer https target for jina
    target = url if url.startswith("http") else f"https://{url}"
    jina_url = f"https://r.jina.ai/{target}"
    r = requests.get(jina_url, headers={"User-Agent": UA}, timeout=timeout)
    return r.status_code, r.text


def _is_challenge(text: str) -> bool:
    head = text[:2000].lower()
    markers = [
        "just a moment...",
        "attention required",
        "access denied",
        "temporarily blocked",
        "performing security verification",
        "cf-browser-verification",
        "challenge-platform",
    ]
    return any(m in head for m in markers)


def fetch_page(
    url: str,
    *,
    cache_path: Path | None = None,
    prefer_jina: bool = False,
    min_len: int = 2000,
    sleep: float = 0.8,
    force_refresh: bool = False,
) -> tuple[str, str]:
    """Return (source, body). source is 'direct' | 'jina' | 'cache'."""
    if (
        cache_path
        and cache_path.exists()
        and cache_path.stat().st_size > min_len
        and not force_refresh
    ):
        cached = cache_path.read_text(encoding="utf-8", errors="ignore")
        if not _is_challenge(cached):
            return "cache", cached

    bodies: list[tuple[str, str]] = []
    order = ["jina", "direct"] if prefer_jina else ["direct", "jina"]
    for mode in order:
        try:
            status, text = fetch_jina(url) if mode == "jina" else fetch_direct(url)
        except Exception:
            continue
        if status != 200 or len(text) < min_len or _is_challenge(text):
            time.sleep(0.3)
            continue
        bodies.append((mode, text))
        break

    if not bodies:
        # last resort: keep jina even if short (caller may still parse / fallback)
        try:
            status, text = fetch_jina(url)
            if status == 200 and not _is_challenge(text):
                bodies.append(("jina", text))
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

    if not bodies:
        raise RuntimeError(f"Blocked/challenge for {url}")

    source, text = bodies[0]
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    time.sleep(sleep)
    return source, text
