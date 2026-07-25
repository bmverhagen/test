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

Stable long-run mode with **adaptive delay**, **checkpoint/resume**, and live
progress on stderr. Validated live: **100/100 in ~161s** and **1000/1000 in ~29min** (0 captcha, 0 retries, no cache).

```bash
# Staged stress test
python scrape_descriptions.py bulk -f asins.txt --max 100 -o out100.json

# Full 1000 (resumable)
python scrape_descriptions.py bulk -f asins.txt --max 1000 -o out1000.json \
  --delay 0.5 --checkpoint-every 25

# Resume after interrupt (default)
python scrape_descriptions.py bulk -f asins.txt --max 1000 -o out1000.json
```

Progress lines look like:

```text
[08:35:33] OK [80/1000] asin=B0... provider=soft/twister bullets=5 bytes=928694
           ok=80 fail=0 captcha=0 rate=0.63/s eta=24.5m delay=0.35s
[08:35:33] CHECKPOINT wrote 80 products → out1000.json.checkpoint.json
```

On captcha/block the delay grows (`×1.7`, cap 8s); after success streaks it
eases back toward `min_delay` (0.35s). Checkpoint files let you Ctrl+C and
continue later without re-downloading OK items.

## Tests

```bash
pip install pytest
pytest -q
```
