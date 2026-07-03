from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import StrategyConfig
from .signals import enrich_bars, entry_signal, mark_drop_events
from .trades import (
    ClosedTrade,
    ExitReason,
    OpenTrade,
    calc_net_pnl,
    calc_shares,
    should_exit,
)


@dataclass
class BacktestResult:
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: pd.Series | None = None
    signals_df: pd.DataFrame | None = None
    config: StrategyConfig | None = None

    @property
    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.__dict__ for t in self.trades])


class BacktestEngine:
    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def run(
        self,
        df: pd.DataFrame,
        *,
        isin: str = "",
        name: str = "",
        ticker: str = "",
    ) -> BacktestResult:
        if df.empty or len(df) < 30:
            return BacktestResult(config=self.config)

        cfg = self.config
        take_profit = cfg.effective_take_profit_pct()

        enriched = enrich_bars(df, cfg)
        enriched = mark_drop_events(enriched, cfg)

        trades: list[ClosedTrade] = []
        open_trade: OpenTrade | None = None
        cooldown_until = -1
        equity = cfg.position_eur
        equity_points: list[tuple[object, float]] = []

        for i, (ts, row) in enumerate(enriched.iterrows()):
            price = float(row["close"])

            if open_trade is not None:
                hold_bars = i - open_trade.entry_bar_index
                exit_now, reason = should_exit(
                    entry_price=open_trade.entry_price,
                    current_price=price,
                    hold_bars=hold_bars,
                    take_profit_pct=take_profit,
                    stop_loss_pct=cfg.stop_loss_pct,
                    max_hold_bars=cfg.max_hold_bars,
                )

                if exit_now and reason:
                    gross, fees, net = calc_net_pnl(
                        open_trade.shares,
                        open_trade.entry_price,
                        price,
                        cfg.buy_fee_eur,
                        cfg.sell_fee_eur,
                    )
                    net_pct = (net / cfg.position_eur) * 100

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
                            net_pnl_pct=net_pct,
                            hold_bars=hold_bars,
                            exit_reason=reason,
                            drop_pct=open_trade.drop_pct,
                        )
                    )
                    equity += net
                    open_trade = None
                    cooldown_until = i + cfg.cooldown_bars

            elif i >= cooldown_until and entry_signal(row, cfg):
                shares = calc_shares(cfg.position_eur, price, cfg.buy_fee_eur)
                if shares <= 0:
                    continue

                open_trade = OpenTrade(
                    entry_time=ts,
                    entry_price=price,
                    shares=shares,
                    entry_bar_index=i,
                    drop_pct=float(row.get("drop_pct", 0)),
                )

            equity_points.append((ts, equity))

        # Sluit open trade aan einde data
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
            config=cfg,
        )
