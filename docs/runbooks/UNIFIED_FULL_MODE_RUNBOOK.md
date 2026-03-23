# Unified Full Mode Runbook
## VCP + Range Expansion + Mean Reversion

## Purpose

This runbook standardizes execution for the unified mode:

- setup mode: `full`
- markets: configurable (`india`, `us`)
- timeframes: configurable (`daily`, `weekly`)

## 1) Canonical Production Command

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily,weekly \
  --setups full \
  --daily-lookback 252 \
  --weekly-lookback 104 \
  --skip-us-refresh
```

## 2) India-Only Full Mode

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframes daily,weekly \
  --setups full \
  --daily-lookback 252 \
  --weekly-lookback 104 \
  --skip-us-refresh
```

## 3) Execution Flow (What Happens)

1. setup mode normalization (`all -> full`)
2. Java compile
3. grouped scans (`market x timeframe`) using `run_full_us_scan.py`
4. Java scan/watchlist runs for VCP/range-expansion
5. Python MR scan runs and merges into hit list
6. overlays/ranking/shortlist applied
7. latest aliases and system summary refreshed

## 4) Success Criteria

- no runtime exception from orchestrator
- `output/system_latest_summary.md` updated
- expected `*_full_LATEST.*` files exist
- manifests updated for each group

## 5) Validate Generated Files

```bash
ls -1 output | grep 'vcp_hits_.*_full_LATEST.json'
ls -1 output | grep 'watchlist_.*_full_LATEST.html'
ls -1 output | grep 'portfolio_shortlist_.*_full_LATEST.csv'
ls -1 output | grep 'scan_manifest_.*_full_LATEST.json'
```

## 6) Setup Split Verification (Full Mode)

```bash
ls -1 output | grep '_vcp_LATEST.json'
ls -1 output | grep '_range_expansion_LATEST.json'
ls -1 output | grep '_mean_reversion_LATEST.json'
```

## 7) Quick Metrics Snapshot

```bash
python3 - <<'PY'
import json
from pathlib import Path
out = Path('output')
for tf in ('daily','weekly'):
    p = out / f'vcp_hits_india_{tf}_full_LATEST.json'
    if not p.exists():
        print(tf.upper(), 'missing')
        continue
    rows = json.loads(p.read_text())
    b = {}
    for r in rows:
        k = str(r.get('setup','UNKNOWN')).upper()
        b[k] = b.get(k, 0) + 1
    print(tf.upper(), 'hits=', len(rows), 'setups=', b)
PY
```

## 8) If Orchestrator Compile Fails

Run direct scanner commands per market/timeframe:

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

See `docs/runbooks/TROUBLESHOOTING.md` for root-cause workflows.

