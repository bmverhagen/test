#!/usr/bin/env python3
"""CLI: ontdek micropatronen in de Amazon long-tail en print rising/declining digest."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from momentum import analyse, classify

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
REPORTS_DIR = os.path.join(HERE, "reports")

STAGE_ORDER = {
    "EXPLODING": 0,
    "RISING": 1,
    "WATCH": 2,
    "DECLINING": 3,
    "FADING": 4,
    "NOISE": 5,
}


def pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon long-tail micropatroon radar")
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--min-df", type=int, default=3)
    parser.add_argument("--min-jaccard", type=float, default=0.28)
    parser.add_argument("--json-out", default=os.path.join(REPORTS_DIR, "micropatterns.json"))
    args = parser.parse_args()

    if not os.path.exists(os.path.join(args.data_dir, "observations.csv")):
        raise SystemExit("Geen data. Draai eerst: python3 generate_longtail_demo.py")

    results, baseline, clusters = analyse(
        args.data_dir, min_df=args.min_df, min_jaccard=args.min_jaccard
    )
    ranked = sorted(
        results,
        key=lambda r: (STAGE_ORDER[classify(r)[0]], -r.excess, -r.longtail_asins),
    )

    print("=" * 86)
    print("MICROPATRONEN — Amazon long-tail attribuut-clusters (auto-discovery)")
    print(f"Categorie-baseline (28d vs 28d): {pct(baseline)} geschatte units")
    print(f"Ontdekte clusters: {len(clusters)} · long-tail band rank {1500}–{25000}")
    print("=" * 86)

    header = (
        f"{'CLUSTER':<36}{'FASE':<12}{'MOM*':>7}{'LT':>5}"
        f"{'↑':>4}{'↓':>4}{'PHRASES':>8}"
    )
    print(header)
    print("-" * len(header))

    by_stage: dict[str, list] = defaultdict(list)
    payload = []
    for res in ranked:
        stage, action = classify(res)
        by_stage[stage].append((res, action))
        label = res.cluster.label[:34]
        print(
            f"{label:<36}{stage:<12}{pct(res.excess):>7}"
            f"{res.longtail_asins:>5}{res.rising_asins:>4}{res.falling_asins:>4}"
            f"{len(res.cluster.phrases):>8}"
        )
        payload.append(
            {
                "cluster_id": res.cluster.cluster_id,
                "label": res.cluster.label,
                "phrases": res.cluster.phrases,
                "cohesion": round(res.cluster.cohesion, 3),
                "asin_count": res.cluster.asin_count,
                "longtail_asins": res.longtail_asins,
                "rising_asins": res.rising_asins,
                "falling_asins": res.falling_asins,
                "momentum": round(res.momentum, 4),
                "excess_vs_baseline": round(res.excess, 4),
                "avg_rank_last": round(res.avg_rank_last, 1),
                "stage": stage,
                "action": action,
                "examples": res.examples,
            }
        )

    print("* mom = long-tail unitsgroei van het cluster minus categorie-baseline\n")

    print("RISING / EXPLODING — opkomende micropatronen")
    print("-" * 86)
    interesting = by_stage["EXPLODING"] + by_stage["RISING"]
    if not interesting:
        print("  (geen)")
    for res, action in interesting:
        print(f"[{classify(res)[0]}] {res.cluster.label} ({pct(res.excess)} vs cat)")
        print(f"   phrases: {', '.join(res.cluster.phrases[:6])}")
        print(f"   → {action}")
        for ex in res.examples[:2]:
            print(f"     · {ex}")
        print()

    print("DECLINING / FADING — minder interessant / afkoelend")
    print("-" * 86)
    cool = by_stage["DECLINING"] + by_stage["FADING"]
    if not cool:
        print("  (geen)")
    for res, action in cool:
        print(f"[{classify(res)[0]}] {res.cluster.label} ({pct(res.excess)} vs cat)")
        print(f"   phrases: {', '.join(res.cluster.phrases[:6])}")
        print(f"   → {action}")
        for ex in res.examples[:2]:
            print(f"     · {ex}")
        print()

    os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
    with open(args.json_out, "w") as fh:
        json.dump(
            {
                "baseline": baseline,
                "cluster_count": len(clusters),
                "micropatterns": payload,
            },
            fh,
            indent=2,
        )
    print(f"JSON → {args.json_out}")


if __name__ == "__main__":
    main()
