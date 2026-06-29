from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from nu_nl_scraper.models import Article

API_URL = "https://www.nu.nl/block/lean_json/articlelist"


def build_articlelist_url(
    *,
    limit: int = 20,
    offset: int = 0,
    source: str = "latest",
    filter_type: str = "site",
    section: str | None = None,
) -> str:
    params: dict[str, str | int] = {
        "limit": limit,
        "offset": offset,
        "source": source,
        "filter": filter_type,
    }
    if filter_type == "section" and section:
        params["section"] = section
    return f"{API_URL}?{urlencode(params)}"


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_articlelist_payload(payload: dict[str, Any], source_url: str) -> list[Article]:
    context = payload.get("data", {}).get("context", {})
    raw_articles = context.get("articles", [])
    if not isinstance(raw_articles, list):
        return []

    articles: list[Article] = []
    for raw in raw_articles:
        if not isinstance(raw, dict):
            continue

        title = _first_str(raw, "title", "headline")
        url = _first_str(raw, "url", "link", "uri")
        if not title or not url:
            continue

        article_id = _first_str(raw, "id", "articleId", "article_id")
        if article_id and article_id.startswith("article-"):
            article_id = article_id.removeprefix("article-")

        image = raw.get("image")
        image_url = None
        if isinstance(image, dict):
            image_url = _first_str(image, "url", "src")
        elif isinstance(image, str):
            image_url = image

        published_at = _parse_timestamp(
            raw.get("publicationDate")
            or raw.get("publishedAt")
            or raw.get("publication_date")
            or raw.get("date")
        )

        articles.append(
            Article(
                title=title,
                url=url,
                article_id=article_id,
                summary=_first_str(raw, "summary", "description", "intro"),
                category=_first_str(raw, "section", "category"),
                published_at=published_at,
                image_url=image_url,
                image_credit=_first_str(raw, "imageCredit", "image_credit"),
                source="api",
                extra={"feed_url": source_url, "raw": raw},
            )
        )

    return articles
