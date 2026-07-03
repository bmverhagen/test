#!/usr/bin/env python3
"""Scrape Amazon.nl search results for babyspeelgoed (baby toys)."""

import csv
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE_URL = "https://www.amazon.nl"
SEARCH_URL = f"{BASE_URL}/s?k=babyspeelgoed"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_products(html: str) -> list[dict]:
    blocks = re.split(r'data-component-type="s-search-result"', html)[1:]
    products = []
    seen_asins: set[str] = set()

    for block in blocks:
        asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', block)
        if not asin_match:
            continue

        asin = asin_match.group(1)
        if asin in seen_asins:
            continue
        seen_asins.add(asin)

        title_match = re.search(r'<h2 aria-label="([^"]+)"', block)
        if not title_match:
            title_match = re.search(
                r'<h2[^>]*>\s*<a[^>]*>\s*<span[^>]*>([^<]+)</span>', block, re.DOTALL
            )
        title = unescape(title_match.group(1).strip()) if title_match else None

        price_match = re.search(r'<span class="a-offscreen">(€[^<]+)</span>', block)
        price = price_match.group(1).replace("\xa0", " ").strip() if price_match else None

        rating_match = re.search(r'(\d,\d)\s+van\s+5\s+sterren', block)
        rating = rating_match.group(1) if rating_match else None

        reviews_match = re.search(r'(\d[\d\.]*)\s+beoordelingen', block)
        reviews = reviews_match.group(1).replace(".", "") if reviews_match else None

        url_match = re.search(rf'href="(/[^"]+/dp/{asin}[^"]*)"', block)
        product_url = urljoin(BASE_URL, url_match.group(1).split("?")[0]) if url_match else None

        prime = "a-icon-prime" in block or "Prime" in block

        products.append(
            {
                "asin": asin,
                "title": title,
                "price": price,
                "rating": rating,
                "reviews_count": int(reviews) if reviews else None,
                "url": product_url,
                "prime": prime,
            }
        )

    return products


def save_results(products: list[dict], prefix: str = "amazon_babyspeelgoed") -> None:
    payload = {
        "url": SEARCH_URL,
        "query": "babyspeelgoed",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total_products": len(products),
        "products": products,
    }

    json_path = f"{prefix}.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    csv_path = f"{prefix}.csv"
    fieldnames = ["asin", "title", "price", "rating", "reviews_count", "url", "prime"]
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)

    print(f"Saved {len(products)} products to {json_path} and {csv_path}")


def main() -> int:
    html_path = sys.argv[1] if len(sys.argv) > 1 else None

    if html_path:
        with open(html_path, encoding="utf-8", errors="replace") as handle:
            html = handle.read()
    else:
        print(f"Fetching {SEARCH_URL} ...")
        html = fetch_html(SEARCH_URL)

    products = parse_products(html)
    save_results(products)

    for index, product in enumerate(products[:10], start=1):
        print(
            f"{index}. {product['title']} | {product['price']} | "
            f"{product['rating']} ({product['reviews_count']} reviews)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
