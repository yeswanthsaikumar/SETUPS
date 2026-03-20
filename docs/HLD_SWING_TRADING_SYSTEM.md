# High-Level Design (HLD)
## Breakout Swing Trading System (VCP + Range Expansion)

## 1. Purpose and Scope
This system is a market scanner and decision-support engine for swing trading. It identifies bullish breakout opportunities using VCP and Range Expansion setups across US and India universes, on daily and weekly timeframes.

Primary goals:
- Detect high-quality breakout candidates consistently.
- Produce actionable trade plans (entry, stop, targets, size).
- Generate open-trade and watchlist outputs for execution workflow.
- Backtest strategy behavior over historical windows.

Out of scope (current state):
- Direct broker execution.
- Intraday execution routing.
- Transaction cost/slippage-accurate portfolio simulation.
- Portfolio optimization at account level.

## 2. Business Capabilities
- Universe management for US and India symbols.
- Multi-timeframe scanning (`daily`, `weekly`).
- Multi-setup scanning (`vcp`, `range_expansion`, `both`).
- Risk-plan generation per signal.
- Batch-parallel scan orchestration.
- Report generation (CSV/JSON/HTML interactive views).
- Backtest replay using same core detection stack.

## 3. System Context
External dependencies:
- Yahoo Finance chart API (historical candles).
- Local filesystem for cache and output persistence.

Internal boundaries:
- Python layer (`apps/python/cli/`): orchestration, batching, report assembly.
- Java layer (`src/`): strategy logic, signal detection, trade planning, backtest simulation.

## 4. Architecture Overview

```text
User / Scheduler
  -> run_vcp_system.py (orchestration)
      -> optional fetch_us_stocks.py
      -> javac src/*.java
      -> run_full_us_scan.py (per market/timeframe)
          -> parallel java -cp src Main --mode=scan/watchlist
              -> ScannerEngine
                  -> YahooFinanceProvider (cached candles)
                  -> VcpDetector
                  -> BreakoutEvaluator
                  -> TradePlanner
          -> result parsing + HTML/CSV/JSON generation
      -> system summary generation

Backtesting
  -> run_backtest.py
      -> parallel java -cp src Main --mode=backtest
          -> BacktestEngine (replay + trade simulation)
      -> aggregate metrics + matrix reports
```

## 5. Logical Components
### 5.1 Python Orchestration Layer
- `run_vcp_system.py`
  - Market/timeframe/setup scheduler.
  - Java compile trigger.
  - Full-run summary generation.
- `run_full_us_scan.py`
  - Symbol loading and normalization.
  - Batch splitting and parallel worker execution.
  - Output consolidation into latest snapshots.
  - Interactive HTML generation (filters, sorting, export).
- `run_backtest.py`
  - Batch-parallel historical replay runs.
  - Aggregation of trade-level output and metrics.
  - Interactive HTML performance report.

### 5.2 Java Strategy Layer
- `Main`
  - Entry point for `scan`, `watchlist`, `backtest` modes.
- `CliOptions`
  - Parses runtime params and normalizes setup/timeframe.
- `ScannerEngine`
  - Drives symbol-by-symbol evaluation.
- `VcpDetector`
  - Detects and scores setup candidates (multi-window, dynamic thresholds).
- `BreakoutEvaluator`
  - Confirms breakout/continuation conditions.
- `TradePlanner`
  - Computes stop, risk/share, position size, T1/T2/T3.
- `BacktestEngine`
  - Historical replay, signal-to-exit simulation.

### 5.3 Data and Storage
- Inputs: `data/universes/*.csv`, `*.txt`
- Cache: `cache/<SYMBOL>_<LOOKBACK>.csv`
- Outputs: `output/*LATEST*`, run folders `output/scan_*`, `output/backtest_*`

## 6. Key End-to-End Flows
### 6.1 Daily Production Scan
1. Parse run command and validate arguments.
2. Optionally refresh US symbol universe.
3. Compile Java sources.
4. For each market x timeframe:
   - Load symbols.
   - Execute parallel Java scan batches.
   - Execute parallel watchlist batches.
   - Parse and persist outputs.
5. Build system summary.

### 6.2 Signal Evaluation (per symbol)
1. Load candles from cache or Yahoo.
2. Validate trend and quality prerequisites.
3. Evaluate multi-window setup candidates.
4. Select best-scoring setup.
5. Confirm breakout or near-breakout.
6. Build trade plan.
7. Emit result or reject.

### 6.3 Backtest Replay
1. For each symbol, iterate bars across lookback.
2. Run same detector/evaluator on each index.
3. If signal exists, simulate forward exit path.
4. Track R-multiple, MAE/MFE, target milestones.
5. Aggregate cross-symbol metrics and produce reports.

## 7. Core Design Decisions
- Single detector stack for live scan and backtest to reduce logic drift.
- Local file cache to reduce API latency and external dependency risk.
- Batch-parallel orchestration at Python layer for scale and recoverability.
- Separation of concerns:
  - Detection and scoring in Java.
  - Multi-market automation and reporting in Python.

## 8. Non-Functional Characteristics
- Performance: worker x batch model supports large universes.
- Reliability: retries + cache fallback on data fetch.
- Operability: timestamped outputs and latest aliases simplify daily use.
- Extensibility: setup filter and modular detector/evaluator/planner design.

## 9. Current Constraints and Risks
- No portfolio-level risk budgeting (signals are independent).
- No transaction-cost/slippage model in live recommendations.
- Dependence on Yahoo data quality and symbol mappings.
- No persistent database/history warehouse (filesystem only).
- Limited observability for rejection reasons at symbol level.

## 10. Security and Compliance Notes
- No credentials required for current public data flow.
- No order placement by default (analysis-only system).
- Ensure compliance with local market regulations before automation/execution.

## 11. Target HLD Evolution (Next Stage)
- Add portfolio construction service.
- Add regime filter service (market breadth/volatility trend).
- Add execution adapter (paper + broker abstraction).
- Add experiment framework for parameter variants and A/B runs.
- Add metadata store (SQLite/Postgres) for audit and analytics.

## 12. Success Metrics
- Signal quality: win rate, avg R, profit factor by setup/window.
- Stability: daily run success rate, API/cache failure rates.
- Usability: review-to-decision time from report open to shortlist.
- Risk quality: drawdown and exposure consistency after portfolio layer.

