"""
embed_enrich.py — bulk video-verrijking via embed-pagina's, ZONDER browser.

De embed-pagina (tiktok.com/embed/v2/<video-id>) is bedoeld voor
insluiten op andere sites en werkt daarom met kale HTTP — geen
Playwright, geen login, geen bot-muur. Eén GET van ~300KB bevat per
video vrijwel alles wat de zware detailpagina ook geeft:

    itemInfos     — tellers (plays/likes/comments/shares), createTime,
                    caption, isAd, isECVideo, locationCreated
    authorInfos   — uniqueId, nickname, verified
    authorStats   — volgers, hearts, videoCount
    musicInfos    — sound-id, naam, original
    challenges    — alle hashtags
    stickerText   — tekst-overlays ín de video
    viewerRegion  — regio die TikTok aan JOU toekent (proxycheck!)

Dat maakt honderden verrijkingen per minuut mogelijk (parallelle
HTTP-requests) waar de detailpagina ~2 s per video kost via Playwright.
Ontbreekt t.o.v. de detailpagina: bookmarks (collectCount),
diversificationLabels en suggestedWords — daarvoor blijft geo_probe.py.

    python3 embed_enrich.py --from-json data/trending_hair_nl_top200.json
    python3 embed_enrich.py --ids 7595385142798060830 --limit 500
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from tiktok_tags import fmt_int

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "embed_enrich.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

VIDEO_DATA_RE = re.compile(r'"videoData":\s*')


def extract_json_object(html, start):
    depth = 0
    for i, ch in enumerate(html[start:start + 60000]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start:start + i + 1]
    return None


def fetch_embed(video_id, timeout=15):
    url = f"https://www.tiktok.com/embed/v2/{video_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "nl-NL"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    m = VIDEO_DATA_RE.search(html)
    if not m:
        return None
    raw = extract_json_object(html, m.end())
    if not raw:
        return None
    vd = json.loads(raw)
    ii = vd.get("itemInfos") or {}
    ai = vd.get("authorInfos") or {}
    st = vd.get("authorStats") or {}
    mu = vd.get("musicInfos") or {}
    stickers = []
    for s in vd.get("stickerTextList") or []:
        stickers.extend(s.get("stickerText") or [])
    return {
        "id": ii.get("id"),
        "desc": (ii.get("text") or "")[:300],
        "createTime": int(ii.get("createTime") or 0),
        "plays": ii.get("playCount"),
        "likes": ii.get("diggCount"),
        "comments": ii.get("commentCount"),
        "shares": ii.get("shareCount"),
        "isAd": ii.get("isAd"),
        "isECVideo": ii.get("isECVideo"),
        "locationCreated": ii.get("locationCreated"),
        "author": ai.get("uniqueId"),
        "authorFollowers": st.get("followerCount"),
        "musicId": mu.get("musicId"),
        "music": mu.get("musicName"),
        "musicOriginal": mu.get("original"),
        "hashtags": [c.get("challengeName")
                     for c in vd.get("challengeInfoList") or []],
        "stickerText": stickers,
        "viewerRegion": ii.get("viewerRegion"),
    }


def collect_ids(rows, limit):
    seen, out = set(), []
    for r in rows:
        tag = r.get("term") or r.get("tag")
        for v in ((r.get("localVideos") or []) + (r.get("videos") or [])
                  + (r.get("topVideos") or [])):
            vid = v.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append((tag, vid))
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json",
                    help="harvest-output (trending.py / tiktok_tags.py)")
    ap.add_argument("--ids", default="", help="komma-gescheiden video-id's")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    pairs = []
    if args.from_json:
        path = os.path.join(HERE, args.from_json)
        if not os.path.exists(path):
            sys.exit(f"{args.from_json} niet gevonden.")
        rows = json.load(open(path, encoding="utf-8"))
        pairs = collect_ids(rows, args.limit)
    for vid in args.ids.split(","):
        if vid.strip():
            pairs.append((None, vid.strip()))
    if not pairs:
        sys.exit("geen video's: geef --from-json en/of --ids")

    print(f"[embed] {len(pairs)} video's verrijken "
          f"({args.workers} parallel)…", file=sys.stderr)
    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_embed, vid): (tag, vid)
                for tag, vid in pairs}
        for n, fut in enumerate(as_completed(futs), 1):
            tag, vid = futs[fut]
            try:
                d = fut.result()
            except Exception:
                d = None
            if d and d.get("id"):
                d["tag"] = tag
                results.append(d)
            else:
                failed += 1
            if n % 25 == 0 or n == len(pairs):
                print(f"  {n}/{len(pairs)} klaar ({failed} mislukt)",
                      file=sys.stderr)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"[embed] {len(results)} opgeslagen → {args.out}", file=sys.stderr)

    print()
    print("=" * 92)
    print(f"  EMBED-ENRICH — {len(results)} video's ({failed} mislukt), "
          f"browser-loos")
    print("=" * 92)
    locs = Counter(r.get("locationCreated") or "?" for r in results)
    print("  herkomst:", ", ".join(f"{k}:{v}" for k, v in
                                   locs.most_common(12)))
    nlbe = [r for r in results if r.get("locationCreated") in ("NL", "BE")]
    if nlbe:
        print("\n  GEMAAKT IN NL/BE:")
        for r in sorted(nlbe, key=lambda r: -(r.get("plays") or 0))[:10]:
            print(f"    {fmt_int(r.get('plays') or 0):>8} plays | "
                  f"@{r.get('author')} | #{r.get('tag')} | "
                  f"{(r.get('desc') or '')[:45]}")
    ads = sum(1 for r in results if r.get("isAd"))
    ec = sum(1 for r in results if r.get("isECVideo"))
    print(f"\n  advertenties: {ads} | e-commerce-video's: {ec} | "
          f"viewerRegion (proxycheck): "
          f"{Counter(r.get('viewerRegion') for r in results).most_common(1)}")


if __name__ == "__main__":
    main()
