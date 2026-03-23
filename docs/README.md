# SETUPS Trading System

Unified swing-trading scanner for US and India markets with three setup families:

- `VCP` (volatility contraction breakout)
- `RANGE_EXPANSION` (contraction + expansion breakout)
- `MEAN_REVERSION` (pullback snap-back in trend)

The canonical mode is `--setups full`, which runs all three in one pass.

## What This System Produces

- Open trade candidates with trade plan (`entry`, `sl`, `shares`, `T1/T2/T3`)
- Watchlist candidates near pivot
- Portfolio shortlist constrained by portfolio heat
- Rejection diagnostics (validation + liquidity + regime + quality)
- Interactive HTML reports + structured CSV/JSON exports
- Run manifests and event logs for operations and audit

## Runtime Architecture

```text
run_vcp_system.py (orchestrator)
  -> optional universe refresh
  -> javac src/*.java (unless mean_reversion-only mode)
  -> run_full_us_scan.py (per market x timeframe)
       -> Java scan/watchlist for VCP + range expansion
       -> Python mean reversion detector (for full/mean_reversion modes)
  -> output/*LATEST* + system summary
```

## Setup Modes

- `full` (default): VCP + range expansion + mean reversion
- `both`: VCP + range expansion (legacy behavior)
- `vcp`: VCP only
- `range_expansion`: range expansion only
- `mean_reversion`: mean reversion only
- `all`: legacy alias of `full`

## Quick Start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```

Open latest reports:

```bash
open output/vcp_hits_india_daily_full_LATEST.html
open output/vcp_hits_india_weekly_full_LATEST.html
```

## Core Commands

Run full India + US, daily + weekly:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily,weekly \
  --setups full \
  --daily-lookback 252 \
  --weekly-lookback 104 \
  --skip-us-refresh
```

India only, all setups:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframes daily,weekly \
  --setups full \
  --skip-us-refresh
```

Mean reversion only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily,weekly \
  --setups mean_reversion \
  --skip-us-refresh
```

Direct scanner for one market/timeframe:

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india \
  --timeframe daily \
  --setups full \
  --lookback 252 \
  --workers 4 \
  --batch 25 \
  --cache-dir cache \
  --output-dir output
```

## Output Contract (LATEST)

For each `{market}_{timeframe}_{mode}` label (for `full`, suffix is `_full`):

- `vcp_hits_*_LATEST.{csv,json,html}`
- `open_trades_*_LATEST.{csv,json,html}`
- `watchlist_*_LATEST.{csv,json,html}`
- `portfolio_shortlist_*_LATEST.{csv,json,html}`
- `rejections_*_LATEST.{csv,json}`
- `scan_manifest_*_LATEST.json`
- `scan_bundle_*_LATEST.json`

Additional per-setup splits for `full` mode:

- `vcp_hits_{market}_{timeframe}_vcp_LATEST.{csv,json}`
- `vcp_hits_{market}_{timeframe}_range_expansion_LATEST.{csv,json}`
- `vcp_hits_{market}_{timeframe}_mean_reversion_LATEST.{csv,json}`

System-level summary:

- `output/system_latest_summary.md`
- `output/system_latest_summary.json`

## Documentation Map

- `docs/INDEX.md`: master index
- `docs/GETTING_STARTED.md`: onboarding
- `docs/reference/HLD_SWING_TRADING_SYSTEM.md`: high-level design
- `docs/reference/LLD_SWING_TRADING_SYSTEM.md`: low-level design
- `docs/reference/SYSTEM_DESIGN.md`: formulas and decision rules
- `docs/runbooks/DAILY_RUNBOOK.md`: daily operations
- `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md`: full-mode runbook
- `docs/runbooks/TROUBLESHOOTING.md`: troubleshooting guide

## Web and Docker

Web layer is under `apps/web/` and serves generated reports from `output/`.
Use `apps/web/README.md` for API, Docker, and deployment instructions.
