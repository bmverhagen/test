#!/usr/bin/env python3
"""Scrape artikelen van NOS.nl via RSS-feeds en JSON-LD metadata."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import feedparser
import requests

USER_AGENT = "NOS-Artikel-Scraper/1.0 (+https://github.com/bmverhagen/test)"
DEFAULT_FEEDS = [
    "https://feeds.nos.nl/nosnieuwsalgemeen",
    "https://feeds.nos.nl/nosnieuwsbinnenland",
    "https://feeds.nos.nl/nosnieuwsbuitenland",
    "https://feeds.nos.nl/nosnieuwspolitiek",
    "https://feeds.nos.nl/nosnieuwseconomie",
    "https://feeds.nos.nl/nosnieuwsopmerkelijk",
    "https://feeds.nos.nl/nosnieuwskoningshuis",
    "https://feeds.nos.nl/nosnieuwscultuurenmedia",
    "https://feeds.nos.nl/nosnieuwstech",
    "https://feeds.nos.nl/nossportalgemeen",
    "https://feeds.nos.nl/nosvoetbal",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_json_ld(html: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None

    data = json.loads(match.group(1))
    graph = data.get("@graph", [data])
    for item in graph:
        if item.get("@type") == "NewsArticle":
            return item
    return None


def fetch_article(url: str, delay: float) -> dict[str, Any] | None:
    time.sleep(delay)
    response = SESSION.get(url, timeout=30, allow_redirects=True)
    response.raise_for_status()

    article = parse_json_ld(response.text)
    if not article:
        return None

    keywords = article.get("keywords")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    image = article.get("image")
    if isinstance(image, dict):
        image = image.get("url")

    return {
        "url": response.url,
        "titel": article.get("headline") or article.get("name"),
        "samenvatting": article.get("description"),
        "inhoud": article.get("articleBody"),
        "sectie": article.get("articleSection"),
        "trefwoorden": keywords or [],
        "afbeelding": image,
        "gepubliceerd": article.get("datePublished"),
        "bijgewerkt": article.get("dateModified"),
    }


def collect_feed_items(feed_url: str) -> list[dict[str, str]]:
    parsed = feedparser.parse(feed_url, agent=USER_AGENT)
    items: list[dict[str, str]] = []

    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue

        items.append(
            {
                "feed": feed_url,
                "feed_titel": parsed.feed.get("title", feed_url),
                "link": link,
                "titel": entry.get("title", ""),
                "samenvatting_rss": strip_html(entry.get("summary", "")),
                "gepubliceerd_rss": entry.get("published", ""),
            }
        )

    return items


def scrape(
    feeds: list[str],
    limit_per_feed: int | None,
    delay: float,
    fetch_full: bool,
) -> list[dict[str, Any]]:
    seen_links: set[str] = set()
    articles: list[dict[str, Any]] = []

    for feed_url in feeds:
        print(f"Feed ophalen: {feed_url}")
        try:
            feed_items = collect_feed_items(feed_url)
        except Exception as exc:
            print(f"  Fout bij feed {feed_url}: {exc}")
            continue

        if limit_per_feed is not None:
            feed_items = feed_items[:limit_per_feed]

        print(f"  {len(feed_items)} artikelen gevonden")

        for item in feed_items:
            link = item["link"]
            if link in seen_links:
                continue
            seen_links.add(link)

            article: dict[str, Any] = {
                "bron_feed": item["feed_titel"],
                "link": link,
                "titel": item["titel"],
                "samenvatting_rss": item["samenvatting_rss"],
                "gepubliceerd_rss": item["gepubliceerd_rss"],
            }

            if fetch_full:
                try:
                    print(f"  Artikel ophalen: {item['titel'][:70]}")
                    details = fetch_article(link, delay)
                    if details:
                        article.update(details)
                    else:
                        article["fout"] = "Geen JSON-LD gevonden op artikelpagina"
                except Exception as exc:
                    article["fout"] = str(exc)

            articles.append(article)

    articles.sort(
        key=lambda a: a.get("gepubliceerd") or a.get("gepubliceerd_rss") or "",
        reverse=True,
    )
    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape NOS artikelen via RSS-feeds")
    parser.add_argument(
        "-o",
        "--output",
        default="data/nos_artikelen.json",
        help="Uitvoerbestand (JSON)",
    )
    parser.add_argument(
        "--feeds",
        nargs="*",
        default=DEFAULT_FEEDS,
        help="RSS-feed URLs om te scrapen",
    )
    parser.add_argument(
        "--limit-per-feed",
        type=int,
        default=10,
        help="Maximum aantal artikelen per feed (0 = alles)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Pauze tussen artikelverzoeken in seconden",
    )
    parser.add_argument(
        "--rss-only",
        action="store_true",
        help="Alleen RSS-metadata ophalen, geen volledige artikelpagina's",
    )
    args = parser.parse_args()

    limit = None if args.limit_per_feed == 0 else args.limit_per_feed
    articles = scrape(
        feeds=args.feeds,
        limit_per_feed=limit,
        delay=args.delay,
        fetch_full=not args.rss_only,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "gescrapet_op": datetime.now(timezone.utc).isoformat(),
        "aantal_artikelen": len(articles),
        "feeds": args.feeds,
        "artikelen": articles,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nKlaar: {len(articles)} artikelen opgeslagen in {output_path}")


if __name__ == "__main__":
    main()
