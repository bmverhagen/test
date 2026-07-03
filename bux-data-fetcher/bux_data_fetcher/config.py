from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bux_token: str | None
    openfigi_api_key: str | None
    output_dir: Path
    request_delay: float
    years: int = 2
    interval_minutes: int = 10

    @property
    def start_date(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=self.years * 365)

    @property
    def end_date(self) -> datetime:
        return datetime.now(timezone.utc)

    @property
    def instruments_path(self) -> Path:
        return self.output_dir / "instruments.parquet"

    @property
    def candles_dir(self) -> Path:
        return self.output_dir / "candles_10m"


def load_config(
    *,
    years: int = 2,
    interval_minutes: int = 10,
    output_dir: str | None = None,
) -> Config:
    token = os.getenv("BUX_TOKEN") or None
    if token:
        token = token.strip() or None

    out = Path(output_dir or os.getenv("OUTPUT_DIR", "./data"))
    delay = float(os.getenv("REQUEST_DELAY", "0.3"))

    return Config(
        bux_token=token,
        openfigi_api_key=os.getenv("OPENFIGI_API_KEY") or None,
        output_dir=out,
        request_delay=delay,
        years=years,
        interval_minutes=interval_minutes,
    )
