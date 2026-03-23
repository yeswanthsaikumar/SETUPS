# Getting Started (Current System)

## Goal

Run your first successful scan using the current unified mode:

- `VCP`
- `RANGE_EXPANSION`
- `MEAN_REVERSION`

in one command (`--setups full`).

## 1) First Run (Recommended)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --setups full --skip-us-refresh
```

What this does:

- runs India + US
- runs daily + weekly
- uses lookbacks: daily `252`, weekly `104`
- writes consolidated outputs to `output/`

## 2) Open Results

```bash
open output/system_latest_summary.md
open output/vcp_hits_india_daily_full_LATEST.html
open output/vcp_hits_india_weekly_full_LATEST.html
```

## 3) Verify Outputs Exist

```bash
ls -1 output | grep 'vcp_hits_.*_full_LATEST.html'
ls -1 output | grep 'watchlist_.*_full_LATEST.html'
ls -1 output | grep 'portfolio_shortlist_.*_full_LATEST.json'
```

## 4) Run a Smaller Scope (Fast Validation)

India only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframes daily,weekly \
  --setups full \
  --skip-us-refresh
```

Daily only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily \
  --setups full \
  --skip-us-refresh
```

## 5) Setup Modes Cheat Sheet

- `full` - VCP + range expansion + mean reversion (default)
- `both` - VCP + range expansion only
- `vcp` - VCP only
- `range_expansion` - range expansion only
- `mean_reversion` - mean reversion only
- `all` - alias of `full`

## 6) If `run_vcp_system.py` Fails at Java Compile

Use direct scanner fallback for execution continuity:

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

## 7) Where to Go Next

- Architecture: `docs/reference/HLD_SWING_TRADING_SYSTEM.md`
- Implementation details: `docs/reference/LLD_SWING_TRADING_SYSTEM.md`
- Strategy formulas: `docs/reference/SYSTEM_DESIGN.md`
- Daily operations: `docs/runbooks/DAILY_RUNBOOK.md`
- Full mode operations: `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md`
- Troubleshooting: `docs/runbooks/TROUBLESHOOTING.md`
