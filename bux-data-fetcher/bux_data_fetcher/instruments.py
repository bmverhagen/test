from __future__ import annotations

import html
import logging
import re
import string
import time
from dataclasses import asdict, dataclass
from typing import Iterable

import bux
import requests

from .config import Config

logger = logging.getLogger(__name__)

PRODUCT_LIST_URL = "https://bux.com/knowledge-centre/product-list/"
PRODUCT_API_URL = "https://bux.com/wp-json/vo/v1/post"

PRODUCT_ITEM_RE = re.compile(
    r'<div class="product-item[^"]*">.*?'
    r'<div class="product-item__title h4">\s*(.*?)\s*</div>.*?'
    r'<div class="product-item__short-name">\s*(.*?)\s*</div>',
    re.DOTALL,
)


@dataclass
class Instrument:
    isin: str
    name: str
    ticker: str | None = None
    security_type: str | None = None
    exchange: str | None = None
    country_code: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
            "Referer": PRODUCT_LIST_URL,
            "Origin": "https://bux.com",
        }
    )
    return session


def _parse_product_html(html_text: str, source: str) -> list[Instrument]:
    instruments: list[Instrument] = []
    seen: set[str] = set()

    for raw_name, raw_isin in PRODUCT_ITEM_RE.findall(html_text):
        name = html.unescape(re.sub(r"\s+", " ", raw_name.strip()))
        isin = raw_isin.strip()
        if not isin or isin in seen:
            continue
        seen.add(isin)
        instruments.append(Instrument(isin=isin, name=name, source=source))

    return instruments


def fetch_instruments_from_website(config: Config) -> list[Instrument]:
    """Haal producten op via de Bux kennisbank productlijst."""
    session = _session()
    instruments: dict[str, Instrument] = {}

    response = session.get(PRODUCT_LIST_URL, timeout=30)
    response.raise_for_status()
    for item in _parse_product_html(response.text, "bux_website_initial"):
        instruments[item.isin] = item

    for letter in list(string.ascii_lowercase) + ["#"]:
        try:
            api_response = session.post(
                PRODUCT_API_URL,
                data={"type": "vo_product", "search": "", "letter": letter},
                timeout=30,
            )
            if api_response.status_code != 200:
                logger.debug("Letter %s: HTTP %s", letter, api_response.status_code)
                continue

            payload = api_response.json()
            for item in _parse_product_html(payload.get("html", ""), f"bux_website_{letter}"):
                instruments[item.isin] = item
        except (requests.RequestException, ValueError) as exc:
            logger.debug("Letter %s mislukt: %s", letter, exc)

        time.sleep(config.request_delay)

    logger.info("Website scrape: %d unieke instrumenten", len(instruments))
    return list(instruments.values())


def _collect_from_securities(securities: Iterable, source: str) -> list[Instrument]:
    result: list[Instrument] = []
    for sec in securities:
        isin = getattr(sec, "id", None) or sec.get("id")
        if not isin:
            continue
        result.append(
            Instrument(
                isin=isin,
                name=getattr(sec, "name", None) or sec.get("name", ""),
                ticker=getattr(sec, "ticker_code", None) or sec.get("tickerCode"),
                security_type=getattr(sec, "security_type", None) or sec.get("securityType"),
                source=source,
            )
        )
    return result


def fetch_instruments_from_bux_api(config: Config) -> list[Instrument]:
    """Haal alle verhandelbare producten op via de Bux Zero API."""
    if not config.bux_token:
        raise ValueError("BUX_TOKEN is vereist voor API-instrumenten ophalen")

    api = bux.UserAPI(token=config.bux_token)
    instruments: dict[str, Instrument] = {}

    def add(items: Iterable[Instrument]) -> None:
        for item in items:
            instruments[item.isin] = item

    for name, fetcher in [
        ("usa", lambda: api.securities().usa().requests()),
        ("etf", lambda: api.securities().etfs().requests()),
        ("new", lambda: api.securities().filter_new().requests()),
    ]:
        try:
            data = fetcher()
            stocks = data if isinstance(data, list) else getattr(data, "stocks", [])
            add(_collect_from_securities(stocks, f"bux_api_{name}"))
            time.sleep(config.request_delay)
        except Exception as exc:
            logger.warning("Kon %s lijst niet ophalen: %s", name, exc)

    try:
        countries = api.securities().countries().requests()
        for country in countries:
            try:
                matches = api.securities().filter_tag(country.id).requests()
                add(_collect_from_securities(matches.stocks, f"bux_api_country_{country.id}"))
                time.sleep(config.request_delay)
            except Exception as exc:
                logger.debug("Land %s mislukt: %s", country.id, exc)
    except Exception as exc:
        logger.warning("Kon landen niet ophalen: %s", exc)

    try:
        tags = api.securities().featured_tags().requests()
        for tag in tags:
            try:
                matches = api.securities().filter_tag(tag.id).requests()
                add(_collect_from_securities(matches.stocks, f"bux_api_tag_{tag.id}"))
                time.sleep(config.request_delay)
            except Exception as exc:
                logger.debug("Tag %s mislukt: %s", tag.id, exc)
    except Exception as exc:
        logger.warning("Kon tags niet ophalen: %s", exc)

    search_chars = string.ascii_lowercase + string.digits
    for char in search_chars:
        try:
            results = api.search(char).requests()
            for sec in results.eqty + results.etf:
                isin = sec.id
                instruments[isin] = Instrument(
                    isin=isin,
                    name=sec.name,
                    ticker=sec.ticker_code,
                    security_type=sec.security_type,
                    country_code=sec.country_code,
                    source=f"bux_api_search_{char}",
                )
            time.sleep(config.request_delay)
        except Exception as exc:
            logger.debug("Zoek %s mislukt: %s", char, exc)

    for isin in list(instruments.keys()):
        try:
            info = api.security(isin).presentation().requests()
            inst = instruments[isin]
            instruments[isin] = Instrument(
                isin=isin,
                name=info.name,
                ticker=info.ticker_code,
                security_type=info.security_type,
                exchange=info.exchange_id,
                country_code=info.country_code,
                source=inst.source,
            )
            time.sleep(config.request_delay / 2)
        except Exception:
            pass

    logger.info("Bux API: %d unieke instrumenten", len(instruments))
    return list(instruments.values())


def fetch_all_instruments(config: Config) -> list[Instrument]:
    """Combineer alle beschikbare bronnen voor een zo compleet mogelijke lijst."""
    merged: dict[str, Instrument] = {}

    try:
        for item in fetch_instruments_from_website(config):
            merged[item.isin] = item
    except Exception as exc:
        logger.warning("Website scrape mislukt: %s", exc)

    if config.bux_token:
        try:
            for item in fetch_instruments_from_bux_api(config):
                existing = merged.get(item.isin)
                if existing:
                    merged[item.isin] = Instrument(
                        isin=item.isin,
                        name=item.name or existing.name,
                        ticker=item.ticker or existing.ticker,
                        security_type=item.security_type or existing.security_type,
                        exchange=item.exchange or existing.exchange,
                        country_code=item.country_code or existing.country_code,
                        source=f"{existing.source}+{item.source}",
                    )
                else:
                    merged[item.isin] = item
        except Exception as exc:
            logger.error("Bux API instrumenten ophalen mislukt: %s", exc)
            if not merged:
                raise
    elif not merged:
        raise ValueError(
            "Geen instrumenten gevonden. Stel BUX_TOKEN in (python3 -m bux get-token) "
            "of controleer netwerktoegang tot bux.com."
        )

    return sorted(merged.values(), key=lambda x: x.name.lower())
