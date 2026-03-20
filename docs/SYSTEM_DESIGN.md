# System Design - Breakout Scanner (VCP + Range Expansion)

## 1) Objective

Build a practical scanner that identifies bullish breakout entries for both:

- `VCP` (contraction base + breakout), and
- `RANGE_EXPANSION` (contraction base + expansion breakout),

then outputs a complete trade plan for each shortlisted symbol.

## 2) Implemented Architecture

```text
Main
  -> ScannerEngine
      -> MarketDataProvider
      -> VcpDetector
          -> Indicators
      -> BreakoutEvaluator
      -> TradePlanner
  -> ScanResult (console output)
  -> WatchlistResult (near-pivot potential breakout output)

Python orchestration
  -> apps/python/cli/run_vcp_system.py (market/timeframe/setup scheduler)
      -> apps/python/cli/run_full_us_scan.py (parallel batch runner)
          -> java -cp src Main ...
  -> output/* (CSV, JSON, HTML, summaries)
  -> run_backtest.py --matrix-all (US/India x daily/weekly batch backtest)
```

### Core responsibilities

- `MarketDataProvider`: candle source abstraction
- `VcpDetector`: identifies contraction structure and quality score
- `BreakoutEvaluator`: confirms breakout quality
- `TradePlanner`: converts signal to position sizing and targets
- `ScannerEngine`: orchestration and ranking
- `apps/python/cli/run_full_us_scan.py`: batch scan orchestration, parsing, report generation
- `apps/python/cli/run_vcp_system.py`: daily automation across US/India and daily/weekly runs
- `WatchlistResult`: potential breakout candidate with trade plan + pivot distance

## 3) Current Detection Logic

### Setup detection (multi-variation)

- Evaluates multiple consolidation windows per timeframe:
  - Daily windows include short-term and quarter-like lengths (`Q1/Q2/Q3/Q4`)
  - Weekly windows include few-week and quarter-like lengths (`Q1/Q2/Q3/Q4`)
- Splits base into waves (`waveCount=3`) and checks contraction quality.
- Uses dynamic thresholds by window length:
  - shorter windows require tighter contraction/expansion quality
  - longer windows allow slightly more tolerant thresholds
- Uses dynamic base-height filters by window length:
  - short windows must stay tighter
  - long windows allow wider ranges
- Uses dynamic VCP contraction-count requirements:
  - required contraction pairs are stricter on short windows
  - required contraction pairs are more flexible on long windows
- Captures setup metadata:
  - `setupType` (`VCP` or `RANGE_EXPANSION`)
  - `pivot`, `support`, `qualityScore`
  - `rangeContraction`, `volumeContraction`, `rangeExpansion`
  - `windowLabel`, `windowBars`, `baseRangeHeightPct`, `contractionDepthPct`
  - `rangeContractionCount`, `volumeContractionCount`, `contractionPairs`
  - `setupRating` (`A+` to `D`)

### Breakout confirmation

- Latest close > pivot * (1 + `breakoutBufferPct`)
- Latest volume >= 20-bar avg volume * `breakoutVolumeMultiplier`
- For `RANGE_EXPANSION`: additional expansion and strong-close checks

### Trade plan

- Entry = breakout close
- Stop = support * (1 - `stopBufferPct`)
- Position size from account risk (`accountSize` * `riskPerTradePct`)
- Targets at 1R, 2R, 3R

### Watchlist mode

- Uses same setup detector (`VCP` / `RANGE_EXPANSION`) and quality filters.
- Excludes already-triggered breakouts.
- Keeps symbols within configurable distance to pivot (`watchlistMaxDistanceToPivotPct`).
- Builds a precomputed trade plan using breakout entry above pivot.

## 4) Runtime Defaults and Modes

- Daily mode: `252` bars (~1 year)
- Weekly mode: `104` bars (~2 years)
- Market coverage: US + India
- Setup filter: `both|vcp|range_expansion`

## 5) Output Design

- CSV/JSON for machine consumption
- HTML for human shortlist review
- HTML includes:
  - full trade plan columns
  - setup and window variation
  - height/depth/length/contraction-count/rating fields
  - color rating badges (`A+/A/B/C/D`)
  - price chart links (Yahoo + TradingView)
  - fundamentals link (Yahoo key statistics)
  - descriptive result column names with inline column guide
- Additional outputs now include:
  - `open_trades_*` (confirmed breakouts, execution list)
  - `watchlist_*` (potential near-breakout candidates)
- System-level summary:
  - `output/system_latest_summary.md`
  - `output/system_latest_summary.json`

## 6) Why This Size Is Reasonable

- Small enough to run in one JVM process quickly
- Components are independent and replaceable
- Easy to add real data and persistence without rewriting strategy logic

## 7) Step-by-Step Improvement Plan (Next)

1. **HTML usability upgrades**
   - Add client-side sort/filter/search in report tables
   - Add setup/window quick filters and score slider
   - Add risk-reward column and color tags

2. **Fundamental enrichment**
   - Add links for financials, balance sheet, and cash flow pages
   - Add optional basic fundamentals columns (market cap, sector, PE)

3. **Signal quality controls**
   - Add liquidity floor and spread/price sanity checks
   - Add optional minimum score and minimum expansion gates per setup

4. **Automation hardening**
   - Add scheduled run templates (macOS launchd)
   - Add retention policy for old scan folders

5. **Backtest alignment**
   - Ensure backtest reuses exact same multi-window setup logic
   - Track results by setup type and window variation

6. **Quality and reliability**
   - Unit tests: detector edge cases, position sizing
   - Integration tests: provider -> scanner
   - Logging with INFO/WARN/ERROR levels

7. **Performance scaling**
   - Scan symbols in parallel batches
   - Cache derived indicators per symbol
   - Keep latest N bars only in memory for scanner mode

## 8) How To Execute

Note: root scripts remain as compatibility wrappers, so `python3 run_vcp_system.py` still works.

### One-time

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
javac src/*.java
```

### Daily run (recommended)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh
```

### Explicit full configuration

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --markets us,india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both
```

### India-only triggered scan (variation filters active)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --markets india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both --skip-us-refresh
```

### Verify latest output

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
cat output/system_latest_summary.md
ls -lh output/vcp_hits_*_LATEST.html
```

### Backtest all markets/timeframes (single command)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_backtest.py --matrix-all --setups both
```

Backtest matrix summary outputs:
- `output/backtest_matrix_LATEST.md`
- `output/backtest_matrix_LATEST.html`
- `output/backtest_matrix_LATEST.json`

## 9) Suggested Milestones

- **Milestone 1 (done)**: multi-setup breakout scanner with trade plan and HTML chart links
- **Milestone 2**: interactive HTML analytics + fundamentals enrichment
- **Milestone 3**: deeper risk controls, backtest analytics, and scheduled alerting

## 10) Config Defaults

See `src/AppConfig.java` for all thresholds and risk defaults.
Tune there first before changing detector internals.

