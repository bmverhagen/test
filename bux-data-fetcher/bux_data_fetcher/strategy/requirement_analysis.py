from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .stock_profile import StockProfile
from .stock_screener import ScreeningResult, StockRequirements


@dataclass
class RequirementAnalysis:
    """Data-gedreven aanbevelingen op basis van correlatie met dip PnL."""
    recommended: StockRequirements
    correlations: dict[str, float]
    best_bucket_notes: str


def analyze_requirements(
    profiles: list[StockProfile],
    performances: list[dict],
) -> RequirementAnalysis:
    """
    Bepaal optimale drempels via correlatie dip_pnl met profiel-metrics.
    performances: [{dip_pnl, dip_win_rate, dip_expectancy, dip_vs_buyhold, isin}, ...]
    """
    rows = []
    perf_map = {p["isin"]: p for p in performances}
    for prof in profiles:
        perf = perf_map.get(prof.isin, {})
        rows.append({**prof.to_dict(), **perf})

    if not rows:
        return RequirementAnalysis(
            recommended=StockRequirements(),
            correlations={},
            best_bucket_notes="Geen data",
        )

    df = pd.DataFrame(rows)
    target = "dip_pnl_eur" if "dip_pnl_eur" in df.columns else "dip_vs_buyhold_eur"

    metric_cols = [
        "daily_volatility_pct", "annualized_volatility_pct", "avg_true_range_pct",
        "avg_volume", "avg_dollar_volume", "volume_cv",
        "panic_events_per_year", "bounce_after_drop_pct", "pct_bars_in_correction",
        "price_avg", "buyhold_return_pct",
    ]

    correlations = {}
    for col in metric_cols:
        if col in df.columns and target in df.columns and len(df) >= 3:
            corr = df[col].corr(df[target])
            if not np.isnan(corr):
                correlations[col] = float(corr)

    # Winnaars vs verliezers
    if target in df.columns and len(df) >= 2:
        winners = df[df[target] > 0]
        losers = df[df[target] <= 0]
    else:
        winners = df
        losers = pd.DataFrame()

    rec = StockRequirements()

    if len(winners) > 0:
        rec = StockRequirements(
            min_daily_volatility_pct=max(0.5, float(winners["daily_volatility_pct"].quantile(0.25))),
            max_daily_volatility_pct=float(winners["daily_volatility_pct"].quantile(0.75)) * 1.5,
            min_annualized_volatility_pct=max(15, float(winners["annualized_volatility_pct"].quantile(0.25))),
            max_annualized_volatility_pct=float(winners["annualized_volatility_pct"].quantile(0.75)) * 1.5,
            min_atr_pct=max(0.5, float(winners["avg_true_range_pct"].quantile(0.25))),
            max_atr_pct=float(winners["avg_true_range_pct"].quantile(0.75)) * 1.5,
            min_avg_volume=float(winners["avg_volume"].quantile(0.25)),
            min_avg_dollar_volume=float(winners["avg_dollar_volume"].quantile(0.25)),
            max_volume_cv=float(winners["volume_cv"].quantile(0.75)) * 1.2,
            min_panic_events_per_year=max(4, float(winners["panic_events_per_year"].quantile(0.25))),
            min_bounce_after_drop_pct=float(winners["bounce_after_drop_pct"].quantile(0.25)),
            max_pct_bars_in_correction=min(40, float(winners["pct_bars_in_correction"].quantile(0.75)) * 1.2),
            min_price_eur=max(1, float(winners["price_avg"].quantile(0.1))),
            max_price_eur=float(winners["price_avg"].quantile(0.9)) * 2,
            min_dip_expectancy_eur=0.0,
            min_dip_pnl_eur=0.0,
            min_dip_vs_buyhold_eur=0.0,
        )

    notes_parts = []
    if correlations:
        top = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        notes_parts.append(
            "Sterkste correlaties met dip PnL: "
            + ", ".join(f"{k} ({v:+.2f})" for k, v in top)
        )
    if len(winners) and len(losers):
        notes_parts.append(
            f"Winners ({len(winners)}): gem. vol {winners['daily_volatility_pct'].mean():.2f}%, "
            f"paniek/jaar {winners['panic_events_per_year'].mean():.1f}. "
            f"Losers ({len(losers)}): gem. vol {losers['daily_volatility_pct'].mean():.2f}%, "
            f"paniek/jaar {losers['panic_events_per_year'].mean():.1f}."
        )

    return RequirementAnalysis(
        recommended=rec,
        correlations=correlations,
        best_bucket_notes=" | ".join(notes_parts) if notes_parts else "Te weinig data voor correlatie",
    )


def format_screening_table(results: list[ScreeningResult]) -> str:
    lines = [
        "",
        "=" * 100,
        "STOCK SCREENING — Geschiktheid voor Dip Strategie",
        "=" * 100,
        f"{'Ticker':<10} {'Score':>6} {'OK':>4} {'Vol%':>6} {'ATR%':>6} {'Pan/jr':>7} "
        f"{'Bounce%':>8} {'DipPnL':>10} {'OOS Win%':>9} {'vs B&H':>10}",
        "-" * 100,
    ]

    for r in sorted(results, key=lambda x: -x.score):
        p = r.profile
        ticker = (p.ticker or p.isin)[:10]
        ok = "✓" if r.passed else "✗"
        dip_pnl = f"€{r.dip_pnl_eur:+8.2f}" if r.dip_pnl_eur is not None else "       n/a"
        win = f"{r.dip_win_rate_pct:5.1f}" if r.dip_win_rate_pct is not None else "  n/a"
        vs_bh = f"€{r.dip_vs_buyhold_eur:+8.2f}" if r.dip_vs_buyhold_eur is not None else "       n/a"

        lines.append(
            f"{ticker:<10} {r.score:5.1f}% {ok:>4} {p.daily_volatility_pct:6.2f} "
            f"{p.avg_true_range_pct:6.2f} {p.panic_events_per_year:7.1f} "
            f"{p.bounce_after_drop_pct:+8.2f} {dip_pnl} {win} {vs_bh}"
        )

    lines.append("=" * 100)
    return "\n".join(lines)


def format_requirements(req: StockRequirements, analysis: RequirementAnalysis) -> str:
    lines = [
        "",
        "AANBEVOLEN STOCK REQUIREMENTS (train-set, niet voor filtering)",
        "  ⚠ Drempels zijn indicatief — pas/fail gebruikt OOS test metrics",
        "-" * 50,
        f"  Daily volatility:     {req.min_daily_volatility_pct:.1f}% – {req.max_daily_volatility_pct:.1f}%",
        f"  Annualized vol:       {req.min_annualized_volatility_pct:.0f}% – {req.max_annualized_volatility_pct:.0f}%",
        f"  ATR (dag):            {req.min_atr_pct:.1f}% – {req.max_atr_pct:.1f}%",
        f"  Min gem. volume:      {req.min_avg_volume:,.0f}",
        f"  Min dollar volume:    €{req.min_avg_dollar_volume:,.0f}",
        f"  Max volume CV:        {req.max_volume_cv:.1f}",
        f"  Min paniek events/jaar: {req.min_panic_events_per_year:.0f}",
        f"  Min bounce na drop:   {req.min_bounce_after_drop_pct:+.1f}%",
        f"  Max % in correctie:   {req.max_pct_bars_in_correction:.0f}%",
        f"  Prijs range:          €{req.min_price_eur:.0f} – €{req.max_price_eur:.0f}",
        f"  Min OOS expectancy:   €{req.min_dip_expectancy_eur:.2f}",
        f"  Min OOS netto PnL:    €{req.min_dip_pnl_eur:.2f}",
        "",
        f"  {analysis.best_bucket_notes}",
        "-" * 50,
    ]
    return "\n".join(lines)
