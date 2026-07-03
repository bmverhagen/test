from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import bux
import pandas as pd
import yfinance as yf

from .config import Config
from .instruments import Instrument
from .ticker_mapper import isin_to_yahoo_ticker

logger = logging.getLogger(__name__)

SourceType = Literal["bux_api", "yfinance_5m", "yfinance_1h"]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    rename = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def resample_to_10m(df: pd.DataFrame) -> pd.DataFrame:
    """Resample OHLCV data naar 10-minuten candles."""
    if df.empty:
        return df

    df = _normalize_columns(df)
    resampled = df.resample("10min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna(subset=["open", "close"])

    return resampled


def fetch_bux_graph(
    isin: str,
    graph_type: str,
    config: Config,
) -> pd.DataFrame:
    """Haal prijsgrafiek op via Bux Zero API."""
    if not config.bux_token:
        return pd.DataFrame()

    api = bux.UserAPI(token=config.bux_token)
    graph = api.security(isin).graph(graph_type).requests()

    rows = []
    for point in graph.prices:
        rows.append(
            {
                "timestamp": point.time.replace(tzinfo=timezone.utc),
                "close": float(point.price),
                "open": float(point.price),
                "high": float(point.price),
                "low": float(point.price),
                "volume": None,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df["source"] = f"bux_graph_{graph_type}"
    return df


def fetch_yfinance_intraday(
    yahoo_symbol: str,
    start: datetime,
    end: datetime,
    *,
    interval: str,
) -> pd.DataFrame:
    ticker = yf.Ticker(yahoo_symbol)
    df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
    if df.empty:
        return df
    df = _normalize_columns(df)
    df["source"] = f"yfinance_{interval}"
    return df


def fetch_10m_history(
    instrument: Instrument,
    config: Config,
    yahoo_symbol: str | None = None,
) -> pd.DataFrame:
    """
    Haal 10-minuten historische data op voor de afgelopen N jaar.

    Strategie:
    1. Laatste 60 dagen: Yahoo 5m data -> resample naar 10m (hoogste resolutie)
    2. 60 dagen tot 2 jaar: Yahoo 1h data -> resample naar 10m
    3. Optioneel: Bux graph API data als aanvulling (beperkte historie in app)
    """
    end = config.end_date
    start = config.start_date
    frames: list[pd.DataFrame] = []

    symbol = yahoo_symbol or isin_to_yahoo_ticker(
        instrument.isin,
        known_ticker=instrument.ticker,
        exchange=instrument.exchange,
        config=config,
    )

    if symbol:
        recent_start = end - timedelta(days=59)
        try:
            df_5m = fetch_yfinance_intraday(symbol, recent_start, end, interval="5m")
            if not df_5m.empty:
                df_10m = resample_to_10m(df_5m)
                frames.append(df_10m)
                logger.debug("%s: %d 10m bars uit 5m data (60 dagen)", symbol, len(df_10m))
        except Exception as exc:
            logger.debug("5m fetch mislukt voor %s: %s", symbol, exc)

        hourly_start = max(start, end - timedelta(days=729))
        hourly_end = end - timedelta(days=59)
        if hourly_start < hourly_end:
            try:
                df_1h = fetch_yfinance_intraday(symbol, hourly_start, hourly_end, interval="1h")
                if not df_1h.empty:
                    df_10m = resample_to_10m(df_1h)
                    frames.append(df_10m)
                    logger.debug("%s: %d 10m bars uit 1h data", symbol, len(df_10m))
            except Exception as exc:
                logger.debug("1h fetch mislukt voor %s: %s", symbol, exc)

        time.sleep(config.request_delay)
    else:
        logger.warning("Geen Yahoo ticker voor %s (%s)", instrument.isin, instrument.name)

    if config.bux_token:
        try:
            api = bux.UserAPI(token=config.bux_token)
            presentation = api.security(instrument.isin).presentation().requests()
            for graph_type in presentation.graph_types:
                df_bux = fetch_bux_graph(instrument.isin, graph_type, config)
                if not df_bux.empty:
                    frames.append(resample_to_10m(df_bux))
            time.sleep(config.request_delay)
        except Exception as exc:
            logger.debug("Bux graph mislukt voor %s: %s", instrument.isin, exc)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="first")]
    combined = combined.sort_index()
    combined = combined[(combined.index >= start) & (combined.index <= end)]

    combined["isin"] = instrument.isin
    combined["name"] = instrument.name
    combined["ticker"] = instrument.ticker or symbol

    return combined
