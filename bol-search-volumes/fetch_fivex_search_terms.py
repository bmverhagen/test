#!/usr/bin/env python3
"""Fetch bol.com search terms via FiveX public proxy (single-term only).

Endpoint:
  GET https://www.fivex.com/api/bol-search-terms?query=<term>

Limits:
  - Free quota is server-enforced (IP), ~3/day without account → HTTP 429
  - Optional header X-FX-Bol-Preview: 1 is what the marketing UI uses for
    non-counting calls; it often still returns data but is rate/CF sensitive
  - No multi-term/bulk endpoint exists

For ~100 seeds prefer Bolmate demo (fetch_search_volumes.py) or bol Retailer API.
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
from typing import Any


ENDPOINT = "https://www.fivex.com/api/bol-search-terms"


def fetch_one(
    query: str,
    *,
    preview: bool = True,
    timeout: float = 30.0,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; bol-search-volumes/1.0)",
        "Referer": "https://www.fivex.com/nl/gratis-zoekwoorden-bol-tool/",
        "Origin": "https://www.fivex.com",
    }
    if preview:
        headers["X-FX-Bol-Preview"] = "1"

    url = f"{ENDPOINT}?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {query!r}: {body}") from exc


def fetch_many(
    terms: list[str],
    *,
    preview: bool = True,
    delay: float = 0.8,
    retries: int = 3,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for term in terms:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                payload = fetch_one(term, preview=preview)
                out.append(payload)
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001 - collect per-term errors
                last_err = exc
                wait = delay * (attempt + 2)
                msg = str(exc)
                if "429" in msg:
                    wait = max(wait, 60.0)
                print(f"retry {term!r} ({attempt+1}/{retries}): {exc}", file=sys.stderr)
                time.sleep(wait)
        if last_err is not None:
            out.append({"query": term, "error": str(last_err)})
        time.sleep(delay)
    return out


def summarize(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        if payload.get("error"):
            rows.append(
                {
                    "query": payload.get("query"),
                    "error": payload.get("error"),
                    "latest_period": None,
                    "latest_total": None,
                    "related_count": 0,
                    "top_related": None,
                }
            )
            continue
        periods = payload.get("periods") or []
        # Prefer last complete-looking month: skip trailing period if total is tiny vs previous
        latest = periods[-1] if periods else {}
        if len(periods) >= 2:
            prev = periods[-2]
            if (latest.get("total") or 0) < 0.15 * max(prev.get("total") or 1, 1):
                latest = prev
        items = payload.get("items") or []
        related = [i.get("term") for i in items[1:6] if i.get("term")]
        rows.append(
            {
                "query": payload.get("query"),
                "error": None,
                "latest_period": (
                    f"{latest.get('period', {}).get('year')}-"
                    f"{str(latest.get('period', {}).get('month')).zfill(2)}"
                    if latest.get("period")
                    else None
                ),
                "latest_total": latest.get("total"),
                "related_count": max(0, len(items) - 1),
                "top_related": ", ".join(related),
            }
        )
    return rows


def load_terms(path: Path | None, cli_terms: list[str]) -> list[str]:
    terms: list[str] = []
    if path:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    terms.extend(cli_terms)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        k = t.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FiveX bol-search-terms sequential fetcher")
    p.add_argument("terms", nargs="*")
    p.add_argument("-f", "--file", type=Path)
    p.add_argument("--no-preview", action="store_true", help="Do not send X-FX-Bol-Preview")
    p.add_argument("--delay", type=float, default=0.8, help="Delay between requests (seconds)")
    p.add_argument("-o", "--output", type=Path, help="Full JSON array output")
    p.add_argument("--csv", type=Path, help="Summary CSV output")
    args = p.parse_args(argv)

    terms = load_terms(args.file, args.terms)
    if not terms:
        p.error("Provide terms as args and/or --file")

    print(f"Fetching {len(terms)} terms via FiveX (preview={not args.no_preview})...", file=sys.stderr)
    payloads = fetch_many(terms, preview=not args.no_preview, delay=args.delay)
    rows = summarize(payloads)
    ok = sum(1 for r in rows if not r.get("error"))
    print(f"Done: {ok}/{len(rows)} ok", file=sys.stderr)

    for r in rows:
        if r.get("error"):
            print(f"{r['query']:<28} ERROR {r['error'][:80]}")
        else:
            print(
                f"{r['query']:<28} {r['latest_period']}: total={r['latest_total']} "
                f"related={r['related_count']}"
            )

    if args.output:
        args.output.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote JSON -> {args.output}", file=sys.stderr)
    if args.csv:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote CSV  -> {args.csv}", file=sys.stderr)
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
