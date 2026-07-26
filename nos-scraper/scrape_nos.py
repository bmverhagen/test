#!/usr/bin/env python3
"""Scrape NOS artikelen via officiële RSS-feeds en schrijf JSON-output."""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

FEEDS = {
    "algemeen": "https://feeds.nos.nl/nosnieuwsalgemeen",
    "binnenland": "https://feeds.nos.nl/nosnieuwsbinnenland",
    "buitenland": "https://feeds.nos.nl/nosnieuwsbuitenland",
    "economie": "https://feeds.nos.nl/nosnieuwseconomie",
    "politiek": "https://feeds.nos.nl/nosnieuwspolitiek",
    "sport": "https://feeds.nos.nl/nossportalgemeen",
    "tech": "https://feeds.nos.nl/nosnieuwstech",
    "cultuur-en-media": "https://feeds.nos.nl/nosnieuwscultuurenmedia",
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def fetch_feed(category: str, url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "nos-scraper/1.0 (+local)"})
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[dict] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description_html = item.findtext("description") or ""
        guid = (item.findtext("guid") or link).strip()
        pub_raw = item.findtext("pubDate") or ""
        enclosure = item.find("enclosure")
        image = enclosure.get("url") if enclosure is not None else None

        try:
            published_at = parsedate_to_datetime(pub_raw).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, IndexError):
            published_at = pub_raw or None

        items.append(
            {
                "id": guid,
                "title": title,
                "url": link,
                "category": category,
                "published_at": published_at,
                "summary": strip_html(description_html),
                "summary_html": description_html.strip(),
                "image": image,
                "source": "NOS",
                "feed": url,
            }
        )
    return items


def scrape(categories: list[str] | None = None) -> dict:
    selected = categories or list(FEEDS)
    all_articles: list[dict] = []
    seen: set[str] = set()
    by_category: dict[str, int] = {}
    errors: list[dict] = []

    for category in selected:
        url = FEEDS[category]
        try:
            arts = fetch_feed(category, url)
            by_category[category] = len(arts)
            for art in arts:
                key = art["url"] or art["id"]
                if key in seen:
                    continue
                seen.add(key)
                all_articles.append(art)
        except Exception as exc:  # noqa: BLE001 - collect per-feed errors
            errors.append({"category": category, "feed": url, "error": str(exc)})
            by_category[category] = 0

    all_articles.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "NOS",
        "feeds": {k: FEEDS[k] for k in selected},
        "article_count": len(all_articles),
        "articles": all_articles,
        "by_category": by_category,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape NOS artikelen naar JSON")
    parser.add_argument(
        "-o",
        "--output",
        default="nos_artikelen.json",
        help="Pad voor JSON-output (default: nos_artikelen.json)",
    )
    parser.add_argument(
        "-c",
        "--category",
        action="append",
        choices=sorted(FEEDS),
        help="Beperk tot categorie (herhaalbaar)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Schrijf JSON ook naar stdout",
    )
    args = parser.parse_args()

    data = scrape(args.category)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    out_path.write_text(text, encoding="utf-8")

    print(
        json.dumps(
            {
                "scraped_at": data["scraped_at"],
                "article_count": data["article_count"],
                "by_category": data["by_category"],
                "errors": data["errors"],
                "output": str(out_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.stdout:
        print(text)


if __name__ == "__main__":
    main()
