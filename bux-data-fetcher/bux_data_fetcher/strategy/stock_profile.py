from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .signals import enrich_bars, mark_drop_events
from .config import StrategyConfig


@dataclass
class StockProfile:
    isin: str
    ticker: str
    name: str

    # Prijs & rendement
    price_start: float
    price_end: float
    price_avg: float
    buyhold_return_pct: float

    # Volatiliteit
    daily_volatility_pct: float      # Std dagreturns (%)
    annualized_volatility_pct: float
    avg_true_range_pct: float          # ATR / prijs (%)
    max_daily_drop_pct: float
    max_daily_gain_pct: float

    # Volume & liquiditeit
    avg_volume: float
    median_volume: float
    volume_cv: float                   # Coef. of variation (lager = stabieler)
    avg_dollar_volume: float           # prijs × volume proxy

    # Dip-strategie relevant
    panic_events_per_year: float
    avg_drop_magnitude_pct: float      # Gem. drop_pct bij paniek events
    pct_bars_in_correction: float      # % bars met drop ≥ drempel
    rsi_oversold_pct: float            # % bars RSI < 35

    # Mean-reversion proxy
    bounce_after_drop_pct: float       # Gem. return 6 bars na paniek-drop

    def to_dict(self) -> dict:
        return asdict(self)


def _daily_bars(df: pd.DataFrame) -> pd.DataFrame:
    daily = df.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return daily


def compute_stock_profile(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    *,
    isin: str = "",
    ticker: str = "",
    name: str = "",
) -> StockProfile:
    df = df.sort_index()
    daily = _daily_bars(df)
    enriched = mark_drop_events(enrich_bars(df, cfg), cfg)

    daily_returns = daily["close"].pct_change().dropna() * 100
    daily_vol = float(daily_returns.std()) if len(daily_returns) > 1 else 0.0
    ann_vol = daily_vol * np.sqrt(252)

    # ATR %
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - daily["close"].shift()).abs(),
        (daily["low"] - daily["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr_pct = float((tr / daily["close"]).mean() * 100) if len(daily) > 0 else 0.0

    vol = df["volume"].fillna(0)
    price_avg = float(df["close"].mean())
    avg_vol = float(vol.mean())
    med_vol = float(vol.median())
    vol_cv = float(vol.std() / avg_vol) if avg_vol > 0 else 0.0

    panic_mask = enriched["panic_drop"].fillna(False)
    panic_count = int(panic_mask.sum())
    years = max((df.index[-1] - df.index[0]).days / 365.25, 0.1)
    panic_per_year = panic_count / years

    drop_pcts = enriched.loc[panic_mask, "drop_pct"].dropna()
    avg_drop = float(drop_pcts.mean()) if len(drop_pcts) else 0.0

    correction_pct = float((enriched["drop_pct"] <= -cfg.min_drop_pct).mean() * 100)

    rsi = enriched["rsi"].dropna()
    oversold_pct = float((rsi < cfg.rsi_oversold).mean() * 100) if len(rsi) else 0.0

    # Bounce na paniek: return over volgende 6 bars
    bounces = []
    for i, (ts, row) in enumerate(enriched.iterrows()):
        if row.get("panic_drop") and i + cfg.drop_window_bars < len(enriched):
            p0 = float(row["close"])
            p1 = float(enriched.iloc[i + cfg.drop_window_bars]["close"])
            if p0 > 0:
                bounces.append((p1 / p0 - 1) * 100)
    bounce_avg = float(np.mean(bounces)) if bounces else 0.0

    p0 = float(df.iloc[0]["close"])
    p1 = float(df.iloc[-1]["close"])

    return StockProfile(
        isin=isin,
        ticker=ticker,
        name=name,
        price_start=p0,
        price_end=p1,
        price_avg=price_avg,
        buyhold_return_pct=(p1 / p0 - 1) * 100 if p0 > 0 else 0.0,
        daily_volatility_pct=daily_vol,
        annualized_volatility_pct=ann_vol,
        avg_true_range_pct=atr_pct,
        max_daily_drop_pct=float(daily_returns.min()) if len(daily_returns) else 0.0,
        max_daily_gain_pct=float(daily_returns.max()) if len(daily_returns) else 0.0,
        avg_volume=avg_vol,
        median_volume=med_vol,
        volume_cv=vol_cv,
        avg_dollar_volume=price_avg * avg_vol,
        panic_events_per_year=panic_per_year,
        avg_drop_magnitude_pct=avg_drop,
        pct_bars_in_correction=correction_pct,
        rsi_oversold_pct=oversold_pct,
        bounce_after_drop_pct=bounce_avg,
    )
