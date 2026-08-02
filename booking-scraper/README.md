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

## Filters (techniek)

De scraper bouwt een `searchresults.nl.html`-URL met `nflt`-chips:

- `review_score=90` — Fantastisch 9+
- `mealplan=1` — ontbijt inbegrepen
- `popular_activities=2` — zwembad
- `roomfacility=32` — balkon
- `price=0-<per-nacht-cap>-1` — ruwe budgetslider (per nacht)

Daarna filtert de scraper **client-side** nogmaals op totale prijs ≤ max en score ≥ min.

**Let op:** Booking’s balkonfilter geldt op accommodatieniveau. De goedkoopste getoonde kamer heeft soms géén balkon (bijv. “ohne Balkon”). Gebruik `--require-room-balcony-text` om die eruit te filteren, of controleer de kamer bij boeking.

## Tests

```bash
PYTHONPATH=. python -m pytest tests -v
```

## Disclaimer

Alleen voor persoonlijk gebruik. Respecteer de gebruiksvoorwaarden van Booking.com; overmatig scrapen kan tot blokkades leiden. Prijzen en beschikbaarheid wijzigen snel — check altijd op Booking.com vóór je boekt.
