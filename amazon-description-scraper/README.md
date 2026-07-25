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


## Bulk pipeline (100–1000+)

Parallel long-run mode with **global spacing**, **adaptive backoff**,
**checkpoint/resume**, and live progress on stderr.

Validated live (no HTTP cache):

| Mode | Config | Result |
| --- | --- | --- |
| safe sequential | `--safe` | **1000/1000** in ~29min (~0.57/s) |
| fast parallel (default) | workers=5, spacing=0.12 | **200/200 in 52s (~3.86/s)**, 0 captcha → ~4–5min/1000 |

```bash
# Fast default (~4–6× sneller dan sequential)
python scrape_descriptions.py bulk -f asins.txt --max 1000 -o out.json

# Tune
python scrape_descriptions.py bulk -f asins.txt -o out.json --workers 5 --spacing 0.12

# Safest (sequential)
python scrape_descriptions.py bulk -f asins.txt -o out.json --safe
```

Progress lines look like:

```text
[09:20:01] OK [80/1000] asin=B0... provider=soft/twister bullets=5
           ok=80 fail=0 captcha=0 rate=3.28/s eta=4.7m spacing=0.15s workers=4
```

On captcha/block spacing grows; after success streaks it eases down.
Checkpoint files let you Ctrl+C and resume without re-downloading OK items.

## Tests

```bash
pip install pytest
pytest -q
```
