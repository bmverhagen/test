# Amazon Category Brand Scraper

Extracts **brand names** from Amazon **category pages** — search/browse listings
(`/s?...`, `/b?node=...`) and best-seller style lists (`/gp/bestsellers/...`,
`.../zgbs/...`).

**Product detail pages are never scraped.** URLs pointing at product pages
(`/dp/...`, `/gp/product/...`, etc.) are rejected up front, and pagination only
follows the listing's own "next page" links, so the scraper cannot wander onto
product pages by itself.

## Where brands come from

All brand data is read from the category page HTML itself:

| Source | What it is |
| --- | --- |
| `brand_filter` | The "Brands" refinement sidebar (`p_89`/`p_123` filters) |
| `product_card` | The brand line on each search-result card (all known layouts, including the legacy `by <brand>` row) |
| `structured_data` | `brand` fields in embedded `application/ld+json` |

On the newest card layout Amazon shows no separate brand row; those cards are
counted for a brand only when the product title starts with a brand that the
page itself lists (word-bounded match, longest brand wins), so the scraper
never invents brand names.

Results are deduplicated case-insensitively and sorted by how many product
cards mention each brand.

### Best-seller pages and the per-product view

Best-seller pages (`/gp/bestsellers/...`, `.../zgbs/<group>/<node>`) show
rank-ordered products but no explicit brand fields. For these, the scraper
learns a brand vocabulary from the same node's regular search listing
(`/s?rh=n%3A<node>&fs=true` — also a category page, fetched automatically),
plus Amazon's house brands ("Amazon Basics" etc.), and matches best-seller
titles against it. Titles that still don't match get a conservative
first-word guess, clearly labeled `title_guess`; titles starting with
numbers or noise get no brand rather than a wrong one.

With `--top N` the output switches from the aggregated brand list to a
per-product view: rank, brand, title, ASIN, and how the brand was determined
(`brand_row`, `known_brand`, or `title_guess`).

```bash
# Top 10 best-selling coffee machines with the brand of each product
python scrape_brands.py 'https://www.amazon.com/Best-Sellers-Coffee-Machines/zgbs/kitchen/289745/' --top 10
```

```csv
rank,brand,title,asin,brand_source
1,BLACK+DECKER,"BLACK+DECKER 12-Cup Digital Coffee Maker, Programmable, ...",B01GJOMWVA,known_brand
2,Cuisinart,"Cuisinart 14-Cup Coffee Maker, Programmable PerfecTemp ...",B00MVWGQX0,known_brand
3,BLACK+DECKER,"BLACK+DECKER 12-Cup Coffee Maker with Easy On/Off Switch, ...",B0C8B9V7HR,known_brand
4,Amazon Basics,"Amazon Basics 5 Cup Drip Coffee Maker with Glass Coffee Pot ...",B0D9QFRJMX,known_brand
```

`--top` also works on regular search listings (rank is then the display
position across the pages fetched).

## Install

```bash
cd amazon-category-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Scrape one category page, print CSV to stdout
python scrape_brands.py 'https://www.amazon.com/s?rh=n%3A172282'

# Browse node, follow up to 3 listing pages, save as CSV
python scrape_brands.py 'https://www.amazon.com/b?node=172282' --pages 3 -o brands.csv

# Best sellers list, JSON output
python scrape_brands.py 'https://www.amazon.com/gp/bestsellers/electronics/' --format json

# Several categories at once, plain list of brand names
python scrape_brands.py 'https://www.amazon.com/s?k=headphones' 'https://www.amazon.com/s?k=speakers' --format txt

# Parse a category page you saved from the browser (no network needed)
python scrape_brands.py --from-file saved_category_page.html --format json
```

The same CLI is available as `python -m amazon_category_scraper ...`.

Product URLs are refused:

```text
$ python scrape_brands.py 'https://www.amazon.com/dp/B0EXAMPLE1'
Refusing to scrape a product page: ... This tool only scrapes category pages ...
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--pages N` | 1 | Max listing pages to follow per category URL |
| `--top N` | off | Per-product view: first N products by rank with each product's brand (0 = all) |
| `--delay S` | 2.5 | Base delay between requests (jitter is added) |
| `--timeout S` | 20 | HTTP timeout |
| `--retries N` | 3 | Retries per page (429/5xx/robot check/network errors, exponential backoff) |
| `--user-agent UA` | rotate | Fixed User-Agent instead of rotating desktop UAs |
| `-o / --output FILE` | stdout | Output file |
| `--format csv/json/txt` | from extension | Output format |
| `--from-file FILE` | – | Parse saved HTML instead of fetching (repeatable) |

### Output (CSV)

```csv
brand,product_mentions,sources
Sony,14,brand_filter|product_card
Samsung,11,product_card
TCL,6,brand_filter|product_card|structured_data
```

`product_mentions` is the number of product cards listing that brand;
brands seen only in the sidebar or structured data have `0` mentions.

## Library use

```python
from amazon_category_scraper import CategoryBrandScraper

scraper = CategoryBrandScraper(max_pages=2)
report = scraper.scrape(["https://www.amazon.com/s?rh=n%3A172282"])
for brand in report.brands:
    print(brand.name, brand.product_mentions, brand.sources)
```

## Notes on blocking

Amazon aggressively rate-limits datacenter IPs and may answer with a captcha
page (surfaced as `BlockedError`) or HTTP 503. The scraper retries with
exponential backoff and rotates user agents, but from a blocked network you may
need to raise `--delay`, run from a different network, or save the page in your
browser and use `--from-file`. Respect Amazon's Terms of Service and
`robots.txt`, and only scrape data you are allowed to use.

## Tests

Offline tests run against bundled HTML fixtures (no network):

```bash
python -m pytest tests/ -v    # or: python -m unittest discover tests -v
```
