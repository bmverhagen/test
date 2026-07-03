#!/usr/bin/env python3
"""CLI: test welke aandelen geschikt zijn (volatiliteit, volume, etc.)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from .backtest_cli import load_candle
from .config import load_config
from .strategy.backtest import BacktestEngine
from .strategy.benchmarks import compare_instrument, run_buy_and_hold
from .strategy.config import StrategyConfig
from .strategy.metrics import summarize
from .strategy.requirement_analysis import (
    analyze_requirements,
    format_requirements,
    format_screening_table,
)
from .strategy.stock_profile import compute_stock_profile
from .strategy.stock_screener import StockRequirements, score_profile
from .strategy.validation import split_temporal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Extra test-aandelen (grote Bux-achtige liquid names) voor betere analyse
EXTRA_TICKERS = [
    "ASML.AS", "HEIA.AS", "PHIA.AS", "ADYEN.AS", "ABN.AS",
    "AAPL", "MSFT", "TSLA", "NVDA", "AMD",
    "SAP.DE", "SIE.DE", "BMW.DE", "ALV.DE",
    "LVMH.PA", "OR.PA", "SAN.PA",
]


def fetch_yfinance_candles(ticker: str, years: int = 2) -> pd.DataFrame:
    """Haal 1h data op en resample naar 10m voor screening."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=min(years * 365, 729))

    t = yf.Ticker(ticker)
    df = t.history(start=start, end=end, interval="1h", auto_adjust=True)
    if df.empty:
        return df

    df.columns = [c.lower() for c in df.columns]
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # Resample 1h → 10m (forward fill voor profiel; voldoende voor volatiliteit)
    df10 = df.resample("10min").agg({
        "open": "ffill", "high": "ffill", "low": "ffill",
        "close": "ffill", "volume": "ffill",
    }).dropna(subset=["close"])

    df10["isin"] = ticker
    df10["ticker"] = ticker
    df10["name"] = ticker
    return df10


def load_all_candles(data_dir: Path, extra_tickers: list[str], years: int) -> list[tuple[Path | None, pd.DataFrame]]:
    datasets: list[tuple[Path | None, pd.DataFrame]] = []

    candles_dir = data_dir / "candles_10m"
    if candles_dir.exists():
        for path in sorted(candles_dir.glob("*.parquet")):
            try:
                df = load_candle(path)
                if len(df) >= 30:
                    datasets.append((path, df))
            except Exception as exc:
                logger.warning("Skip %s: %s", path.name, exc)

    for ticker in extra_tickers:
        try:
            df = fetch_yfinance_candles(ticker, years=years)
            if len(df) >= 30:
                datasets.append((None, df))
                logger.info("Extra data: %s (%d bars)", ticker, len(df))
        except Exception as exc:
            logger.debug("Extra ticker %s mislukt: %s", ticker, exc)

    return datasets


def screen_all(args: argparse.Namespace) -> int:
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
    req = StockRequirements(min_dip_win_rate_pct=args.min_win_rate)
    train_ratio = getattr(args, "train_ratio", 0.7)
    min_test_trades = max(3, req.min_dip_trades // 2)

    extra = EXTRA_TICKERS if args.extra else []
    if args.limit:
        extra = extra[: max(0, args.limit - 3)]

    datasets = load_all_candles(Path(args.data_dir), extra, args.years)
    if not datasets:
        print("Geen candle data gevonden.")
        return 1

    results = []
    performances = []

    print(
        f"\nScreening {len(datasets)} aandelen "
        f"(OOS: laatste {100 - int(train_ratio * 100)}% per aandeel)...\n"
    )

    for path, df in tqdm(datasets, desc="Analyseren"):
        meta = df.iloc[0]
        isin = str(meta.get("isin", path.stem if path else meta.get("ticker", "unknown")))
        ticker = str(meta.get("ticker", isin))
        name = str(meta.get("name", ticker))

        train_df, test_df = split_temporal(df, train_ratio)
        if len(test_df) < 30:
            test_df = df  # fallback bij korte series

        # Profiel + requirement-analyse alleen op train (geen lookahead)
        profile = compute_stock_profile(train_df, cfg, isin=isin, ticker=ticker, name=name)

        dip_train = BacktestEngine(cfg).run(train_df, isin=isin, name=name, ticker=ticker)
        dip_test = BacktestEngine(cfg).run(test_df, isin=isin, name=name, ticker=ticker)
        dip_summary = summarize(dip_test)

        bh_result = run_buy_and_hold(test_df, cfg, isin=isin, name=name, ticker=ticker)
        dip_pnl = dip_summary.total_net_pnl_eur
        bh_pnl = sum(t.net_pnl_eur for t in bh_result.trades)
        vs_bh = dip_pnl - bh_pnl

        performances.append({
            "isin": isin,
            "dip_pnl_eur": dip_pnl,
            "dip_win_rate": dip_summary.win_rate_pct,
            "dip_expectancy": dip_summary.expectancy_eur,
            "dip_vs_buyhold": vs_bh,
            "dip_trades": dip_summary.total_trades,
            "train_win_rate": summarize(dip_train).win_rate_pct,
        })

        if dip_summary.total_trades < min_test_trades:
            result = score_profile(
                profile, req,
                dip_pnl=dip_pnl,
                dip_win_rate=dip_summary.win_rate_pct,
                dip_trades=dip_summary.total_trades,
                dip_expectancy=dip_summary.expectancy_eur,
                dip_vs_buyhold=vs_bh,
            )
            result.failures.insert(0, f"OOS te weinig trades ({dip_summary.total_trades} < {min_test_trades})")
            result.passed = False
        else:
            result = score_profile(
                profile, req,
                dip_pnl=dip_pnl,
                dip_win_rate=dip_summary.win_rate_pct,
                dip_trades=dip_summary.total_trades,
                dip_expectancy=dip_summary.expectancy_eur,
                dip_vs_buyhold=vs_bh,
            )
        results.append(result)

    profiles = [r.profile for r in results]
    analysis = analyze_requirements(profiles, performances)

    print(format_screening_table(results))
    print(format_requirements(analysis.recommended, analysis))

    passed = [r for r in results if r.passed]
    print(f"\n  {len(passed)}/{len(results)} aandelen voldoen aan alle requirements")

    if passed:
        print("\n  GESCHIKT:")
        for r in sorted(passed, key=lambda x: -x.score):
            print(f"    ✓ {r.profile.ticker or r.profile.isin}  score={r.score:.0f}%  "
                  f"dip PnL=€{r.dip_pnl_eur:+.2f}  vol={r.profile.daily_volatility_pct:.2f}%")

    failed = [r for r in results if not r.passed]
    if failed:
        print("\n  AFGEWEZEN (top redenen):")
        for r in sorted(failed, key=lambda x: -x.score)[:5]:
            reason = r.failures[0] if r.failures else "?"
            print(f"    ✗ {r.profile.ticker or r.profile.isin}  score={r.score:.0f}%  → {reason}")

    if args.output:
        out = Path(args.output)
        rows = []
        for r in results:
            row = {**r.profile.to_dict(), "score": r.score, "passed": r.passed,
                   "failures": "; ".join(r.failures),
                   "dip_pnl_eur": r.dip_pnl_eur, "dip_win_rate_pct": r.dip_win_rate_pct,
                   "dip_vs_buyhold_eur": r.dip_vs_buyhold_eur}
            rows.append(row)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\n  Opgeslagen: {out}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Test welke aandelen geschikt zijn voor dip-strategie (vol, volume, etc.)."
    )
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--position", type=float, default=1000.0)
    parser.add_argument("--buy-fee", type=float, default=1.0)
    parser.add_argument("--sell-fee", type=float, default=1.0)
    parser.add_argument("--extra", action="store_true",
                        help="Voeg 17 extra grote aandelen toe via yfinance")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default=None, help="CSV output pad")
    parser.add_argument(
        "--profile",
        choices=("default", "high-win-rate"),
        default="high-win-rate",
        help="Strategie preset (default: high-win-rate voor ≥75%% WR na fees)",
    )
    parser.add_argument(
        "--min-win-rate",
        type=float,
        default=75.0,
        help="Minimale OOS dip win rate %% netto na fees (default: 75)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Train/test split; performance gemeten op test (default: 0.7)",
    )
    args = parser.parse_args(argv)
    return screen_all(args)


if __name__ == "__main__":
    sys.exit(main())
