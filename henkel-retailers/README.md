# Henkel haarproducten — top 20 NL webshops

Eerste stap voor conditioner-rank/BSR-onderzoek: **waar** worden Henkel-haarmerken
(Syoss, Schwarzkopf, Gliss, Taft, got2b, …) in Nederland online verkocht.

## Rankingmethode

Dit is **geen officiële Henkel-omzetranking** (die is niet publiek). De volgorde
combineert:

1. **Marktrelevantie** in NL mass hair care (drogist / supermarket / marketplace)
2. **Geverifieerde productaanwezigheid** (publieke product-/merkenpagina’s of
   folderacties met Syoss / Gliss / Schwarzkopf)
3. **Online bereikbaarheid** (eigen webshop of sterke online checkout)

Focus: **Nederland**. Internationale DE-ketens (dm, Rossmann) staan niet in deze
lijst tenzij ze een sterke NL-webshop hebben.

## Output

| Bestand | Inhoud |
| --- | --- |
| `data/top20_shops.json` | Gerankte lijst + merken + bewijs-URL’s |
| `data/top20_shops.csv` | Zelfde data, plat voor spreadsheets |
| `brands.py` | Henkel-merklijst gebruikt voor latere scrapes |
| `data/conditioner_ranks/conditioner_ranks_latest.json` | Conditioner-zoekranks per shop |
| `data/conditioner_ranks/conditioner_ranks_latest.csv` | Plat productbestand |
| `data/conditioner_ranks/summary.csv` | Per-shop status + Henkel best rank |

## Conditioner ranks (BSR-proxy)

Zoek/categorie-positie voor query **`conditioner`** op alle 20 shops:

```bash
cd conditioner_scraper
python3 scrape_conditioner_ranks.py   # pages 1..10 per shop
```

Elke shop heeft resultaten. Waar live fetch geblokkeerd is (datacenter-IP/CDN),
worden curated conditioner-rijen toegevoegd zodat de dataset toch gevuld is;
die rijen staan gemarkeerd in `note` / `fallback`.

`rank` = positie in de opkomende lijst (zoekresultaat of categorie “meest relevant”).
Dat is een **BSR-proxy**, geen officiële Amazon BSR behalve op Amazon zelf.

Sommige shops blokkeren datacenter-IP’s (o.a. Bol, Etos, AH). Voor die shops staat
`source_type=serp_fallback` / `fallback_web` en is de volgorde een publieke zoekhit-
ranking, niet de live on-site sort.

## Belangrijk voor BSR

Alleen **Amazon.nl** heeft een echte Best Sellers Rank. Overige shops hebben hooguit
zoekpositie of eigen populariteitssignalen. Gebruik deze top 20 als retailer-scope;
meet “rank” daarna per platform apart.
