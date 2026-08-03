# Extended JS reverse-engineering hunt

Method: download free-tool HTML + JS bundles from 30+ sites, extract `/api/*`
and volume-related strings, then live-probe every promising endpoint.

## Working no-auth ingresses found

### 1) Keyword Volume Checker — Supabase edge function (NEW, from JS)

Reversed from `keywordvolumechecker.com/assets/index-*.js`:

```js
supabase.functions.invoke("keyword-volume", { body: { keywords, country } })
```

```http
POST https://lsbehnmosinxcmafumbo.supabase.co/functions/v1/keyword-volume
Authorization: Bearer <public anon JWT from frontend>
apikey: <same>
Content-Type: application/json

{"keywords":["laptop","shampoo"],"country":"us"}
```

| Test | Result |
|------|--------|
| 5 keywords | absolute `volume` + cpc/difficulty/intent/trend |
| 5× rapid calls | **5/5** |
| **1000 keywords** (40×25 chunks) | **1000/1000** in ~306s |

No user login. Uses the site's **public anon key** embedded in the browser bundle.

Script: `fetch_kvc_volume.py`  
Artifact: `batch_out/noauth_kvc_1000.csv`

### 2) Smart-Minded DataForSEO proxy (still strongest bulk)

```http
POST https://www.smart-minded.com/api/dataforseo
{"path":"/v3/keywords_data/google_ads/search_volume/live","body":[{...}]}
```

- **1000/POST** in ~5s
- Also `keywords_for_keywords/live` (seed → ~1900 KWs)

---

## JS-confirmed but not usable no-auth

| Site | JS evidence | Live result |
|------|-------------|-------------|
| **Helium** `keywordResearch.js` / `h10-features` | `members.helium10.com/api/v1/cerebro/product/magnet-demo-search`; also authed `/api/v1/keywords/search-volume` | Magnet demo **429**; chart endpoints need session |
| **SellerApp** `sa_main.js` | `POST api.sellerapp.com/amazon/{geo}/research/new/free_tool/keyword` + header `x-client: website` | Path confirmed; upstream **503** |
| **SoldScope** | demo `search-volume` needs `captchaToken`/`apiKey` | **422** |
| **Maxmerce** `umi.js` | `/bi/api/keyword/*` proxy to RESEARCH_API | **401** without account |
| **Thieve** `_buildManifest` | `/api/google/search-volume`, `/api/google/keyword-ideas` | Initially 500 (bad body), then CF **403** |
| **SellerSprite** | `gkdata` / open API | session expired / login |
| **KeywordTool** guest MCP | suggestions + ≤5 metrics | 60/hr 120/day cap |
| **AmzScout / Ahrefs / Jungle Scout** | marketing / CF / no open volume JSON | dead for no-auth |

---

## Sites/pages JS scanned (sample)

Helium free Magnet/Cerebro, SoldScope, SellerApp, Smart-Minded, Olifant Vercel,
KeywordTool.io, Ahrefs Amazon tool, Maxmerce, AmzScout, SellerSprite, Thieve,
Viral Launch/Intellifox, DataHawk, Zonguru, KeywordVolumeChecker, KeywordFinder,
Canopy, Kparser, SellerMetrics, BookBeam, PublisherRocket, Kindlepreneur, Pattern, …

Full downloaded bundle list under `/tmp/jsrev/` on the agent VM.

---

## Practical pick

| Need | Use |
|------|-----|
| **Often + absolute, chunked** | KVC Supabase `keyword-volume` (≤25/call, 1000/1000 proven) |
| **Fastest bulk absolute (1 call)** | Smart-Minded Google Ads SV (1000/POST) |
| Amazon-native relative | Amazon completion scorer / Olifant |
| Amazon absolute | Helium Magnet only when not 429 — not scalable here |
