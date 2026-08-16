#!/usr/bin/env python3
"""Draait de Trend Radar en print de wekelijkse digest (PoC)."""

import os

from engine import analyse, classify

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

STAGE_ORDER = {"ESTABLISHED →": 0, "PROVEN": 1, "FIRST MONEY": 2, "WATCH": 3, "FADING": 4}


def pct(x: float) -> str:
    return f"{x * +100:+.0f}%"


def main() -> None:
    if not os.path.exists(os.path.join(DATA_DIR, "observations.csv")):
        raise SystemExit("Geen data gevonden. Draai eerst: python3 generate_demo_data.py")

    results, baseline = analyse(DATA_DIR)
    rows = sorted(results, key=lambda r: (STAGE_ORDER[classify(r, baseline)[0]], -(r.momentum - baseline)))

    print("=" * 78)
    print("TREND RADAR — WEEKLY DIGEST · categorie: Hair · marketplace: amazon.de (demo)")
    print(f"Categorie-baseline (28d vs 28d ervoor): {pct(baseline)} geschatte units")
    print("=" * 78)

    header = f"{'SIGNAAL':<24}{'FASE':<14}{'MOMENTUM*':>10}{'ASINS':>7}{'RISING':>8}{'TOP100':>8}"
    print(header)
    print("-" * len(header))
    for res in rows:
        stage, _ = classify(res, baseline)
        print(f"{res.name:<24}{stage:<14}{pct(res.momentum - baseline):>10}{res.asin_count:>7}{res.rising_asins:>8}{res.top100_asins:>8}")
    print("* momentum = mid-tail unitsgroei van het signaal minus de categorie-baseline\n")

    print("ACTIES DEZE WEEK")
    print("-" * 78)
    for res in rows:
        stage, action = classify(res, baseline)
        if stage == "WATCH":
            continue
        print(f"[{stage}] {res.name} ({pct(res.momentum - baseline)} vs categorie)")
        print(f"   → {action}")
        for example in res.examples[:2]:
            print(f"     · {example}")
        print()


if __name__ == "__main__":
    main()
