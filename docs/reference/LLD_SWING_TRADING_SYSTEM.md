# Low-Level Design (LLD)
## Breakout Swing Trading System (Implementation-Level)

## 1. Runtime Entry Points
### 1.1 Python CLI entrypoints
- `apps/python/cli/run_vcp_system.py`
- `apps/python/cli/run_backtest.py`

### 1.2 Java entry
- `src/Main.java`
  - `--mode=scan`
  - `--mode=watchlist`
  - `--mode=backtest`

## 2. Module Breakdown and Contracts

## 2.1 `apps/python/cli/run_vcp_system.py`
Responsibilities:
- Parse system-run options (`markets`, `timeframes`, `setups`, lookbacks).
- Resolve universe files.
- Compile Java classes.
- Trigger grouped scans via `run_full_us_scan.py`.
- Write consolidated run summary.

Key functions:
- `parse_args()`
- `resolve_us_symbols()`, `resolve_india_symbols()`
- `compile_java()`
- `run_market_timeframe_scan()`
- `write_summary()`

I/O:
- Input: CLI args + universe files.
- Output: latest grouped files + `output/system_latest_summary.*`.

Failure behavior:
- Fails fast on missing symbols/java source.
- Propagates subprocess failure as runtime error.

## 2.2 `apps/python/cli/run_full_us_scan.py`
Responsibilities:
- Load and normalize symbol universe.
- Split symbols into batches.
- Execute parallel Java scan and watchlist processes.
- Parse console-line hits into structured records.
- Write timestamped and LATEST outputs.
- Build interactive HTML report.

Execution model:
- ThreadPoolExecutor with `workers`.
- Each batch invokes Java process with `java -cp src Main ...`.
- Shared lock for synchronized progress logging.

Output contracts:
- `vcp_hits_<market>_<timeframe>[_<setup>]_LATEST.{csv,json,html}`
- `open_trades_<market>_<timeframe>[_<setup>]_LATEST.{csv,json,html}`
- `watchlist_<market>_<timeframe>[_<setup>]_LATEST.{csv,json,html}`

## 2.3 `src/Main.java`
Control flow:
1. Parse `CliOptions`.
2. Create `AppConfig(timeframe)`.
3. Build provider (Yahoo or sample).
4. Build `ScannerEngine`.
5. Route by mode:
   - `scan` -> `runScan`
   - `watchlist` -> `runWatchlist`
   - `backtest` -> `runBacktest`

## 2.4 `src/CliOptions.java`
Key parsing rules:
- Setup normalization: `both`, `vcp`, `range_expansion`.
- Default lookback by timeframe if absent (`weekly` -> 104).
- Symbols from `--symbols=...` CSV list.

## 2.5 `src/ScannerEngine.java`
Core methods:
- `scan(symbols, lookbackBars, timeframe)`
- `scanWatchlist(symbols, lookbackBars, timeframe)`
- `evaluateAtIndex(symbol, candles, idx)`
- `evaluateWatchlistAtIndex(symbol, candles, idx)`

`evaluateAtIndex` logic:
1. Slice candles up to index.
2. `VcpDetector.detect(slice, config, setupFilter)`.
3. Reject if setup null/score below threshold.
4. Confirm breakout or near-breakout via `BreakoutEvaluator`.
5. Build `TradePlan`.
6. Return `ScanResult`.

`evaluateWatchlistAtIndex` logic:
1. Detect setup + quality gates.
2. Reject if already breakout.
3. Check pivot distance in watchlist band.
4. Build precomputed breakout trade plan.
5. Return `WatchlistResult`.

## 2.6 `src/VcpDetector.java`
Pipeline gates:
1. Candle count >= minimum window requirement.
2. Minimum price (`config.minPrice`).
3. Proximity to annual high (`maxDistanceFrom52WkHighPct`).
4. Above moving average requirement (`requireAboveMA`, `maPeriod`).
5. For each configured window:
   - Build waves and contraction stats.
   - ATR non-expansion gate.
   - Compute base geometry, pivot/support.
   - Evaluate VCP candidate.
   - Evaluate Range Expansion candidate.
6. Return best-scoring setup across all windows.

Setup scoring details:
- VCP score uses range/volume contraction blend plus wick-body adjustment.
- Range-expansion score blends contraction and expansion strength with capped multipliers.
- Rating derived from quality + compactness + window bonus.

## 2.7 `src/BreakoutEvaluator.java`
`isBullishBreakout()` requirements:
- Close above pivot + breakout buffer.
- Volume above rolling average x multiplier.
- Intraday high pierces pivot.
- For range expansion setups: ATR-relative expansion + strong close in range.

`isNearBreakoutContinuation()` requirements:
- Close 3%-8% above pivot (configurable).
- Healthy volume.
- Price holds pivot region.
- For range expansion: close-position strength.

## 2.8 `src/TradePlanner.java`
Formula:
- `stop = support * (1 - stopBufferPct)`
- `riskPerShare = entry - stop`
- `shares = floor((accountSize * riskPerTradePct)/riskPerShare)`
- `T1 = entry + 1R`, `T2 = entry + 2R`, `T3 = entry + 3R`

Rejects plan if risk/share <= 0 or shares < 1.

## 2.9 `src/YahooFinanceProvider.java`
Behavior:
- Cache-first read with TTL check.
- If stale/missing: fetch Yahoo chart JSON.
- Parse arrays (`timestamp`, `open`, `high`, `low`, `close`, `volume`).
- Write normalized CSV cache.
- Fallback to stale cache if online fetch fails.

Cache key:
- `<SYMBOL>_<LOOKBACK>.csv`

## 2.10 `apps/python/cli/run_backtest.py` + `src/BacktestEngine.java`
Backtest mechanics:
- Python splits symbols into worker batches.
- Java replay runs at bar index `i` and calls `evaluateAtIndex`.
- On signal, `simulateTrade` walks forward to stop/target/time exit.
- Outputs trade-level data with setup metadata and excursion analytics.

Exit priority:
1. Stop and target same bar -> stop-first (conservative).
2. Stop.
3. T3.
4. T2.
5. T1.
6. Time exit.

## 3. Data Structures
### 3.1 `VcpSetup`
Fields used downstream:
- `setupType`, `pivotPrice`, `supportPrice`, `qualityScore`
- `rangeContraction`, `volumeContraction`, `rangeExpansion`
- `baseWindowBars`, `baseWindowLabel`
- `baseRangeHeightPct`, `contractionDepthPct`
- `setupRating`, contraction counts

### 3.2 `ScanResult`
Core fields:
- `symbol`, `setup`, `signalCandle`, `tradePlan`, `signalType`

### 3.3 `WatchlistResult`
Core fields:
- `symbol`, `setup`, `signalCandle`, `tradePlan`, `distanceToPivotPct`

### 3.4 `BacktestTrade`
Core fields:
- Entry/exit date and price, stop, shares, pnl, R multiple.
- `setupType`, `setupRating`, `windowLabel`, `qualityScore`.
- `mae`, `mfe`, `holdBars`, `hitT1/T2/T3`, `exitReason`.

## 4. Important Configuration Surface (`AppConfig`)
Daily vs Weekly differ for:
- Consolidation windows.
- Min quality score.
- Contraction and expansion thresholds.
- MA period and annual-high lookback.
- Breakout/continuation thresholds.
- Watchlist pivot distance.

High-impact knobs:
- `minQualityScore`
- `breakoutBufferPct`
- `breakoutVolumeMultiplier`
- `nearBreakoutMinAbovePivotPct` / `nearBreakoutMaxAbovePivotPct`
- `watchlistMaxDistanceToPivotPct`
- `riskPerTradePct`

## 5. Sequence Diagrams (Text)
### 5.1 Scan path
1. Python runner calls Java per batch.
2. Java `Main` builds config/engine.
3. Engine loads candles from provider.
4. Detector returns best setup or null.
5. Evaluator confirms breakout/continuation.
6. Planner builds plan.
7. Java prints structured line.
8. Python parses line and persists reports.

### 5.2 Backtest path
1. Python batches symbols and invokes backtest mode.
2. Java replays each symbol across bars.
3. On each signal, simulator evaluates future bars.
4. Trade is materialized with analytics.
5. Python aggregates JSON outputs and computes group metrics.

## 6. Error Handling and Edge Cases
- Missing/invalid symbol files -> Python raises `FileNotFoundError`.
- Empty or broken Yahoo response -> retry, then stale-cache fallback.
- Insufficient candles -> symbol skipped.
- Invalid risk math (negative risk/share) -> trade plan rejected.
- Batch subprocess non-zero -> batch ignored by orchestrator.

## 7. Performance Notes
- Parallelism at process level avoids JVM shared-state complexity.
- Cache reduces repeated API calls and run-to-run latency.
- Scan cost scales with `symbols x windows x timeframes`.
- Backtest cost scales with `symbols x bars x forward-hold`.

## 8. Observability Gaps (Current)
- No per-symbol rejection reason ledger persisted.
- Limited structured logs for detector-stage failures.
- No run metadata database (only file artifacts).

## 9. Recommended LLD Enhancements
1. Add explicit rejection-reason enum and output file per run.
2. Add `scan_manifest.json` with config hash and runtime metadata.
3. Add deterministic run IDs and metrics ingestion hooks.
4. Add contract tests for parser between Java line format and Python parser.
5. Add schema versioning for JSON outputs.

