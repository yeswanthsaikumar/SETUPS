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
| `docs/runbooks/DAILY_RUNBOOK.md` | **Primary** — complete daily workflow, review guide, EOD checklist, all command variants |
| `docs/runbooks/BACKTEST_RUNBOOK.md` | **Backtest guide** — how the 3-year engine works, parameters, interpreting results, macro events |
| `docs/runbooks/TROUBLESHOOTING.md` | Error recovery, diagnostics |
| `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md` | Full-mode deep dive (advanced) |

---

## System Overview

| Doc | Purpose |
|-----|---------|
| `docs/README.md` | Architecture, all commands, output contract, position sizing model |
| `docs/GETTING_STARTED.md` | First-time setup and first run |

---

## Reference (Architecture & Design)

| Doc | Purpose |
|-----|---------|
| `docs/reference/HLD_SWING_TRADING_SYSTEM.md` | High-level component architecture |
| `docs/reference/LLD_SWING_TRADING_SYSTEM.md` | Module contracts and data flow |
| `docs/reference/SYSTEM_DESIGN.md` | Scoring formulas, filtering, ranking logic |
| `docs/reference/SWING_TRADING_ADVANCED_IMPROVEMENTS.md` | Enhancement roadmap |

---

## Feature Guides

| Doc | Purpose |
|-----|---------|
| `docs/guides/BREAKOUT_QUALITY_FILTERS.md` | Quality score components |
| `docs/guides/MULTI_TIMEFRAME_ALIGNMENT.md` | MTF agreement logic |
| `docs/guides/DATA_QUALITY_CHECKS.md` | Cache and bar validation |
| `docs/guides/STRUCTURED_EXPORTS.md` | JSON/CSV export schema |
| `docs/guides/TRADE_PLAN_ASSISTANT.md` | Symbol deep-dive assistant |
| `docs/guides/US_UNIVERSE_REFRESH.md` | US ticker universe management |

---

## Study Lab (Past Winners)

| Doc | Purpose |
|-----|---------|
| `docs/studies/past_winners/README.md` | Hub for studying and saving historical winner patterns |
| `docs/studies/past_winners/WINNER_ENTRY_TEMPLATE.md` | Structured template: pattern, entry/exit, R:R, sizing, context |
| `docs/studies/past_winners/DAILY_REVIEW_LOOP.md` | Daily and weekly process to build pattern memory |
| `trade_data/past_winners/catalog.json` | Persistent winner catalogue data |
| `trade_data/past_winners/glossary.json` | Pattern wisdom glossary and stats |

---

## Scripts Reference

| Script | Command | Time |
|--------|---------|------|
| Full daily run | `./run_master.sh` | ~3–5 min |
| Analysis dashboards | `./run_analysis_dashboards.sh` | ~30 sec |
| Backtest only | `python3 apps/python/cli/generate_backtest_dashboard.py` | ~25 sec |
| Trade plans only | `python3 apps/python/cli/generate_trade_plans_page.py` | ~5 sec |
| Sector analysis only | `python3 apps/python/cli/generate_sector_macro_page.py` | ~10 sec |
| Master report only | `python3 apps/python/cli/generate_master_report.py` | ~20 sec |
| Search symbol | `python3 apps/python/cli/search_symbol.py RELIANCE.NS` | ~2 sec |

---

## Output Files to Monitor Daily

| File | What it is |
|------|------------|
| `output/index.html` | **Hub — open this first** |
| `output/master_report_LATEST.html` | All signals + fundamentals |
| `output/trade_plans_live.html` | Today's signal cards with position sizes |
| `output/backtest_3yr_dashboard.html` | Historical performance + regime context |
| `output/sector_macro_analysis.html` | Sector rotation + macro impact |
| `output/system_latest_summary.md` | Scan run summary |
| `output/rejections_*_LATEST.csv` | Why stocks were filtered out |
