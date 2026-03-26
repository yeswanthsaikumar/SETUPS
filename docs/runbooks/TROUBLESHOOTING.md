# Troubleshooting — SETUPS Scanner

## 1) Java Compile Error

**Symptoms:** stack trace from `javac` before scans start.

```bash
javac src/*.java          # isolate the error
# fix the source file, then:
./run_master.sh
```

**Continuity fallback** (run while fixing Java):

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india --timeframe daily \
  --setups full --lookback 252 \
  --workers 4 --batch 25 --cache-dir cache --output-dir output

python3 apps/python/cli/generate_master_report.py \
  --output-dir output --cache-dir cache
```

---

## 2) Zero or Very Few Hits

**Check the rejection file first:**

```bash
head -50 output/rejections_india_daily_LATEST.csv
cat output/system_latest_summary.md
```

Common causes:

| Cause | Fix |
|---|---|
| Strict liquidity thresholds | Lower `--min-avg-volume` in direct scanner |
| Unfavorable regime mode | Use `--regime-mode soft` |
| Insufficient cache bars | Let cache fill with more historical data |
| True market conditions | Normal — no valid setups today |

---

## 3) Mean Reversion Missing in Full Mode

```bash
# Check if MR hits exist
ls -1 output | grep '_mean_reversion_LATEST.json'

# Count MR in full hit list
python3 - <<'PY'
import json; from pathlib import Path
p = Path('output/vcp_hits_india_daily_full_LATEST.json')
rows = json.loads(p.read_text()) if p.exists() else []
print('total', len(rows), 'MR', sum(1 for r in rows if str(r.get('setup','')).upper()=='MEAN_REVERSION'))
PY
```

If zero MR repeatedly: `./run_master.sh --setups mean_reversion` to isolate MR pipeline.

---

## 4) Stale / Unchanged Report

```bash
ls -1t output | head -10            # check file timestamps
stat output/master_report_LATEST.html
```

If timestamps are old, the previous run may have failed silently. Check `/tmp/scan_progress.log`.

---

## 5) Slow Runtime

```bash
./run_master.sh --workers 8 --batch 50   # more parallelism
./run_master.sh --markets india          # narrow scope
./run_master.sh --timeframes daily       # daily only
./run_master.sh --skip-fundamentals      # skip yfinance calls
```

---

## 6) Diagnostic Files

| File | What to look at |
|---|---|
| `output/system_latest_summary.md` | Run overview, counts per group |
| `output/rejections_*_LATEST.csv` | Which stocks were filtered and why |
| `output/scan_manifest_*_LATEST.json` | Timing and batch stats per group |
| `output/scan_*/events.jsonl` | Event-level run log |
| `output/scan_*/scan.log` | Verbose Java scan log |
| `/tmp/scan_progress.log` | Live progress during `./run_master.sh` |

---

## 7) Escalation Checklist

Before asking for help, capture:

- exact command used
- full stderr / traceback
- `output/system_latest_summary.md`
- `output/rejections_*_LATEST.csv`
- `output/scan_*/scan_manifest.json`
