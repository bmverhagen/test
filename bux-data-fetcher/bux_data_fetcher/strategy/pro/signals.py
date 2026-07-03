from __future__ import annotations

import numpy as np
import pandas as pd

from ..signals import compute_rsi
from .config import ProStrategyConfig


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _daily_sma_mapped(close: pd.Series, window: int) -> pd.Series:
    daily = close.resample("1D").last()
    sma = daily.rolling(window, min_periods=max(5, window // 4)).mean()
    return sma.reindex(close.index, method="ffill")


def enrich_pro_bars(df: pd.DataFrame, cfg: ProStrategyConfig) -> pd.DataFrame:
    out = df.copy().sort_index()
    close = out["close"]
    high = out["high"]
    low = out["low"]
    vol = out["volume"].fillna(0)

    # Intraday mean & z-score
    out["sma_mean"] = close.rolling(cfg.zscore_window, min_periods=20).mean()
    std = close.rolling(cfg.zscore_window, min_periods=20).std().replace(0, np.nan)
    out["zscore"] = (close - out["sma_mean"]) / std

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14, min_periods=5).mean()
    out["atr_pct"] = (out["atr"] / close) * 100

    # RSI(2) + RSI(14)
    out["rsi2"] = compute_rsi(close, 2)
    out["rsi14"] = compute_rsi(close, 14)

    # Volume
    out["volume_sma"] = vol.rolling(20, min_periods=5).mean()
    out["volume_ratio"] = vol / out["volume_sma"].replace(0, np.nan)

    # Daily trend filters
    out["sma50_daily"] = _daily_sma_mapped(close, cfg.sma_slow_daily)
    out["sma200_daily"] = _daily_sma_mapped(close, cfg.sma_long_daily)

    # Regime
    out["adx"] = _compute_adx(high, low, close, cfg.adx_period)

    # Reversal candle quality
    bar_range = (high - low).replace(0, np.nan)
    out["close_position"] = (close - low) / bar_range
    out["bullish_bar"] = close > out["open"]
    out["rsi2_turning_up"] = (out["rsi2"].shift(1) <= cfg.rsi2_max) & (out["rsi2"] > out["rsi2"].shift(1))
    out["rsi14_turning_up"] = (out["rsi14"].shift(1) <= cfg.rsi14_cross_back) & (out["rsi14"] > out["rsi14"].shift(1))

    # Dip-path helper
    out["drop_pct"] = (close / close.shift(6) - 1) * 100

    return out


def pro_entry_signal(row: pd.Series, cfg: ProStrategyConfig) -> bool:
    """
    Confluence entry — minimaal 2 van 3 signaalgroepen:
    A) Trend OK (SMA50 daily)
    B) Mean reversion setup (z-score + RSI bounce)
    C) Volume bevestiging
    """
    if pd.isna(row.get("sma50_daily")) or pd.isna(row.get("zscore")):
        return False

    price = float(row["close"])
    if price <= float(row["sma50_daily"]):
        return False

    if cfg.require_sma200 and not pd.isna(row.get("sma200_daily")):
        if price <= float(row["sma200_daily"]):
            return False

    adx = float(row.get("adx", 0))
    if adx > cfg.adx_max:
        return False

    # Signaalgroep B: extension + momentum turn
    extended = float(row["zscore"]) <= cfg.zscore_entry
    rsi_bounce = bool(row.get("rsi2_turning_up")) or bool(row.get("rsi14_turning_up"))
    signal_b = extended and rsi_bounce

    # Alternatief: paniek-daling in uptrend (dip recovery path)
    drop_pct = float(row.get("drop_pct", 0)) if "drop_pct" in row.index else 0
    vol_ok = float(row.get("volume_ratio", 0)) >= cfg.min_volume_ratio
    signal_b_alt = drop_pct <= -2.5 and vol_ok and rsi_bounce

    if not (signal_b or signal_b_alt):
        return False

    if not vol_ok:
        return False

    # Edge filter: ruimte tot mean moet ≥3× fees (pomegra research)
    if not pd.isna(row.get("sma_mean")):
        dist_to_mean_pct = (float(row["sma_mean"]) - price) / price * 100
        if dist_to_mean_pct < cfg.min_take_profit_pct * 0.7:
            return False

    if cfg.require_bullish_reversal:
        if not row.get("bullish_bar", False):
            return False
        if float(row.get("close_position", 0)) < 0.5:
            return False

    return True


def pro_should_exit(
    *,
    entry_price: float,
    current_price: float,
    hold_bars: int,
    row: pd.Series,
    cfg: ProStrategyConfig,
) -> tuple[bool, str | None]:
    pnl_pct = (current_price / entry_price - 1) * 100
    tp = cfg.min_take_profit_pct

    # Mean reversion exit (primary — Quantitativo / z-score frameworks)
    if cfg.exit_at_mean and not pd.isna(row.get("sma_mean")):
        if current_price >= float(row["sma_mean"]) and pnl_pct > cfg.fee_pct:
            return True, "mean_reversion"

    if pnl_pct >= tp:
        return True, "take_profit"

    # ATR-based stop
    atr = float(row.get("atr", 0) or 0)
    if atr > 0:
        stop_price = entry_price - cfg.stop_atr_mult * atr
        stop_pct = max((1 - stop_price / entry_price) * 100, 0)
        if stop_pct > cfg.max_stop_pct:
            stop_pct = cfg.max_stop_pct
        if pnl_pct <= -stop_pct:
            return True, "stop_loss"
    elif pnl_pct <= -cfg.max_stop_pct:
        return True, "stop_loss"

    if hold_bars >= cfg.max_hold_bars:
        return True, "time_stop"

    # RSI recovered — take profit on momentum
    if float(row.get("rsi2", 50)) > 80 and pnl_pct > cfg.fee_pct:
        return True, "rsi_overbought"

    return False, None
