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
    brand_counter = Counter()
    evidence = []
    matched_tags = []      # directly harvested tags for this attribute
    co_occurs_in = []      # tags where this attr shows up only as co-hashtag

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
        for v in r.get("videos", []):
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
        "velocity": round(velocity, 2) if velocity else None,
        "engagement": round(engagement, 4) if engagement else None,
        "brands": brand_counter.most_common(5),
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
        rows.append(agg)

    rows.sort(key=lambda r: -(r["velocity"] or 0))

    print("=" * 100)
    print("  TIKTOK → AMAZON ATTRIBUTE BRIDGE — trend insights, "
          "joinable to products")
    print("=" * 100)
    print(f"  {'attribute':<18} {'level':<10} {'tiktok views':>12} "
          f"{'vel':>5} {'hype':<26} {'amazon':<14}")
    print("-" * 100)
    for r in rows:
        am = r["amazon"]
        amtxt = (am["phase"].replace(" →", "").strip()[:13] if am
                 else "— (none)")
        vel = f"x{r['velocity']}" if r["velocity"] else "-"
        print(f"  {r['attribute']:<18} {r['level']:<10} "
              f"{fmt_int(r['tiktok_views']):>12} {vel:>5} "
              f"{r['hype_phase']:<26} {amtxt:<14}")
    print("-" * 100)

    print("\n  ACTIONS (cross-platform funnel):")
    for r in rows:
        brands = ", ".join(f"{b}({c})" for b, c in r["brands"][:4]) or "—"
        eng = (f", eng {r['engagement']*100:.1f}%"
               if r["engagement"] else "")
        print(f"\n  • {r['attribute'].upper()} [{r['level']}] — {r['action']}")
        print(f"      tiktok: {fmt_int(r['tiktok_views'])} views, "
              f"vel {r['velocity']}{eng}")
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
