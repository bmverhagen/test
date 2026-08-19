"""
Attribute bridge: turn raw TikTok trends into Amazon-joinable insights.

The problem: TikTok gives hashtags/keywords; Amazon gives product titles.
They don't join on ASIN — they join on PRODUCT ATTRIBUTE (ingredient,
format, concern, technique). This module maps both sides onto one shared
attribute taxonomy, so every TikTok trend becomes a row you can couple to
Amazon products.

What it does
------------
1. Load TikTok keyword data (data/tiktok_tags.json).
2. For each attribute in the taxonomy, aggregate the matching TikTok
   signals: views, velocity, engagement, and mine the captions for BRAND
   mentions and product evidence. Media noise (news, celebrities, memes)
   never enters because the taxonomy only contains product attributes.
3. Optionally run the Amazon engine on the demo data and JOIN on the
   attribute name -> a unified "hype vs revenue" view per attribute:
     - TikTok side  = demand/hype (views, velocity)
     - Amazon side  = revenue proof (mid-tail momentum, funnel phase)
4. Emit data/attributes.json (the join key for downstream Amazon work)
   and a readable digest.

The funnel logic is deliberately cross-platform:
  hype WITHOUT Amazon product  -> WHITESPACE (make/stock it)
  hype WITH rising Amazon      -> FIRST MONEY / PROVEN (act now)
  Amazon big, hype cooling     -> ESTABLISHED / defend

Usage:
    python3 generate_demo_data.py      # so the Amazon side has data
    python3 attribute_bridge.py
    python3 attribute_bridge.py --no-amazon   # TikTok side only
"""

import argparse
import json
import os
import re
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

# Shared attribute taxonomy. `amazon` = title needles (aligned with
# engine.SIGNALS); `tiktok` = hashtag/caption aliases incl. Dutch terms.
TAXONOMY = {
    "rosemary oil": {"level": "ingredient",
                     "amazon": ["rosemary oil"],
                     "tiktok": ["rosemaryoil", "rozemarijnolie",
                                "rosemary", "rozemarijn"]},
    "scalp serum": {"level": "format",
                    "amazon": ["scalp serum", "scalp treatment"],
                    "tiktok": ["scalpserum", "scalpcare", "scalptreatment",
                               "hoofdhuid", "scalphealth"]},
    "bond repair": {"level": "format",
                    "amazon": ["bond repair", "bonding", "probond",
                               "bond intense"],
                    "tiktok": ["bondrepair", "hairrepair", "damagedhair"]},
    "leave-in": {"level": "format",
                 "amazon": ["leave-in"],
                 "tiktok": ["leaveinconditioner", "leavein",
                            "leaveintreatment"]},
    "argan oil": {"level": "ingredient",
                  "amazon": ["argan oil"],
                  "tiktok": ["arganoil", "arganolie"]},
    "keratin": {"level": "ingredient",
                "amazon": ["keratin"],
                "tiktok": ["keratin"]},
    "hair oiling": {"level": "technique",
                    "amazon": ["hair oil"],
                    "tiktok": ["hairoiling", "hairoil", "haarolie"]},
    "heatless curls": {"level": "technique",
                       "amazon": ["heatless"],
                       "tiktok": ["heatlesscurls", "heatlesshair",
                                  "sockcurls", "heatlesscurlstutorial"]},
    "curly hair care": {"level": "concern",
                        "amazon": ["curl", "curly"],
                        "tiktok": ["curlyhair", "krullen", "curlygirlmethode",
                                   "curlyhairroutine", "krullendhaar",
                                   "curlygirlmethod"]},
    "hair growth": {"level": "concern",
                    "amazon": ["hair growth", "growth serum"],
                    "tiktok": ["hairgrowth", "haargroei", "hairgrowthtips"]},
    "hair loss": {"level": "concern",
                  "amazon": ["hair loss", "thinning", "anti-hair fall"],
                  "tiktok": ["haaruitval", "hairloss", "alopecia"]},
    "hair mask": {"level": "format",
                  "amazon": ["hair mask"],
                  "tiktok": ["haarmasker", "hairmask"]},
}

# Known hair-care brands to mine from captions (lowercased tokens).
BRANDS = [
    "olaplex", "k18", "mielle", "shea moisture", "sheamoisture", "ogx",
    "ouai", "gisou", "kerastase", "kérastase", "redken", "medicube",
    "garnier", "loreal", "l'oreal", "l’oreal", "batiste", "herbal essences",
    "not your mother", "bounce curl", "the ordinary", "kristin ess",
    "living proof", "amika", "verb", "moroccanoil", "cerave",
]

# Caption cues that separate BUY-intent from pure media trends. A video
# whose caption contains one of these is treated as a commerce signal.
COMMERCE_CUES = [
    "tiktokshop", "tiktok shop", "tiktokmademebuyit", "link in bio",
    "linkinbio", "shop now", "shopnow", "use code", "kortingscode",
    "korting", "affiliate", "#ad", "amazonfinds", "amazon", "sephora",
    "ulta", "douglas", "kruidvat", "bestellen", "gekocht", "sold out",
    "restock", "must have", "musthave", "where to buy",
]


def fmt_int(n):
    if not n:
        return "-"
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def matches(text, needles):
    t = text.lower()
    return any(n in t for n in needles)


DUTCH_HINTS = (" een ", " het ", " niet ", " voor ", " mijn ", " deze ",
               " ook ", " maar ", " echt ", " krullen ", " hoofdhuid ",
               " tegen ", " jouw ", " gebruik ")


def is_dutch(v):
    """NL/Flanders proxy: TikTok's per-video textLanguage ('lang' field),
    with a Dutch-stopword fallback for unclassified captions."""
    lang = v.get("lang")
    if lang == "nl":
        return True
    if lang not in (None, "", "un"):
        return False
    d = " " + (v.get("desc") or "").lower() + " "
    return sum(1 for w in DUTCH_HINTS if w in d) >= 2


def compute_signals(vids, brand_counter):
    """Second-order leading indicators from the raw harvested videos.

    Research-backed early signals that plain view counts miss:
      save_rate        bookmarks/plays — purchase-intent proxy (people save
                       what they plan to buy/try, strongest leading metric)
      unique_creators  breadth: >=~10 independent creators = real trend,
                       1-2 accounts = fluke (top_author_share catches this)
      breakout_share   videos where plays > 5x the author's followers =
                       the algorithm is pushing the topic beyond existing
                       audiences (pre-viral tell)
      fresh_share_30d  fraction of harvested videos <30d old; combined with
                       recency_boost (avg plays recent vs older) it answers
                       "is this still rising or already peaked?"
      commerce_intent  fraction of captions with shop/buy cues — separates
                       purchasable trends from pure media noise
      branded_share    fraction of videos naming a known brand; low share +
                       commerce intent = unbranded demand = private-label gap
      top_brand_share  concentration among brand mentions; >50% = one brand
                       owns the trend (benchmark/dupe target, hard to enter)
    """
    n = len(vids)
    if not n:
        return {}
    plays = sum(v.get("plays") or 0 for v in vids)
    bookmarks = sum(v.get("bookmarks") or 0 for v in vids)
    shares = sum(v.get("shares") or 0 for v in vids)

    author_counts = Counter(v["author"] for v in vids if v.get("author"))
    top_author_share = (author_counts.most_common(1)[0][1] / n
                        if author_counts else 0.0)

    now = time.time()
    recent = [v for v in vids
              if v.get("createTime") and now - v["createTime"] < 30 * 86400]
    older = [v for v in vids
             if v.get("createTime") and now - v["createTime"] >= 30 * 86400]

    def avg_plays(rows):
        return (sum(v.get("plays") or 0 for v in rows) / len(rows)
                if rows else 0)

    recent_avg, older_avg = avg_plays(recent), avg_plays(older)

    breakout = [v for v in vids
                if (v.get("authorFollowers") or 0) > 0
                and (v.get("plays") or 0) > 5 * v["authorFollowers"]]
    commerce = [v for v in vids
                if any(c in (v.get("desc") or "").lower()
                       for c in COMMERCE_CUES)]
    branded = [v for v in vids
               if any(b in (v.get("desc") or "").lower() for b in BRANDS)]

    total_mentions = sum(brand_counter.values())
    top_brand_share = (brand_counter.most_common(1)[0][1] / total_mentions
                       if total_mentions else 0.0)

    nl_vids = [v for v in vids if is_dutch(v)]
    nl_recent = [v for v in nl_vids
                 if v.get("createTime")
                 and now - v["createTime"] < 30 * 86400]

    return {
        "sample_videos": n,
        "save_rate": round(bookmarks / plays, 4) if plays else None,
        "share_rate": round(shares / plays, 4) if plays else None,
        "unique_creators": len(author_counts),
        "top_author_share": round(top_author_share, 2),
        "breakout_share": round(len(breakout) / n, 2),
        "fresh_share_30d": round(len(recent) / n, 2),
        "recency_boost": (round(recent_avg / older_avg, 2)
                          if older_avg else None),
        "commerce_intent": round(len(commerce) / n, 2),
        "branded_share": round(len(branded) / n, 2),
        "top_brand_share": round(top_brand_share, 2),
        "nl_videos": len(nl_vids),
        "nl_share": round(len(nl_vids) / n, 2),
        "nl_plays": sum(v.get("plays") or 0 for v in nl_vids),
        "nl_recent_30d": len(nl_recent),
    }


def conviction_score(row):
    """0-100 composite: how many INDEPENDENT signals confirm this trend.

    One hot metric can be a fluke; velocity + saves + breadth + commerce
    intent + algorithmic push confirming each other rarely is.
    """
    s = row.get("signals") or {}

    def cap(x, lim):
        return min((x or 0) / lim, 1.0)

    score = (
        25 * cap(row.get("velocity"), 3.0)          # posting acceleration
        + 20 * cap(s.get("save_rate"), 0.05)        # 5% saves = exceptional
        + 15 * cap(s.get("unique_creators"), 25)    # breadth
        + 15 * cap(s.get("commerce_intent"), 0.25)  # buy-intent
        + 15 * cap(s.get("breakout_share"), 0.30)   # algorithmic push
        + 10 * cap(s.get("fresh_share_30d"), 0.50)  # still-fresh content
    )
    # Haircut when one account dominates the sample: not an organic trend.
    if (s.get("top_author_share") or 0) > 0.4:
        score *= 0.7
    return int(round(score))


def opportunity(row):
    """Commercial read of the brand landscape inside the trend."""
    s = row.get("signals") or {}
    branded = s.get("branded_share") or 0
    top_brand = s.get("top_brand_share") or 0
    commerce = s.get("commerce_intent") or 0
    if branded < 0.25 and commerce >= 0.10:
        return "PRIVATE-LABEL KANS — koopintentie zonder merkdominantie"
    if branded >= 0.25 and top_brand >= 0.50:
        leader = row["brands"][0][0] if row["brands"] else "?"
        return f"MERK-GEDOMINEERD — {leader} bezit de trend (dupe/benchmark)"
    if branded >= 0.25:
        return "GEFRAGMENTEERD MERKVELD — ruimte voor een challenger"
    return "MEDIA-TREND — nog weinig directe koopsignalen"


def load_tiktok():
    path = os.path.join(HERE, "data", "tiktok_tags.json")
    if not os.path.exists(path):
        return []
    return json.load(open(path, encoding="utf-8"))


def aggregate_attribute(attr, spec, tt_rows):
    """Aggregate an attribute from TikTok data.

    Headline metrics (views/velocity/posts) come ONLY from tags whose
    NAME matches an alias (a directly harvested tag). Co-hashtag presence
    is recorded separately as a weaker co-occurrence signal and never
    inherits the parent tag's totals — otherwise e.g. #hairgrowth
    appearing under #rosemaryoil would steal rosemary oil's view count.
    """
    aliases = [attr.replace(" ", "")] + spec["tiktok"]
    views = velocity = engagement = posts = 0.0
    nl_est_views = 0
    brand_counter = Counter()
    evidence = []
    matched_tags = []      # directly harvested tags for this attribute
    co_occurs_in = []      # tags where this attr shows up only as co-hashtag
    vids = {}              # id -> video, deduped across matched tags

    for r in tt_rows:
        tag = r["tag"].lower()
        co = " ".join(h.lower() for h, _ in r.get("topCoHashtags", []))
        direct = any(a in tag for a in aliases)
        if not direct:
            if any(a in co for a in aliases):
                co_occurs_in.append(r["tag"])
            continue
        # direct match: this tag IS the attribute -> trust its metrics
        matched_tags.append(r["tag"])
        views = max(views, r.get("totalViews") or 0)
        if r.get("velocityRatio"):
            velocity = max(velocity, r["velocityRatio"])
        if r.get("engagementRate"):
            engagement = max(engagement, r["engagementRate"])
        posts = max(posts, r.get("totalVideos") or 0)
        # per-tag NL estimate (tag total x Dutch share of THAT tag's feed);
        # summing per tag avoids crediting a global tag's views to NL just
        # because a sister tag in the same attribute is Dutch.
        nl_est_views += (r.get("nl") or {}).get("estNLViews") or 0
        for v in r.get("videos", []):
            vids[v.get("id") or len(vids)] = v
            desc = (v.get("desc") or "")
            low = desc.lower()
            for b in BRANDS:
                if b in low:
                    brand_counter[b] += 1
            if desc and len(evidence) < 4 and matches(low, aliases):
                evidence.append({"plays": v.get("plays"),
                                 "author": v.get("author"),
                                 "desc": desc[:90]})

    if not matched_tags:
        # attribute only co-occurs, not directly harvested -> not measurable
        # from this watchlist; surface as a discovery hint, no borrowed views.
        if co_occurs_in:
            return {"attribute": attr, "level": spec["level"],
                    "matched_tags": [], "co_occurs_in": co_occurs_in,
                    "tiktok_views": 0, "tiktok_posts": 0, "velocity": None,
                    "engagement": None, "brands": [], "evidence": [],
                    "amazon_needles": spec["amazon"],
                    "amazon_query": f"{attr} hair", "discovery_only": True}
        return None
    return {
        "attribute": attr,
        "level": spec["level"],
        "matched_tags": matched_tags,
        "co_occurs_in": co_occurs_in,
        "tiktok_views": int(views),
        "tiktok_posts": int(posts),
        "nl_est_views": int(nl_est_views),
        "velocity": round(velocity, 2) if velocity else None,
        "engagement": round(engagement, 4) if engagement else None,
        "brands": brand_counter.most_common(5),
        "signals": compute_signals(list(vids.values()), brand_counter),
        "evidence": evidence,
        "amazon_needles": spec["amazon"],
        "amazon_query": f"{attr} hair",
        "discovery_only": False,
    }


def hype_phase(row):
    """TikTok-side phase from velocity + size (detection-research thresholds)."""
    vel = row["velocity"] or 0
    big = row["tiktok_views"] >= 5_000_000_000
    if vel >= 3:
        return "EMERGING (accelerating hard)"
    if vel >= 2:
        return "RISING"
    if vel >= 1.5:
        return "HEATING"
    if big:
        return "ESTABLISHED (large, flat)"
    return "STABLE"


def run_amazon():
    """Return {attribute_name: (funnel_phase, momentum, asin_count)} or {}."""
    try:
        import engine
    except Exception:
        return {}
    data_dir = os.path.join(HERE, "data")
    if not os.path.exists(os.path.join(data_dir, "asins.csv")):
        return {}
    results, baseline = engine.analyse(data_dir)
    out = {}
    for res in results:
        phase, _action = engine.classify(res, baseline)
        out[res.name] = {"phase": phase,
                         "momentum": round(res.momentum, 3),
                         "asins": res.asin_count,
                         "rising": res.rising_asins,
                         "top100": res.top100_asins}
    return out


def combined_phase(hype, amazon):
    """Cross-platform funnel: what to do, given both sides."""
    has_amazon = amazon is not None and amazon.get("asins", 0) > 0
    accelerating = hype.startswith(("EMERGING", "RISING", "HEATING"))
    if accelerating and not has_amazon:
        return "WHITESPACE — hype, geen Amazon-product: maken/inkopen"
    if accelerating and has_amazon:
        ap = amazon["phase"]
        if "FIRST MONEY" in ap or "PROVEN" in ap:
            return "ACT NOW — hype + stijgende Amazon-omzet"
        if "ESTABLISHED" in ap:
            return "DEFEND — hype + gevestigd op Amazon"
        return "VALIDATE — hype, Amazon nog vlak: klein ads-experiment"
    if has_amazon and "ESTABLISHED" in amazon["phase"]:
        return "MATURE — omzet zonder verse hype: verdedigen"
    return "MONITOR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-amazon", action="store_true")
    ap.add_argument("--nl", action="store_true",
                    help="rank op NL-relevantie (Nederlandstalige video's) "
                         "i.p.v. globale conviction")
    ap.add_argument("--out", default="data/attributes.json")
    args = ap.parse_args()

    tt_rows = load_tiktok()
    if not tt_rows:
        print("No data/tiktok_tags.json — run tiktok_tags.py first.")
        return

    amazon = {} if args.no_amazon else run_amazon()

    rows = []
    discovery = []
    for attr, spec in TAXONOMY.items():
        agg = aggregate_attribute(attr, spec, tt_rows)
        if not agg:
            continue
        if agg.get("discovery_only"):
            discovery.append(agg)
            continue
        agg["hype_phase"] = hype_phase(agg)
        am = amazon.get(attr)
        agg["amazon"] = am
        agg["action"] = combined_phase(agg["hype_phase"], am)
        agg["conviction"] = conviction_score(agg)
        agg["opportunity"] = opportunity(agg)
        rows.append(agg)

    if args.nl:
        rows.sort(key=lambda r: -r.get("nl_est_views", 0))
    else:
        rows.sort(key=lambda r: -r["conviction"])

    print("=" * 100)
    title = ("NL-TRENDING" if args.nl else "trend insights")
    print(f"  TIKTOK → AMAZON ATTRIBUTE BRIDGE — {title}, "
          "joinable to products")
    print("=" * 100)
    print(f"  {'attribute':<18} {'level':<10} {'tiktok views':>12} "
          f"{'NL views':>9} {'NL%':>4} {'vel':>5} {'conv':>5} "
          f"{'hype':<24} {'amazon':<13}")
    print("-" * 100)
    for r in rows:
        am = r["amazon"]
        s = r.get("signals") or {}
        amtxt = (am["phase"].replace(" →", "").strip()[:12] if am
                 else "— (none)")
        vel = f"x{r['velocity']}" if r["velocity"] else "-"
        nlpct = (f"{s['nl_share']:.0%}" if s.get("nl_share") is not None
                 else "-")
        print(f"  {r['attribute']:<18} {r['level']:<10} "
              f"{fmt_int(r['tiktok_views']):>12} "
              f"{fmt_int(r['nl_est_views']):>9} {nlpct:>4} {vel:>5} "
              f"{r['conviction']:>4}% {r['hype_phase']:<24} {amtxt:<13}")
    print("-" * 100)
    print("  NL views = som van per-tag schattingen (tag-totaal x "
          "NL-aandeel van die tag) | NL% = NL-aandeel v.d. harvest")
    print("  conv = conviction: hoeveel ONAFHANKELIJKE signalen elkaar "
          "bevestigen (velocity, saves,\n  creator-breedte, koopintentie, "
          "algoritme-push, versheid) — 1 hete metric kan toeval zijn,\n"
          "  5 bevestigende zelden.")

    print("\n  ACTIONS (cross-platform funnel):")
    for r in rows:
        s = r.get("signals") or {}
        brands = ", ".join(f"{b}({c})" for b, c in r["brands"][:4]) or "—"
        eng = (f", eng {r['engagement']*100:.1f}%"
               if r["engagement"] else "")
        print(f"\n  • {r['attribute'].upper()} [{r['level']}] "
              f"— conviction {r['conviction']}% — {r['action']}")
        print(f"      {r['opportunity']}")
        print(f"      tiktok: {fmt_int(r['tiktok_views'])} views, "
              f"vel {r['velocity']}{eng}")
        if s:
            save = (f"{s['save_rate']*100:.1f}%" if s.get("save_rate")
                    else "-")
            boost = (f"x{s['recency_boost']}" if s.get("recency_boost")
                     else "-")
            print(f"      signalen (n={s['sample_videos']}): "
                  f"save-rate {save} | {s['unique_creators']} creators "
                  f"(top {s['top_author_share']:.0%}) | "
                  f"breakout {s['breakout_share']:.0%} | "
                  f"koopintentie {s['commerce_intent']:.0%} | "
                  f"<30d {s['fresh_share_30d']:.0%} (plays {boost})")
            if s.get("nl_videos"):
                print(f"      NL: {s['nl_videos']} NL-video's "
                      f"({s['nl_share']:.0%} v.d. feed), "
                      f"{fmt_int(s['nl_plays'])} plays, "
                      f"{s['nl_recent_30d']} in laatste 30d "
                      f"→ ±{fmt_int(r['nl_est_views'])} NL-views")
        print(f"      merken die de trend dragen: {brands}")
        print(f"      → Amazon join op: {r['amazon_needles']}")
        if r["amazon"]:
            a = r["amazon"]
            print(f"      Amazon nu: {a['phase'].strip()} "
                  f"(momentum {a['momentum']:+.0%}, {a['asins']} ASINs, "
                  f"{a['rising']} stijgend)")

    if discovery:
        print("\n  DISCOVERY — attributen die alleen als co-hashtag opduiken "
              "(nog niet gemeten; zet op de watchlist):")
        for d in discovery:
            print(f"    {d['attribute']:<18} [{d['level']}] "
                  f"co-occurs in: {', '.join(d['co_occurs_in'][:5])}")

    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    with open(os.path.join(HERE, args.out), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"\n  joinable attribute table -> {args.out}")


if __name__ == "__main__":
    main()
