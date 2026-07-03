from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import Config, load_config
from .historical import fetch_yfinance_intraday, resample_to_10m
from .instruments import Instrument
from .storage import ensure_dirs, save_candles, save_instruments
from .yahoo_universe import YahooInstrument, to_instruments

logger = logging.getLogger(__name__)


def fetch_yahoo_10m_candles(
    ticker: str,
    *,
    years: int = 2,
    end: datetime | None = None,
    request_delay: float = 0.25,
) -> pd.DataFrame:
    """
    Haal 10m candles op via Yahoo Finance (geen Bux token).

    Zelfde strategie als historical.fetch_10m_history:
    - 5m data laatste 60 dagen
    - 1h data tot 2 jaar terug
    """
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=min(years * 365, 729))
    frames: list[pd.DataFrame] = []

    recent_start = end - timedelta(days=59)
    try:
        df_5m = fetch_yfinance_intraday(ticker, recent_start, end, interval="5m")
        if not df_5m.empty:
            frames.append(resample_to_10m(df_5m))
    except Exception as exc:
        logger.debug("5m mislukt %s: %s", ticker, exc)

    hourly_end = end - timedelta(days=59)
    if start < hourly_end:
        try:
            df_1h = fetch_yfinance_intraday(ticker, start, hourly_end, interval="1h")
            if not df_1h.empty:
                frames.append(resample_to_10m(df_1h))
        except Exception as exc:
            logger.debug("1h mislukt %s: %s", ticker, exc)

    if request_delay > 0:
        time.sleep(request_delay)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="first")]
    combined = combined.sort_index()
    combined = combined[(combined.index >= start) & (combined.index <= end)]

    combined["isin"] = ticker.replace("/", "_").replace(".", "_")
    combined["name"] = ticker
    combined["ticker"] = ticker
    return combined


def yahoo_to_bux_instrument(y: YahooInstrument) -> Instrument:
    return Instrument(
        isin=y.isin,
        name=y.name,
        ticker=y.ticker,
        security_type="stock",
        exchange=y.exchange,
        country_code=y.region,
        source="yahoo",
    )


def fetch_and_save_tickers(
    tickers: list[str],
    config: Config,
    *,
    force: bool = False,
    min_bars: int = 100,
) -> tuple[list[str], list[str]]:
    """Download en sla parquet op. Return (success, failed)."""
    ensure_dirs(config)
    instruments = to_instruments(tickers)
    save_instruments([yahoo_to_bux_instrument(i) for i in instruments], config)

    ok: list[str] = []
    failed: list[str] = []

    for inst in instruments:
        path = config.candles_dir / f"{inst.isin}.parquet"
        if not force and path.exists():
            ok.append(inst.ticker)
            continue

        df = fetch_yahoo_10m_candles(
            inst.ticker,
            years=config.years,
            request_delay=config.request_delay,
        )
        if df.empty or len(df) < min_bars:
            failed.append(inst.ticker)
            logger.warning("Geen voldoende data: %s (%d bars)", inst.ticker, len(df))
            continue

        save_candles(df, config, inst.isin)
        ok.append(inst.ticker)
        logger.info("%s: %d bars opgeslagen", inst.ticker, len(df))

    return ok, failed


def save_ticker_manifest(tickers: list[str], config: Config, name: str = "random_100") -> Path:
    ensure_dirs(config)
    path = config.output_dir / f"yahoo_{name}.txt"
    path.write_text("\n".join(tickers) + "\n")
    return path


def load_ticker_manifest(config: Config, name: str = "random_100") -> list[str]:
    path = config.output_dir / f"yahoo_{name}.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]
