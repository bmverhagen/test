"""
trending.py — geef een SECTOR en een LAND, krijg de meest trending
terms terug inclusief onderliggende data. Live van TikTok, geen login,
geen API-key, geen proxy nodig.

    python3 trending.py --sector hair --country NL
    python3 trending.py --sector skincare --country DE
    python3 trending.py --sector custom --seeds tag1,tag2 --lexicon woord1,woord2 --country NL

Hoe het werkt
-------------
1. SEEDS: per sector een watchlist in de landstaal + de Engelse tags die
   lokale creators ook gebruiken.
2. HARVEST: elke tag-pagina wordt headless geladen; TikTok's interne API
   levert per video caption, engagement, followers en TikTok's eigen
   taalclassificatie (textLanguage).
3. LANDFILTER: video's in de landstaal zijn de harde land-proxy. Per term
   berekenen we lokale share, plays, posts/dag, velocity en geschatte
   lokale views (tag-totaal x lokaal aandeel).
4. DISCOVERY: co-hashtags uit LOKALE video's die op het sector-lexicon
   matchen en nog niet in de watchlist zitten, worden ook geoogst — zo
   vind je termen die je zelf niet had bedacht.
5. RANKING: trend-score 0-100 uit lokale versnelling, lokale activiteit,
   lokale omvang en engagement.

Output: console-digest + data/trending_<sector>_<land>.json met alle
onderliggende data (per term: totalen, lokale metrics, top lokale
video's, lokale co-hashtags, alle lokale video's ruw).

Let op: voor Engelstalige landen (US/GB/AU) kan taal alleen "Engels"
aantonen, niet het land zelf — daarvoor is een residential proxy in dat
land de upgrade. Voor NL/DE/FR/ES/IT is taal een sterke land-proxy.
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

from tiktok_tags import UA, NOISE_TAGS, fmt_int, harvest_tag, is_dutch

HERE = os.path.dirname(os.path.abspath(__file__))

COUNTRIES = {
    "NL": {"lang": "nl", "locale": "nl-NL", "tz": "Europe/Amsterdam",
           "name": "Nederland"},
    "BE": {"lang": "nl", "locale": "nl-BE", "tz": "Europe/Brussels",
           "name": "België"},
    "DE": {"lang": "de", "locale": "de-DE", "tz": "Europe/Berlin",
           "name": "Duitsland"},
    "AT": {"lang": "de", "locale": "de-AT", "tz": "Europe/Vienna",
           "name": "Oostenrijk"},
    "FR": {"lang": "fr", "locale": "fr-FR", "tz": "Europe/Paris",
           "name": "Frankrijk"},
    "ES": {"lang": "es", "locale": "es-ES", "tz": "Europe/Madrid",
           "name": "Spanje"},
    "IT": {"lang": "it", "locale": "it-IT", "tz": "Europe/Rome",
           "name": "Italië"},
    "US": {"lang": "en", "locale": "en-US", "tz": "America/New_York",
           "name": "Verenigde Staten"},
    "GB": {"lang": "en", "locale": "en-GB", "tz": "Europe/London",
           "name": "Verenigd Koninkrijk"},
}

# Per sector: seeds per taal (en-seeds worden altijd meegenomen omdat
# lokale creators ook Engelse tags gebruiken) + lexicon voor discovery.
SECTORS = {
    "hair": {
        "lexicon": ["hair", "haar", "curl", "krul", "locken", "scalp",
                    "hoofdhuid", "kopfhaut", "olie", "öl", "serum", "bond",
                    "repair", "growth", "groei", "wachstum", "frizz",
                    "keratin", "keratine", "shampoo", "conditioner",
                    "blowout", "kapper", "friseur", "mask", "vlecht",
                    "braid", "kapsel", "coupe", "balayage", "highlight",
                    "blond", "brunette", "extension", "pruik", "wig",
                    "föhn", "fohn", "stijltang", "krultang", "heatless",
                    "wolfcut", "gloss", "glans", "toner", "olaplex",
                    "k18", "botox", "slickback", "ponytail", "bun",
                    "knotje", "hairstyle", "haircut"],
        "seeds": {
            "en": ["hairtok", "haircare", "hairgrowth", "rosemaryoil",
                   "bondrepair", "scalpcare", "curlyhair", "hairoil",
                   "hairmask", "heatlesscurls"],
            "nl": ["haarverzorging", "haartok", "haargroei", "krullen",
                   "haarolie", "haarmasker", "hoofdhuid", "haaruitval",
                   "haartips", "rozemarijnolie"],
            "de": ["haarpflege", "haarwachstum", "haarausfall", "locken",
                   "haaröl", "rosmarinöl", "haarmaske", "kopfhaut"],
        },
    },
    "skincare": {
        "lexicon": ["skin", "huid", "haut", "serum", "spf", "retinol",
                    "niacinamide", "acne", "akne", "moistur", "cleanser",
                    "glow", "barrier", "pores", "porien", "sunscreen",
                    "zonnebrand", "peeling"],
        "seeds": {
            "en": ["skincare", "skintok", "glassskin", "retinol",
                   "niacinamide", "skinbarrier", "slugging", "spf",
                   "acne", "koreanskincare"],
            "nl": ["huidverzorging", "acne", "drogehuid", "puistjes",
                   "huidtips"],
            "de": ["hautpflege", "hautpflegeroutine", "akne",
                   "trockenehaut", "unreinehaut"],
        },
    },
    "makeup": {
        "lexicon": ["makeup", "mascara", "blush", "lip", "foundation",
                    "concealer", "contour", "brow", "lash", "eyeliner",
                    "visagie", "schmink", "beauty"],
        "seeds": {
            "en": ["makeup", "makeuptutorial", "makeuphacks", "beautytok",
                   "lipcombo", "blush", "foundation", "mascara"],
            "nl": ["makeuptips", "beautytipsnl", "visagie"],
            "de": ["schminken", "makeupdeutsch", "schminktipps"],
        },
    },
    "fitness": {
        "lexicon": ["gym", "fitness", "workout", "train", "muscle",
                    "spier", "abnehmen", "afvallen", "protein", "eiwit",
                    "cardio", "kracht", "sport", "shred", "bulk"],
        "seeds": {
            "en": ["gymtok", "fitness", "workout", "gymmotivation",
                   "homeworkout", "weightloss", "musclegain"],
            "nl": ["sportschool", "afvallen", "krachttraining",
                   "spiermassa", "fitnessnederland"],
            "de": ["fitnessstudio", "abnehmen", "krafttraining",
                   "muskelaufbau"],
        },
    },
    "cleaning": {
        "lexicon": ["clean", "schoonmaak", "putz", "organiz", "opruim",
                    "declutter", "huishoud", "haushalt", "wasmiddel",
                    "stofzuig"],
        "seeds": {
            "en": ["cleantok", "cleaninghacks", "homeorganization",
                   "declutter", "cleaningmotivation"],
            "nl": ["schoonmaken", "schoonmaakhacks", "opruimen",
                   "huishouden"],
            "de": ["putzen", "haushaltstipps", "aufräumen", "putzroutine"],
        },
    },
    "food": {
        "lexicon": ["recipe", "recept", "rezept", "food", "eten", "essen",
                    "meal", "airfryer", "protein", "eiwit", "bak", "kook",
                    "koch", "lunch", "dinner", "snack"],
        "seeds": {
            "en": ["foodtok", "easyrecipes", "mealprep", "airfryerrecipes",
                   "highprotein", "dinnerideas"],
            "nl": ["recepten", "makkelijkerecepten", "airfryerrecepten",
                   "gezonderecepten", "avondeten"],
            "de": ["rezepte", "schnellerezepte", "airfryerrezepte",
                   "gesunderezepte"],
        },
    },
    "pets": {
        "lexicon": ["dog", "hond", "hund", "cat", "kat", "katze", "puppy",
                    "pet", "huisdier", "haustier", "kitten", "asiel"],
        "seeds": {
            "en": ["dogtok", "cattok", "dogtraining", "pethacks",
                   "puppytraining"],
            "nl": ["hond", "kat", "puppytraining", "huisdieren"],
            "de": ["hunde", "katzen", "hundetraining", "haustiere"],
        },
    },
}


def is_lang(v, lang):
    """Is deze video in de doeltaal? TikTok's eigen classificatie, met
    een stopwoord-fallback voor Nederlands."""
    if v.get("lang") == lang:
        return True
    if lang == "nl":
        return is_dutch(v)
    return False


def build_seeds(sector_cfg, lang):
    seeds = list(sector_cfg["seeds"].get(lang, []))
    for s in sector_cfg["seeds"].get("en", []):
        if s not in seeds:
            seeds.append(s)
    return seeds


def summarize_term(tag, detail, videos, lang):
    """Per term: globale harvest-metrics + het lokale (landstaal-)deel."""
    now = time.time()

    def window(vs, lo_d, hi_d):
        return [v for v in vs
                if v["createTime"]
                and lo_d * 86400 <= now - v["createTime"] < hi_d * 86400]

    local = [v for v in videos if is_lang(v, lang)]
    share = len(local) / len(videos) if videos else 0.0

    l7, l_prior = window(local, 0, 7), window(local, 7, 37)
    vel_now = len(l7) / 7
    vel_prior = len(l_prior) / 30 if l_prior else 0
    # Velocity is alleen betrouwbaar met genoeg massa in het
    # vergelijkingsvenster. De feed van mega-tags (bv. #kapper) is
    # recency-biased: bijna alles is <7d oud, dus het prior-venster
    # bevat soms maar 1 video -> ratio's als x55 die niets betekenen.
    vel_reliable = len(l_prior) >= 5

    co = Counter()
    for v in local:
        for h in v["hashtags"]:
            t = h.lower()
            if t != tag.lower() and t not in NOISE_TAGS:
                co[t] += 1

    plays = sum(v["plays"] for v in videos)
    eng = sum(v["likes"] + v["comments"] + v["shares"] + v["bookmarks"]
              for v in videos)
    l_plays = sum(v["plays"] for v in local)
    l_eng = sum(v["likes"] + v["comments"] + v["shares"] + v["bookmarks"]
                for v in local)

    return {
        "term": tag,
        "globalVideos": detail.get("videoCount"),
        "globalViews": detail.get("viewCount"),
        "harvested": len(videos),
        "engagementRate": round(eng / plays, 4) if plays else None,
        "local": {
            "videos": len(local),
            "share": round(share, 3),
            "plays": l_plays,
            "engagementRate": (round(l_eng / l_plays, 4)
                               if l_plays else None),
            "estViews": int((detail.get("viewCount") or 0) * share),
            "postsPerDay7": round(vel_now, 2),
            "velocityRatio": (round(vel_now / vel_prior, 2)
                              if vel_prior and vel_reliable else None),
            "priorSample": len(l_prior),
            "recent7": len(l7),
            "topCoHashtags": co.most_common(10),
            "topVideos": sorted(local, key=lambda v: -v["plays"])[:3],
        },
        "topVideos": sorted(videos, key=lambda v: -v["plays"])[:3],
        "localVideos": local,
    }


def trend_score(t):
    """0-100: hoe trending is deze term in het DOELLAND, nu.

    De velocity-ratio weegt bewust licht (15%): de tag-feed bestaat uit
    een vers-slot + all-time-hits-slot, waardoor de middenperiode
    (7-37d) ondervertegenwoordigd is en de ratio structureel te hoog
    uitvalt. Echte maand-op-maand groei kan alleen uit dagelijkse
    snapshots komen (daily_radar.py) of uit de Google Trends-momentum
    (country_demand.py)."""
    loc = t["local"]

    def cap(x, lim):
        return min((x or 0) / lim, 1.0)

    return int(round(
        15 * cap(loc["velocityRatio"], 5.0)     # indicatieve versnelling
        + 30 * cap(loc["postsPerDay7"], 2.0)    # lokale activiteit nu
        + 30 * cap(loc["estViews"], 50e6)       # lokale omvang
        + 15 * cap(loc["engagementRate"], 0.08)  # lokale engagement
        + 10 * cap(loc["share"], 0.6)            # hoe lokaal is de term
    ))


def discover(results, seen, lexicon, lang, limit):
    """Nieuwe kandidaat-termen: co-hashtags uit LOKALE video's die op het
    sector-lexicon matchen en nog niet geoogst zijn."""
    cand = Counter()
    for r in results:
        for v in r["localVideos"]:
            for h in v["hashtags"]:
                t = h.lower()
                if t in seen or t in NOISE_TAGS or len(t) < 3:
                    continue
                if any(k in t for k in lexicon):
                    cand[t] += 1
    return [t for t, c in cand.most_common(limit) if c >= 2]


async def run(seeds, lexicon, lang, locale, tz, scrolls, rounds,
              max_terms, proxy):
    results = []
    seen = {s.lower() for s in seeds}
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
                detail, videos = await harvest_tag(page, tag, scrolls)
                r = summarize_term(tag, detail, videos, lang)
                print(f"    {fmt_int(detail.get('viewCount'))} views "
                      f"globaal | {r['local']['videos']} lokale video's "
                      f"({r['local']['share']:.0%})", file=sys.stderr)
                results.append(r)

        await harvest_list(seeds, "seed")
        leftovers = []
        for rnd in range(1, rounds + 1):
            room = max_terms - len(results)
            if room <= 0:
                break
            cand = discover(results, seen, lexicon, lang,
                            limit=min(40, room) + 10)
            new = cand[:min(40, room)]
            leftovers = cand[len(new):]
            if not new:
                break
            seen.update(new)
            print(f"\n[discovery ronde {rnd}] {len(new)} lokale "
                  f"kandidaten: {new}\n", file=sys.stderr)
            await harvest_list(new, f"disc{rnd}")
        await browser.close()
    return results, leftovers


def report(results, leftovers, sector, country_code, country, top,
           out_path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for r in results:
        r["trendScore"] = trend_score(r)
    ranked = sorted(results, key=lambda r: -r["trendScore"])

    print()
    print("=" * 100)
    print(f"  MEEST TRENDING TERMS — sector: {sector.upper()} | land: "
          f"{country['name']} ({country_code}) | {now}")
    print("=" * 100)
    print(f"  {'#':>3} {'term':<22} {'score':>6} {'lok.share':>9} "
          f"{'est. lok. views':>15} {'lok.posts/d':>11} {'vs prior':>9} "
          f"{'eng':>6}")
    print("-" * 100)
    for i, r in enumerate(ranked[:top], 1):
        loc = r["local"]
        ratio = (f"x{loc['velocityRatio']}" if loc["velocityRatio"]
                 else "-")
        er = (f"{loc['engagementRate'] * 100:.1f}%"
              if loc["engagementRate"] else "-")
        print(f"  {i:>3} #{r['term']:<21} {r['trendScore']:>5}% "
              f"{loc['share']:>8.0%} {fmt_int(loc['estViews']):>15} "
              f"{loc['postsPerDay7']:>11} {ratio:>9} {er:>6}")
    print("-" * 100)
    print("  score = 30% lokale activiteit + 30% lokale omvang + 15% "
          "engagement + 15% versnelling* + 10% lokale share")
    print("  * 'vs prior' is INDICATIEF: de feed toont vooral verse "
          "video's + oude hits, waardoor deze ratio\n    te hoog uitvalt. "
          "Echte groei meet je met dagelijkse snapshots (daily_radar.py) "
          "of Google Trends\n    momentum (country_demand.py).")

    print("\n  ONDERLIGGENDE DATA (top terms):")
    for r in ranked[:min(top, 8)]:
        loc = r["local"]
        co = ", ".join(f"#{h}({c})" for h, c in loc["topCoHashtags"][:6])
        print(f"\n  • #{r['term'].upper()} — score {r['trendScore']}%")
        print(f"      globaal: {fmt_int(r['globalViews'])} views / "
              f"{fmt_int(r['globalVideos'])} video's | lokaal: "
              f"{loc['videos']} video's ({loc['share']:.0%}), "
              f"{fmt_int(loc['plays'])} plays, "
              f"±{fmt_int(loc['estViews'])} views, "
              f"{loc['recent7']} posts in 7d")
        if co:
            print(f"      lokale co-hashtags: {co}")
        for v in loc["topVideos"][:2]:
            age = (int((time.time() - v["createTime"]) / 86400)
                   if v["createTime"] else "?")
            print(f"      {fmt_int(v['plays']):>7} plays | @{v['author']} "
                  f"| {age}d | {v['desc'][:65]}")

    cooling = sorted(
        [r for r in results
         if r["local"]["velocityRatio"] is not None
         and r["local"]["velocityRatio"] < 0.9
         and r["local"]["videos"] >= 15],
        key=lambda r: r["local"]["velocityRatio"])
    stalled = [r for r in results
               if r["local"]["videos"] >= 25 and r["local"]["recent7"] == 0
               and r["local"]["estViews"] > 3e6
               and r["local"]["velocityRatio"] is None]
    if cooling or stalled:
        print("\n  DALENDE / AFKOELENDE TERMS (lokale post-activiteit "
              "krimpt):")
        for r in cooling:
            loc = r["local"]
            print(f"    #{r['term']:<22} vel x{loc['velocityRatio']:<5} | "
                  f"{loc['videos']} lokale video's | "
                  f"±{fmt_int(loc['estViews'])} views")
        for r in stalled:
            loc = r["local"]
            print(f"    #{r['term']:<22} STILGEVALLEN (0 posts in 7d) | "
                  f"{loc['videos']} lokale video's | "
                  f"±{fmt_int(loc['estViews'])} views")

    if leftovers:
        print(f"\n  NOG NIET GEOOGSTE LOKALE KANDIDATEN (volgende run): "
              f"{', '.join('#' + t for t in leftovers)}")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=1, ensure_ascii=False)
    print(f"\n  volledige onderliggende data -> {out_path}")


def main():
    ap = argparse.ArgumentParser(
        description="Sector + land in, meest trending terms uit.")
    ap.add_argument("--sector", required=True,
                    help=f"één van: {', '.join(SECTORS)} — of 'custom' "
                         f"met --seeds/--lexicon")
    ap.add_argument("--country", required=True,
                    help=f"één van: {', '.join(COUNTRIES)}")
    ap.add_argument("--seeds", default=None,
                    help="komma-gescheiden eigen watchlist (custom sector)")
    ap.add_argument("--lexicon", default=None,
                    help="komma-gescheiden discovery-woorden (custom)")
    ap.add_argument("--scrolls", type=int, default=5)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--rounds", type=int, default=1,
                    help="aantal discovery-rondes (co-hashtag mining)")
    ap.add_argument("--max-terms", type=int, default=60,
                    help="maximaal aantal te oogsten termen")
    ap.add_argument("--no-discover", action="store_true")
    ap.add_argument("--proxy", default=None,
                    help="residential proxy in het doelland (optioneel, "
                         "maakt ook de feed-samenstelling lokaal)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cc = args.country.upper()
    if cc not in COUNTRIES:
        sys.exit(f"Onbekend land '{cc}'. Kies uit: {', '.join(COUNTRIES)}")
    country = COUNTRIES[cc]

    sector = args.sector.lower()
    if sector == "custom":
        if not args.seeds:
            sys.exit("custom sector vereist --seeds")
        seeds = [t.strip().lstrip("#") for t in args.seeds.split(",")]
        lexicon = ([w.strip().lower() for w in args.lexicon.split(",")]
                   if args.lexicon else [])
    elif sector in SECTORS:
        cfg = SECTORS[sector]
        # --seeds mag de watchlist ook bij een bekende sector overriden;
        # het sector-lexicon blijft dan gelden voor discovery.
        if args.seeds:
            seeds = [t.strip().lstrip("#") for t in args.seeds.split(",")]
        else:
            seeds = build_seeds(cfg, country["lang"])
        lexicon = cfg["lexicon"]
    else:
        sys.exit(f"Onbekende sector '{sector}'. Kies uit: "
                 f"{', '.join(SECTORS)} of 'custom'.")

    if country["lang"] == "en":
        print("[let op] Engelstalig land: taal bewijst 'Engels', niet het "
              "land zelf. Gebruik --proxy voor echte US/GB-scheiding.\n",
              file=sys.stderr)

    out = args.out or f"data/trending_{sector}_{cc.lower()}.json"
    rounds = 0 if args.no_discover else args.rounds
    results, leftovers = asyncio.run(
        run(seeds, lexicon, country["lang"], country["locale"],
            country["tz"], args.scrolls, rounds, args.max_terms,
            args.proxy))
    report(results, leftovers, sector, cc, country, args.top, out)


if __name__ == "__main__":
    main()
