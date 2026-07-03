from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    """
    Sentiment-dip recovery strategie.

    Logica: detecteer harde koerscorrecties (proxy voor negatief nieuws/sentiment),
    wacht op reversal-bevestiging, koop de dip, verkoop bij herstel.
    """

    # Bux EU market order kosten
    buy_fee_eur: float = 1.0
    sell_fee_eur: float = 1.0

    # Positiegrootte per trade
    position_eur: float = 1000.0

    # Paniek-drop detectie (negatief sentiment proxy)
    drop_window_bars: int = 6          # 6 × 10m = 1 uur
    min_drop_pct: float = 3.0          # Minimale daling % in window
    volume_spike_mult: float = 1.5     # Volume vs 20-bar gemiddelde

    # Sentiment (news headlines, optioneel)
    min_negative_sentiment: float = 0.3  # 0-1 score drempel
    require_news_sentiment: bool = False  # False = alleen prijs-proxy

    # Entry: wacht op reversal na drop
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    reversal_bars: int = 2             # Consecutive bullish bars nodig
    max_bars_after_drop: int = 12      # Instappen binnen 2 uur na drop

    # Exit
    take_profit_pct: float = 4.0       # Bruto % winst doel (fee-adjusted min wordt toegepast)
    stop_loss_pct: float = 2.5         # Bruto % verlies limiet
    max_hold_bars: int = 78            # Max ~2 handelsdagen (6.5u × 12)

    # Risico filters
    min_net_profit_eur: float = 3.0    # Minimale netto winst na fees
    max_open_trades: int = 1           # Per instrument
    cooldown_bars: int = 18            # Pauze na exit (~3 uur) tegen overtrading

    @property
    def round_trip_fee_eur(self) -> float:
        return self.buy_fee_eur + self.sell_fee_eur

    @property
    def fee_pct(self) -> float:
        """Kosten als % van positie."""
        if self.position_eur <= 0:
            return 0.0
        return (self.round_trip_fee_eur / self.position_eur) * 100

    @property
    def min_take_profit_pct(self) -> float:
        """Minimale take-profit % om fees terug te verdienen + buffer."""
        return self.fee_pct + (self.min_net_profit_eur / self.position_eur) * 100

    def effective_take_profit_pct(self) -> float:
        return max(self.take_profit_pct, self.min_take_profit_pct)
