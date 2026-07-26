# Bol.com voorraadchecker (winkelwagenmethode)

Python-script dat de beschikbare voorraad van een bol.com-product bepaalt met de bekende **winkelwagenmethode**:

1. Product in de winkelwagen zetten
2. Aantal verhogen naar **500**
3. De werkelijk beschikbare hoeveelheid uitlezen uit de basket-API

## Installatie

```bash
cd bol-voorraad-checker
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Gebruik

```bash
# Via product-URL
python bol_voorraad.py "https://www.bol.com/nl/nl/p/voorbeeld/9300000123456789/"

# Via product-id
python bol_voorraad.py 9300000123456789

# Specifieke verkoper-offer
python bol_voorraad.py 9300000123456789 --offer-id 1234567890

# JSON-output
python bol_voorraad.py 9300000123456789 --json
```

### Handige opties

| Optie | Betekenis |
| --- | --- |
| `--max-quantity 500` | Aantal dat in de winkelwagen gezet wordt (standaard 500) |
| `--offer-id` | `retailerOfferId` van een specifieke verkoper (`0` = standaard/buy-box) |
| `--country nl\|be` | Nederlandse of Belgische shop |
| `--json` | Machineleesbare output |
| `--keep-in-cart` | Product niet uit de winkelwagen verwijderen na de check |
| `--delay 0.4` | Pauze tussen API-calls |
| `--proxy` | HTTP(S)-proxy, bijv. `http://user:pass@host:port` |

## Voorbeelduitvoer

```text
Product-id : 9300000123456789
Offer-id  : 0 (bol.com buy-box / standaard)
Voorraad  : 37
Opgevraagd : 500
```

Als bol.com `500` teruggeeft zonder limietmelding, is de voorraad **mogelijk 500 of hoger** (bol toont meestal max. 500).

## Belangrijk

- Dit gebruikt de **publieke website-API** van bol.com (`/rnwy/basket/...`), geen officiële Retailer API.
- Bol.com heeft botbescherming (Akamai). Vanaf datacenter-/VPN-IP’s kun je HTTP 403 krijgen. Draai het script idealiter vanaf een gewoon thuisnetwerk.
- Gebruik dit spaarzaam; veel requests kunnen tot tijdelijke blokkades leiden.
- Alleen bedoeld voor eigen productresearch / educatief gebruik.
