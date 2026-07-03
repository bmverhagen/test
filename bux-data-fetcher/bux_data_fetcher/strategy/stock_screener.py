from __future__ import annotations

from dataclasses import dataclass, field

from .stock_profile import StockProfile


@dataclass
class StockRequirements:
    """
    Aanbevolen filters voor aandelen geschikt voor de dip-strategie.
    Gebaseerd op backtest + profiel analyse.
    """

    # Volatiliteit: genoeg beweging voor 4% TP, niet extreem chaotisch
    min_daily_volatility_pct: float = 1.5
    max_daily_volatility_pct: float = 6.0
    min_annualized_volatility_pct: float = 25.0
    max_annualized_volatility_pct: float = 80.0
    min_atr_pct: float = 1.0
    max_atr_pct: float = 5.0

    # Volume & liquiditeit
    min_avg_volume: float = 10_000
    min_avg_dollar_volume: float = 500_000
    max_volume_cv: float = 3.0          # Te spiky volume = onbetrouwbaar

    # Dip-kansen
    min_panic_events_per_year: float = 8.0
    min_bounce_after_drop_pct: float = 0.0   # Positieve mean-reversion
    max_pct_bars_in_correction: float = 25.0  # Niet permanent in downtrend

    # Prijs (Bux fractional OK, maar extreme penny stocks vermijden)
    min_price_eur: float = 5.0
    max_price_eur: float = 500.0

    # Backtest performance (indien beschikbaar) — win rate is netto na fees
    min_dip_win_rate_pct: float = 75.0
    min_dip_trades: int = 5            # Min. trades voor betrouwbare win rate
    min_dip_expectancy_eur: float = 0.0
    min_dip_vs_buyhold_eur: float = 0.0    # Alpha vs passief


@dataclass
class ScreeningResult:
    profile: StockProfile
    passed: bool
    score: float                         # 0-100 geschiktheid
    failures: list[str] = field(default_factory=list)
    dip_pnl_eur: float | None = None
    dip_win_rate_pct: float | None = None
    dip_expectancy_eur: float | None = None
    dip_vs_buyhold_eur: float | None = None


def score_profile(
    profile: StockProfile,
    req: StockRequirements,
    *,
    dip_pnl: float | None = None,
    dip_win_rate: float | None = None,
    dip_trades: int | None = None,
    dip_expectancy: float | None = None,
    dip_vs_buyhold: float | None = None,
) -> ScreeningResult:
    failures: list[str] = []
    points = 0.0
    max_points = 0.0

    checks = [
        (req.min_daily_volatility_pct <= profile.daily_volatility_pct <= req.max_daily_volatility_pct,
         f"daily vol {profile.daily_volatility_pct:.2f}% buiten [{req.min_daily_volatility_pct}, {req.max_daily_volatility_pct}]"),
        (req.min_annualized_volatility_pct <= profile.annualized_volatility_pct <= req.max_annualized_volatility_pct,
         f"ann. vol {profile.annualized_volatility_pct:.1f}% buiten [{req.min_annualized_volatility_pct}, {req.max_annualized_volatility_pct}]"),
        (req.min_atr_pct <= profile.avg_true_range_pct <= req.max_atr_pct,
         f"ATR {profile.avg_true_range_pct:.2f}% buiten [{req.min_atr_pct}, {req.max_atr_pct}]"),
        (profile.avg_volume >= req.min_avg_volume,
         f"avg volume {profile.avg_volume:,.0f} < {req.min_avg_volume:,.0f}"),
        (profile.avg_dollar_volume >= req.min_avg_dollar_volume,
         f"dollar volume {profile.avg_dollar_volume:,.0f} < {req.min_avg_dollar_volume:,.0f}"),
        (profile.volume_cv <= req.max_volume_cv,
         f"volume CV {profile.volume_cv:.2f} > {req.max_volume_cv}"),
        (profile.panic_events_per_year >= req.min_panic_events_per_year,
         f"paniek events {profile.panic_events_per_year:.1f}/jaar < {req.min_panic_events_per_year}"),
        (profile.bounce_after_drop_pct >= req.min_bounce_after_drop_pct,
         f"bounce na drop {profile.bounce_after_drop_pct:.2f}% < {req.min_bounce_after_drop_pct}%"),
        (profile.pct_bars_in_correction <= req.max_pct_bars_in_correction,
         f"{profile.pct_bars_in_correction:.1f}% bars in correctie > {req.max_pct_bars_in_correction}%"),
        (req.min_price_eur <= profile.price_avg <= req.max_price_eur,
         f"prijs €{profile.price_avg:.2f} buiten [{req.min_price_eur}, {req.max_price_eur}]"),
    ]

    for ok, msg in checks:
        max_points += 10
        if ok:
            points += 10
        else:
            failures.append(msg)

    if dip_trades is not None:
        max_points += 10
        if dip_trades >= req.min_dip_trades:
            points += 10
        else:
            failures.append(f"te weinig trades ({dip_trades} < {req.min_dip_trades})")

    if dip_win_rate is not None:
        max_points += 10
        if dip_win_rate >= req.min_dip_win_rate_pct:
            points += 10
        else:
            failures.append(
                f"win rate {dip_win_rate:.1f}% < {req.min_dip_win_rate_pct}% (netto na fees)"
            )

    if dip_expectancy is not None:
        max_points += 10
        if dip_expectancy >= req.min_dip_expectancy_eur:
            points += 10
        else:
            failures.append(f"expectancy €{dip_expectancy:.2f} < €{req.min_dip_expectancy_eur}")

    if dip_vs_buyhold is not None:
        max_points += 10
        if dip_vs_buyhold >= req.min_dip_vs_buyhold_eur:
            points += 10
        else:
            failures.append(f"alpha vs B&H €{dip_vs_buyhold:.2f} < €{req.min_dip_vs_buyhold_eur}")

    score = (points / max_points * 100) if max_points > 0 else 0.0
    passed = len(failures) == 0

    return ScreeningResult(
        profile=profile,
        passed=passed,
        score=score,
        failures=failures,
        dip_pnl_eur=dip_pnl,
        dip_win_rate_pct=dip_win_rate,
        dip_expectancy_eur=dip_expectancy,
        dip_vs_buyhold_eur=dip_vs_buyhold,
    )
