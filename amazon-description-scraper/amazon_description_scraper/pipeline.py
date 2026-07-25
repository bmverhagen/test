"""Stable bulk download pipeline for hundreds/thousands of ASINs.

Design goals (validated against amazon.nl):
- Prefer twister, fall back to /dp (SoftProvider)
- Sequential by default; adaptive delay grows on captcha/blocks
- Checkpoint every N items so long runs can resume
- Live progress logs to stderr (ok/fail/rate/ETA/provider mix)
- Always cache-bust (no shared HTTP cache reliance)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from .models import Marketplace, ProductDescription, resolve_marketplace
from .providers.soft import SoftProvider
from .scraper import DescriptionScraper
from .storage import write_csv, write_json

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
    delay: float = 0.55

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


class AdaptivePacer:
    """Increase delay on blocks; slowly ease back after success streaks."""

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
        time.sleep(self.delay)


def _is_captcha_error(product: ProductDescription) -> bool:
    err = (product.error or "").casefold()
    return any(
        token in err
        for token in ("robot", "captcha", "blocked", "validatecaptcha")
    )


def _load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data.get("products") or []
    out: dict[str, dict] = {}
    for item in products:
        asin = item.get("asin")
        if asin and not item.get("error"):
            out[asin] = item
    return out


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class BulkPipeline:
    """Long-running ASIN download pipeline with resume + adaptive pacing."""

    def __init__(
        self,
        marketplace: str | Marketplace = "nl",
        delay: float = 0.55,
        checkpoint_every: int = 25,
        log: Callable[[str], None] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        self.marketplace = (
            marketplace
            if isinstance(marketplace, Marketplace)
            else resolve_marketplace(marketplace)
        )
        self.checkpoint_every = max(1, checkpoint_every)
        self.stream = stream or sys.stderr
        self._log = log or (lambda msg: print(msg, file=self.stream, flush=True))
        self.scraper = DescriptionScraper(
            marketplace=self.marketplace,
            provider="soft",
            workers=1,
            delay=0.0,  # pacing owned by AdaptivePacer
            no_cache=True,
            warm_session=True,
        )
        self.pacer = AdaptivePacer(delay=delay)

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._log(f"[{ts}] {msg}")

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
        normalized = self.scraper.normalize_asins(asins)
        if max_items is not None:
            normalized = normalized[:max_items]

        done: dict[str, dict] = _load_checkpoint(checkpoint_path) if resume else {}
        if done:
            self.log(f"RESUME: loaded {len(done)} OK products from {checkpoint_path}")

        pending = [a for a in normalized if a not in done]
        stats = PipelineStats(total=len(normalized), delay=self.pacer.delay)
        # Count already-done toward totals for ETA clarity
        stats.ok = len(done)
        stats.attempted = len(done)
        for item in done.values():
            prov = item.get("provider") or "unknown"
            stats.by_provider[prov] = stats.by_provider.get(prov, 0) + 1
            stats.bytes_total += int(item.get("source_bytes") or 0)

        self.log(
            f"START marketplace={self.marketplace.domain} total={len(normalized)} "
            f"pending={len(pending)} delay={self.pacer.delay:.2f}s "
            f"checkpoint_every={self.checkpoint_every} no_cache=1 workers=1"
        )
        self.scraper._ensure_warm()
        self.log("Session warmed")

        failures: list[dict] = []
        since_checkpoint = 0

        for index, asin in enumerate(pending, start=1):
            self.pacer.wait()
            product = self.scraper.fetch_one(asin)
            captcha = _is_captcha_error(product)

            if product.error or not (
                product.title or product.feature_bullets or product.best_description
            ):
                # One hard retry after backoff for captcha/empty
                stats.retries += 1
                self.pacer.on_block()
                stats.delay = self.pacer.delay
                self.log(
                    f"RETRY {asin} captcha={captcha} err={product.error!r} "
                    f"new_delay={self.pacer.delay:.2f}s"
                )
                self.pacer.wait()
                product = self.scraper.fetch_one(asin)
                captcha = _is_captcha_error(product)

            if product.error or not (
                product.title or product.feature_bullets or product.best_description
            ):
                stats.note_failure(product, captcha=captcha)
                failures.append(product.to_dict())
                self.pacer.on_block()
                stats.delay = self.pacer.delay
                status = "FAIL"
            else:
                done[asin] = product.to_dict()
                stats.note_success(product)
                self.pacer.on_success()
                stats.delay = self.pacer.delay
                status = "OK"
                since_checkpoint += 1

            eta = stats.eta_seconds
            eta_s = "?" if eta is None else f"{eta/60:.1f}m"
            self.log(
                f"{status} [{stats.attempted}/{stats.total}] asin={asin} "
                f"provider={product.provider} bullets={len(product.feature_bullets)} "
                f"bytes={product.source_bytes or 0} "
                f"ok={stats.ok} fail={stats.failed} captcha={stats.captcha_hits} "
                f"rate={stats.rate:.2f}/s eta={eta_s} delay={self.pacer.delay:.2f}s"
            )

            if since_checkpoint >= self.checkpoint_every or index == len(pending):
                payload = {
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "marketplace": self.marketplace.domain,
                    "provider": "soft",
                    "stats": stats.to_dict(),
                    "total": len(done),
                    "products": list(done.values()),
                    "failures": failures[-50:],
                }
                _atomic_write_json(checkpoint_path, payload)
                since_checkpoint = 0
                self.log(
                    f"CHECKPOINT wrote {len(done)} products → {checkpoint_path} "
                    f"providers={stats.by_provider}"
                )

        # Final outputs
        products = [
            ProductDescription(
                asin=item["asin"],
                marketplace=item.get("marketplace") or self.marketplace.domain,
                url=item.get("url") or self.marketplace.product_url(item["asin"]),
                title=item.get("title"),
                brand=item.get("brand"),
                feature_bullets=item.get("feature_bullets") or [],
                description=item.get("description"),
                aplus_text=item.get("aplus_text"),
                overview=item.get("overview") or {},
                meta_description=item.get("meta_description"),
                provider=item.get("provider") or "soft",
                source_bytes=item.get("source_bytes"),
                error=item.get("error"),
            )
            for item in done.values()
        ]
        if output_path.suffix.lower() == ".csv":
            write_csv(output_path, products)
        else:
            write_json(
                output_path,
                products,
                marketplace=self.marketplace.domain,
                provider="soft",
            )
            # Enrich with stats
            final = json.loads(output_path.read_text(encoding="utf-8"))
            final["stats"] = stats.to_dict()
            final["failures_count"] = stats.failed
            _atomic_write_json(output_path, final)

        success_rate = (stats.ok / stats.total) if stats.total else 0
        self.log(
            f"DONE ok={stats.ok}/{stats.total} fail={stats.failed} "
            f"captcha_hits={stats.captcha_hits} success_rate={success_rate:.1%} "
            f"elapsed={stats.elapsed:.1f}s avg_rate={stats.rate:.2f}/s "
            f"providers={stats.by_provider} output={output_path}"
        )
        return stats
