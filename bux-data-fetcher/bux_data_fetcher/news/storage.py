from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from ..config import Config

logger = logging.getLogger(__name__)


def news_dir(config: Config) -> Path:
    return config.output_dir / "news"


def news_path(config: Config, isin: str) -> Path:
    safe = isin.replace("/", "_")
    return news_dir(config) / f"{safe}.parquet"


def save_news(articles: list, config: Config, isin: str) -> Path | None:
    if not articles:
        return None
    out_dir = news_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = news_path(config, isin)
    df = pd.DataFrame([a.to_dict() for a in articles])
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    df.to_parquet(path, index=False)
    logger.info("Nieuws opgeslagen: %s (%d artikelen)", path, len(df))
    return path


def load_news(config: Config, isin: str) -> list:
    from .scraper import NewsArticle

    path = news_path(config, isin)
    if not path.exists():
        return []

    df = pd.read_parquet(path)
    articles = []
    for _, row in df.iterrows():
        pub = row["published_at"]
        if hasattr(pub, "to_pydatetime"):
            pub = pub.to_pydatetime()
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=__import__("datetime").timezone.utc)

        articles.append(
            NewsArticle(
                isin=row["isin"],
                ticker=row.get("ticker") if pd.notna(row.get("ticker")) else None,
                name=row["name"],
                title=row["title"],
                url=row["url"],
                source=row.get("source", ""),
                published_at=pub,
                sentiment=float(row.get("sentiment", 0)),
                query=row.get("query", ""),
                scraper=row.get("scraper", ""),
            )
        )
    return articles


def load_news_progress(config: Config) -> set[str]:
    progress_file = config.output_dir / "news_progress.json"
    if not progress_file.exists():
        return set()
    with open(progress_file) as f:
        return set(json.load(f).get("completed", []))


def save_news_progress(config: Config, completed: set[str]) -> None:
    progress_file = config.output_dir / "news_progress.json"
    config.output_dir.mkdir(parents=True, exist_ok=True)
    with open(progress_file, "w") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)
