from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .backtest import BacktestEngine, BacktestResult
from .config import StrategyConfig
from .trades import ClosedTrade, ExitReason


def _exit_color(trade: ClosedTrade) -> str:
    if trade.net_pnl_eur > 0:
        return "#22c55e"
    return "#ef4444"


def _exit_label(reason: ExitReason) -> str:
    return {
        ExitReason.TAKE_PROFIT: "TP",
        ExitReason.STOP_LOSS: "SL",
        ExitReason.TIME_STOP: "TIME",
        ExitReason.END_OF_DATA: "EOD",
    }.get(reason, str(reason))


def plot_trades_on_price(
    df: pd.DataFrame,
    trades: list[ClosedTrade],
    *,
    ticker: str,
    output_path: Path | str | None = None,
    title: str | None = None,
    max_trades: int | None = 40,
    figsize: tuple[float, float] = (14, 6),
    show: bool = False,
) -> Path | None:
    """
    Plot prijs + instap (groen ▲) en verkoop (▼ win=green, loss=red).

    Returns pad naar opgeslagen PNG als output_path gezet is.
    """
    if df.empty:
        return None

    price = df["close"].copy()
    if not isinstance(price.index, pd.DatetimeIndex):
        price.index = pd.to_datetime(price.index, utc=True)

    plot_trades = trades
    if max_trades and len(plot_trades) > max_trades:
        plot_trades = plot_trades[-max_trades:]

    if plot_trades:
        t0 = min(pd.Timestamp(t.entry_time) for t in plot_trades)
        t1 = max(pd.Timestamp(t.exit_time) for t in plot_trades)
        pad = pd.Timedelta(days=3)
        window = price[(price.index >= t0 - pad) & (price.index <= t1 + pad)]
        if len(window) >= 20:
            price = window

    fig, ax = plt.subplots(figsize=figsize, facecolor="#0f172a")
    ax.set_facecolor("#1e293b")

    ax.plot(price.index, price.values, color="#94a3b8", linewidth=1.0, alpha=0.9, label="Close")

    wins = sum(1 for t in trades if t.net_pnl_eur > 0)
    total_pnl = sum(t.net_pnl_eur for t in trades)

    for trade in plot_trades:
        entry_t = pd.Timestamp(trade.entry_time)
        exit_t = pd.Timestamp(trade.exit_time)
        color = _exit_color(trade)

        ax.axvspan(entry_t, exit_t, alpha=0.06, color=color, linewidth=0)

        ax.scatter(
            [entry_t], [trade.entry_price],
            marker="^", s=120, color="#3b82f6", edgecolors="white",
            linewidths=0.8, zorder=5, label="_buy",
        )
        ax.scatter(
            [exit_t], [trade.exit_price],
            marker="v", s=120, color=color, edgecolors="white",
            linewidths=0.8, zorder=5, label="_sell",
        )
        ax.plot(
            [entry_t, exit_t],
            [trade.entry_price, trade.exit_price],
            color=color, alpha=0.35, linewidth=1.0, linestyle="--",
        )

    # Legenda (unieke handles)
    from matplotlib.lines import Line2D
    legend_items = [
        Line2D([0], [0], color="#94a3b8", linewidth=2, label="Prijs"),
        Line2D([0], [0], marker="^", color="#3b82f6", linestyle="None",
               markersize=10, label="Instap (buy)"),
        Line2D([0], [0], marker="v", color="#22c55e", linestyle="None",
               markersize=10, label="Verkoop win"),
        Line2D([0], [0], marker="v", color="#ef4444", linestyle="None",
               markersize=10, label="Verkoop verlies"),
    ]
    ax.legend(handles=legend_items, loc="upper left", framealpha=0.85)

    wr = (wins / len(trades) * 100) if trades else 0
    headline = title or (
        f"{ticker} — {len(trades)} trades | Win {wr:.0f}% | Net €{total_pnl:+.0f}"
    )
    ax.set_title(headline, color="white", fontsize=13, pad=12)
    ax.set_ylabel("Prijs", color="#cbd5e1")
    ax.tick_params(colors="#cbd5e1")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=25)
    ax.grid(True, alpha=0.15, color="#64748b")
    for spine in ax.spines.values():
        spine.set_color("#334155")

    plt.tight_layout()

    saved: Path | None = None
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
        saved = out

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved


def run_and_plot_ticker(
    df: pd.DataFrame,
    cfg,
    *,
    ticker: str,
    isin: str | None = None,
    output_dir: Path | str = "data/plots",
    max_trades: int | None = 40,
) -> tuple[BacktestResult, Path | None]:
    """Backtest één ticker en sla trade chart op."""
    from .pro import ProBacktestEngine, ProStrategyConfig

    isin = isin or ticker.replace(".", "_")
    if isinstance(cfg, ProStrategyConfig):
        result = ProBacktestEngine(cfg).run(df, isin=isin, name=ticker, ticker=ticker)
    else:
        result = BacktestEngine(cfg).run(df, isin=isin, name=ticker, ticker=ticker)
    out = Path(output_dir) / f"{ticker.replace('/', '_')}_trades.png"
    path = plot_trades_on_price(
        df, result.trades,
        ticker=ticker,
        output_path=out,
        max_trades=max_trades,
    )
    return result, path
