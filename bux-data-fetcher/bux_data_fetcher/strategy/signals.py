from __future__ import annotations

import pandas as pd

from .config import StrategyConfig


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def enrich_bars(df: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """Voeg technische indicatoren en signaal-kolommen toe."""
    out = df.copy()
    out = out.sort_index()

    # Rolling returns
    out["return_pct"] = out["close"].pct_change() * 100
    out["drop_pct"] = (
        (out["close"] / out["close"].shift(config.drop_window_bars) - 1) * 100
    )

    # Volume
    vol = out["volume"].fillna(0)
    out["volume_sma"] = vol.rolling(20, min_periods=5).mean()
    out["volume_ratio"] = vol / out["volume_sma"].replace(0, float("nan"))

    # RSI
    out["rsi"] = compute_rsi(out["close"], config.rsi_period)

    # Paniek-drop signaal (proxy negatief sentiment)
    out["panic_drop"] = (
        (out["drop_pct"] <= -config.min_drop_pct)
        & (out["volume_ratio"] >= config.volume_spike_mult)
    )

    # Bullish bar
    out["bullish_bar"] = out["close"] > out["open"]

    # Reversal: RSI was oversold en stijgt
    out["rsi_turning_up"] = (
        (out["rsi"].shift(1) <= config.rsi_oversold)
        & (out["rsi"] > out["rsi"].shift(1))
    )

    # Consecutive bullish bars
    bullish_streak = out["bullish_bar"].astype(int)
    out["bullish_streak"] = bullish_streak.groupby(
        (bullish_streak != bullish_streak.shift()).cumsum()
    ).cumsum()

    # Bar range positie (close near high = strength)
    bar_range = (out["high"] - out["low"]).replace(0, float("nan"))
    out["close_position"] = (out["close"] - out["low"]) / bar_range

    return out


def mark_drop_events(df: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """
    Markeer bars waar een paniek-drop plaatsvond en een instap-venster opent.
    """
    out = df.copy()
    out["drop_event"] = False
    out["bars_since_drop"] = float("nan")

    last_drop_idx = None
    for i, (ts, row) in enumerate(out.iterrows()):
        if row.get("panic_drop", False):
            last_drop_idx = i
            out.at[ts, "drop_event"] = True

        if last_drop_idx is not None:
            bars_since = i - last_drop_idx
            if bars_since <= config.max_bars_after_drop:
                out.at[ts, "bars_since_drop"] = bars_since
            else:
                last_drop_idx = None

    return out


def entry_signal(row: pd.Series, config: StrategyConfig) -> bool:
    """
    Instap na koersdip: reversal-bevestiging binnen venster na drop.
    """
    if pd.isna(row.get("bars_since_drop")):
        return False

    bars_since = row["bars_since_drop"]
    if bars_since < 1 or bars_since > config.max_bars_after_drop:
        return False

    reversal = (
        row.get("bullish_streak", 0) >= config.reversal_bars
        or row.get("rsi_turning_up", False)
        or (
            row.get("bullish_bar", False)
            and row.get("close_position", 0) >= 0.6
        )
    )

    return bool(reversal)
