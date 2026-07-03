"""Consistent Mean Reversion Pro — evidence-based strategy module."""

from .config import ProStrategyConfig
from .engine import ProBacktestEngine, summarize_pro

__all__ = ["ProStrategyConfig", "ProBacktestEngine", "summarize_pro"]
