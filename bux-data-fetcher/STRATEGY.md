# Sentiment Dip Recovery — Trading Strategie

Backtestbare strategie voor Bux Zero: profiteer van koersdalingen na negatief nieuws/sentiment door de dip te kopen en te verkopen bij herstel.

## Strategie-logica

```
Negatief nieuws / paniek
        ↓
Harde koerscorrectie (-3%+ in 1 uur, volume spike)
        ↓
Wacht op reversal-bevestiging (2 bullish bars / RSI bounce)
        ↓
INSTAP (market buy, €1 fee)
        ↓
Take profit +4%  OF  Stop loss -2.5%  OF  Time stop (13 uur)
        ↓
EXIT (market sell, €1 fee)
```

### Signaal-detectie

| Signaal | Beschrijving |
|---------|--------------|
| **Paniek-drop** | Koers daalt ≥3% in 6 bars (1 uur) + volume ≥1.5× gemiddelde |
| **Sentiment proxy** | Prijsactie als proxy; optioneel nieuws-headlines scoren negatief |
| **Reversal entry** | 2 opeenvolgende groene candles, RSI bounce, of close in bovenste 60% van bar |

### Instap-regels (hoge likelihood)

1. **Niet blind kopen** — wacht tot selling pressure afneemt (reversal)
2. **Fee-drempel** — take-profit minimaal 4% bij €1000 positie (€2 fees = 0.2% drag)
3. **Cooldown** — 3 uur pauze na elke trade tegen overtrading
4. **Positiegrootte** — minimaal €500-€1000 zodat fees <1% van trade zijn

### Kosten (Bux EU market orders)

- **Buy:** €1,00 per market order
- **Sell:** €1,00 per market order
- **Round-trip:** €2,00

Bij €500 positie = 0,4% fee drag → je hebt minimaal ~2,5% koersherstel nodig voor winst.
Bij €1000 positie = 0,2% fee drag → rendabeler.

## Backtesten

```bash
cd bux-data-fetcher

# Alle instrumenten (vereist candle data in data/candles_10m/)
python3 backtest.py all

# Eén aandeel
python3 backtest.py single data/candles_10m/US88025U1097.parquet --show-trades

# Parameter optimalisatie
python3 backtest.py optimize

# Custom parameters
python3 backtest.py all --position 1000 --take-profit 4 --stop-loss 2.5 --drop-pct 3
```

## Geoptimaliseerde defaults (3 test-aandelen)

| Parameter | Waarde | Reden |
|-----------|--------|-------|
| Positie | €1000 | Lagere fee-impact |
| Drop drempel | 3% | Filtert ruis, vangt echte correcties |
| Take profit | 4% | Ruim boven fee breakeven |
| Stop loss | 2.5% | Asymmetrisch R:R (1.6:1) |
| Cooldown | 18 bars | Voorkomt overtrading |

Grid search resultaat op testdata: **49.8% win rate, €+6.16 expectancy/trade, €+1644 netto** over 267 trades.

## Live trading checklist

1. Monitor nieuws via `python3 fetch_news.py` of Bux app voor negatieve headlines
2. Bevestig paniek-drop in chart (≥3% daling + volume)
3. Wacht op reversal — geen knife catching
4. Instappen met market order (€1)
5. Zet mentale take-profit (+4%) en stop-loss (-2.5%)
6. Verkopen bij doel of na max ~13 uur

## Historisch nieuws scrapen

```bash
# Scrape 2 jaar nieuws voor alle instrumenten
python3 fetch_news.py

# Test met 5 instrumenten
python3 fetch_news.py --limit 5

# Meerdere talen (EU aandelen)
python3 fetch_news.py --lang en-US,nl-NL,de-DE
```

**Bronnen:**
- Google News RSS (`after:YYYY-MM-DD before:YYYY-MM-DD` per kwartaal)
- Google News recency (`when:7d`, `when:30d`, `when:1y`)
- Yahoo Finance recent nieuws (yfinance)

Output: `data/news/{ISIN}.parquet` met kolommen `title`, `published_at`, `sentiment`, `source`, `url`.

Backtest met nieuws-filter:
```bash
python3 backtest.py all --require-news
```

## Strategie vergelijking

```bash
python3 backtest.py compare
```

Vergelijkt drie strategieën op dezelfde data:

| Strategie | Beschrijving |
|-----------|--------------|
| **Dip** | Instap na paniek-daling + reversal |
| **Buy & Hold** | 1× kopen aan start, houden tot einde |
| **Random** | Zelfde # trades als dip, random instap **buiten correcties**, zelfde TP/SL/fees |

## Stock screening — welke aandelen passen?

Niet elk aandeel leent zich voor dip-trading. Gebruik de screener om volatiliteit, liquiditeit en mean-reversion te meten:

```bash
python3 screen_stocks.py              # lokale Bux candle data
python3 screen_stocks.py --extra        # + 17 grote EU/US tickers via yfinance
python3 screen_stocks.py --strict       # strengere filters
```

### Aanbevolen requirements (19 aandelen, data-gedreven)

| Filter | Aanbevolen range | Waarom |
|--------|------------------|--------|
| **Dagvolatiliteit** | 1,8% – 4,1% | Genoeg beweging voor 4% TP, niet extreem chaotisch |
| **Geannualiseerde vol** | 28% – 66% | Past bij swing/recovery trades |
| **ATR (dag %)** | 2,3% – 5,4% | Realistische intraday swings |
| **Gem. volume** | ≥ 42.000 | Voldoende liquiditeit |
| **Dollar volume** | ≥ €3M/dag | Lage slippage, betrouwbare fills |
| **Volume CV** | ≤ 1,3 | Geen extreem spiky/onbetrouwbaar volume |
| **Paniek-events/jaar** | ≥ 16 | Genoeg dip-kansen (≥3% drop + volume spike) |
| **Bounce na drop** | ≥ -0,3% | Lichte mean-reversion (positief = beter) |
| **Prijs** | €20 – €996 | Vermijd illiquide penny stocks |

**Sterkste correlaties met dip PnL:** `bounce_after_drop_pct` (+0,38), daarna buy-and-hold return (+0,26). Winners hadden gemiddeld **29 paniek-events/jaar** vs 33 bij verliezers — kwaliteit van bounce telt meer dan pure volatiliteit.

### Welk type aandeel?

| Type | Geschikt? | Voorbeeld |
|------|-----------|-----------|
| **Mid-cap met nieuwsgevoeligheid** | ✓ Best | PHIA.AS (Philips) — enige die alle filters passeerde |
| **Hoge vol growth/biotech** | △ Alleen met strikte SL | TXG — hoge bounce (+1,55%) maar ATR te hoog |
| **Mega-cap (AAPL, MSFT)** | ✗ Te weinig alpha | Lage vol, dip-strategie ≈ buy-and-hold |
| **Hyper-vol (TSLA, AMD, NVDA)** | ✗ Underperformt B&H | Veel dips maar geen consistente edge vs passief |
| **Defensive low-vol (ALV, HEIA)** | ✗ Te weinig kansen | Weinig paniek-events, lage bounce |

### Backtest-filters (indien data beschikbaar)

- **Win rate dip-trades ≥ 75%** (netto na €1 buy + €1 sell fees)
- Minimaal 5 trades voor betrouwbare statistiek
- Expectancy ≥ €0 per trade
- Alpha vs buy-and-hold ≥ €0

### 75% win rate preset

De standaard 4% take-profit levert ~41–59% win rate. Voor **≥75% win rate na fees** gebruik de `high-win-rate` preset:

| Parameter | Default | High win rate |
|-----------|---------|---------------|
| Take profit | 4% | **1%** |
| Stop loss | 2.5% | **5%** |
| Drop drempel | 3% | 3% |

```bash
# Backtest met 75%-WR preset
python3 backtest.py all --profile high-win-rate

# Parameter search met min 75% WR filter
python3 backtest.py optimize --min-win-rate 75

# Screen aandelen (default: high-win-rate + 75% WR filter)
python3 screen_stocks.py --extra
```

**9/19 geteste aandelen** halen ≥75% WR met deze preset (min 5 trades): TXG, AAPL, PHIA.AS, BMW.DE, FLWS, TSLA, SAP.DE, ASML.AS, ALV.DE.

Win rate = percentage trades met `net_pnl_eur > 0` (fees al verwerkt).

## Anti-overfitting

Kleine samples (3–19 aandelen) overfitten snel. Daarom:

| Maatregel | Wat het doet |
|-----------|--------------|
| **Train/test split (70/30)** | Parameters scoren op **test** (laatste 30%), niet op train |
| **`validate` commando** | Toont train vs test + overfit-waarschuwing |
| **`optimize` op OOS** | Alleen combinaties met positieve test expectancy, geen train>>test gap |
| **Vaste presets** | `high-win-rate` preset i.p.v. grid search op kleine sample |
| **Screener OOS** | Win rate & PnL gemeten op holdout periode per aandeel |
| **Kleinere parameter grid** | Minder combinaties = minder data mining |

```bash
# Valideer huidige preset (train vs test)
python3 backtest.py validate --profile high-win-rate

# Backtest alleen out-of-sample
python3 backtest.py all --profile high-win-rate --oos-only

# Backtest + train/test rapport
python3 backtest.py all --profile high-win-rate --validate

# Optimize (score = OOS test, reject overfit)
python3 backtest.py optimize --min-win-rate 75
```

**Regel:** optimaliseer nooit op dezelfde data waarmee je evalueert. Bij <10 aandelen: gebruik vaste presets, geen grid search.

## Test op 100 random aandelen (zonder Bux token)

```bash
python3 fetch_yahoo.py random --count 100
python3 fetch_yahoo.py test --count 100 --profile high-win-rate
```

Resultaat op sample (seed=42, high-win-rate preset):
- **100/100** aandelen data OK via Yahoo Finance
- Portfolio OOS: **72.9% win rate**, maar **negatieve expectancy** (€-2.42/trade)
- **41/100** aandelen individueel winstgevend
- **37/100** halen ≥75% win rate per aandeel

Conclusie: hoge win rate ≠ winstgevend; kleine TP (1%) dekt fees niet altijd op alle aandelen.

## Beperkingen

- Historische **nieuws-sentiment data** is niet gratis beschikbaar → backtest gebruikt prijsactie als proxy
- 10m data ouder dan 60 dagen is afgeleid van uurdata → minder precisie voor entry-timing
- Resultaten op 3 aandelen zijn **niet representatief** voor alle ~3000 Bux producten
- **Geen garantie** op consistente winst — altijd verder backtesten op meer data
