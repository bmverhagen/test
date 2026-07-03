from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .backtest import BacktestEngine, BacktestResult
from .config import StrategyConfig
from .metrics import PerformanceSummary, summarize


@dataclass(frozen=True)
class InstrumentData:
    df: pd.DataFrame
    isin: str
    name: str
    ticker: str


def split_temporal(df: pd.DataFrame, train_ratio: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronologische train/test split (geen shuffle — voorkomt look-ahead bias)."""
    if df.empty:
        return df, df
    ratio = min(max(train_ratio, 0.5), 0.9)
    cutoff = max(int(len(df) * ratio), 30)
    cutoff = min(cutoff, len(df) - 10) if len(df) > 40 else len(df)
    return df.iloc[:cutoff].copy(), df.iloc[cutoff:].copy()


def backtest_instruments(
    instruments: list[InstrumentData],
    cfg: StrategyConfig,
    *,
    period: str = "all",
    train_ratio: float = 0.7,
) -> BacktestResult:
    """Run backtest over meerdere instrumenten, optioneel alleen train of test periode."""
    engine = BacktestEngine(cfg)
    trades = []

    for inst in instruments:
        df = inst.df
        if period == "train":
            df, _ = split_temporal(df, train_ratio)
        elif period == "test":
            _, df = split_temporal(df, train_ratio)
        elif period != "all":
            raise ValueError(f"Onbekende period: {period}")

        if len(df) < 30:
            continue

        result = engine.run(
            df,
            isin=inst.isin,
            name=inst.name,
            ticker=inst.ticker,
        )
        trades.extend(result.trades)

    return BacktestResult(trades=trades, config=cfg)


@dataclass
class TrainTestReport:
    train: PerformanceSummary
    test: PerformanceSummary
    train_ratio: float
    overfit_warning: bool
    overfit_reasons: list[str] = field(default_factory=list)

    @property
    def test_score(self) -> float:
        """Score op out-of-sample data (test set)."""
        if self.test.total_trades == 0:
            return -1e9
        score = self.test.expectancy_eur * 10 + self.test.win_rate_pct * 0.3
        if self.test.expectancy_eur <= 0:
            score *= 0.25
        if self.overfit_warning:
            score *= 0.5
        return score


def detect_overfit(
    train: PerformanceSummary,
    test: PerformanceSummary,
    *,
    max_win_rate_gap_pp: float = 15.0,
    max_expectancy_ratio: float = 3.0,
) -> tuple[bool, list[str]]:
    """Flag als train veel beter presteert dan test (klassiek overfit signaal)."""
    reasons: list[str] = []

    if train.total_trades >= 5 and test.total_trades >= 3:
        wr_gap = train.win_rate_pct - test.win_rate_pct
        if wr_gap > max_win_rate_gap_pp:
            reasons.append(f"win rate gap train→test {wr_gap:.1f}pp")

        if train.expectancy_eur > 0 and test.expectancy_eur <= 0:
            reasons.append("positieve expectancy train, negatief test")
        elif (
            train.expectancy_eur > 1
            and test.expectancy_eur > 0
            and train.expectancy_eur / test.expectancy_eur > max_expectancy_ratio
        ):
            ratio = train.expectancy_eur / test.expectancy_eur
            reasons.append(f"expectancy ratio train/test {ratio:.1f}x")

    if train.total_net_pnl_eur > 0 and test.total_net_pnl_eur < 0 and test.total_trades >= 3:
        reasons.append("winst train, verlies test")

    return bool(reasons), reasons


def evaluate_train_test(
    instruments: list[InstrumentData],
    cfg: StrategyConfig,
    *,
    train_ratio: float = 0.7,
) -> TrainTestReport:
    train_result = backtest_instruments(instruments, cfg, period="train", train_ratio=train_ratio)
    test_result = backtest_instruments(instruments, cfg, period="test", train_ratio=train_ratio)

    train_summary = summarize(train_result)
    test_summary = summarize(test_result)
    overfit, reasons = detect_overfit(train_summary, test_summary)

    return TrainTestReport(
        train=train_summary,
        test=test_summary,
        train_ratio=train_ratio,
        overfit_warning=overfit,
        overfit_reasons=reasons,
    )


@dataclass
class LeaveOneOutFold:
    held_out_ticker: str
    summary: PerformanceSummary


def leave_one_out(
    instruments: list[InstrumentData],
    cfg: StrategyConfig,
) -> list[LeaveOneOutFold]:
    """Elk instrument 1× als holdout — robuustheid over verschillende aandelen."""
    folds: list[LeaveOneOutFold] = []
    engine = BacktestEngine(cfg)

    for holdout in instruments:
        if len(holdout.df) < 30:
            continue
        result = engine.run(
            holdout.df,
            isin=holdout.isin,
            name=holdout.name,
            ticker=holdout.ticker,
        )
        folds.append(
            LeaveOneOutFold(
                held_out_ticker=holdout.ticker or holdout.isin,
                summary=summarize(result),
            )
        )
    return folds


def format_train_test_report(report: TrainTestReport, cfg: StrategyConfig) -> str:
    pct_train = int(report.train_ratio * 100)
    pct_test = 100 - pct_train
    lines = [
        "",
        "=" * 60,
        "OUT-OF-SAMPLE VALIDATIE (anti-overfit)",
        "=" * 60,
        f"  Split: {pct_train}% train (eerste periode) / {pct_test}% test (holdout)",
        "",
        f"  {'':18s} {'Train':>12s} {'Test (OOS)':>12s}",
        f"  {'Trades':18s} {report.train.total_trades:12d} {report.test.total_trades:12d}",
        f"  {'Win rate':18s} {report.train.win_rate_pct:11.1f}% {report.test.win_rate_pct:11.1f}%",
        f"  {'Netto P&L':18s} €{report.train.total_net_pnl_eur:+10.2f} €{report.test.total_net_pnl_eur:+10.2f}",
        f"  {'Expectancy':18s} €{report.train.expectancy_eur:+10.2f} €{report.test.expectancy_eur:+10.2f}",
        "",
    ]

    if report.overfit_warning:
        lines.append("  ⚠ OVERFIT WAARSCHUWING:")
        for reason in report.overfit_reasons:
            lines.append(f"    - {reason}")
    else:
        lines.append("  ✓ Geen sterke overfit-signalen train vs test")

    lines.extend([
        "",
        f"  Parameters: TP={cfg.effective_take_profit_pct():.1f}%, "
        f"SL={cfg.stop_loss_pct}%, drop={cfg.min_drop_pct}%",
        "=" * 60,
    ])
    return "\n".join(lines)


def format_loo_report(folds: list[LeaveOneOutFold]) -> str:
    if not folds:
        return "Geen LOO folds."

    lines = [
        "",
        "LEAVE-ONE-OUT (per aandeel, volledige periode)",
        "-" * 50,
        f"  {'Ticker':<10} {'Trades':>7} {'Win%':>7} {'Net PnL':>10}",
    ]
    positive = 0
    for fold in sorted(folds, key=lambda f: f.held_out_ticker):
        s = fold.summary
        if s.total_net_pnl_eur > 0:
            positive += 1
        lines.append(
            f"  {fold.held_out_ticker:<10} {s.total_trades:7d} "
            f"{s.win_rate_pct:6.1f}% €{s.total_net_pnl_eur:+9.2f}"
        )

    lines.append(
        f"\n  {positive}/{len(folds)} aandelen positief op eigen tijdlijn "
        f"(lager = strategie werkt niet universeel)"
    )
    return "\n".join(lines)
