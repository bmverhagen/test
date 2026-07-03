# Bux Zero Historische Data Fetcher

Haalt alle aandelen/ETF's op die via Bux Zero verhandeld worden en downloadt **10-minuten OHLCV candles** voor de afgelopen 2 jaar.

## Vereisten

- Python 3.10+
- Een **Bux Zero account** met access token (voor de volledige productlijst)
- Optioneel: OpenFIGI API key (voor ISIN → Yahoo Finance ticker mapping)

## Installatie

```bash
cd bux-data-fetcher
pip install -r requirements.txt
cp .env.example .env
```

## Bux Token ophalen

```bash
python3 -m bux get-token
```

Plak het token in `.env`:

```
BUX_TOKEN=jouw_token_hier
```

## Gebruik zonder Bux token (Yahoo Finance)

Geen Bux account nodig. Haal random US aandelen op via Yahoo Finance en test de strategie:

```bash
# 100 random aandelen downloaden (NASDAQ/NYSE universe, ~5 min)
python3 fetch_yahoo.py random --count 100 --seed 42

# Strategie testen op die 100 aandelen (OOS validatie)
python3 fetch_yahoo.py test --count 100 --profile pro

# Fetch + test in één keer
python3 fetch_yahoo.py test --count 100 --fetch
```

Ticker universe komt van [NASDAQ symbol directory](https://nasdaqtrader.com/) (~5000+ US equities), geen Wikipedia of Bux token vereist.

Output:
- `data/yahoo_random_100.txt` — lijst tickers
- `data/candles_10m/{TICKER}.parquet` — 10m OHLCV
- `data/random_100_results.csv` — per-aandeel resultaten

## Gebruik

```bash
# Alles ophalen (instrumenten + historische data)
python fetch_all.py all

# Alleen instrumentenlijst
python fetch_all.py instruments

# Alleen historische data (vereist bestaande instruments.parquet)
python fetch_all.py history

# Test met 5 instrumenten
python fetch_all.py all --limit 5
```

## Output

```
data/
├── instruments.parquet      # Alle Bux producten (ISIN, naam, ticker)
├── progress.json            # Voortgang bij grote downloads
└── candles_10m/
    ├── US0028241000.parquet # 10-min candles per instrument
    └── ...
```

Elke candle file bevat kolommen: `open`, `high`, `low`, `close`, `volume`, `source`, `isin`, `name`, `ticker`.

## Data bronnen

| Bron | Wat | Beperking |
|------|-----|-----------|
| **Bux API** | Volledige productlijst (~3000+) | Vereist `BUX_TOKEN` |
| **bux.com productlijst** | Fallback zonder token | Beperkt door WAF (16-50 producten) |
| **Yahoo Finance 5m** | Laatste 60 dagen | Resampled naar 10m |
| **Yahoo Finance 1h** | Laatste ~2 jaar | Resampled naar 10m |
| **Bux graph API** | App-grafiek data | Beperkte historie (geen echte 10m) |

### Belangrijke beperking

**Echte 10-minuten data voor een volledige 2-jaar periode is niet gratis beschikbaar.** Yahoo Finance biedt:
- 5-minuten data: maximaal **60 dagen** terug
- 1-uur data: maximaal **730 dagen** terug

Dit script combineert beide bronnen en resampled naar 10-minuten candles. Voor de periode ouder dan 60 dagen zijn de 10m-bars afgeleid van uurdata (elke 6 bars delen dezelfde OHLC).

Voor professionele tick-level 10m data over 2 jaar heb je een betaalde data provider nodig (bijv. Polygon.io, EODHD).

## Geschatte schaal

- ~3.000 instrumenten
- ~2 jaar × 252 handelsdagen × 6.5 uur × 6 bars/uur ≈ **~30.000 bars/instrument**
- Totale download: uren (rate limiting + Yahoo API)

## Herstarten na onderbreking

Het script slaat voortgang op in `progress.json` en slaat reeds gedownloade instrumenten over. Gebruik `--force` om alles opnieuw te downloaden.

## Trading strategie & backtest

Zie [STRATEGY.md](./STRATEGY.md) voor de **Sentiment Dip Recovery** strategie.

```bash
# Historisch nieuws scrapen (Google News RSS, 2 jaar)
python3 fetch_news.py

# Backtest op alle beschikbare candle data
python3 backtest.py all

# Backtest met verplicht negatief nieuws-sentiment
python3 backtest.py all --require-news

# Vergelijk met buy & hold en random baseline
python3 backtest.py compare

# Screen aandelen op volatiliteit, liquiditeit & dip-geschiktheid
python3 screen_stocks.py --extra

# Plot trades (instap ▲ / verkoop ▼) op prijsgrafiek
python3 plot_trades.py --from-results data/random_100_results.csv --top 3 --bottom 3
python3 plot_trades.py --tickers BGMS,TOYO,AQB
```

### Nieuws data

Nieuws wordt gescraped via **Google News RSS** (met `after:/before:` datumbereiken) + **Yahoo Finance** recent nieuws. Opgeslagen in `data/news/{ISIN}.parquet` met sentiment score per headline.
