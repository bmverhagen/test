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

Region-localised harvesting (e.g. the Netherlands)
--------------------------------------------------
TikTok's tag feed is geo-aware: the videos returned depend on the
request's IP. To get NL-localised data, route through a Dutch
residential proxy and set the region:

    python3 tiktok_tags.py --region NL --proxy http://user:pass@nl-proxy:port

Without a proxy the pipeline still runs, but the feed is localised to
the exit IP of this machine (not NL). The `--region` flag sets the
browser locale + timezone and picks a region-appropriate default
watchlist.

Discovery
---------
Pass `--discover` to run one round of co-hashtag mining: after harvesting
the seed tags, the most frequent hair-relevant co-hashtags that are NOT
already in the watchlist are harvested too, so the list grows itself.

Usage:
    python3 tiktok_tags.py                          # default (intl hair)
    python3 tiktok_tags.py --region NL --discover
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

# international hair-care attribute vocabulary (matches the Amazon demo)
DEFAULT_TAGS = [
    "rosemaryoil", "bondrepair", "scalpserum", "hairoiling",
    "heatlesscurls", "leaveinconditioner",
]

# Dutch hair-care watchlist: NL-language terms + globally used English tags
# that Dutch beauty creators also use.
NL_HAIR_TAGS = [
    "haarverzorging", "haarroutine", "haartok", "haargroei",
    "rozemarijnolie", "haarolie", "krullen", "krullenverzorging",
    "hoofdhuid", "haaruitval", "haarmasker", "gladhaar",
    "beautytipsnl", "haartips", "rosemaryoil", "bondrepair",
    "scalpcare", "curlygirlmethode",
]

# region -> (locale, timezone, default watchlist)
REGION_CONFIG = {
    "NL": ("nl-NL", "Europe/Amsterdam", NL_HAIR_TAGS),
    "BE": ("nl-BE", "Europe/Brussels", NL_HAIR_TAGS),
    "US": ("en-US", "America/New_York", DEFAULT_TAGS),
    "GB": ("en-GB", "Europe/London", DEFAULT_TAGS),
    "DE": ("de-DE", "Europe/Berlin", DEFAULT_TAGS),
}

# lexicon to keep co-hashtag discovery on-topic (hair) and drop generic noise
HAIR_LEXICON = ("hair", "haar", "curl", "krul", "scalp", "hoofdhuid",
                "rosemary", "rozemarijn", "oil", "olie", "serum", "bond",
                "repair", "growth", "groei", "blowout", "frizz", "keratin",
                "shampoo", "conditioner", "balayage", "kapper", "coupe")
NOISE_TAGS = {"fyp", "foryou", "foryoupage", "viral", "tiktok", "trending",
              "fyp\u30b7", "viral\u30b7", "capcut", "duet", "greenscreen"}


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


def discover_candidates(results, seeds, limit):
    """Co-hashtag mining: hair-relevant tags not yet in the watchlist."""
    seen = {s.lower() for s in seeds}
    score = Counter()
    for r in results:
        for tag, cnt in r["topCoHashtags"]:
            t = tag.lower()
            if t in seen or t in NOISE_TAGS:
                continue
            if any(k in t for k in HAIR_LEXICON):
                score[t] += cnt
    return [t for t, _ in score.most_common(limit)]


async def run(tags, max_scrolls, region, proxy, discover):
    locale, tz, _ = REGION_CONFIG.get(
        region, ("en-US", "America/New_York", DEFAULT_TAGS))
    results = []
    async with async_playwright() as pw:
        launch_kwargs = {"headless": True}
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
        browser = await pw.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            user_agent=UA, locale=locale, timezone_id=tz,
            viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        async def harvest_list(taglist, phase):
            for i, tag in enumerate(taglist, 1):
                print(f"[{phase} {i}/{len(taglist)}] #{tag} ...",
                      file=sys.stderr)
                detail, videos = await harvest_tag(page, tag, max_scrolls)
                print(f"    totals: {fmt_int(detail.get('videoCount'))} "
                      f"videos / {fmt_int(detail.get('viewCount'))} views | "
                      f"harvested {len(videos)} videos", file=sys.stderr)
                results.append(summarize(tag, detail, videos))

        await harvest_list(tags, "seed")

        if discover:
            cand = discover_candidates(results, tags, limit=8)
            if cand:
                print(f"\n[discover] new hair candidates: {cand}\n",
                      file=sys.stderr)
                await harvest_list(cand, "disc")

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
    ranked = sorted(results, key=lambda r: -(r["totalViews"] or 0))
    for r in ranked:
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
    ap.add_argument("--tags", default=None,
                    help="comma-separated watchlist (overrides --region "
                         "default)")
    ap.add_argument("--region", default=None,
                    help="NL, BE, US, GB, DE — sets locale/timezone and "
                         "default watchlist")
    ap.add_argument("--proxy", default=None,
                    help="proxy server, e.g. http://user:pass@nl-host:port "
                         "(use a Dutch residential proxy for real NL data)")
    ap.add_argument("--discover", action="store_true",
                    help="run one co-hashtag mining round for new hair tags")
    ap.add_argument("--scrolls", type=int, default=8,
                    help="max scroll rounds per tag (~30 videos each)")
    ap.add_argument("--out", default="data/tiktok_tags.json")
    args = ap.parse_args()

    if args.tags:
        tags = [t.strip().lstrip("#") for t in args.tags.split(",")
                if t.strip()]
    elif args.region and args.region.upper() in REGION_CONFIG:
        tags = REGION_CONFIG[args.region.upper()][2]
    else:
        tags = DEFAULT_TAGS

    region = (args.region or "US").upper()
    if args.region and not args.proxy:
        print(f"[warn] --region {region} set but no --proxy: feed will be "
              f"localised to THIS machine's IP, not {region}. Plug in a "
              f"{region} residential proxy for true local data.\n",
              file=sys.stderr)

    results = asyncio.run(
        run(tags, args.scrolls, region, args.proxy, args.discover))
    report(results, args.out)


if __name__ == "__main__":
    main()
