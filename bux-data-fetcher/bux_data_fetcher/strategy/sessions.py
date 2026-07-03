from __future__ import annotations

import pandas as pd

from .trades import ExitReason


def annotate_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Markeer sessie-grenzen en overnight gaps (close → next open).

    Eerste bar van elke kalenderdag = session open; gap_pct vs vorige close.
    """
    out = df.copy().sort_index()
    if out.empty:
        return out

    dates = pd.Series([ts.date() for ts in out.index], index=out.index)
    session_open = dates != dates.shift(1)
    prev_close = out["close"].shift(1)

    out["is_session_open"] = session_open
    out["prev_session_close"] = prev_close.where(session_open)
    out["overnight_gap_pct"] = (
        (out["open"] - prev_close) / prev_close.replace(0, float("nan")) * 100
    ).where(session_open)

    return out


def _pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price / entry - 1) * 100


def evaluate_bar_exit_long(
    *,
    entry_price: float,
    open_: float,
    high: float,
    low: float,
    close: float,
    is_session_open: bool,
    take_profit_pct: float,
    stop_loss_pct: float,
    mean_target: float | None = None,
) -> tuple[float, ExitReason] | None:
    """
    Evalueer exit op één bar met OHLC — incl. overnight gap op session open.

    Volgorde (conservatief voor long):
    1. Session open: gap kan direct door stop/TP gaan → fill at open
    2. Intrabar low: stop loss (limit at stop, tenzij open al eronder)
    3. Mean reversion target (als high raakt mean boven entry)
    4. Intrabar high: take profit
    """
    stop_price = entry_price * (1 - stop_loss_pct / 100)
    tp_price = entry_price * (1 + take_profit_pct / 100)

    # 1) Overnight gap @ open
    if is_session_open:
        open_pnl = _pnl_pct(entry_price, open_)
        if open_pnl <= -stop_loss_pct:
            return open_, ExitReason.STOP_LOSS
        if open_pnl >= take_profit_pct:
            return open_, ExitReason.TAKE_PROFIT

    # 2) Stop via intrabar low (open kan al gecheckt zijn)
    if low <= stop_price:
        fill = min(open_, stop_price) if is_session_open and open_ < stop_price else stop_price
        return fill, ExitReason.STOP_LOSS

    # 3) Mean reversion (Pro)
    if mean_target is not None and mean_target > entry_price:
        if high >= mean_target and _pnl_pct(entry_price, mean_target) > 0:
            return mean_target, ExitReason.TAKE_PROFIT

    # 4) Take profit via high
    if high >= tp_price:
        fill = max(open_, tp_price) if is_session_open and open_ > tp_price else tp_price
        return fill, ExitReason.TAKE_PROFIT

    return None


def evaluate_bar_exit_pro(
    *,
    entry_price: float,
    row: pd.Series,
    hold_bars: int,
    take_profit_pct: float,
    stop_loss_pct: float,
    max_stop_pct: float,
    max_hold_bars: int,
    atr: float,
    stop_atr_mult: float,
    exit_at_mean: bool,
    fee_pct: float,
) -> tuple[float, ExitReason] | None:
    """Pro exit met ATR stop, mean target, en overnight gap."""
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    is_session_open = bool(row.get("is_session_open", False))

    # ATR stop (absolute)
    if atr > 0:
        stop_price = entry_price - stop_atr_mult * atr
        stop_pct = max((1 - stop_price / entry_price) * 100, 0)
        if stop_pct > max_stop_pct:
            stop_price = entry_price * (1 - max_stop_pct / 100)
    else:
        stop_price = entry_price * (1 - max_stop_pct / 100)

    tp_price = entry_price * (1 + take_profit_pct / 100)
    mean_target = float(row["sma_mean"]) if exit_at_mean and not pd.isna(row.get("sma_mean")) else None

    # Overnight gap @ open
    if is_session_open:
        if open_ <= stop_price:
            return open_, ExitReason.STOP_LOSS
        if open_ >= tp_price:
            return open_, ExitReason.TAKE_PROFIT
        if mean_target is not None and open_ >= mean_target:
            if _pnl_pct(entry_price, open_) > fee_pct:
                return open_, ExitReason.TAKE_PROFIT

    # Intrabar stop
    if low <= stop_price:
        fill = open_ if is_session_open and open_ < stop_price else stop_price
        return fill, ExitReason.STOP_LOSS

    # Mean reversion
    if mean_target is not None and mean_target > entry_price and high >= mean_target:
        if _pnl_pct(entry_price, mean_target) > fee_pct:
            return mean_target, ExitReason.TAKE_PROFIT

    # Take profit
    if high >= tp_price:
        fill = open_ if is_session_open and open_ > tp_price else tp_price
        return fill, ExitReason.TAKE_PROFIT

    # RSI overbought @ close
    if float(row.get("rsi2", 50)) > 80 and _pnl_pct(entry_price, close) > fee_pct:
        return close, ExitReason.TAKE_PROFIT

    if hold_bars >= max_hold_bars:
        return close, ExitReason.TIME_STOP

    return None
