from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import quote

import feedparser
import requests
import yfinance as yf

from ..config import Config
from ..instruments import Instrument
from ..strategy.news_sentiment import aggregate_sentiment, score_headline

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class NewsArticle:
    isin: str
    ticker: str | None
    name: str
    title: str
    url: str
    source: str
    published_at: datetime
    sentiment: float
    query: str
    scraper: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat()
        return d

    @property
    def id(self) -> str:
        raw = f"{self.url}|{self.title}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean_title(title: str, source: str = "") -> str:
    title = re.sub(r"\s+", " ", title.strip())
    if source and title.endswith(f" - {source}"):
        title = title[: -(len(source) + 3)].strip()
    return title


def build_search_queries(instrument: Instrument, yahoo_ticker: str | None = None) -> list[str]:
    """Genereer Google News zoekqueries voor een instrument."""
    queries: list[str] = []
    name = instrument.name.strip()
    ticker = (yahoo_ticker or instrument.ticker or "").strip()

    # Verwijder juridische suffixen
    clean_name = re.sub(
        r"\s+(Inc\.?|Corp\.?|Corporation|Ltd\.?|PLC|AG|SA|NV|N\.V\.|SE|SpA|S\.A\.|B\.V\.)$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()

    if ticker:
        base_ticker = ticker.split(".")[0]
        queries.append(f"{base_ticker} stock")
        queries.append(f'"{base_ticker}" stock')

    if clean_name and clean_name.lower() not in {ticker.lower() for ticker in [ticker] if ticker}:
        queries.append(f'"{clean_name}" stock')
        if len(clean_name.split()) <= 4:
            queries.append(f"{clean_name} stock")

    # Dedupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


def _google_news_rss_url(query: str, *, start: datetime, end: datetime, lang: str = "en-US") -> str:
    date_filter = f"after:{start.strftime('%Y-%m-%d')}+before:{end.strftime('%Y-%m-%d')}"
    full_query = f"{query} {date_filter}"
    gl = "US" if lang.endswith("US") else lang.split("-")[-1]
    ceid = f"{gl}:{lang.split('-')[0]}"
    return (
        f"{GOOGLE_NEWS_RSS}?q={quote(full_query)}"
        f"&hl={lang}&gl={gl}&ceid={quote(ceid)}"
    )


def scrape_google_news_month(
    query: str,
    *,
    start: datetime,
    end: datetime,
    lang: str = "en-US",
    session: requests.Session | None = None,
) -> list[dict]:
    """Scrape één maand Google News via RSS."""
    url = _google_news_rss_url(query, start=start, end=end, lang=lang)
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.RequestException as exc:
        logger.debug("Google News fetch mislukt (%s): %s", query[:40], exc)
        return []

    articles = []
    for entry in feed.entries:
        source = ""
        if hasattr(entry, "source") and entry.source:
            source = getattr(entry.source, "title", str(entry.source))

        title = _clean_title(entry.get("title", ""), source)
        pub = _parse_pubdate(entry.get("published") or entry.get("updated"))
        link = entry.get("link", "")

        if not title or not pub or not link:
            continue
        if pub < start or pub >= end:
            continue

        articles.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": pub,
                "query": query,
                "scraper": "google_news_rss",
            }
        )

    return articles


def scrape_google_news_historical(
    queries: Iterable[str],
    *,
    start: datetime,
    end: datetime,
    lang: str = "en-US",
    delay: float = 0.5,
) -> list[dict]:
    """Scrape historisch nieuws in maandelijkse chunks (2 jaar)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    all_articles: dict[str, dict] = {}

    # Recency queries (meer resultaten voor recente periode)
    for when in ("7d", "30d", "1y"):
        for query in queries:
            url = (
                f"{GOOGLE_NEWS_RSS}?q={quote(f'{query} when:{when}')}"
                f"&hl={lang}&gl={'US' if lang.endswith('US') else lang.split('-')[-1]}"
                f"&ceid={quote('US:en' if lang.endswith('US') else f'{lang.split('-')[-1]}:{lang.split('-')[0]}')}"
            )
            try:
                feed = feedparser.parse(session.get(url, timeout=30).content)
                for entry in feed.entries:
                    source = getattr(getattr(entry, "source", None), "title", "")
                    title = _clean_title(entry.get("title", ""), source)
                    pub = _parse_pubdate(entry.get("published") or entry.get("updated"))
                    link = entry.get("link", "")
                    if title and pub and link and start <= pub <= end:
                        all_articles[link] = {
                            "title": title,
                            "url": link,
                            "source": source,
                            "published_at": pub,
                            "query": query,
                            "scraper": "google_news_rss",
                        }
            except requests.RequestException:
                pass
            time.sleep(delay / 2)

    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=90), end)

        for query in queries:
            batch = scrape_google_news_month(
                query,
                start=chunk_start,
                end=chunk_end,
                lang=lang,
                session=session,
            )
            for art in batch:
                all_articles[art["url"]] = art

            time.sleep(delay)

        chunk_start = chunk_end

    return list(all_articles.values())


def scrape_yahoo_finance_news(ticker: str) -> list[dict]:
    """Haal recent Yahoo Finance nieuws op via yfinance (max ~10-20 artikelen)."""
    articles = []
    try:
        news = yf.Ticker(ticker).news or []
    except Exception as exc:
        logger.debug("yfinance news mislukt voor %s: %s", ticker, exc)
        return []

    for item in news:
        content = item.get("content", item)
        title = content.get("title", "")
        pub_str = content.get("pubDate") or content.get("displayTime")
        if not title or not pub_str:
            continue

        try:
            pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue

        url = ""
        for key in ("clickThroughUrl", "canonicalUrl"):
            url_obj = content.get(key)
            if isinstance(url_obj, dict) and url_obj.get("url"):
                url = url_obj["url"]
                break

        provider_obj = content.get("provider") or {}
        provider = provider_obj.get("displayName", "Yahoo Finance") if isinstance(provider_obj, dict) else "Yahoo Finance"
        articles.append(
            {
                "title": title,
                "url": url or f"yahoo://news/{item.get('id', '')}",
                "source": provider,
                "published_at": pub,
                "query": ticker,
                "scraper": "yfinance",
            }
        )

    return articles


def fetch_news_for_instrument(
    instrument: Instrument,
    config: Config,
    *,
    yahoo_ticker: str | None = None,
    years: int = 2,
    langs: list[str] | None = None,
) -> list[NewsArticle]:
    """Haal historisch + recent nieuws op voor één instrument."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=years * 365)
    langs = langs or ["en-US"]

    queries = build_search_queries(instrument, yahoo_ticker)
    if not queries:
        logger.warning("Geen zoekqueries voor %s", instrument.isin)
        return []

    raw_articles: dict[str, dict] = {}

    for lang in langs:
        batch = scrape_google_news_historical(
            queries,
            start=start,
            end=end,
            lang=lang,
            delay=config.request_delay,
        )
        for art in batch:
            raw_articles[art["url"]] = art

    if yahoo_ticker:
        for art in scrape_yahoo_finance_news(yahoo_ticker):
            raw_articles[art["url"]] = art
        time.sleep(config.request_delay)

    results: list[NewsArticle] = []
    for art in raw_articles.values():
        pub: datetime = art["published_at"]
        if pub < start or pub > end:
            continue

        results.append(
            NewsArticle(
                isin=instrument.isin,
                ticker=yahoo_ticker or instrument.ticker,
                name=instrument.name,
                title=art["title"],
                url=art["url"],
                source=art["source"],
                published_at=pub,
                sentiment=score_headline(art["title"]),
                query=art["query"],
                scraper=art["scraper"],
            )
        )

    results.sort(key=lambda a: a.published_at)
    logger.info(
        "%s (%s): %d nieuwsartikelen",
        instrument.ticker or instrument.isin,
        instrument.name[:30],
        len(results),
    )
    return results


def sentiment_around_time(
    articles: list[NewsArticle],
    timestamp: datetime,
    *,
    lookback_hours: int = 48,
) -> float:
    """Gemiddeld sentiment van nieuws in venster vóór timestamp."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    window_start = timestamp - timedelta(hours=lookback_hours)
    relevant = [
        a for a in articles
        if window_start <= a.published_at <= timestamp
    ]
    if not relevant:
        return 0.0
    return aggregate_sentiment([a.title for a in relevant])


def negative_news_before(
    articles: list[NewsArticle],
    timestamp: datetime,
    *,
    lookback_hours: int = 48,
    threshold: float = 0.3,
) -> bool:
    """True als er negatief nieuws was in lookback venster."""
    score = sentiment_around_time(articles, timestamp, lookback_hours=lookback_hours)
    return score <= -threshold
