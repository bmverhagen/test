from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .benchmarks import InstrumentComparison


@dataclass
class PortfolioComparison:
    instruments: list[InstrumentComparison]
    position_eur: float

    @property
    def dip_total_pnl(self) -> float:
        return sum(i.dip_pnl_eur for i in self.instruments)

    @property
    def buyhold_total_pnl(self) -> float:
        return sum(i.buyhold_pnl_eur for i in self.instruments)

    @property
    def random_total_pnl(self) -> float:
        return sum(i.random_pnl_eur for i in self.instruments)

    @property
    def dip_total_trades(self) -> int:
        return sum(i.dip_trades for i in self.instruments)

    @property
    def random_total_trades(self) -> int:
        return sum(i.random_trades for i in self.instruments)

    @property
    def dip_avg_return_pct(self) -> float:
        if not self.instruments:
            return 0.0
        return sum(i.dip_return_pct for i in self.instruments) / len(self.instruments)

    @property
    def buyhold_avg_return_pct(self) -> float:
        if not self.instruments:
            return 0.0
        return sum(i.buyhold_return_pct for i in self.instruments) / len(self.instruments)

    @property
    def random_avg_return_pct(self) -> float:
        if not self.instruments:
            return 0.0
        return sum(i.random_return_pct for i in self.instruments) / len(self.instruments)

    @property
    def capital_deployed(self) -> float:
        return self.position_eur * len(self.instruments)


def format_comparison(comparison: PortfolioComparison) -> str:
    lines = [
        "",
        "=" * 78,
        "STRATEGIE VERGELIJKING — Dip vs Buy & Hold vs Random (buiten dip)",
        "=" * 78,
        f"{'Ticker':<12} {'Dip PnL':>10} {'Dip %':>8} {'B&H PnL':>10} {'B&H %':>8} "
        f"{'Rnd PnL':>10} {'Rnd %':>8} {'#Dip':>5} {'#Rnd':>5}",
        "-" * 78,
    ]

    for inst in comparison.instruments:
        ticker = (inst.ticker or inst.isin)[:12]
        lines.append(
            f"{ticker:<12} "
            f"€{inst.dip_pnl_eur:+9.2f} {inst.dip_return_pct:+7.2f}% "
            f"€{inst.buyhold_pnl_eur:+9.2f} {inst.buyhold_return_pct:+7.2f}% "
            f"€{inst.random_pnl_eur:+9.2f} {inst.random_return_pct:+7.2f}% "
            f"{inst.dip_trades:5d} {inst.random_trades:5d}"
        )

    lines.extend([
        "-" * 78,
        f"{'TOTAAL':<12} "
        f"€{comparison.dip_total_pnl:+9.2f} {comparison.dip_avg_return_pct:+7.2f}% "
        f"€{comparison.buyhold_total_pnl:+9.2f} {comparison.buyhold_avg_return_pct:+7.2f}% "
        f"€{comparison.random_total_pnl:+9.2f} {comparison.random_avg_return_pct:+7.2f}% "
        f"{comparison.dip_total_trades:5d} {comparison.random_total_trades:5d}",
        "",
        "  Return % = netto P&L / positie (€) per instrument",
        f"  Geïnvesteerd kapitaal per strategie: €{comparison.capital_deployed:,.0f} "
        f"({len(comparison.instruments)} × €{comparison.position_eur:,.0f})",
        "",
        "  Alpha vs Buy & Hold:",
        f"    Dip strategie:    €{comparison.dip_total_pnl - comparison.buyhold_total_pnl:+.2f} "
        f"({comparison.dip_avg_return_pct - comparison.buyhold_avg_return_pct:+.2f}% pts)",
        f"    Random baseline:  €{comparison.random_total_pnl - comparison.buyhold_total_pnl:+.2f} "
        f"({comparison.random_avg_return_pct - comparison.buyhold_avg_return_pct:+.2f}% pts)",
        f"    Dip vs Random:    €{comparison.dip_total_pnl - comparison.random_total_pnl:+.2f} "
        f"({comparison.dip_avg_return_pct - comparison.random_avg_return_pct:+.2f}% pts)",
        "",
        "  Random baseline: zelfde # trades (≈), zelfde €1000 positie, zelfde TP/SL/fees,",
        "  maar instap op willekeurige momenten BUITEN actieve correcties (drop ≥ drempel).",
        "=" * 78,
    ])
    return "\n".join(lines)


def comparison_to_dataframe(comparison: PortfolioComparison) -> pd.DataFrame:
    rows = [
        {
            "ticker": i.ticker or i.isin,
            "name": i.name,
            "dip_trades": i.dip_trades,
            "dip_pnl_eur": i.dip_pnl_eur,
            "dip_return_pct": i.dip_return_pct,
            "buyhold_pnl_eur": i.buyhold_pnl_eur,
            "buyhold_return_pct": i.buyhold_return_pct,
            "random_trades": i.random_trades,
            "random_pnl_eur": i.random_pnl_eur,
            "random_return_pct": i.random_return_pct,
            "dip_vs_buyhold_eur": i.dip_pnl_eur - i.buyhold_pnl_eur,
            "dip_vs_random_eur": i.dip_pnl_eur - i.random_pnl_eur,
        }
        for i in comparison.instruments
    ]
    return pd.DataFrame(rows)
