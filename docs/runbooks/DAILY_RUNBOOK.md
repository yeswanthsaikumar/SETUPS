# Daily Runbook
## SETUPS Full-Mode Operations

## 1) Standard Daily Run (After Market Close)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --setups full --skip-us-refresh
```

This runs:

- markets: US + India
- timeframes: daily + weekly
- setups: VCP + range expansion + mean reversion

## 2) Primary Verification

```bash
cat output/system_latest_summary.md
ls -1 output | grep '_full_LATEST.html'
```

Open key reports:

```bash
open output/vcp_hits_india_daily_full_LATEST.html
open output/watchlist_india_daily_full_LATEST.html
open output/portfolio_shortlist_india_daily_full_LATEST.html
```

## 3) Core Command Matrix

India only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframes daily,weekly \
  --setups full \
  --skip-us-refresh
```

US only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets us \
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

Weekly only:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes weekly \
  --setups full \
  --skip-us-refresh
```

## 4) Setup-Specific Runs

VCP only:

```bash
python3 apps/python/cli/run_vcp_system.py --setups vcp --skip-us-refresh
```

Range expansion only:

```bash
python3 apps/python/cli/run_vcp_system.py --setups range_expansion --skip-us-refresh
```

Mean reversion only:

```bash
python3 apps/python/cli/run_vcp_system.py --setups mean_reversion --skip-us-refresh
```

## 5) Strict Filter Profile (Execution-Ready)

Use direct scanner for tighter control:

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india \
  --timeframe daily \
  --setups full \
  --lookback 252 \
  --min-price-floor 20 \
  --min-avg-volume 200000 \
  --min-avg-dollar-volume 5000000 \
  --regime-mode soft \
  --rs-weight 0.35 \
  --max-portfolio-heat-r 6 \
  --workers 4 \
  --batch 25 \
  --cache-dir cache \
  --output-dir output
```

## 6) Artifacts to Review Daily

- `output/system_latest_summary.md`
- `output/vcp_hits_*_full_LATEST.{csv,json,html}`
- `output/open_trades_*_full_LATEST.{csv,json,html}`
- `output/watchlist_*_full_LATEST.{csv,json,html}`
- `output/portfolio_shortlist_*_full_LATEST.{csv,json,html}`
- `output/rejections_*_LATEST.{csv,json}`
- `output/scan_manifest_*_LATEST.json`

## 7) Troubleshooting Fast Path

If orchestrator fails at Java compile:

1. run direct scanner fallback (`run_full_us_scan.py`) for required market/timeframe
2. check `scan.log`, `events.jsonl`, and `rejections_*`
3. fix Java source compile issue and retry orchestrator

See detailed playbooks in `docs/runbooks/TROUBLESHOOTING.md`.

## 8) End-of-Day Checklist

- run completed with no fatal error
- summary updated in `output/system_latest_summary.md`
- at least one report opened and reviewed
- rejection file checked for unusual spikes
- shortlist reviewed for risk concentration
