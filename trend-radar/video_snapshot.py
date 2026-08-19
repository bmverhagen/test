"""
video_snapshot.py — dagelijkse snapshots op VIDEO-niveau, puur TikTok.

Doel: "Nederlandse views per dag" meten zonder externe bronnen. De
play-teller van een Nederlandstalige video groeit vrijwel alleen door
NL/Vlaamse kijkers. Door per dag dezelfde video-id's opnieuw vast te
leggen wordt het dag-op-dag verschil in plays op NL-video's de beste
TikTok-native meting van Nederlandse kijkvraag per tag:

    NL-views/dag per tag = som van Δplays over de NL-video's van die tag

Dit vervangt de rol van externe kruisvalidatie: cumulatieve tellers
per video liegen niet (geen sampling, geen feed-bias) — je meet de
groei van bekende video's exact, plus hoeveel NIEUWE NL-video's er per
dag bijkomen.

    python3 video_snapshot.py --from-json data/trending_hair_nl_top200.json
    python3 video_snapshot.py --from-json data/tiktok_tags.json

Werkwijze:
1. Draai dagelijks een harvest (trending.py voor de hele lijst, of
   sneller: alleen je top-30) — die schrijft de JSON.
2. Draai daarna dit script: het slaat per (datum, tag, video-id) alle
   tellers op in data/video_history.db.
3. Vanaf dag 2 print de digest per tag: NL-Δplays/dag, nieuwe
   NL-video's, en de snelst groeiende individuele video's (viraliteit).

Cron (na de harvest):
    45 7 * * * cd /pad/naar/trend-radar && python3 video_snapshot.py \
        --from-json data/trending_hair_nl_top200.json >> logs/videos.log
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from tiktok_tags import fmt_int, is_dutch

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "video_history.db")


def db_connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS video_snapshots (
        date TEXT NOT NULL,
        tag TEXT NOT NULL,
        video_id TEXT NOT NULL,
        plays INTEGER, likes INTEGER, comments INTEGER,
        shares INTEGER, bookmarks INTEGER,
        lang TEXT, author TEXT, create_time INTEGER,
        PRIMARY KEY (date, tag, video_id))""")
    return con


def iter_tag_videos(rows):
    """Ondersteunt zowel trending.py-output (term/localVideos) als
    tiktok_tags.py-output (tag/videos)."""
    for r in rows:
        tag = r.get("term") or r.get("tag")
        vids = r.get("localVideos") or r.get("videos") or []
        if tag and vids:
            yield tag, vids


def ingest(con, rows, today):
    n = 0
    for tag, vids in iter_tag_videos(rows):
        for v in vids:
            if not v.get("id"):
                continue
            con.execute(
                "INSERT OR REPLACE INTO video_snapshots VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (today, tag, v["id"], v.get("plays"), v.get("likes"),
                 v.get("comments"), v.get("shares"), v.get("bookmarks"),
                 v.get("lang"), v.get("author"), v.get("createTime")))
            n += 1
    con.commit()
    return n


def prev_date(con, today):
    row = con.execute(
        "SELECT MAX(date) FROM video_snapshots WHERE date<?",
        (today,)).fetchone()
    return row[0] if row and row[0] else None


def snapshot(con, date):
    """{(tag, video_id): rij} voor één datum."""
    out = {}
    for row in con.execute(
            "SELECT tag, video_id, plays, likes, bookmarks, lang, author, "
            "create_time FROM video_snapshots WHERE date=?", (date,)):
        out[(row[0], row[1])] = {"plays": row[2] or 0, "likes": row[3] or 0,
                                 "bookmarks": row[4] or 0, "lang": row[5],
                                 "author": row[6], "createTime": row[7]}
    return out


def days_between(d1, d2):
    a = datetime.strptime(d1, "%Y-%m-%d")
    b = datetime.strptime(d2, "%Y-%m-%d")
    return max((b - a).days, 1)


def digest(con, today):
    prev = prev_date(con, today)
    n_dates = con.execute("SELECT COUNT(DISTINCT date) FROM "
                          "video_snapshots").fetchone()[0]
    print()
    print("=" * 92)
    print(f"  VIDEO-SNAPSHOT {today} — {n_dates} snapshot-dag(en) in "
          f"{os.path.basename(DB)}")
    print("=" * 92)
    if not prev:
        print("  Eerste snapshot: nog geen vergelijking mogelijk. Draai "
              "na de volgende harvest opnieuw\n  voor echte NL-Δplays "
              "per dag.")
        return
    nd = days_between(prev, today)
    cur, old = snapshot(con, today), snapshot(con, prev)

    per_tag = {}
    gainers = []
    for (tag, vid), c in cur.items():
        nl = c["lang"] == "nl" or is_dutch(
            {"lang": c["lang"], "desc": ""})
        t = per_tag.setdefault(tag, {"dplays": 0, "nl_dplays": 0,
                                     "new_nl": 0, "matched": 0})
        o = old.get((tag, vid))
        if o:
            d = (c["plays"] - o["plays"]) / nd
            t["matched"] += 1
            t["dplays"] += d
            if nl:
                t["nl_dplays"] += d
                if d > 0:
                    gainers.append((d, tag, vid, c))
        elif nl:
            t["new_nl"] += 1

    ranked = sorted(per_tag.items(), key=lambda kv: -kv[1]["nl_dplays"])
    print(f"  {'#tag':<26} {'NL-views/dag':>13} {'alle Δplays/d':>14} "
          f"{'nieuwe NL-vid':>14} {'gevolgd':>8}")
    print("-" * 92)
    for tag, t in ranked[:30]:
        print(f"  #{tag:<25} {fmt_int(int(t['nl_dplays'])):>13} "
              f"{fmt_int(int(t['dplays'])):>14} {t['new_nl']:>14} "
              f"{t['matched']:>8}")
    print("-" * 92)
    print("  NL-views/dag = som van Δplays over Nederlandstalige video's "
          "die op beide dagen gezien zijn —\n  exacte tellers, geen "
          "sampling. nieuwe NL-vid = NL-video's die er sinds de vorige "
          "snapshot bij kwamen.")

    if gainers:
        print("\n  SNELST GROEIENDE NL-VIDEO'S (viraliteit):")
        for d, tag, vid, c in sorted(gainers, reverse=True)[:8]:
            print(f"    +{fmt_int(int(d))}/dag | #{tag} | @{c['author']} "
                  f"| nu {fmt_int(c['plays'])} plays")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", required=True,
                    help="output van trending.py of tiktok_tags.py")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    path = os.path.join(HERE, args.from_json)
    if not os.path.exists(path):
        sys.exit(f"{args.from_json} niet gevonden — draai eerst de "
                 f"harvest (trending.py / tiktok_tags.py).")
    rows = json.load(open(path, encoding="utf-8"))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = db_connect(args.db)
    n = ingest(con, rows, today)
    print(f"[ingest] {n} video-snapshots opgeslagen voor {today}",
          file=sys.stderr)
    digest(con, today)


if __name__ == "__main__":
    main()
