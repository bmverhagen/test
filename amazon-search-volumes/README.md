# Search volume ingress — no auth (validated @ 1000 keywords)

## Working endpoint

```http
POST https://www.smart-minded.com/api/dataforseo
Content-Type: application/json
Origin: https://www.smart-minded.com
Referer: https://www.smart-minded.com/amazon-keyword-tool/

{
  "path": "/v3/keywords_data/google_ads/search_volume/live",
  "body": [{
    "keywords": ["laptop", "... up to 1000 ..."],
    "location_code": 2840,
    "language_code": "en"
  }]
}
```

**No login. No API key.** Absolute monthly search volume + CPC + competition + 12 monthly periods.

> Volumes are **Google Ads** (proxied by Smart-Minded’s Amazon Keyword Tool UI), **not** Amazon ABA.

---

## Live 1000-term test

| Metric | Result |
|--------|--------|
| Keywords | **1000** (`terms_1000.txt`) |
| Returned by API | **1000/1000** |
| With numeric `search_volume` | **989/1000** (11 null from Google Ads) |
| Wall time (1 POST) | **~5–6s** |

Artifacts:

- [`batch_out/noauth_smartminded_1000.csv`](./batch_out/noauth_smartminded_1000.csv)
- [`batch_out/noauth_smartminded_1000_report.json`](./batch_out/noauth_smartminded_1000_report.json)
- [`batch_out/noauth_smartminded_1000_stress.json`](./batch_out/noauth_smartminded_1000_stress.json)

Sample:

| keyword | search_volume | competition | cpc |
|---------|---------------|-------------|-----|
| laptop | 673000 | HIGH | 1.8 |
| shampoo | 135000 | HIGH | 1.41 |
| yoga mat | 110000 | HIGH | 1.27 |
| best pens | 12100 | HIGH | 0.97 |

---

## High-frequency usage (stress-tested)

| Pattern | Result |
|---------|--------|
| Size ladder 100→1000 | all OK |
| **10×100** rapid, no pause | **10/10** |
| **5×200** with 1s gap | **5/5** |
| 3×1000 back-to-back | 1st OK; 2nd/3rd empty → wait ~15s → OK again |

**Practical rule:** prefer chunks of **100–1000** keywords; on empty `result`, retry with **8–15s** backoff (built into the fetcher).

```bash
python3 fetch_smartminded_volume.py -f terms_1000.txt --location US --lang en \
  -o batch_out/noauth_smartminded_1000.csv \
  --json-out batch_out/noauth_smartminded_1000_report.json

# high-frequency style
python3 fetch_smartminded_volume.py -f terms_1000.txt --chunk-size 200 --chunk-pause 1 \
  -o batch_out/out.csv
```

Locations: `US=2840`, `NL=2528`, `DE=2276`, `UK=2826`.

---

## Other no-auth candidates (worse for 1k / frequency)

| Source | Auth | Absolute? | 1k / frequency |
|--------|------|-----------|----------------|
| **Smart-Minded Google Ads proxy** | none | **yes** | **best — 1000/POST** |
| Olifant Vercel | none | relative 0–100 | 1 call/KW; 101/101 earlier |
| Helium Magnet demo | none | Amazon-style abs sometimes | IP **429** — not for bulk |
| SoldScope demo | captcha/apiKey | Amazon abs | blocked |
| SellerApp free tool | intended none | Amazon | upstream 404/503 |
| KeywordFinder.dev | captcha | ? | 403 CAPTCHA |
| KeywordTool guest MCP | none (guest quota) | suggestions only | hourly guest quota |

---

## Helium (Amazon-flavored, not bulk)

Still useful for a few head terms when IP is not 429:

```bash
python3 fetch_helium_magnet_demo.py laptop --market US
```

Absolute only when `bestPhrase.phrase == seed`. See [`samples/`](./samples/).
