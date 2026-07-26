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

Typische runtime: **~6 seconden** per product (was ~22s).

Optimalisaties:
- Geen category-warmup / vaste sleeps
- Images/fonts/trackers geblokkeerd
- API-calls direct vanaf de productpagina (geen aparte basket-pagina)
- Voorraad uit GraphQL-response i.p.v. extra state-fetch

## Technische flow

1. Camoufox opent de productpagina (2e poging bij bot-blokkade)
2. `offerUid` wordt uit de productpagina gehaald
3. REST: `POST /nl/rnwy/basket/v2/items` met `{globalId, quantity:1, offerUid}`
4. GraphQL: `UpdateItemQuantity` naar 500
5. REST: `/messages` voor limiet-/voorraadmeldingen

## Let op

- Dit gebruikt de publieke website-API van bol.com, geen officiële Retailer API
- Gebruik spaarzaam; veel requests kunnen tot tijdelijke blokkades leiden
- Alleen bedoeld voor eigen productresearch / educatief gebruik
