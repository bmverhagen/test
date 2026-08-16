"""Long-tail momentum per micropatroon-cluster.

Focus expliciet NIET op top-100 bestsellers: momentum wordt alleen gemeten
op ASINs die (gemiddeld) in de long-tail zitten. Dat is waar opkomende
attributen eerst geld trekken zonder al in marktrapportages te staan.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field

from cluster import MicroPattern, discover_clusters
from extract import build_phrase_index

# Long-tail band: dieper dan klassieke mid-tail / bestsellers.
LONG_TAIL_MIN = 1500
LONG_TAIL_MAX = 25000
TOP_EXCLUDE = 300  # alles boven top-300 telt niet mee als early signal
WINDOW = 28


def estimate_daily_units(rank: int) -> float:
    """Power-law rank → units/dag. Vorm telt voor momentum, niet absolute €."""
    return 5000.0 / (max(rank, 1) ** 0.85)


@dataclass
class ClusterMomentum:
    cluster: MicroPattern
    longtail_asins: int = 0
    rising_asins: int = 0
    falling_asins: int = 0
    units_prev: float = 0.0
    units_last: float = 0.0
    review_velocity_change: float = 0.0
    avg_rank_last: float = 0.0
    examples: list[str] = field(default_factory=list)

    @property
    def momentum(self) -> float:
        if self.units_prev <= 0:
            return 0.0
        return self.units_last / self.units_prev - 1.0

    @property
    def excess(self) -> float:
        """Gevuld na analyse met baseline-subtractie."""
        return getattr(self, "_excess", self.momentum)

    @excess.setter
    def excess(self, value: float) -> None:
        self._excess = value


def load_data(data_dir: str):
    asins: dict[str, dict] = {}
    with open(os.path.join(data_dir, "asins.csv")) as fh:
        for row in csv.DictReader(fh):
            asins[row["asin"]] = {
                "title": row["title"],
                "price": float(row["price"]),
            }

    observations: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    with open(os.path.join(data_dir, "observations.csv")) as fh:
        for row in csv.DictReader(fh):
            observations[row["asin"]].append(
                (int(row["day"]), int(row["rank"]), int(row["reviews_total"]))
            )
    for series in observations.values():
        series.sort()
    return asins, observations


def classify(m: ClusterMomentum) -> tuple[str, str]:
    """(fase, actie) voor een micropatroon in de long-tail."""
    excess = m.excess
    if m.longtail_asins < 3:
        return ("NOISE", "Te weinig long-tail ASINs — nog geen cluster-signaal.")
    if excess >= 0.35 and m.rising_asins >= 4:
        return (
            "EXPLODING",
            "Sterk long-tail micropatroon: claim in NPD/PDP meenemen, Sponsored-tests op clusterphrases.",
        )
    if excess >= 0.18 and m.rising_asins >= 2:
        return (
            "RISING",
            "Opkomend attribuut-cluster: klein ads-experiment + assortiment checken op whitespace.",
        )
    if excess <= -0.20 and m.falling_asins >= 2:
        return (
            "DECLINING",
            "Long-tail vraag zakt: creative/budget op deze claim afbouwen, PDP herframen.",
        )
    if excess <= -0.35:
        return ("FADING", "Micropatroon koelt hard af — deprioriteren.")
    return ("WATCH", "Nog geen bewezen long-tail momentum — monitoren.")


def analyse(
    data_dir: str,
    *,
    min_df: int = 3,
    min_jaccard: float = 0.28,
) -> tuple[list[ClusterMomentum], float, list[MicroPattern]]:
    asins, observations = load_data(data_dir)
    phrases = build_phrase_index(asins, min_df=min_df)
    clusters = discover_clusters(phrases, min_jaccard=min_jaccard, min_asins=min_df)

    # Categorie-baseline over alle ASINs met genoeg historie
    category_prev = category_last = 0.0
    asin_windows: dict[str, dict] = {}

    for asin, meta in asins.items():
        series = observations.get(asin)
        if not series or len(series) < 2 * WINDOW:
            continue
        last_window = series[-WINDOW:]
        prev_window = series[-2 * WINDOW : -WINDOW]
        units_last = sum(estimate_daily_units(r) for _, r, _ in last_window)
        units_prev = sum(estimate_daily_units(r) for _, r, _ in prev_window)
        category_prev += units_prev
        category_last += units_last
        avg_rank_last = sum(r for _, r, _ in last_window) / WINDOW
        avg_rank_prev = sum(r for _, r, _ in prev_window) / WINDOW
        reviews_last = last_window[-1][2] - last_window[0][2]
        reviews_prev = prev_window[-1][2] - prev_window[0][2]
        asin_windows[asin] = {
            "title": meta["title"],
            "units_last": units_last,
            "units_prev": units_prev,
            "avg_rank_last": avg_rank_last,
            "avg_rank_prev": avg_rank_prev,
            "reviews_last": reviews_last,
            "reviews_prev": reviews_prev,
        }

    baseline = (category_last / category_prev - 1.0) if category_prev else 0.0
    results: list[ClusterMomentum] = []

    for cluster in clusters:
        cm = ClusterMomentum(cluster=cluster)
        rank_acc = 0.0
        for asin in cluster.asins:
            w = asin_windows.get(asin)
            if not w:
                continue
            # Long-tail filter: ASIN moet in de long-tail band zitten (nu of vorig venster)
            in_long_tail = (
                LONG_TAIL_MIN <= w["avg_rank_prev"] <= LONG_TAIL_MAX
                or LONG_TAIL_MIN <= w["avg_rank_last"] <= LONG_TAIL_MAX
            )
            # Top-300 uitsluiten als early-signal bron
            if w["avg_rank_last"] < TOP_EXCLUDE and w["avg_rank_prev"] < TOP_EXCLUDE:
                continue
            if not in_long_tail:
                continue

            cm.longtail_asins += 1
            cm.units_prev += w["units_prev"]
            cm.units_last += w["units_last"]
            rank_acc += w["avg_rank_last"]
            if w["units_last"] > w["units_prev"] * 1.10:
                cm.rising_asins += 1
            elif w["units_last"] < w["units_prev"] * 0.90:
                cm.falling_asins += 1
            if w["reviews_prev"] > 0:
                cm.review_velocity_change += w["reviews_last"] / w["reviews_prev"] - 1.0
            if len(cm.examples) < 3:
                cm.examples.append(
                    f"{asin} · {w['title'][:56]} "
                    f"(rank {int(w['avg_rank_prev'])}→{int(w['avg_rank_last'])})"
                )

        if cm.longtail_asins:
            cm.avg_rank_last = rank_acc / cm.longtail_asins
        cm.excess = cm.momentum - baseline
        results.append(cm)

    results.sort(key=lambda r: (-r.excess, -r.longtail_asins))
    return results, baseline, clusters
