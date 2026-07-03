#!/usr/bin/env python3
"""Vergelijk Dip vs Pro strategie op Yahoo sample + genereer rapport."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from bux_data_fetcher.backtest_cli import load_candle
from bux_data_fetcher.strategy.backtest import BacktestEngine
from bux_data_fetcher.strategy.benchmarks import run_buy_and_hold
from bux_data_fetcher.strategy.config import StrategyConfig
from bux_data_fetcher.strategy.metrics import summarize
from bux_data_fetcher.strategy.pro import ProBacktestEngine, ProStrategyConfig
from bux_data_fetcher.strategy.validation import split_temporal
from bux_data_fetcher.yahoo_data import load_ticker_manifest


def load_ticker_df(data_dir: Path, ticker: str) -> pd.DataFrame | None:
    safe = ticker.replace("/", "_").replace(".", "_")
    for candidate in (safe, ticker):
        path = data_dir / "candles_10m" / f"{candidate}.parquet"
        if path.exists():
            return load_candle(path)
    return None


def backtest_oos(df: pd.DataFrame, engine, isin: str, ticker: str, train_ratio: float = 0.7):
    _, test_df = split_temporal(df, train_ratio)
    if len(test_df) < 30:
        test_df = df
    return engine.run(test_df, isin=isin, name=ticker, ticker=ticker)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vergelijk Dip vs Pro Mean Reversion strategie")
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--position", type=float, default=1000.0)
    parser.add_argument("--output", default="./data/pro_vs_dip_comparison.csv")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    from bux_data_fetcher.config import load_config
    tickers = load_ticker_manifest(load_config(output_dir=data_dir), f"random_{args.count}")
    if not tickers:
        print(f"Geen manifest. Run: python3 fetch_yahoo.py random --count {args.count}")
        return 1

    dip_cfg = StrategyConfig(position_eur=args.position)
    pro_cfg = ProStrategyConfig(position_eur=args.position)
    dip_engine = BacktestEngine(dip_cfg)
    pro_engine = ProBacktestEngine(pro_cfg)

    rows = []
    for ticker in tqdm(tickers, desc="Vergelijken"):
        df = load_ticker_df(Path(args.data_dir), ticker)
        if df is None or len(df) < 100:
            continue

        isin = ticker.replace(".", "_")
        dip_full = dip_engine.run(df, isin=isin, name=ticker, ticker=ticker)
        pro_full = pro_engine.run(df, isin=isin, name=ticker, ticker=ticker)
        bh_full = run_buy_and_hold(df, dip_cfg, isin=isin, name=ticker, ticker=ticker)

        dip_oos = backtest_oos(df, dip_engine, isin, ticker, args.train_ratio)
        pro_oos = backtest_oos(df, pro_engine, isin, ticker, args.train_ratio)

        ds = summarize(dip_full)
        ps = summarize(pro_full)
        dos = summarize(dip_oos)
        pos = summarize(pro_oos)
        bh_pnl = sum(t.net_pnl_eur for t in bh_full.trades)

        rows.append({
            "ticker": ticker,
            "dip_trades": ds.total_trades,
            "dip_wr": ds.win_rate_pct,
            "dip_pnl": ds.total_net_pnl_eur,
            "dip_oos_pnl": dos.total_net_pnl_eur,
            "dip_oos_wr": dos.win_rate_pct,
            "pro_trades": ps.total_trades,
            "pro_wr": ps.win_rate_pct,
            "pro_pnl": ps.total_net_pnl_eur,
            "pro_oos_pnl": pos.total_net_pnl_eur,
            "pro_oos_wr": pos.win_rate_pct,
            "pro_oos_exp": pos.expectancy_eur,
            "bh_pnl": bh_pnl,
            "pro_beats_dip": pos.total_net_pnl_eur > dos.total_net_pnl_eur,
            "pro_profitable_oos": pos.total_net_pnl_eur > 0,
        })

    if not rows:
        print("Geen data.")
        return 1

    df_out = pd.DataFrame(rows)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(out, index=False)

    # Portfolio aggregates
    dip_oos_total = df_out["dip_oos_pnl"].sum()
    pro_oos_total = df_out["pro_oos_pnl"].sum()
    pro_wins = df_out["pro_profitable_oos"].sum()
    pro_beats = df_out["pro_beats_dip"].sum()
    pro_pos_full = (df_out["pro_pnl"] > 0).sum()

    summary = {
        "stocks": len(df_out),
        "dip_oos_total_pnl": round(dip_oos_total, 2),
        "pro_oos_total_pnl": round(pro_oos_total, 2),
        "pro_oos_profitable_stocks": int(pro_wins),
        "pro_beats_dip_oos": int(pro_beats),
        "pro_full_profitable_stocks": int(pro_pos_full),
        "pro_avg_oos_wr": round(df_out["pro_oos_wr"].mean(), 1),
        "dip_avg_oos_wr": round(df_out["dip_oos_wr"].mean(), 1),
    }

    print("\n" + "=" * 60)
    print("STRATEGIE VERGELIJKING — OOS (holdout 30%)")
    print("=" * 60)
    print(f"  Aandelen getest:           {summary['stocks']}")
    print(f"  Dip OOS netto P&L:         €{summary['dip_oos_total_pnl']:+,.0f}")
    print(f"  Pro OOS netto P&L:         €{summary['pro_oos_total_pnl']:+,.0f}")
    print(f"  Pro winnaars OOS:          {summary['pro_oos_profitable_stocks']}/{summary['stocks']}")
    print(f"  Pro beats Dip (OOS):       {summary['pro_beats_dip_oos']}/{summary['stocks']}")
    print(f"  Pro avg OOS win rate:      {summary['pro_avg_oos_wr']:.1f}%")
    print(f"  Dip avg OOS win rate:      {summary['dip_avg_oos_wr']:.1f}%")
    print(f"  Pro winnaars (full):       {summary['pro_full_profitable_stocks']}/{summary['stocks']}")
    print("=" * 60)

    top = df_out.nlargest(5, "pro_oos_pnl")[["ticker", "pro_oos_pnl", "pro_oos_wr", "pro_trades"]]
    print("\nTop 5 Pro OOS:")
    print(top.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    summary_path = out.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nCSV: {out}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
