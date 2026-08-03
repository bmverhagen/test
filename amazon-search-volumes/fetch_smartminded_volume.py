#!/usr/bin/env python3
"""No-auth bulk search volume via Smart-Minded's public DataForSEO proxy.

Used by the Smart-Minded "Amazon Keyword Tool" UI, but the live path is
Google Ads search volume (not Amazon ABA). No login / API key required.

Validated: 1000 keywords in one POST (~5s). High-frequency chunked calls work;
back-to-back full-1000 can briefly return empty results — retry with backoff.

Example:
  python3 fetch_smartminded_volume.py laptop kindle --location US --lang en
  python3 fetch_smartminded_volume.py -f terms_1000.txt -o batch_out/out.csv
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

ENDPOINT = "https://www.smart-minded.com/api/dataforseo"
DFS_PATH = "/v3/keywords_data/google_ads/search_volume/live"

# Common DataForSEO location codes
LOCATIONS = {
    "US": 2840,
    "NL": 2528,
    "DE": 2276,
    "UK": 2826,
    "GB": 2826,
}


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


def _post_once(
    keywords: list[str],
    *,
    location_code: int,
    language_code: str,
    timeout: float,
) -> list[dict]:
    # Frontend: fetch("/api/dataforseo", { body: JSON.stringify({ path, body }) })
    body = {
        "path": DFS_PATH,
        "body": [
            {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code,
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
        # Soft throttle sometimes returns Ok with tasks=None / empty.
        raise RuntimeError(f"empty tasks: {payload.get('status_message')}")
    task0 = tasks[0]
    if task0.get("status_code") not in (None, 20000):
        raise RuntimeError(
            f"DFS task status {task0.get('status_code')}: {task0.get('status_message')}"
        )
    results = (task0.get("result") or []) if isinstance(task0.get("result"), list) else []
    if not results and keywords:
        raise RuntimeError("empty result array (likely soft rate-limit)")
    return results


def fetch_chunk(
    keywords: list[str],
    *,
    location_code: int = 2840,
    language_code: str = "en",
    timeout: float = 180.0,
    retries: int = 5,
    retry_wait: float = 8.0,
) -> list[dict]:
    """Fetch one chunk with retries on empty/soft-throttle responses."""
    last_err: Exception | None = None
    results: list[dict] = []
    for attempt in range(retries):
        try:
            results = _post_once(
                keywords,
                location_code=location_code,
                language_code=language_code,
                timeout=timeout,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = retry_wait * (1 + attempt)
            print(
                f"retry {attempt+1}/{retries} wait={wait:.0f}s: {exc}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)
    else:
        raise RuntimeError(f"failed after {retries} retries: {last_err}")

    by_kw = {str(r.get("keyword", "")).casefold(): r for r in results if isinstance(r, dict)}
    rows: list[dict] = []
    for kw in keywords:
        r = by_kw.get(kw.casefold())
        if not r:
            rows.append(
                {
                    "keyword": kw,
                    "returned": False,
                    "ok": False,
                    "search_volume": None,
                    "cpc": None,
                    "competition": None,
                    "monthly_searches": {},
                    "error": "missing in response",
                }
            )
            continue
        monthly = {}
        for m in r.get("monthly_searches") or []:
            y, mo = m.get("year"), m.get("month")
            if y is not None and mo is not None:
                monthly[f"{int(y):04d}-{int(mo):02d}"] = m.get("search_volume")
        vol = r.get("search_volume")
        rows.append(
            {
                "keyword": kw,
                "returned": True,
                "ok": vol is not None,
                "search_volume": vol,
                "cpc": r.get("cpc"),
                "competition": r.get("competition"),
                "monthly_searches": monthly,
                "error": None if vol is not None else "null search_volume",
            }
        )
    return rows


def fetch_search_volumes(
    keywords: list[str],
    *,
    location_code: int = 2840,
    language_code: str = "en",
    timeout: float = 180.0,
    chunk_size: int = 1000,
    chunk_pause: float = 1.0,
    retries: int = 5,
) -> list[dict]:
    """Return one result dict per keyword. Chunks at DFS ~1000 KW/task limit."""
    if not keywords:
        return []
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    all_rows: list[dict] = []
    chunks = [keywords[i : i + chunk_size] for i in range(0, len(keywords), chunk_size)]
    for i, chunk in enumerate(chunks):
        print(
            f"chunk {i+1}/{len(chunks)} size={len(chunk)}",
            file=sys.stderr,
            flush=True,
        )
        all_rows.extend(
            fetch_chunk(
                chunk,
                location_code=location_code,
                language_code=language_code,
                timeout=timeout,
                retries=retries,
            )
        )
        if i + 1 < len(chunks) and chunk_pause > 0:
            time.sleep(chunk_pause)
    return all_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    month_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in sorted(row.get("monthly_searches") or {}):
            if k not in seen:
                seen.add(k)
                month_keys.append(k)
    fieldnames = [
        "keyword",
        "returned",
        "ok",
        "search_volume",
        "cpc",
        "competition",
        "error",
        *month_keys,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            out = {
                "keyword": row["keyword"],
                "returned": row.get("returned", True),
                "ok": row["ok"],
                "search_volume": row["search_volume"],
                "cpc": row["cpc"],
                "competition": row["competition"],
                "error": row["error"] or "",
            }
            for mk in month_keys:
                out[mk] = (row.get("monthly_searches") or {}).get(mk, "")
            w.writerow(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keywords", nargs="*", help="Keywords to look up")
    ap.add_argument("-f", "--file", type=Path, help="File with one keyword per line")
    ap.add_argument(
        "--location",
        default="US",
        help="Location code or name (US/NL/DE/UK or numeric DFS code)",
    )
    ap.add_argument("--lang", default="en", help="Language code (default en)")
    ap.add_argument("--chunk-size", type=int, default=1000, help="Max keywords per POST")
    ap.add_argument(
        "--chunk-pause",
        type=float,
        default=1.0,
        help="Seconds between chunks (default 1)",
    )
    ap.add_argument("--retries", type=int, default=5, help="Retries on empty/soft-limit")
    ap.add_argument("-o", "--out", type=Path, help="Write CSV here")
    ap.add_argument("--json-out", type=Path, help="Write full JSON report here")
    args = ap.parse_args()

    keywords = list(args.keywords)
    if args.file:
        keywords.extend(load_terms(args.file))
    if not keywords:
        ap.error("Provide keywords and/or -f terms file")

    loc_raw = str(args.location).strip()
    if loc_raw.isdigit():
        location_code = int(loc_raw)
    else:
        location_code = LOCATIONS.get(loc_raw.upper())
        if location_code is None:
            ap.error(f"Unknown location {loc_raw!r}; use US/NL/DE/UK or numeric code")

    rows = fetch_search_volumes(
        keywords,
        location_code=location_code,
        language_code=args.lang,
        chunk_size=args.chunk_size,
        chunk_pause=args.chunk_pause,
        retries=args.retries,
    )
    returned = sum(1 for r in rows if r.get("returned"))
    with_vol = sum(1 for r in rows if r["ok"])
    print(
        f"returned={returned}/{len(rows)} with_volume={with_vol}/{len(rows)} "
        f"location={location_code} lang={args.lang}",
        file=sys.stderr,
    )
    for r in rows:
        print(f"{r['keyword']}\t{r['search_volume']}\t{r['competition']}\t{r['cpc']}")

    if args.out:
        write_csv(args.out, rows)
        print(f"wrote {args.out}", file=sys.stderr)
    if args.json_out:
        report = {
            "auth": None,
            "endpoint": f"POST {ENDPOINT}",
            "path": DFS_PATH,
            "note": (
                "No login. Used by Smart-Minded Amazon Keyword Tool UI, "
                "but volumes are Google Ads (not Amazon ABA). "
                "Up to ~1000 keywords/POST; retry on empty soft-throttle."
            ),
            "location_code": location_code,
            "language_code": args.lang,
            "n": len(rows),
            "returned": returned,
            "with_volume": with_vol,
            "rows": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    return 0 if returned == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
