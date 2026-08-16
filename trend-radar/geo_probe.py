"""
geo_probe.py — waar komt een video vandaan? (locationCreated per video)

Antwoord op: "ik wil óók Engelstalige video's die Nederlanders bekijken."
Kijkers-geografie per video is niet publiek, maar de video-DETAILpagina
bevat wél `locationCreated`: het land waar de video gemaakt is. Daarmee
vang je de grootste groep die taalfiltering mist: Nederlandse/Vlaamse
creators die in het ENGELS posten voor bereik — hun publiek is alsnog
overwegend NL/BE.

Wat dit script doet:
1. Leest video's uit een eerdere harvest (trending.py of tiktok_tags.py
   JSON) — standaard alleen de niet-Nederlandstalige video's.
2. Laadt per video de detailpagina en parseert de SSR-blob
   (__UNIVERSAL_DATA_FOR_REHYDRATION__ → webapp.video-detail) voor:
   locationCreated, textLanguage, verse stats (plays/likes/bookmarks),
   diversificationLabels (TikToks eigen categorie-labels) en
   suggestedWords (zoektermen die TikTok aan de video hangt).
3. Rapporteert per tag welke anderstalige video's uit NL/BE komen, en
   de landverdeling van de rest.

    python3 geo_probe.py --from-json data/trending_hair_nl_top200.json
    python3 geo_probe.py --from-json data/tiktok_tags.json --limit 60
    python3 geo_probe.py --videos @maggiemh/7044722712388046126

Kosten: ~2 s per video (één page-load). Output ook naar
data/geo_probe.json zodat andere scripts hem kunnen gebruiken.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict

from playwright.async_api import async_playwright

from tiktok_tags import fmt_int

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "geo_probe.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BLOB_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.S)

LOCAL_COUNTRIES = {"NL", "BE"}


def collect_candidates(rows, include_nl=False):
    """Verzamel (tag, video) kandidaten uit trending.py- of
    tiktok_tags.py-output. Standaard alleen niet-NL-talige video's:
    daarvan willen we weten of ze tóch uit NL/BE komen."""
    seen = set()
    out = []
    for r in rows:
        tag = r.get("term") or r.get("tag")
        vids = ((r.get("topVideos") or []) + (r.get("localVideos") or [])
                + (r.get("videos") or []))
        for v in vids:
            vid, author = v.get("id"), v.get("author")
            if not vid or not author or vid in seen:
                continue
            if not include_nl and v.get("lang") == "nl":
                continue
            seen.add(vid)
            out.append({"tag": tag, "id": vid, "author": author,
                        "lang": v.get("lang"), "plays": v.get("plays")})
    # grootste eerst: daar zit het meeste kijkvolume
    out.sort(key=lambda v: -(v.get("plays") or 0))
    return out


def parse_detail(html):
    m = BLOB_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    item = (data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.video-detail", {})
            .get("itemInfo", {}).get("itemStruct"))
    if not item:
        return None
    stats = item.get("stats") or {}
    s2 = item.get("statsV2") or {}

    def num(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {
        "locationCreated": item.get("locationCreated"),
        "lang": item.get("textLanguage"),
        "desc": (item.get("desc") or "")[:200],
        "createTime": item.get("createTime"),
        "plays": num(s2.get("playCount")) or stats.get("playCount"),
        "likes": num(s2.get("diggCount")) or stats.get("diggCount"),
        "bookmarks": num(s2.get("collectCount")) or stats.get("collectCount"),
        "comments": num(s2.get("commentCount")) or stats.get("commentCount"),
        "shares": num(s2.get("shareCount")) or stats.get("shareCount"),
        "labels": item.get("diversificationLabels") or [],
        "suggested": [w.strip() for w in (item.get("suggestedWords") or [])
                      if w and w.strip()][:8],
    }


async def probe(cands, proxy=None, delay_ms=800):
    results = []
    launch = {"headless": True}
    if proxy:
        launch["proxy"] = {"server": proxy}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**launch)
        ctx = await browser.new_context(user_agent=UA, locale="nl-NL",
                                        timezone_id="Europe/Amsterdam")
        page = await ctx.new_page()
        for i, c in enumerate(cands, 1):
            url = f"https://www.tiktok.com/@{c['author']}/video/{c['id']}"
            try:
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=30000)
                await page.wait_for_timeout(delay_ms)
                detail = parse_detail(await page.content())
            except Exception as e:
                print(f"  [{i}/{len(cands)}] @{c['author']}/{c['id']} — "
                      f"fout: {str(e)[:60]}", file=sys.stderr)
                continue
            if not detail:
                print(f"  [{i}/{len(cands)}] @{c['author']}/{c['id']} — "
                      f"geen detail (verwijderd/geo-blok?)", file=sys.stderr)
                continue
            merged = {**c, **detail}
            results.append(merged)
            loc = detail["locationCreated"] or "?"
            print(f"  [{i}/{len(cands)}] {loc:>2} [{detail['lang']}] "
                  f"#{c['tag']} @{c['author']} "
                  f"{fmt_int(detail['plays'] or 0)} plays",
                  file=sys.stderr)
        await browser.close()
    return results


def report(results):
    print()
    print("=" * 96)
    print(f"  GEO-PROBE — {len(results)} video's verrijkt met locationCreated")
    print("=" * 96)

    local = [r for r in results
             if r["locationCreated"] in LOCAL_COUNTRIES and r["lang"] != "nl"]
    if local:
        print("\n  ANDERSTALIG MAAR GEMAAKT IN NL/BE — Engelstalige (e.a.) "
              "video's met Nederlands publiek:")
        print(f"  {'land':<5} {'taal':<5} {'plays':>9} {'saves':>8} "
              f"{'tag':<20} {'creator':<20} omschrijving")
        print("-" * 96)
        for r in sorted(local, key=lambda r: -(r["plays"] or 0)):
            print(f"  {r['locationCreated']:<5} {r['lang'] or '?':<5} "
                  f"{fmt_int(r['plays'] or 0):>9} "
                  f"{fmt_int(r['bookmarks'] or 0):>8} "
                  f"#{(r['tag'] or '')[:18]:<19} "
                  f"@{(r['author'] or '')[:18]:<19} "
                  f"{(r['desc'] or '')[:34]}")
    else:
        print("\n  Geen anderstalige video's uit NL/BE in deze set.")

    by_tag = defaultdict(Counter)
    for r in results:
        by_tag[r["tag"]][r["locationCreated"] or "?"] += 1
    print("\n  HERKOMST PER TAG (aantal gepeilde video's per land):")
    for tag, cnt in sorted(by_tag.items(),
                           key=lambda kv: -sum(kv[1].values())):
        top = ", ".join(f"{k}:{v}" for k, v in cnt.most_common(6))
        nl_n = sum(v for k, v in cnt.items() if k in LOCAL_COUNTRIES)
        tot = sum(cnt.values())
        print(f"    #{tag:<24} {nl_n}/{tot} uit NL/BE   ({top})")

    labels = Counter()
    for r in results:
        labels.update(r.get("labels") or [])
    if labels:
        print("\n  TIKTOK-CATEGORIELABELS in deze set (diversification):")
        print("    " + ", ".join(f"{k} ({v})"
                                 for k, v in labels.most_common(12)))

    print("-" * 96)
    print("  locationCreated = land van de maker (uit de detailpagina-SSR). "
          "Anderstalige video's uit NL/BE\n  zijn de grootste groep die "
          "taalfiltering mist: NL-creators die Engels posten voor bereik.\n"
          "  Voor het féítelijke NL-kijkgedrag op buitenlandse video's is "
          "een NL-residential-proxy nodig:\n  de tag-feed zelf is "
          "geo-gepersonaliseerd, dus wat je via een NL-IP binnenkrijgt "
          "(ook Engelstalig)\n  is per definitie wat TikTok de NL-markt "
          "voorschotelt. Draai daarvoor trending.py met --proxy.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json",
                    help="output van trending.py of tiktok_tags.py")
    ap.add_argument("--videos", nargs="*", default=[],
                    help="losse video's als @author/id")
    ap.add_argument("--limit", type=int, default=30,
                    help="max aantal video's om te peilen (default 30)")
    ap.add_argument("--include-nl", action="store_true",
                    help="ook Nederlandstalige video's peilen")
    ap.add_argument("--proxy", help="bijv. socks5://host:port (NL-IP)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    cands = []
    if args.from_json:
        path = os.path.join(HERE, args.from_json)
        if not os.path.exists(path):
            sys.exit(f"{args.from_json} niet gevonden — draai eerst een "
                     f"harvest.")
        rows = json.load(open(path, encoding="utf-8"))
        cands = collect_candidates(rows, include_nl=args.include_nl)
    for spec in args.videos:
        m = re.match(r"@?([\w.\-]+)/(\d+)", spec)
        if not m:
            sys.exit(f"ongeldig video-formaat: {spec} (verwacht @author/id)")
        cands.append({"tag": None, "author": m.group(1), "id": m.group(2),
                      "lang": None, "plays": None})
    if not cands:
        sys.exit("geen video's: geef --from-json en/of --videos")
    cands = cands[:args.limit]

    print(f"[geo-probe] {len(cands)} video's peilen…", file=sys.stderr)
    results = asyncio.run(probe(cands, proxy=args.proxy))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"[geo-probe] {len(results)} resultaten → {args.out}",
          file=sys.stderr)
    report(results)


if __name__ == "__main__":
    main()
