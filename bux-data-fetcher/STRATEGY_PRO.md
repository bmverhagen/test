# Consistent Mean Reversion Pro — Evidence-Based Strategy

Gebaseerd op uitgebreid online onderzoek (Quantitativo, EasySwing, TickerDaily, Alqama QuantX, pfolio, FTO) en backtests op 100 random US aandelen.

## Waarom de oude Dip-strategie faalde

| Probleem | Oplossing in Pro |
|----------|------------------|
| 1% TP te klein vs €2 fees | Min TP 2% (= 3× fee drag) |
| Geen trendfilter | Alleen long boven SMA50 daily |
| Knife-catching | RSI(2)/RSI(14) bounce vereist |
| Vaste SL/TP | ATR-based stop + exit at mean (z-score 0) |
| Te veel trades (ruis) | Striktere confluence + edge filter |
| Geen regime filter | ADX < 40 (skip extreme trends) |

## Pro Strategie — Regels

### Entry (alle vereist)

1. **Trend:** Close > SMA50 (daily)
2. **Regime:** ADX < 40
3. **Extension:** Z-score ≤ -1.2 (prijs onder 78-bar mean)
4. **Momentum turn:** RSI(2) of RSI(14) stijgt vanuit oversold
5. **Volume:** ≥ 1.2× 20-bar gemiddelde
6. **Edge:** Afstand tot mean ≥ 70% van min take-profit (dekt fees)

**Alternatief pad:** Paniek-drop ≥2.5% in 1u + volume + RSI bounce (in uptrend)

### Exit (eerste die triggert)

1. **Mean reversion:** Prijs bereikt SMA(78) — primary exit
2. **Take profit:** +2% bruto minimum
3. **Stop loss:** 2.5× ATR (max 5%)
4. **Time stop:** 60 bars (~10 uur)
5. **RSI(2) > 80:** momentum recovered

## Onderzoeksbronnen

| Bron | Key insight |
|------|-------------|
| [Quantitativo RSI(2)](https://www.quantitativo.com/p/trading-the-mean-reversion-curve) | RSI2 < 10-15 + trend filter → 64% WR, +0.4% per trade |
| [EasySwing RSI Reversion](https://easyswing.trading/blog/rsi-mean-reversion-oversold-bounce) | Bounce candle + volume → 78% WR, +0.44R expectancy |
| [Alqama QuantX](https://github.com/Alqama-svg/Quant_Strategy_Backtester) | Z-score MR + trend filter → Sharpe 2.36, 66% WR |
| [pomegra transaction costs](https://pomegra.io/learn/library/track-e-trading-risk/technical-analysis/chapter-14-what-doesnt-work-and-the-data/transaction-costs-and-edge) | Edge moet ≥3× round-trip costs |
| [TickerDaily RSI](https://tickerdaily.com/learn/swing-trading/rsi) | RSI alleen = negatief; confluence = 65-70% WR |

## Backtest resultaten (100 random US aandelen, seed=42)

| Strategie | Full PnL | OOS PnL | Win rate | Trades/stock |
|-----------|----------|---------|----------|--------------|
| **Dip (high-WR)** | €-13.606 | €-2.056 | 70% | ~50 |
| **Pro Mean Reversion** | **€-506** | **€-280** | **73%** | **~9** |
| Buy & Hold | €+19.212 | — | — | 1 |

**Pro is 27× beter dan Dip** op dezelfde universe, maar nog niet consistent winstgevend op willekeurige small/mid caps.

### Pro selectief (48/100 winstgevend full period)

Top performers: MYPS, SIMO, YDKG, FEMY, OMC, PAGS

## Aanbevolen deployment

```bash
# 1. Data (geen Bux token)
python3 fetch_yahoo.py random --count 100

# 2. Vergelijk strategieën
python3 compare_strategies.py --count 100

# 3. Alleen Pro op winstgevende aandelen (walk-forward)
python3 fetch_yahoo.py test --profile pro  # TODO: wire pro profile
```

### Live checklist

1. **Universe:** Liquid US stocks boven SMA50
2. **Skip:** ADX > 40, afstand tot mean te klein
3. **Entry:** Wacht op RSI bounce + volume
4. **Exit:** Mean reversion eerst, niet greedy TP
5. **Position:** ≥€1000 (fee drag <0.2%)
6. **Validate:** Maandelijks OOS check met `validate` commando

## Eerlijkheid over "consistent profitable"

Geen intraday strategie is **universeel** winstgevend op 100 random aandelen met €1 fees. Research toont edge in:
- **Geselecteerde liquid large-caps** in uptrend
- **Lage frequentie, hoge kwaliteit** setups
- **Mean reversion exits** i.p.v. fixed tiny TP

Pro is de best geteste variant in dit project — gebruik **selectief** op aandelen die walk-forward positive expectancy tonen.
