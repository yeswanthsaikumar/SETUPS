# Documentation Index — SETUPS Scanner

## Start Here

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
# opens output/master_report_LATEST.html automatically
```

→ See `docs/runbooks/DAILY_RUNBOOK.md` for the full daily workflow.

---

## Runbooks (Day-to-Day Operations)

| Doc | Purpose |
|---|---|
| `docs/runbooks/DAILY_RUNBOOK.md` | **Primary** — how the system works, daily run, report review, EOD checklist |
| `docs/runbooks/TROUBLESHOOTING.md` | Diagnostics: compile errors, zero hits, MR missing, slow runtime |
| `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md` | Full-mode deep dive (advanced) |

## System Overview

| Doc | Purpose |
|---|---|
| `docs/README.md` | System overview, architecture, commands, output contract |
| `docs/GETTING_STARTED.md` | First-time setup and first run |

## Reference (Architecture & Design)

| Doc | Purpose |
|---|---|
| `docs/reference/HLD_SWING_TRADING_SYSTEM.md` | High-level component architecture |
| `docs/reference/LLD_SWING_TRADING_SYSTEM.md` | Module contracts and data flow |
| `docs/reference/SYSTEM_DESIGN.md` | Scoring formulas, filtering, ranking logic |
| `docs/reference/SWING_TRADING_ADVANCED_IMPROVEMENTS.md` | Enhancement roadmap |

## Feature Guides

| Doc | Purpose |
|---|---|
| `docs/guides/BREAKOUT_QUALITY_FILTERS.md` | Quality score components |
| `docs/guides/MULTI_TIMEFRAME_ALIGNMENT.md` | MTF agreement logic |
| `docs/guides/DATA_QUALITY_CHECKS.md` | Cache and bar validation |
| `docs/guides/STRUCTURED_EXPORTS.md` | JSON/CSV export schema |
| `docs/guides/US_UNIVERSE_REFRESH.md` | US ticker universe management |

---

## Output Files to Monitor Daily

| File | What it is |
|---|---|
| `output/master_report_LATEST.html` | **Primary review — open this** |
| `output/system_latest_summary.md` | Orchestrator run summary |
| `output/rejections_*_LATEST.csv` | Filter rejection diagnostics |
| `output/vcp_hits_*_LATEST.json` | Raw breakout signals |
| `output/open_trades_*_LATEST.json` | Active positions |
