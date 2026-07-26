# Bol.com voorraadchecker (winkelwagenmethode)

Python-script dat de beschikbare voorraad van een bol.com-product bepaalt met de **winkelwagenmethode**:

1. Productpagina openen
2. Product in de winkelwagen zetten
3. Aantal verhogen naar **500** (GraphQL `UpdateItemQuantity`)
4. Werkelijke beschikbare hoeveelheid uitlezen

Gebruikt [Camoufox](https://github.com/daijro/camoufox) om bol.com’s botbescherming te passeren.

## Installatie

```bash
cd bol-voorraad-checker
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
camoufox fetch
```

## Gebruik

```bash
# Via product-URL
python bol_voorraad.py "https://www.bol.com/nl/nl/p/voorbeeld/9300000123456789/"

# Via product-id
python bol_voorraad.py 9300000123456789

# Specifieke offer
python bol_voorraad.py 9300000123456789 --offer-uid 41925260-65c5-4e37-be1e-7a4b47ba40d1

# JSON-output
python bol_voorraad.py 9300000123456789 --json

# Snelst zonder extra IP: turbo JS-loop + offer-cache (~0.5–0.9s/product)
python bol_voorraad.py --batch products.txt --out results.jsonl --fast

# Echt sneller wall-clock: meerdere proxies / exit-IP's
python bol_voorraad.py --batch products.txt --out results.jsonl --fast --workers 4 --proxy http://user:pass@host:port
```

### Opties

| Optie | Betekenis |
| --- | --- |
| `--max-quantity 500` | Aantal dat in de winkelwagen gezet wordt |
| `--offer-uid` | UUID van een specifieke verkoper-offer |
| `--country nl\|be` | Nederlandse of Belgische shop |
| `--json` | Machineleesbare output |
| `--keep-in-cart` | Product niet opruimen na de check |
| `--headed` | Browser zichtbaar maken |
| `--batch FILE` | Product-ids/URLs (één per regel) |
| `--collect N` | Verzamel N product-ids van bol.com |
| `--batch-run` | Na `--collect` meteen voorraad checken |
| `--out FILE` | JSONL-resultatenbestand |
| `--delay SEC` | Pauze tussen batch-items (default 0) |
| `--workers N` | Parallelle browsers (het best met `--proxy`) |
| `--fast` | Turbo JS-loop + offer-cache + delay=0 |
| `--turbo` | Hele batch in één browser JS-loop |
| `--proxy URL` | Proxy voor parallelle snelheid |
| `--offer-cache FILE` | Cache productId→offerUid (cart-only) |
| `--isolated` | Batch: verse browser-context per product |

## Voorbeelduitvoer

```text
Product   : Wonact Muggenlamp - 4000V - ...
Product-id: 9300000183271157
Offer-uid : a538d4f8-dd41-4cfd-a46a-0092e2c871c2
Voorraad  : 490 (aangepast door bol.com na limiet/voorraadcheck)
Opgevraagd : 500
Melding   : Het artikel ... is niet leverbaar in de gewenste hoeveelheid...
```

Als bol.com `500` teruggeeft zonder voorraadmelding, is de voorraad **mogelijk 500 of hoger**.

## Snelheid

| Pad | Tijd |
| --- | --- |
| `--fast` / turbo (offer-cache) | **~0.5–0.9s/product** |
| 100 producten, 1 IP | **~110s** (100/100, gemeten) |
| Eerste keer / HTML nodig | ~2–4s |
| `--workers N --proxy …` | wall-clock ≈ /N (aparte exit-IP’s) |

Geen publieke stock-API voor willekeurige producten. Retailer API = alleen eigen offers. Losse HTTP/`curl` → **403** (Akamai).

Optimalisaties:
- Chunked turbo JS-loop (minder Python-overhead) + basket-hergebruik
- 403-backoff + mid-batch rewarm/retry (minder mislukte 100-runs)
- `RemoveItem` fire-and-forget ∥ volgende add (als cleanup aan staat)
- Offer-cache slaat HTML-stap over
- Echte parallelle snelheid alleen met proxies (zelfde cloud-IP → Akamai)

## Technische flow

1. Camoufox voor Akamai-TLS + cookies (+ HTML alleen voor `offerUid` indien onbekend)
2. Parallel: GraphQL `CreateBasket` + REST `POST /nl/rnwy/basket/v2/items` (qty 1)
3. GraphQL `UpdateItemQuantity` → 500
4. Voorraad = `items[].quantity` gematcht op `itemId`

Direct `POST` met `quantity:500` is sneller maar onbetrouwbaar (vaak qty=1 zonder echte stock-cap).

## Let op

- Publieke website-API van bol.com, geen officiële Retailer API
- Gebruik spaarzaam; veel requests → tijdelijke blokkades
- Alleen voor eigen productresearch / educatief gebruik
