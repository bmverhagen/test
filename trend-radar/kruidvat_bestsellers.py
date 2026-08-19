"""
kruidvat_bestsellers.py — geschatte bestseller-rank binnen een Kruidvat-categorie.

Kruidvat publiceert geen units en geen sales-rank. De schapvolgorde is
merchandising. Dit script geeft tóch een antwoord: een RELATIEVE rank
binnen één categorie, uit publieke proxies die wél meetbaar zijn.

Model (geen valse stuks-verkopen):
  1. Review-volume (log)     — reviews mag je alleen na een online
                               aankoop schrijven → trage webshop-proxy
  2. Review-velocity         — Δreviews sinds vorige snapshot (vanaf dag 2)
  3. Bol.com top-10 overlap  — Bol publiceert wél "best verkocht";
                               zelfde lijn in NL is onafhankelijke bevestiging
  4. Rating                  — tie-breaker, geen volume
  5. Anti-merchandising      — hoge schapplaats + weinig reviews =
                               PUSH (launch/actie), geen seller

Output is een 0-100 score + label, geen "347 flessen/week". Eerste
testrun: shampoo-categorie, 20 SKU's van kruidvat.nl (aug 2026).

    python3 kruidvat_bestsellers.py
    python3 kruidvat_bestsellers.py --from-json kruidvat_shampoo_seed.json
"""

import argparse
import json
import math
import os
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "kruidvat_shampoo_seed.json")
DB = os.path.join(HERE, "data", "kruidvat_history.db")


def db_connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS review_snapshots (
        date TEXT NOT NULL,
        ean TEXT NOT NULL,
        name TEXT,
        reviews INTEGER,
        PRIMARY KEY (date, ean))""")
    return con


def prev_reviews(con, today):
    row = con.execute("SELECT MAX(date) FROM review_snapshots WHERE date<?",
                      (today,)).fetchone()
    prev = row[0] if row and row[0] else None
    if not prev:
        return None, {}
    out = {r[0]: r[1] for r in con.execute(
        "SELECT ean, reviews FROM review_snapshots WHERE date=?", (prev,))}
    return prev, out


def score_items(items, velocity):
    """velocity: {ean: Δreviews/dag} of leeg."""
    logs = [math.log1p(max(p.get("reviews") or 0, 0)) for p in items]
    lo, hi = (min(logs), max(logs)) if logs else (0, 1)
    span = (hi - lo) or 1.0
    vels = list(velocity.values()) if velocity else []
    vmax = max(vels) if vels else 0

    out = []
    for p, lg in zip(items, logs):
        reviews = p.get("reviews") or 0
        shelf = p.get("shelf") or 99
        vol = (lg - lo) / span                          # 0-1
        vel = 0.0
        if vmax > 0 and p.get("ean") in velocity:
            vel = max(velocity[p["ean"]], 0) / vmax
        bol = 1.0 if p.get("bolTop10") else 0.0
        rating = ((p.get("rating") or 4.0) - 3.0) / 2.0  # 3→0, 5→1
        rating = max(0.0, min(1.0, rating))

        # merchandising-straf: vooraan zonder reviews = push, geen seller
        push = reviews < 25 and shelf <= 15
        house_boost_only = bool(p.get("houseBrand")) and reviews < 40

        raw = (0.70 * vol) + (0.15 * vel) + (0.10 * bol) + (0.05 * rating)
        if push:
            raw *= 0.25
        if house_boost_only:
            raw *= 0.7
        score = round(100 * raw, 1)

        if push:
            label = "PUSH / LAUNCH"
        elif reviews >= 200 and bol:
            label = "CONFIRMED SELLER"
        elif reviews >= 150:
            label = "ONLINE WORKHORSE"
        elif p.get("houseBrand") and reviews >= 40:
            label = "HUISMERK-VOLUME"
        elif reviews < 40:
            label = "DUN SIGNAAL"
        else:
            label = "WAARSCHIJNLIJK SELLER"

        gap = shelf - 1  # 0 = ook merchandising-#1
        out.append({**p, "score": score, "label": label,
                    "reviewLog": round(lg, 2),
                    "dReviews": velocity.get(p.get("ean") or "", None),
                    "shelfGap": gap})
    out.sort(key=lambda r: (-r["score"], -(r.get("reviews") or 0)))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def brand_profiles(ranked):
    """Digital-shelf profiel per merk binnen deze zoekterm/categorie."""
    total_rev = sum(r.get("reviews") or 0 for r in ranked) or 1
    n = len(ranked) or 1
    by = {}
    for r in ranked:
        b = r.get("brand") or "?"
        t = by.setdefault(b, {"skus": [], "reviews": 0, "shelf_sum": 0,
                              "page1": 0, "best_rank": 99, "best_shelf": 99,
                              "house": False})
        t["skus"].append(r)
        t["reviews"] += r.get("reviews") or 0
        sh = r.get("shelf") or 99
        t["shelf_sum"] += sh
        t["page1"] += 1 if sh <= 20 else 0
        t["best_rank"] = min(t["best_rank"], r.get("rank") or 99)
        t["best_shelf"] = min(t["best_shelf"], sh)
        t["house"] = t["house"] or bool(r.get("houseBrand"))
    out = []
    for b, t in by.items():
        k = len(t["skus"])
        review_share = 100.0 * t["reviews"] / total_rev
        shelf_share = 100.0 * k / n
        gap = review_share - shelf_share
        if gap >= 8:
            verdict = "ONDERSCHAPT"   # meer vraag dan schap
        elif gap <= -8:
            verdict = "OVERSCHAPT"    # meer schap dan vraag
        else:
            verdict = "IN BALANS"
        if t["house"]:
            verdict = "HUISMERK-DRUK"
        out.append({
            "brand": b, "skus": k, "reviews": t["reviews"],
            "reviewShare": round(review_share, 1),
            "shelfShare": round(shelf_share, 1),
            "avgShelf": round(t["shelf_sum"] / k, 1),
            "bestRank": t["best_rank"], "bestShelf": t["best_shelf"],
            "gap": round(gap, 1), "verdict": verdict,
            "topSku": t["skus"][0]["name"],
        })
    out.sort(key=lambda x: -x["reviewShare"])
    return out


def report(ranked, today, prev, query="shampoo", focus=None):
    print()
    print("=" * 96)
    print(f"  KRUIDVAT BESTSELLER-SCHATTING  {today}  "
          f"— relatieve rank binnen categorie (geen units)")
    print("=" * 96)
    print(f"  {'rk':<4} {'schap':>5} {'reviews':>8} {'Δrev':>6} "
          f"{'score':>6}  {'label':<20} product")
    print("-" * 96)
    for r in ranked:
        d = r.get("dReviews")
        ds = f"{d:+.0f}" if d is not None else "  —"
        print(f"  {r['rank']:<4} {r.get('shelf') or '—':>5} "
              f"{r.get('reviews') or 0:>8} {ds:>6} {r['score']:>6.1f}  "
              f"{r['label']:<20} {r['name'][:48]}")
    print("-" * 96)
    mismatch = [r for r in ranked
                if (r.get("shelf") or 99) <= 5 and r["rank"] >= 10]
    hidden = [r for r in ranked
              if r["rank"] <= 3 and (r.get("shelf") or 0) >= 8]
    if hidden:
        print("  Verborgen sellers (hoog review-volume, laag in schap):")
        for r in hidden:
            print(f"    #{r['rank']}  {r['name'][:55]}  "
                  f"(schap {r['shelf']}, {r['reviews']} reviews)")
    if mismatch:
        print("  Schap-push zonder sales-bewijs:")
        for r in mismatch:
            print(f"    schap {r['shelf']}  {r['name'][:55]}  "
                  f"→ geschatte rank #{r['rank']} ({r['label']})")
    print()
    print("  Methode: 70% log(reviews) binnen de cohort + 15% Δreviews "
          "(vanaf snapshot 2) + 10% Bol-top-10\n  + 5% rating. PUSH = "
          "schap ≤15 en <25 reviews. Dit is een rang, geen Nielsen-units.\n"
          "  Reviews = alleen online aankopen; winkelverkoop ontbreekt. "
          "Herhaal wekelijks voor velocity.")
    if not prev:
        print("  Eerste snapshot: velocity nog leeg. Draai volgende week "
              "opnieuw met verse review-tellingen.")

    profiles = brand_profiles(ranked)
    print()
    print("=" * 96)
    print(f"  MERKPROFIEL op zoekterm/categorie «{query}»  "
          f"— waar staat welk merk, en klopt het schap met de vraag?")
    print("=" * 96)
    print(f"  {'merk':<22} {'SKU':>3} {'reviews':>8} {'vraag%':>7} "
          f"{'schap%':>7} {'beste rk':>8} {'beste schap':>11}  oordeel")
    print("-" * 96)
    for p in profiles:
        print(f"  {p['brand']:<22} {p['skus']:>3} {p['reviews']:>8} "
              f"{p['reviewShare']:>6.1f}% {p['shelfShare']:>6.1f}% "
              f"{p['bestRank']:>8} {p['bestShelf']:>11}  {p['verdict']}")
    print("-" * 96)
    print("  vraag% = aandeel van alle reviews in deze lijst (online-koopproxy). "
          "schap% = aandeel SKU's in de cohort.\n  ONDERSCHAPT = meer vraag dan "
          "schap (verborgen seller). OVERSCHAPT = retailer duwt je harder dan "
          "klanten kopen.")

    if focus:
        hit = next((p for p in profiles
                    if p["brand"].lower() == focus.lower()), None)
        print()
        if not hit:
            print(f"  Merk «{focus}» staat niet in deze zoekterm.")
        else:
            print(f"  WAAR STAAT {hit['brand'].upper()} op «{query}»")
            print(f"    {hit['skus']} SKU's · beste geschatte rank #{hit['bestRank']} "
                  f"· beste schapplaats {hit['bestShelf']}")
            print(f"    {hit['reviewShare']:.1f}% van de online-vraag vs "
                  f"{hit['shelfShare']:.1f}% van het schap → {hit['verdict']}")
            print(f"    top-SKU: {hit['topSku']}")
            yours = [r for r in ranked
                     if (r.get("brand") or "").lower() == focus.lower()]
            for r in yours:
                print(f"      schap {r.get('shelf'):>2} → geschatte #{r['rank']:<2}  "
                      f"{r['label']:<20} {r['name'][:42]}")
    return profiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", default=SEED)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--query", default="shampoo",
                    help="zoekterm/categorie-label voor het merkprofiel")
    ap.add_argument("--brand", default=None,
                    help="eigen merk: print 'waar sta ik' op deze zoekterm")
    args = ap.parse_args()

    path = args.from_json if os.path.isabs(args.from_json) \
        else os.path.join(HERE, args.from_json)
    items = json.load(open(path, encoding="utf-8"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    con = db_connect(args.db)
    for p in items:
        key = p.get("ean") or p.get("id") or p["name"]
        p["ean"] = key
        con.execute("INSERT OR REPLACE INTO review_snapshots VALUES (?,?,?,?)",
                    (today, key, p.get("name"), p.get("reviews") or 0))
    con.commit()
    prev, old = prev_reviews(con, today)
    velocity = {}
    if prev:
        for p in items:
            key = p.get("ean") or p.get("id") or p["name"]
            if key in old:
                velocity[key] = (p.get("reviews") or 0) - old[key]

    ranked = score_items(items, velocity)
    profiles = report(ranked, today, prev, query=args.query, focus=args.brand)
    out = os.path.join(HERE, "data", "kruidvat_bestsellers.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"query": args.query, "ranked": ranked,
                   "brands": profiles}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
