# System Internals and Tuning Report

This document explains how your SETUPS pipeline filters stocks, generates reports, and produces backtest analytics, with practical tuning guidance for both setup detection and backtest quality.

---

## 1) End-to-End Architecture (What runs, in order)

### Daily production flow

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
./run_analysis_dashboards.sh
```

### Pipeline map

- `run_master.sh`
  - runs `apps/python/cli/run_vcp_system.py`
    - compiles Java (`javac src/*.java`)
    - runs `apps/python/cli/run_full_us_scan.py` for each market/timeframe slice
  - runs `apps/python/cli/generate_master_report.py`
- `run_analysis_dashboards.sh`
  - runs `apps/python/cli/generate_backtest_dashboard.py`
  - runs `apps/python/cli/generate_trade_plans_page.py`
  - runs `apps/python/cli/generate_sector_macro_page.py`

### Setup families and list types

- Setup families: `VCP`, `RANGE_EXPANSION`, `MEAN_REVERSION`, `BREAKOUT_PULLBACK`
- List types: `BREAKOUT`, `WATCHLIST`, `OPEN_TRADE`, `PORTFOLIO`

---

## 2) How Stocks Are Filtered (Internals)

Filtering is layered. A stock must survive each layer to appear in final outputs.

### 2.1 Universe and symbol normalization

Source is loaded by `run_full_us_scan.py` from universe files (India/US), then normalized:
- invalid symbols removed
- non-common listings filtered
- exchange suffixes handled (`.NS`, `.BO`)

### 2.2 Technical detection layer (Java core)

Core engine chain:
- `src/ScannerEngine.java`
- `src/VcpDetector.java`
- `src/BreakoutEvaluator.java`
- `src/TradePlanner.java`

#### A) Pre-setup gates

Applied before setup scoring:
- minimum price gate (`AppConfig.minPrice`)
- 52-week high proximity gate (`maxDistanceFrom52WkHighPct`)
- MA trend gate (`requireAboveMA`, `maPeriod`)
- data sufficiency gate

#### B) Setup detection and scoring

`VcpDetector` tries multiple windows and keeps best candidate:
- VCP scoring: contraction structure + volume behavior
- Range expansion scoring: breakout range/volume expansion + structure
- Mean reversion scoring: pullback depth/recovery/volume/structure

Key controls are in `src/AppConfig.java`:
- `consolidationWindows`
- `minQualityScore`
- contraction thresholds
- expansion thresholds

#### C) Breakout/continuation validation

`BreakoutEvaluator` enforces:
- close above pivot + breakout buffer
- intraday pivot break confirmation
- volume multiplier confirmation
- additional range/close-in-range checks for range expansion

#### D) Entry anti-chase and plan construction

`ScannerEngine` blocks over-extended breakouts using `maxBreakoutEntryDistancePct`.

`TradePlanner` then creates plan:
- entry
- breakout-anchored stop for triggered breakouts (breakout candle low)
- support-based stop for non-triggered contexts
- position size (`shares`) from account risk

If plan invalid (`entry <= stop`, no shares), symbol is rejected.

### 2.3 Post-technical filtering and ranking (Python layer)

In `run_full_us_scan.py`, technically valid rows are further filtered/enriched:

- liquidity checks:
  - min average volume
  - min average dollar volume
- regime gating:
  - `off`, `soft`, `hard` regime modes
- relative strength scoring (3m/6m/12m vs benchmark sample)
- watchlist quality ranking (pivot proximity, regime support, weekly agreement, dry-up, freshness)
- portfolio heat constraint (`max_portfolio_heat_r`)

Rejected names are written to `rejections_*_LATEST.csv/json` with reason codes.

### 2.4 Fundamentals and trigger enrichment (after technical filters)

After rows pass technical/system filters, fundamentals are fetched from cache/provider:
- provider: `apps/python/lib/fundamentals_provider.py`
- integration: `run_full_us_scan.py`

Populated fields include:
- `fundSummary`
- `triggerEarningsGrowth`
- `triggerDebtReduction`
- `triggerMacroTailwind`
- `triggerMarketTailwind`
- `triggerSummary`

This means fundamentals do not decide technical signal existence; they enrich and prioritize already-valid technical candidates.

---

## 3) How Reports Are Generated

### 3.1 Scan report set (per market/timeframe)

From `run_full_us_scan.py`:
- `vcp_hits_*_LATEST.csv/json/html`
- `watchlist_*_LATEST.csv/json/html`
- `open_trades_*_LATEST.csv/json/html`
- `portfolio_shortlist_*_LATEST.csv/json/html`
- `rejections_*_LATEST.csv/json`
- `scan_manifest_*_LATEST.json`
- `scan_bundle_*_LATEST.json`

### 3.2 Master merged report

`generate_master_report.py` reads all `*_LATEST.json` and builds:
- `output/master_report_LATEST.html`
- recomputed position sizing (`account_size`, `risk_pct`)
- fundamentals overlay and list-type merged filtering

### 3.3 Dashboard set

`run_analysis_dashboards.sh` regenerates:
- `output/backtest_3yr_dashboard.html`
- `output/trade_plans_live.html`
- `output/sector_macro_analysis.html`
- `output/index.html`

---

## 4) Backtest Internals (How results are produced)

Backtest stack:
- Java simulation: `src/BacktestEngine.java`
- exported trade model: `src/BacktestTrade.java`
- export writer: `src/ResultExporter.java`
- Python presenter: `apps/python/cli/run_backtest.py`

### 4.1 Signal replay model

- backtest iterates historical bars
- evaluates scanner logic at each bar
- simulates trade from entry bar forward
- records trade metrics and context

### 4.2 Exit and stop model (structure-first)

Current simulation exits on structure breaks, not arbitrary TP liquidation:
- initial stop from breakout structure (breakout candle low + volatility buffer)
- trailing stop from highest-high structure for winners
- EMA10-based dynamic structure in strong regime context
- explicit exit reason tags (`STRUCTURE_BREAK_*`)

### 4.3 Recorded trade analytics

Backtest exports include core + context fields:
- performance: `rMultiple`, `pnl`, `mae`, `mfe`, `holdBars`
- hit flags: `hitT1`, `hitT2`, `hitT3`
- benchmark context: `benchmarkReturnPct`, `alphaPct`, `marketStrengthScore`
- intelligence: `rewardToRiskT1`, `positionRiskAmount`, `positionNotional`, `pivotPrice`, `pivotDistancePct`, `entryMarketRegime`, `relativeStrengthScore`, `macroTrigger`, `structureStopModel`

### 4.4 Backtest Trade Intelligence UI

`run_backtest.py` now includes compact intelligence in HTML:
- regime distribution
- RS leadership distribution
- macro-trigger mix
- table filters for `Regime`, `RS`, and `Macro Trigger`

This helps explain why trades moved, not just whether they won.

---

## 5) Fine-Tuning Guide (What to tune, where, and expected effect)

### 5.1 Setup detection quality tuning

File: `src/AppConfig.java`

Most impactful knobs:
- `minQualityScore`
  - up: fewer, cleaner setups
  - down: more setups, more noise
- `breakoutVolumeMultiplier`
  - up: stronger conviction breakouts only
  - down: earlier/more signals
- `breakoutBufferPct`
  - up: fewer fake pivot touches
  - down: more aggressive entries
- `maxBreakoutEntryDistancePct`
  - lower value reduces chase entries
- watchlist continuation bounds:
  - `nearBreakoutMinAbovePivotPct`
  - `nearBreakoutMaxAbovePivotPct`

### 5.2 Risk and execution realism tuning

Files: `run_backtest.py`, `BacktestEngine.java`, `AppConfig.java`

- Costs in backtest (`run_backtest.py`):
  - `--commission-bps`
  - `--slippage-bps`
  - `--fixed-cost`
- Structure stop/trail behavior (`AppConfig`):
  - volatility buffers (`structureStopBuffer*`)
  - trailing percentages (`structureTrailPct*`)
  - `emaTrailBufferPct`
  - `strongTrendMarketScoreThreshold`

### 5.3 Ranking and selection tuning

File: `apps/python/cli/run_full_us_scan.py`

- ranking weights (`WATCHLIST_RANK_WEIGHTS`)
- RS impact (`--rs-weight`)
- heat capping (`--max-portfolio-heat-r`)
- regime strictness (`--regime-mode` soft/hard)

### 5.4 Fundamentals trigger strictness

File: `apps/python/cli/run_full_us_scan.py`

Trigger threshold logic is centralized in:
- `_earnings_trigger_from_fundamentals(...)`
- `_debt_trigger_from_fundamentals(...)`

Tune these thresholds to make trigger labels more conservative or aggressive.

---

## 6) Practical Tuning Workflow (recommended)

1) Freeze a baseline snapshot.
2) Change only one cluster of knobs at a time.
3) Re-run full scan + dashboards.
4) Compare:
   - hit count quality (`A+/A` ratio)
   - watchlist-to-open-trade conversion quality
   - backtest alpha / max drawdown / regime robustness

### Baseline run

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh && ./run_analysis_dashboards.sh
```

### Controlled variations

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh --markets india --timeframes daily --setups full --skip-fundamentals
./run_analysis_dashboards.sh --max-stocks 500
```

### Backtest sensitivity (faster matrix style)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_backtest.py --market india --timeframe daily --stability-lookbacks 504,728,900 --stability-hold-bars 12,16,20,24
```

---

## 7) Internal Diagnostics You Should Watch Daily

- `rejections_*_LATEST.csv`
  - tells you exactly where symbols fail (quality, pivot distance, liquidity, regime)
- `scan_manifest_*_LATEST.json`
  - confirms parameters and counts used for each run
- `system_latest_summary.md`
  - high-level totals across slices
- `master_report_LATEST.html`
  - operational list review (`OPEN_TRADE` -> `BREAKOUT` -> `WATCHLIST`)
- `backtest_3yr_dashboard.html`
  - regime-aware performance and movement reason context

---

## 8) Suggested Next Fine-Tuning Priorities

1. Increase signal precision first:
   - slightly raise `minQualityScore`
   - slightly tighten `maxBreakoutEntryDistancePct`
2. Improve downside control second:
   - widen high-volatility structure stop buffer modestly
   - tune EMA trail only for strongest regimes
3. Improve ranking quality third:
   - increase RS and regime weight for `PORTFOLIO`
   - keep fundamentals as ranking enhancers, not hard technical gate
4. Re-test in batches (India daily first), then roll to all slices.

---

## 9) Reference Files

- `run_master.sh`
- `run_analysis_dashboards.sh`
- `apps/python/cli/run_vcp_system.py`
- `apps/python/cli/run_full_us_scan.py`
- `apps/python/cli/generate_master_report.py`
- `apps/python/cli/run_backtest.py`
- `src/AppConfig.java`
- `src/ScannerEngine.java`
- `src/VcpDetector.java`
- `src/BreakoutEvaluator.java`
- `src/BacktestEngine.java`
- `src/BacktestTrade.java`
- `src/ResultExporter.java`

