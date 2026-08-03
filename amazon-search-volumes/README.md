# Amazon search volume ingress research

Live survey of **no-auth / demo** Amazon keyword volume APIs for seed terms
(e.g. `shampoo`) on Amazon.nl / .de / .com.

## Verdict

**Helium 10 Magnet demo is still the best working no-auth ingress.**  
No better public endpoint returned absolute monthly volume for an arbitrary seed
without captcha, API key, or a dead backend.

Closest runners-up that *almost* work:

| Tool | Endpoint | Why not better |
|------|----------|----------------|
| SoldScope free volume | `GET /api/demo/keyword-research/search-volume` | Needs `captchaToken` **or** `apiKey` (422 without) |
| SellerApp free keyword | `POST /amazon/{geo}/research/new/free_tool/keyword` | Correct path reversed from JS; live **503** upstream |
| TrendsAPI / TrendsMCP | `POST https://api.trendsapi.ai/api` | Free key exists (100/mo) but signup needs Turnstile + permanent email; key emailed, not returned |
| DataForSEO Amazon bulk SV | `…/amazon/bulk_search_volume/live` | 401 without paid/trial credentials; sandbox host NXDOMAIN |
| SellerSprite | `/v2/keyword-research`, open API | Session / `secret-key` required |
| KeywordTool.io Amazon | `/search/keywords/amazon/*` | Suggestions only; volume gated (empty `[]` / login) |
| Jungle Scout free page | admin-ajax / developer API | CF challenge; paid API key required |
| Keepa / Rainforest | public `demo` keys | Invalid / trial signup required |
| Amazon completion | `completion.amazon.*/api/2017/suggestions` | Suggestions only — **no volume** |

---

## Best working request (Helium Magnet demo)

```http
POST https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search
Content-Type: application/x-www-form-urlencoded
Origin: https://www.helium10.com
Referer: https://www.helium10.com/tools/free/amazon-keyword-tool/

keyword=laptop&marketplace=ATVPDKIKX0DER
```

Marketplace IDs (from Helium frontend):

| Market | `marketplace` |
|--------|----------------|
| amazon.com | `ATVPDKIKX0DER` |
| amazon.nl | `A1805IZSGTT6HS` |
| amazon.de | `A1PA6795UKMFR9` |

### How to get **seed absolute** volume

Demo response shape:

- `results.bestPhrase.impressionExact30` → **absolute** monthly estimate  
- `results.searchResults[*].impressionExact30` → usually **relative 0–100** scores  

**Rule:** treat the seed as absolute **only when**

```text
normalize(bestPhrase.phrase) == normalize(keyword)
```

Examples live-tested:

| Seed | Market | `bestPhrase.phrase` | Seed absolute? | Value |
|------|--------|---------------------|----------------|-------|
| `laptop` | US | `laptop` | **yes** | **881687** |
| `yoga mat` | US | `yoga mat` | **yes** | **506976** |
| `shampoo` | US | `shampoo and conditioner set` | no (seed rel 93.2) | best abs 543039 (different phrase) |
| `shampoo` | NL | `olaplex` | no (seed rel 97.75) | best abs 579 (different phrase) |
| `koffie` | NL | `koffiebonen` | no (seed rel 1.41) | best abs 566 |

When the seed is *not* the best phrase, this demo **does not** expose seed absolute volume. There is no alternate Helium demo path (`magnet-history`, `magnet-trends`, etc. → 404). Sibling demo: `cerebro-demo-search` (ASIN in, not seed keyword).

### Rate limit

Aggressive **HTTP 429** (`Request limit for this IP exceed`). Pace heavily (multi-second gaps); burst from one IP dies quickly.

### Sample JSON (seed absolute — `laptop` US)

See [`samples/helium_laptop_US_seed_absolute.json`](./samples/helium_laptop_US_seed_absolute.json).

```json
{
  "results": {
    "status": "success",
    "bestPhrase": {
      "id": 31236,
      "phrase": "laptop",
      "organic": true,
      "smart": true,
      "impressionExact30": 881687,
      "resultsNumber": ">100,000"
    },
    "searchResults": {
      "305248": {
        "phrase": "macbook",
        "impressionExact30": 37.05
      }
    }
  }
}
```

### Sample JSON (seed relative only — `shampoo` NL)

See [`samples/helium_shampoo_NL_relative_seed.json`](./samples/helium_shampoo_NL_relative_seed.json).

```json
{
  "results": {
    "status": "success",
    "bestPhrase": {
      "phrase": "olaplex",
      "impressionExact30": 579
    },
    "searchResults": {
      "824": {
        "phrase": "shampoo",
        "impressionExact30": 97.75
      }
    }
  }
}
```

---

## Fetcher

```bash
python3 fetch_helium_magnet_demo.py laptop --market US
python3 fetch_helium_magnet_demo.py shampoo --market NL -o out.json
python3 fetch_helium_magnet_demo.py yoga mat air fryer --market US --sleep 5
```

Prints `seed_absolute` when `bestPhrase` matches the seed; otherwise `seed_relative` + `best_phrase_absolute` for the different winning phrase.

---

## Tools tried (≥8) — live results

1. **Helium Magnet demo** — works; seed abs only when phrase match (above).
2. **Helium Cerebro demo / other magnet-* paths** — cerebro needs ASIN; history/trends 404.
3. **SoldScope** `api/demo/.../search-volume` — 422 captcha/apiKey; US sometimes 429.
4. **SellerSprite** web + `api.sellersprite.com` — unauthorized / login.
5. **SellerApp** free_tool/keyword — JS-confirmed; **503** live.
6. **KeywordTool.io** Amazon — locations/categories 200; results volume empty/`[]`.
7. **Jungle Scout** free page / developer API — CF 403 / 404 without key.
8. **DataForSEO** Amazon bulk SV — 401; sandbox host missing.
9. **TrendsAPI / TrendsMCP** — auth required; signup Turnstile + non-disposable email.
10. **Keepa / Rainforest** — demo key rejected.
11. **Ahrefs Amazon Keyword Tool** — marketing shell; app endpoints 404 without session.
12. **AMZScout / Viral Launch / DataHawk / Sellics-Pattern / Thieve / MerchantWords** — no open volume JSON (CF, 404, or HTML only).
13. **Amazon completion API** — suggestions, no volume.
14. **GitHub “estimate” repos** — autocomplete-rank heuristics (0–100), not absolute monthly volume.
15. **xiyinli / dianxiaomi** — connection reset / 404.

---

## Practical guidance

- For **one-off head terms on US** that are their own `bestPhrase` (laptop, yoga mat, …), Helium demo gives usable absolute volume with pacing.
- For **arbitrary seeds** (shampoo on NL/DE/US), demo usually returns **relative** seed scores — not production-grade absolute volume.
- For reliable absolute seed volume at scale: Paid Helium / Jungle Scout / SellerSprite / SoldScope API / DataForSEO Amazon — not these demos.
