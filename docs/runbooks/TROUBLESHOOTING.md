# Troubleshooting Runbook
## SETUPS Scanner and Orchestration

## 1) `run_vcp_system.py` Fails at Java Compile

Symptoms:

- compile stack trace from `javac`
- runtime error before scan groups start

Checks:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
javac src/*.java
```

Recovery:

1. fix Java compile error in affected source file
2. rerun compile command
3. rerun orchestrator

Continuity fallback (while fixing Java):

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

## 2) Zero Hits but Expected Signals

Checks:

- inspect watchlist output (signals may be near pivot, not breakout)
- inspect rejection report for filter pressure
- verify mode and timeframe in summary

Commands:

```bash
cat output/system_latest_summary.md
open output/watchlist_india_daily_full_LATEST.html
head -50 output/rejections_india_daily_LATEST.csv
```

Common causes:

- strict liquidity thresholds
- unfavorable regime mode (`hard`)
- insufficient cache bars for some symbols
- true market conditions with no valid triggers

## 3) Mean Reversion Not Appearing in Full Mode

Checks:

```bash
ls -1 output | grep '_mean_reversion_LATEST.json'
python3 - <<'PY'
import json
from pathlib import Path
p = Path('output/vcp_hits_india_daily_full_LATEST.json')
rows = json.loads(p.read_text()) if p.exists() else []
print('total', len(rows), 'mr', sum(1 for r in rows if str(r.get('setup','')).upper()=='MEAN_REVERSION'))
PY
```

If zero MR repeatedly:

- run `--setups mean_reversion` to isolate MR pipeline
- verify cache availability and lookback depth
- lower MR score threshold via direct scanner (`--mr-min-score`)

## 4) Reports Exist but Look Stale

Checks:

- confirm command finished recently
- compare run folders under `output/scan_*`
- confirm `_LATEST` files updated timestamp

Commands:

```bash
ls -1t output | head -20
stat output/vcp_hits_india_daily_full_LATEST.json
```

## 5) Slow Runtime

Performance controls:

- increase `--workers` cautiously
- tune `--batch`
- use narrower market/timeframe scope
- ensure cache is populated

Example:

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframes daily \
  --setups full \
  --workers 6 \
  --batch 40 \
  --skip-us-refresh
```

## 6) Diagnostic Files to Inspect

Per run folder (`output/scan_*`):

- `scan.log`
- `events.jsonl`
- `batch_log.txt`
- `scan_manifest.json`
- `scan_bundle_*.json`
- `rejections_*.csv`

System-level:

- `output/system_latest_summary.md`
- `output/system_latest_summary.json`

## 7) Escalation Checklist

Before escalating an issue, capture:

- exact command used
- full stderr/traceback
- affected run folder path (`output/scan_*`)
- copies of `scan_manifest.json`, `events.jsonl`, `rejections_*.csv`
- whether issue reproduces with a small symbol subset

