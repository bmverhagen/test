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

## Dagelijkse radar (`daily_radar.py`) — "elke dag alle trends"

Bindt beide scrapers samen tot een dagelijkse pijplijn met een
**tijdreeks-geheugen** (SQLite), zodat je niet alleen een momentopname
krijgt maar bewéging: wat is NIEUW vandaag, wat ACCELEREERT, wat KOELT AF.

```
1. tiktok_scrape.py  -> trending hashtag-chart (alle regio's)
2. tiktok_tags.py    -> jouw keyword-watchlist (+ co-hashtag discovery)
3. ingest in SQLite  -> één rij per key per dag
4. diff vandaag vs vorige run:
     NEW          = keys die vandaag nieuw zijn
     ACCELERATING = momentum/velocity hoger dan gisteren (2e afgeleide)
     COOLING      = momentum/velocity lager dan gisteren
5. dagelijkse digest, nieuwste & snelst stijgende bovenaan
```

De SQLite-historie is wat échte trenddetectie mogelijk maakt: momentum is
een 1e afgeleide, **acceleration** (verandering van momentum t.o.v.
gisteren) is de 2e afgeleide en het vroegste betrouwbare doorbraaksignaal.

```bash
# volledige dagelijkse run (scrape + ingest + digest):
python3 daily_radar.py --regions US,GB,DE,NL --periods 7,30 \
    --tags-region NL --discover

# opnieuw analyseren zonder scrapen (gebruikt laatste snapshots):
python3 daily_radar.py --skip-scrape
```

Dagelijks laten draaien via cron (elke ochtend 06:00):

```cron
0 6 * * * cd /pad/naar/trend-radar && python3 daily_radar.py \
    --regions US,GB,DE,NL --tags-region NL --discover >> data/radar.log 2>&1
```

De tijdreeks staat in `data/trend_history.db`; na de tweede run verschijnen
de ACCELERATING/COOLING-secties automatisch.

## Attribuut-brug (`attribute_bridge.py`) — trends koppelen aan Amazon

Zet ruwe TikTok-trends om naar **product-attributen** (ingrediënt / format
/ zorg / techniek) in exact het vocabulaire dat de Amazon-engine uit
titels haalt. Zo wordt elke trend een rij die je 1-op-1 aan Amazon-
producten koppelt. Media-ruis (nieuws, celebs, memes) komt er nooit in,
omdat de taxonomie alleen product-attributen bevat.

Per attribuut levert het:
- TikTok-kant: views, velocity, engagement, én de **merken** die de trend
  dragen (uit de captions: Olaplex, K18, Mielle, SheaMoisture, ...)
- Amazon-kant: mid-tail momentum + funnel-fase (via `engine.py`)
- een **cross-platform actie**:
  - hype zónder Amazon-product → WHITESPACE (maken/inkopen)
  - hype mét stijgende Amazon-omzet → ACT NOW
  - Amazon groot, hype vlak → DEFEND / MATURE

### Second-order signalen (uit de ruwe video's, geen extra scraping)

Views en velocity alleen zeggen niet of een trend écht is en of er geld in
zit. Daarom rekent de brug per attribuut extra leading indicators uit over
de ~150 geoogste video's:

| signaal | wat het meet | waarom het telt |
|---|---|---|
| **save-rate** | bookmarks/plays | mensen saven wat ze willen kopen/proberen — sterkste koopintentie-proxy |
| **unique creators** + top-author-share | breedte van de trend | 1-2 accounts = toeval; 100+ onafhankelijke creators = echte trend |
| **breakout-share** | aandeel video's met plays > 5× de followers van de maker | het algoritme duwt het onderwerp voorbij bestaande audiences = pre-viral |
| **koopintentie** | aandeel captions met shop-cues (tiktokshop, link in bio, #ad, korting, …) | scheidt koopbare trends van pure media-trends |
| **branded-share + merkconcentratie** | hoeveel video's noemen een merk, en domineert er één? | onbrande vraag + koopintentie = **private-label gat**; één dominant merk = benchmark/dupe-doelwit |
| **versheid** | aandeel <30 dagen oud + plays recent vs ouder | nog stijgend of al gepiekt? |

Deze worden gecombineerd tot een **conviction-score (0-100)**: hoeveel
onafhankelijke signalen elkaar bevestigen. Eén hete metric kan toeval
zijn; velocity + saves + creator-breedte + koopintentie + algoritme-push
die elkaar bevestigen zelden. Bij één dominant account krijgt de score
een korting.

Daarnaast krijgt elk attribuut een **commerciële lezing van het merkveld**:
- `PRIVATE-LABEL KANS` — koopintentie zonder merkdominantie (instappen)
- `MERK-GEDOMINEERD` — één merk bezit de trend (dupe/benchmark)
- `GEFRAGMENTEERD MERKVELD` — ruimte voor een challenger
- `MEDIA-TREND` — nog weinig directe koopsignalen

Voorbeeld uit een echte run: *scalp serum* kreeg conviction 69% met
`PRIVATE-LABEL KANS` (14% koopintentie, geen dominant merk), terwijl
*heatless curls* met méér views als media-trend werd ontmaskerd
(47% algoritme-push maar 1% koopintentie).

### NL-trending — hoe trending is het in Nederland (niet global)

De tag-totalen van TikTok zijn globaal, maar TikTok stuurt per video wél
zijn eigen taalclassificatie mee (`textLanguage`). Nederlandstalige
video's zijn een harde NL/Vlaanderen-proxy — daarmee meten we per trend
hoe groot hij ís in Nederland, zonder proxy of login:

- per tag: **nl-share** (aandeel NL-video's in de feed), **nl-plays**,
  **NL-velocity** (posts/dag laatste 7d vs 30d ervoor, alléén binnen de
  NL-video's) en **est. NL views** (tag-totaal × NL-aandeel)
- `tiktok_tags.py` print automatisch een NL-TRENDING-ranking zodra er
  Nederlandstalige video's in de harvest zitten
- `attribute_bridge.py --nl` rankt de attributen op geschatte NL-views
  (som van de per-tag schattingen, zodat een globale Engelse tag nooit
  NL-views "leent" van een Nederlandse zustertag)

```bash
python3 tiktok_tags.py --region NL          # NL-watchlist + NL-ranking
python3 attribute_bridge.py --nl            # attributen op NL-relevantie
```

Voorbeeld uit een echte run (zonder proxy!): *#krullen* is de grootste
NL-trend (57% Nederlandstalig, ±580M NL-views, NL-velocity x8.2),
*#hoofdhuid* is bijna puur NL (82%) en *haaruitval* versnelt hard
(x6.4). Een NL-residential-proxy blijft een upgrade (dan is ook de
feed-samenstelling zelf NL-gewogen), maar is niet meer nodig om
NL-trends te kunnen ranken.

## Sector + land → trending terms (`trending.py`)

Het hoofdcommando: geef een **sector** en een **land**, krijg de meest
trending terms terug inclusief onderliggende data.

```bash
python3 trending.py --sector hair --country NL
python3 trending.py --sector skincare --country DE
python3 trending.py --sector food --country BE --top 15
python3 trending.py --sector custom --seeds airfryer,heteluchtfriteuse \
                    --lexicon airfryer,frituur --country NL
```

Ingebouwde sectoren: `hair`, `skincare`, `makeup`, `fitness`,
`cleaning`, `food`, `pets` — elk met seeds per taal (landstaal + de
Engelse tags die lokale creators ook gebruiken) en een sector-lexicon
voor discovery. Landen: NL, BE, DE, AT, FR, ES, IT, US, GB.

Per term krijg je:
- **trend-score 0-100** = 35% lokale versnelling + 25% lokale
  activiteit (posts/dag laatste 7d) + 25% lokale omvang (est. views)
  + 15% engagement
- globale totalen, lokale share/plays/est. views, posts/dag,
  velocity-ratio, lokale co-hashtags en top lokale video's
- alle lokale video's ruw in `data/trending_<sector>_<land>.json`

**Discovery** mint co-hashtags uit lokale video's die op het
sector-lexicon matchen en oogst de beste automatisch mee — zo vind je
termen die je zelf niet had bedacht. Live voorbeeld (skincare/NL):
`#huidverbetering` (score 70, x5.7 versnelling, 82% NL) en
`#huidtherapeut` zaten niet in de seeds maar werden ontdekt en bleken
respectievelijk #1 en #3 van Nederland.

Kanttekening: voor Engelstalige landen (US/GB) bewijst taal alleen
"Engels", niet het land — daar is een residential proxy in het doelland
de upgrade. Voor NL/DE/FR/ES/IT is taal een sterke land-proxy.

## Echte per-land vraag, taal-onafhankelijk (`country_demand.py`)

TikTok publiceert geen per-land views, en een taalfilter mist
Nederlanders die Engelse termen kijken/zoeken ("olaplex", "heatless
curls"). `country_demand.py` vult dat gat met de officiële per-land
databron: Google Trends met `geo=NL` — meet wat héél Nederland zoekt,
ongeacht taal.

```bash
python3 country_demand.py --country NL \
    --from-tiktok data/trending_hair_nl_top200.json --limit 80 --rising
python3 country_demand.py --country NL --terms krullen,olaplex
```

- **Anker-normalisatie**: Google Trends normaliseert alleen bínnen één
  opvraag; door in elke batch een vast anker mee te sturen (default
  "shampoo") worden alle termen cross-batch vergelijkbaar
  (index 50 = half zo veel gezocht als shampoo in NL).
- **Momentum**: laatste 14 dagen vs de 30 ervoor.
- **Combined score**: 50% NL-zoekvraag × momentum + 50% TikTok
  trend-score — hype én echte landelijke vraag in één getal.
- **`--rising`**: Google's eigen RISING/BREAKOUT zoekopdrachten per
  topterm — productniveau-vraag die NU opkomt in het land, alle talen
  (live voorbeeld: "krultang automatisch" +550%, "stijltang en krultang
  in 1" BREAKOUT, "k18 leave-in molecular repair hair mask" +190%,
  "krullen crème kruidvat" +140%).
- Hashtags worden automatisch naar zoektermen gesegmenteerd
  ("heatlesscurls" → "heatless curls"); Nederlandse compounds blijven
  intact.

Vereist `pytrends` (`pip install pytrends`).

De headline-cijfers komen alleen van direct geoogste tags; attributen die
alleen als co-hashtag opduiken verschijnen als DISCOVERY-kandidaten voor de
watchlist (ze erven nooit de views van hun parent-tag).

```bash
python3 generate_demo_data.py     # zodat de Amazon-kant data heeft
python3 attribute_bridge.py       # join TikTok-hype ↔ Amazon-omzet
python3 attribute_bridge.py --no-amazon   # alleen de TikTok-kant
```

Output: console-digest + `data/attributes.json` — de joinbare
attribuut-tabel (join-key = attribuutnaam, gelijk aan `engine.SIGNALS`).

## Wat dit bewijst

- Signalen worden gedetecteerd op **behoefte/format-niveau**, niet op los ASIN-niveau
- Mid-tail momentum wordt afgezet tegen de categorie-baseline (geen seizoensruis)
- Elke bevinding krijgt een funnel-fase + concrete actie — het digest-formaat dat
  aan brand/e-commerce teams wordt geleverd
