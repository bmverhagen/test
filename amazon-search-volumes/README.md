# Search volume ingress — no auth (extended hunt)

See full probe matrix in [`HUNT.md`](./HUNT.md).

## Best ingress found

**Smart-Minded public DataForSEO proxy — no login.**

| Use case | Endpoint path | Scale (live) |
|----------|---------------|--------------|
| **Bulk absolute volumes** | `google_ads/search_volume/live` | **1000 keywords / POST**, ~5s |
| **Seed → related + volumes** | `google_ads/keywords_for_keywords/live` | 1 seed → **~1900** KWs w/ volume |

```http
POST https://www.smart-minded.com/api/dataforseo
Content-Type: application/json

{
  "path": "/v3/keywords_data/google_ads/search_volume/live",
  "body": [{
    "keywords": ["… tot 1000 …"],
    "location_code": 2840,
    "language_code": "en"
  }]
}
```

> Absolute monthly volumes are **Google Ads**, not Amazon ABA.  
> Amazon absolute no-auth at 1k-scale was **not** found (Helium Magnet is Amazon-abs but IP **429**).

---

## Commands

```bash
# 1000-term bulk absolute (validated)
python3 fetch_smartminded_volume.py -f terms_1000.txt --location US \
  -o batch_out/noauth_smartminded_1000.csv

# discovery: one seed → many related absolute volumes
python3 fetch_smartminded_k4k.py "yoga mat" --limit 500 \
  -o batch_out/k4k_yoga_mat.csv

# Amazon-native relative 0–100 (completion API, high frequency)
python3 fetch_amazon_completion_score.py -f terms_100.txt --market US \
  -o batch_out/amz_completion_rel.csv

# Amazon-branded relative tool (Olifant)
python3 fetch_olifant_keywords.py -f terms_100.txt --marketplace com \
  -o batch_out/noauth_olifant_100.csv
```

Artifacts: `batch_out/noauth_smartminded_1000.csv`, `batch_out/k4k_yoga_mat.csv`, `HUNT.md`.

---

## What else was tried (short)

| Candidate | Result |
|-----------|--------|
| Helium Magnet demo | Amazon abs sometimes; **429** bulk |
| Smart-Minded Amazon `ranked_keywords` | ASIN→KW ok; SV mostly 0 |
| Smart-Minded Amazon bulk SV | **403** path not allowed |
| SoldScope / SellerApp / Maxmerce | captcha / 503 / **401** |
| KeywordTool guest MCP | abs on ≤5; 60/hr 120/day |
| SellerSprite / MerchantWords / Keepa / Rainforest / TrendsMCP | auth/session/key |
| Ahrefs / Jungle Scout free pages | no open volume JSON |

---

## Helium (Amazon abs, not scalable here)

```bash
python3 fetch_helium_magnet_demo.py laptop --market US
```

Absolute only when `bestPhrase.phrase == seed`. Samples under [`samples/`](./samples/).
