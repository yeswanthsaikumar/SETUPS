# Low-Level Design (LLD)
## SETUPS Swing Trading System

## 1. Runtime Entry Points

### Python CLI

- `apps/python/cli/run_vcp_system.py`
- `apps/python/cli/run_full_us_scan.py`
- `apps/python/cli/run_backtest.py`

### Java Entry

- `src/Main.java`
  - `--mode=scan`
  - `--mode=watchlist`
  - `--mode=backtest`

## 2. `run_vcp_system.py` Contract

Responsibilities:

- parse high-level run arguments
- normalize setup mode (`all -> full`)
- resolve symbol files
- compile Java (skip only for `mean_reversion` mode)
- invoke grouped scans using `run_full_us_scan.py`
- build `system_latest_summary.{md,json}`

Key functions:

- `parse_args()`
- `normalize_setup_mode()`
- `compile_java()`
- `run_market_timeframe_scan()`
- `setup_split_counts()`
- `write_summary()`

Key mode behavior:

- default setups: `full`
- accepted setups: `full|both|vcp|range_expansion|mean_reversion|all`
- `all` is normalized to `full`

## 3. `run_full_us_scan.py` Contract

Responsibilities:

- parse market-scan arguments
- normalize setup mode (`all -> full`)
- load and normalize symbols
- execute Java batches for VCP/range modes
- execute Python mean reversion detector for full/MR modes
- perform enrichment, filtering, ranking, heat controls
- write run artifacts + latest aliases

Key functions:

- `parse_args()`
- `normalize_setups_mode()`
- `_java_setups()`
- `_run_mr_scan()`
- `scan_batch()`
- `scan_watchlist_batch()`
- `enrich_and_filter_rows()`
- `rank_watchlist_rows()`
- `apply_portfolio_heat()`

Mode routing logic:

- `mean_reversion` -> no Java scan, Python MR only
- `full` -> Java `both` + Python MR
- `both|vcp|range_expansion` -> Java only

## 4. Mean Reversion Detector Contract

File: `apps/python/lib/mean_reversion_detector.py`

Primary APIs:

- `detect_mean_reversion(...) -> Optional[MeanReversionSignal]`
- `scan_symbols_for_mean_reversion(...) -> list[dict]`

Behavior:

- formula-based (no ML)
- daily/weekly timeframe-aware parameters
- weekly aggregation from cached daily bars when needed
- returns rows aligned to scanner export schema

## 5. Java Core Contract

Main modules:

- `src/ScannerEngine.java`
- `src/VcpDetector.java`
- `src/BreakoutEvaluator.java`
- `src/TradePlanner.java`
- `src/YahooFinanceProvider.java`

Key behavior:

- evaluate candidate windows
- score setup quality and rating
- confirm breakout/continuation
- construct deterministic trade plan

## 6. Output Artifacts

Per run folder (`output/scan_<label>_<timestamp>/`):

- `vcp_hits_*.{csv,json,html}`
- `open_trades_*.{csv,json,html}`
- `watchlist_*.{csv,json,html}`
- `portfolio_shortlist_*.{csv,json,html}`
- `rejections_*.{csv,json}`
- `scan_manifest.json`
- `scan_bundle_*.json`
- `scan.log`
- `events.jsonl`
- `batch_log.txt`

LATEST aliases in `output/` are always refreshed.

For `full` mode, per-setup split latest files are also written:

- `_vcp_`
- `_range_expansion_`
- `_mean_reversion_`

## 7. Data Contracts

Scan row core fields:

- `symbol`, `setup`, `window`, `rating`
- `close`, `pivot`, `entry`, `sl`, `shares`
- `T1`, `T2`, `T3`, `score`
- ranking/enrichment overlays (`rsScore`, `regimeSupport`, `watchlistQualityScore`, etc.)

Rejection row fields:

- `symbol`, `reason`, `source`, `detail`

Manifest highlights:

- run metadata (market, timeframe, setups, lookback, workers)
- filter configuration snapshot
- counts (`hits`, `watchlist`, `shortlist`, `rejections`)
- artifact paths

## 8. Validation and Failure Handling

Validation layers:

- schema/type checks (`validate_rows`)
- trade-plan sanity (`entry > sl`, positive shares)
- liquidity/regime filters

Failure behavior:

- Java process errors surfaced per batch with warnings
- hard failures in orchestration subprocesses bubble to caller
- data-quality and filter rejections retained in `rejections_*`

## 9. Performance Notes

- process-level parallelism: `workers x batch`
- cache-first data retrieval minimizes network IO
- scanner scales roughly with symbols x windows x timeframes

## 10. Known Technical Constraints

- output history is filesystem-based (no DB)
- Java compile required for hybrid/full runs
- web layer and CLI setup-mode support can diverge if not kept in sync
