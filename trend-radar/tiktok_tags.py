"""
TikTok keyword/tag harvester — deep data per attribute (no login).

Where tiktok_scrape.py harvests TikTok's own top-3 trend charts, this
script goes deep on an ARBITRARY keyword watchlist (e.g. the attribute
vocabulary of the Amazon engine: "rosemaryoil", "bondrepair", ...).

For each keyword it loads https://www.tiktok.com/tag/<keyword> in
headless Chromium and intercepts TikTok's own internal API calls:

  - api/challenge/detail    -> hashtag totals: videoCount, viewCount
  - api/challenge/item_list -> the video feed; auto-paginated by
                               scrolling (~160 videos/tag anonymously)

Per video we capture: caption, creation time, author, playCount, likes,
comments, shares, bookmarks, co-hashtags and music. Per keyword we
aggregate: totals, post velocity (posts/day last 7d vs prior 30d), mean
engagement rate, top co-hashtags and the top videos.

Usage:
    python3 tiktok_tags.py                          # default watchlist
    python3 tiktok_tags.py --tags rosemaryoil,bondrepair --scrolls 8
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# default watchlist = attribute vocabulary of the Amazon hair-care demo
DEFAULT_TAGS = [
    "rosemaryoil", "bondrepair", "scalpserum", "hairoiling",
    "heatlesscurls", "leaveinconditioner",
]


def fmt_int(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def parse_item(it):
    stats = it.get("statsV2") or it.get("stats") or {}
    author = it.get("author") or {}
    music = it.get("music") or {}
    tags = [t.get("hashtagName") for t in (it.get("textExtra") or [])
            if t.get("hashtagName")]
    return {
        "id": it.get("id"),
        "desc": (it.get("desc") or "")[:300],
        "createTime": int(it.get("createTime") or 0),
        "author": author.get("uniqueId"),
        "authorFollowers": (it.get("authorStats") or {}).get(
            "followerCount"),
        "plays": int(stats.get("playCount") or 0),
        "likes": int(stats.get("diggCount") or 0),
        "comments": int(stats.get("commentCount") or 0),
        "shares": int(stats.get("shareCount") or 0),
        "bookmarks": int(stats.get("collectCount") or 0),
        "hashtags": tags,
        "music": music.get("title"),
    }


async def harvest_tag(page, tag, max_scrolls):
    detail = {}
    videos = {}
    done = asyncio.Event()

    async def on_resp(r):
        try:
            if "api/challenge/detail" in r.url:
                j = await r.json()
                st = ((j.get("challengeInfo") or {}).get("statsV2")
                      or (j.get("challengeInfo") or {}).get("stats") or {})
                detail["videoCount"] = int(st.get("videoCount") or 0)
                detail["viewCount"] = int(st.get("viewCount") or 0)
            elif "api/challenge/item_list" in r.url:
                j = await r.json()
                for it in (j.get("itemList") or []):
                    v = parse_item(it)
                    if v["id"]:
                        videos[v["id"]] = v
                if not j.get("hasMore"):
                    done.set()
        except Exception:
            pass

    page.on("response", on_resp)
    try:
        await page.goto(f"https://www.tiktok.com/tag/{tag}",
                        wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(4_000)
        for _ in range(max_scrolls):
            if done.is_set():
                break
            await page.evaluate(
                "window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2_200)
    finally:
        page.remove_listener("response", on_resp)
    return detail, list(videos.values())


def summarize(tag, detail, videos):
    now = time.time()
    recent7 = [v for v in videos
               if v["createTime"] and now - v["createTime"] < 7 * 86400]
    prior30 = [v for v in videos
               if v["createTime"]
               and 7 * 86400 <= now - v["createTime"] < 37 * 86400]
    velocity_now = len(recent7) / 7
    velocity_prior = len(prior30) / 30 if prior30 else 0

    co = Counter()
    for v in videos:
        for h in v["hashtags"]:
            if h.lower() != tag.lower():
                co[h] += 1

    plays = sum(v["plays"] for v in videos)
    eng = sum(v["likes"] + v["comments"] + v["shares"] + v["bookmarks"]
              for v in videos)
    top = sorted(videos, key=lambda v: -v["plays"])[:5]

    return {
        "tag": tag,
        "totalVideos": detail.get("videoCount"),
        "totalViews": detail.get("viewCount"),
        "harvested": len(videos),
        "harvestPlays": plays,
        "engagementRate": round(eng / plays, 4) if plays else None,
        "postsPerDayLast7": round(velocity_now, 1),
        "postsPerDayPrior30": round(velocity_prior, 1),
        "velocityRatio": round(velocity_now / velocity_prior, 2)
        if velocity_prior else None,
        "topCoHashtags": co.most_common(12),
        "topVideos": top,
        "videos": videos,
    }


async def run(tags, max_scrolls):
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA, locale="en-US",
            viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        for i, tag in enumerate(tags, 1):
            print(f"[{i}/{len(tags)}] #{tag} ...", file=sys.stderr)
            detail, videos = await harvest_tag(page, tag, max_scrolls)
            print(f"    totals: {fmt_int(detail.get('videoCount'))} videos"
                  f" / {fmt_int(detail.get('viewCount'))} views | "
                  f"harvested {len(videos)} videos", file=sys.stderr)
            results.append(summarize(tag, detail, videos))
        await browser.close()
    return results


def report(results, out_path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print()
    print("=" * 100)
    print(f"  TIKTOK KEYWORD DEEP-DIVE — live, {now}")
    print("=" * 100)
    print(f"  {'#tag':<22} {'tag total':>18} {'harvest':>8} "
          f"{'eng.rate':>9} {'posts/d 7d':>11} {'vs prior':>9}")
    print("-" * 100)
    for r in results:
        total = (f"{fmt_int(r['totalVideos'])} vid / "
                 f"{fmt_int(r['totalViews'])}")
        ratio = (f"x{r['velocityRatio']}" if r['velocityRatio'] else "-")
        er = (f"{r['engagementRate'] * 100:.1f}%"
              if r['engagementRate'] is not None else "-")
        print(f"  #{r['tag']:<21} {total:>18} {r['harvested']:>8} "
              f"{er:>9} {r['postsPerDayLast7']:>11} {ratio:>9}")
    print("-" * 100)
    print("  posts/d 7d = harvested posts per day, last 7 days | "
          "vs prior = velocity vs the 30 days before that")

    for r in results:
        co = ", ".join(f"#{h}({c})" for h, c in r["topCoHashtags"][:8])
        print(f"\n  #{r['tag']} — top co-hashtags: {co}")
        for v in r["topVideos"][:3]:
            age_d = int((time.time() - v["createTime"]) / 86400) \
                if v["createTime"] else "?"
            print(f"      {fmt_int(v['plays']):>7} plays | "
                  f"{fmt_int(v['likes'])} likes | @{v['author']} | "
                  f"{age_d}d ago | {v['desc'][:70]}")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print(f"\n  full raw data (all videos, captions, co-hashtags): "
          f"{out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=",".join(DEFAULT_TAGS))
    ap.add_argument("--scrolls", type=int, default=8,
                    help="max scroll rounds per tag (~30 videos each)")
    ap.add_argument("--out", default="data/tiktok_tags.json")
    args = ap.parse_args()
    tags = [t.strip().lstrip("#") for t in args.tags.split(",")
            if t.strip()]
    results = asyncio.run(run(tags, args.scrolls))
    report(results, args.out)


if __name__ == "__main__":
    main()
