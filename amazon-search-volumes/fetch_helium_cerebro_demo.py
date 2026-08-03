#!/usr/bin/env python3
"""Helium 10 Cerebro public demo (reverse ASIN → keywords).

POST https://members.helium10.com/api/v1/cerebro/product/cerebro-demo-search
form: asin + marketplace

Companion to Magnet demo (seed keyword). Same IP rate limit (429).
Use when you have a competitor ASIN and want related keyword rows.
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

URL = "https://members.helium10.com/api/v1/cerebro/product/cerebro-demo-search"

MARKETPLACES = {
    "US": "ATVPDKIKX0DER",
    "NL": "A1805IZSGTT6HS",
    "DE": "A1PA6795UKMFR9",
    "UK": "A1F83G8C2ARO7P",
    "FR": "A13V1IB3VIYZZH",
}


def resolve_marketplace(market: str) -> str:
    key = market.strip().upper()
    if key in MARKETPLACES:
        return MARKETPLACES[key]
    if market.startswith("A") and len(market) >= 10:
        return market
    raise SystemExit(f"Unknown market {market!r}")


def cerebro_demo(asin: str, marketplace: str, timeout: float = 60.0) -> dict[str, Any]:
    body = urllib.parse.urlencode({"asin": asin, "marketplace": marketplace}).encode()
    req = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.helium10.com",
            "Referer": "https://www.helium10.com/tools/keyword-research/cerebro/",
            "User-Agent": "Mozilla/5.0 (compatible; amazon-search-volumes/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asins", nargs="+")
    ap.add_argument("--market", default="US")
    ap.add_argument("--sleep", type=float, default=6.0)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    marketplace = resolve_marketplace(args.market)
    all_raw = []
    for i, asin in enumerate(args.asins):
        if i:
            time.sleep(args.sleep)
        try:
            payload = cerebro_demo(asin, marketplace)
        except RuntimeError as exc:
            print(f"FAIL\t{asin}\t{exc}", file=sys.stderr)
            continue
        res = payload.get("results") or {}
        sr = res.get("searchResults") or {}
        rows = list(sr.values()) if isinstance(sr, dict) else []
        abs_n = 0
        for row in rows:
            try:
                if float(row.get("impressionExact30") or 0) > 100:
                    abs_n += 1
            except (TypeError, ValueError):
                pass
        print(f"OK\t{asin}\trows={len(rows)}\tabsolute_gt_100={abs_n}\tstatus={res.get('status')}")
        all_raw.append({"asin": asin, "marketplace": marketplace, "payload": payload})
    if args.output:
        args.output.write_text(json.dumps(all_raw, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
