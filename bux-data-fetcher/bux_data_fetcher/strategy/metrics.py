from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtest import BacktestResult
from .config import StrategyConfig


@dataclass
class PerformanceSummary:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    total_net_pnl_eur: float
    avg_net_pnl_eur: float
    avg_win_eur: float
    avg_loss_eur: float
    profit_factor: float
    expectancy_eur: float
    max_drawdown_pct: float
    total_fees_eur: float
    avg_hold_bars: float
    take_profit_count: int
    stop_loss_count: int
    time_stop_count: int
    fee_breakeven_pct: float
    min_recommended_position_eur: float


def compute_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak.replace(0, float("nan"))
    return float(abs(dd.min()) * 100)


def trades_equity_curve(trades: list, start_equity: float = 1000.0) -> pd.Series:
    """Bouw equity curve uit gesloten trades."""
    if not trades:
        return pd.Series(dtype=float)
    equity = start_equity
    points = []
    for t in trades:
        equity += t.net_pnl_eur
        points.append((t.exit_time, equity))
    return pd.Series([e for _, e in points], index=[t for t, _ in points])


def summarize(result: BacktestResult) -> PerformanceSummary:
    cfg = result.config or StrategyConfig()
    trades = result.trades

    if not trades:
        return PerformanceSummary(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            total_net_pnl_eur=0.0,
            avg_net_pnl_eur=0.0,
            avg_win_eur=0.0,
            avg_loss_eur=0.0,
            profit_factor=0.0,
            expectancy_eur=0.0,
            max_drawdown_pct=0.0,
            total_fees_eur=0.0,
            avg_hold_bars=0.0,
            take_profit_count=0,
            stop_loss_count=0,
            time_stop_count=0,
            fee_breakeven_pct=cfg.fee_pct,
            min_recommended_position_eur=_min_position_for_target(cfg, target_net_eur=5.0),
        )

    df = result.trades_df
    wins = df[df["net_pnl_eur"] > 0]
    losses = df[df["net_pnl_eur"] <= 0]

    gross_wins = wins["net_pnl_eur"].sum() if len(wins) else 0.0
    gross_losses = abs(losses["net_pnl_eur"].sum()) if len(losses) else 0.0

    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    equity = result.equity_curve
    if equity is None or equity.empty:
        equity = trades_equity_curve(trades, start_equity=cfg.position_eur)

    return PerformanceSummary(
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=(len(wins) / len(trades)) * 100,
        total_net_pnl_eur=float(df["net_pnl_eur"].sum()),
        avg_net_pnl_eur=float(df["net_pnl_eur"].mean()),
        avg_win_eur=float(wins["net_pnl_eur"].mean()) if len(wins) else 0.0,
        avg_loss_eur=float(losses["net_pnl_eur"].mean()) if len(losses) else 0.0,
        profit_factor=pf,
        expectancy_eur=float(df["net_pnl_eur"].mean()),
        max_drawdown_pct=compute_drawdown(equity) if len(equity) > 0 else 0.0,
        total_fees_eur=float(df["fees_eur"].sum()),
        avg_hold_bars=float(df["hold_bars"].mean()),
        take_profit_count=int((df["exit_reason"] == "take_profit").sum()),
        stop_loss_count=int((df["exit_reason"] == "stop_loss").sum()),
        time_stop_count=int((df["exit_reason"] == "time_stop").sum()),
        fee_breakeven_pct=cfg.fee_pct,
        min_recommended_position_eur=_min_position_for_target(cfg, target_net_eur=5.0),
    )


def _min_position_for_target(cfg: StrategyConfig, target_net_eur: float) -> float:
    """
    Minimale positie zodat take_profit_pct netto target_net_eur oplevert na €2 fees.
    """
    tp = cfg.effective_take_profit_pct() / 100
    if tp <= 0:
        return cfg.position_eur
    return max(cfg.position_eur, (cfg.round_trip_fee_eur + target_net_eur) / tp)


def format_summary(summary: PerformanceSummary, cfg: StrategyConfig) -> str:
    lines = [
        "=" * 60,
        "BACKTEST RESULTATEN — Sentiment Dip Recovery",
        "=" * 60,
        f"  Trades totaal:        {summary.total_trades}",
        f"  Win rate:             {summary.win_rate_pct:.1f}% ({summary.winning_trades}W / {summary.losing_trades}L)",
        f"  Netto P&L:            €{summary.total_net_pnl_eur:+.2f}",
        f"  Gem. per trade:       €{summary.avg_net_pnl_eur:+.2f}",
        f"  Gem. winst:           €{summary.avg_win_eur:+.2f}",
        f"  Gem. verlies:         €{summary.avg_loss_eur:+.2f}",
        f"  Profit factor:        {summary.profit_factor:.2f}",
        f"  Expectancy:           €{summary.expectancy_eur:+.2f}/trade",
        f"  Max drawdown:         {summary.max_drawdown_pct:.1f}%",
        f"  Totale fees:          €{summary.total_fees_eur:.2f}",
        f"  Gem. hold tijd:       {summary.avg_hold_bars:.0f} bars (~{summary.avg_hold_bars * 10:.0f} min)",
        "",
        "  Exit breakdown:",
        f"    Take profit:        {summary.take_profit_count}",
        f"    Stop loss:          {summary.stop_loss_count}",
        f"    Time stop:          {summary.time_stop_count}",
        "",
        "  Kosten & instap:",
        f"    Buy fee:            €{cfg.buy_fee_eur:.2f}",
        f"    Sell fee:           €{cfg.sell_fee_eur:.2f}",
        f"    Positie per trade:  €{cfg.position_eur:.2f}",
        f"    Fee drag:           {summary.fee_breakeven_pct:.2f}% per round-trip",
        f"    Min. take-profit:   {cfg.effective_take_profit_pct():.2f}% (fee-adjusted)",
        f"    Aanbevolen min positie (€5 netto): €{summary.min_recommended_position_eur:.0f}",
        "=" * 60,
    ]
    return "\n".join(lines)
