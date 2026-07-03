from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExitReason(str, Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TIME_STOP = "time_stop"
    END_OF_DATA = "end_of_data"


@dataclass
class OpenTrade:
    entry_time: object
    entry_price: float
    shares: float
    entry_bar_index: int
    drop_pct: float


@dataclass
class ClosedTrade:
    isin: str
    name: str
    ticker: str
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    shares: float
    gross_pnl_eur: float
    fees_eur: float
    net_pnl_eur: float
    net_pnl_pct: float
    hold_bars: int
    exit_reason: ExitReason
    drop_pct: float


def calc_shares(position_eur: float, price: float, buy_fee_eur: float) -> float:
    """Aantal aandelen na aftrek buy fee."""
    investable = position_eur - buy_fee_eur
    if price <= 0 or investable <= 0:
        return 0.0
    return investable / price


def calc_net_pnl(
    shares: float,
    entry_price: float,
    exit_price: float,
    buy_fee_eur: float,
    sell_fee_eur: float,
) -> tuple[float, float, float]:
    """Return (gross_pnl, fees, net_pnl)."""
    gross = shares * (exit_price - entry_price)
    fees = buy_fee_eur + sell_fee_eur
    net = gross - fees
    return gross, fees, net


def should_exit(
    *,
    entry_price: float,
    current_price: float,
    hold_bars: int,
    take_profit_pct: float,
    stop_loss_pct: float,
    max_hold_bars: int,
) -> tuple[bool, ExitReason | None]:
    pnl_pct = (current_price / entry_price - 1) * 100

    if pnl_pct >= take_profit_pct:
        return True, ExitReason.TAKE_PROFIT
    if pnl_pct <= -stop_loss_pct:
        return True, ExitReason.STOP_LOSS
    if hold_bars >= max_hold_bars:
        return True, ExitReason.TIME_STOP

    return False, None
