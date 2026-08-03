# Extended ingress hunt (no-auth)

Goal: find a **good** no-auth search-volume ingress that scales (ideally Amazon absolute, bulk / high frequency).

## Verdict after broad live probing

| Rank | Ingress | Auth | Absolute? | Amazon? | Scale | Status |
|------|---------|------|-----------|---------|-------|--------|
| **1** | **Smart-Minded** `google_ads/search_volume/live` | none | **yes** | no (Google Ads) | **1000/POST**, high-freq chunks | **BEST** — validated 1000/1000 |
| **2** | **Smart-Minded** `google_ads/keywords_for_keywords/live` | none | **yes** | no | 1 seed → **~1900** KWs w/ volume | **BEST for discovery** |
| 3 | Olifant `GET /api/keywords` | none | relative 0–100 | Amazon-branded | 1 call/KW; 101/101 | OK secondary |
| 4 | Amazon `completion.*/suggestions` | none | relative DIY 0–100 | **yes** | **50/50 rapid** in ~6s | Amazon-native relative |
| 5 | Helium Magnet demo | none | Amazon abs *sometimes* | **yes** | IP **429** here | Not bulk-safe |
| 6 | KeywordTool guest MCP | none | yes (first 5 only) | Google/Bing guest | 60/hr, 120/day | Too capped |
| 7 | Smart-Minded Amazon `ranked_keywords` | none | mostly **0** SV | Amazon KW list from ASIN | needs Google SV enrich | Discovery only |

There is **no** currently working no-auth endpoint that returns **Amazon ABA absolute** monthly volume for arbitrary seeds at 1000-scale from this environment. Helium is the only Amazon-absolute demo found; it is rate-limited.

---

## Smart-Minded allowlist (live-mapped)

`POST https://www.smart-minded.com/api/dataforseo` body `{"path","body"}`

| Path | Allowed | Notes |
|------|---------|-------|
| `/v3/keywords_data/google_ads/search_volume/live` | **yes** | Bulk absolute SV, up to ~1000 KW |
| `/v3/keywords_data/google_ads/keywords_for_keywords/live` | **yes** | Seed → related + absolute SV |
| `/v3/dataforseo_labs/amazon/ranked_keywords/live` | **yes** | ASIN → Amazon keywords; `search_volume` often 0 |
| Amazon bulk SV / related / suggestions | **403** path not allowed | |
| Bing / Google Labs / SERP Amazon | **403** | |
| `GET /api/rainforest?type=autocomplete` | **yes** | Suggestions only |
| `GET /api/rainforest?type=search` | **403** | |

---

## Probe matrix (this round + prior)

### Working / useful
- Smart-Minded Google Ads SV — 1000 OK, 10×100 OK, 5×200 OK
- Smart-Minded k4k — `yoga mat` → 1909 rows with volume in ~8.5s
- Olifant keywords — relative
- Amazon completion — 50/50 rapid
- FiveX `bol-search-terms` — bol.com only (not Amazon)
- KeywordTool guest MCP — absolute on ≤5 cached; hourly/daily caps

### Blocked / dead for no-auth Amazon absolute
- Helium Magnet / Cerebro demos — **429**
- SoldScope demo SV — captchaToken/apiKey **422**
- SellerApp free_tool — **503/404**
- Maxmerce `/api/keyword/*` — **401** (account)
- DataForSEO Amazon direct — **401**
- SellerSprite web/API — session expired / unauthorized
- MerchantWords / Rainforest / Keepa demo — 403/401/400
- Viral Launch `/api/keyword` — HTML shell, not JSON API
- Ahrefs Amazon tool — marketing shell, no open volume JSON
- Jungle Scout free page — CF / missing AJAX payload
- KeywordFinder.dev — CAPTCHA **403**
- TrendsMCP Amazon — needs API key
- Zonguru / SearchVolume.io / Keywords Everywhere — 404/401/reset

---

## Recommended usage

**Bulk absolute numbers (best no-auth ingress found):**

```bash
python3 fetch_smartminded_volume.py -f terms_1000.txt --location US \
  -o batch_out/noauth_smartminded_1000.csv
```

**Seed → many related absolute volumes:**

```bash
python3 fetch_smartminded_k4k.py "yoga mat" --limit 500 \
  -o batch_out/k4k_yoga_mat.csv
```

**Amazon-native relative (high frequency, not absolute):**

```bash
python3 fetch_amazon_completion_score.py -f terms_100.txt --market US \
  -o batch_out/amz_completion_rel.csv
```

For true Amazon absolute at scale: paid DataForSEO Amazon / Helium / Jungle Scout / SellerSprite — not available no-auth here.
