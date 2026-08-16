"""Trend Radar engine: attribuut-extractie, sales-proxy, momentum en funnel-fasen.

Kernprincipes:
- Detectie op behoefte/format-niveau (signalen), niet op los ASIN-niveau.
- Mid-tail focus (rank MID_TAIL_MIN..MID_TAIL_MAX): daar worden trends geld
  vóórdat ze in top-100 of klassieke marktrapportages zichtbaar zijn.
- Momentum wordt afgezet tegen de categorie-baseline zodat seizoenseffecten
  het signaal niet vervuilen.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field

MID_TAIL_MIN = 300
MID_TAIL_MAX = 3000
TOP_ESTABLISHED = 100
WINDOW = 28  # dagen per vergelijkingsvenster

# Signaal-definities: naam -> zoektermen in titel (lowercase). In productie is dit
# een LLM/embedding-stap; voor de PoC volstaan curated keywords per categorie.
SIGNALS: dict[str, list[str]] = {
    "bond repair": ["bond repair", "bond intense", "probond", "bonding"],
    "scalp serum": ["scalp serum", "scalp treatment"],
    "rosemary oil": ["rosemary oil"],
    "leave-in": ["leave-in"],
    "argan oil": ["argan oil"],
    "volume": ["volume shampoo"],
    "repair kit / multi-step": ["kit", "3-step"],
    "keratin": ["keratin"],
}


def estimate_daily_units(rank: int) -> float:
    """Power-law proxy: rank -> geschatte units/dag.

    Gekalibreerd op de vuistregel dat rank ~100 in een grote categorie enkele
    tientallen units/dag doet en rank ~3000 enkele units. Voor momentum-analyse
    telt de vorm van de curve, niet de absolute kalibratie.
    """
    return 5000.0 / (rank ** 0.85)


@dataclass
class SignalResult:
    name: str
    asin_count: int = 0
    rising_asins: int = 0
    units_prev: float = 0.0
    units_last: float = 0.0
    review_velocity_change: float = 0.0
    top100_asins: int = 0
    examples: list[str] = field(default_factory=list)

    @property
    def momentum(self) -> float:
        if self.units_prev <= 0:
            return 0.0
        return self.units_last / self.units_prev - 1.0


def load_data(data_dir: str):
    asins: dict[str, dict] = {}
    with open(os.path.join(data_dir, "asins.csv")) as fh:
        for row in csv.DictReader(fh):
            asins[row["asin"]] = {"title": row["title"], "price": float(row["price"])}

    observations: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    with open(os.path.join(data_dir, "observations.csv")) as fh:
        for row in csv.DictReader(fh):
            observations[row["asin"]].append(
                (int(row["day"]), int(row["rank"]), int(row["reviews_total"]))
            )
    for series in observations.values():
        series.sort()
    return asins, observations


def extract_signals(title: str) -> list[str]:
    lowered = title.lower()
    return [name for name, needles in SIGNALS.items() if any(n in lowered for n in needles)]


def analyse(data_dir: str) -> tuple[list[SignalResult], float]:
    asins, observations = load_data(data_dir)
    results: dict[str, SignalResult] = {name: SignalResult(name) for name in SIGNALS}
    category_prev = category_last = 0.0

    for asin, meta in asins.items():
        series = observations.get(asin)
        if not series:
            continue
        last_window = series[-WINDOW:]
        prev_window = series[-2 * WINDOW:-WINDOW]
        if len(prev_window) < WINDOW:
            continue

        units_last = sum(estimate_daily_units(r) for _, r, _ in last_window)
        units_prev = sum(estimate_daily_units(r) for _, r, _ in prev_window)
        category_prev += units_prev
        category_last += units_last

        # mid-tail filter voor het early signal (gemiddelde rank in laatste venster)
        avg_rank_last = sum(r for _, r, _ in last_window) / WINDOW
        avg_rank_prev = sum(r for _, r, _ in prev_window) / WINDOW
        in_mid_tail = MID_TAIL_MIN <= avg_rank_prev <= MID_TAIL_MAX or MID_TAIL_MIN <= avg_rank_last <= MID_TAIL_MAX

        reviews_last = last_window[-1][2] - last_window[0][2]
        reviews_prev = prev_window[-1][2] - prev_window[0][2]

        for signal in extract_signals(meta["title"]):
            res = results[signal]
            res.asin_count += 1
            if avg_rank_last <= TOP_ESTABLISHED:
                res.top100_asins += 1
            if not in_mid_tail:
                continue
            res.units_prev += units_prev
            res.units_last += units_last
            if units_last > units_prev * 1.10:
                res.rising_asins += 1
            if reviews_prev > 0:
                res.review_velocity_change += (reviews_last / reviews_prev - 1.0)
            if len(res.examples) < 3:
                res.examples.append(f"{asin} · {meta['title'][:52]} (rank {int(avg_rank_prev)}→{int(avg_rank_last)})")

    baseline = (category_last / category_prev - 1.0) if category_prev else 0.0
    return [r for r in results.values() if r.asin_count > 0], baseline


def classify(res: SignalResult, baseline: float) -> tuple[str, str]:
    """Geeft (funnel-fase, aanbevolen actie)."""
    excess = res.momentum - baseline
    if res.top100_asins > 0 and excess > 0.05:
        return ("ESTABLISHED →", "Trend bereikt de top-100: verdedigen of bewust skippen — entry wordt duur.")
    if excess >= 0.25 and res.rising_asins >= 4:
        return ("PROVEN", "Instapwindow open: signaal op PDP/hero-bullets, Sponsored-terms opschalen, bundel/kit overwegen.")
    if excess >= 0.15 and res.rising_asins >= 2:
        return ("FIRST MONEY", "Vroeg signaal: klein ads-experiment starten + signaal doorzetten naar NPD/assortiment.")
    if excess <= -0.15:
        return ("FADING", "Momentum verdwijnt: creative/budget op deze claim afbouwen, PDP herframen.")
    return ("WATCH", "Nog geen bewezen koopmomentum: monitoren, niet op investeren.")
