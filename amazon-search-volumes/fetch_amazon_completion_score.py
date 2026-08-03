#!/usr/bin/env python3
"""No-auth Amazon-native relative score via public completion API.

Not absolute monthly volume. Score ~0–100 based on how early/often the
phrase appears in Amazon autocomplete suggestions across prefixes.

High frequency: completion.amazon.* accepts rapid calls (50/50 smoke OK).

Example:
  python3 fetch_amazon_completion_score.py laptop shampoo --market US
  python3 fetch_amazon_completion_score.py -f terms_100.txt -o out.csv
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

MARKET_HOST = {
    "US": ("completion.amazon.com", "ATVPDKIKX0DER"),
    "NL": ("completion.amazon.nl", "A1805IZSGTT6HS"),
    "DE": ("completion.amazon.de", "A1PA6795UKMFR9"),
    "UK": ("completion.amazon.co.uk", "A1F83G8C2ARO7P"),
}


def load_terms(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        k = t.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def suggest(prefix: str, host: str, mid: str, timeout: float = 15.0) -> list[str]:
    qs = urllib.parse.urlencode(
        {
            "prefix": prefix,
            "alias": "aps",
            "mid": mid,
            "site-variant": "desktop",
        }
    )
    url = f"https://{host}/api/2017/suggestions?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    ideas = []
    for s in payload.get("suggestions") or []:
        if isinstance(s, dict):
            val = s.get("value") or s.get("keyword")
            if val:
                ideas.append(str(val))
    return ideas


def score_keyword(keyword: str, host: str, mid: str, sleep: float = 0.05) -> dict:
    """Relative 0–100 score from prefix presence/position."""
    kw = keyword.strip()
    if not kw:
        return {"keyword": keyword, "ok": False, "score": None, "error": "empty"}
    # prefixes: first char, growing, full phrase
    prefixes: list[str] = []
    for i in range(1, len(kw) + 1):
        prefixes.append(kw[:i])
    # also whole words cumulative
    parts = kw.split()
    acc = []
    for p in parts:
        acc.append(p)
        phrase = " ".join(acc)
        if phrase not in prefixes:
            prefixes.append(phrase)

    total = 0.0
    weight_sum = 0.0
    hits = 0
    for idx, prefix in enumerate(prefixes):
        weight = 1.0 + (len(prefixes) - idx) * 0.15  # earlier prefixes weigh more
        try:
            ideas = suggest(prefix, host, mid)
        except Exception as exc:  # noqa: BLE001
            return {
                "keyword": kw,
                "ok": False,
                "score": None,
                "error": str(exc),
                "prefixes": len(prefixes),
                "hits": hits,
            }
        weight_sum += weight
        exact = kw.casefold()
        pos = None
        for j, idea in enumerate(ideas):
            if idea.casefold() == exact or exact in idea.casefold():
                pos = j
                hits += 1
                break
        if pos is not None:
            # top position ~1.0, 10th ~0.1
            total += weight * max(0.0, 1.0 - pos / 10.0)
        if sleep:
            time.sleep(sleep)

    score = round(100.0 * (total / weight_sum), 2) if weight_sum else 0.0
    return {
        "keyword": kw,
        "ok": True,
        "score": score,
        "error": None,
        "prefixes": len(prefixes),
        "hits": hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keywords", nargs="*")
    ap.add_argument("-f", "--file", type=Path)
    ap.add_argument("--market", default="US", choices=sorted(MARKET_HOST))
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    kws = list(args.keywords)
    if args.file:
        kws.extend(load_terms(args.file))
    if not kws:
        ap.error("keywords or -f required")

    host, mid = MARKET_HOST[args.market]
    rows = []
    for kw in kws:
        row = score_keyword(kw, host, mid, sleep=args.sleep)
        rows.append(row)
        print(f"{row['keyword']}\t{row['score']}\t{row.get('hits')}\t{row.get('error') or ''}")

    ok = sum(1 for r in rows if r["ok"])
    print(f"ok={ok}/{len(rows)} market={args.market}", file=sys.stderr)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fields = ["keyword", "ok", "score", "hits", "prefixes", "error"]
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({**r, "error": r.get("error") or ""})
    if args.json_out:
        report = {
            "auth": None,
            "endpoint": f"GET https://{host}/api/2017/suggestions",
            "note": "Amazon-native relative 0-100 estimate; NOT absolute monthly volume.",
            "market": args.market,
            "n": len(rows),
            "ok": ok,
            "rows": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
