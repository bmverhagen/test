#!/usr/bin/env python3
"""Genereert een long-tail demo-catalogus met plantbare micropatronen.

Doel: de discovery-engine moet ZONDER curated taxonomie clusters terugvinden
zoals "rice water · fermented", "silk protein · heat protect", en dalers
zoals "charcoal detox". Bestsellers in top-100 zitten erin als ruis die
uitgefilterd moet worden.
"""

from __future__ import annotations

import csv
import math
import os
import random

random.seed(7)
DAYS = 120
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")

BRANDS = [
    "Novellia", "Kuralux", "Herbastra", "Vionne", "Tressano", "Lumeya",
    "Capellio", "Nordhaar", "Silkero", "Botanera", "Aurelia", "Driftwood",
    "Pebbly", "Solara", "Nimbus", "Oriva", "Riva", "Maneful",
]


def drift_series(start_rank: float, end_rank: float, noise: float = 0.10) -> list[int]:
    series = []
    for day in range(DAYS):
        t = day / (DAYS - 1)
        s = t * t * (3 - 2 * t)  # smoothstep: acceleratie in 2e helft
        base = start_rank * (end_rank / start_rank) ** s
        rank = max(1, int(base * math.exp(random.gauss(0, noise))))
        series.append(rank)
    return series


# (count, title_template, price_band, start_rank, end_rank, reviews/dag@1000, pattern_tag)
# pattern_tag is alleen voor onze eigen checks — de engine ziet hem niet.
SPECS = [
    # RISING micropatronen (long-tail → mid/long) — multi-phrase zodat clustering werkt
    (7, "{b} Fermented Rice Water Hair Rinse {s}ml", (11, 19), (9000, 14000), (2200, 3800), 2.4, "rice_water"),
    (5, "{b} Rice Water Fermented Scalp Treatment {s}ml", (13, 22), (8000, 12000), (2000, 3500), 2.2, "rice_water"),
    (6, "{b} Silk Protein Heat Protect Spray {s}ml", (10, 18), (7000, 11000), (1800, 3200), 2.0, "silk_heat"),
    (4, "{b} Heat Protect Silk Protein Mist Leave-On {s}ml", (12, 20), (6500, 10000), (1700, 3000), 1.9, "silk_heat"),
    (6, "{b} Exfoliating Scalp Scrub Detox {s}ml", (14, 24), (10000, 16000), (2800, 4500), 1.8, "scalp_scrub"),
    (4, "{b} Scalp Scrub Exfoliating Sugar Crystals {s}g", (9, 15), (9500, 15000), (3000, 5000), 1.7, "scalp_scrub"),
    (5, "{b} Apple Cider Vinegar Clarifying Rinse {s}ml", (8, 14), (7500, 12000), (2500, 4200), 2.1, "acv"),
    (3, "{b} Clarifying Apple Cider Vinegar Hair Rinse {s}ml", (8, 13), (8000, 13000), (2700, 4500), 2.0, "acv"),
    # Single-attribute riser die als singleton-cluster mag overleven
    (5, "{b} Blue Tansy Soothing Hair Oil {s}ml", (15, 26), (8500, 13000), (2400, 4000), 1.6, "blue_tansy"),
    # DECLINING micropatronen (waren mid-tail, zakken dieper weg)
    (6, "{b} Charcoal Detox Shampoo Deep Clean {s}ml", (7, 12), (1800, 2800), (7000, 12000), 0.9, "charcoal"),
    (4, "{b} Detox Charcoal Clay Hair Mask {s}ml", (9, 15), (2000, 3200), (8000, 13000), 0.8, "charcoal"),
    (5, "{b} Biotin Gummies Hair Growth 60 Count", (10, 16), (1600, 2500), (6000, 11000), 1.0, "biotin_gummies"),
    (3, "{b} Hair Growth Biotin Gummies Vegan", (11, 17), (1700, 2600), (6500, 11500), 0.9, "biotin_gummies"),
    # STABLE long-tail noise (geen sterk micropatroon)
    (8, "{b} Moisture Shampoo Everyday {s}ml", (5, 9), (4000, 7000), (4000, 7000), 1.0, "noise"),
    (6, "{b} Repair Conditioner Smooth {s}ml", (6, 10), (3500, 6500), (3500, 6500), 1.0, "noise"),
    (5, "{b} Curl Cream Define Soft Hold {s}ml", (8, 14), (5000, 9000), (4800, 8800), 1.1, "noise"),
    # Extra rising classic die discovery ook zonder taxonomie moet vinden
    (5, "{b} Rosemary Oil Hair Growth Drops {s}ml", (9, 15), (6000, 10000), (1600, 2800), 2.5, "rosemary"),
]

TOP_SELLERS = [
    ("Classic Anti-Dandruff Shampoo 500ml", 12.99, 20, 40),
    ("Daily Moisture Shampoo & Conditioner Duo", 15.99, 35, 60),
    ("Repair & Protect Shampoo 400ml", 9.99, 50, 85),
    ("Color Care Conditioner 300ml", 11.49, 70, 95),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    asin_rows: list[tuple[str, str, float]] = []
    obs_rows: list[tuple[str, int, int, int]] = []
    counter = 1

    def next_asin() -> str:
        nonlocal counter
        asin = f"B0LT{counter:05d}"
        counter += 1
        return asin

    for count, template, price_band, start_range, end_range, review_rate, _tag in SPECS:
        for _ in range(count):
            asin = next_asin()
            title = template.format(b=random.choice(BRANDS), s=random.choice([50, 100, 150, 200, 250]))
            price = round(random.uniform(*price_band), 2)
            asin_rows.append((asin, title, price))
            ranks = drift_series(random.uniform(*start_range), random.uniform(*end_range))
            reviews = 0.0
            for day, rank in enumerate(ranks):
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
        w = csv.writer(fh)
        w.writerow(["asin", "title", "price"])
        w.writerows(asin_rows)

    with open(os.path.join(OUT_DIR, "observations.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["asin", "day", "rank", "reviews_total"])
        w.writerows(obs_rows)

    print(
        f"Long-tail demo: {len(asin_rows)} ASINs, {len(obs_rows)} observaties → {OUT_DIR}/"
    )


if __name__ == "__main__":
    main()
