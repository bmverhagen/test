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

## Wat dit bewijst

- Signalen worden gedetecteerd op **behoefte/format-niveau**, niet op los ASIN-niveau
- Mid-tail momentum wordt afgezet tegen de categorie-baseline (geen seizoensruis)
- Elke bevinding krijgt een funnel-fase + concrete actie — het digest-formaat dat
  aan brand/e-commerce teams wordt geleverd
