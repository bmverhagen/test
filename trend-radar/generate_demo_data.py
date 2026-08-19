#!/usr/bin/env python3
"""Genereert een realistische demo-dataset voor de Trend Radar PoC.

Output:
  data/asins.csv         - ASIN, titel, prijs
  data/observations.csv  - dagelijkse rank + cumulatief reviewaantal per ASIN (120 dagen)

De patronen zijn gemodelleerd naar echte, gedocumenteerde hair-trends:
  - bond repair leave-in  -> sterk stijgend in de mid-tail (PROVEN-patroon)
  - scalp serum           -> stijgend, vroeger stadium (FIRST MONEY-patroon)
  - rosemary oil          -> snel stijgend, hoge review-velocity
  - argan oil (only)      -> dalend (FADING-patroon)
  - volume shampoo        -> vlak
  - klassieke top-sellers -> stabiel in top-100 (baseline / ESTABLISHED)
"""

import csv
import math
import os
import random

random.seed(42)
DAYS = 120
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")


def drift_series(start_rank: float, end_rank: float, noise: float = 0.08) -> list[int]:
    """Rank-verloop van start naar eind met lognormale ruis (rank: lager = beter)."""
    series = []
    for day in range(DAYS):
        t = day / (DAYS - 1)
        # smoothstep zodat de versnelling in de tweede helft zit (zoals echte trends)
        s = t * t * (3 - 2 * t)
        base = start_rank * (end_rank / start_rank) ** s
        rank = max(1, int(base * math.exp(random.gauss(0, noise))))
        series.append(rank)
    return series


ASIN_SPECS = [
    # (aantal, titel-template, prijsband, start_rank_range, eind_rank_range, reviews/dag @rank1000)
    (6, "{brand} Bond Repair Leave-In Treatment {size}ml", (14, 24), (1400, 2600), (300, 700), 3.0),
    (3, "{brand} No.8 Bond Intense Repair Mask {size}ml", (18, 30), (900, 1600), (250, 500), 2.5),
    (4, "{brand} Scalp Serum with Niacinamide {size}ml", (16, 28), (2400, 3000), (800, 1400), 2.0),
    (3, "{brand} Rosemary Oil Hair Growth Scalp Treatment {size}ml", (9, 15), (1800, 2800), (350, 800), 4.0),
    (5, "{brand} Argan Oil Shampoo Classic {size}ml", (7, 12), (500, 900), (1200, 2200), 1.0),
    (4, "{brand} Volume Shampoo Fresh {size}ml", (6, 10), (700, 1300), (700, 1300), 1.0),
    (4, "{brand} Hair Mask Kit Repair & Shine 3-Step", (19, 32), (1600, 2400), (700, 1200), 1.8),
    (3, "{brand} Keratin Smooth Conditioner {size}ml", (8, 13), (400, 800), (450, 850), 1.2),
]

BRANDS = ["Novellia", "Kuralux", "Herbastra", "Vionne", "Tressano", "Lumeya",
          "Capellio", "Nordhaar", "Silkero", "Botanera", "Riva Beauty", "Maneful"]

TOP_SELLERS = [
    ("Classic Anti-Dandruff Shampoo 500ml", 12.99, 25, 45),
    ("Daily Moisture Shampoo & Conditioner Set", 15.99, 40, 70),
    ("Repair & Protect Shampoo 400ml", 9.99, 55, 90),
    # bond-product dat de top-100 binnenkomt (fase 3 -> 4 overgang zichtbaar maken)
    ("ProBond Repair Shampoo Salon Formula 300ml", 21.99, 260, 85),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    asin_rows, obs_rows = [], []
    counter = 1

    def next_asin() -> str:
        nonlocal counter
        asin = f"B0DEMO{counter:04d}"
        counter += 1
        return asin

    for count, template, price_band, start_range, end_range, review_rate in ASIN_SPECS:
        for _ in range(count):
            asin = next_asin()
            title = template.format(brand=random.choice(BRANDS), size=random.choice([100, 150, 200, 250]))
            price = round(random.uniform(*price_band), 2)
            asin_rows.append((asin, title, price))
            ranks = drift_series(random.uniform(*start_range), random.uniform(*end_range))
            reviews = 0.0
            for day, rank in enumerate(ranks):
                # review-instroom schaalt met verkoopsnelheid (~1/rank)
                reviews += review_rate * (1000 / max(rank, 50)) * random.uniform(0.6, 1.4)
                obs_rows.append((asin, day, rank, int(reviews)))

    for title, price, start_rank, end_rank in TOP_SELLERS:
        asin = next_asin()
        asin_rows.append((asin, title, price))
        ranks = drift_series(start_rank, end_rank, noise=0.05)
        reviews = 0.0
        for day, rank in enumerate(ranks):
            reviews += 5.0 * (1000 / max(rank, 20)) * random.uniform(0.8, 1.2)
            obs_rows.append((asin, day, rank, int(reviews)))

    with open(os.path.join(OUT_DIR, "asins.csv"), "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["asin", "title", "price"])
        writer.writerows(asin_rows)

    with open(os.path.join(OUT_DIR, "observations.csv"), "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["asin", "day", "rank", "reviews_total"])
        writer.writerows(obs_rows)

    print(f"Demo-dataset geschreven: {len(asin_rows)} ASINs, {len(obs_rows)} observaties -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
