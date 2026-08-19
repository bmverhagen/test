"""
transcripts.py — gesproken tekst per video (ASR-ondertitels), puur TikTok.

TikTok genereert automatische ondertitels (ASR) voor video's met
spraak. De video-detailpagina vermeldt per video de beschikbare
tracks (`video.subtitleInfos`, incl. taal en bron) en de bijbehorende
WebVTT-bestanden zijn direct downloadbaar. Daarmee krijg je de
VOLLEDIGE gesproken tekst van een video — waar merknamen en
producten vaak wél genoemd worden terwijl ze niet in de caption staan.

    python3 transcripts.py --from-json data/trending_hair_nl_top200.json --nl
    python3 transcripts.py --videos @zackouda/7674338575718141216

Output: data/transcripts.json met per video de transcript-tekst, de
taal van de track en gevonden keyword-hits; plus een console-digest
met de meest genoemde termen over alle transcripten (ruw
product/merk-signaal uit spraak).

Kosten: ~2-3 s per video (één page-load + één VTT-download).
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter

from playwright.async_api import async_playwright

from tiktok_tags import UA, is_dutch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "transcripts.json")

BLOB_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.S)

NL_STOP = set("""de het een en van in op is dat je ik niet met voor aan er
ook als dan maar zijn heb hebben wordt worden bij naar dus wat dit die deze
door over uit nog wel geen hoe mijn jouw jullie we ze hij zij hun onze meer
heel echt gewoon even weer gaat gaan doen doet kan kunnen moet moeten wil
willen laat laten""".split())


def vtt_to_text(vtt):
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or line == "WEBVTT" or "-->" in line
                or line.isdigit()):
            continue
        lines.append(line)
    # opeenvolgende duplicaten (rolling captions) ontdubbelen
    out = []
    for ln in lines:
        if not out or out[-1] != ln:
            out.append(ln)
    return " ".join(out)


def collect(rows, nl_only):
    seen = set()
    out = []
    for r in rows:
        tag = r.get("term") or r.get("tag")
        for v in ((r.get("localVideos") or []) + (r.get("videos") or [])):
            if not v.get("id") or v["id"] in seen:
                continue
            if nl_only and not is_dutch(v):
                continue
            seen.add(v["id"])
            out.append({"tag": tag, "id": v["id"], "author": v.get("author"),
                        "plays": v.get("plays")})
    out.sort(key=lambda v: -(v.get("plays") or 0))
    return out


async def fetch_transcript(page, author, video_id):
    url = f"https://www.tiktok.com/@{author}/video/{video_id}"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)
    m = BLOB_RE.search(await page.content())
    if not m:
        return None
    try:
        item = (json.loads(m.group(1))["__DEFAULT_SCOPE__"]
                ["webapp.video-detail"]["itemInfo"]["itemStruct"])
    except (KeyError, json.JSONDecodeError):
        return None
    subs = item.get("video", {}).get("subtitleInfos") or []
    if not subs:
        return {"lang": None, "text": None}
    # voorkeur: ASR-track in de oorspronkelijke taal, anders de eerste
    track = next((s for s in subs if s.get("Source") == "ASR"), subs[0])
    try:
        resp = await page.request.get(track["Url"])
        text = vtt_to_text(await resp.text())
    except Exception:
        return {"lang": track.get("LanguageCodeName"), "text": None}
    return {"lang": track.get("LanguageCodeName"), "text": text,
            "tracks": [s.get("LanguageCodeName") for s in subs]}


async def run(cands):
    out = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="nl-NL",
                                        timezone_id="Europe/Amsterdam")
        page = await ctx.new_page()
        for i, c in enumerate(cands, 1):
            try:
                t = await fetch_transcript(page, c["author"], c["id"])
            except Exception as e:
                print(f"  [{i}/{len(cands)}] @{c['author']} fout: "
                      f"{str(e)[:60]}", file=sys.stderr)
                continue
            if t is None:
                print(f"  [{i}/{len(cands)}] @{c['author']} — geen detail",
                      file=sys.stderr)
                continue
            got = "geen spraak/track" if not t.get("text") else \
                f"{t['lang']}, {len(t['text'])} tekens"
            print(f"  [{i}/{len(cands)}] @{c['author']} — {got}",
                  file=sys.stderr)
            out.append({**c, **t})
        await browser.close()
    return out


def report(results):
    with_text = [r for r in results if r.get("text")]
    print()
    print("=" * 92)
    print(f"  TRANSCRIPTS — {len(with_text)}/{len(results)} video's met "
          f"gesproken tekst")
    print("=" * 92)
    words = Counter()
    for r in with_text:
        for w in re.findall(r"[a-zà-ÿ']{4,}", r["text"].lower()):
            if w not in NL_STOP:
                words[w] += 1
    if words:
        print("\n  MEEST GENOEMDE TERMEN (over alle transcripten):")
        print("    " + ", ".join(f"{w} ({n})"
                                 for w, n in words.most_common(25)))
    for r in with_text[:8]:
        print(f"\n  #{r['tag']} @{r['author']} [{r['lang']}]:")
        print(f"    \"{r['text'][:180]}…\"")
    print("-" * 92)
    print("  In spraak vallen merk- en productnamen die captions "
          "weglaten. Voer de transcript-tekst aan\n  attribute_bridge of "
          "een LLM voor product/merk-extractie per trend.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json",
                    help="harvest-output (trending.py / tiktok_tags.py)")
    ap.add_argument("--videos", nargs="*", default=[],
                    help="losse video's als @author/id")
    ap.add_argument("--nl", action="store_true",
                    help="alleen NL-video's uit de harvest")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    cands = []
    if args.from_json:
        path = os.path.join(HERE, args.from_json)
        if not os.path.exists(path):
            sys.exit(f"{args.from_json} niet gevonden.")
        rows = json.load(open(path, encoding="utf-8"))
        cands = collect(rows, nl_only=args.nl)
    for spec in args.videos:
        m = re.match(r"@?([\w.\-]+)/(\d+)", spec)
        if not m:
            sys.exit(f"ongeldig formaat: {spec} (verwacht @author/id)")
        cands.append({"tag": None, "author": m.group(1),
                      "id": m.group(2), "plays": None})
    if not cands:
        sys.exit("geen video's: geef --from-json en/of --videos")
    cands = cands[:args.limit]

    print(f"[transcripts] {len(cands)} video's…", file=sys.stderr)
    results = asyncio.run(run(cands))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"[transcripts] opgeslagen → {args.out}", file=sys.stderr)
    report(results)


if __name__ == "__main__":
    main()
