# Bol.com search volumes (Bolmate demo ingress)

Bulk fetch of bol.com search-volume trends via Bolmate’s public demo login.

## Why this path

- Official bol Retailer API: `GET /retailer/insights/search-terms` (one term per call, seller JWT required)
- FiveX free tool: single-term, ~3 searches/day without account
- **Bolmate demo**: multi-term in one request — suitable for ~100 product seeds

Bolmate documents free public search trends (no registration). The SPA auto-fills:

- URL: `https://app.bolmate.nl/inloggen?demo=1&redirect=/zoekvolume`
- Email: `demo@bolmate.nl`
- Password: `bolmate_demo`
- Extra login field: `fp` (fingerprint string)

## API

```http
POST https://app.bolmate.nl/bolmate-core/v1/auth/login
{"email":"demo@bolmate.nl","password":"bolmate_demo","fp":"<any-string>"}

POST https://app.bolmate.nl/bolmate-core/v1/search-volumes/get
{
  "account_id": "<from login response user.accounts[0].id>",
  "search_terms": ["laptop", "airfryer", "..."],
  "period": "MONTH",
  "number_of_periods": 12,
  "with_comparison": true
}
```

Auth is returned as a `Set-Cookie: Authorization=...` cookie (also sendable as `Authorization` header).

## Usage

```bash
python3 fetch_search_volumes.py laptop airfryer powerbank

python3 fetch_search_volumes.py -f terms.example.txt \
  --csv out.csv -o out.json --top 30
```

## FiveX (also checked)

Deep notes: [`FIVEX.md`](./FIVEX.md)

```bash
# Sequential only — no bulk endpoint; IP free-quota / CF sensitive
python3 fetch_fivex_search_terms.py -f terms.example.txt --csv fivex.csv -o fivex.json
```

- Public: `GET https://www.fivex.com/api/bol-search-terms?query=...`
- Free limit ~3/day per IP (`429`); `X-FX-Bol-Preview: 1` often still works with pacing
- Portal API twin: `GET https://fivex.com/portal/api/bol-search-terms` → needs API key (`401` without)
- **Not suitable as primary bulk path** vs Bolmate demo multi-term

## Notes

- Demo credentials live in Bolmate’s frontend for their free tool; treat availability/rate limits as third-party.
- For production seller automation, prefer bol’s official Retailer Insights API with your own Client ID/Secret.
