"""
country_demand.py — echte per-land vraag (bijv. Nederlandse views/zoek-
volume) per term, taal-onafhankelijk. Google Trends met geo=<land> meet
wat heel Nederland zoekt — óók Nederlanders die Engelse termen zoeken
("olaplex", "heatless curls"), die bij een taalfilter buiten beeld
blijven. TikTok publiceert geen per-land views; dit is de officiële
per-land databron die dat gat vult.

    python3 country_demand.py --country NL --from-tiktok data/trending_hair_nl_top200.json --limit 80
    python3 country_demand.py --country NL --terms krullen,olaplex,"heatless curls"
    python3 country_demand.py --country DE --terms haarpflege --rising

Hoe de score werkt
------------------
Google Trends normaliseert 0-100 BINNEN één opvraag; losse opvragen zijn
onderling niet vergelijkbaar. Daarom gaat er in elke batch een vast
ANKER mee (default "shampoo") en wordt alles geschaald naar dat anker:

    nl_index = gemiddelde(term, laatste 14d) / gemiddelde(anker, 14d) x 100

Zo is elke term cross-batch vergelijkbaar: nl_index 50 = half zo veel
gezocht als shampoo in Nederland. Daarnaast per term:

    momentum = gemiddelde laatste 14d / gemiddelde 30d ervoor

Met --rising worden ook Google's eigen RISING/BREAKOUT gerelateerde
zoekopdrachten voor de topterms opgehaald: dé bron voor wat er NU in
het land opkomt, ongeacht taal.

Als een TikTok-harvest wordt meegegeven (--from-tiktok) worden de twee
signalen gecombineerd: combined = 50% NL-zoekvraag x momentum + 50%
TikTok trend-score.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from pytrends.request import TrendReq

HERE = os.path.dirname(os.path.abspath(__file__))

# Engelse vocab voor greedy segmentatie van aan-elkaar-geschreven
# hashtags ("heatlesscurls" -> "heatless curls"). Nederlandse compounds
# ("haarverzorging") segmenteren niet volledig en blijven dus intact —
# precies goed, want Nederlanders zoeken ze als één woord.
EN_VOCAB = sorted([
    "hair", "curly", "curl", "curls", "scalp", "heatless", "bond",
    "repair", "care", "mask", "loss", "growth", "oil", "oiling",
    "routine", "tips", "tutorial", "tutorials", "style", "styles",
    "styling", "transformation", "treatment", "dry", "shampoo", "girl",
    "method", "cut", "extensions", "tape", "slick", "back", "bun",
    "wolf", "natural", "healthy", "journey", "products", "community",
    "specialist", "salon", "color", "dye", "goals", "inspo", "wavy",
    "long", "black", "afro", "braids", "braiding", "type4", "keratin",
    "skin", "glass", "barrier", "korean", "glowing", "tok",
], key=len, reverse=True)

SPLIT_OVERRIDES = {
    "curlygirlmethode": "curly girl methode",
    "hairtok": "hairtok",
    "haartok": "haartok",
    "cleantok": "cleantok",
    "skintok": "skintok",
}


def segment(tag):
    """Hashtag -> zoekterm. Volledige greedy segmentatie met Engelse
    vocab; lukt dat niet, dan blijft de tag intact (Nederlands)."""
    t = tag.lower().strip().lstrip("#")
    if t in SPLIT_OVERRIDES:
        return SPLIT_OVERRIDES[t]
    parts, rest = [], t
    while rest:
        hit = next((w for w in EN_VOCAB if rest.startswith(w)), None)
        if not hit:
            return t  # geen volledige Engelse segmentatie -> laat intact
        parts.append(hit)
        rest = rest[len(hit):]
    return " ".join(parts)


def fetch_batch(pt, phrases, anchor, geo, timeframe, retries=3):
    for attempt in range(retries):
        try:
            pt.build_payload(phrases + [anchor], geo=geo,
                             timeframe=timeframe)
            df = pt.interest_over_time()
            return df
        except Exception as e:
            wait = 20 * (attempt + 1)
            print(f"    [retry] {e} — wacht {wait}s", file=sys.stderr)
            time.sleep(wait)
    return None


def score_terms(terms, geo, anchor, timeframe):
    """Per term: index t.o.v. anker (cross-batch vergelijkbaar) en
    momentum (14d vs 30d ervoor)."""
    pt = TrendReq(hl="nl-NL", tz=-60)
    out = {}
    batches = [terms[i:i + 4] for i in range(0, len(terms), 4)]
    for bi, batch in enumerate(batches, 1):
        phrases = [p for _, p in batch]
        print(f"[gtrends {bi}/{len(batches)}] {phrases}", file=sys.stderr)
        df = fetch_batch(pt, phrases, anchor, geo, timeframe)
        if df is None or df.empty:
            for tag, p in batch:
                out[tag] = {"phrase": p, "index": None, "momentum": None}
            continue
        anchor_recent = df[anchor].tail(14).mean() or 1e-9
        for tag, p in batch:
            if p not in df.columns:
                out[tag] = {"phrase": p, "index": None, "momentum": None}
                continue
            recent = df[p].tail(14).mean()
            prior = df[p].iloc[-44:-14].mean()
            out[tag] = {
                "phrase": p,
                "index": round(100 * recent / anchor_recent, 1),
                "momentum": (round(recent / prior, 2) if prior and prior > 0
                             else None),
            }
        time.sleep(2.5)
    return out


def fetch_rising(phrases, geo, timeframe, limit=8):
    """Google's eigen rising/breakout gerelateerde zoekopdrachten in het
    land — wat er NU opkomt, ongeacht taal."""
    pt = TrendReq(hl="nl-NL", tz=-60)
    rising = {}
    for p in phrases[:limit]:
        try:
            pt.build_payload([p], geo=geo, timeframe=timeframe)
            rq = pt.related_queries()
            df = (rq.get(p) or {}).get("rising")
            if df is not None and not df.empty:
                rising[p] = [(row["query"], row["value"])
                             for _, row in df.head(8).iterrows()]
            time.sleep(2.5)
        except Exception as e:
            print(f"    [rising skip] {p}: {e}", file=sys.stderr)
            time.sleep(10)
    return rising


def load_tiktok(path, limit):
    rows = json.load(open(path, encoding="utf-8"))
    # neem de best scorende NL-termen ÉN de globale (0-score) tags: die
    # laatste zijn juist waar de taalfilter blind voor was.
    with_signal = [r for r in rows if r["trendScore"] > 0]
    zero = [r for r in rows if r["trendScore"] == 0]
    n_zero = min(len(zero), max(10, limit // 3))
    picked = with_signal[:limit - n_zero] + zero[:n_zero]
    return {r["term"]: r["trendScore"] for r in picked}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="NL")
    ap.add_argument("--terms", default=None,
                    help="komma-gescheiden termen/hashtags")
    ap.add_argument("--from-tiktok", default=None,
                    help="pad naar trending_*.json van trending.py")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--anchor", default="shampoo",
                    help="ankerterm voor cross-batch normalisatie")
    ap.add_argument("--timeframe", default="today 3-m")
    ap.add_argument("--rising", action="store_true",
                    help="haal ook Google's rising/breakout queries op")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    geo = args.country.upper()
    tiktok_scores = {}
    if args.terms:
        tags = [t.strip() for t in args.terms.split(",") if t.strip()]
    elif args.from_tiktok:
        tiktok_scores = load_tiktok(args.from_tiktok, args.limit)
        tags = list(tiktok_scores)
    else:
        sys.exit("geef --terms of --from-tiktok")
    tags = tags[:args.limit]

    terms = [(t, segment(t)) for t in tags]
    # dedupliceer op zoekterm (bv. hairoil en haarolie blijven apart,
    # maar identieke frasen niet dubbel opvragen)
    seen, uniq = set(), []
    for tag, p in terms:
        if p in seen:
            continue
        seen.add(p)
        uniq.append((tag, p))

    scores = score_terms(uniq, geo, args.anchor, args.timeframe)

    rows = []
    for tag, s in scores.items():
        idx = s["index"]
        mom = s["momentum"]
        tt = tiktok_scores.get(tag)
        combined = None
        if idx is not None:
            g = min(idx, 100) * (min(mom, 3.0) / 1.0 if mom else 1.0)
            g = min(g, 100)
            combined = (round(0.5 * g + 0.5 * tt) if tt is not None
                        else round(g))
        # groot + vlak = evergreen (bv. "kapper"): altijd veel gezocht,
        # maar geen trend — nooit als stijger presenteren.
        if idx is not None and idx >= 30 and mom and 0.85 <= mom <= 1.15:
            label = "EVERGREEN"
        elif mom and mom > 1.15:
            label = "STIJGER"
        elif mom and mom < 0.85:
            label = "DALER"
        else:
            label = "stabiel" if idx else "-"
        rows.append({"term": tag, "phrase": s["phrase"],
                     "nl_index": idx, "momentum": mom,
                     "tiktok_score": tt, "combined": combined,
                     "label": label})
    rows.sort(key=lambda r: -(r["combined"] or -1))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print()
    print("=" * 96)
    print(f"  ECHTE {geo}-VRAAG PER TERM — Google Trends geo={geo} "
          f"(taal-onafhankelijk) | anker: {args.anchor} | {now}")
    print("=" * 96)
    print(f"  {'#':>3} {'term':<24} {'zoekterm':<22} {'index':>6} "
          f"{'momentum':>9} {'tiktok':>7} {'combined':>9} {'label':<10}")
    print("-" * 96)
    for i, r in enumerate(rows, 1):
        idx = f"{r['nl_index']:.0f}" if r["nl_index"] is not None else "-"
        mom = f"x{r['momentum']}" if r["momentum"] else "-"
        tt = f"{r['tiktok_score']}%" if r["tiktok_score"] is not None \
            else "-"
        cb = f"{r['combined']}%" if r["combined"] is not None else "-"
        print(f"  {i:>3} #{r['term']:<23} {r['phrase']:<22} {idx:>6} "
              f"{mom:>9} {tt:>7} {cb:>9} {r['label']:<10}")
    print("-" * 96)
    print(f"  index = zoekvolume in {geo} t.o.v. '{args.anchor}' (=100), "
          f"laatste 14d | momentum = 14d vs 30d ervoor\n"
          f"  combined = 50% {geo}-zoekvraag x momentum + 50% TikTok "
          f"trend-score")

    decliners = sorted(
        [r for r in rows
         if r["momentum"] and r["momentum"] <= 0.9
         and (r["nl_index"] or 0) >= 2],
        key=lambda r: r["momentum"])
    if decliners:
        print(f"\n  DALERS — zoekvraag in {geo} krimpt (momentum <= 0.9, "
              f"met relevante omvang):")
        for r in decliners:
            print(f"    {r['term']:<24} index {r['nl_index']:>5} | "
                  f"momentum x{r['momentum']} "
                  f"({(1 - r['momentum']):.0%} minder dan de 30d ervoor)")

    if args.rising:
        top_phrases = [r["phrase"] for r in rows
                       if r["nl_index"] and r["nl_index"] > 2][:8]
        rising = fetch_rising(top_phrases, geo, args.timeframe)
        if rising:
            print(f"\n  RISING/BREAKOUT ZOEKOPDRACHTEN IN {geo} "
                  f"(Google's eigen stijgers, alle talen):")
            for p, qs in rising.items():
                items = ", ".join(
                    f"{q} ({'BREAKOUT' if v >= 5000 else f'+{v}%'})"
                    for q, v in qs[:6])
                print(f"    {p}: {items}")

    out = args.out or f"data/demand_{geo.lower()}.json"
    os.makedirs(os.path.join(HERE, os.path.dirname(out)) or ".",
                exist_ok=True)
    with open(os.path.join(HERE, out), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    csv_path = os.path.join(HERE, out).replace(".json", ".csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "term", "zoekterm", f"{geo.lower()}_index",
                    "momentum", "tiktok_score", "combined", "label"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["term"], r["phrase"], r["nl_index"],
                        r["momentum"], r["tiktok_score"], r["combined"],
                        r["label"]])
    print(f"\n  data -> {out} + {os.path.basename(csv_path)}")


if __name__ == "__main__":
    main()
