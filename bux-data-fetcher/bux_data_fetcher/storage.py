from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .config import Config
from .instruments import Instrument

logger = logging.getLogger(__name__)


def ensure_dirs(config: Config) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.candles_dir.mkdir(parents=True, exist_ok=True)


def save_instruments(instruments: list[Instrument], config: Config) -> Path:
    ensure_dirs(config)
    df = pd.DataFrame([i.to_dict() for i in instruments])
    path = config.instruments_path
    df.to_parquet(path, index=False)
    logger.info("Instrumenten opgeslagen: %s (%d rijen)", path, len(df))
    return path


def load_instruments(config: Config) -> list[Instrument]:
    path = config.instruments_path
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    def _optional_str(value) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        return text or None

    return [
        Instrument(
            isin=row["isin"],
            name=row["name"],
            ticker=_optional_str(row.get("ticker")),
            security_type=_optional_str(row.get("security_type")),
            exchange=_optional_str(row.get("exchange")),
            country_code=_optional_str(row.get("country_code")),
            source=_optional_str(row.get("source")) or "cache",
        )
        for _, row in df.iterrows()
    ]


def candle_path(config: Config, isin: str) -> Path:
    safe_isin = isin.replace("/", "_")
    return config.candles_dir / f"{safe_isin}.parquet"


def save_candles(df: pd.DataFrame, config: Config, isin: str) -> Path | None:
    if df.empty:
        return None
    ensure_dirs(config)
    path = candle_path(config, isin)
    df.to_parquet(path)
    return path


def load_progress(config: Config) -> set[str]:
    progress_file = config.output_dir / "progress.json"
    if not progress_file.exists():
        return set()
    with open(progress_file) as f:
        data = json.load(f)
    return set(data.get("completed", []))


def save_progress(config: Config, completed: set[str]) -> None:
    ensure_dirs(config)
    progress_file = config.output_dir / "progress.json"
    with open(progress_file, "w") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)


def is_completed(config: Config, isin: str) -> bool:
    return candle_path(config, isin).exists()
