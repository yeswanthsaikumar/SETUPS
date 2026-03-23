# System Design
## SETUPS Swing Trading Engine (VCP + Range Expansion + Mean Reversion)

## 1) Objective

Design a deterministic multi-setup swing scanner that:

- finds high-quality trade opportunities
- converts them to risk-aware trade plans
- exports operationally useful artifacts for execution and review

## 2) Setup Families

### 2.1 VCP

- contraction base with improving structure
- breakout confirmation through pivot + volume + candle quality

### 2.2 Range Expansion

- contraction context followed by expansion breakout candle
- confirms momentum expansion over baseline volatility

### 2.3 Mean Reversion

- pullback in broader uptrend
- reversal/snap-back trigger with risk-defined recovery plan

## 3) Runtime Modes

- `full` (default): VCP + range expansion + mean reversion
- `both`: VCP + range expansion only
- `mean_reversion`: MR only
- `vcp`, `range_expansion`: setup-specific
- `all`: alias of `full`

## 4) End-to-End Runtime Flow

```text
run_vcp_system.py
  -> normalize setups
  -> compile Java (except mean_reversion mode)
  -> run_full_us_scan.py per market/timeframe
      -> Java scan/watchlist batches
      -> Python MR scan (for full/MR)
      -> enrich/filter/rank
      -> save outputs + manifests + logs
  -> system summary
```

## 5) Rule Engine Pipeline

For each symbol/timeframe:

1. Load bars from cache/provider
2. Detect setup candidates
3. Score and rate quality
4. Confirm signal conditions
5. Build trade plan
6. Validate record and apply overlays
7. Rank and shortlist
8. Export results

## 6) Strategy Logic (Formula-Based)

No machine-learning model is used in live setup selection; logic is rule/formula based.

### 6.1 VCP / Range Expansion (Java)

Core modules:

- `VcpDetector`
- `BreakoutEvaluator`
- `TradePlanner`

Typical formulas include:

- range contraction / volume contraction
- ATR-relative expansion checks
- breakout buffer above pivot
- volume vs average-volume thresholding
- candle shape score adjustments

### 6.2 Mean Reversion (Python)

Core module:

- `apps/python/lib/mean_reversion_detector.py`

Signal concept:

- trend context (`close` relative to long MA)
- pullback evidence (RSI / BB / short MA behavior)
- reversal trigger subtype (`BB_BOUNCE`, `MA_RECLAIM`, `OVERSOLD_SNAP`)
- risk plan from ATR and local structure

## 7) Trade Plan Standard

Output fields:

- `entry`
- `sl` (stop-loss)
- `shares`
- `T1`, `T2`, `T3`

General risk shape:

- positive risk required (`entry > sl`)
- `shares` derived from account risk budget
- targets structured in ascending reward sequence

## 8) Overlay Filters and Ranking

Implemented overlays:

1. Rejection diagnostics
2. Liquidity filters
3. Market regime filter (`off|soft|hard`)
4. Relative strength ranking
5. Portfolio heat control

Common ranking features:

- setup quality score
- RS score
- regime support
- watchlist quality decomposition
- heat-aware shortlist selection

## 9) Data Quality and Validation

Validation layers include:

- numeric sanity checks
- trade-plan sanity (`entry`, `sl`, `shares`)
- missing-data and cache-availability checks

Failed records are tracked in `rejections_*` outputs with reason codes.

## 10) Export and Manifest Design

### 10.1 Core exports

- `vcp_hits_*`
- `open_trades_*`
- `watchlist_*`
- `portfolio_shortlist_*`
- `rejections_*`

Each as CSV/JSON and HTML where applicable.

### 10.2 Metadata exports

- `scan_manifest*.json`
- `scan_bundle*.json`
- `events.jsonl`
- `scan.log`

These support reproducibility, observability, and troubleshooting.

## 11) Full-Mode Output Semantics

For `full` mode labels (`*_full_*`):

- combined outputs include all setup types
- additional split latest files are generated per setup:
  - `_vcp_`
  - `_range_expansion_`
  - `_mean_reversion_`

## 12) Operational Design Principles

- deterministic and explainable
- cache-first for stability
- parallelizable by worker/batch
- clear separation between detection and orchestration

## 13) Known Constraints

- Java compile health affects hybrid/full orchestration
- filesystem-only history (no DB by default)
- data provider quality can impact signal availability

## 14) Recommended Extension Path

- add persistent run history store
- add parser contract tests and schema versioning
- add richer portfolio correlation controls
- align web API setup-mode options with CLI modes continuously
