# SETUPS Trading System

Swing-trading scanner for US and India markets.  
**Single command to run, single HTML file to review.**

## Setup Families

| Setup | Description |
|---|---|
| `VCP` | Volatility contraction breakout |
| `RANGE_EXPANSION` | Contraction + expansion breakout |
| `MEAN_REVERSION` | Pullback snap-back in trend |
| `BREAKOUT_PULLBACK` | First pullback after an initial breakout |

`--setups full` runs all four in one pass (default).

## What the System Produces

- **`output/master_report_LATEST.html`** — single interactive report with all markets, timeframes and setups merged; includes entry price, position size, fundamentals, filters and CSV export
- Per-setup raw files: `vcp_hits`, `watchlist`, `open_trades`, `portfolio_shortlist`, `rejections` in JSON/CSV/HTML

## Architecture

```
run_master.sh
  ├─ run_vcp_system.py            ← orchestrator
  │    ├─ javac src/*.java
  │    └─ run_full_us_scan.py     ← per market × timeframe
  │         ├─ Java: VCP · Range · Breakout Pullback
  │         └─ Python: Mean Reversion
  └─ generate_master_report.py    ← merges + enriches → master HTML
```

## Quick Start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
```

Opens `output/master_report_LATEST.html` in your browser.

## Common Commands

```bash
./run_master.sh                          # India + US, daily + weekly, all setups
./run_master.sh --markets india          # India only
./run_master.sh --markets us             # US only
./run_master.sh --skip-fundamentals      # faster, no yfinance calls
./run_master.sh --account-size 2000000   # ₹20L portfolio
./run_master.sh --setups vcp             # VCP only
```

## Setup Modes

- `full` (default) — all four setups
- `vcp` — VCP only
- `range_expansion` — Range Expansion only
- `mean_reversion` — Mean Reversion only
- `breakout_pullback` — Breakout Pullback only
- `both` — VCP + Range Expansion (legacy)

## Output Files

| File | Description |
|---|---|
| `output/master_report_LATEST.html` | **Primary review file** |
| `output/vcp_hits_*_LATEST.{csv,json,html}` | Breakout signals |
| `output/watchlist_*_LATEST.*` | Near-pivot candidates |
| `output/open_trades_*_LATEST.*` | Active position tracking |
| `output/portfolio_shortlist_*_LATEST.*` | Portfolio heat-constrained shortlist |
| `output/rejections_*_LATEST.{csv,json}` | Filter rejection diagnostics |
| `output/system_latest_summary.md` | Run summary |

## Documentation

- `docs/runbooks/DAILY_RUNBOOK.md` — daily operations and review guide
- `docs/runbooks/TROUBLESHOOTING.md` — diagnostics and recovery
- `docs/INDEX.md` — full doc map
- `docs/reference/SYSTEM_DESIGN.md` — scoring formulas and filter logic
