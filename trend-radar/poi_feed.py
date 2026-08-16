"""
poi_feed.py — video's per LOCATIE (plaats-pagina's), puur NL-gebonden.

TikTok-video's kunnen een locatie-tag (POI) dragen: van "Amsterdam"
tot één specifieke kapperszaak. De plaats-pagina is anoniem
scrapebaar en levert twee dingen:

    api/poi/detail     — naam, adres, aantal video's op deze locatie
    api/poi/item_list  — de video-feed van die locatie (zelfde
                         itemStruct als tag-feeds, ~30 per pagina)

Dit is de meest expliciete NL-bron die er is: een video getagd op een
Nederlandse locatie is per definitie NL-gebonden, ongeacht de taal —
dus óók Engelstalige video's van/voor Nederlanders.

POI-id's komen uit je eigen harvest: parse_item legt per video
poiId/poiName/poiAddress vast. Dit script kan ook direct met id's
overweg:

    python3 poi_feed.py --from-json data/trending_hair_nl_top200.json
    python3 poi_feed.py --ids 22535865202914970   # Amsterdam
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter

from playwright.async_api import async_playwright

from tiktok_tags import UA, fmt_int, parse_item

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "poi_feed.json")


def pois_from_harvest(rows, top_n):
    usage = Counter()
    meta = {}
    for r in rows:
        for v in ((r.get("localVideos") or []) + (r.get("videos") or [])
                  + (r.get("topVideos") or [])):
            pid = v.get("poiId")
            if not pid:
                continue
            usage[pid] += 1
            meta.setdefault(pid, {"name": v.get("poiName"),
                                  "address": v.get("poiAddress")})
    return [{"id": pid, **meta[pid], "harvestUse": n}
            for pid, n in usage.most_common(top_n)]


async def harvest_poi(page, poi_id, scrolls):
    detail = {}
    videos = {}

    async def on_resp(r):
        try:
            if "api/poi/detail" in r.url:
                j = await r.json()
                detail.update((j.get("poiInfo") or {}))
            elif "api/poi/item_list" in r.url:
                j = await r.json()
                for it in j.get("itemList") or []:
                    v = parse_item(it)
                    if v.get("id"):
                        videos[v["id"]] = v
        except Exception:
            pass

    page.on("response", on_resp)
    try:
        await page.goto(f"https://www.tiktok.com/place/x-{poi_id}",
                        wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(4000)
        for _ in range(scrolls):
            await page.mouse.wheel(0, 2500)
            await page.wait_for_timeout(1600)
    finally:
        page.remove_listener("response", on_resp)
    poi = detail.get("poi") or {}
    stats = detail.get("stats") or detail.get("statistics") or {}
    return {"id": poi_id, "name": poi.get("name"),
            "address": poi.get("address"), "city": poi.get("city"),
            "videoCount": stats.get("videoCount"),
            "viewCount": stats.get("viewCount")}, list(videos.values())


async def run(poi_ids, scrolls):
    out = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="nl-NL",
                                        timezone_id="Europe/Amsterdam")
        page = await ctx.new_page()
        for i, pid in enumerate(poi_ids, 1):
            detail, videos = await harvest_poi(page, pid, scrolls)
            out.append({**detail, "videos": videos})
            print(f"  [{i}/{len(poi_ids)}] {detail.get('name') or pid}: "
                  f"{len(videos)} video's in feed", file=sys.stderr)
        await browser.close()
    return out


def report(results):
    print()
    print("=" * 92)
    print(f"  POI-FEED — {len(results)} locaties")
    print("=" * 92)
    for r in sorted(results, key=lambda r: -len(r["videos"])):
        vids = r["videos"]
        plays = sum(v.get("plays") or 0 for v in vids)
        tags = Counter()
        for v in vids:
            tags.update(v.get("hashtags") or [])
        top_tags = ", ".join(f"#{t}" for t, _ in tags.most_common(6))
        print(f"\n  {r.get('name') or r['id']}  "
              f"({(r.get('address') or '')[:50]})")
        print(f"    {len(vids)} video's | {fmt_int(plays)} plays totaal | "
              f"tags: {top_tags}")
        for v in sorted(vids, key=lambda v: -(v.get('plays') or 0))[:3]:
            print(f"      {fmt_int(v.get('plays')):>8} plays | "
                  f"[{v.get('lang')}] @{v.get('author')} | "
                  f"{(v.get('desc') or '')[:48]}")
    print("-" * 92)
    print("  Een video getagd op een NL-locatie is NL-gebonden ongeacht "
          "de taal. POI-id's verzamelen\n  gaat vanzelf: elke harvest legt "
          "poiId/poiName/poiAddress per video vast.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json",
                    help="harvest-output (trending.py / tiktok_tags.py)")
    ap.add_argument("--ids", default="", help="komma-gescheiden POI-id's")
    ap.add_argument("--top", type=int, default=10,
                    help="max POI's uit de harvest (default 10)")
    ap.add_argument("--scrolls", type=int, default=3)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    ids = []
    if args.from_json:
        path = os.path.join(HERE, args.from_json)
        if not os.path.exists(path):
            sys.exit(f"{args.from_json} niet gevonden.")
        rows = json.load(open(path, encoding="utf-8"))
        seeds = pois_from_harvest(rows, args.top)
        if not seeds:
            print("[poi] geen poiId's in deze harvest — draai de harvest "
                  "opnieuw met de nieuwste tiktok_tags.py", file=sys.stderr)
        ids = [s["id"] for s in seeds]
    ids += [i.strip() for i in args.ids.split(",") if i.strip()]
    if not ids:
        sys.exit("geen POI's: geef --from-json en/of --ids")

    print(f"[poi] {len(ids)} locaties harvesten…", file=sys.stderr)
    results = asyncio.run(run(ids, args.scrolls))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"[poi] opgeslagen → {args.out}", file=sys.stderr)
    report(results)


if __name__ == "__main__":
    main()
