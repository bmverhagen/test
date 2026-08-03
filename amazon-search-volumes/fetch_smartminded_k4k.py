#!/usr/bin/env python3
"""No-auth keyword expansion via Smart-Minded DataForSEO proxy.

Path: /v3/keywords_data/google_ads/keywords_for_keywords/live
One seed → hundreds/thousands of related keywords with absolute Google Ads
search_volume (not Amazon ABA). No login.

Example:
  python3 fetch_smartminded_k4k.py "yoga mat" --limit 200 -o out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://www.smart-minded.com/api/dataforseo"
DFS_PATH = "/v3/keywords_data/google_ads/keywords_for_keywords/live"
LOCATIONS = {"US": 2840, "NL": 2528, "DE": 2276, "UK": 2826, "GB": 2826}


def fetch_k4k(
    seed: str,
    *,
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 100,
    timeout: float = 120.0,
) -> list[dict]:
    body = {
        "path": DFS_PATH,
        "body": [
            {
                "keywords": [seed],
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "sort_by": "search_volume",
            }
        ],
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.smart-minded.com",
            "Referer": "https://www.smart-minded.com/amazon-keyword-tool/",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    if payload.get("status_code") not in (None, 20000):
        raise RuntimeError(
            f"DFS status {payload.get('status_code')}: {payload.get('status_message')}"
        )
    tasks = payload.get("tasks") or []
    if not tasks:
        raise RuntimeError("empty tasks")
    task0 = tasks[0]
    if task0.get("status_code") not in (None, 20000):
        raise RuntimeError(
            f"task {task0.get('status_code')}: {task0.get('status_message')}"
        )

    rows: list[dict] = []
    for r in task0.get("result") or []:
        if not isinstance(r, dict):
            continue
        # Some payloads nest under items; live k4k often returns flat keyword rows.
        candidates = r.get("items") if isinstance(r.get("items"), list) else [r]
        for it in candidates:
            if not isinstance(it, dict) or not it.get("keyword"):
                continue
            monthly = {}
            for m in it.get("monthly_searches") or []:
                y, mo = m.get("year"), m.get("month")
                if y is not None and mo is not None:
                    monthly[f"{int(y):04d}-{int(mo):02d}"] = m.get("search_volume")
            rows.append(
                {
                    "seed": seed,
                    "keyword": it.get("keyword"),
                    "search_volume": it.get("search_volume"),
                    "cpc": it.get("cpc"),
                    "competition": it.get("competition"),
                    "competition_index": it.get("competition_index"),
                    "monthly_searches": monthly,
                }
            )
    # de-dupe by keyword keeping highest volume
    best: dict[str, dict] = {}
    for row in rows:
        k = str(row["keyword"]).casefold()
        prev = best.get(k)
        if prev is None or (row.get("search_volume") or 0) > (prev.get("search_volume") or 0):
            best[k] = row
    out = sorted(best.values(), key=lambda r: r.get("search_volume") or 0, reverse=True)
    return out[:limit] if limit else out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seed", help="Seed keyword")
    ap.add_argument("--location", default="US")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    loc = args.location.strip()
    location_code = int(loc) if loc.isdigit() else LOCATIONS[loc.upper()]
    rows = fetch_k4k(
        args.seed,
        location_code=location_code,
        language_code=args.lang,
        limit=args.limit,
    )
    print(f"seed={args.seed!r} n={len(rows)} location={location_code}", file=sys.stderr)
    for r in rows[:30]:
        print(f"{r['keyword']}\t{r['search_volume']}\t{r['competition']}\t{r['cpc']}")
    if len(rows) > 30:
        print(f"... {len(rows)-30} more", file=sys.stderr)

    if args.out:
        fields = ["seed", "keyword", "search_volume", "cpc", "competition", "competition_index"]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {args.out}", file=sys.stderr)
    if args.json_out:
        report = {
            "auth": None,
            "endpoint": f"POST {ENDPOINT}",
            "path": DFS_PATH,
            "note": "No login. Google Ads related keywords + absolute volumes.",
            "seed": args.seed,
            "n": len(rows),
            "rows": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
