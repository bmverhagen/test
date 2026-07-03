#!/usr/bin/env python3
"""CLI: Yahoo Finance data zonder Bux token + strategie test op random sample."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from tqdm import tqdm

from .config import load_config
from .strategy.config import StrategyConfig
from .strategy.validation import (
    evaluate_train_test,
    format_loo_report,
    format_train_test_report,
    leave_one_out,
)
from .yahoo_data import fetch_and_save_tickers, load_ticker_manifest, save_ticker_manifest
from .yahoo_universe import build_universe, sample_random_tickers

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def cmd_universe(args: argparse.Namespace) -> int:
    tickers = build_universe()
    print(f"Universe: {len(tickers)} tickers (S&P500 + NASDAQ100 + FTSE100 + DAX + fallback)")
    if args.output:
        Path(args.output).write_text("\n".join(tickers) + "\n")
        print(f"Opgeslagen: {args.output}")
    else:
        print("Voorbeeld:", ", ".join(tickers[:20]), "...")
    return 0


def cmd_fetch_random(args: argparse.Namespace) -> int:
    config = load_config(years=args.years, output_dir=args.output_dir)
    universe = build_universe()
    tickers = sample_random_tickers(args.count, seed=args.seed, universe=universe)
    manifest = save_ticker_manifest(tickers, config, name=f"random_{args.count}")

    print(f"Random sample: {len(tickers)} tickers (seed={args.seed})")
    print(f"Manifest: {manifest}\n")

    ok, failed = fetch_and_save_tickers(
        tickers,
        config,
        force=args.force,
        min_bars=args.min_bars,
    )

    print(f"\nKlaar: {len(ok)} OK, {len(failed)} mislukt")
    if failed:
        print(f"Mislukte tickers ({len(failed)}): {', '.join(failed[:15])}"
              + (" ..." if len(failed) > 15 else ""))

    summary = {
        "seed": args.seed,
        "requested": args.count,
        "success": len(ok),
        "failed": len(failed),
        "tickers_ok": ok,
        "tickers_failed": failed,
    }
    summary_path = config.output_dir / f"yahoo_random_{args.count}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary: {summary_path}")
    return 0 if ok else 1


def load_instruments_by_tickers(data_dir: str | Path, tickers: list[str]) -> list:
    """Laad alleen instrumenten uit manifest (match op ticker of isin)."""
    from .backtest_cli import InstrumentData, load_candle

    config = load_config(output_dir=data_dir)
    candles_dir = config.candles_dir
    ticker_set = {t.upper() for t in tickers}
    instruments = []

    for path in sorted(candles_dir.glob("*.parquet")):
        df = load_candle(path)
        if df.empty or len(df) < 30:
            continue
        meta = df.iloc[0]
        ticker = str(meta.get("ticker", path.stem))
        isin = str(meta.get("isin", path.stem))
        if ticker.upper() not in ticker_set and isin.upper() not in ticker_set:
            continue
        instruments.append(
            InstrumentData(
                df=df,
                isin=isin,
                name=str(meta.get("name", ticker)),
                ticker=ticker,
            )
        )
    return instruments


def cmd_test(args: argparse.Namespace) -> int:
    config = load_config(output_dir=args.output_dir)
    manifest_name = f"random_{args.count}"
    tickers = load_ticker_manifest(config, name=manifest_name)

    if not tickers and args.fetch:
        fetch_args = argparse.Namespace(
            count=args.count,
            seed=args.seed,
            years=args.years,
            output_dir=args.output_dir,
            force=False,
            min_bars=args.min_bars,
        )
        if cmd_fetch_random(fetch_args) != 0:
            return 1
        tickers = load_ticker_manifest(config, name=manifest_name)

    instruments = load_instruments_by_tickers(args.output_dir, tickers)
    if args.limit:
        instruments = instruments[: args.limit]

    if len(instruments) < 5:
        print(
            f"Te weinig data ({len(instruments)}/{len(tickers)} tickers met candles). "
            f"Run eerst:\n  python3 fetch_yahoo.py random --count {args.count}"
        )
        return 1

    if args.profile == "high-win-rate":
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

    print(f"Strategie test op {len(instruments)} Yahoo-aandelen (geen Bux token)\n")

    report = evaluate_train_test(instruments, cfg, train_ratio=args.train_ratio)
    print(format_train_test_report(report, cfg))

    if len(instruments) >= 3:
        folds = leave_one_out(instruments, cfg)
        print(format_loo_report(folds))

        positive = sum(1 for f in folds if f.summary.total_net_pnl_eur > 0)
        wr_above_75 = sum(
            1 for f in folds
            if f.summary.total_trades >= 3 and f.summary.win_rate_pct >= 75
        )
        print(
            f"\n  Per aandeel: {positive}/{len(folds)} positief PnL, "
            f"{wr_above_75}/{len(folds)} met ≥75% win rate (min 3 trades)"
        )

    if args.output:
        out = Path(args.output)
        rows = []
        from .strategy.backtest import BacktestEngine
        from .strategy.metrics import summarize
        from .strategy.validation import split_temporal

        engine = BacktestEngine(cfg)
        for inst in instruments:
            train_df, test_df = split_temporal(inst.df, args.train_ratio)
            full = summarize(engine.run(inst.df, isin=inst.isin, name=inst.name, ticker=inst.ticker))
            test = summarize(engine.run(test_df, isin=inst.isin, name=inst.name, ticker=inst.ticker))
            rows.append({
                "ticker": inst.ticker,
                "trades_full": full.total_trades,
                "win_rate_full": full.win_rate_pct,
                "pnl_full": full.total_net_pnl_eur,
                "trades_oos": test.total_trades,
                "win_rate_oos": test.win_rate_pct,
                "pnl_oos": test.total_net_pnl_eur,
            })
        import pandas as pd
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\nResultaten: {out}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Yahoo Finance data zonder Bux token — random sample + strategie test."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_uni = sub.add_parser("universe", help="Toon/download ticker universe")
    p_uni.add_argument("--output", default=None)
    p_uni.set_defaults(func=cmd_universe)

    p_rand = sub.add_parser("random", help="Fetch N random aandelen via Yahoo Finance")
    p_rand.add_argument("--count", type=int, default=100)
    p_rand.add_argument("--seed", type=int, default=42)
    p_rand.add_argument("--years", type=int, default=2)
    p_rand.add_argument("--output-dir", default="./data")
    p_rand.add_argument("--force", action="store_true")
    p_rand.add_argument("--min-bars", type=int, default=100)
    p_rand.set_defaults(func=cmd_fetch_random)

    p_test = sub.add_parser("test", help="Test strategie op opgeslagen random sample")
    p_test.add_argument("--count", type=int, default=100, help="Manifest random_N")
    p_test.add_argument("--seed", type=int, default=42)
    p_test.add_argument("--years", type=int, default=2)
    p_test.add_argument("--output-dir", default="./data")
    p_test.add_argument("--fetch", action="store_true", help="Fetch eerst als manifest ontbreekt")
    p_test.add_argument("--min-bars", type=int, default=100)
    p_test.add_argument("--limit", type=int, default=None)
    p_test.add_argument("--train-ratio", type=float, default=0.7)
    p_test.add_argument("--buy-fee", type=float, default=1.0)
    p_test.add_argument("--sell-fee", type=float, default=1.0)
    p_test.add_argument("--position", type=float, default=1000.0)
    p_test.add_argument(
        "--profile",
        choices=("default", "high-win-rate"),
        default="high-win-rate",
    )
    p_test.add_argument("--output", default=None, help="CSV per aandeel")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
