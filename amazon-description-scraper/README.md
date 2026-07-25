# Amazon Description Scraper

Haalt **productomschrijvingen** van Amazon op — zo snel mogelijk, met plug-in
JSON-providers zodat je niet per se de volle HTML hoeft te parsen.

## Belangrijkste bevinding (endpoint-probe)

Amazon heeft **geen publieke, onauthenticated JSON-endpoint** die de
productomschrijving teruggeeft. Live probe op `amazon.nl`:

| Endpoint | Grootte | Omschrijving? |
| --- | --- | --- |
| `/dp/{ASIN}` | ~1.2 MB HTML | **Ja** — feature bullets, A+, optioneel `#productDescription` |
| `/gp/product/{ASIN}` | ~1.2 MB HTML | Zelfde als `/dp` |
| `/gp/aw/d/{ASIN}` | ~1.2 MB HTML | Geen lichte mobile-variant meer |
| `/gp/product/ajax/aodAjaxMain/?asin=` | ~35 KB | Nee — alleen seller offers |
| Twister ajax | leeg / variants | Nee |
| `completion.amazon.*/api/2017/suggestions` | tiny JSON | Nee — autocomplete |
| Legacy `experienceId=productDescriptionSection` | 404 | Weg |

**Conclusie:** zonder credentials is `/dp/{ASIN}` de enige betrouwbare bron.
Voor “direct inpluggen zonder HTML” gebruik je een JSON-provider hieronder.

## Providers (plug-ins)

| Provider | Wat het is | Auth |
| --- | --- | --- |
| `html` (default) | Concurrent scrape van `/dp/{ASIN}`, parseert bullets/description/A+ | Geen |
| `paapi` | [Product Advertising API 5.0](https://webservices.amazon.com/paapi5/documentation/) `GetItems` — officiële JSON | Associates keys |
| `rainforest` | `GET https://api.rainforestapi.com/request?type=product` | API key |
| `keepa` | `GET https://api.keepa.com/product` | API key |
| `generic_json` | Eigen GET-URL met `{asin}` / `{domain}` placeholders | Optioneel |

> PA-API levert **feature bullets** (`ItemInfo.Features`), geen lange
> producttekst. Rainforest/Keepa/HTML leveren wél langere descriptions waar
> Amazon die toont.

## Install

```bash
cd amazon-description-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Gebruik

```bash
# Eén ASIN op amazon.nl (default)
python scrape_descriptions.py scrape B0B4WQXL21

# Batch + concurrent (snel)
python scrape_descriptions.py scrape -f asins.txt --workers 12 -o out.json

# CSV
python scrape_descriptions.py scrape B0B4WQXL21 B09V323255 --format csv -o out.csv

# Endpoint-probe (wat werkt écht voor dit ASIN?)
python scrape_descriptions.py probe-endpoints B0B4WQXL21 -m nl
```

### JSON-providers (geen HTML-parse)

```bash
# Rainforest
export RAINFOREST_API_KEY=...
python scrape_descriptions.py scrape B0B4WQXL21 -p rainforest

# Keepa
export KEEPA_API_KEY=...
python scrape_descriptions.py scrape B0B4WQXL21 -p keepa

# Officiële PA-API
export PAAPI_ACCESS_KEY=... PAAPI_SECRET_KEY=... PAAPI_PARTNER_TAG=...
python scrape_descriptions.py scrape B0B4WQXL21 -p paapi -m nl

# Eigen endpoint
python scrape_descriptions.py scrape B0B4WQXL21 -p generic_json \
  --endpoint-url 'https://api.example.com/amazon/product?asin={asin}&domain={domain}' \
  --json-map 'title=title,description=description,feature_bullets=bullets,brand=brand'
```

## Outputvelden

- `title`, `brand`
- `feature_bullets` — “Over dit artikel”
- `description` — klassieke productbeschrijving (vaak leeg als A+ die vervangt)
- `aplus_text` — A+ content als plain text
- `overview` — productoverzicht key/values
- `best_description` — langste bruikbare tekst uit bovenstaande
- `provider`, `source_bytes`, `error`

## Snelheidstips

1. Gebruik `--workers 8..16` voor HTML-batch (default 8).
2. Voor productie/volume: `rainforest`, `keepa` of `paapi` — die omzeilen HTML + bot-checks.
3. Bij robot-checks: `--delay 0.5` en lagere `--workers`, of switch naar een JSON-provider.
4. Marketplace default is `nl`; andere: `com`, `de`, `fr`, `co.uk`, `it`, `es`, `com.be`.

## Tests

```bash
pip install pytest
pytest -q
```
