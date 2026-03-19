# Daily Breakout Runbook (US + India)

## Default Daily Workflow

Run once after market close:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh
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
python3 run_vcp_system.py --skip-us-refresh --setups vcp
```

Range expansion only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh --setups range_expansion
```

## Common Variants

US only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh --markets us
```

India only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh --markets india
```

Weekly only:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh --timeframes weekly
```

## Outputs To Check

Always-updated latest files:

```bash
ls -lh output/vcp_hits_*_LATEST.csv
cat output/system_latest_summary.md
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

