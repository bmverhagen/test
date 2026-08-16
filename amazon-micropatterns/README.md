# Amazon Micropatronen — Long-tail attribute clusters

Automatisch ontdekken welke **attribuut-clusters** in de Amazon **long-tail**
stijgen of dalen — niet top-100 bestsellers, niet losse ASINs, geen handmatige
taxonomie.

## Wat dit anders doet dan Trend Radar (mid-tail PoC)

| | Trend Radar (`engine.py`) | Micropatronen (deze map) |
|---|---|---|
| Vocabulaire | Curated `SIGNALS` / taxonomie | Bottom-up n-grams uit titels |
| Eenheid | Vooraf benoemd signaal | Auto-cluster van co-occurring phrases |
| Rank-band | Mid-tail ~300–3000 | Long-tail ~1500–25000 (top-300 uitgesloten) |
| Vraag | "Doet bond repair het?" | "Welke onbekende micropatronen komen op?" |

## Pipeline

```
ASIN-titels + dagelijkse rank/reviews
        │
        ▼
phrase-extractie (uni/bi/trigrams, brand/stopword-filter)
        │
        ▼
co-occurrence clustering (Jaccard-graaf → micropatronen)
        │
        ▼
long-tail momentum (28d vs 28d, minus categorie-baseline)
        │
        ▼
fase: EXPLODING / RISING / WATCH / DECLINING / FADING
```

Een micropatroon is bv. `rice water · fermented` — meerdere attributen die
samen op dezelfde long-tail producten voorkomen en collectief stijgen.

## Draaien

```bash
cd amazon-micropatterns
python3 generate_longtail_demo.py   # demo-catalogus met plantbare patronen
python3 run_micropatterns.py        # digest + reports/micropatterns.json
python3 -m unittest discover -s tests -v
```

Alleen Python 3 stdlib (geen extra packages).

## Demo-data

`generate_longtail_demo.py` plant o.a.:

- **Rising:** fermented rice water rinse, silk protein + heat protect, scalp scrub,
  apple cider vinegar rinse, blue tansy, rosemary oil
- **Declining:** charcoal detox, biotin gummies
- **Ruis:** stabiele long-tail generics + top-sellers (moeten uitgefilterd worden)

In productie vervang je `data/asins.csv` + `data/observations.csv` door Keepa-
achtige historie of je eigen scrape; `extract` / `cluster` / `momentum` blijven gelijk.

## Output

Console-digest met rising vs declining clusters, plus
`reports/micropatterns.json` per cluster: phrases, cohesion, long-tail ASINs,
momentum, fase, voorbeeldproducten.
