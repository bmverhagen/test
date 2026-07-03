from __future__ import annotations

import io
import logging
import random
from dataclasses import dataclass

import pandas as pd
import requests

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Fallback als externe bronnen falen
FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JNJ",
    "V", "XOM", "JPM", "WMT", "MA", "PG", "HD", "CVX", "MRK", "ABBV",
    "KO", "PEP", "COST", "AVGO", "MCD", "TMO", "CSCO", "ACN", "ABT", "DHR",
    "LIN", "ADBE", "NKE", "TXN", "NEE", "PM", "CRM", "WFC", "DIS", "BMY",
    "RTX", "UPS", "HON", "QCOM", "INTC", "AMGN", "IBM", "LOW", "SPGI", "CAT",
    "GE", "BA", "GS", "AMD", "DE", "BLK", "SYK", "MDT", "GILD", "AXP",
    "ISRG", "TJX", "VRTX", "REGN", "LMT", "BKNG", "ADI", "MMC", "CI", "PLD",
    "CB", "SO", "DUK", "ZTS", "MO", "PNC", "USB", "CME", "BDX", "EOG",
    "SLB", "NOC", "ITW", "HCA", "CSX", "CL", "APD", "MCK", "FIS", "COP",
    "TGT", "AON", "FCX", "GM", "F", "PYPL", "SQ", "SNAP", "ROKU", "PLTR",
    "ASML", "SAP", "NVO", "AZN", "SHEL", "HSBC", "UL", "BP", "RIO", "BHP",
    "TM", "SONY", "HMC", "SHOP", "MELI", "SE", "BABA", "JD", "PDD", "NIO",
]


@dataclass(frozen=True)
class YahooInstrument:
    """Pseudo-instrument zonder Bux/ISIN — ticker is de sleutel."""

    ticker: str
    name: str
    exchange: str
    region: str

    @property
    def isin(self) -> str:
        """Gebruik ticker als ID in parquet bestandsnaam."""
        return self.ticker.replace("/", "_").replace(".", "_")

    def to_dict(self) -> dict:
        return {
            "isin": self.isin,
            "name": self.name,
            "ticker": self.ticker,
            "security_type": "stock",
            "exchange": self.exchange,
            "country_code": self.region,
            "source": "yahoo",
        }


def _read_wikipedia_table(url: str, symbol_col: str = "Symbol") -> list[str]:
    tables = pd.read_html(url)
    for table in tables:
        for col in (symbol_col, "Ticker", "EPIC"):
            if col in table.columns:
                symbols = table[col].astype(str).str.strip()
                symbols = symbols.str.replace(".", "-", regex=False)
                return [s for s in symbols if s and s != "nan"]
    return []


def _fetch_symbol_file(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.text.strip()
    lines = text.splitlines()
    # Laatste regel is File Creation Time
    data = "\n".join(lines[:-1])
    return pd.read_csv(io.StringIO(data), sep="|")


def _clean_equity_symbols(symbols: pd.Series, names: pd.Series | None = None) -> list[str]:
    skip_name = (
        r"Preferred|Warrant|Units?|Rights|Notes|Debenture|ETF|Fund|Trust|Acquisition"
    )
    out: list[str] = []
    for i, raw in enumerate(symbols):
        if pd.isna(raw):
            continue
        s = str(raw).strip().upper()
        if not s or s in ("NAN", "SYMBOL"):
            continue
        if "=" in s or "+" in s or "$" in s or "^" in s or "/" in s or " " in s:
            continue
        if names is not None and i < len(names):
            name = str(names.iloc[i]) if hasattr(names, "iloc") else str(names[i])
            if pd.notna(name) and pd.Series([name]).str.contains(skip_name, case=False, regex=True).iloc[0]:
                continue
        # Alleen common stock tickers (1-5 chars, optioneel één hyphen)
        base = s.replace("-", "")
        if not base.isalnum() or len(s) > 5:
            continue
        if s.count("-") > 1:
            continue
        out.append(s)
    return out


def fetch_nasdaq_trader_universe() -> list[str]:
    """NASDAQ + NYSE/AMEX common stocks via officiële symbol directory (geen token)."""
    tickers: list[str] = []
    try:
        nasdaq = _fetch_symbol_file(NASDAQ_LISTED_URL)
        mask = (
            nasdaq["Test Issue"].astype(str).str.upper().eq("N")
            & nasdaq["ETF"].astype(str).str.upper().eq("N")
        )
        tickers.extend(
            _clean_equity_symbols(
                nasdaq.loc[mask, "Symbol"],
                nasdaq.loc[mask, "Security Name"],
            )
        )
        logger.info("NASDAQ listed: %d equities", len(tickers))
    except Exception as exc:
        logger.warning("NASDAQ symbol file mislukt: %s", exc)

    try:
        other = _fetch_symbol_file(OTHER_LISTED_URL)
        mask = (
            other["Test Issue"].astype(str).str.upper().eq("N")
            & other["ETF"].astype(str).str.upper().eq("N")
        )
        col = "NASDAQ Symbol" if "NASDAQ Symbol" in other.columns else "ACT Symbol"
        name_col = "Security Name" if "Security Name" in other.columns else None
        nyse = _clean_equity_symbols(
            other.loc[mask, col],
            other.loc[mask, name_col] if name_col else None,
        )
        tickers.extend(nyse)
        logger.info("NYSE/AMEX listed: +%d equities", len(nyse))
    except Exception as exc:
        logger.warning("Other listed symbol file mislukt: %s", exc)

    return tickers


def fetch_sp500_tickers() -> list[str]:
    try:
        tickers = _read_wikipedia_table(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )
        logger.info("S&P 500: %d tickers", len(tickers))
        return tickers
    except Exception as exc:
        logger.warning("S&P 500 Wikipedia mislukt: %s", exc)
        return []


def fetch_nasdaq100_tickers() -> list[str]:
    try:
        tickers = _read_wikipedia_table(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            symbol_col="Ticker",
        )
        logger.info("NASDAQ-100: %d tickers", len(tickers))
        return tickers
    except Exception as exc:
        logger.warning("NASDAQ-100 Wikipedia mislukt: %s", exc)
        return []


def fetch_ftse100_tickers() -> list[str]:
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/FTSE_100_Index")
        for table in tables:
            if "EPIC" in table.columns:
                tickers = table["EPIC"].astype(str).str.strip()
                tickers = tickers + ".L"
                return [t for t in tickers if t and t != "nan"]
        return []
    except Exception as exc:
        logger.warning("FTSE 100 Wikipedia mislukt: %s", exc)
        return []


def fetch_dax_tickers() -> list[str]:
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/DAX")
        for table in tables:
            if "Ticker" in table.columns:
                tickers = table["Ticker"].astype(str).str.strip()
                tickers = tickers + ".DE"
                return [t for t in tickers if t and t != "nan"]
        return []
    except Exception as exc:
        logger.warning("DAX Wikipedia mislukt: %s", exc)
        return []


def build_universe() -> list[str]:
    """Combineer publieke bronnen tot ticker universe (geen Bux token)."""
    parts = [
        fetch_nasdaq_trader_universe(),
        fetch_sp500_tickers(),
        fetch_nasdaq100_tickers(),
        fetch_ftse100_tickers(),
        fetch_dax_tickers(),
        FALLBACK_TICKERS,
    ]
    seen: set[str] = set()
    universe: list[str] = []
    for group in parts:
        for ticker in group:
            t = ticker.upper().strip()
            if t and t not in seen:
                seen.add(t)
                universe.append(ticker.strip())
    return universe


def sample_random_tickers(
    count: int = 100,
    *,
    seed: int = 42,
    universe: list[str] | None = None,
) -> list[str]:
    """Kies N willekeurige tickers uit universe."""
    pool = universe or build_universe()
    if not pool:
        pool = FALLBACK_TICKERS
    rng = random.Random(seed)
    n = min(count, len(pool))
    return sorted(rng.sample(pool, n))


def to_instruments(tickers: list[str]) -> list[YahooInstrument]:
    return [
        YahooInstrument(
            ticker=t,
            name=t,
            exchange="YAHOO",
            region="US" if "." not in t else t.split(".")[-1],
        )
        for t in tickers
    ]
