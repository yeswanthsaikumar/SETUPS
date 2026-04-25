# High-Level Design (HLD)
## SETUPS Swing Trading System

## 1. Purpose

Provide a deterministic, operations-friendly swing-trading scan engine that identifies high-quality candidates across:

- `VCP`
- `RANGE_EXPANSION`
- `MEAN_REVERSION`

for US and India markets on daily and weekly timeframes.

## 2. Scope

In scope:

- batch scanning and ranking
- trade-plan generation (`entry`, `sl`, `shares`, `T1/T2/T3`)
- watchlist and shortlist generation
- rejection diagnostics and structured exports
- run manifests and event logs

Out of scope:

- direct broker execution
- account-level optimization and order routing
- real-time intraday strategy execution

## 3. Canonical Operating Mode

`--setups full` is the canonical mode and executes:

- Java detector path for `VCP` + `RANGE_EXPANSION`
- Python detector path for `MEAN_REVERSION`

Legacy alias:

- `--setups all` -> normalized to `full`

## 4. System Context

External dependencies:

- Yahoo Finance historical data
- Local filesystem (`cache/`, `output/`)

Internal layers:

- Python orchestration (`apps/python/cli/`)
- Java core engine (`src/`)
- Python mean reversion library (`apps/python/lib/mean_reversion_detector.py`)

## 5. Architecture View

```text
User / Scheduler
  -> apps/python/cli/run_vcp_system.py
      -> optional universe refresh
      -> Java compile (except mean_reversion-only runs)
      -> apps/python/cli/run_full_us_scan.py (per market x timeframe)
          -> java -cp src Main --mode=scan/watchlist (VCP + range expansion)
          -> Python mean reversion scan (full/mean_reversion)
          -> ranking, filters, portfolio heat control
          -> output artifacts + manifests + logs
      -> output/system_latest_summary.{md,json}
```

## 6. Logical Components

### 6.1 Orchestration and Scheduling

- `run_vcp_system.py`
  - coordinates market/timeframe groups
  - handles setup mode normalization
  - compiles Java for hybrid runs
  - writes system-level summary

- `run_full_us_scan.py`
  - loads symbols, batches work, runs Java workers
  - executes mean reversion detector where applicable
  - enriches/filter/ranks signals
  - writes HTML/CSV/JSON and operational manifests

### 6.2 Detection Engines

- Java (`src/`)
  - `VcpDetector`, `BreakoutEvaluator`, `TradePlanner`, `ScannerEngine`
- Python (`apps/python/lib/mean_reversion_detector.py`)
  - deterministic mean reversion setup detector
  - timeframe-aware daily/weekly bar handling

### 6.3 Data and Persistence

- universe files: `data/universes/`
- cache files: `cache/<SYMBOL>_<LOOKBACK>.csv`
- run outputs: `output/scan_*`
- latest aliases: `output/*_LATEST.*`
- metadata: `scan_manifest_*`, `scan_bundle_*`, `events.jsonl`, `scan.log`

## 7. Primary User Flows

### 7.1 Daily Operations Flow

1. Run `run_vcp_system.py --setups full`
2. For each market x timeframe group:
   - detect candidates
   - apply overlays (liquidity, regime, RS, heat)
   - export final artifacts
3. Review `system_latest_summary.md`
4. Review open trades, watchlist, shortlist

### 7.2 Single-Scope Diagnostic Flow

1. Run `run_full_us_scan.py` for one market/timeframe
2. Inspect run folder (`scan_*`)
3. Use `rejections_*`, `scan_manifest.json`, `events.jsonl` for diagnosis

## 8. Non-Functional Characteristics

- deterministic formulas (no ML in live signal path)
- cache-first operation for repeatability and speed
- process-level parallelism via worker/batch model
- explainable outputs through reason fields and tooltips

## 9. Risks and Constraints

- dependency on data quality from Yahoo + symbol mapping
- compile-time dependency for Java components in hybrid/full mode
- no persistent DB; filesystem-only operational history

## 10. Evolution Direction

- add API/UI parity for full setup mode in web layer where needed
- add persistent run metadata store (SQLite/Postgres)
- add tighter portfolio construction constraints across correlated symbols
- add formal contract tests between Java line format and Python parser
