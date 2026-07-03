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

## Beperkingen

- Historische **nieuws-sentiment data** is niet gratis beschikbaar → backtest gebruikt prijsactie als proxy
- 10m data ouder dan 60 dagen is afgeleid van uurdata → minder precisie voor entry-timing
- Resultaten op 3 aandelen zijn **niet representatief** voor alle ~3000 Bux producten
- **Geen garantie** op consistente winst — altijd verder backtesten op meer data
