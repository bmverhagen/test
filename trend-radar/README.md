# Trend Radar — Proof of Concept

Early Commerce Signal engine: detecteert welke productbehoeften en formats in de
Amazon **mid-tail** (rank ~300–3000) al bij shoppers trekken, vóór ze mainstream zijn.

## Pipeline

```
observations (dagelijkse rank/prijs/reviews per ASIN)
        │
        ▼
attribuut-extractie (titel → signalen zoals "bond repair", "scalp serum")
        │
        ▼
rank → geschatte units (power-law proxy)
        │
        ▼
momentum per signaal: mid-tail groei laatste 28d vs 28d ervoor, t.o.v. categorie-baseline
        │
        ▼
funnel-fase: WATCH → FIRST MONEY → PROVEN → ESTABLISHED (+ FADING)
        │
        ▼
wekelijkse digest met acties voor marketing / e-commerce
```

## Draaien

```bash
python3 generate_demo_data.py   # maakt data/asins.csv + data/observations.csv (demo)
python3 run_radar.py            # draait de engine en print de weekly digest
```

Geen dependencies buiten de Python 3 stdlib.

## Data

`generate_demo_data.py` genereert een **demo-dataset** (hair-categorie, 120 dagen,
~70 ASINs) met patronen gemodelleerd naar echte, gedocumenteerde trends
(bond repair, scalp serum, rosemary oil, dalend argan-only). In productie vervang je
deze stap door een dagelijkse Amazon-scrape of een data-provider (Keepa-achtige
historie); de engine (`engine.py`) blijft identiek.

## Pure TikTok-scrape (live, geen login of API-key)

`tiktok_scrape.py` scrapet **echte, live trending hashtags** van TikTok's
Creative Center. De JSON-API daarachter vereist JS-gesigneerde headers en kale
curl krijgt een lege app-shell — maar als een echte browser de pagina laadt,
embedt de server een SSR-payload in de HTML met per hashtag: naam, rank,
posts, video views, industrie, top-creators én een **dagelijkse
populariteitscurve**. Het script:

1. draait headless Chromium (Playwright) en leest die SSR-payload uit
2. oogst per regio (27 landen) × periode (7/30/120 dagen) de top-hashtags
3. berekent momentum uit de dagcurves en classificeert:
   EXPLODING / RISING / PEAKING / FADING

```bash
pip install playwright && python3 -m playwright install chromium
python3 tiktok_scrape.py                        # 8 default-regio's, 30d
python3 tiktok_scrape.py --all-regions --periods 7,30
```

Output: console-tabel + `data/tiktok_trends.json` (incl. ruwe dagcurves).
Dit is de "hype"-kant van de hype-naar-omzet funnel; de Amazon-engine
hieronder is de "revenue"-kant.

## TikTok keyword deep-dive (`tiktok_tags.py`)

Waar `tiktok_scrape.py` TikToks eigen top-3 trendlijsten oogst, duikt
`tiktok_tags.py` diep op een **eigen keyword-watchlist** (het
attribuut-vocabulaire van de Amazon-engine). Per keyword laadt het
`tiktok.com/tag/<keyword>` headless en onderschept TikToks interne API's:

- `challenge/detail` → totaal aantal video's + views voor de hashtag
- `challenge/item_list` → de videofeed, gepagineerd via scrollen
  (~160-190 video's per tag zonder login)

Per video: caption, publicatiedatum, creator, plays, likes, comments,
shares, bookmarks, co-hashtags en muziek. Per keyword aggregeert het:
post-velocity (posts/dag laatste 7d vs 30d ervoor), engagement rate,
top co-hashtags en top-video's.

```bash
python3 tiktok_tags.py                              # default watchlist
python3 tiktok_tags.py --tags rosemaryoil,bondrepair --scrolls 8
```

Output: console-digest + `data/tiktok_tags.json` (alle video's ruw).
De co-hashtags voeden de watchlist automatisch met nieuwe kandidaten;
de velocity-ratio is het vroegste hype-signaal per attribuut.

### Regio-gerichte harvest (bijv. Nederland) + auto-discovery

TikToks tag-feed is geo-afhankelijk (afhankelijk van het IP). Voor
NL-gelokaliseerde data route je via een Nederlandse residential proxy en
zet je de regio. `--region NL` gebruikt een Nederlandse hair-watchlist
(`#haarverzorging`, `#krullen`, `#rozemarijnolie`, `#haaruitval`, ...) en
zet locale/timezone op NL. `--discover` draait één ronde co-hashtag mining
(gefilterd op een hair-lexicon) om nieuwe haartags automatisch toe te
voegen.

```bash
# echte NL-data (proxy vereist):
python3 tiktok_tags.py --region NL --discover \
    --proxy http://user:pass@nl-host:port

# zonder proxy: pijplijn draait, maar feed = IP van deze machine
python3 tiktok_tags.py --region NL --discover
```

Zonder proxy zijn de tag-totalen globaal; de Nederlandstalige tags
brengen alsnog NL-content naar boven. Resultaten worden gesorteerd op
populariteit (views) met velocity per tag. Merk op: de trending-*chart*
van Creative Center dekt NL niet (27 landen, NL niet inbegrepen) — daarom
is deze watchlist + proxy-route de manier om NL-haartrends te krijgen.

## Wat dit bewijst

- Signalen worden gedetecteerd op **behoefte/format-niveau**, niet op los ASIN-niveau
- Mid-tail momentum wordt afgezet tegen de categorie-baseline (geen seizoensruis)
- Elke bevinding krijgt een funnel-fase + concrete actie — het digest-formaat dat
  aan brand/e-commerce teams wordt geleverd
