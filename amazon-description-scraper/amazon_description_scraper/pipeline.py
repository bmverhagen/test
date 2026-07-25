"""Bulk download pipeline — turbo by default, soft/safe available.

Speed ladder validated on amazon.nl (no HTTP cache):
- --safe sequential soft: ~0.57/s
- soft parallel w5/s0.12: ~3.9/s
- turbo w24/s0.02 + fast_parse: ~9.9/s on 200/200 (0 captcha)
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
    by_provider: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    delay: float = 0.02
    workers: int = 24
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
        remaining = self.total - self.attempted
        if remaining <= 0 or self.rate <= 0:
            return 0.0
        return remaining / self.rate

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "elapsed": round(self.elapsed, 2),
            "rate_per_sec": round(self.rate, 3),
            "eta_seconds": None if self.eta_seconds is None else round(self.eta_seconds, 1),
            "success_rate": round(self.ok / self.attempted, 4) if self.attempted else None,
        }


class SpacingGate:
    def __init__(
        self,
        spacing: float = 0.02,
        min_spacing: float = 0.015,
        max_spacing: float = 2.0,
        growth: float = 1.8,
        decay_every: int = 40,
        decay_factor: float = 0.92,
    ) -> None:
        self.spacing = spacing
        self.min_spacing = min_spacing
        self.max_spacing = max_spacing
        self.growth = growth
        self.decay_every = decay_every
        self.decay_factor = decay_factor
        self._lock = threading.Lock()
        self._next_start = 0.0
        self._success_streak = 0

    def wait_turn(self) -> None:
        if self.spacing <= 0:
            return
        with self._lock:
            now = time.time()
            wait = self._next_start - now
            if wait > 0:
                time.sleep(wait)
            self._next_start = time.time() + self.spacing

    def on_success(self) -> None:
        with self._lock:
            self._success_streak += 1
            if self._success_streak >= self.decay_every and self.spacing > self.min_spacing:
                self.spacing = max(self.min_spacing, self.spacing * self.decay_factor)
                self._success_streak = 0

    def on_block(self) -> None:
        with self._lock:
            self._success_streak = 0
            self.spacing = min(self.max_spacing, max(self.min_spacing, self.spacing) * self.growth)


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
    )


class BulkPipeline:
    def __init__(
        self,
        marketplace: str | Marketplace = "nl",
        delay: float | None = None,
        spacing: float | None = None,
        workers: int = 24,
        checkpoint_every: int = 50,
        engine: str = "turbo",
        log: Callable[[str], None] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        self.marketplace = (
            marketplace
            if isinstance(marketplace, Marketplace)
            else resolve_marketplace(marketplace)
        )
        self.engine = engine
        if engine == "turbo":
            default_spacing = 0.02
            default_workers = 24
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
            min_spacing=0.015 if engine == "turbo" else 0.08,
            max_spacing=2.0 if engine == "turbo" else 4.0,
            growth=1.8,
            decay_every=40,
            decay_factor=0.92,
        )
        self._stats_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._turbo: TurboClient | None = None
        self._soft_local = threading.local()

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._log(f"[{ts}] {msg}")

    def _client_fetch(self, asin: str) -> ProductDescription:
        if self.engine == "turbo":
            assert self._turbo is not None
            return self._turbo.fetch(asin, self.marketplace)
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

    def _fetch_asin(self, asin: str) -> ProductDescription:
        self.gate.wait_turn()
        product = self._client_fetch(asin)
        if _is_good(product):
            return product
        self.gate.on_block()
        self.gate.wait_turn()
        return self._client_fetch(asin)

    def run(
        self,
        asins: list[str],
        *,
        output: Path | str,
        resume: bool = True,
        max_items: int | None = None,
    ) -> PipelineStats:
        output_path = Path(output)
        checkpoint_path = output_path.with_suffix(output_path.suffix + ".checkpoint.json")

        seen: set[str] = set()
        normalized: list[str] = []
        for value in asins:
            asin = extract_asin(value)
            if asin and asin not in seen:
                seen.add(asin)
                normalized.append(asin)
        if max_items is not None:
            normalized = normalized[:max_items]

        done = _load_checkpoint(checkpoint_path) if resume else {}
        if done:
            self.log(f"RESUME: loaded {len(done)} OK products from {checkpoint_path}")
        pending = [a for a in normalized if a not in done]

        stats = PipelineStats(
            total=len(normalized),
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

        self.log(
            f"START engine={self.engine} marketplace={self.marketplace.domain} "
            f"total={len(normalized)} pending={len(pending)} workers={self.workers} "
            f"spacing={self.gate.spacing:.3f}s checkpoint_every={self.checkpoint_every} no_cache=1"
        )

        if self.engine == "turbo":
            self._turbo = TurboClient(pool_size=max(120, self.workers * 5), retries=1, timeout=8.0)
            self._turbo.warm(self.marketplace)
        else:
            Fetcher(language=f"{self.marketplace.language},en;q=0.8").get(
                self.marketplace.base_url + "/", check_robot=False
            )
        self.log("Session warmed")

        failures: list[dict] = []
        since_checkpoint = 0

        def handle_result(asin: str, product: ProductDescription) -> None:
            nonlocal since_checkpoint
            captcha = _is_captcha_error(product)
            with self._stats_lock:
                if _is_good(product):
                    done[asin] = product.to_dict()
                    stats.note_success(product)
                    self.gate.on_success()
                    status = "OK"
                    since_checkpoint += 1
                else:
                    stats.note_failure(product, captcha=captcha)
                    failures.append(product.to_dict())
                    self.gate.on_block()
                    status = "FAIL"
                stats.delay = self.gate.spacing
                attempted = stats.attempted
                ok = stats.ok
                failed = stats.failed
                captcha_hits = stats.captcha_hits
                rate = stats.rate
                eta = stats.eta_seconds
                spacing = self.gate.spacing
                providers = dict(stats.by_provider)
                should_checkpoint = since_checkpoint >= self.checkpoint_every

            eta_s = "?" if eta is None else f"{eta/60:.1f}m"
            self.log(
                f"{status} [{attempted}/{stats.total}] asin={asin} "
                f"provider={product.provider} bullets={len(product.feature_bullets)} "
                f"bytes={product.source_bytes or 0} "
                f"ok={ok} fail={failed} captcha={captcha_hits} "
                f"rate={rate:.2f}/s eta={eta_s} spacing={spacing:.3f}s workers={self.workers}"
            )

            if should_checkpoint or attempted >= stats.total:
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
                        }
                        since_checkpoint = 0
                    _atomic_write_json(checkpoint_path, payload)
                    self.log(
                        f"CHECKPOINT wrote {payload['total']} products → {checkpoint_path} "
                        f"providers={providers}"
                    )

        if self.workers == 1:
            for asin in pending:
                product = self._fetch_asin(asin)
                if not _is_good(product):
                    with self._stats_lock:
                        stats.retries += 1
                handle_result(asin, product)
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(self._fetch_asin, asin): asin for asin in pending}
                for future in as_completed(futures):
                    asin = futures[future]
                    try:
                        product = future.result()
                    except Exception as exc:  # noqa: BLE001
                        product = ProductDescription(
                            asin=asin,
                            marketplace=self.marketplace.domain,
                            url=self.marketplace.product_url(asin),
                            provider=self.engine,
                            error=str(exc),
                        )
                    if not _is_good(product):
                        with self._stats_lock:
                            stats.retries += 1
                    handle_result(asin, product)

        products = [_product_from_dict(item, self.marketplace) for item in done.values()]
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
            _atomic_write_json(output_path, final)

        success_rate = (stats.ok / stats.total) if stats.total else 0
        self.log(
            f"DONE engine={self.engine} ok={stats.ok}/{stats.total} fail={stats.failed} "
            f"captcha_hits={stats.captcha_hits} success_rate={success_rate:.1%} "
            f"elapsed={stats.elapsed:.1f}s avg_rate={stats.rate:.2f}/s "
            f"workers={self.workers} spacing={self.gate.spacing:.3f}s "
            f"providers={stats.by_provider} output={output_path}"
        )
        return stats
