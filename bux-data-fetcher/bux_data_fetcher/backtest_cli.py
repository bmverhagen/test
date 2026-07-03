from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from .config import load_config
from .news.storage import load_news
from .strategy.backtest import BacktestEngine, BacktestResult
from .strategy.config import StrategyConfig
from .strategy.metrics import format_summary, summarize

logger = logging.getLogger(__name__)


def load_candle(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def build_config(args: argparse.Namespace) -> StrategyConfig:
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


def cmd_single(args: argparse.Namespace) -> int:
    path = Path(args.candles)
    df = load_candle(path)
    meta = df.iloc[0] if not df.empty else {}
    cfg = build_config(args)
    news = load_news(load_config(output_dir=args.data_dir), isin=str(meta.get("isin", path.stem)))

    result = BacktestEngine(cfg).run(
        df,
        isin=str(meta.get("isin", path.stem)),
        name=str(meta.get("name", "")),
        ticker=str(meta.get("ticker", "")),
        news_articles=news or None,
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
    engine = BacktestEngine(cfg)
    all_trades = []

    print(f"Backtest over {len(files)} instrumenten\n")
    for path in files:
        df = load_candle(path)
        meta = df.iloc[0] if not df.empty else {}
        isin = str(meta.get("isin", path.stem))
        news = load_news(data_config, isin)
        result = engine.run(
            df,
            isin=isin,
            name=str(meta.get("name", "")),
            ticker=str(meta.get("ticker", "")),
            news_articles=news or None,
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

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        combined.trades_df.to_csv(out, index=False)
        print(f"\nTrades opgeslagen: {out}")

    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    candles_dir = Path(args.data_dir) / "candles_10m"
    files = sorted(candles_dir.glob("*.parquet"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("Geen data.")
        return 1

    drop_pcts = [2.5, 3.0, 4.0, 5.0]
    take_profits = [2.0, 2.5, 3.0, 4.0]
    stop_losses = [1.5, 2.0, 2.5]
    positions = [300.0, 500.0, 1000.0]

    best = None
    results = []

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
                    engine = BacktestEngine(cfg)
                    trades = []
                    for path in files:
                        df = load_candle(path)
                        meta = df.iloc[0] if not df.empty else {}
                        r = engine.run(
                            df,
                            isin=str(meta.get("isin", path.stem)),
                            name=str(meta.get("name", "")),
                            ticker=str(meta.get("ticker", "")),
                        )
                        trades.extend(r.trades)

                    s = summarize(BacktestResult(trades=trades, config=cfg))
                    if s.total_trades < 3:
                        continue

                    score = s.win_rate_pct * 0.4 + min(s.profit_factor, 5) * 20 + s.expectancy_eur * 5
                    if s.expectancy_eur <= 0:
                        score *= 0.5

                    row = {
                        "drop_pct": drop,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "position_eur": pos,
                        "trades": s.total_trades,
                        "win_rate": s.win_rate_pct,
                        "net_pnl": s.total_net_pnl_eur,
                        "expectancy": s.expectancy_eur,
                        "profit_factor": s.profit_factor,
                        "score": score,
                    }
                    results.append(row)
                    if best is None or score > best["score"]:
                        best = row

    if not results:
        print("Geen geldige parametercombinaties (te weinig trades).")
        return 1

    results_df = pd.DataFrame(results).sort_values("score", ascending=False)
    print("Top 10 parameter sets:\n")
    print(results_df.head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    if best:
        print(
            f"\nBeste: drop={best['drop_pct']}%, TP={best['take_profit']}%, "
            f"SL={best['stop_loss']}%, positie=€{best['position_eur']:.0f}"
        )
        print(
            f"  Win rate={best['win_rate']:.1f}%, expectancy=€{best['expectancy']:+.2f}, "
            f"net=€{best['net_pnl']:+.2f}"
        )

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
    p_all.set_defaults(func=cmd_all)

    p_opt = sub.add_parser("optimize", help="Grid search voor beste parameters")
    add_strategy_args(p_opt)
    p_opt.add_argument("--data-dir", default="./data")
    p_opt.add_argument("--limit", type=int, default=None)
    p_opt.set_defaults(func=cmd_optimize)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
