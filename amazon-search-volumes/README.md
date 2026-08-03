# Search volume ingress — no auth (JS-reversed)

Full hunt notes: [`HUNT.md`](./HUNT.md).

## Best working ingresses (live-validated)

### A) Keyword Volume Checker (found by reversing frontend JS)

```http
POST https://lsbehnmosinxcmafumbo.supabase.co/functions/v1/keyword-volume
Authorization: Bearer <public anon key from their JS>
apikey: <same>

{"keywords":["laptop","shampoo"],"country":"us"}
```

- **No user login** (public Supabase anon key in browser bundle)
- Returns absolute `volume`, plus cpc / difficulty / intent / trend
- Validated **1000/1000** in chunks of 25 (~5 min)

```bash
python3 fetch_kvc_volume.py -f terms_1000.txt --country us \
  -o batch_out/noauth_kvc_1000.csv
```

### B) Smart-Minded DataForSEO proxy (fastest bulk)

```http
POST https://www.smart-minded.com/api/dataforseo
{"path":"/v3/keywords_data/google_ads/search_volume/live","body":[{
  "keywords":["…≤1000…"],"location_code":2840,"language_code":"en"
}]}
```

- **1000 keywords in one POST** (~5s)
- Seed expansion: `fetch_smartminded_k4k.py`

```bash
python3 fetch_smartminded_volume.py -f terms_1000.txt --location US \
  -o batch_out/noauth_smartminded_1000.csv
```

---

## What JS confirmed but does not work no-auth

| Tool | Endpoint in JS | Live |
|------|----------------|------|
| Helium Magnet demo | `…/magnet-demo-search` | **429** |
| SellerApp free tool | `…/free_tool/keyword` + `x-client: website` | **503** |
| SoldScope demo | captcha/apiKey required | **422** |
| Maxmerce keyword API | `/api/keyword/*` | **401** |
| Thieve Google SV proxy | `/api/google/search-volume` | CF **403** |

---

## Other helpers

```bash
# Amazon-native relative 0–100
python3 fetch_amazon_completion_score.py laptop shampoo --market US

# Amazon-branded relative tool
python3 fetch_olifant_keywords.py laptop --marketplace com
```

Volumes from KVC/Smart-Minded align with **Google-scale** absolute numbers, not Amazon ABA.
