from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from .config import load_config
from .news.storage import load_news
from .strategy.backtest import BacktestEngine, BacktestResult
from .strategy.benchmarks import compare_instrument
from .strategy.comparison import PortfolioComparison, comparison_to_dataframe, format_comparison
from .strategy.config import StrategyConfig
from .strategy.metrics import format_summary, summarize
from .strategy.validation import (
    InstrumentData,
    evaluate_train_test,
    format_loo_report,
    format_train_test_report,
    leave_one_out,
    split_temporal,
)

logger = logging.getLogger(__name__)


def load_candle(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def run_backtest_engine(cfg, df, *, isin, name, ticker, news=None):
    """Run dip of pro engine afhankelijk van config type."""
    from .strategy.pro import ProBacktestEngine, ProStrategyConfig

    if isinstance(cfg, ProStrategyConfig):
        return ProBacktestEngine(cfg).run(df, isin=isin, name=name, ticker=ticker)
    return BacktestEngine(cfg).run(
        df, isin=isin, name=name, ticker=ticker, news_articles=news or None,
    )


def build_config(args: argparse.Namespace):
    profile = getattr(args, "profile", "default")
    if profile == "pro":
        from .strategy.pro import ProStrategyConfig
        return ProStrategyConfig(
            buy_fee_eur=args.buy_fee,
            sell_fee_eur=args.sell_fee,
            position_eur=args.position,
        )
    if profile == "high-win-rate":
        return StrategyConfig.high_win_rate(
            buy_fee_eur=args.buy_fee,
            sell_fee_eur=args.sell_fee,
            position_eur=args.position,
            require_news_sentiment=getattr(args, "require_news", False),
        )
    return StrategyConfig(
        buy_fee_eur=args.buy_fee,
        sell_fee_eur=args.sell_fee,
        position_eur=args.position,
        min_drop_pct=args.drop_pct,
        take_profit_pct=args.take_profit,
        stop_loss_pct=args.stop_loss,
        volume_spike_mult=args.volume_mult,
        reversal_bars=args.reversal_bars,
        max_hold_bars=args.max_hold,
        require_news_sentiment=getattr(args, "require_news", False),
    )


def add_strategy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--buy-fee", type=float, default=1.0, help="Buy fee in EUR (Bux market order)")
    parser.add_argument("--sell-fee", type=float, default=1.0, help="Sell fee in EUR")
    parser.add_argument("--position", type=float, default=1000.0, help="Positiegrootte per trade in EUR")
    parser.add_argument("--drop-pct", type=float, default=3.0, help="Minimale paniek-daling % in 1 uur")
    parser.add_argument("--take-profit", type=float, default=4.0, help="Take profit % (bruto)")
    parser.add_argument("--stop-loss", type=float, default=2.5, help="Stop loss % (bruto)")
    parser.add_argument("--volume-mult", type=float, default=1.5, help="Volume spike vs gemiddelde")
    parser.add_argument("--reversal-bars", type=int, default=2, help="Consecutive bullish bars voor instap")
    parser.add_argument("--max-hold", type=int, default=78, help="Maximaal aantal bars in trade")
    parser.add_argument(
        "--require-news",
        action="store_true",
        help="Alleen instappen als negatief nieuws in 48u (vereist news data)",
    )
    parser.add_argument(
        "--profile",
        choices=("default", "high-win-rate", "pro"),
        default="default",
        help="Strategie preset: pro = evidence-based mean reversion",
    )


def load_instruments(
    data_dir: str | Path,
    *,
    limit: int | None = None,
) -> list[InstrumentData]:
    candles_dir = Path(data_dir) / "candles_10m"
    files = sorted(candles_dir.glob("*.parquet"))
    if limit:
        files = files[:limit]

    instruments: list[InstrumentData] = []
    for path in files:
        df = load_candle(path)
        if df.empty or len(df) < 30:
            continue
        meta = df.iloc[0]
        instruments.append(
            InstrumentData(
                df=df,
                isin=str(meta.get("isin", path.stem)),
                name=str(meta.get("name", "")),
                ticker=str(meta.get("ticker", path.stem)),
            )
        )
    return instruments


def add_validation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Fractie data voor training; rest is out-of-sample test (default: 0.7)",
    )
    parser.add_argument(
        "--oos-only",
        action="store_true",
        help="Evalueer/score alleen op test (holdout) periode",
    )


def cmd_single(args: argparse.Namespace) -> int:
    path = Path(args.candles)
    df = load_candle(path)
    meta = df.iloc[0] if not df.empty else {}
    cfg = build_config(args)
    news = load_news(load_config(output_dir=args.data_dir), isin=str(meta.get("isin", path.stem)))

    result = run_backtest_engine(
        cfg, df,
        isin=str(meta.get("isin", path.stem)),
        name=str(meta.get("name", "")),
        ticker=str(meta.get("ticker", "")),
        news=news or None,
    )

    summary = summarize(result)
    print(format_summary(summary, cfg))

    if result.trades and args.show_trades:
        cols = [
            "entry_time", "exit_time", "entry_price", "exit_price",
            "net_pnl_eur", "net_pnl_pct", "exit_reason", "drop_pct",
        ]
        print("\nTrades:")
        print(result.trades_df[cols].to_string())

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        result.trades_df.to_csv(out, index=False)
        print(f"\nTrades opgeslagen: {out}")

    return 0


def cmd_all(args: argparse.Namespace) -> int:
    candles_dir = Path(args.data_dir) / "candles_10m"
    if not candles_dir.exists():
        print(f"Geen candle data in {candles_dir}")
        return 1

    files = sorted(candles_dir.glob("*.parquet"))
    if args.limit:
        files = files[: args.limit]

    cfg = build_config(args)
    data_config = load_config(output_dir=args.data_dir)
    all_trades = []
    train_ratio = getattr(args, "train_ratio", 0.7)
    oos_only = getattr(args, "oos_only", False)

    label = f"Backtest over {len(files)} instrumenten"
    if oos_only:
        label += f" (OOS test, laatste {100 - int(train_ratio * 100)}%)"
    print(f"{label}\n")

    for path in files:
        df = load_candle(path)
        meta = df.iloc[0] if not df.empty else {}
        isin = str(meta.get("isin", path.stem))
        if oos_only:
            _, df = split_temporal(df, train_ratio)
            if len(df) < 30:
                continue
        news = load_news(data_config, isin)
        result = run_backtest_engine(
            cfg, df,
            isin=isin,
            name=str(meta.get("name", "")),
            ticker=str(meta.get("ticker", "")),
            news=news or None,
        )
        all_trades.extend(result.trades)
        if result.trades:
            s = summarize(result)
            ticker = meta.get("ticker", path.stem)
            print(
                f"  {str(ticker):10s}  {len(result.trades):3d} trades  "
                f"win={s.win_rate_pct:5.1f}%  net=€{s.total_net_pnl_eur:+8.2f}"
            )

    combined = BacktestResult(trades=all_trades, config=cfg)
    print("\n" + format_summary(summarize(combined), cfg))

    if not oos_only and getattr(args, "validate", False):
        instruments = load_instruments(args.data_dir, limit=args.limit)
        report = evaluate_train_test(instruments, cfg, train_ratio=train_ratio)
        print(format_train_test_report(report, cfg))

    if getattr(args, "compare", False):
        _run_comparison(files, cfg, data_config, args)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        combined.trades_df.to_csv(out, index=False)
        print(f"\nTrades opgeslagen: {out}")

    return 0


def _run_comparison(
    files: list[Path],
    cfg: StrategyConfig,
    data_config,
    args: argparse.Namespace,
) -> None:
    comparisons = []
    for path in files:
        df = load_candle(path)
        meta = df.iloc[0] if not df.empty else {}
        isin = str(meta.get("isin", path.stem))
        news = load_news(data_config, isin)
        comp = compare_instrument(
            df,
            cfg,
            isin=isin,
            name=str(meta.get("name", "")),
            ticker=str(meta.get("ticker", "")),
            news_articles=news or None,
            random_seed=getattr(args, "random_seed", 42),
            random_runs=getattr(args, "random_runs", 50),
        )
        comparisons.append(comp)

    portfolio = PortfolioComparison(instruments=comparisons, position_eur=cfg.position_eur)
    print(format_comparison(portfolio))

    if getattr(args, "comparison_output", None):
        out = Path(args.comparison_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        comparison_to_dataframe(portfolio).to_csv(out, index=False)
        print(f"\nVergelijking opgeslagen: {out}")


def cmd_compare(args: argparse.Namespace) -> int:
    candles_dir = Path(args.data_dir) / "candles_10m"
    if not candles_dir.exists():
        print(f"Geen candle data in {candles_dir}")
        return 1

    files = sorted(candles_dir.glob("*.parquet"))
    if args.limit:
        files = files[: args.limit]

    cfg = build_config(args)
    data_config = load_config(output_dir=args.data_dir)
    _run_comparison(files, cfg, data_config, args)
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    instruments = load_instruments(args.data_dir, limit=args.limit)
    if not instruments:
        print("Geen data.")
        return 1

    train_ratio = getattr(args, "train_ratio", 0.7)
    # Smaller grid — brede search op kleine sample = overfit
    drop_pcts = [3.0, 4.0, 5.0]
    take_profits = [1.0, 1.5, 2.0, 2.5]
    stop_losses = [3.0, 4.0, 5.0, 6.0]
    positions = [500.0, 1000.0, 2000.0]

    min_win_rate = getattr(args, "min_win_rate", 0.0)
    min_train_trades = getattr(args, "min_trades", 5)
    min_test_trades = max(3, min_train_trades // 2)

    best = None
    results = []

    print(
        f"Grid search op {len(instruments)} instrumenten — "
        f"score op OOS winstgevendheid (expectancy + net PnL)\n"
    )

    for drop in drop_pcts:
        for tp in take_profits:
            for sl in stop_losses:
                for pos in positions:
                    cfg = StrategyConfig(
                        min_drop_pct=drop,
                        take_profit_pct=tp,
                        stop_loss_pct=sl,
                        position_eur=pos,
                        buy_fee_eur=args.buy_fee,
                        sell_fee_eur=args.sell_fee,
                    )
                    report = evaluate_train_test(instruments, cfg, train_ratio=train_ratio)

                    if report.train.total_trades < min_train_trades:
                        continue
                    if report.test.total_trades < min_test_trades:
                        continue
                    if min_win_rate > 0 and report.test.win_rate_pct < min_win_rate:
                        continue
                    if report.test.expectancy_eur <= 0:
                        continue
                    if report.overfit_warning:
                        continue

                    score = report.test_score

                    row = {
                        "drop_pct": drop,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "position_eur": pos,
                        "train_trades": report.train.total_trades,
                        "test_trades": report.test.total_trades,
                        "train_win_rate": report.train.win_rate_pct,
                        "test_win_rate": report.test.win_rate_pct,
                        "train_net": report.train.total_net_pnl_eur,
                        "test_net": report.test.total_net_pnl_eur,
                        "test_expectancy": report.test.expectancy_eur,
                        "score": score,
                    }
                    results.append(row)
                    if best is None or score > best["score"]:
                        best = row

    if not results:
        msg = (
            f"Geen robuuste parametercombinaties op OOS test "
            f"(min {min_test_trades} test trades, positieve test expectancy"
        )
        if min_win_rate > 0:
            msg += f", ≥{min_win_rate:.0f}% test win rate"
        msg += ", geen overfit)."
        print(msg)
        print("\nTip: gebruik Pro strategie voor winstgevendheid:")
        print("  python3 backtest.py validate --profile pro")
        return 1

    results_df = pd.DataFrame(results).sort_values("score", ascending=False)
    print("Top 10 (gesorteerd op OOS test score):\n")
    print(results_df.head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    if best:
        print(
            f"\nBeste (OOS): drop={best['drop_pct']}%, TP={best['take_profit']}%, "
            f"SL={best['stop_loss']}%, positie=€{best['position_eur']:.0f}"
        )
        print(
            f"  Test:  win rate={best['test_win_rate']:.1f}%, "
            f"expectancy=€{best['test_expectancy']:+.2f}, net=€{best['test_net']:+.2f} "
            f"({best['test_trades']} trades)"
        )
        print(
            f"  Train: win rate={best['train_win_rate']:.1f}%, "
            f"net=€{best['train_net']:+.2f} ({best['train_trades']} trades)"
        )

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    instruments = load_instruments(args.data_dir, limit=args.limit)
    if not instruments:
        print("Geen data.")
        return 1

    cfg = build_config(args)
    train_ratio = getattr(args, "train_ratio", 0.7)

    print(f"Validatie over {len(instruments)} instrumenten")
    report = evaluate_train_test(instruments, cfg, train_ratio=train_ratio)
    print(format_train_test_report(report, cfg))

    if len(instruments) >= 2:
        folds = leave_one_out(instruments, cfg)
        print(format_loo_report(folds))

    if report.test.total_trades == 0:
        print("\nTe weinig test trades — vergroot dataset of verlaag --train-ratio.")
        return 1

    if report.overfit_warning:
        print("\nConclusie: parameters presteren veel beter in-sample dan out-of-sample.")
        print("Gebruik vaste presets; optimaliseer niet verder op deze sample.")
        return 1

    print("\nConclusie: geen sterke overfit-signalen — test prestaties zijn acceptabel.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backtest: koop dip na negatief sentiment/paniek-daling (Bux €1 fees)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_single = sub.add_parser("single", help="Backtest één instrument")
    add_strategy_args(p_single)
    p_single.add_argument("candles", help="Pad naar parquet candle file")
    p_single.add_argument("--data-dir", default="./data")
    p_single.add_argument("--show-trades", action="store_true")
    p_single.add_argument("--output", default=None)
    p_single.set_defaults(func=cmd_single)

    p_all = sub.add_parser("all", help="Backtest alle instrumenten in data/")
    add_strategy_args(p_all)
    p_all.add_argument("--data-dir", default="./data")
    p_all.add_argument("--limit", type=int, default=None)
    p_all.add_argument("--output", default=None)
    p_all.add_argument("--compare", action="store_true", help="Toon vergelijking met B&H en random baseline")
    p_all.add_argument("--random-seed", type=int, default=42)
    p_all.add_argument("--random-runs", type=int, default=50, help="Monte Carlo runs voor random baseline")
    p_all.add_argument("--comparison-output", default=None, help="CSV met strategie vergelijking")
    add_validation_args(p_all)
    p_all.add_argument(
        "--validate",
        action="store_true",
        help="Toon train/test split na backtest (anti-overfit check)",
    )
    p_all.set_defaults(func=cmd_all)

    p_cmp = sub.add_parser("compare", help="Vergelijk dip vs buy&hold vs random baseline")
    add_strategy_args(p_cmp)
    p_cmp.add_argument("--data-dir", default="./data")
    p_cmp.add_argument("--limit", type=int, default=None)
    p_cmp.add_argument("--random-seed", type=int, default=42)
    p_cmp.add_argument("--random-runs", type=int, default=50)
    p_cmp.add_argument("--comparison-output", default=None)
    p_cmp.set_defaults(func=cmd_compare)

    p_opt = sub.add_parser("optimize", help="Grid search — score op OOS test (anti-overfit)")
    add_strategy_args(p_opt)
    add_validation_args(p_opt)
    p_opt.add_argument("--data-dir", default="./data")
    p_opt.add_argument("--limit", type=int, default=None)
    p_opt.add_argument(
        "--min-win-rate",
        type=float,
        default=0.0,
        help="Optioneel min test win rate %% (0 = uit; focus op winstgevendheid)",
    )
    p_opt.add_argument("--min-trades", type=int, default=5, help="Minimaal train trades per combinatie")
    p_opt.set_defaults(func=cmd_optimize)

    p_val = sub.add_parser("validate", help="Train/test + leave-one-out validatie")
    add_strategy_args(p_val)
    add_validation_args(p_val)
    p_val.add_argument("--data-dir", default="./data")
    p_val.add_argument("--limit", type=int, default=None)
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
