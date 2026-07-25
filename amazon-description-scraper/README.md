# Amazon Description Scraper

Haalt **productomschrijvingen** van Amazon op. Default provider is `soft`:
twister-first + `/dp` fallback, sequential, **zonder HTTP-cache**, getest op
**100/100 ASINs zonder captcha** op amazon.nl.

## Endpoint-bevindingen

| Endpoint | Omschrijving? | Bulk? |
| --- | --- | --- |
| `/gp/twister/dimension?isDimensionSlotsAjax=1&asinList={ASIN}&vs=1` | **Ja** (streaming JSON met feature-HTML) | 1 ASIN (multi-ASIN = 404 op NL) |
| `/dp/{ASIN}` | **Ja** | 1 ASIN |
| `/gp/product/ajax/aodAjaxMain/` | Nee (offers) | 1 ASIN |
| Multi-ASIN twister / legacy description-ajax | Nee | — |

Er is **geen gratis Amazon-batch-JSON** voor 100 descriptions in één call.
Voor écht block-vrij op schaal: `paapi` / `rainforest` / `keepa` / `generic_json`.

### Soft bulk (aanbevolen, geen cache)

Gevalideerd: 100 ASINs, 0 captchas, ~196s, 74× twister + 26× dp.

```bash
python scrape_descriptions.py scrape -f asins.txt -p soft -o out.json
```

Gedrag:
1. Warm session op de storefront
2. Per ASIN: twister → fallback `/dp`
3. `workers=1`, delay ≈ 0.55s, retries bij captcha
4. Cache-bypass via `Cache-Control: no-cache` + `_=<nonce>` query param

> `workers>=3` vanaf een datacenter-IP triggert snel captchas.

## Providers

| Provider | Wat |
| --- | --- |
| `soft` (default) | Twister-first + DP fallback, sequential-safe |
| `twister` | Alleen `/gp/twister/dimension` streaming JSON |
| `html` | Alleen `/dp/{ASIN}` (sneller parallel, meer block-risico) |
| `paapi` | Officiële Product Advertising API 5.0 |
| `rainforest` / `keepa` | Third-party JSON |
| `generic_json` | Eigen GET-URL met `{asin}` / `{domain}` |

## Install

```bash
cd amazon-description-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Gebruik

```bash
# 1 ASIN
python scrape_descriptions.py scrape B0B4WQXL21 -o one.json

# 100 ASINs, geen captcha, geen cache
python scrape_descriptions.py scrape -f asins.txt -p soft -o out.json

# Sneller (meer block-risico)
python scrape_descriptions.py scrape -f asins.txt -p html --workers 8 --no-cache

# Endpoint probe
python scrape_descriptions.py probe-endpoints B0B4WQXL21 -m nl

# JSON providers
export RAINFOREST_API_KEY=...
python scrape_descriptions.py scrape B0B4WQXL21 -p rainforest
```

## Outputvelden

`title`, `brand`, `feature_bullets`, `description`, `aplus_text`, `overview`,
`best_description`, `provider` (bij soft: `soft/twister` of `soft/html`),
`source_bytes`, `error`.


## Bulk pipeline (100–1000+) — turbo default

After **55+ micro-benchmarks** and multi-hundred validations, default `bulk`
uses the **turbo** engine:

| Mode | Config | Result |
| --- | --- | --- |
| `--safe` | soft sequential | 1000/1000 ~29min (~0.57/s) |
| soft parallel | w5 / s0.12 | 200/200 ~52s (~3.9/s) |
| **turbo default** | w24 / s0.02 + fast_parse | **1000/1000 in 54.6s (~18.3/s)**, 0 captcha |

Validated 1000 ASINs with turbo: **54.6s (~18.3/s), 0 captcha**.

What turbo stacks (from the experiment winners):
shared pooled Session, gzip/br, twister→dp, skip retry on twister 404,
regex-first parse, 24 workers, 0.02s spacing gate, adaptive backoff.

```bash
# Ultra-fast default
python scrape_descriptions.py bulk -f asins.txt --max 1000 -o out.json

# Tune even more aggressively
python scrape_descriptions.py bulk -f asins.txt -o out.json --workers 24 --spacing 0.02

# Classic soft parallel / safest sequential
python scrape_descriptions.py bulk -f asins.txt -o out.json --engine soft --workers 5 --spacing 0.12
python scrape_descriptions.py bulk -f asins.txt -o out.json --safe
```

```text
[09:40:01] OK [200/200] provider=turbo/twister bullets=5
           ok=200 fail=0 captcha=0 rate=9.9/s spacing=0.015s workers=24
```

## Tests

```bash
pip install pytest
pytest -q
```
