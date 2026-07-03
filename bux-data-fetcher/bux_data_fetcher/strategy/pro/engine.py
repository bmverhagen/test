from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..backtest import BacktestResult
from ..config import StrategyConfig
from ..metrics import PerformanceSummary, summarize
from ..trades import ClosedTrade, ExitReason, OpenTrade, calc_net_pnl, calc_shares
from .config import ProStrategyConfig
from .signals import enrich_pro_bars, pro_entry_signal, pro_should_exit


def _map_exit_reason(reason: str | None) -> ExitReason:
    mapping = {
        "take_profit": ExitReason.TAKE_PROFIT,
        "mean_reversion": ExitReason.TAKE_PROFIT,
        "rsi_overbought": ExitReason.TAKE_PROFIT,
        "stop_loss": ExitReason.STOP_LOSS,
        "time_stop": ExitReason.TIME_STOP,
    }
    return mapping.get(reason or "", ExitReason.TIME_STOP)


class ProBacktestEngine:
    """Backtest engine voor Consistent Mean Reversion Pro strategie."""

    def __init__(self, config: ProStrategyConfig | None = None):
        self.config = config or ProStrategyConfig()

    def run(
        self,
        df: pd.DataFrame,
        *,
        isin: str = "",
        name: str = "",
        ticker: str = "",
    ) -> BacktestResult:
        cfg = self.config
        if df.empty or len(df) < 100:
            return BacktestResult(config=_legacy_cfg(cfg))

        enriched = enrich_pro_bars(df, cfg)
        trades: list[ClosedTrade] = []
        open_trade: OpenTrade | None = None
        cooldown_until = -1
        equity = cfg.position_eur
        equity_points: list[tuple[object, float]] = []

        for i, (ts, row) in enumerate(enriched.iterrows()):
            price = float(row["close"])

            if open_trade is not None:
                hold_bars = i - open_trade.entry_bar_index
                exit_now, reason = pro_should_exit(
                    entry_price=open_trade.entry_price,
                    current_price=price,
                    hold_bars=hold_bars,
                    row=row,
                    cfg=cfg,
                )
                if exit_now and reason:
                    gross, fees, net = calc_net_pnl(
                        open_trade.shares,
                        open_trade.entry_price,
                        price,
                        cfg.buy_fee_eur,
                        cfg.sell_fee_eur,
                    )
                    trades.append(
                        ClosedTrade(
                            isin=isin,
                            name=name,
                            ticker=ticker,
                            entry_time=open_trade.entry_time,
                            exit_time=ts,
                            entry_price=open_trade.entry_price,
                            exit_price=price,
                            shares=open_trade.shares,
                            gross_pnl_eur=gross,
                            fees_eur=fees,
                            net_pnl_eur=net,
                            net_pnl_pct=(net / cfg.position_eur) * 100,
                            hold_bars=hold_bars,
                            exit_reason=_map_exit_reason(reason),
                            drop_pct=float(row.get("zscore", 0)),
                        )
                    )
                    equity += net
                    open_trade = None
                    cooldown_until = i + cfg.cooldown_bars

            elif i >= cooldown_until and pro_entry_signal(row, cfg):
                shares = calc_shares(cfg.position_eur, price, cfg.buy_fee_eur)
                if shares > 0:
                    open_trade = OpenTrade(
                        entry_time=ts,
                        entry_price=price,
                        shares=shares,
                        entry_bar_index=i,
                        drop_pct=float(row.get("zscore", 0)),
                    )

            equity_points.append((ts, equity))

        if open_trade is not None:
            last_ts = enriched.index[-1]
            last_price = float(enriched.iloc[-1]["close"])
            hold_bars = len(enriched) - 1 - open_trade.entry_bar_index
            gross, fees, net = calc_net_pnl(
                open_trade.shares,
                open_trade.entry_price,
                last_price,
                cfg.buy_fee_eur,
                cfg.sell_fee_eur,
            )
            trades.append(
                ClosedTrade(
                    isin=isin,
                    name=name,
                    ticker=ticker,
                    entry_time=open_trade.entry_time,
                    exit_time=last_ts,
                    entry_price=open_trade.entry_price,
                    exit_price=last_price,
                    shares=open_trade.shares,
                    gross_pnl_eur=gross,
                    fees_eur=fees,
                    net_pnl_eur=net,
                    net_pnl_pct=(net / cfg.position_eur) * 100,
                    hold_bars=hold_bars,
                    exit_reason=ExitReason.END_OF_DATA,
                    drop_pct=open_trade.drop_pct,
                )
            )

        equity_curve = pd.Series(
            [e for _, e in equity_points],
            index=[t for t, _ in equity_points],
        )

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            signals_df=enriched,
            config=_legacy_cfg(cfg),
        )


def _legacy_cfg(cfg: ProStrategyConfig) -> StrategyConfig:
    """Map naar StrategyConfig voor metrics compatibiliteit."""
    return StrategyConfig(
        buy_fee_eur=cfg.buy_fee_eur,
        sell_fee_eur=cfg.sell_fee_eur,
        position_eur=cfg.position_eur,
        take_profit_pct=cfg.min_take_profit_pct,
        stop_loss_pct=cfg.max_stop_pct,
    )


def summarize_pro(result: BacktestResult, cfg: ProStrategyConfig) -> PerformanceSummary:
    return summarize(result)
