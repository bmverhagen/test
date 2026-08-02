# Booking.com — directe backend-ingangen

De HTML-kaarten zijn niet de bron. Booking levert zoekresultaten via Capla/GraphQL.

## 1. Capla Apollo store (SSR, aanbevolen)

Elke `searchresults`‑pagina bevat:

```html
<script type="application/json" data-capla-store-data>
  { "ROOT_QUERY": { "searchQueries": { "search({...})": { "results": [...], "pagination": {...} } } } }
</script>
```

Dit is de genormaliseerde Apollo-cache van dezelfde GraphQL-query die de frontend gebruikt.

| Veld | Pad |
| --- | --- |
| Resultaten | `ROOT_QUERY.searchQueries["search({input})"].results[]` |
| Totaal | `...pagination.nbResultsTotal` |
| Naam | `displayName.text` |
| Score | `basicPropertyData.reviews.totalScore` |
| Totaalprijs | `priceDisplayInfoIrene.displayPrice.amountPerStay.amountUnformatted` |
| Per nacht | `priceDisplayInfoIrene.averagePricePerNight.amountUnformatted` |
| Ontbijt | `mealPlanIncluded.text` / `mealPlanType` |
| Kamer | `matchingUnitConfigurations.commonConfiguration.name` |

Auth-context zit in:

```html
<script type="application/json" data-capla-application-context>
  { "csrfToken": "eyJ...", "affiliate": { "id": 304142 }, "pageviewId": "..." }
</script>
```

De scraper leest dit via `booking_scraper.capla` (primaire parser).

## 2. GraphQL API

```
POST https://www.booking.com/dml/graphql?lang=nl
Content-Type: application/json
Cookie: aws-waf-token=...
X-Booking-CSRF-Token: <csrfToken uit application-context>
```

Body (persisted query):

```json
{
  "operationName": "FullSearch",
  "variables": { "input": { "...zelfde input als in de Capla search-key..." } },
  "extensions": {
    "persistedQuery": {
      "version": 1,
      "sha256Hash": "<hash uit frontend bundle>"
    }
  }
}
```

Vereisten:

- Geldige **AWS WAF**-cookie (`aws-waf-token`) — zonder browser-sessie → 403
- Geldige **CSRF**-JWT uit Capla context
- Correcte **persistedQuery sha256Hash** (wijzigt met frontend-deploys)
- GET op dit endpoint → `405`; onbekende hash → `PersistedQueryNotFound`

Omdat de hash breekbaar is, gebruikt deze scraper Capla-SSR i.p.v. losse GraphQL-POSTs.

## 3. Officiële Demand API (partners)

```
POST https://demandapi.booking.com/3.2/accommodations/search
Authorization: Bearer <partner-token>
```

Alleen voor goedgekeurde affiliates/OTA’s — niet publiek.

## 4. Autocomplete (bestemming → dest_id)

```
GET https://accommodations.booking.com/autocomplete.json?query=Schwarzwald&lang=nl&size=10
```

Zwarte Woud / Black Forest = `dest_id=1477`, `dest_type=region`.

## Zoek-input (uit Capla)

```json
{
  "dates": { "checkin": "2026-08-26", "checkout": "2026-08-29" },
  "location": { "destId": 1477, "destType": "REGION", "searchString": "Zwarte Woud" },
  "nbAdults": 2,
  "nbChildren": 0,
  "nbRooms": 1,
  "filters": {
    "selectedFilters": "review_score=90;mealplan=1;popular_activities=2;roomfacility=32;price=0-167-1"
  },
  "sorters": { "selectedSorter": "price" },
  "pagination": { "offset": 0, "rowsPerPage": 25 }
}
```
