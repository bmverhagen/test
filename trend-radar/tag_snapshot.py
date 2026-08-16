"""
tag_snapshot.py — goedkope dagelijkse snapshots op TAG-niveau.

TikTok publiceert per tag precies twee cumulatieve tellers via
api/challenge/detail: videoCount en viewCount. Die worden bij het laden
van de tag-pagina meteen meegestuurd — geen video-harvest of scrollen
nodig (~5 sec per tag i.p.v. ~15).

Cumulatieve tellers zijn het zuiverste groeisignaal dat er is: het
dag-op-dag verschil is de EXACTE groei van de hele tag (geen
feed-sampling, geen recency-bias, geen kleine noemers). Dit is de
definitieve oplossing voor het "x55/x11"-probleem.

    python3 tag_snapshot.py --tags krullen,kapper,stijltang
    python3 tag_snapshot.py --from-json data/trending_hair_nl_top200.json
    python3 tag_snapshot.py --from-json data/trending_hair_nl_top200.json --limit 200

Elke run schrijft (datum, tag, videoCount, viewCount) naar SQLite
(data/tag_history.db). Vanaf dag 2 print de digest per tag:
    Δviews/dag   — echte views erbij per dag
    Δposts/dag   — echte nieuwe video's per dag
    versnelling  — Δviews vandaag vs vorige Δviews (vanaf 3 snapshots)

Draai dagelijks (cron):
    15 7 * * * cd /pad/naar/trend-radar && python3 tag_snapshot.py \
        --from-json data/trending_hair_nl_top200.json >> logs/tags.log
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from tiktok_tags import UA, fmt_int

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "tag_history.db")


def db_connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS tag_snapshots (
        date TEXT NOT NULL,
        tag TEXT NOT NULL,
        video_count INTEGER,
        view_count INTEGER,
        PRIMARY KEY (date, tag))""")
    return con


async def fetch_detail(page, tag, timeout_s=12):
    """Laad de tag-pagina en vang alléén challenge/detail af (geen
    scroll, vroege exit zodra de tellers binnen zijn)."""
    holder = {}

    async def on_resp(r):
        if "api/challenge/detail" in r.url:
            try:
                j = await r.json()
                st = ((j.get("challengeInfo") or {}).get("statsV2")
                      or (j.get("challengeInfo") or {}).get("stats") or {})
                holder["videoCount"] = int(st.get("videoCount") or 0)
                holder["viewCount"] = int(st.get("viewCount") or 0)
            except Exception:
                pass

    page.on("response", on_resp)
    try:
        await page.goto(f"https://www.tiktok.com/tag/{tag}",
                        wait_until="domcontentloaded", timeout=30_000)
        for _ in range(timeout_s * 2):
            if holder:
                break
            await page.wait_for_timeout(500)
    finally:
        page.remove_listener("response", on_resp)
    return holder or None


async def run(tags):
    out = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="nl-NL",
                                        timezone_id="Europe/Amsterdam")
        page = await ctx.new_page()
        for i, tag in enumerate(tags, 1):
            d = await fetch_detail(page, tag)
            if d:
                out[tag] = d
                print(f"[{i}/{len(tags)}] #{tag}: "
                      f"{fmt_int(d['videoCount'])} vid / "
                      f"{fmt_int(d['viewCount'])} views", file=sys.stderr)
            else:
                print(f"[{i}/{len(tags)}] #{tag}: geen detail (skip)",
                      file=sys.stderr)
        await browser.close()
    return out


def prev_snapshots(con, tag, today):
    """Laatste 2 eerdere snapshots (datum, video_count, view_count)."""
    return con.execute(
        "SELECT date, video_count, view_count FROM tag_snapshots "
        "WHERE tag=? AND date<? ORDER BY date DESC LIMIT 2",
        (tag, today)).fetchall()


def days_between(d1, d2):
    a = datetime.strptime(d1, "%Y-%m-%d")
    b = datetime.strptime(d2, "%Y-%m-%d")
    return max((b - a).days, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=None)
    ap.add_argument("--from-json", default=None,
                    help="trending_*.json van trending.py (neemt de terms)")
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    if args.tags:
        tags = [t.strip().lstrip("#") for t in args.tags.split(",")
                if t.strip()]
    elif args.from_json:
        rows = json.load(open(os.path.join(HERE, args.from_json),
                              encoding="utf-8"))
        tags = [r["term"] for r in rows]
    else:
        sys.exit("geef --tags of --from-json")
    tags = tags[:args.limit]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    details = asyncio.run(run(tags))

    con = db_connect(args.db)
    deltas = []
    for tag, d in details.items():
        con.execute(
            "INSERT OR REPLACE INTO tag_snapshots VALUES (?,?,?,?)",
            (today, tag, d["videoCount"], d["viewCount"]))
        prev = prev_snapshots(con, tag, today)
        if prev:
            pd, pv, pw = prev[0]
            nd = days_between(pd, today)
            dviews = (d["viewCount"] - pw) / nd
            dposts = (d["videoCount"] - pv) / nd
            accel = None
            if len(prev) == 2:
                p2d, p2v, p2w = prev[1]
                nd2 = days_between(p2d, pd)
                prev_dviews = (pw - p2w) / nd2
                accel = (dviews / prev_dviews
                         if prev_dviews and prev_dviews > 0 else None)
            deltas.append((tag, dviews, dposts, accel,
                           d["viewCount"], d["videoCount"]))
    con.commit()

    n_dates = con.execute(
        "SELECT COUNT(DISTINCT date) FROM tag_snapshots").fetchone()[0]
    print()
    print("=" * 90)
    print(f"  TAG-SNAPSHOT {today} — {len(details)} tags opgeslagen "
          f"({n_dates} snapshot-dag(en) in {os.path.basename(args.db)})")
    print("=" * 90)
    if not deltas:
        print("  Eerste snapshot: nog geen vergelijking mogelijk. "
              "Draai morgen weer voor echte Δviews/dag.")
        return
    print(f"  {'#tag':<26} {'Δviews/dag':>12} {'Δposts/dag':>11} "
          f"{'versnelling':>12} {'totaal views':>13}")
    print("-" * 90)
    for tag, dv, dp, acc, tv, _tp in sorted(deltas, key=lambda x: -x[1]):
        a = f"x{acc:.2f}" if acc else "-"
        print(f"  #{tag:<25} {fmt_int(int(dv)):>12} {dp:>11.1f} "
              f"{a:>12} {fmt_int(tv):>13}")
    print("-" * 90)
    print("  Δ = exacte groei van de cumulatieve tag-tellers — geen "
          "sampling, geen feed-bias.")


if __name__ == "__main__":
    main()
