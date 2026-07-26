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

# Batch snel (offer-cache + cart-only na 1e product)
python bol_voorraad.py --batch products.txt --out results.jsonl --fast

# Tweede run is sneller: offer_cache.json slaat HTML-stap over (~1s/product)
python bol_voorraad.py --batch products.txt --out results.jsonl --fast --offer-cache offer_cache.json
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
| `--workers N` | Parallelle browsers (op 1 IP vaak trager) |
| `--fast` | Preset: delay=0, geen cleanup, offer-cache |
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

Typisch: **~2–3s/product** (met HTML), **~1–1.5s/product** met offer-cache (cart-only).
Losse HTTP/`curl` → **403** (Akamai); calls blijven in Camoufox.

Optimalisaties:
- Snellere productload (`commit` + fail-fast op blockpages)
- Parallel createBasket + state; hergebruik cart-regel; basket-rotatie
- Offer-cache: na 1e run geen product-HTML meer nodig
- Geen RemoveItem-cleanup; match op `productId`
- Images/fonts/trackers geblokkeerd

## Technische flow

1. Camoufox opent de productpagina (Akamai; nodig voor `offerUid` + cookies)
2. Directe backend-calls in die browser-context:
   - GraphQL `CreateBasket`
   - REST `POST /nl/rnwy/basket/v2/items` `{globalId, quantity:1, offerUid}`
   - GraphQL `UpdateItemQuantity` → 500
3. Voorraad = quantity van de rij met het gevraagde `productId` (niet blind `items[0]`)

Pure `requests`/`curl_cffi` met gekopieerde cookies werkt **niet** (403). Officiële Retailer API vereist retailer-credentials en toont alleen **jouw** offers.

## Let op

- Publieke website-API van bol.com, geen officiële Retailer API
- Gebruik spaarzaam; veel requests → tijdelijke blokkades
- Alleen voor eigen productresearch / educatief gebruik
