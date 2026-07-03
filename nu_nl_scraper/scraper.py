from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Literal

import requests

from nu_nl_scraper.api import build_articlelist_url, parse_articlelist_payload
from nu_nl_scraper.article import extract_article_body
from nu_nl_scraper.feeds import (
    KNOWN_CATEGORIES,
    deduplicate_articles,
    parse_rss,
    rss_url_for_category,
)
from nu_nl_scraper.models import Article

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class NuNlScraper:
    """Scrape headlines and article metadata from NU.nl."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 20.0,
        request_delay: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/rss+xml, application/xml, application/json, text/html, */*",
                "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
            }
        )

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        if self.request_delay > 0:
            time.sleep(self.request_delay)
        return response

    def fetch_rss(self, category: str | None = None) -> list[Article]:
        feed_url = rss_url_for_category(category)
        response = self._get(feed_url)
        return parse_rss(response.text, feed_url)

    def fetch_api(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        section: str | None = None,
    ) -> list[Article]:
        filter_type = "section" if section else "site"
        api_url = build_articlelist_url(
            limit=limit,
            offset=offset,
            filter_type=filter_type,
            section=section,
        )
        response = self._get(api_url)
        payload = response.json()
        return parse_articlelist_payload(payload, api_url)

    def fetch_categories(self, categories: list[str] | None = None) -> list[Article]:
        selected = categories or list(KNOWN_CATEGORIES)
        articles: list[Article] = []
        for category in selected:
            articles.extend(self.fetch_rss(category))
        return deduplicate_articles(articles)

    def fetch_article_body(self, url: str) -> str | None:
        response = self._get(url)
        return extract_article_body(response.text)

    def enrich_with_body(self, articles: list[Article]) -> list[Article]:
        enriched: list[Article] = []
        for article in articles:
            try:
                body = self.fetch_article_body(article.url)
            except requests.RequestException:
                body = None
            enriched.append(
                Article(
                    title=article.title,
                    url=article.url,
                    article_id=article.article_id,
                    summary=article.summary,
                    category=article.category,
                    published_at=article.published_at,
                    image_url=article.image_url,
                    image_credit=article.image_credit,
                    body=body,
                    source=article.source,
                    extra=article.extra,
                )
            )
        return enriched

    def scrape(
        self,
        *,
        source: Literal["rss", "api", "auto"] = "auto",
        category: str | None = None,
        categories: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        include_body: bool = False,
    ) -> list[Article]:
        articles: list[Article] = []

        if source in {"rss", "auto"}:
            try:
                if categories:
                    articles = self.fetch_categories(categories)
                else:
                    articles = self.fetch_rss(category)
            except requests.RequestException as exc:
                if source == "rss":
                    raise
                print(f"RSS fetch failed ({exc}); trying API fallback.", file=sys.stderr)

        if not articles and source in {"api", "auto"}:
            articles = self.fetch_api(limit=limit or 20, offset=offset, section=category)

        if limit is not None:
            articles = articles[:limit]

        if include_body:
            articles = self.enrich_with_body(articles)

        return articles


def write_json(articles: list[Article], output_path: Path) -> None:
    payload = [article.to_dict() for article in articles]
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(articles: list[Article], output_path: Path) -> None:
    rows = [article.to_dict() for article in articles]
    fieldnames = [
        "title",
        "url",
        "article_id",
        "summary",
        "category",
        "published_at",
        "image_url",
        "image_credit",
        "body",
        "source",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_articles(articles: list[Article]) -> None:
    for index, article in enumerate(articles, start=1):
        published = article.published_at.isoformat() if article.published_at else "unknown"
        print(f"{index}. {article.title}")
        print(f"   URL: {article.url}")
        print(f"   Category: {article.category or 'n/a'} | Published: {published}")
        if article.summary:
            print(f"   Summary: {article.summary}")
        print()


def run_cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Scrape headlines from NU.nl")
    parser.add_argument(
        "--source",
        choices=["auto", "rss", "api"],
        default="auto",
        help="Data source (default: auto, prefers RSS then API)",
    )
    parser.add_argument(
        "--category",
        help="RSS/API category or section (e.g. tech, voetbal, binnenland)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        help="Fetch multiple RSS categories and merge results",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of articles to return")
    parser.add_argument("--offset", type=int, default=0, help="API pagination offset")
    parser.add_argument(
        "--include-body",
        action="store_true",
        help="Fetch full article HTML bodies (may be blocked by WAF)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write results to a JSON or CSV file (extension selects format)",
    )
    parser.add_argument("--list-categories", action="store_true", help="List known RSS categories")
    args = parser.parse_args(argv)

    if args.list_categories:
        print("\n".join(KNOWN_CATEGORIES))
        return 0

    scraper = NuNlScraper()
    articles = scraper.scrape(
        source=args.source,
        category=args.category,
        categories=args.categories,
        limit=args.limit,
        offset=args.offset,
        include_body=args.include_body,
    )

    if args.output:
        suffix = args.output.suffix.lower()
        if suffix == ".csv":
            write_csv(articles, args.output)
        else:
            write_json(articles, args.output)
        print(f"Wrote {len(articles)} articles to {args.output}", file=sys.stderr)
    else:
        print_articles(articles)

    return 0
