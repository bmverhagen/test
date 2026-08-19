"""
sound_snapshot.py — sound-trends met exacte tellers, puur TikTok.

Trends verspreiden zich vaak via een SOUND in plaats van (of eerder
dan) via een hashtag: creators gebruiken de audio van een viral video
zonder de tags over te nemen. De muziekpagina is anoniem scrapebaar en
`api/music/detail` geeft per sound een exacte cumulatieve teller:

    stats.videoCount = totaal aantal video's dat deze sound gebruikt

Net als bij tag_snapshot.py maakt dagelijks snapshotten daarvan een
zuivere groeimeting: Δposts/dag per sound, zonder feed-bias. De
video-feed van de sound (api/music/item_list) levert dezelfde
itemStruct als tag-feeds, dus taal/NL-share en engagement zijn er
ook per sound.

Sound-id's komen uit je eigen harvest: trending.py / tiktok_tags.py
slaan per video musicId + musicOriginal op. Dit script telt de meest
gebruikte sounds in de harvest en volgt de top N.

    python3 sound_snapshot.py --from-json data/trending_hair_nl_top200.json
    python3 sound_snapshot.py --ids 7543689509486676741,7213259234
    # cron, dagelijks na de harvest:
    30 8 * * * cd /pad/naar/trend-radar && python3 sound_snapshot.py \
        --from-json data/trending_hair_nl_top200.json >> logs/sounds.log

Kosten: ~2-3 s per sound (één page-load, geen scrollen).
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from tiktok_tags import UA, fmt_int

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "sound_history.db")


def db_connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS sound_snapshots (
        date TEXT NOT NULL,
        sound_id TEXT NOT NULL,
        title TEXT,
        author TEXT,
        original INTEGER,
        video_count INTEGER,
        PRIMARY KEY (date, sound_id))""")
    return con


def sounds_from_harvest(rows, top_n):
    """Tel sound-gebruik over alle geharveste video's; geef de top N
    (id, titel, #video's-in-harvest, tags-waar-gezien)."""
    usage = Counter()
    meta = {}
    for r in rows:
        tag = r.get("term") or r.get("tag")
        for v in ((r.get("localVideos") or []) + (r.get("videos") or [])
                  + (r.get("topVideos") or [])):
            mid = v.get("musicId")
            if not mid:
                continue
            usage[mid] += 1
            m = meta.setdefault(mid, {"title": v.get("music"),
                                      "original": v.get("musicOriginal"),
                                      "tags": set()})
            if tag:
                m["tags"].add(tag)
    out = []
    for mid, n in usage.most_common(top_n):
        m = meta[mid]
        out.append({"id": mid, "title": m["title"], "harvestUse": n,
                    "original": m["original"],
                    "tags": sorted(m["tags"])[:6]})
    return out


async def fetch_detail(page, sound_id):
    holder = {}
    done = asyncio.Event()

    async def on_resp(r):
        if "api/music/detail" in r.url:
            try:
                holder["json"] = await r.json()
                done.set()
            except Exception:
                pass

    page.on("response", on_resp)
    try:
        await page.goto(f"https://www.tiktok.com/music/x-{sound_id}",
                        wait_until="domcontentloaded", timeout=30000)
        try:
            await asyncio.wait_for(done.wait(), timeout=8)
        except asyncio.TimeoutError:
            pass
    finally:
        page.remove_listener("response", on_resp)
    mi = (holder.get("json") or {}).get("musicInfo") or {}
    music = mi.get("music") or {}
    stats = mi.get("stats") or {}
    if not music.get("id"):
        return None
    return {"id": music["id"], "title": music.get("title"),
            "author": music.get("authorName"),
            "original": bool(music.get("original")),
            "videoCount": stats.get("videoCount")}


async def run(sound_ids):
    out = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="nl-NL",
                                        timezone_id="Europe/Amsterdam")
        page = await ctx.new_page()
        for i, sid in enumerate(sound_ids, 1):
            d = await fetch_detail(page, sid)
            if d:
                out.append(d)
                print(f"  [{i}/{len(sound_ids)}] {d['title'][:40]!r}: "
                      f"{fmt_int(d['videoCount'] or 0)} video's",
                      file=sys.stderr)
            else:
                print(f"  [{i}/{len(sound_ids)}] {sid} — geen detail "
                      f"(verwijderd/regio-blok?)", file=sys.stderr)
        await browser.close()
    return out


def prev_snapshots(con, today):
    row = con.execute("SELECT MAX(date) FROM sound_snapshots WHERE date<?",
                      (today,)).fetchone()
    prev = row[0] if row and row[0] else None
    if not prev:
        return None, {}
    out = {}
    for r in con.execute("SELECT sound_id, video_count FROM sound_snapshots "
                         "WHERE date=?", (prev,)):
        out[r[0]] = r[1] or 0
    return prev, out


def days_between(d1, d2):
    a = datetime.strptime(d1, "%Y-%m-%d")
    b = datetime.strptime(d2, "%Y-%m-%d")
    return max((b - a).days, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json",
                    help="harvest-output (trending.py / tiktok_tags.py)")
    ap.add_argument("--ids", default="",
                    help="komma-gescheiden sound-id's")
    ap.add_argument("--top", type=int, default=25,
                    help="max sounds uit de harvest volgen (default 25)")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    seeds = []
    if args.from_json:
        path = os.path.join(HERE, args.from_json)
        if not os.path.exists(path):
            sys.exit(f"{args.from_json} niet gevonden — draai eerst een "
                     f"harvest.")
        rows = json.load(open(path, encoding="utf-8"))
        seeds = sounds_from_harvest(rows, args.top)
        if not seeds:
            print("[sounds] geen musicId's in deze harvest — draai de "
                  "harvest opnieuw met de nieuwste tiktok_tags.py",
                  file=sys.stderr)
    ids = [s["id"] for s in seeds]
    ids += [i.strip() for i in args.ids.split(",") if i.strip()]
    if not ids:
        sys.exit("geen sounds: geef --from-json en/of --ids")
    seed_by_id = {s["id"]: s for s in seeds}

    print(f"[sounds] {len(ids)} sounds peilen…", file=sys.stderr)
    details = asyncio.run(run(ids))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = db_connect(args.db)
    for d in details:
        con.execute("INSERT OR REPLACE INTO sound_snapshots VALUES "
                    "(?,?,?,?,?,?)",
                    (today, d["id"], d["title"], d["author"],
                     int(d["original"]), d["videoCount"]))
    con.commit()

    prev, old = prev_snapshots(con, today)
    print()
    print("=" * 92)
    print(f"  SOUND-SNAPSHOT {today} — {len(details)} sounds")
    print("=" * 92)
    header = (f"  {'sound':<38} {'video/s':>9} {'Δposts/dag':>11} "
              f"{'orig':>5}  gezien-bij")
    print(header)
    print("-" * 92)
    nd = days_between(prev, today) if prev else None

    def delta(d):
        if not prev or d["id"] not in old:
            return None
        return (d["videoCount"] - old[d["id"]]) / nd

    for d in sorted(details, key=lambda d: -(delta(d) or -1)):
        dd = delta(d)
        ds = f"+{dd:,.0f}" if dd is not None and dd >= 0 else (
            f"{dd:,.0f}" if dd is not None else "eerste dag")
        seed = seed_by_id.get(d["id"], {})
        tags = ",".join(seed.get("tags", [])[:3])
        title = (d["title"] or "?")[:36]
        print(f"  {title:<38} {fmt_int(d['videoCount'] or 0):>9} {ds:>11} "
              f"{'ja' if d['original'] else '':>5}  {tags}")
    print("-" * 92)
    print("  video/s = exact cumulatief aantal video's met deze sound "
          "(api/music/detail — geen sampling).\n  Δposts/dag wordt zichtbaar "
          "vanaf de tweede snapshot-dag. Een 'original' sound die hard "
          "stijgt\n  is vaak een trend-in-wording nog vóór er een duidelijke "
          "hashtag bestaat.")


if __name__ == "__main__":
    main()
