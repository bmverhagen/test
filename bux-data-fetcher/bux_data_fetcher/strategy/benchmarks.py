from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from .backtest import BacktestEngine, BacktestResult
from .config import StrategyConfig
from .signals import enrich_bars, mark_drop_events
from .trades import (
    ClosedTrade,
    ExitReason,
    calc_net_pnl,
    calc_shares,
    should_exit,
)


def _is_dip_zone(row: pd.Series, config: StrategyConfig) -> bool:
    """
    Bars waar geen random entry mag: actieve paniek/correctie.
    Dip-strategie entry-venster (reversal na drop) blijft wél beschikbaar voor random
    als de correctie voorbij is — maar tijdens de daling zelf niet.
    """
    if row.get("panic_drop", False):
        return True
    if float(row.get("drop_pct", 0)) <= -config.min_drop_pct:
        return True
    return False


def run_buy_and_hold(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    *,
    isin: str = "",
    name: str = "",
    ticker: str = "",
) -> BacktestResult:
    """Koop op eerste bar, houd tot einde, zelfde positie en fees."""
    if df.empty or len(df) < 2:
        return BacktestResult(config=cfg)

    entry_price = float(df.iloc[0]["close"])
    exit_price = float(df.iloc[-1]["close"])
    shares = calc_shares(cfg.position_eur, entry_price, cfg.buy_fee_eur)
    if shares <= 0:
        return BacktestResult(config=cfg)

    gross, fees, net = calc_net_pnl(
        shares, entry_price, exit_price, cfg.buy_fee_eur, cfg.sell_fee_eur
    )
    trade = ClosedTrade(
        isin=isin,
        name=name,
        ticker=ticker,
        entry_time=df.index[0],
        exit_time=df.index[-1],
        entry_price=entry_price,
        exit_price=exit_price,
        shares=shares,
        gross_pnl_eur=gross,
        fees_eur=fees,
        net_pnl_eur=net,
        net_pnl_pct=(net / cfg.position_eur) * 100,
        hold_bars=len(df) - 1,
        exit_reason=ExitReason.END_OF_DATA,
        drop_pct=0.0,
    )
    return BacktestResult(trades=[trade], config=cfg)


def _valid_non_dip_indices(enriched: pd.DataFrame, cfg: StrategyConfig) -> list[int]:
    max_entry = max(0, len(enriched) - cfg.max_hold_bars - 2)
    return [
        i for i, (_, row) in enumerate(enriched.iterrows())
        if i <= max_entry and not _is_dip_zone(row, cfg)
    ]


def run_random_baseline(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    *,
    target_trades: int,
    isin: str = "",
    name: str = "",
    ticker: str = "",
    seed: int = 42,
    enriched: pd.DataFrame | None = None,
) -> BacktestResult:
    """
    Zelfde aantal trades als dip-strategie, random instapmomenten buiten dip-vensters.
    Zelfde positiegrootte, fees, TP/SL en max hold.
    """
    if df.empty or len(df) < 30 or target_trades <= 0:
        return BacktestResult(config=cfg)

    if enriched is None:
        enriched = mark_drop_events(enrich_bars(df, cfg), cfg)

    valid = _valid_non_dip_indices(enriched, cfg)
    rng = random.Random(seed)

    take_profit = cfg.effective_take_profit_pct()
    trades: list[ClosedTrade] = []

    # Verdeel timeline in N segmenten → 1 random entry per segment (buiten dip)
    n = target_trades
    total = len(enriched)
    bucket = max(1, total // max(n, 1))
    entry_candidates: list[int] = []

    for b in range(n):
        start_i = b * bucket
        end_i = min((b + 1) * bucket, total - cfg.max_hold_bars - 1)
        bucket_valid = [i for i in valid if start_i <= i < end_i]
        if bucket_valid:
            entry_candidates.append(rng.choice(bucket_valid))
        elif valid:
            entry_candidates.append(min(valid, key=lambda i: abs(i - (start_i + end_i) // 2)))

    entry_candidates = sorted(set(entry_candidates))
    next_allowed = 0

    for entry_i in entry_candidates:
        if entry_i < next_allowed or entry_i >= len(enriched):
            continue

        entry_ts = enriched.index[entry_i]
        entry_price = float(enriched.iloc[entry_i]["close"])
        shares = calc_shares(cfg.position_eur, entry_price, cfg.buy_fee_eur)
        if shares <= 0:
            continue

        exit_i = None
        exit_reason = ExitReason.END_OF_DATA
        exit_price = entry_price

        for j in range(entry_i + 1, len(enriched)):
            price = float(enriched.iloc[j]["close"])
            hold_bars = j - entry_i
            exit_now, reason = should_exit(
                entry_price=entry_price,
                current_price=price,
                hold_bars=hold_bars,
                take_profit_pct=take_profit,
                stop_loss_pct=cfg.stop_loss_pct,
                max_hold_bars=cfg.max_hold_bars,
            )
            if exit_now and reason:
                exit_i = j
                exit_price = price
                exit_reason = reason
                break

        if exit_i is None:
            continue

        hold_bars = exit_i - entry_i
        gross, fees, net = calc_net_pnl(
            shares, entry_price, exit_price, cfg.buy_fee_eur, cfg.sell_fee_eur
        )
        trades.append(
            ClosedTrade(
                isin=isin,
                name=name,
                ticker=ticker,
                entry_time=entry_ts,
                exit_time=enriched.index[exit_i],
                entry_price=entry_price,
                exit_price=exit_price,
                shares=shares,
                gross_pnl_eur=gross,
                fees_eur=fees,
                net_pnl_eur=net,
                net_pnl_pct=(net / cfg.position_eur) * 100,
                hold_bars=hold_bars,
                exit_reason=exit_reason,
                drop_pct=0.0,
            )
        )
        next_allowed = exit_i + cfg.cooldown_bars

    return BacktestResult(trades=trades, signals_df=enriched, config=cfg)


def run_random_baseline_monte_carlo(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    *,
    target_trades: int,
    runs: int = 50,
    base_seed: int = 42,
    **kwargs,
) -> BacktestResult:
    """Gemiddelde random baseline over meerdere seeds."""
    if target_trades <= 0:
        return BacktestResult(config=cfg)

    enriched = mark_drop_events(enrich_bars(df, cfg), cfg)
    all_trade_pnls: list[list[float]] = []

    for run in range(runs):
        result = run_random_baseline(
            df,
            cfg,
            target_trades=target_trades,
            seed=base_seed + run,
            enriched=enriched,
            **kwargs,
        )
        all_trade_pnls.append([t.net_pnl_eur for t in result.trades])

    if not all_trade_pnls:
        return BacktestResult(config=cfg)

    # Neem median run (meest representatief)
    totals = [sum(pnls) for pnls in all_trade_pnls]
    median_idx = sorted(range(len(totals)), key=lambda i: totals[i])[len(totals) // 2]

    return run_random_baseline(
        df,
        cfg,
        target_trades=target_trades,
        seed=base_seed + median_idx,
        enriched=enriched,
        **kwargs,
    )


@dataclass
class InstrumentComparison:
    isin: str
    ticker: str
    name: str
    dip_trades: int
    dip_pnl_eur: float
    dip_return_pct: float
    buyhold_pnl_eur: float
    buyhold_return_pct: float
    random_trades: int
    random_pnl_eur: float
    random_return_pct: float


def compare_instrument(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    *,
    isin: str,
    name: str,
    ticker: str,
    news_articles: list | None = None,
    random_seed: int = 42,
    random_runs: int = 1,
) -> InstrumentComparison:
    dip_result = BacktestEngine(cfg).run(
        df, isin=isin, name=name, ticker=ticker, news_articles=news_articles
    )
    bh_result = run_buy_and_hold(df, cfg, isin=isin, name=name, ticker=ticker)

    target = len(dip_result.trades)
    if random_runs > 1:
        random_result = run_random_baseline_monte_carlo(
            df, cfg, target_trades=target, isin=isin, name=name, ticker=ticker,
            runs=random_runs, base_seed=random_seed,
        )
    else:
        random_result = run_random_baseline(
            df, cfg, target_trades=target, isin=isin, name=name, ticker=ticker,
            seed=random_seed,
        )

    dip_pnl = sum(t.net_pnl_eur for t in dip_result.trades)
    bh_pnl = sum(t.net_pnl_eur for t in bh_result.trades)
    rnd_pnl = sum(t.net_pnl_eur for t in random_result.trades)

    return InstrumentComparison(
        isin=isin,
        ticker=ticker,
        name=name,
        dip_trades=len(dip_result.trades),
        dip_pnl_eur=dip_pnl,
        dip_return_pct=(dip_pnl / cfg.position_eur) * 100 if cfg.position_eur else 0,
        buyhold_pnl_eur=bh_pnl,
        buyhold_return_pct=(bh_pnl / cfg.position_eur) * 100 if cfg.position_eur else 0,
        random_trades=len(random_result.trades),
        random_pnl_eur=rnd_pnl,
        random_return_pct=(rnd_pnl / cfg.position_eur) * 100 if cfg.position_eur else 0,
    )
