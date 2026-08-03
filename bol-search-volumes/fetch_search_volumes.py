#!/usr/bin/env python3
"""Fetch bol.com search volumes via Bolmate's public demo ingress.

Bolmate advertises free search trends without registration. The SPA auto-logins
with a public demo account when opened as:
  https://app.bolmate.nl/inloggen?demo=1&redirect=/zoekvolume

This script uses that same documented demo flow, then calls the multi-term
endpoint that the UI uses for /zoekvolume.

Endpoint:
  POST https://app.bolmate.nl/bolmate-core/v1/search-volumes/get

Official alternative (seller credentials required):
  GET https://api.bol.com/retailer/insights/search-terms
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://app.bolmate.nl/bolmate-core/v1"
DEMO_EMAIL = "demo@bolmate.nl"
DEMO_PASSWORD = "bolmate_demo"


class BolmateClient:
    def __init__(self) -> None:
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj)
        )
        self.account_id: str | None = None

    def _call(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://app.bolmate.nl",
            "Referer": "https://app.bolmate.nl/zoekvolume",
            "User-Agent": (
                "Mozilla/5.0 (compatible; bol-search-volumes/1.0; "
                "+https://app.bolmate.nl/inloggen?demo=1)"
            ),
        }
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(
            BASE + path, data=body, headers=headers, method=method
        )
        try:
            with self._opener.open(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc

    def login_demo(self) -> dict[str, Any]:
        fp = hashlib.sha256(b"bolmate-demo-fp").hexdigest()
        payload = {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "fp": fp}
        data = self._call("POST", "/auth/login", payload)
        if data.get("status") != "success":
            raise RuntimeError(f"Demo login failed: {data}")
        accounts = (data.get("user") or {}).get("accounts") or []
        if not accounts:
            raise RuntimeError("Demo login succeeded but no account_id was returned")
        self.account_id = accounts[0]["id"]
        return data

    def get_search_volumes(
        self,
        search_terms: list[str],
        period: str = "MONTH",
        number_of_periods: int = 12,
        with_comparison: bool = True,
    ) -> dict[str, Any]:
        if not self.account_id:
            raise RuntimeError("Not logged in; call login_demo() first")
        terms = [t.strip() for t in search_terms if t and t.strip()]
        if not terms:
            raise ValueError("No search terms provided")
        data = self._call(
            "POST",
            "/search-volumes/get",
            {
                "account_id": self.account_id,
                "search_terms": terms,
                "period": period,
                "number_of_periods": number_of_periods,
                "with_comparison": with_comparison,
            },
        )
        if data.get("status") != "success":
            raise RuntimeError(f"search-volumes/get failed: {data}")
        return data


def load_terms(path: Path | None, cli_terms: list[str]) -> list[str]:
    terms: list[str] = []
    if path:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            terms.append(line)
    terms.extend(cli_terms)
    # de-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def summarize_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("search_volume_data") or []:
        periods = item.get("periods") or []
        latest = periods[-1] if periods else {}
        totals = item.get("country_totals") or {}
        rows.append(
            {
                "search_term": item.get("search_term"),
                "latest_period": latest.get("period"),
                "latest_total": latest.get("total"),
                "latest_nl": latest.get("NL"),
                "latest_be": latest.get("BE"),
                "total_nl_periods": totals.get("NL"),
                "total_be_periods": totals.get("BE"),
            }
        )
    rows.sort(key=lambda r: r.get("latest_total") or 0, reverse=True)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch bol.com search volumes via Bolmate demo multi-term API"
    )
    parser.add_argument(
        "terms",
        nargs="*",
        help="Search terms (or pass --file)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Text file with one search term per line",
    )
    parser.add_argument(
        "--period",
        choices=["DAY", "WEEK", "MONTH"],
        default="MONTH",
        help="Aggregation period (default: MONTH)",
    )
    parser.add_argument(
        "--number-of-periods",
        type=int,
        default=12,
        help="How many periods to return (default: 12)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write full JSON response to this path",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Write summary CSV (latest period + country totals)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Print top N terms by latest total (default: 20)",
    )
    args = parser.parse_args(argv)

    terms = load_terms(args.file, args.terms)
    if not terms:
        parser.error("Provide search terms as args and/or --file")

    client = BolmateClient()
    client.login_demo()
    print(f"Logged in (demo). account_id={client.account_id}", file=sys.stderr)
    print(f"Fetching {len(terms)} terms ({args.period} x {args.number_of_periods})...", file=sys.stderr)

    payload = client.get_search_volumes(
        terms,
        period=args.period,
        number_of_periods=args.number_of_periods,
    )
    rows = summarize_rows(payload)
    print(f"Got {len(rows)} terms, {len(payload.get('related_terms') or [])} related terms", file=sys.stderr)

    for row in rows[: max(0, args.top)]:
        print(
            f"{row['search_term']:<30} "
            f"{row['latest_period']}: total={row['latest_total']} "
            f"(NL={row['latest_nl']}, BE={row['latest_be']})"
        )

    if args.output:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote JSON -> {args.output}", file=sys.stderr)
    if args.csv:
        write_csv(args.csv, rows)
        print(f"Wrote CSV  -> {args.csv}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
