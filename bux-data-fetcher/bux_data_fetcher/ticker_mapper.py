from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

from .config import Config

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

EXCHANGE_SUFFIX = {
    "XAMS": ".AS",
    "XETR": ".DE",
    "XPAR": ".PA",
    "XMIL": ".MI",
    "XMAD": ".MC",
    "XBRU": ".BR",
    "XLIS": ".LS",
    "XSWX": ".SW",
    "XSTO": ".ST",
    "XCSE": ".CO",
    "XHEL": ".HE",
    "XWAR": ".WA",
    "XWBO": ".VI",
    "XDUB": ".IR",
    "XLON": ".L",
}

# OpenFIGI exchCode -> Yahoo Finance suffix
OPENFIGI_EXCHANGE_SUFFIX = {
    "US": "",
    "UA": "",
    "UN": "",
    "UW": "",
    "UR": "",
    "UQ": "",
    "UF": "",
    "UB": "",
    "GR": ".DE",
    "GF": ".DE",
    "GD": ".DE",
    "GY": ".DE",
    "GS": ".DE",
    "GA": ".DE",
    "GT": ".DE",
    "NA": ".AS",
    "NL": ".AS",
    "FP": ".PA",
    "IM": ".MI",
    "SM": ".MC",
    "BB": ".BR",
    "PL": ".LS",
    "SW": ".SW",
    "SS": ".ST",
    "DC": ".CO",
    "FH": ".HE",
    "PW": ".WA",
    "AV": ".VI",
    "ID": ".IR",
    "LN": ".L",
    "LO": ".L",
}


def _openfigi_lookup(isins: list[str], api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    mapping: dict[str, str] = {}
    batch_size = 100

    for i in range(0, len(isins), batch_size):
        batch = isins[i : i + batch_size]
        payload = [{"idType": "ID_ISIN", "idValue": isin} for isin in batch]

        try:
            response = requests.post(OPENFIGI_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            results = response.json()
        except requests.RequestException as exc:
            logger.warning("OpenFIGI batch mislukt: %s", exc)
            time.sleep(1)
            continue

        for isin, result in zip(batch, results):
            data = result.get("data")
            if not data:
                continue
            entry = next((d for d in data if d.get("exchCode") == "US"), data[0])
            ticker = entry.get("ticker")
            exch = entry.get("exchCode", "")
            if ticker:
                suffix = OPENFIGI_EXCHANGE_SUFFIX.get(exch, EXCHANGE_SUFFIX.get(exch, ""))
                if suffix and not ticker.endswith(suffix):
                    mapping[isin] = f"{ticker}{suffix}"
                else:
                    mapping[isin] = ticker

        time.sleep(0.5)

    return mapping


def isin_to_yahoo_ticker(
    isin: str,
    *,
    known_ticker: str | None = None,
    exchange: str | None = None,
    config: Config | None = None,
) -> str | None:
    """Map ISIN naar Yahoo Finance symbool."""
    if known_ticker is not None and str(known_ticker).strip() not in ("", "nan", "None"):
        ticker = str(known_ticker).strip()
        if exchange and exchange in EXCHANGE_SUFFIX:
            suffix = EXCHANGE_SUFFIX[exchange]
            if not ticker.endswith(suffix):
                return f"{ticker}{suffix}"
        if isin.startswith("US") and "." not in ticker:
            return ticker
        if not isin.startswith("US") and "." not in ticker and exchange:
            suffix = EXCHANGE_SUFFIX.get(exchange, "")
            if suffix:
                return f"{ticker}{suffix}"
        return ticker

    if config:
        cache = getattr(isin_to_yahoo_ticker, "_cache", None)
        if cache is None:
            isin_to_yahoo_ticker._cache = {}
            cache = isin_to_yahoo_ticker._cache
        if isin in cache:
            return cache[isin]

        result = _openfigi_lookup([isin], config.openfigi_api_key).get(isin)
        cache[isin] = result
        return result

    return None


def bulk_isin_to_yahoo(instruments: Iterable, config: Config) -> dict[str, str]:
    """Bulk ISIN -> Yahoo ticker mapping via OpenFIGI."""
    to_lookup: list[str] = []
    result: dict[str, str] = {}

    for inst in instruments:
        if inst.ticker and str(inst.ticker).strip():
            mapped = isin_to_yahoo_ticker(
                inst.isin,
                known_ticker=inst.ticker,
                exchange=inst.exchange,
            )
            if mapped:
                result[inst.isin] = mapped
                continue
        to_lookup.append(inst.isin)

    if to_lookup:
        figi_map = _openfigi_lookup(to_lookup, config.openfigi_api_key)
        result.update(figi_map)

    logger.info("Ticker mapping: %d instrumenten met Yahoo symbool", len(result))
    return result
