from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from xml.etree import ElementTree as ET

from nu_nl_scraper.models import Article

BASE_URL = "https://www.nu.nl"
DEFAULT_RSS_URL = f"{BASE_URL}/rss"

KNOWN_CATEGORIES = (
    "achterklap",
    "algemeen",
    "binnenland",
    "buitenland",
    "economie",
    "misdaad",
    "muziek",
    "nujij",
    "schaatsen",
    "sport-overig",
    "tech",
    "tennis",
    "videos",
    "voetbal",
    "wk-voetbal",
)

ARTICLE_ID_RE = re.compile(r"/(\d+)/")


def rss_url_for_category(category: str | None = None) -> str:
    if not category:
        return DEFAULT_RSS_URL
    return f"{BASE_URL}/rss/{category.strip().lower()}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    text = (element.text or "").strip()
    return text or None


def _parse_pub_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _article_id_from_url(url: str, guid: str | None = None) -> str | None:
    if guid and guid.startswith("article-"):
        return guid.removeprefix("article-")
    match = ARTICLE_ID_RE.search(url)
    return match.group(1) if match else None


def parse_rss(xml_text: str, source_url: str) -> list[Article]:
    root = ET.fromstring(xml_text)
    articles: list[Article] = []

    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue

        fields: dict[str, ET.Element | None] = {}
        for child in item:
            fields[_local_name(child.tag)] = child

        title = _text(fields.get("title"))
        link = _text(fields.get("link"))
        if not title or not link:
            continue

        guid = _text(fields.get("guid"))
        enclosure = fields.get("enclosure")
        image_url = enclosure.attrib.get("url") if enclosure is not None else None

        articles.append(
            Article(
                title=title,
                url=link,
                article_id=_article_id_from_url(link, guid),
                summary=_text(fields.get("description")),
                category=_text(fields.get("category")),
                published_at=_parse_pub_date(_text(fields.get("pubDate"))),
                image_url=image_url,
                image_credit=_text(fields.get("rights")),
                source="rss",
                extra={"feed_url": source_url},
            )
        )

    return articles


def deduplicate_articles(articles: Iterable[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        key = article.article_id or article.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique
