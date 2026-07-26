"""Bulk download pipeline — iterative pass-1 turbo by default.

Priority: **100% success**, then speed.
- Batched mode: pass-1 rounds over remaining failures (max_passes)
- Stream mode: continuous queue — misses requeue immediately (max_retries)
- Soft-fail and captcha both widen spacing; successes decay it
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import heapq
import itertools
from typing import Callable, TextIO

from .models import Marketplace, ProductDescription, resolve_marketplace
from .parser import extract_asin
from .providers.soft import SoftProvider
from .fetcher import Fetcher
from .storage import write_csv, write_json
from .turbo import TurboClient

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    total: int = 0
    attempted: int = 0
    ok: int = 0
    failed: int = 0
    captcha_hits: int = 0
    retries: int = 0
    bytes_total: int = 0
    passes: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    delay: float = 0.05
    workers: int = 12
    engine: str = "turbo"

    def note_success(self, product: ProductDescription) -> None:
        self.ok += 1
        self.attempted += 1
        self.by_provider[product.provider] = self.by_provider.get(product.provider, 0) + 1
        if product.source_bytes:
            self.bytes_total += product.source_bytes

    def note_failure(self, product: ProductDescription, captcha: bool = False) -> None:
        self.failed += 1
        self.attempted += 1
        if captcha:
            self.captcha_hits += 1
        self.by_provider["error"] = self.by_provider.get("error", 0) + 1

    @property
    def elapsed(self) -> float:
        return max(0.001, time.time() - self.started_at)

    @property
    def rate(self) -> float:
        return self.attempted / self.elapsed

    @property
    def eta_seconds(self) -> float | None:
        remaining = self.total - self.ok - self.failed
        # During multipass, treat unfinished as remaining work
        unfinished = max(0, self.total - self.ok)
        if unfinished <= 0 or self.rate <= 0:
            return 0.0
        return unfinished / max(self.rate, 0.01)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "iterations": self.passes,
            "elapsed": round(self.elapsed, 2),
            "rate_per_sec": round(self.rate, 3),
            "eta_seconds": None if self.eta_seconds is None else round(self.eta_seconds, 1),
            "success_rate": round(self.ok / self.total, 4) if self.total else None,
        }


class SpacingGate:
    def __init__(
        self,
        spacing: float = 0.05,
        min_spacing: float = 0.03,
        max_spacing: float = 1.5,
        growth: float = 1.35,
        soft_growth: float = 1.08,
        decay_every: int = 20,
        decay_factor: float = 0.92,
        grow_cooldown: float = 2.0,
    ) -> None:
        self.spacing = spacing
        self.min_spacing = min_spacing
        self.max_spacing = max_spacing
        self.growth = growth
        self.soft_growth = soft_growth
        self.decay_every = decay_every
        self.decay_factor = decay_factor
        self.grow_cooldown = grow_cooldown
        self._lock = threading.Lock()
        self._next_start = 0.0
        self._success_streak = 0
        self._last_grow_at = 0.0

    def wait_turn(self) -> None:
        if self.spacing <= 0:
            return
        while True:
            with self._lock:
                now = time.time()
                wait = self._next_start - now
                if wait <= 0:
                    self._next_start = now + self.spacing
                    return
            # Sleep outside the lock so other workers are not blocked.
            time.sleep(wait)

    def on_success(self) -> None:
        with self._lock:
            self._success_streak += 1
            if self._success_streak >= self.decay_every and self.spacing > self.min_spacing:
                self.spacing = max(self.min_spacing, self.spacing * self.decay_factor)
                self._success_streak = 0

    def _grow(self, factor: float) -> None:
        """Grow spacing at most once per grow_cooldown (avoids parallel miss storms)."""
        now = time.time()
        if now - self._last_grow_at < self.grow_cooldown:
            return
        self._last_grow_at = now
        self._success_streak = 0
        self.spacing = min(
            self.max_spacing,
            max(self.min_spacing, self.spacing) * factor,
        )

    def on_soft_fail(self) -> None:
        """Mild backoff for empty/404 responses under load."""
        with self._lock:
            self._grow(self.soft_growth)

    def on_block(self) -> None:
        with self._lock:
            self._grow(self.growth)

    def cap_spacing(self, max_spacing: float) -> None:
        """Lower the ceiling and clamp current spacing (retry-tail mode)."""
        with self._lock:
            self.max_spacing = max(self.min_spacing, max_spacing)
            self.spacing = min(self.spacing, self.max_spacing)

    def reset_spacing(self, spacing: float) -> None:
        with self._lock:
            self.spacing = max(self.min_spacing, min(self.max_spacing, spacing))
            self._success_streak = 0
            self._next_start = 0.0


class AdaptivePacer:
    """Back-compat sequential pacer for unit tests."""

    def __init__(
        self,
        delay: float = 0.55,
        min_delay: float = 0.35,
        max_delay: float = 8.0,
        growth: float = 1.7,
        decay_every: int = 20,
        decay_factor: float = 0.9,
    ) -> None:
        self.delay = delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.growth = growth
        self.decay_every = decay_every
        self.decay_factor = decay_factor
        self._success_streak = 0

    def wait(self) -> None:
        time.sleep(self.delay)

    def on_success(self) -> None:
        self._success_streak += 1
        if self._success_streak >= self.decay_every and self.delay > self.min_delay:
            self.delay = max(self.min_delay, self.delay * self.decay_factor)
            self._success_streak = 0

    def on_block(self) -> None:
        self._success_streak = 0
        self.delay = min(self.max_delay, self.delay * self.growth)


def _is_captcha_error(product: ProductDescription) -> bool:
    err = (product.error or "").casefold()
    return any(token in err for token in ("robot", "captcha", "blocked", "validatecaptcha"))


def _is_good(product: ProductDescription) -> bool:
    # Confirmed delisted/unavailable pages count as successful terminal outcomes
    # (no description exists to scrape).
    if product.unavailable and not product.error:
        return True
    return not product.error and bool(
        product.title or product.feature_bullets or product.best_description
    )


def _load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for item in data.get("products") or []:
        asin = item.get("asin")
        if asin and not item.get("error"):
            out[asin] = item
    return out


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _product_from_dict(item: dict, marketplace: Marketplace) -> ProductDescription:
    return ProductDescription(
        asin=item["asin"],
        marketplace=item.get("marketplace") or marketplace.domain,
        url=item.get("url") or marketplace.product_url(item["asin"]),
        title=item.get("title"),
        brand=item.get("brand"),
        feature_bullets=item.get("feature_bullets") or [],
        description=item.get("description"),
        aplus_text=item.get("aplus_text"),
        overview=item.get("overview") or {},
        meta_description=item.get("meta_description"),
        provider=item.get("provider") or "turbo",
        source_bytes=item.get("source_bytes"),
        error=item.get("error"),
        unavailable=bool(item.get("unavailable")),
    )


class BulkPipeline:
    def __init__(
        self,
        marketplace: str | Marketplace = "nl",
        delay: float | None = None,
        spacing: float | None = None,
        workers: int = 12,
        checkpoint_every: int = 50,
        engine: str = "turbo",
        max_passes: int = 15,
        max_retries: int = 5,
        stream_retries: bool = False,
        stable: bool = True,
        log: Callable[[str], None] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        self.marketplace = (
            marketplace
            if isinstance(marketplace, Marketplace)
            else resolve_marketplace(marketplace)
        )
        self.engine = engine
        self.stable = stable
        self.max_passes = max(1, max_passes)
        self.max_retries = max(0, max_retries)
        self.stream_retries = bool(stream_retries)
        if engine == "turbo":
            default_spacing = 0.05 if stable else 0.02
            default_workers = 12 if stable else 24
        else:
            default_spacing = 0.12
            default_workers = 5
        initial = (
            default_spacing
            if spacing is None and delay is None
            else (spacing if spacing is not None else delay)
        )
        assert initial is not None
        self.workers = max(1, workers if workers is not None else default_workers)
        self.checkpoint_every = max(1, checkpoint_every)
        self.stream = stream or sys.stderr
        self._log = log or (lambda msg: print(msg, file=self.stream, flush=True))
        self.gate = SpacingGate(
            spacing=initial,
            min_spacing=0.03 if (engine == "turbo" and stable) else (0.015 if engine == "turbo" else 0.08),
            max_spacing=1.25 if (engine == "turbo" and stable) else (2.0 if engine == "turbo" else 8.0),
            growth=1.4,
            soft_growth=1.06,
            decay_every=15 if stable else 40,
            decay_factor=0.90,
            grow_cooldown=3.0 if stable else 1.0,
        )
        self._stats_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._turbo: TurboClient | None = None
        self._soft_local = threading.local()

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._log(f"[{ts}] {msg}")

    def _client_fetch(
        self,
        asin: str,
        *,
        prefer_html: bool = False,
        confirm_unavailable: bool = False,
        skip_dp: bool = False,
        multi_host: bool = False,
    ) -> ProductDescription:
        if self.engine == "turbo":
            assert self._turbo is not None
            return self._turbo.fetch(
                asin,
                self.marketplace,
                prefer_html=prefer_html,
                confirm_unavailable=confirm_unavailable,
                skip_dp=skip_dp,
                multi_host=multi_host,
            )
        provider = getattr(self._soft_local, "provider", None)
        if provider is None:
            fetcher = Fetcher(
                language=f"{self.marketplace.language},en;q=0.8",
                max_retries=2,
                backoff=1.0,
            )
            provider = SoftProvider(fetcher=fetcher, no_cache=True, max_attempts=2)
            self._soft_local.provider = provider
        return provider.fetch(asin, self.marketplace)

    def _fetch_asin(
        self,
        asin: str,
        *,
        prefer_html: bool = False,
        attempts: int = 2,
        grow_on_soft_fail: bool = True,
        confirm_unavailable: bool = False,
        skip_dp: bool = False,
        multi_host: bool = False,
    ) -> ProductDescription:
        """Fetch with in-pass attempts; optional soft-fail growth."""
        last = None
        for _attempt in range(max(1, attempts)):
            self.gate.wait_turn()
            product = self._client_fetch(
                asin,
                prefer_html=prefer_html,
                confirm_unavailable=confirm_unavailable,
                skip_dp=skip_dp,
                multi_host=multi_host,
            )
            last = product
            if _is_good(product):
                return product
            if _is_captcha_error(product):
                self.gate.on_block()
                time.sleep(min(8.0, max(1.0, self.gate.spacing * 2)))
            elif grow_on_soft_fail:
                self.gate.on_soft_fail()
            else:
                time.sleep(min(1.5, self.gate.spacing))
        assert last is not None
        return last

    def _warm(self) -> None:
        if self.engine == "turbo":
            # Reuse client across iterations: keeps connection pool + no-twister memory.
            if self._turbo is None:
                self._turbo = TurboClient(
                    pool_size=max(80, self.workers * 6),
                    retries=0,  # Amazon soft 5xx retries only add latency
                    timeout=8.0 if self.stable else 6.0,
                    twister_timeout=4.0,
                    no_cache=True,
                )
            self._turbo.warm(self.marketplace)
        else:
            Fetcher(language=f"{self.marketplace.language},en;q=0.8").get(
                self.marketplace.base_url + "/", check_robot=False
            )

    def run(
        self,
        asins: list[str],
        *,
        output: Path | str,
        resume: bool = True,
        max_items: int | None = None,
        allow_duplicates: bool = False,
    ) -> PipelineStats:
        output_path = Path(output)
        checkpoint_path = output_path.with_suffix(output_path.suffix + ".checkpoint.json")

        normalized: list[str] = []
        seen: set[str] = set()
        for value in asins:
            asin = extract_asin(value)
            if not asin:
                continue
            if allow_duplicates:
                normalized.append(asin)
            elif asin not in seen:
                seen.add(asin)
                normalized.append(asin)
        if max_items is not None:
            normalized = normalized[:max_items]

        done = _load_checkpoint(checkpoint_path) if resume and not allow_duplicates else {}
        if done:
            self.log(f"RESUME: loaded {len(done)} OK products from {checkpoint_path}")

        # Unique pending for stable 100% mode; allow_duplicates keeps every line.
        if allow_duplicates:
            pending = list(normalized)
        else:
            pending = [a for a in normalized if a not in done]

        stats = PipelineStats(
            total=len(normalized) if allow_duplicates else len(dict.fromkeys(normalized)),
            delay=self.gate.spacing,
            workers=self.workers,
            engine=self.engine,
        )
        stats.ok = len(done)
        stats.attempted = len(done)
        for item in done.values():
            prov = item.get("provider") or "unknown"
            stats.by_provider[prov] = stats.by_provider.get(prov, 0) + 1
            stats.bytes_total += int(item.get("source_bytes") or 0)

        if self.stream_retries and self.stable:
            mode = "stream-retries"
        elif self.stable:
            mode = "iterative-pass1"
        else:
            mode = "fast-single"
        max_tries = 1 + self.max_retries if self.stream_retries else self.max_passes
        self.log(
            f"START engine={self.engine} mode={mode} marketplace={self.marketplace.domain} "
            f"total={stats.total} pending={len(pending)} workers={self.workers} "
            f"spacing={self.gate.spacing:.3f}s "
            f"{'max_retries=' + str(self.max_retries) + ' max_tries=' + str(max_tries) if self.stream_retries else 'max_iterations=' + str(self.max_passes)} "
            f"checkpoint_every={self.checkpoint_every} no_cache=1"
        )

        self._warm()
        self.log("Session warmed")

        failures: list[dict] = []
        last_miss: dict[str, ProductDescription] = {}
        since_checkpoint = 0
        remaining = list(pending)

        def write_checkpoint() -> None:
            nonlocal since_checkpoint
            with self._io_lock:
                with self._stats_lock:
                    payload = {
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "marketplace": self.marketplace.domain,
                        "provider": self.engine,
                        "stats": stats.to_dict(),
                        "total": len(done),
                        "products": list(done.values()),
                        "failures": failures[-50:],
                        "pending_estimate": max(0, stats.total - stats.ok),
                    }
                    since_checkpoint = 0
                    pending_est = payload["pending_estimate"]
                _atomic_write_json(checkpoint_path, payload)
                self.log(
                    f"CHECKPOINT wrote {payload['total']} products → {checkpoint_path} "
                    f"providers={dict(stats.by_provider)} pending≈{pending_est}"
                )

        def handle_success(asin: str, product: ProductDescription) -> None:
            nonlocal since_checkpoint
            with self._stats_lock:
                done[asin] = product.to_dict()
                stats.note_success(product)
                self.gate.on_success()
                stats.delay = self.gate.spacing
                since_checkpoint += 1
                ok = stats.ok
                attempted = stats.attempted
                rate = stats.rate
                eta = stats.eta_seconds
                spacing = self.gate.spacing
                should_checkpoint = since_checkpoint >= self.checkpoint_every
            eta_s = "?" if eta is None else f"{eta/60:.1f}m"
            self.log(
                f"OK [{ok}/{stats.total}] asin={asin} "
                f"provider={product.provider} bullets={len(product.feature_bullets)} "
                f"bytes={product.source_bytes or 0} "
                f"ok={ok} fail={stats.failed} captcha={stats.captcha_hits} "
                f"rate={rate:.2f}/s eta={eta_s} spacing={spacing:.3f}s "
                f"workers={self.workers} pass={stats.passes}"
            )
            if should_checkpoint:
                write_checkpoint()

        # --- Fast stream: bulk first-pass → low-concurrency delayed retries ---
        if self.stream_retries and self.engine == "turbo":
            max_tries = 1 + self.max_retries
            pass1_spacing = max(
                self.gate.min_spacing, 0.05 if self.stable else self.gate.spacing
            )
            # Cap global spacing so soft-fails cannot push the gate to ~1s.
            self.gate.cap_spacing(0.22)
            self.gate.reset_spacing(pass1_spacing)
            # Tail concurrency: moderate, then tighter when few ASINs remain.
            tail_workers = max(4, min(8, max(1, self.workers // 3)))
            deep_tail_workers = 3
            ok_by_try: dict[int, int] = {}
            fail_by_try: dict[int, int] = {}
            max_try_seen = 1
            progress_every = max(25, min(100, stats.total // 20 or 25))

            def _asin_backoff(attempt: int) -> float:
                # Per-ASIN delay before next try (does not slow other ASINs).
                base = min(1.6, 0.12 * (1.30 ** max(0, attempt - 1)))
                # Deep tries: extra cool-down so Amazon soft-5xx can clear.
                if attempt >= 10:
                    base += 0.8
                return base

            def _fetch_try(asin: str, attempt: int) -> ProductDescription:
                skip_dp = attempt == 1
                in_fetch_attempts = 1 if attempt == 1 else 2
                # Mild global growth only in bulk; tail relies on per-ASIN backoff + cap.
                grow = attempt == 1
                no_tw = bool(self._turbo and self._turbo.knows_no_twister(asin))
                # Global aw failover (EU/US/…) from try 1 after local miss.
                # prefer_html only forces aw-first order for known no-twister.
                prefer_html = no_tw
                multi_host = True
                confirm_unavailable = attempt >= 3
                try:
                    product = self._fetch_asin(
                        asin,
                        prefer_html=prefer_html,
                        attempts=in_fetch_attempts,
                        grow_on_soft_fail=grow,
                        confirm_unavailable=confirm_unavailable,
                        skip_dp=skip_dp,
                        multi_host=multi_host,
                    )
                except Exception as exc:  # noqa: BLE001
                    return ProductDescription(
                        asin=asin,
                        marketplace=self.marketplace.domain,
                        url=self.marketplace.product_url(asin),
                        provider=self.engine,
                        error=str(exc),
                    )
                if _is_good(product):
                    return product
                # Stop burning retries on hard-404 / delisted ASINs.
                if (
                    self._turbo is not None
                    and attempt >= 3
                    and (no_tw or attempt >= 6)
                ):
                    delisted = self._turbo.probe_delisted(
                        asin, self.marketplace, min_404s=3
                    )
                    if delisted is not None:
                        self.log(
                            f"DELIST asin={asin} try={attempt} "
                            f"→ unavailable (stop retries)"
                        )
                        return delisted
                return product

            self.log(
                f"STREAM start: pending={len(remaining)} bulk_workers={self.workers} "
                f"tail_workers={tail_workers} max_retries={self.max_retries} "
                f"max_tries={max_tries} spacing={self.gate.spacing:.3f}s "
                f"spacing_cap={self.gate.max_spacing:.3f}s "
                f"multi_host=1 (EU/US/global from try 1)"
            )

            # Phase 1 — full concurrency, first try only (no retry overlap).
            phase1_misses: list[tuple[str, ProductDescription]] = []
            bulk = list(remaining)
            stats.passes = 1
            if bulk:
                chunk_size = max(self.workers * 10, 100)

                def bulk_one(asin: str) -> tuple[str, ProductDescription]:
                    return asin, _fetch_try(asin, 1)

                for chunk_start in range(0, len(bulk), chunk_size):
                    chunk = bulk[chunk_start : chunk_start + chunk_size]
                    if self.workers == 1:
                        chunk_results = [bulk_one(a) for a in chunk]
                    else:
                        chunk_results = []
                        with ThreadPoolExecutor(max_workers=self.workers) as pool:
                            futs = [pool.submit(bulk_one, a) for a in chunk]
                            for fut in as_completed(futs):
                                chunk_results.append(fut.result())
                    for asin, product in chunk_results:
                        if _is_good(product):
                            last_miss.pop(asin, None)
                            with self._stats_lock:
                                ok_by_try[1] = ok_by_try.get(1, 0) + 1
                            handle_success(asin, product)
                        else:
                            last_miss[asin] = product
                            with self._stats_lock:
                                stats.retries += 1
                                fail_by_try[1] = fail_by_try.get(1, 0) + 1
                            phase1_misses.append((asin, product))

            write_checkpoint()
            no_twister_n = len(self._turbo._no_twister) if self._turbo else 0
            self.log(
                f"STREAM phase1 done: ok={stats.ok}/{stats.total} "
                f"misses={len(phase1_misses)} no_twister_known={no_twister_n} "
                f"spacing={self.gate.spacing:.3f}s → tail_workers={tail_workers}"
            )

            # Phase 2 — low concurrency + per-ASIN delayed requeue.
            if phase1_misses and self.max_retries > 0:
                self.gate.cap_spacing(0.25)
                self.gate.reset_spacing(0.10)
                self._warm()

                heap: list[tuple[float, int, str, int]] = []
                seq = itertools.count()
                heap_lock = threading.Lock()
                pending_terminal = len(phase1_misses)
                terminal_lock = threading.Lock()
                inflight_limit = {"n": tail_workers}
                limit_lock = threading.Lock()
                inflight_n = 0
                inflight_lock = threading.Lock()
                wake = threading.Event()

                now0 = time.time()
                for asin, _prod in phase1_misses:
                    heapq.heappush(
                        heap, (now0 + _asin_backoff(1), next(seq), asin, 2)
                    )

                def _adjust_inflight_limit() -> None:
                    with terminal_lock:
                        left = pending_terminal
                    target = deep_tail_workers if left <= 40 else tail_workers
                    with limit_lock:
                        if target == inflight_limit["n"]:
                            return
                        old = inflight_limit["n"]
                        inflight_limit["n"] = target
                    if target < old:
                        self.log(
                            f"STREAM deep-tail: pending≈{left} → "
                            f"inflight_limit {old}->{target}"
                        )

                def push_retry(asin: str, next_attempt: int) -> None:
                    ready = time.time() + _asin_backoff(next_attempt - 1)
                    with heap_lock:
                        heapq.heappush(heap, (ready, next(seq), asin, next_attempt))
                    wake.set()

                def pop_ready() -> tuple[str, int] | None:
                    with heap_lock:
                        if not heap:
                            return None
                        ready, _, asin, attempt = heap[0]
                        if ready - time.time() > 0:
                            return None
                        heapq.heappop(heap)
                        return asin, attempt

                def tail_worker() -> None:
                    nonlocal max_try_seen, pending_terminal, inflight_n
                    while True:
                        with terminal_lock:
                            if pending_terminal <= 0:
                                wake.set()
                                return
                        _adjust_inflight_limit()
                        with limit_lock:
                            allowed = inflight_limit["n"]
                        with inflight_lock:
                            at_cap = inflight_n >= allowed
                        if at_cap:
                            wake.wait(timeout=0.15)
                            wake.clear()
                            continue

                        item = pop_ready()
                        if item is None:
                            with heap_lock:
                                if heap:
                                    wait = max(0.01, heap[0][0] - time.time())
                                else:
                                    wait = 0.05
                            wake.wait(timeout=min(wait, 0.25))
                            wake.clear()
                            continue

                        with inflight_lock:
                            if inflight_n >= allowed:
                                # Slot lost — put work back.
                                asin, attempt = item
                                with heap_lock:
                                    heapq.heappush(
                                        heap, (time.time(), next(seq), asin, attempt)
                                    )
                                continue
                            inflight_n += 1

                        try:
                            asin, attempt = item
                            with self._stats_lock:
                                max_try_seen = max(max_try_seen, attempt)
                                stats.passes = max_try_seen

                            product = _fetch_try(asin, attempt)
                            if _is_good(product):
                                last_miss.pop(asin, None)
                                with self._stats_lock:
                                    ok_by_try[attempt] = ok_by_try.get(attempt, 0) + 1
                                handle_success(asin, product)
                                with terminal_lock:
                                    pending_terminal -= 1
                            elif attempt < max_tries:
                                last_miss[asin] = product
                                with self._stats_lock:
                                    stats.retries += 1
                                    fail_by_try[attempt] = (
                                        fail_by_try.get(attempt, 0) + 1
                                    )
                                    requeues = stats.retries
                                push_retry(asin, attempt + 1)
                                if requeues % progress_every == 0:
                                    with heap_lock:
                                        hq = len(heap)
                                    self.log(
                                        f"STREAM requeue asin={asin} "
                                        f"try={attempt}->{attempt + 1} "
                                        f"ok={stats.ok}/{stats.total} "
                                        f"requeues={requeues} tail_q≈{hq} "
                                        f"inflight_cap={allowed} "
                                        f"spacing={self.gate.spacing:.3f}s "
                                        f"backoff={_asin_backoff(attempt):.2f}s"
                                    )
                            else:
                                last_miss[asin] = product
                                with self._stats_lock:
                                    fail_by_try[attempt] = (
                                        fail_by_try.get(attempt, 0) + 1
                                    )
                                    stats.note_failure(
                                        product, captcha=_is_captcha_error(product)
                                    )
                                    failures.append(product.to_dict())
                                self.log(
                                    f"FAIL [{stats.ok + stats.failed}/{stats.total}] "
                                    f"asin={asin} exhausted stream retries "
                                    f"(tries={attempt}/{max_tries})"
                                )
                                with terminal_lock:
                                    pending_terminal -= 1
                        finally:
                            with inflight_lock:
                                inflight_n -= 1
                            wake.set()

                threads = [
                    threading.Thread(
                        target=tail_worker, name=f"stream-tail-{i}", daemon=True
                    )
                    for i in range(tail_workers)
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

            remaining = []
            write_checkpoint()
            self.log(
                f"STREAM done: ok_by_try={dict(sorted(ok_by_try.items()))} "
                f"miss_by_try={dict(sorted(fail_by_try.items()))} "
                f"requeues={stats.retries} max_try_seen={max_try_seen} "
                f"tail_workers={tail_workers}"
            )

            products = [
                _product_from_dict(item, self.marketplace) for item in done.values()
            ]
            if not allow_duplicates:
                order = {a: i for i, a in enumerate(dict.fromkeys(normalized))}
                products.sort(key=lambda p: order.get(p.asin, 10**9))

            if output_path.suffix.lower() == ".csv":
                write_csv(output_path, products)
            else:
                write_json(
                    output_path,
                    products,
                    marketplace=self.marketplace.domain,
                    provider=self.engine,
                )
                final = json.loads(output_path.read_text(encoding="utf-8"))
                final["stats"] = stats.to_dict()
                final["failures_count"] = stats.failed
                final["pending_final"] = remaining
                final["ok_by_try"] = ok_by_try
                final["miss_by_try"] = fail_by_try
                final["tail_workers"] = tail_workers
                _atomic_write_json(output_path, final)

            success_rate = (stats.ok / stats.total) if stats.total else 0
            self.log(
                f"DONE engine={self.engine} mode={mode} ok={stats.ok}/{stats.total} "
                f"fail={stats.failed} captcha_hits={stats.captcha_hits} "
                f"success_rate={success_rate:.1%} max_try={stats.passes} "
                f"requeues={stats.retries} elapsed={stats.elapsed:.1f}s "
                f"avg_rate={stats.rate:.2f}/s workers={self.workers} "
                f"tail_workers={tail_workers} spacing={self.gate.spacing:.3f}s "
                f"providers={stats.by_provider} output={output_path}"
            )
            if stats.failed == 0 and stats.total > 0:
                self.log(
                    f"STREAM_RETRIES_NEEDED={max(ok_by_try) if ok_by_try else 1} "
                    f"(tries until 100% match: {stats.ok}/{stats.total})"
                )
            else:
                self.log(
                    f"STREAM_RETRIES_USED={self.max_retries} "
                    f"(incomplete: {stats.ok}/{stats.total}, fail={stats.failed})"
                )
            return stats

        # Always pass-1 settings: ajax-first chain, full workers, soft-fail growth.
        # Turbo remembers structural no-twister ASINs → aw-first on later attempts.
        grow_on_soft_fail = True
        confirm_unavailable = False
        pass_workers = self.workers
        pass1_spacing = max(self.gate.min_spacing, 0.05 if self.stable else self.gate.spacing)

        for iter_num in range(1, self.max_passes + 1):
            if not remaining:
                break
            stats.passes = iter_num
            # Reset to pass-1 baseline each iteration (adaptive growth still applies in-iter).
            self.gate.spacing = pass1_spacing
            # Iter 1: single attempt, skip heavy /dp. Later: 2 attempts + full chain.
            attempts = 1 if iter_num == 1 else 2
            skip_dp = iter_num == 1

            before_ok = stats.ok
            before_pending = len(remaining)
            no_twister_n = len(self._turbo._no_twister) if self._turbo else 0
            self.log(
                f"ITER {iter_num}/{self.max_passes}: pending={before_pending} "
                f"workers={pass_workers} spacing={self.gate.spacing:.3f}s "
                f"attempts={attempts} skip_dp={int(skip_dp)} "
                f"no_twister_known={no_twister_n} ok_so_far={stats.ok}/{stats.total}"
            )

            if iter_num > 1:
                # Re-warm cookies only; keep pooled client + no-twister memory.
                self._warm()
                pause = 0.5
                self.log(f"ITER cooldown {pause:.1f}s before retrying failures (pass-1 again)")
                time.sleep(pause)

            pass_failures: list[tuple[str, ProductDescription]] = []
            batch = list(remaining)

            def run_one(asin: str) -> tuple[str, ProductDescription]:
                try:
                    # no-twister ASINs are aw-first inside TurboClient (no EU fan-out).
                    return asin, self._fetch_asin(
                        asin,
                        prefer_html=False,
                        attempts=attempts,
                        grow_on_soft_fail=grow_on_soft_fail,
                        confirm_unavailable=confirm_unavailable,
                        skip_dp=skip_dp,
                    )
                except Exception as exc:  # noqa: BLE001
                    return asin, ProductDescription(
                        asin=asin,
                        marketplace=self.marketplace.domain,
                        url=self.marketplace.product_url(asin),
                        provider=self.engine,
                        error=str(exc),
                    )

            # Process in chunks so we don't enqueue 10k futures at once and so
            # checkpoints/logs stream steadily during long runs.
            chunk_size = max(pass_workers * 10, 100)
            for chunk_start in range(0, len(batch), chunk_size):
                chunk = batch[chunk_start : chunk_start + chunk_size]
                if pass_workers == 1:
                    chunk_results = [run_one(a) for a in chunk]
                else:
                    chunk_results = []
                    with ThreadPoolExecutor(max_workers=pass_workers) as pool:
                        futures = [pool.submit(run_one, a) for a in chunk]
                        for fut in as_completed(futures):
                            chunk_results.append(fut.result())

                for asin, product in chunk_results:
                    if _is_good(product):
                        last_miss.pop(asin, None)
                        handle_success(asin, product)
                    else:
                        with self._stats_lock:
                            stats.retries += 1
                        last_miss[asin] = product
                        pass_failures.append((asin, product))
                        # Spacing growth already applied inside _fetch_asin.
                        self.log(
                            f"MISS [iter={iter_num}] asin={asin} "
                            f"provider={product.provider} err={(product.error or 'empty')[:60]} "
                            f"spacing={self.gate.spacing:.3f}s still_bad={len(pass_failures)}"
                        )

            remaining = [a for a, _ in pass_failures]
            recovered = stats.ok - before_ok
            write_checkpoint()
            self.log(
                f"ITER {iter_num} done: recovered={recovered} "
                f"ok={stats.ok}/{stats.total} remaining={len(remaining)}"
            )

            if remaining and iter_num < self.max_passes:
                self.log(
                    f"ITER {iter_num} incomplete → next pass-1 round "
                    f"({len(remaining)} pending)"
                )

        # Final failures after all iterations
        for asin in remaining:
            product = last_miss.get(asin) or ProductDescription(
                asin=asin,
                marketplace=self.marketplace.domain,
                url=self.marketplace.product_url(asin),
                provider=self.engine,
                error="exhausted iterative pass-1 retries",
            )
            if not product.error:
                product.error = "exhausted iterative pass-1 retries"
            captcha = _is_captcha_error(product)
            with self._stats_lock:
                stats.note_failure(product, captcha=captcha)
                failures.append(product.to_dict())
            self.log(
                f"FAIL [{stats.ok + stats.failed}/{stats.total}] asin={asin} exhausted iterations"
            )

        write_checkpoint()

        products = [_product_from_dict(item, self.marketplace) for item in done.values()]
        # Preserve input order for unique mode
        if not allow_duplicates:
            order = {a: i for i, a in enumerate(dict.fromkeys(normalized))}
            products.sort(key=lambda p: order.get(p.asin, 10**9))

        if output_path.suffix.lower() == ".csv":
            write_csv(output_path, products)
        else:
            write_json(
                output_path,
                products,
                marketplace=self.marketplace.domain,
                provider=self.engine,
            )
            final = json.loads(output_path.read_text(encoding="utf-8"))
            final["stats"] = stats.to_dict()
            final["failures_count"] = stats.failed
            final["pending_final"] = remaining
            _atomic_write_json(output_path, final)

        success_rate = (stats.ok / stats.total) if stats.total else 0
        self.log(
            f"DONE engine={self.engine} mode={mode} ok={stats.ok}/{stats.total} "
            f"fail={stats.failed} captcha_hits={stats.captcha_hits} "
            f"success_rate={success_rate:.1%} iterations={stats.passes} "
            f"elapsed={stats.elapsed:.1f}s avg_rate={stats.rate:.2f}/s "
            f"workers={self.workers} spacing={self.gate.spacing:.3f}s "
            f"providers={stats.by_provider} output={output_path}"
        )
        if stats.failed == 0 and stats.total > 0:
            self.log(
                f"ITERATIONS_NEEDED={stats.passes} "
                f"(pass-1 rounds until 100% match: {stats.ok}/{stats.total})"
            )
        else:
            self.log(
                f"ITERATIONS_USED={stats.passes} "
                f"(incomplete: {stats.ok}/{stats.total}, fail={stats.failed})"
            )
        return stats
