# Amazon search volume ingress (no auth)

## Verdict (100-term test)

**Best no-auth solution that works at ~100 keywords:**

| Source | Auth | Absolute volume? | Live batch (`terms_100.txt`, 101 keywords) |
|--------|------|------------------|--------------------------------------------|
| **Smart-Minded** (`/api/dataforseo` → Google Ads SV) | none | **yes** (monthly + CPC) | **101/101** in one POST |
| Olifant Vercel keyword tool | none | no — relative ~0–100 | **101/101** (1 call/keyword) |
| Helium 10 Magnet demo | none | yes Amazon-style abs *when seed = bestPhrase* | **blocked** (IP **429** here) |

Artifacts from the live 100-run:

- [`batch_out/noauth_smartminded_100.csv`](./batch_out/noauth_smartminded_100.csv)
- [`batch_out/noauth_olifant_100.csv`](./batch_out/noauth_olifant_100.csv)

> Smart-Minded is exposed via an “Amazon keyword tool” UI, but the proxied path is
> **Google Ads** search volume — not Amazon ABA. Use it when you need **no-auth absolute
> numbers at bulk**. Use Helium when you need Amazon-flavored abs for a few head terms
> and the IP is not rate-limited.

---

## 1) Smart-Minded — no auth, bulk absolute (validated 101/101)

```http
POST https://www.smart-minded.com/api/dataforseo
Content-Type: application/json

{
  "path": "/v3/keywords_data/google_ads/search_volume/live",
  "body": [{
    "keywords": ["laptop", "kindle", "..."],
    "location_code": 2840,
    "language_code": "en"
  }]
}
```

```bash
python3 fetch_smartminded_volume.py -f terms_100.txt --location US --lang en \
  -o batch_out/noauth_smartminded_100.csv \
  --json-out batch_out/noauth_smartminded_100_report.json
```

Sample from the 100-run (US / en):

| keyword | search_volume | competition | cpc |
|---------|---------------|-------------|-----|
| laptop | 673000 | HIGH | 1.8 |
| kindle | 673000 | MEDIUM | 1.49 |
| air fryer | 550000 | HIGH | 0.78 |
| backpack | 450000 | HIGH | 0.75 |

Also returns **12 monthly periods** per keyword.

---

## 2) Olifant — no auth, relative Amazon scores (validated 101/101)

```http
GET https://amazon-keyword-tool.vercel.app/api/keywords?input=laptop&marketplace=com
```

```bash
python3 fetch_olifant_keywords.py -f terms_100.txt --marketplace com \
  -o batch_out/noauth_olifant_100.csv \
  --json-out batch_out/noauth_olifant_100_report.json
```

`searchVolume` is **relative ~0–100** (e.g. laptop=89), not absolute monthly searches.

---

## 3) Helium Magnet demo — true Amazon-style abs, rate-limited

Works without auth for single seeds when `bestPhrase.phrase == seed`:

```http
POST https://members.helium10.com/api/v1/cerebro/product/magnet-demo-search
Content-Type: application/x-www-form-urlencoded

keyword=laptop&marketplace=ATVPDKIKX0DER
```

Live-validated absolute examples (earlier, before IP lock):

| Market | Seed | Absolute (`bestPhrase.impressionExact30`) |
|--------|------|-------------------------------------------|
| US | laptop | **881687** |
| US | yoga mat | **506976** |
| NL | kindle | **13144** |
| DE | kindle | **320248** |

```bash
python3 fetch_helium_magnet_demo.py laptop --market US
python3 batch_magnet_100.py -f terms_100.txt --market US   # often dies on 429
```

**100-term batch from this environment:** IP stayed on HTTP **429** after cool-downs;
not usable for bulk here. Samples under [`samples/`](./samples/).

**Rule:** treat seed as absolute only when `normalize(bestPhrase.phrase) == normalize(keyword)`.
Otherwise seed rows are relative ~0–100.

---

## Marketplace / location notes

| Tool | Scope knobs |
|------|-------------|
| Smart-Minded | DataForSEO `location_code` (US=2840, NL=2528, DE=2276) + `language_code` |
| Olifant | `marketplace=com\|de\|nl\|…` |
| Helium | Amazon marketplace id (`ATVPDKIKX0DER` US, `A1805IZSGTT6HS` NL, `A1PA6795UKMFR9` DE) |

---

## What failed for no-auth Amazon absolute at scale

| Tool | Why |
|------|-----|
| SellerApp free keyword | Correct `x-client: website` path; upstream 503/404 |
| SoldScope demo volume | Needs `captchaToken` or `apiKey` |
| DataForSEO Amazon bulk (direct) | 401 / Smart-Minded Amazon path 403 |
| Jungle Scout / SellerSprite / Keepa / Rainforest | login, CF, or paid key |
| Amazon completion API | suggestions only — no volume |

---

## Practical pick

- **Need 100 no-auth absolute numbers now** → Smart-Minded Google Ads proxy.
- **Need Amazon-branded relative scores, 100 ok** → Olifant.
- **Need Amazon absolute for a few head terms** → Helium Magnet demo with heavy pacing (when not 429).
