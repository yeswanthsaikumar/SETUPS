# SETUPS Trading System

Swing-trading scanner + 3-year backtest engine for NSE India and US markets.  
**Two commands per day. Four HTML dashboards. One complete picture.**

---

## Quick Start

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS

# Step 1 — Run daily scan (~3–5 min)
./run_master.sh

# Step 2 — Regenerate analysis dashboards (~30 sec)
./run_analysis_dashboards.sh

# Or run both in sequence
./run_master.sh && ./run_analysis_dashboards.sh
```

Opens `output/index.html` in your browser — the hub linking all dashboards.

---

## Setup Families

| Setup | Description |
|-------|-------------|
| `VCP` | Volatility contraction — price tightens then breaks out on volume |
| `RANGE_EXPANSION` | Wide-range expansion candle clears a consolidation base |
| `MEAN_REVERSION` | Pullback snap-back to SMA20/BB band in an uptrend |
| `BREAKOUT_PULLBACK` | First controlled pullback after an initial breakout |

`--setups full` runs all four in one pass (default).

---

## System Architecture

```
Daily Scan
──────────
run_master.sh
  ├─ run_vcp_system.py              ← orchestrator (India+US × daily+weekly)
  │    └─ run_full_us_scan.py       ← per market × timeframe
  │         ├─ Java: VCP · Range Expansion · Breakout Pullback
  │         └─ Python: Mean Reversion
  └─ generate_master_report.py      ← merges signals + fundamentals → HTML

Analysis Dashboards (run after scan)
─────────────────────────────────────
run_analysis_dashboards.sh
  ├─ generate_backtest_dashboard.py  ← 3-yr Python backtest over cache/*.NS_900.csv
  ├─ generate_trade_plans_page.py    ← signal cards with sparklines + position sizing
  └─ generate_sector_macro_page.py   ← sector heatmaps + macro event framework
```

---

## Daily Output Files

### Scan outputs (`./run_master.sh`)

| File | Description |
|------|-------------|
| `output/master_report_LATEST.html` | **Primary review** — all markets/setups, fundamentals |
| `output/vcp_hits_*_LATEST.{csv,json,html}` | Raw breakout signals per market × timeframe |
| `output/watchlist_*_LATEST.*` | Near-pivot candidates |
| `output/open_trades_*_LATEST.*` | Active position tracking with live % gain |
| `output/portfolio_shortlist_*_LATEST.*` | Top picks by portfolio-heat-constrained rank |
| `output/breakout_performance_*_LATEST.html` | % gain & days held per open trade |
| `output/rejections_*_LATEST.{csv,json}` | Filter rejection diagnostics |
| `output/system_latest_summary.md` | Run summary |

### Analysis dashboard outputs (`./run_analysis_dashboards.sh`)

| File | Size | Description |
|------|------|-------------|
| `output/index.html` | 13 KB | **Hub** — links all dashboards |
| `output/backtest_3yr_dashboard.html` | ~3.4 MB | 5-tab backtest: equity curve, trade plans, sector heatmap, macro impact, trade log |
| `output/trade_plans_live.html` | ~936 KB | 222+ signal cards with sparklines, entry/stop/T1/T2/T3, position sizing |
| `output/sector_macro_analysis.html` | ~82 KB | 14-sector quarterly+monthly heatmaps, RS rankings, macro event analysis, fundamentals framework |

---

## Backtest Dashboard — 5 Tabs

| Tab | Content |
|-----|---------|
| 📈 **Performance** | Equity curve, win rate, avg-R, profit factor, max drawdown, monthly R bars, exit type chart, setup breakdown |
| 🎯 **Trade Plans** | All current signals — Entry, Pivot, Stop, T1/T2/T3, Shares, R:R, Regime, RS 3M — filterable |
| 🏘️ **Sector Analysis** | Quarterly/monthly return heatmaps, sector backtest performance table |
| 🌍 **Macro Impact** | 47 events (RBI, Fed, Budget, Elections, Global) each with nearby-trade win rate |
| 📚 **Trade Log** | Top 500 historical trades — entry/exit, R-multiple, T1/T2/T3 hits, MAE/MFE, CSV export |

---

## Position Sizing Model

| Parameter | Default | Override |
|-----------|---------|----------|
| Account size | ₹10,00,000 | `--account-size 2000000` |
| Risk per trade | 1% | hardcoded |
| Stop placement | 10-bar swing low (max 4% from entry) | — |
| T1 (35% exit) | Entry + 1.5 × Risk | — |
| T2 (40% exit) | Entry + 2.5 × Risk | — |
| T3 (25% exit) | Entry + 4.0 × Risk | — |
| Commission | 10 bps round-trip | — |
| Max hold | 20 bars | — |

**Formula:** `Shares = floor(Account × 1%) / (Entry − Stop)`

---

## Common Commands

### Scan variants

```bash
./run_master.sh                           # Default — India + US, all setups
./run_master.sh --markets india           # India only
./run_master.sh --markets us              # US only
./run_master.sh --timeframes daily        # Daily only
./run_master.sh --setups vcp              # VCP only
./run_master.sh --skip-fundamentals       # Faster run, no yfinance
./run_master.sh --account-size 2000000    # ₹20L portfolio sizing
./run_master.sh --force-us-refresh        # Refresh US ticker universe
```

### Dashboard variants

```bash
./run_analysis_dashboards.sh                         # Full run
./run_analysis_dashboards.sh --max-stocks 300        # Quick test
./run_analysis_dashboards.sh --account-size 2000000  # ₹20L sizing
```

### Standalone backtest

```bash
python3 apps/python/cli/generate_backtest_dashboard.py
python3 apps/python/cli/generate_backtest_dashboard.py --max-stocks 500
python3 apps/python/cli/generate_backtest_dashboard.py --account-size 2000000
```

### Individual pages

```bash
python3 apps/python/cli/generate_trade_plans_page.py    # Trade plans only
python3 apps/python/cli/generate_sector_macro_page.py   # Sector analysis only
python3 apps/python/cli/generate_master_report.py       # Master report only
```

### Search a symbol

```bash
python3 apps/python/cli/search_symbol.py RELIANCE.NS
```

---

## Documentation Map

| Doc | Purpose |
|-----|---------|
| `docs/runbooks/DAILY_RUNBOOK.md` | **Primary** — full daily workflow, review guide, EOD checklist |
| `docs/runbooks/BACKTEST_RUNBOOK.md` | Backtest engine guide — how it works, parameters, interpreting results |
| `docs/runbooks/TROUBLESHOOTING.md` | Error recovery, diagnostics |
| `docs/GETTING_STARTED.md` | First-time setup and first run |
| `docs/INDEX.md` | Full documentation map |
