"""Sentiment-dip recovery trading strategy en backtester."""

from .backtest import BacktestEngine, BacktestResult
from .config import StrategyConfig

__all__ = ["BacktestEngine", "BacktestResult", "StrategyConfig"]
