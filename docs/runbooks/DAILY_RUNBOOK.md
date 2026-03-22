# Daily Breakout Runbook (US + India)

## Default Daily Workflow

Run once after market close:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```

This runs:

- US daily (1-year bars, 252)
- US weekly (2-year bars, 104)
- India daily (1-year bars, 252)
- India weekly (2-year bars, 104)
- Setup mode: `both` (`VCP` + `RANGE_EXPANSION`)

## Setup-Specific Runs

VCP only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh --setups vcp
```

Range expansion only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh --setups range_expansion
```

## Common Variants

US only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh --markets us
```

India only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh --markets india
```

Weekly only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh --timeframes weekly
```

## Top-5 Overlay Operations

Top-5 overlays are active in the scan engine:

- rejection diagnostics
- liquidity filters
- market regime filter
- relative-strength ranking
- portfolio heat shortlist

For strict manual scans (single market/timeframe), run `run_full_us_scan.py` directly with explicit thresholds:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india \
  --timeframe daily \
  --setups both \
  --lookback 252 \
  --min-avg-volume 100000 \
  --min-avg-dollar-volume 10000000 \
  --regime-mode soft \
  --rs-weight 0.35 \
  --max-portfolio-heat-r 6
```

## Outputs To Check

Always-updated latest files:

```bash
ls -lh output/vcp_hits_*_LATEST.csv
cat output/system_latest_summary.md
```

Top-5 specific latest files:

```bash
ls -lh output/portfolio_shortlist_*_LATEST.csv
ls -lh output/rejections_*_LATEST.csv
ls -lh output/scan_manifest_*_LATEST.json
ls -lh output/scan_bundle_*_LATEST.json
```

Per-run observability artifacts (inside each `output/scan_*` folder):

```bash
ls -lh output/scan_*/scan.log | tail -5
ls -lh output/scan_*/events.jsonl | tail -5
ls -lh output/scan_*/batch_log.txt | tail -5
```

If `--setups both`, split lists are also written:

```bash
ls -lh output/*_vcp_LATEST.csv
ls -lh output/*_range_expansion_LATEST.csv
```

## Cleanup (safe routine)

Remove transient build/cache artifacts when needed:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
find src -name "*.class" -delete
rm -rf __pycache__
```

Clear market data cache only if you want a full refetch:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
rm -rf cache/*
```

