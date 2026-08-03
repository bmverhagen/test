#!/usr/bin/env python3
"""No-auth search volumes via Keyword Volume Checker's public Supabase function.

Discovered by reversing https://keywordvolumechecker.com/ frontend JS:
  supabase.functions.invoke("keyword-volume", { body: { keywords, country } })

Uses the site's public anon key (no user login / signup). UI advertises ≤25
keywords per request; validated 1000/1000 in chunks of 25.

Example:
  python3 fetch_kvc_volume.py laptop shampoo --country us
  python3 fetch_kvc_volume.py -f terms_1000.txt -o batch_out/out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://lsbehnmosinxcmafumbo.supabase.co"
# Public anon key embedded in keywordvolumechecker.com frontend bundle.
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxzYmVobm1vc2lueGNtYWZ1bWJvIiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3NzgxODQ2NDcsImV4cCI6MjA5Mzc2MDY0N30."
    "AfEnA1y9CT_SGFwVgkDQvYjBHYMRU3rYMqxNN2bZWz4"
)
FUNCTION = "keyword-volume"


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


def invoke(keywords: list[str], country: str = "us", timeout: float = 120.0) -> list[dict]:
    url = f"{SUPABASE_URL}/functions/v1/{FUNCTION}"
    body = {"keywords": keywords, "country": country}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {ANON_KEY}",
            "apikey": ANON_KEY,
            "Origin": "https://keywordvolumechecker.com",
            "Referer": "https://keywordvolumechecker.com/",
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
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return list(payload.get("results") or [])


def fetch_volumes(
    keywords: list[str],
    *,
    country: str = "us",
    chunk_size: int = 25,
    chunk_pause: float = 0.4,
    retries: int = 4,
) -> list[dict]:
    rows: list[dict] = []
    for i in range(0, len(keywords), chunk_size):
        chunk = keywords[i : i + chunk_size]
        last_err: Exception | None = None
        results: list[dict] = []
        for attempt in range(retries):
            try:
                results = invoke(chunk, country=country)
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(2.5 * (attempt + 1))
        else:
            for kw in chunk:
                rows.append(
                    {
                        "keyword": kw,
                        "ok": False,
                        "volume": None,
                        "cpc": None,
                        "difficulty": None,
                        "intent": None,
                        "trend": None,
                        "error": str(last_err),
                    }
                )
            continue
        by = {str(r.get("keyword", "")).casefold(): r for r in results}
        for kw in chunk:
            r = by.get(kw.casefold())
            if not r:
                rows.append(
                    {
                        "keyword": kw,
                        "ok": False,
                        "volume": None,
                        "cpc": None,
                        "difficulty": None,
                        "intent": None,
                        "trend": None,
                        "error": "missing in response",
                    }
                )
                continue
            rows.append(
                {
                    "keyword": kw,
                    "ok": r.get("volume") is not None,
                    "volume": r.get("volume"),
                    "cpc": r.get("cpc"),
                    "difficulty": r.get("difficulty"),
                    "intent": r.get("intent"),
                    "trend": r.get("trend"),
                    "error": None,
                }
            )
        print(
            f"chunk {i//chunk_size+1}/{(len(keywords)+chunk_size-1)//chunk_size} "
            f"got={len(results)}",
            file=sys.stderr,
            flush=True,
        )
        if i + chunk_size < len(keywords) and chunk_pause > 0:
            time.sleep(chunk_pause)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keywords", nargs="*")
    ap.add_argument("-f", "--file", type=Path)
    ap.add_argument("--country", default="us")
    ap.add_argument("--chunk-size", type=int, default=25)
    ap.add_argument("--chunk-pause", type=float, default=0.4)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    keywords = list(args.keywords)
    if args.file:
        keywords.extend(load_terms(args.file))
    if not keywords:
        ap.error("keywords or -f required")

    rows = fetch_volumes(
        keywords,
        country=args.country,
        chunk_size=args.chunk_size,
        chunk_pause=args.chunk_pause,
    )
    ok = sum(1 for r in rows if r["ok"])
    print(f"ok={ok}/{len(rows)} country={args.country}", file=sys.stderr)
    for r in rows:
        print(f"{r['keyword']}\t{r['volume']}\t{r['difficulty']}\t{r['cpc']}\t{r['intent']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fields = ["keyword", "ok", "volume", "cpc", "difficulty", "intent", "trend", "error"]
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({**r, "error": r.get("error") or ""})
        print(f"wrote {args.out}", file=sys.stderr)
    if args.json_out:
        report = {
            "auth": "public supabase anon key from frontend (no user login)",
            "endpoint": f"POST {SUPABASE_URL}/functions/v1/{FUNCTION}",
            "discovered_from": "keywordvolumechecker.com assets JS invoke('keyword-volume')",
            "country": args.country,
            "n": len(rows),
            "ok": ok,
            "rows": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
