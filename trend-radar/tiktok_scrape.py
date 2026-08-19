"""
Pure TikTok trend scrape — proof of concept (no login, no API key).

How it works
------------
TikTok's Creative Center publishes trending hashtags at
https://ads.tiktok.com/creative/creativeCenter/trends/hashtag.
The JSON API behind it requires JS-signed headers ("no permission" for
plain HTTP), and plain curl gets an empty app shell. But when a real
browser loads the page, the server embeds a react-query "dehydrated
state" blob in the HTML containing, per hashtag:

  - hashtagName, rankIndex, industryIDs
  - publishCnt (posts), vv (video views)
  - popularityCurve: a DAILY normalized popularity time series
  - topCreators driving the trend

Anonymously each page exposes the top 3 hashtags, but the page accepts
`region` (27 countries) and `period` (7/30/120 days) URL parameters, so
we harvest region x period combinations with one headless Chromium
instance and aggregate. The daily curves let us compute momentum and
classify each trend as EXPLODING / RISING / PEAKING / FADING — the
"hype" side of the hype-to-revenue funnel.

Usage
-----
    python3 tiktok_scrape.py                       # default 8 regions
    python3 tiktok_scrape.py --regions US,DE,FR --periods 7,30
    python3 tiktok_scrape.py --all-regions
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

from playwright.async_api import async_playwright

BASE = "https://ads.tiktok.com/creative/creativeCenter/trends/hashtag"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

ALL_REGIONS = ["US", "FR", "DE", "IT", "ES", "GB", "AR", "AU", "BR", "CA",
               "CO", "EG", "ID", "IL", "JP", "KR", "MY", "MX", "PH", "SA",
               "SG", "ZA", "TW", "TH", "TR", "AE", "VN"]
DEFAULT_REGIONS = ["US", "GB", "DE", "FR", "ES", "IT", "CA", "AU"]


def fmt_int(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def extract_records(html):
    """Pull hashtag records out of the SSR dehydrated-state script."""
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        s = m.group(1).strip()
        if '"hashtagName"' not in s:
            continue
        # the script body is (or contains) one JSON object
        start = s.find("{")
        try:
            state = json.loads(s[start:])
        except json.JSONDecodeError:
            continue
        found = []

        def walk(node):
            if isinstance(node, dict):
                if "hashtagName" in node and "popularityCurve" in node:
                    found.append(node)
                else:
                    for v in node.values():
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(state)
        if found:
            return found
    return []


def extract_dom_industries(body_text):
    """Map hashtag -> industry label from the rendered rows.

    Rendered row pattern: "<rank>\n#<name>\n[Industry label]\n<posts>\nPosts..."
    """
    mapping = {}
    lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("#") and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not re.match(r"^[\d.,]+[KMB]?$", nxt) and "Posts" not in nxt:
                mapping[ln.lstrip("#")] = nxt
    return mapping


def curve_metrics(curve):
    """Return (momentum, status) from the daily popularity curve (0-100)."""
    vals = [p["value"] for p in curve if isinstance(p.get("value"),
                                                    (int, float))]
    if len(vals) < 6:
        return 0.0, "?"
    recent = sum(vals[-3:]) / 3
    prior = sum(vals[-10:-3]) / max(1, len(vals[-10:-3]))
    early = sum(vals[:3]) / 3
    momentum = recent - prior
    peak = max(vals)
    if recent >= peak * 0.9 and momentum > 5:
        status = "EXPLODING"
    elif momentum > 2:
        status = "RISING"
    elif recent >= peak * 0.8:
        status = "PEAKING"
    elif recent < prior - 5 or recent < early:
        status = "FADING"
    else:
        status = "STABLE"
    return momentum, status


async def harvest(regions, periods):
    per_tag = {}   # name -> merged record
    industry_labels = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="en-US")
        page = await ctx.new_page()
        holder = {}

        async def on_resp(r):
            if r.url.startswith(BASE):
                try:
                    holder["html"] = await r.text()
                except Exception:
                    pass

        page.on("response", on_resp)

        combos = [(r, p) for r in regions for p in periods]
        for idx, (region, period) in enumerate(combos, 1):
            holder.clear()
            url = f"{BASE}?region={region}&period={period}"
            try:
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=45_000)
            except Exception as e:
                print(f"  [{idx}/{len(combos)}] {region}/{period}d "
                      f"FAILED ({type(e).__name__})", file=sys.stderr)
                continue
            for _ in range(20):
                if "html" in holder:
                    break
                await page.wait_for_timeout(300)
            recs = extract_records(holder.get("html", ""))
            # give the client a moment to render rows w/ industry labels
            await page.wait_for_timeout(1_200)
            try:
                body = await page.evaluate("document.body.innerText")
                industry_labels.update(extract_dom_industries(body))
            except Exception:
                pass
            names = [r.get("hashtagName") for r in recs]
            print(f"  [{idx}/{len(combos)}] {region}/{period}d -> {names}",
                  file=sys.stderr)
            for r in recs:
                name = r.get("hashtagName")
                if not name:
                    continue
                entry = per_tag.setdefault(name, {
                    "hashtag": name, "regions": [], "periods": [],
                    "posts": 0, "views": 0, "curve": [],
                    "industryIDs": r.get("industryIDs") or [],
                    "topCreators": [
                        c.get("handleName")
                        for c in (r.get("topCreators") or [])[:3]],
                })
                entry["regions"].append(region)
                entry["periods"].append(period)
                entry["posts"] = max(entry["posts"],
                                     int(r.get("publishCnt") or 0))
                entry["views"] = max(entry["views"], int(r.get("vv") or 0))
                if len(r.get("popularityCurve") or []) > len(entry["curve"]):
                    entry["curve"] = r["popularityCurve"]

        await browser.close()

    return per_tag, industry_labels


def report(per_tag, industry_labels, out_path):
    rows = []
    for name, e in per_tag.items():
        momentum, status = curve_metrics(e["curve"])
        rows.append({
            **e,
            "industry": industry_labels.get(name, ""),
            "momentum": round(momentum, 1),
            "status": status,
            "regions": sorted(set(e["regions"])),
        })
    rows.sort(key=lambda r: (-r["momentum"], -r["views"]))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print()
    print("=" * 96)
    print(f"  TIKTOK TREND SCRAPE — live, {now}")
    print(f"  source: Creative Center SSR payload | "
          f"{len(rows)} unique trending hashtags")
    print("=" * 96)
    print(f"  {'hashtag':<26} {'industry':<22} {'posts':>7} {'views':>7} "
          f"{'mom.':>6}  {'status':<10} regions")
    print("-" * 96)
    for r in rows:
        regions = ",".join(r["regions"][:6])
        if len(r["regions"]) > 6:
            regions += f" +{len(r['regions']) - 6}"
        print(f"  #{r['hashtag']:<25} {r['industry'][:22]:<22} "
              f"{fmt_int(r['posts']):>7} {fmt_int(r['views']):>7} "
              f"{r['momentum']:>+6.1f}  {r['status']:<10} {regions}")
    print("-" * 96)
    print("  momentum = popularity(last 3 days) - popularity(prior week), "
          "scale 0-100")
    print("  EXPLODING = at peak and still accelerating | FADING = past "
          "peak, cooling off")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"\n  raw data (incl. daily curves + top creators): {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default=",".join(DEFAULT_REGIONS))
    ap.add_argument("--all-regions", action="store_true")
    ap.add_argument("--periods", default="30")
    ap.add_argument("--out", default="data/tiktok_trends.json")
    args = ap.parse_args()

    regions = ALL_REGIONS if args.all_regions else [
        r.strip().upper() for r in args.regions.split(",") if r.strip()]
    periods = [int(p) for p in args.periods.split(",")]

    print(f"Harvesting {len(regions)} region(s) x {periods} day period(s) "
          f"...", file=sys.stderr)
    per_tag, labels = asyncio.run(harvest(regions, periods))
    report(per_tag, labels, args.out)


if __name__ == "__main__":
    main()
