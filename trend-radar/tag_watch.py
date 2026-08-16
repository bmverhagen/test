"""
tag_watch.py — vang (vrijwel) ALLE nieuwe video's van een watchlist
door de tag-feeds frequent te pollen.

De tag-feed kent geen "sorteer op datum", maar heeft wél een vers-slot:
nieuwe video's verschijnen er binnen uren in. Door elk uur (cron) de
eerste feed-pagina's op te halen en te dedupliceren op video-id bouw je
een near-complete stroom van nieuwe video's op — met per video het
moment waarop jij hem voor het eerst zag (first_seen).

Waarom dit werkt voor NL-schaal tags: een tag als #haarverzorging doet
~1-20 nieuwe posts per dag, terwijl één poll al ~60 video's ziet
(2 scroll-rondes). De dekking is dus ruim — en meetbaar: de vertraging
tussen createTime en first_seen vertelt je per video hoe snel je hem
opving. Blijft die vertraging onder je poll-interval, dan mis je niets.

Wat dit oplevert (naast complete vangst):
  - ECHTE posts/dag per tag = aantal nieuwe id's per dag (geen
    venster-schatting uit één sample meer)
  - first_seen + createTime = opkomstsnelheid per video
  - elke poll ververst ook de tellers van al bekende video's van
    vandaag (voedt dezelfde video_history.db als video_snapshot.py)

Gebruik:
    python3 tag_watch.py --region NL                  # NL-watchlist, 1 pass
    python3 tag_watch.py --tags krullen,haarolie
    # cron, elk uur:
    0 * * * * cd /pad/naar/trend-radar && python3 tag_watch.py --region NL >> logs/watch.log
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from tiktok_tags import (UA, REGION_CONFIG, DEFAULT_TAGS, fmt_int,
                         harvest_tag, is_dutch)
from video_snapshot import db_connect as video_db_connect

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "video_history.db")


def ensure_first_seen(con):
    con.execute("""CREATE TABLE IF NOT EXISTS video_first_seen (
        video_id TEXT PRIMARY KEY,
        tag TEXT,
        first_seen INTEGER,
        create_time INTEGER,
        author TEXT,
        lang TEXT,
        desc TEXT)""")
    return con


async def run(tags, scrolls, locale, tz):
    out = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale=locale,
                                        timezone_id=tz,
                                        viewport={"width": 1440,
                                                  "height": 900})
        page = await ctx.new_page()
        for i, tag in enumerate(tags, 1):
            detail, videos = await harvest_tag(page, tag, scrolls)
            out[tag] = videos
            print(f"[{i}/{len(tags)}] #{tag}: {len(videos)} video's in "
                  f"feed", file=sys.stderr)
        await browser.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=None)
    ap.add_argument("--region", default=None,
                    help="NL/BE/US/GB/DE -> locale + default watchlist")
    ap.add_argument("--scrolls", type=int, default=2,
                    help="scroll-rondes per tag (~30 video's per ronde)")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    region = (args.region or "US").upper()
    locale, tz, default_tags = REGION_CONFIG.get(
        region, ("en-US", "America/New_York", DEFAULT_TAGS))
    if args.tags:
        tags = [t.strip().lstrip("#") for t in args.tags.split(",")
                if t.strip()]
    else:
        tags = default_tags

    now_ts = int(time.time())
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    harvest = asyncio.run(run(tags, args.scrolls, locale, tz))

    con = ensure_first_seen(video_db_connect(args.db))
    new_per_tag = {}
    lags = []
    for tag, videos in harvest.items():
        for v in videos:
            if not v.get("id"):
                continue
            # tellers van vandaag verversen (zelfde tabel als
            # video_snapshot.py -> dag-deltas blijven werken)
            con.execute(
                "INSERT OR REPLACE INTO video_snapshots VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (today, tag, v["id"], v.get("plays"), v.get("likes"),
                 v.get("comments"), v.get("shares"), v.get("bookmarks"),
                 v.get("lang"), v.get("author"), v.get("createTime")))
            cur = con.execute(
                "INSERT OR IGNORE INTO video_first_seen VALUES "
                "(?,?,?,?,?,?,?)",
                (v["id"], tag, now_ts, v.get("createTime"),
                 v.get("author"), v.get("lang"),
                 (v.get("desc") or "")[:200]))
            if cur.rowcount:
                new_per_tag.setdefault(tag, []).append(v)
                if v.get("createTime"):
                    lags.append(now_ts - v["createTime"])
    con.commit()

    total_seen = con.execute(
        "SELECT COUNT(*) FROM video_first_seen").fetchone()[0]
    print()
    print("=" * 88)
    print(f"  TAG-WATCH {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
          f"— {sum(len(v) for v in new_per_tag.values())} nieuwe video's "
          f"deze poll | {total_seen} totaal gevolgd")
    print("=" * 88)
    for tag in sorted(new_per_tag, key=lambda t: -len(new_per_tag[t])):
        vids = new_per_tag[tag]
        nl = sum(1 for v in vids if is_dutch(v))
        fresh = [v for v in vids if v.get("createTime")
                 and now_ts - v["createTime"] < 86400]
        print(f"  #{tag:<24} +{len(vids):>3} nieuw ({nl} NL, "
              f"{len(fresh)} <24u oud)")
        for v in sorted(fresh, key=lambda v: -(v.get("plays") or 0))[:2]:
            age_h = (now_ts - v["createTime"]) / 3600
            print(f"      {fmt_int(v.get('plays')):>7} plays | "
                  f"@{v.get('author')} | {age_h:.1f}u oud | "
                  f"{(v.get('desc') or '')[:55]}")
    if lags:
        fresh_lags = sorted(l for l in lags if l < 7 * 86400)
        if fresh_lags:
            med = fresh_lags[len(fresh_lags) // 2] / 3600
            print(f"\n  opvang-vertraging (nieuwe video's <7d oud, "
                  f"mediaan): {med:.1f} uur na publicatie")
    print("\n  Elke poll: nieuwe id's -> first_seen; bekende id's -> "
          "tellers ververst. Echte posts/dag per tag =\n  nieuwe id's "
          "per dag; blijft de opvang-vertraging onder je poll-interval, "
          "dan mis je niets.")


if __name__ == "__main__":
    main()
