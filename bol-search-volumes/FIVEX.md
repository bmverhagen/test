# FiveX bol search-terms — deep dive (2026-08-03)

Live reverse-engineering of FiveX’s free Bol.com keyword tool and related APIs.

## Public marketing tool

- NL: https://www.fivex.com/nl/gratis-zoekwoorden-bol-tool/
- EN: https://www.fivex.com/tools/bol-search-terms/
- Client logic: `/assets/js/nav.js` → `bindBolSearchTool`

### Endpoint (works unauthenticated)

```http
GET https://www.fivex.com/api/bol-search-terms?query=<term>
Accept: application/json
Referer: https://www.fivex.com/nl/gratis-zoekwoorden-bol-tool/
```

Optional header used by the UI for non-counting/preview calls:

```http
X-FX-Bol-Preview: 1
```

### Response shape (live)

```json
{
  "query": "laptop",
  "period": "MONTH",
  "periods": [
    {
      "period": {"month": "7", "year": "2026"},
      "total": 27398,
      "countries": [
        {"countryCode": "NL", "value": 21614},
        {"countryCode": "BE", "value": 5784}
      ]
    }
  ],
  "items": [
    {
      "term": "laptop",
      "last30": 24865,
      "previous30": 23053,
      "trend": 7.86,
      "last12": 348460
    }
  ]
}
```

- `periods`: 12 monthly points, NL/BE split (same family of numbers as bol insights / Bolmate).
- `items`: seed + ~10 related terms with last30 / previous30 / trend / last12.
- Current calendar month can be a partial stub (e.g. Aug totals ≪ Jul).

### Limits (verified)

| Layer | Behavior |
|---|---|
| UI copy | “3 free searches” / day |
| Client | `sessionStorage.fxBolSearchCount` (Europe/Amsterdam day); blocks submit at ≥3 |
| Client unlock flag | `localStorage.fxBolSearchUnlocked === "1"` — **read in nav.js but never written** in marketing assets |
| Server | `429 {"error":"Free search limit reached."}` — primarily **IP-scoped**; fresh `fivex_visitor_id` cookies do **not** reset it |
| Preview header | Often still returns `200` after free quota; intermittent Cloudflare `502`; `Retry-After: 60` observed under load |
| Bulk | **No** multi-term API. `query=a&query=b` keeps first; `query=a,b` treated as one literal string. POST `/api/bol-search-terms` → `404` |

Paced sequential GETs with `X-FX-Bol-Preview: 1` + retries: **20/20** succeeded in testing. Suitable for light automation, not reliable bulk of 100 without backoff / account.

Signup CTA only links to portal register:

`https://fivex.com/portal/public/auth/register`

Claimed “unlimited with free account” is **not** implemented as a header/query unlock on the public endpoint; likely needs a real portal session/API key (see below).

## Portal / developer API

```http
GET https://fivex.com/portal/api/bol-search-terms?query=laptop
→ 401 {"status":"error","message":"API key is missing or invalid"}
```

- Entire `/portal/api/*` surface returns the same API-key 401 (catch-all auth gate).
- No public OpenAPI/Swagger JSON on www/docs hosts.
- Marketing “REST API” pages are product guides (KPIs, exports, OAuth) — **no documented public search-terms resource**.
- API key format/header name not exposed in public portal JS that we could inspect; requires a FiveX account with API access.

## Other probes (negative)

- No batch routes: `/api/bol-search-terms/bulk|batch`, `/api/keywords`, `/api/search-volume` → HTML SPA fallback or 405.
- `api.fivex.com` — no usable public host for this tool.
- robots.txt: `Disallow: /api/` (marketing crawlers only; endpoint still callable).
- Demo airfryer JSON is **SSR-embedded** on the tool page (not a live call).

## Practical recommendation

| Need | FiveX | Better |
|---|---|---|
| 1–3 manual looks / day | Public `GET /api/bol-search-terms` | — |
| ~20–100 seeds without seller creds | Paced preview GETs (fragile) | **Bolmate demo multi-term** (`search-volumes/get`) |
| Production / unlimited | Portal API key (account) | Official bol `GET /retailer/insights/search-terms` |

Volume cross-check: FiveX Jul ’26 laptop total **27398** matches Bolmate for the same month.
