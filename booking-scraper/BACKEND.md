# Booking.com — backend & filters

## Backend-ingangen

| Pad | Bron | Gebruik |
| --- | --- | --- |
| **Capla Apollo store** | `script[data-capla-store-data]` → `ROOT_QUERY.searchQueries.search(...)` | Primair in scraper |
| **GraphQL** | `POST https://www.booking.com/dml/graphql` | WAF + CSRF + persistedQuery-hash |
| **Demand API** | `POST /accommodations/search` | Alleen partners |
| **Autocomplete** | `accommodations.booking.com/autocomplete.json` | `dest_id` lookup |

CSRF: `script[data-capla-application-context].csrfToken`.

Zwarte Woud / Black Forest = `dest_id=1477`, `dest_type=region`.

## `nflt` filtertaxonomie (Capla, Zwarte Woud)

Chips komen uit `search.filters` in de Capla-store. Catalogus:  
`booking_scraper/data/filter_catalog.json` (187 chips).

### Gecorrigeerde kernfilters

| Filter | Chip | Label |
| --- | --- | --- |
| Score 9+ | `review_score=90` | Fantastisch: 9+ |
| Ontbijt | `mealplan=1` | Ontbijt inbegrepen |
| **Zwembad** | `hotelfacility=433` | Zwembad *(niet `popular_activities=2`)* |
| **Balkon** | `roomfacility=17` | Balkon *(niet `roomfacility=32`)* |
| Terras | `roomfacility=123` | Terras |
| Sauna | `popular_activities=10` | Sauna |
| Parkeren | `hotelfacility=2` | Parkeren |
| Spa | `hotelfacility=54` | Spa- en wellnesscentrum |
| Gratis annuleren | `fc=2` | Gratis annuleren |
| Erg goed ontbijt | `rated_high=1` | Erg goed ontbijt |

### Andere nuttige families

- **Maaltijden:** `mealplan=9` halfpension, `mealplan=3` all-inclusive, `mealplan=999` keuken  
- **Accommodatietype:** `ht_id=204` hotels, `201` appartementen, `208` B&B, `216` pensions, `220` vakantiehuizen, `privacy_type=3` hele woning  
- **Sterren:** `class=1`…`class=5`  
- **Kamer:** `roomfacility=38` eigen badkamer, `81` uitzicht, `999` keuken/kitchenette, `5` bad  
- **Activiteiten:** `popular_activities=70/76/86/26` (wandelen/fietsen/…)  
- **Steden (`uf=`):** Freiburg `-1771505`, Baden-Baden `-1743083`, Titisee `-1874960`, Rust `-1854104`, Bad Wildbad `-1888060`, Bazel `-2551183`, …  
- **Prijs (per nacht):** `price=0-<max>-1`

Named aliases: `python scrape.py --list-filters`.

## Zoek-input (Capla)

```json
{
  "dates": { "checkin": "2026-08-26", "checkout": "2026-08-29" },
  "location": { "destId": 1477, "destType": "REGION", "searchString": "Zwarte Woud" },
  "nbAdults": 2,
  "nbRooms": 1,
  "filters": {
    "selectedFilters": "review_score=90;mealplan=1;hotelfacility=433;roomfacility=17;price=0-167-1"
  },
  "sorters": { "selectedSorter": "price" },
  "pagination": { "offset": 0, "rowsPerPage": 25 }
}
```
