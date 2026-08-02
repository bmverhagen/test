# Booking.com scraper — Zwarte Woud

Zoekt overnachtingen op Booking.com in het **Zwarte Woud** (Schwarzwald) met deze standaardfilters:

| Filter | Standaard |
| --- | --- |
| Data | 26 → 29 augustus 2026 (3 nachten) |
| Regio | Zwarte Woud (`dest_id=1477`) |
| Prijs | ≤ **€500 totaal** voor het verblijf |
| Beoordeling | **9+** |
| Maaltijd | Ontbijt inbegrepen |
| Faciliteit | Zwembad |
| Kamer | Balkon (Booking-filter) |
| Bezetting | 2 volwassenen, 1 kamer |

Booking.com zit achter AWS WAF, dus de live scraper gebruikt **Playwright** (headless Chromium). HTML kan ook offline geparsed worden via `--from-file`.

## Installatie

```bash
cd booking-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Gebruik

```bash
# Standaardzoekopdracht, leesbare tabel naar stdout
python scrape.py

# JSON / CSV
python scrape.py --format json -o resultaten.json
python scrape.py --format csv -o resultaten.csv

# Alleen de Booking-URL tonen (handig om in de browser te openen)
python scrape.py --print-url

# Strenger: alleen kaarten waarvan de getoonde kamer balkon/terras noemt
python scrape.py --require-room-balcony-text

# Offline parse van opgeslagen HTML
python scrape.py --from-file tests/fixtures/search_results.html --format table
```

Of als module:

```bash
python -m booking_scraper --max-price 450 --adults 2
```

## Backend & filters

Booking levert resultaten via de **Capla Apollo store** (`data-capla-store-data`) — dezelfde JSON als `/dml/graphql`. Zie [BACKEND.md](./BACKEND.md).

Standaard-`nflt` (gecorrigeerd vanuit Capla):

| Filter | Chip |
| --- | --- |
| Score 9+ | `review_score=90` |
| Ontbijt | `mealplan=1` |
| Zwembad | `hotelfacility=433` |
| Balkon | `roomfacility=17` |
| Budget | `price=0-<per-nacht>-1` |

```bash
python scrape.py --list-filters
python scrape.py --filter spa,sauna,parking --free-cancellation
python scrape.py --stars 3,4 --property-type hotels --city freiburg
python scrape.py --balcony-or-terrace --print-nflt
```

Daarna filtert de scraper **client-side** op totale prijs en score. Booking’s balkonfilter is accommodatieniveau — gebruik `--require-room-balcony-text` voor strengere kamernamen.

## Tests

```bash
PYTHONPATH=. python -m pytest tests -v
```

## Disclaimer

Alleen voor persoonlijk gebruik. Respecteer de gebruiksvoorwaarden van Booking.com; overmatig scrapen kan tot blokkades leiden. Prijzen en beschikbaarheid wijzigen snel — check altijd op Booking.com vóór je boekt.
