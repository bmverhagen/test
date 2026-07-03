#!/usr/bin/env python3
"""Plot instap/verkoop van dip-strategie trades op prijsgrafiek."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bux_data_fetcher.backtest_cli import load_candle
from bux_data_fetcher.strategy.config import StrategyConfig
from bux_data_fetcher.strategy.plot_trades import plot_trades_on_price, run_and_plot_ticker
from bux_data_fetcher.strategy.metrics import summarize


def load_ticker_df(data_dir: Path, ticker: str) -> pd.DataFrame | None:
    safe = ticker.replace("/", "_").replace(".", "_")
    for candidate in (safe, ticker):
        path = data_dir / "candles_10m" / f"{candidate}.parquet"
        if path.exists():
            return load_candle(path)
    return None


def pick_tickers_from_results(
    results_csv: Path,
    *,
    top: int = 0,
    bottom: int = 0,
    explicit: list[str] | None = None,
) -> list[str]:
    if explicit:
        return explicit

    df = pd.read_csv(results_csv)
    tickers: list[str] = []
    if top > 0:
        tickers.extend(df.nlargest(top, "pnl_full")["ticker"].tolist())
    if bottom > 0:
        tickers.extend(df.nsmallest(bottom, "pnl_full")["ticker"].tolist())
    if not tickers:
        tickers = df.nlargest(6, "trades_full")["ticker"].tolist()
    # uniek, volgorde behouden
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plot trades: groene ▲ = instap, ▼ = verkoop (win/loss kleur)."
    )
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--output-dir", default="./data/plots")
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers, bv. BGMS,TOYO,AQB",
    )
    parser.add_argument(
        "--from-results",
        default=None,
        help="CSV met resultaten (bv. data/random_100_results.csv)",
    )
    parser.add_argument("--top", type=int, default=3, help="Top N winnaars uit results")
    parser.add_argument("--bottom", type=int, default=3, help="Bottom N verliezers uit results")
    parser.add_argument("--count", type=int, default=None, help="Max aantal charts")
    parser.add_argument("--max-trades", type=int, default=40, help="Max trades per chart")
    parser.add_argument("--position", type=float, default=1000.0)
    parser.add_argument("--buy-fee", type=float, default=1.0)
    parser.add_argument("--sell-fee", type=float, default=1.0)
    parser.add_argument(
        "--profile",
        choices=("default", "high-win-rate", "pro"),
        default="pro",
    )
    parser.add_argument("--show", action="store_true", help="Toon interactief (desktop)")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    candles_dir = data_dir / "candles_10m"

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    elif args.from_results:
        tickers = pick_tickers_from_results(
            Path(args.from_results), top=args.top, bottom=args.bottom,
        )
    else:
        results = data_dir / "random_100_results.csv"
        if results.exists():
            tickers = pick_tickers_from_results(results, top=args.top, bottom=args.bottom)
        else:
            tickers = sorted(p.stem for p in candles_dir.glob("*.parquet"))[:6]

    if args.count:
        tickers = tickers[: args.count]

    if not tickers:
        print("Geen tickers gevonden. Geef --tickers of run fetch_yahoo.py eerst.")
        return 1

    if args.profile == "pro":
        from bux_data_fetcher.strategy.pro import ProBacktestEngine, ProStrategyConfig
        cfg = ProStrategyConfig(
            buy_fee_eur=args.buy_fee,
            sell_fee_eur=args.sell_fee,
            position_eur=args.position,
        )
        engine = ProBacktestEngine(cfg)
    elif args.profile == "high-win-rate":
        cfg = StrategyConfig.high_win_rate(
            buy_fee_eur=args.buy_fee,
            sell_fee_eur=args.sell_fee,
            position_eur=args.position,
        )
    else:
        cfg = StrategyConfig(
            buy_fee_eur=args.buy_fee,
            sell_fee_eur=args.sell_fee,
            position_eur=args.position,
        )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    print(f"Trade charts voor {len(tickers)} aandelen → {out_dir}/\n")

    for ticker in tickers:
        df = load_ticker_df(data_dir, ticker)
        if df is None or df.empty:
            print(f"  ✗ {ticker}: geen candle data")
            continue

        result, path = run_and_plot_ticker(
            df, cfg,
            ticker=ticker,
            output_dir=out_dir,
            max_trades=args.max_trades,
        )
        s = summarize(result)
        if path:
            saved.append(path)
            print(
                f"  ✓ {ticker}: {s.total_trades} trades, "
                f"WR {s.win_rate_pct:.0f}%, €{s.total_net_pnl_eur:+.0f} → {path.name}"
            )

        if args.show and path:
            plot_trades_on_price(
                df, result.trades, ticker=ticker, show=True,
                max_trades=args.max_trades,
            )

    if not saved:
        print("\nGeen charts gegenereerd.")
        return 1

    print(f"\n{len(saved)} charts opgeslagen in {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
