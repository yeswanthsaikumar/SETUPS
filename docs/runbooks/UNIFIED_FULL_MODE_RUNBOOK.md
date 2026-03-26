# Full Mode Runbook

> Most daily operations: see `docs/runbooks/DAILY_RUNBOOK.md`.  
> This doc covers advanced validation and per-setup metrics.

## Canonical Command

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
```

## Execution Flow

1. `run_vcp_system.py` orchestrates 4 scans: India/US × daily/weekly
2. Each scan compiles Java, then calls `run_full_us_scan.py`
3. Java handles VCP · Range Expansion · Breakout Pullback (batched, parallel workers)
4. Python handles Mean Reversion — merged into the same hit list
5. Overlays, ranking, portfolio heat shortlist applied per scan
6. `*_LATEST.*` aliases written; `system_run_*/summary.md` refreshed
7. `generate_master_report.py` merges all outputs + fetches fundamentals (parallel)
8. `output/master_report_LATEST.html` ready

## Validate Generated Files

```bash
ls output | grep 'vcp_hits_.*_LATEST.json'
ls output | grep 'watchlist_.*_LATEST.html'
ls output | grep 'portfolio_shortlist_.*_LATEST.csv'
ls output | grep 'breakout_performance_.*_LATEST.html'
ls output | grep 'master_report_LATEST.html'
```

## Quick Hit Count by Setup

```bash
python3 - <<'PY'
import json
from pathlib import Path
out = Path('output')
for market in ('india', 'us'):
    for tf in ('daily', 'weekly'):
        p = out / f'vcp_hits_{market}_{tf}_full_LATEST.json'
        if not p.exists():
            print(f'{market.upper()} {tf.upper()} — missing'); continue
        rows = json.loads(p.read_text())
        b = {}
        for r in rows:
            k = str(r.get('setup', 'UNKNOWN')).upper()
            b[k] = b.get(k, 0) + 1
        print(f'{market.upper()} {tf.upper()} total={len(rows)} {b}')
PY
```

## Success Criteria

- No fatal exception from orchestrator
- `output/master_report_LATEST.html` present and > 1 MB
- `output/system_run_*/summary.md` updated today
- All four market × timeframe hit JSONs present
