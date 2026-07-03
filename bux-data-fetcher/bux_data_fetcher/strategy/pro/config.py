from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProStrategyConfig:
    """
    Consistent Mean Reversion Pro — evidence-based synthesis:

    - Quantitativo: RSI(2) oversold + trend filter (SMA200)
    - EasySwing/TickerDaily: RSI cross-back + volume confirmation
    - Z-score mean reversion: entry at -1.5σ, exit at mean (0σ)
    - FTO/pfolio: ATR stops, fee edge ≥3× round-trip, regime filter (ADX)
    - Alqama QuantX: trend filter rejects ~40% bad entries
    """

    buy_fee_eur: float = 1.0
    sell_fee_eur: float = 1.0
    position_eur: float = 1000.0

    # Trend & regime (only long in healthy uptrend, not strong bear)
    sma_fast_bars: int = 78          # ~13u intraday mean (10m bars)
    sma_slow_daily: int = 50         # daily SMA voor trend
    sma_long_daily: int = 200        # daily SMA200 bull filter
    adx_period: int = 14
    adx_max: float = 40.0            # skip extreme trends only

    # Entry — confluence (2 of 3 signal groups)
    rsi2_max: float = 20.0
    zscore_entry: float = -1.2
    zscore_window: int = 78
    min_volume_ratio: float = 1.2
    rsi14_cross_back: float = 40.0
    require_bullish_reversal: bool = False
    require_sma200: bool = False       # SMA50 voldoende voor liquid US names

    # Exit — mean reversion first, then R-multiple
    exit_at_mean: bool = True
    take_profit_pct: float = 2.0
    stop_atr_mult: float = 2.5
    max_stop_pct: float = 5.0
    max_hold_bars: int = 60
    min_net_profit_eur: float = 5.0

    cooldown_bars: int = 24
    max_open_trades: int = 1

    @property
    def round_trip_fee_eur(self) -> float:
        return self.buy_fee_eur + self.sell_fee_eur

    @property
    def fee_pct(self) -> float:
        if self.position_eur <= 0:
            return 0.0
        return (self.round_trip_fee_eur / self.position_eur) * 100

    @property
    def min_take_profit_pct(self) -> float:
        """Edge moet ≥3× fees zijn (pomegra/aligrithm research)."""
        return max(self.take_profit_pct, self.fee_pct * 3 + (self.min_net_profit_eur / self.position_eur) * 100)
