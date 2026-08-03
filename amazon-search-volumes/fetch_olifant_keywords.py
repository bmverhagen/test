#!/usr/bin/env python3
"""No-auth Amazon-branded keyword scores via Olifant Vercel tool.

GET /api/keywords — no login. searchVolume is relative ~0–100 (not absolute monthly).

Example:
  python3 fetch_olifant_keywords.py laptop --marketplace com
  python3 fetch_olifant_keywords.py -f terms_100.txt -o batch_out/out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://amazon-keyword-tool.vercel.app/api/keywords"


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


def fetch_one(keyword: str, marketplace: str = "com", timeout: float = 30.0) -> dict:
    qs = urllib.parse.urlencode({"input": keyword, "marketplace": marketplace})
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://amazon-keyword-tool.vercel.app/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    # Shape: {"ok": true, "rows": [{keyword, searchVolume, ...}], ...}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("rows") or payload.get("keywords") or []
    else:
        items = []
    seed = None
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            phrase = str(it.get("keyword") or it.get("phrase") or "").casefold()
            if phrase == keyword.casefold():
                seed = it
                break
        if seed is None and items and isinstance(items[0], dict):
            seed = items[0]
    if not isinstance(seed, dict):
        return {
            "keyword": keyword,
            "ok": False,
            "searchVolume": None,
            "competition": None,
            "ppcBidLow": None,
            "ppcBidHigh": None,
            "error": "empty response",
        }
    return {
        "keyword": keyword,
        "ok": seed.get("searchVolume") is not None,
        "searchVolume": seed.get("searchVolume"),
        "competition": seed.get("competition"),
        "ppcBidLow": seed.get("ppcBidLow"),
        "ppcBidHigh": seed.get("ppcBidHigh"),
        "error": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keywords", nargs="*")
    ap.add_argument("-f", "--file", type=Path)
    ap.add_argument("--marketplace", default="com", help="com|de|nl|co.uk|…")
    ap.add_argument("--sleep", type=float, default=0.15, help="Pause between calls")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    keywords = list(args.keywords)
    if args.file:
        keywords.extend(load_terms(args.file))
    if not keywords:
        ap.error("Provide keywords and/or -f terms file")

    rows: list[dict] = []
    for i, kw in enumerate(keywords):
        try:
            row = fetch_one(kw, marketplace=args.marketplace)
        except Exception as exc:  # noqa: BLE001
            row = {
                "keyword": kw,
                "ok": False,
                "searchVolume": None,
                "competition": None,
                "ppcBidLow": None,
                "ppcBidHigh": None,
                "error": str(exc),
            }
        rows.append(row)
        print(
            f"{row['keyword']}\t{row['searchVolume']}\t{row['competition']}\t{row.get('error') or ''}"
        )
        if i + 1 < len(keywords) and args.sleep > 0:
            time.sleep(args.sleep)

    ok = sum(1 for r in rows if r["ok"])
    print(f"ok={ok}/{len(rows)} marketplace={args.marketplace}", file=sys.stderr)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "keyword",
            "ok",
            "searchVolume",
            "competition",
            "ppcBidLow",
            "ppcBidHigh",
            "error",
        ]
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({**r, "error": r.get("error") or ""})
        print(f"wrote {args.out}", file=sys.stderr)

    if args.json_out:
        report = {
            "auth": None,
            "endpoint": f"GET {BASE}?input=...&marketplace={args.marketplace}",
            "note": (
                "No login. Amazon-branded free tool; searchVolume appears "
                "relative 0-100 (not absolute monthly)."
            ),
            "n": len(rows),
            "ok": ok,
            "fail": len(rows) - ok,
            "rows": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)

    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
