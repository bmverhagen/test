"""Bulk download pipeline — stable multipass turbo by default.

Priority: **100% success**, then speed.
- Pass 1: parallel turbo (ajaxv2 → dimension → aw → dp), no-cache
- Later passes: retry only failures with higher spacing / fewer workers
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
    ) -> ProductDescription:
        if self.engine == "turbo":
            assert self._turbo is not None
            return self._turbo.fetch(
                asin,
                self.marketplace,
                prefer_html=prefer_html,
                confirm_unavailable=confirm_unavailable,
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
    ) -> ProductDescription:
        """Fetch with in-pass attempts; optional soft-fail growth."""
        last = None
        for _attempt in range(max(1, attempts)):
            self.gate.wait_turn()
            product = self._client_fetch(
                asin,
                prefer_html=prefer_html,
                confirm_unavailable=confirm_unavailable,
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
            self._turbo = TurboClient(
                pool_size=max(80, self.workers * 6),
                retries=2,
                timeout=12.0 if self.stable else 8.0,
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

        mode = "stable-multipass" if self.stable else "fast-single"
        self.log(
            f"START engine={self.engine} mode={mode} marketplace={self.marketplace.domain} "
            f"total={stats.total} pending={len(pending)} workers={self.workers} "
            f"spacing={self.gate.spacing:.3f}s max_passes={self.max_passes} "
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

        for pass_num in range(1, self.max_passes + 1):
            if not remaining:
                break
            stats.passes = pass_num
            # Retry / resume-tail: HTML-first, fixed spacing (no soft-fail storms).
            # If we already have successes (checkpoint resume), treat pass 1 as retry.
            resume_tail = bool(done) and pass_num == 1 and len(remaining) < stats.total
            prefer_html = self.stable and (pass_num >= 2 or resume_tail)
            grow_on_soft_fail = not prefer_html
            # Enable delist confirmation on late passes, or immediately when
            # resuming a tiny hard-fail tail (already retried many times).
            confirm_unavailable = self.stable and (
                pass_num >= 6 or (resume_tail and len(remaining) <= 25)
            )
            attempts = 2 if (pass_num == 1 and not prefer_html) else (3 if pass_num < 5 else 4)
            if prefer_html:
                pass_workers = max(2, min(6, self.workers - 2 * max(0, pass_num - 1)))
            else:
                pass_workers = self.workers
            if self.stable:
                if not prefer_html:
                    self.gate.spacing = max(self.gate.min_spacing, 0.05)
                elif pass_num < 5:
                    self.gate.spacing = 0.12
                else:
                    self.gate.spacing = 0.25

            self.log(
                f"PASS {pass_num}/{self.max_passes}: pending={len(remaining)} "
                f"workers={pass_workers} spacing={self.gate.spacing:.3f}s "
                f"prefer_html={prefer_html} attempts={attempts} "
                f"ok_so_far={stats.ok}/{stats.total}"
            )

            if pass_num > 1:
                # Fresh session helps after throttle windows
                self._warm()
                # Late passes often hit Amazon 500 storms — wait longer.
                if pass_num >= 8:
                    pause = min(90.0, 20.0 + 8.0 * (pass_num - 8))
                else:
                    pause = min(15.0, 1.4 ** (pass_num - 1))
                self.log(f"PASS cooldown {pause:.1f}s before retrying failures")
                time.sleep(pause)

            pass_failures: list[tuple[str, ProductDescription]] = []
            batch = list(remaining)

            def run_one(asin: str) -> tuple[str, ProductDescription]:
                try:
                    return asin, self._fetch_asin(
                        asin,
                        prefer_html=prefer_html,
                        attempts=attempts,
                        grow_on_soft_fail=grow_on_soft_fail,
                        confirm_unavailable=confirm_unavailable,
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
                        if _is_captcha_error(product):
                            self.gate.on_block()
                        elif grow_on_soft_fail:
                            self.gate.on_soft_fail()
                        self.log(
                            f"MISS [pass={pass_num}] asin={asin} "
                            f"provider={product.provider} err={(product.error or 'empty')[:60]} "
                            f"spacing={self.gate.spacing:.3f}s still_bad={len(pass_failures)}"
                        )

            remaining = [a for a, _ in pass_failures]
            write_checkpoint()

            if remaining and pass_num < self.max_passes:
                self.log(
                    f"PASS {pass_num} done: recovered batch; "
                    f"{len(remaining)} still pending → next pass"
                )

        # Final failures after all passes
        for asin in remaining:
            product = last_miss.get(asin) or ProductDescription(
                asin=asin,
                marketplace=self.marketplace.domain,
                url=self.marketplace.product_url(asin),
                provider=self.engine,
                error="exhausted multipass retries",
            )
            if not product.error:
                product.error = "exhausted multipass retries"
            captcha = _is_captcha_error(product)
            with self._stats_lock:
                stats.note_failure(product, captcha=captcha)
                failures.append(product.to_dict())
            self.log(
                f"FAIL [{stats.ok + stats.failed}/{stats.total}] asin={asin} exhausted passes"
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
            f"success_rate={success_rate:.1%} passes={stats.passes} "
            f"elapsed={stats.elapsed:.1f}s avg_rate={stats.rate:.2f}/s "
            f"workers={self.workers} spacing={self.gate.spacing:.3f}s "
            f"providers={stats.by_provider} output={output_path}"
        )
        return stats
