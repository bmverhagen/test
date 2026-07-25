# Amazon Description Scraper

Haalt **productomschrijvingen** van Amazon op. Default provider is `soft`:
twister-first + `/dp` fallback, sequential, **zonder HTTP-cache**, getest op
**100/100 ASINs zonder captcha** op amazon.nl.

## Endpoint-bevindingen

Endpoint-hunt (60+ URLs): **geen** gratis light JSON zonder captcha/tokens.
Werkende free paths blijven de zware twister/HTML-familie:

| Endpoint | Omschrijving? | Bulk? |
| --- | --- | --- |
| `/gp/twister/ajaxv2?asinList={ASIN}&…` | **Ja** (streaming JSON) | 1 ASIN — turbo primary |
| `/gp/twister/dimension?…` | **Ja** | 1 ASIN (multi-ASIN = 404) |
| `/gp/aw/d/{ASIN}` | **Ja** (mobiele HTML, hoge hit-rate) | 1 ASIN — turbo mid fallback |
| `/dp/{ASIN}` | **Ja** | 1 ASIN — final fallback |
| ACP / experienceId ajax / AOD / completion / api.amazon | Nee | — |

Turbo free chain: **ajaxv2 → aw/d → /dp** (199/200 @ w24 vs 185/200 voor twister→dp).
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


## Bulk pipeline (100–1000+) — iterative pass-1 default

Default `bulk` prioritizes **100% success**, then speed:

| Mode | Config | Goal |
| --- | --- | --- |
| **default** | w12 / s0.05, iterative pass-1 ≤20 | **100% success**, no-cache |
| `--fast` | w24 / s0.02, single pass | max speed (may drop OK%) |
| `--safe` | soft sequential | slowest, max politeness |

Chain per ASIN: **ajaxv2 → (skip dimension on structural 404) → `/gp/aw/d` → `/dp`**.
ASINs without twister payload are remembered and retried **aw-first**.
Every iteration uses the same pass-1 workers/spacing; only failures are retried.
Final log includes `ITERATIONS_NEEDED=N` when coverage reaches 100%.

```bash
# Default — iterative pass-1 until 100%
python scrape_descriptions.py bulk -f asins.txt --max 10000 -o out.json

# Aggressive single-pass
python scrape_descriptions.py bulk -f asins.txt -o out.json --fast

# Classic soft sequential
python scrape_descriptions.py bulk -f asins.txt -o out.json --safe
```

```text
[09:40:01] ITER 1/20: pending=1000 workers=12 ...
[09:41:20] ITER 1 done: recovered=885 ok=885/1000 remaining=115
...
[09:42:05] ITERATIONS_NEEDED=4 (pass-1 rounds until 100% match: 1000/1000)
iterations_needed=4 ok=1000/1000 fail=0 success_rate=100.0%
```

## Tests

```bash
pip install pytest
pytest -q
```
