# Documentation Index — SETUPS Scanner

## Two Commands Per Day

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS

# Step 1 — Daily scan (~3–5 min)
./run_master.sh

# Step 2 — Analysis dashboards (~30 sec)
./run_analysis_dashboards.sh

# Or combined
./run_master.sh && ./run_analysis_dashboards.sh
```

Opens `output/index.html` — the hub linking all 4 HTML dashboards.

---

## Runbooks (Day-to-Day Operations)

| Doc | Purpose |
|-----|---------|
| `runbooks/DAILY_RUNBOOK.md` | **Primary** — complete daily workflow, review guide, EOD checklist |
| `runbooks/BACKTEST_RUNBOOK.md` | **Backtest guide** — 3-year engine, parameters, interpreting results |
| `runbooks/TROUBLESHOOTING.md` | Error recovery, diagnostics |
| `runbooks/UNIFIED_FULL_MODE_RUNBOOK.md` | Full-mode deep dive (advanced) |
| `runbooks/WEB_APP_RUNBOOK.md` | Web dashboard setup and usage |
| `runbooks/SYSTEM_INTERNALS_TUNING_REPORT.md` | Internal tuning params |

---

## System Overview

| Doc | Purpose |
|-----|---------|
| `README.md` | Architecture, all commands, output contract, position sizing model |
| `GETTING_STARTED.md` | First-time setup and first run |

---

## Reference (Architecture & Design)

| Doc | Purpose |
|-----|---------|
| `reference/SYSTEM_DESIGN.md` | Scoring formulas, filtering, ranking logic, component architecture |

---

## Feature Guides

| Doc | Purpose |
|-----|---------|
| `guides/BREAKOUT_QUALITY.md` | Breakout quality score — 4 dimensions, scoring, usage |
| `guides/MULTI_TIMEFRAME.md` | Multi-timeframe alignment logic |
| `guides/DATA_QUALITY.md` | Cache and bar validation checks |
| `guides/STRUCTURED_EXPORTS.md` | JSON/CSV export schema |
| `guides/TRADE_PLAN_ASSISTANT.md` | Symbol deep-dive assistant |
| `guides/US_UNIVERSE_REFRESH.md` | US ticker universe management |

---

## Domain Knowledge

| Doc | Purpose |
|-----|---------|
| `TRADING_PLAYBOOK.md` | Swing trading playbook — market phases, trail rules |
| `TRADING_PLAYBOOK_EVIDENCE.md` | Statistical evidence for playbook rules |
| `BULL_FLAG_DETECTION.md` | Bull flag pattern detection logic |
| `FOLLOWTHROUGH_DETECTION.md` | Follow-through day detection |
| `TRADE_FILTERING_LOGIC.md` | Trade filtering rules explained |
| `WATCHLIST_PATTERN_LAB.md` | Watchlist pattern engine guide |

---

## Scripts Reference

| Script | Command | Time |
|--------|---------|------|
| Full daily run | `./run_master.sh` | ~3–5 min |
| Analysis dashboards | `./run_analysis_dashboards.sh` | ~30 sec |
| Web app | `./run_web.sh` | — |
| Backtest only | `python3 apps/python/cli/run_backtest.py` | ~25 sec |
| Trade plans only | `python3 apps/python/cli/generate_trade_plans_page.py` | ~5 sec |
| Sector analysis only | `python3 apps/python/cli/generate_sector_macro_page.py` | ~10 sec |
| Master report only | `python3 apps/python/cli/generate_master_report.py` | ~20 sec |

---

## Output Files to Monitor Daily

| File | What it is |
|------|------------|
| `output/index.html` | **Hub — open this first** |
| `output/master_report_LATEST.html` | All signals + fundamentals |
| `output/trade_plans_live.html` | Today's signal cards with position sizes |
| `output/sector_macro_analysis.html` | Sector rotation + macro impact |
| `output/system_latest_summary.md` | Scan run summary |

---

## Archive

Old/legacy docs are preserved in `archive/` for reference but are no longer maintained.
