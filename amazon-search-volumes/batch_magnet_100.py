#!/usr/bin/env python3
"""Batch-test Helium Magnet demo (NO AUTH) on N keywords.

Public endpoint — no login / API key.
Handles aggressive IP 429s with long cool-downs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from fetch_helium_magnet_demo import magnet_demo, resolve_marketplace, summarize


def load_terms(path: Path) -> list[str]:
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        k = t.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def fetch_with_retry(
    keyword: str,
    marketplace: str,
    *,
    max_retries: int = 6,
    cool_429: float = 180.0,
) -> dict:
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            payload = magnet_demo(keyword, marketplace)
            row = summarize(keyword, payload)
            row["attempts"] = attempt + 1
            row["error"] = None
            return {"summary": row, "payload": payload}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc)
            if "429" in msg:
                wait = cool_429 * (1 + attempt * 0.5)
            else:
                wait = 20.0 * (attempt + 1)
            print(
                f"retry {keyword!r} ({attempt+1}/{max_retries}) wait={wait:.0f}s: {exc}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)
    return {
        "summary": {
            "keyword": keyword,
            "ok": False,
            "error": str(last_err),
            "attempts": max_retries,
            "seed_is_best_phrase": None,
            "seed_absolute": None,
            "seed_relative": None,
            "best_phrase": None,
            "best_phrase_absolute": None,
        },
        "payload": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-f", "--file", type=Path, default=Path("terms_100.txt"))
    ap.add_argument("--market", default="US")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument(
        "--sleep",
        type=float,
        default=25.0,
        help="Seconds between successful calls (default 25)",
    )
    ap.add_argument("--cool-429", type=float, default=180.0)
    ap.add_argument("--initial-wait", type=float, default=0.0)
    ap.add_argument("-o", "--output-dir", type=Path, default=Path("batch_out"))
    args = ap.parse_args()

    terms = load_terms(args.file)[: args.limit]
    marketplace = resolve_marketplace(args.market)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.initial_wait > 0:
        print(f"Initial cooldown {args.initial_wait:.0f}s...", flush=True)
        time.sleep(args.initial_wait)

    print(
        f"NO-AUTH Helium Magnet batch: {len(terms)} terms, "
        f"market={args.market} ({marketplace}), sleep={args.sleep}s",
        flush=True,
    )

    summaries: list[dict] = []
    raw_ok: list[dict] = []
    consecutive_fail = 0
    t0 = time.time()

    for i, kw in enumerate(terms, 1):
        result = fetch_with_retry(kw, marketplace, cool_429=args.cool_429)
        s = result["summary"]
        summaries.append(s)
        if result["payload"] is not None:
            raw_ok.append(
                {"keyword": kw, "marketplace": marketplace, "payload": result["payload"]}
            )
            consecutive_fail = 0
        else:
            consecutive_fail += 1

        tag = (
            "ABS"
            if s.get("seed_absolute") is not None
            else ("REL" if s.get("ok") else "FAIL")
        )
        print(
            f"[{i}/{len(terms)}] {tag} {kw}: "
            f"seed_abs={s.get('seed_absolute')} best={s.get('best_phrase')!r} "
            f"best_abs={s.get('best_phrase_absolute')}",
            flush=True,
        )

        # Extra cool-down if we keep failing
        if consecutive_fail >= 3:
            extra = 300.0
            print(f"3 consecutive fails — extra cool-down {extra:.0f}s", flush=True)
            time.sleep(extra)
            consecutive_fail = 0
        else:
            time.sleep(args.sleep)

        # checkpoint every 10
        if i % 10 == 0:
            _write_outputs(args.output_dir, args.market, terms, summaries, raw_ok, t0)

    report = _write_outputs(args.output_dir, args.market, terms, summaries, raw_ok, t0)
    print("\n=== REPORT ===", flush=True)
    print(json.dumps(report, indent=2), flush=True)

    # Pass if >=80% HTTP ok (absolute seed is Helium quirk, counted separately)
    if report["http_success"] < int(0.8 * len(terms)):
        return 2
    return 0


def _write_outputs(output_dir, market, terms, summaries, raw_ok, t0):
    elapsed = time.time() - t0
    http_ok = sum(1 for s in summaries if s.get("ok"))
    abs_ok = sum(1 for s in summaries if s.get("seed_absolute") is not None)
    rel_only = sum(1 for s in summaries if s.get("ok") and s.get("seed_absolute") is None)
    fail = sum(1 for s in summaries if not s.get("ok"))
    n = len(summaries)
    report = {
        "auth": None,
        "endpoint": "https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search",
        "market": market,
        "n_requested": len(terms),
        "n_completed": n,
        "http_success": http_ok,
        "http_success_pct": round(100 * http_ok / n, 1) if n else 0,
        "seed_absolute_count": abs_ok,
        "seed_absolute_pct": round(100 * abs_ok / n, 1) if n else 0,
        "seed_relative_only_count": rel_only,
        "fail_count": fail,
        "elapsed_seconds": round(elapsed, 1),
    }

    csv_path = output_dir / f"magnet_{market}_{len(terms)}.csv"
    json_path = output_dir / f"magnet_{market}_{len(terms)}_raw.json"
    report_path = output_dir / f"magnet_{market}_{len(terms)}_report.json"

    fields = [
        "keyword",
        "ok",
        "seed_is_best_phrase",
        "seed_absolute",
        "seed_relative",
        "best_phrase",
        "best_phrase_absolute",
        "attempts",
        "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(summaries)

    # Keep raw payloads smaller for git
    slim = []
    for item in raw_ok:
        res = (item.get("payload") or {}).get("results") or {}
        bp = res.get("bestPhrase") or {}
        slim.append(
            {
                "keyword": item["keyword"],
                "best_phrase": bp.get("phrase"),
                "best_phrase_absolute": bp.get("impressionExact30"),
                "count": res.get("count"),
            }
        )
    json_path.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"checkpoint n={n} http_ok={http_ok} abs={abs_ok} fail={fail}", flush=True)
    return report


if __name__ == "__main__":
    raise SystemExit(main())
