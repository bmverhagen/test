#!/usr/bin/env python3
"""Fetch Amazon keyword volume via Helium 10 Magnet public demo.

POST https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search
form: keyword + marketplace

Demo quirk:
  - results.bestPhrase.impressionExact30 is ABSOLUTE monthly volume
  - results.searchResults[*].impressionExact30 is usually a relative 0-100 score
  - Seed absolute is available only when normalize(bestPhrase.phrase) == normalize(keyword)

Rate limit: aggressive HTTP 429 per IP — use --sleep.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

URL = "https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search"

MARKETPLACES = {
    "US": "ATVPDKIKX0DER",
    "COM": "ATVPDKIKX0DER",
    "NL": "A1805IZSGTT6HS",
    "DE": "A1PA6795UKMFR9",
    "UK": "A1F83G8C2ARO7P",
    "FR": "A13V1IB3VIYZZH",
    "IT": "APJ6JRA9NG5V4",
    "ES": "A1RKKUPIHCS9HS",
    "CA": "A2EUQ1WTGCTBG2",
}


def normalize_phrase(s: str) -> str:
    return " ".join(s.casefold().split())


def resolve_marketplace(market: str) -> str:
    key = market.strip().upper()
    if key in MARKETPLACES:
        return MARKETPLACES[key]
    # allow raw marketplace id
    if market.startswith("A") and len(market) >= 10:
        return market
    raise SystemExit(
        f"Unknown market {market!r}. Use one of: {', '.join(sorted(MARKETPLACES))}"
    )


def magnet_demo(keyword: str, marketplace: str, timeout: float = 45.0) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {"keyword": keyword, "marketplace": marketplace}
    ).encode()
    req = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.helium10.com",
            "Referer": "https://www.helium10.com/tools/free/amazon-keyword-tool/",
            "User-Agent": (
                "Mozilla/5.0 (compatible; amazon-search-volumes/1.0; "
                "+https://www.helium10.com/tools/free/amazon-keyword-tool/)"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def summarize(keyword: str, payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results") or {}
    if results.get("status") != "success":
        return {
            "keyword": keyword,
            "ok": False,
            "status": results.get("status"),
            "raw_status": results,
        }

    best = results.get("bestPhrase") or {}
    seed_norm = normalize_phrase(keyword)
    best_phrase = best.get("phrase") or ""
    match = normalize_phrase(best_phrase) == seed_norm

    seed_row = None
    for row in (results.get("searchResults") or {}).values():
        if normalize_phrase(str(row.get("phrase") or "")) == seed_norm:
            seed_row = row
            break

    out: dict[str, Any] = {
        "keyword": keyword,
        "ok": True,
        "seed_is_best_phrase": match,
        "best_phrase": best_phrase,
        "best_phrase_absolute": best.get("impressionExact30"),
        "seed_relative": None if seed_row is None else seed_row.get("impressionExact30"),
        "seed_absolute": best.get("impressionExact30") if match else None,
        "results_number_best": best.get("resultsNumber"),
        "count": results.get("count"),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keywords", nargs="+", help="Seed keyword(s)")
    ap.add_argument(
        "--market",
        default="US",
        help="US|NL|DE|UK|… or raw marketplace id (default US)",
    )
    ap.add_argument("--sleep", type=float, default=4.0, help="Seconds between calls")
    ap.add_argument("-o", "--output", type=Path, help="Write full raw JSON list here")
    ap.add_argument("--csv", type=Path, help="Write summary CSV here")
    args = ap.parse_args()

    marketplace = resolve_marketplace(args.market)
    summaries: list[dict[str, Any]] = []
    raw_all: list[dict[str, Any]] = []

    for i, kw in enumerate(args.keywords):
        if i:
            time.sleep(args.sleep)
        try:
            payload = magnet_demo(kw, marketplace)
        except RuntimeError as exc:
            print(f"FAIL\t{kw}\t{exc}", file=sys.stderr)
            summaries.append({"keyword": kw, "ok": False, "error": str(exc)})
            continue
        raw_all.append({"keyword": kw, "marketplace": marketplace, "payload": payload})
        row = summarize(kw, payload)
        summaries.append(row)
        if row.get("seed_absolute") is not None:
            print(
                f"ABS\t{kw}\t{row['seed_absolute']}\t"
                f"(bestPhrase={row['best_phrase']!r})"
            )
        else:
            print(
                f"REL\t{kw}\tseed_rel={row.get('seed_relative')}\t"
                f"best={row.get('best_phrase')!r}\t"
                f"best_abs={row.get('best_phrase_absolute')}"
            )

    if args.output:
        args.output.write_text(json.dumps(raw_all, indent=2), encoding="utf-8")
    if args.csv:
        import csv

        fields = [
            "keyword",
            "ok",
            "seed_is_best_phrase",
            "seed_absolute",
            "seed_relative",
            "best_phrase",
            "best_phrase_absolute",
        ]
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in summaries:
                w.writerow(row)

    # exit 0 even if some seeds are relative-only (still successful HTTP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
