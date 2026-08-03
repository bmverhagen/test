#!/usr/bin/env python3
"""Batch-test Helium Magnet demo (no auth) on N keywords.

No login/API key. Retries hard on HTTP 429.
Writes CSV + JSON summary with absolute vs relative seed outcomes.
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
    # de-dupe
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
    max_retries: int = 8,
    base_sleep: float = 8.0,
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
            wait = base_sleep * (attempt + 1)
            if "429" in msg:
                wait = max(wait, 45.0 + attempt * 15.0)
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
    ap.add_argument("--sleep", type=float, default=7.0, help="Delay between successes")
    ap.add_argument("-o", "--output-dir", type=Path, default=Path("batch_out"))
    args = ap.parse_args()

    terms = load_terms(args.file)[: args.limit]
    marketplace = resolve_marketplace(args.market)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"No-auth Helium Magnet batch: {len(terms)} terms, market={args.market} ({marketplace})",
        flush=True,
    )

    summaries: list[dict] = []
    raw_ok: list[dict] = []
    t0 = time.time()

    for i, kw in enumerate(terms, 1):
        result = fetch_with_retry(kw, marketplace)
        s = result["summary"]
        summaries.append(s)
        if result["payload"] is not None:
            raw_ok.append({"keyword": kw, "marketplace": marketplace, "payload": result["payload"]})

        tag = "ABS" if s.get("seed_absolute") is not None else ("REL" if s.get("ok") else "FAIL")
        print(
            f"[{i}/{len(terms)}] {tag} {kw}: "
            f"seed_abs={s.get('seed_absolute')} best={s.get('best_phrase')!r} "
            f"best_abs={s.get('best_phrase_absolute')} err={s.get('error')}",
            flush=True,
        )
        # pace even after success
        time.sleep(args.sleep)

    elapsed = time.time() - t0
    http_ok = sum(1 for s in summaries if s.get("ok"))
    abs_ok = sum(1 for s in summaries if s.get("seed_absolute") is not None)
    rel_only = sum(1 for s in summaries if s.get("ok") and s.get("seed_absolute") is None)
    fail = sum(1 for s in summaries if not s.get("ok"))

    report = {
        "market": args.market,
        "marketplace_id": marketplace,
        "n_terms": len(terms),
        "http_success": http_ok,
        "seed_absolute_count": abs_ok,
        "seed_relative_only_count": rel_only,
        "fail_count": fail,
        "elapsed_seconds": round(elapsed, 1),
        "auth": None,
        "endpoint": "https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search",
    }

    csv_path = args.output_dir / f"magnet_{args.market}_{len(terms)}.csv"
    json_path = args.output_dir / f"magnet_{args.market}_{len(terms)}_raw.json"
    report_path = args.output_dir / f"magnet_{args.market}_{len(terms)}_report.json"

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

    json_path.write_text(json.dumps(raw_ok, indent=2)[:5_000_000], encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== REPORT ===", flush=True)
    print(json.dumps(report, indent=2), flush=True)
    print(f"CSV  -> {csv_path}", flush=True)
    print(f"JSON -> {json_path}", flush=True)

    # Success criterion for this no-auth path: HTTP success on vast majority
    # Absolute seed volume is a subset (Helium demo quirk).
    if http_ok < int(0.8 * len(terms)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
