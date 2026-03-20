# Milestone 3: 2-Year Historical Backtest Performance System

**Status**: ✅ Complete  
**Date**: March 20, 2026

---

## Overview

The backtest system replays 2 years of price history across your entire Indian (or US) universe, fires the same VCP + Range-Expansion detector at every historical bar, then simulates each triggered trade forward until stop, T1/T2/T3, or max-hold is reached.  
All results are aggregated into an interactive HTML performance report.

---

## How It Works

```
run_backtest.py  (Python orchestrator)
│
├─ Loads symbols from CSV (indian_stock_tickers.csv / us_stock_tickers.csv)
├─ Splits into parallel batches (default 20 symbols × 4 workers)
│
├─ Per batch →  java Main --mode=backtest --lookback=728 --export=json
│                │
│                └─ BacktestEngine.java
│                     ├─ Walks every bar i = 40 … N-2
│                     ├─ evaluateAtIndex(symbol, candles, i)
│                     │    └─ VcpDetector + BreakoutEvaluator (same as live scan)
│                     └─ simulateTrade(candles, i, tradePlan)
│                          ├─ Exit at T1/T2/T3 cascade (first target hit wins)
│                          ├─ Exit at stop (conservative: stop fills before target if same bar)
│                          ├─ Exit at max-hold bars (time exit)
│                          └─ Tracks MAE, MFE, holdBars, hitT1/T2/T3
│
├─ Aggregates all batch JSON files
├─ Computes metrics (win rate, avg R, max drawdown, profit factor, etc.)
└─ Generates interactive HTML report
```

---

## Candle Anatomy Weighting (applied during backtest detection)

As of March 2026, every setup detected during backtest replay is scored with the wick/body adjustment:

- **Lower wick** → positive score contribution (demand/support)
- **Bullish body** → positive score contribution
- **Upper wick** → negative score contribution (rejection/supply)
- Capped by `maxWickBodyScoreAdjustment` to prevent scoring instability

This means only setups with healthy candle structure survive the `minQualityScore` gate during replay.

---

## Exit Logic

```
Priority order (per bar after signal):
1. Stop AND Target1 both hit same bar  → STOP fills (conservative)
2. Stop hit                            → STOP
3. High ≥ T3 (3R)                     → TARGET_T3  (hitT1=T hitT2=T hitT3=T)
4. High ≥ T2 (2R)                     → TARGET_T2  (hitT1=T hitT2=T hitT3=F)
5. High ≥ T1 (1R)                     → TARGET_T1  (hitT1=T hitT2=F hitT3=F)
6. Max hold reached                    → TIME_EXIT
```

T2 and T3 are also flagged as *milestones* on each bar even when exit is later — so you can analyse "how far did winning trades actually run?"

---

## Metrics Explained

| Metric | Formula |
|---|---|
| Win Rate | trades with R > 0 / total trades × 100 |
| Avg R | Total R / trade count |
| Total R | Sum of all R-multiples |
| Max Drawdown | Peak-to-trough in cumulative R series |
| Profit Factor | Sum positive R / abs(sum negative R) |
| Avg MAE | Average max adverse excursion % from entry |
| Avg MFE | Average max favorable excursion % from entry |
| Avg Hold | Average hold duration in bars |
| T1 Hit Rate | Trades where T1 was touched / total × 100 |
| T2 Hit Rate | Trades where T2 was touched / total × 100 |
| T3 Hit Rate | Trades where T3 was touched / total × 100 |

---

## HTML Report Sections

1. **Summary Cards** — 9 key stats at a glance
2. **Target Hit Rates** — T1 / T2 / T3 milestone rates side-by-side
3. **Cumulative R Curve** — SVG polyline of running P&L in R-multiples
4. **Monthly Heatmap** — Grid of net R per calendar month (green=profit, red=loss)
5. **Breakdown Panels** — Win rate / avg R grouped by: Setup Type, Rating, Window, Exit Reason
6. **Trade Table** — Full sortable/filterable list of every simulated trade

---

## Usage

### Quick start — India daily 2-year backtest
```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_backtest.py
```

### All options
```bash
python3 run_backtest.py --market india --timeframe daily  --setups both  --hold-bars 20
python3 run_backtest.py --market india --timeframe weekly --setups both  --hold-bars 8
python3 run_backtest.py --market us    --timeframe daily  --setups vcp   --hold-bars 15
python3 run_backtest.py --market india --workers 6 --batch 25
python3 run_backtest.py --matrix-all --setups both
```

### Output files
```
output/
├── backtest_us_daily_LATEST.html
├── backtest_us_weekly_LATEST.html
├── backtest_india_daily_LATEST.html
├── backtest_india_weekly_LATEST.html
├── backtest_matrix_LATEST.html          ← combined 4-run summary
├── backtest_matrix_LATEST.md
├── backtest_matrix_LATEST.json
└── backtest_india_daily_<timestamp>/
    ├── backtest_india_daily_<ts>.html
    ├── backtest_india_daily_<ts>.csv
    └── batch_work/
        ├── batch_0000_backtest.json
        ├── batch_0001_backtest.json
        └── ...
```

---

## Files Changed / Created

| File | Change |
|---|---|
| `src/BacktestTrade.java` | Added: setupType, setupRating, windowLabel, qualityScore, mae, mfe, holdBars, hitT1/T2/T3 |
| `src/BacktestEngine.java` | T1/T2/T3 cascade exits; MAE/MFE tracking; setup metadata in output |
| `src/BacktestReport.java` | Added: maxDrawdown, profitFactor, avgMae, avgMfe, avgHoldBars, T1/T2/T3 hit counts |
| `src/ResultExporter.java` | Updated CSV + JSON export to include all new fields |
| `run_backtest.py` | **NEW** — full parallel orchestrator + metrics + HTML report |
| `docs/MILESTONE_3_BACKTEST.md` | **NEW** — this document |

---

## Assumptions & Limitations

- **Entry price** = close of the signal bar (market-on-close assumption)
- **Stop** = support price × (1 - stopBufferPct)
- **Targets** = T1 = 1R, T2 = 2R, T3 = 3R above entry
- **Same-bar conflict** = if stop and T1 both hit on same bar, stop is assumed to fill first (conservative)
- **Slippage / commissions** = not modelled (R-multiple is a cleaner measure)
- **Position sizing** = same as live scanner (1% risk per trade on ₹1 Cr account)
- Cache is used with TTL=9999 min (no re-fetching during backtest run)

---

## Report Column Glossary (UI)

### Scan report columns
- `Base Height %`: base range height between support and pivot in percent
- `Contraction Depth %`: normalized contraction depth used by VCP scoring
- `Base Length`: number of bars in the evaluated base window
- `Contraction Pairs`: effective contraction pair count (range + volume)
- `Pivot Distance %`: distance from current close to pivot
- `Range Expansion x`: breakout expansion multiplier vs base

### Backtest trade table columns
- `Trade Setup`, `Setup Rating`, `Setup Window`, `Quality Score`
- `Entry Price`, `Exit Price`, `R Multiple`
- `Hold Bars`, `MAE (%)`, `MFE (%)`, `Exit Reason`

