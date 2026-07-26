# NOS artikelen scraper

Scrape recente NOS-artikelen via de officiële RSS-feeds en schrijf ze weg als JSON.

## Gebruik

```bash
python3 scrape_nos.py
# of met custom outputpad:
python3 scrape_nos.py -o nos_artikelen.json
```

Alleen één of meer categorieën:

```bash
python3 scrape_nos.py -c algemeen -c sport
```

## Output

`nos_artikelen.json` bevat:

- `scraped_at` — UTC timestamp
- `article_count` — aantal unieke artikelen
- `articles[]` — lijst met `id`, `title`, `url`, `category`, `published_at`, `summary`, `summary_html`, `image`, `source`, `feed`
- `by_category` — counts per feed
- `errors` — eventuele feed-fouten

## Feeds

| Categorie | Feed |
|---|---|
| algemeen | https://feeds.nos.nl/nosnieuwsalgemeen |
| binnenland | https://feeds.nos.nl/nosnieuwsbinnenland |
| buitenland | https://feeds.nos.nl/nosnieuwsbuitenland |
| economie | https://feeds.nos.nl/nosnieuwseconomie |
| politiek | https://feeds.nos.nl/nosnieuwspolitiek |
| sport | https://feeds.nos.nl/nossportalgemeen |
| tech | https://feeds.nos.nl/nosnieuwstech |
| cultuur-en-media | https://feeds.nos.nl/nosnieuwscultuurenmedia |
