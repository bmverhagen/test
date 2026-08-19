"""
Daily TikTok trend radar — "know all trends every day".

Ties the two scrapers together into a daily pipeline with a time-series
memory, so you get not just a snapshot but MOVEMENT: what's new today,
what's accelerating, what's cooling.

Pipeline
--------
1. Run tiktok_scrape.py  -> trending hashtag CHART (all regions)
2. Run tiktok_tags.py    -> your keyword WATCHLIST (+ co-hashtag discovery)
3. Ingest both into a SQLite time-series (one row per key per day)
4. Diff today vs the previous snapshot:
     - NEW        : keys that appear today but not last run
     - ACCELERATING : momentum/velocity higher than last run (2nd derivative)
     - COOLING    : momentum/velocity lower than last run
5. Print a daily digest, newest & fastest-rising first.

The SQLite history is what makes real trend detection possible: momentum
is a 1st derivative, acceleration (change in momentum vs yesterday) is the
2nd derivative and the earliest reliable breakout signal.

Usage
-----
    # full daily run (scrape + ingest + digest):
    python3 daily_radar.py --regions US,GB,DE,NL --periods 7,30 \
        --tags-region NL --discover

    # re-analyse without scraping (uses last stored snapshots):
    python3 daily_radar.py --skip-scrape

    # backfill a snapshot from an existing json (for testing the diff):
    python3 daily_radar.py --skip-scrape --date 2026-08-15 \
        --hashtags-file data/tiktok_trends_all.json
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "trend_history.db")


def fmt_int(n):
    if n is None:
        return "-"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{sign}{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{sign}{n / 1e3:.0f}K"
    return f"{sign}{n}"


def fmt_delta(n):
    if not n:
        return ""
    return ("+" if n > 0 else "") + fmt_int(n) + " views"


def db_connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        snap_date TEXT, kind TEXT, key TEXT, region TEXT,
        posts INTEGER, views INTEGER, momentum REAL, status TEXT,
        velocity REAL, engagement REAL,
        PRIMARY KEY(snap_date, kind, key, region))""")
    return con


def ingest_hashtags(con, path, snap_date):
    if not os.path.exists(path):
        return 0
    rows = json.load(open(path, encoding="utf-8"))
    for r in rows:
        region = ",".join(r.get("regions") or []) or "-"
        con.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (snap_date, "hashtag", r["hashtag"], region,
                     r.get("posts"), r.get("views"), r.get("momentum"),
                     r.get("status"), None, None))
    con.commit()
    return len(rows)


def ingest_tags(con, path, snap_date, region_label):
    if not os.path.exists(path):
        return 0
    rows = json.load(open(path, encoding="utf-8"))
    for r in rows:
        con.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (snap_date, "tag", r["tag"], region_label,
                     r.get("totalVideos"), r.get("totalViews"), None, None,
                     r.get("velocityRatio"), r.get("engagementRate")))
    con.commit()
    return len(rows)


def run_scrapers(regions, periods, tags_region, discover, scrolls):
    scr = os.path.join(HERE, "tiktok_scrape.py")
    tag = os.path.join(HERE, "tiktok_tags.py")
    print("[1/2] scraping trending hashtag chart ...", file=sys.stderr)
    subprocess.run([sys.executable, scr, "--regions", regions,
                    "--periods", periods, "--out", "data/tiktok_trends.json"],
                   cwd=HERE, check=False)
    print("[2/2] scraping keyword watchlist ...", file=sys.stderr)
    cmd = [sys.executable, tag, "--scrolls", str(scrolls),
           "--out", "data/tiktok_tags.json"]
    if tags_region:
        cmd += ["--region", tags_region]
    if discover:
        cmd += ["--discover"]
    subprocess.run(cmd, cwd=HERE, check=False)


def _snapshot(con, kind, snap_date):
    q = ("SELECT key, posts, views, momentum, status, velocity, "
         "engagement, region FROM snapshots WHERE kind=? AND snap_date=?")
    out = {}
    for row in con.execute(q, (kind, snap_date)):
        out[row[0]] = dict(key=row[0], posts=row[1], views=row[2],
                           momentum=row[3], status=row[4], velocity=row[5],
                           engagement=row[6], region=row[7])
    return out


def analyze(con, kind):
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT snap_date FROM snapshots WHERE kind=? "
        "ORDER BY snap_date DESC", (kind,))]
    if not dates:
        return None
    today = dates[0]
    prev = dates[1] if len(dates) > 1 else None
    cur = _snapshot(con, kind, today)
    old = _snapshot(con, kind, prev) if prev else {}

    metric = "momentum" if kind == "hashtag" else "velocity"
    for k, v in cur.items():
        o = old.get(k)
        v["is_new"] = o is None
        cur_m = v.get(metric)
        old_m = o.get(metric) if o else None
        v["accel"] = (cur_m - old_m) if (cur_m is not None
                                         and old_m is not None) else None
        v["dviews"] = ((v["views"] or 0) - (o["views"] or 0)) if o else None
    return {"today": today, "prev": prev, "cur": cur}


def print_digest(kind, res):
    if not res:
        print(f"\n(no {kind} data yet)")
        return
    title = "TRENDING HASHTAG CHART" if kind == "hashtag" \
        else "KEYWORD WATCHLIST"
    rows = list(res["cur"].values())
    print("\n" + "=" * 92)
    print(f"  {title} — snapshot {res['today']}"
          + (f"  (vs {res['prev']})" if res["prev"] else "  (first snapshot)"))
    print("=" * 92)

    new = sorted([r for r in rows if r["is_new"]],
                 key=lambda r: -(r["views"] or 0))
    if new:
        print(f"\n  NEW since last run ({len(new)}):")
        for r in new[:15]:
            extra = (f"mom {r['momentum']:+.0f}" if kind == "hashtag"
                     else f"vel x{r['velocity']}" if r["velocity"] else "")
            print(f"    #{r['key']:<28} {fmt_int(r['views']):>7} views  "
                  f"{r['status'] or '':<10} {extra}  [{r['region']}]")

    accel = sorted([r for r in rows
                    if r["accel"] is not None and r["accel"] > 0],
                   key=lambda r: -r["accel"])
    if accel:
        print(f"\n  ACCELERATING (2nd derivative up) ({len(accel)}):")
        for r in accel[:15]:
            dv = fmt_delta(r["dviews"])
            print(f"    #{r['key']:<28} accel {r['accel']:+.1f}  "
                  f"{fmt_int(r['views']):>7} views  {dv}  [{r['region']}]")

    cooling = sorted([r for r in rows
                      if r["accel"] is not None and r["accel"] < 0],
                     key=lambda r: r["accel"])
    if cooling:
        print(f"\n  COOLING ({len(cooling)}):")
        for r in cooling[:10]:
            print(f"    #{r['key']:<28} accel {r['accel']:+.1f}  "
                  f"{fmt_int(r['views']):>7} views  [{r['region']}]")

    if not res["prev"]:
        print("\n  (only one snapshot so far — acceleration appears on the "
              "next run)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--regions", default="US,GB,DE,FR,ES,IT,CA,AU")
    ap.add_argument("--periods", default="7,30")
    ap.add_argument("--tags-region", default=None)
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--scrolls", type=int, default=6)
    ap.add_argument("--date", default=None,
                    help="override snapshot date (YYYY-MM-DD), for backfill")
    ap.add_argument("--hashtags-file", default="data/tiktok_trends.json")
    ap.add_argument("--tags-file", default="data/tiktok_tags.json")
    args = ap.parse_args()

    if not args.skip_scrape:
        run_scrapers(args.regions, args.periods, args.tags_region,
                     args.discover, args.scrolls)

    snap_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = db_connect()
    nh = ingest_hashtags(con, os.path.join(HERE, args.hashtags_file),
                         snap_date)
    nt = ingest_tags(con, os.path.join(HERE, args.tags_file), snap_date,
                     (args.tags_region or "intl").upper())
    print(f"ingested snapshot {snap_date}: {nh} hashtags, {nt} keywords",
          file=sys.stderr)

    print_digest("hashtag", analyze(con, "hashtag"))
    print_digest("tag", analyze(con, "tag"))
    con.close()


if __name__ == "__main__":
    main()
