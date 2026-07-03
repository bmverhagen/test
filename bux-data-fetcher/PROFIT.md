# Doel: consistent winstgevend — niet hoge win rate

De strategie optimaliseert voor **netto PnL en expectancy** na fees, niet voor win rate.

## Primaire metrics

| Metric | Doel |
|--------|------|
| **OOS expectancy** | > €0 per trade |
| **OOS netto PnL** | > €0 per aandeel |
| **Profit factor** | > 1.0 |
| **Alpha vs buy & hold** | ≥ €0 (optioneel) |

Win rate is **secundair** — een 55% WR met 2:1 R:R is beter dan 75% WR met 1% TP.

## Aanbevolen strategie: Pro Mean Reversion

```bash
python3 compare_strategies.py --count 100
python3 backtest.py validate --profile pro
python3 screen_stocks.py --profile pro
python3 fetch_yahoo.py test --count 100 --profile pro
```

## Default parameters (Dip)

| Parameter | Waarde | Reden |
|-----------|--------|-------|
| Take profit | 4% | Ruim boven fee breakeven |
| Stop loss | 2.5% | Asymmetrisch R:R |
| Positie | €1000 | Lage fee drag |

## Screener filters (OOS holdout)

- Min 3 trades op testperiode
- Netto PnL > €0
- Expectancy > €0/trade

Geen win-rate filter.

## Anti-overfit

- Score optimize/validate op **test expectancy + net PnL**
- Train/test split 70/30
- Overnight gaps gemodelleerd (close → open)

Zie [STRATEGY_PRO.md](./STRATEGY_PRO.md) voor Pro-regels.
