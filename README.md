# NU.nl Scraper

Python scraper for [NU.nl](https://www.nu.nl), the Dutch news website.

It collects headlines and article metadata from NU.nl's public RSS feeds and, when available, the site's internal `lean_json` article list API. Optional full-text extraction is supported when article pages are reachable.

## Features

- Fetch the main NU.nl RSS feed or category-specific feeds
- Merge multiple categories in one run
- Fallback from RSS to the `lean_json` API when RSS is unavailable
- Export results as JSON or CSV
- Optional full article body extraction

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Print the latest headlines:

```bash
python -m nu_nl_scraper
```

Fetch a specific category:

```bash
python -m nu_nl_scraper --category tech
```

Fetch multiple categories:

```bash
python -m nu_nl_scraper --categories tech voetbal binnenland --limit 50
```

Export to JSON:

```bash
python -m nu_nl_scraper --category economie --output economie.json
```

Export to CSV:

```bash
python -m nu_nl_scraper --output headlines.csv
```

Force the internal API:

```bash
python -m nu_nl_scraper --source api --limit 100
```

List known RSS categories:

```bash
python -m nu_nl_scraper --list-categories
```

## Python API

```python
from nu_nl_scraper import NuNlScraper

scraper = NuNlScraper()
articles = scraper.scrape(category="tech", limit=10)

for article in articles:
    print(article.title, article.url)
```

## Data sources

| Source | URL pattern | Notes |
|--------|-------------|-------|
| RSS | `https://www.nu.nl/rss` | Usually ~30 latest items per feed |
| Category RSS | `https://www.nu.nl/rss/{category}` | e.g. `tech`, `voetbal` |
| Article list API | `https://www.nu.nl/block/lean_json/articlelist` | Paginated JSON endpoint |

## Notes

- NU.nl protects most HTML pages with a WAF. RSS feeds are the most reliable source from cloud environments.
- The `lean_json` API works from many residential networks and CI runners, but may return `403` from some datacenter IPs.
- Use `--include-body` only when article pages are accessible from your network.
- Please respect NU.nl's terms of service and avoid aggressive request rates. The scraper sleeps briefly between requests by default.

## License

MIT
