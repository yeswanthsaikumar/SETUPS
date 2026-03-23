# Documentation Index

## Start Here

- `docs/README.md` - system overview and core commands
- `docs/GETTING_STARTED.md` - quickest path to first successful run
- `docs/runbooks/DAILY_RUNBOOK.md` - daily operating sequence

## Quick Start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --setups full --skip-us-refresh
```

Open report:

```bash
open output/vcp_hits_india_daily_full_LATEST.html
```

## Reference Docs (HLD / LLD / Design)

- `docs/reference/HLD_SWING_TRADING_SYSTEM.md`
  - high-level architecture and component boundaries
- `docs/reference/LLD_SWING_TRADING_SYSTEM.md`
  - implementation details, module contracts, data flow
- `docs/reference/SYSTEM_DESIGN.md`
  - strategy formulas, scoring rules, filtering and ranking logic
- `docs/reference/SWING_TRADING_ADVANCED_IMPROVEMENTS.md`
  - enhancement roadmap and advanced ideas

## Runbooks

- `docs/runbooks/DAILY_RUNBOOK.md`
  - standard market-close workflow and checks
- `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md`
  - full mode (`VCP + range expansion + mean reversion`) operations
- `docs/runbooks/TROUBLESHOOTING.md`
  - compile/runtime/output diagnostics and recovery playbooks

## Feature Guides

- `docs/guides/STRUCTURED_EXPORTS.md`
- `docs/guides/BREAKOUT_QUALITY_FILTERS.md`
- `docs/guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md`
- `docs/guides/BREAKOUT_QUALITY_USAGE_EXAMPLES.md`
- `docs/guides/MULTI_TIMEFRAME_ALIGNMENT.md`
- `docs/guides/MTF_QUICK_START.md`
- `docs/guides/MTF_IMPLEMENTATION_DETAILS.md`
- `docs/guides/DATA_QUALITY_CHECKS.md`
- `docs/guides/DATA_QUALITY_QUICK_REF.md`
- `docs/guides/US_UNIVERSE_REFRESH.md`
- `docs/guides/TRADE_PLAN_ASSISTANT.md`

## Operational Artifacts You Should Monitor

- `output/system_latest_summary.md`
- `output/vcp_hits_*_LATEST.{csv,json,html}`
- `output/open_trades_*_LATEST.{csv,json,html}`
- `output/watchlist_*_LATEST.{csv,json,html}`
- `output/portfolio_shortlist_*_LATEST.{csv,json,html}`
- `output/rejections_*_LATEST.{csv,json}`
- `output/scan_manifest_*_LATEST.json`
- `output/scan_bundle_*_LATEST.json`

## Canonical Command Matrix

Full mode, both markets, both timeframes:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily,weekly \
  --setups full \
  --daily-lookback 252 \
  --weekly-lookback 104 \
  --skip-us-refresh
```

India only:

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

Direct single-scan execution:

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india \
  --timeframe weekly \
  --setups full \
  --lookback 104 \
  --workers 4 \
  --batch 25 \
  --cache-dir cache \
  --output-dir output
```
