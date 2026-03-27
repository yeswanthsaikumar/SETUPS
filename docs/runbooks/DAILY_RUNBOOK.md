# Daily Runbook — SETUPS Scanner

## System Architecture

```
run_master.sh                              ← Step 1: Daily scan
  ├─ run_vcp_system.py                     ← orchestrator (markets × timeframes)
  │    └─ run_full_us_scan.py              ← per scan (India daily/weekly, US daily/weekly)
  │         ├─ Java  → VCP · Range Expansion · Breakout Pullback
  │         └─ Python → Mean Reversion (on cached OHLCV bars)
  └─ generate_master_report.py             ← merges all signals → master HTML

run_analysis_dashboards.sh                 ← Step 2: Analysis dashboards (after scan)
  ├─ generate_backtest_dashboard.py        ← 3-year backtest + equity curve + macro
  ├─ generate_trade_plans_page.py          ← live signal cards with sparklines
  └─ generate_sector_macro_page.py         ← sector heatmaps + macro framework
```

**Setup families:** `VCP` · `RANGE_EXPANSION` · `MEAN_REVERSION` · `BREAKOUT_PULLBACK`  
**List types:** `BREAKOUT` (fresh) · `WATCHLIST` (near trigger) · `OPEN_TRADE` (entered) · `PORTFOLIO` (shortlist)

---

## Complete Daily Workflow

### Step 1 — Run the Scan (primary)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
```

Runs all 4 scans (India+US × daily+weekly), fetches fundamentals, builds the master report.
Opens `output/master_report_LATEST.html` automatically (~3–5 min).

### Step 2 — Regenerate Analysis Dashboards

```bash
./run_analysis_dashboards.sh
```

Reads the fresh scan outputs and regenerates all 4 HTML analysis pages (~30 sec).
Opens `output/index.html` automatically.

### Combined one-liner (scan + dashboards)

```bash
./run_master.sh && ./run_analysis_dashboards.sh
```

---

## What Gets Generated

### After `./run_master.sh`

| File | Description |
|------|-------------|
| `output/master_report_LATEST.html` | **Primary review** — all markets/setups merged, fundamentals |
| `output/vcp_hits_india_daily_full_LATEST.html` | Daily breakout hits (India) |
| `output/watchlist_india_daily_full_LATEST.html` | Near-pivot watchlist |
| `output/portfolio_shortlist_*_LATEST.html` | Top ranked portfolio picks |
| `output/open_trades_*_LATEST.html` | Active position tracking |
| `output/breakout_performance_*_LATEST.html` | % gain & days held per open trade |
| `output/rejections_*_LATEST.csv` | Filter rejection diagnostics |
| `output/system_latest_summary.md` | Run summary |

### After `./run_analysis_dashboards.sh`

| File | Size | Description |
|------|------|-------------|
| `output/index.html` | 13 KB | **Hub page** — links all dashboards |
| `output/backtest_3yr_dashboard.html` | ~2.5 MB | 3-year backtest (5,243 trades, 5 tabs, structure-based stops) |
| `output/trade_plans_live.html` | ~936 KB | Live signal cards with sparklines |
| `output/sector_macro_analysis.html` | ~82 KB | Sector heatmaps + macro events |

---

## Daily Review Order

Open `output/index.html` → click into each dashboard:

```
1. master_report_LATEST.html     ← check OPEN_TRADE → BREAKOUT → WATCHLIST
2. trade_plans_live.html         ← review today's signals, position sizes
3. backtest_3yr_dashboard.html   ← Performance tab for regime context
4. sector_macro_analysis.html    ← Sector Rotation tab for sector bias
```

### Master Report Review

**Review order:** `OPEN_TRADE` → `BREAKOUT` → `WATCHLIST`

| Column | What to look for |
|--------|------------------|
| Rating | Focus `A+` / `A` first |
| Rank Score | Higher = better quality + fundamentals |
| Entry / SL | Entry level and stop-loss |
| Shares / Pos Value | Pre-sized at your risk% |
| % Gain / Days Held | Performance of open positions |
| Regime | Prefer `STRONG` or `FAVORABLE` |
| Dist Pivot | Closer to 0% = tighter entry |
| Fundamentals | EPS/Rev growth, Debt trend, PE, MCap |

**Available filters:** List Type · Setup · Market · Timeframe · Rating · Sector · Min Score · Symbol  
**CSV export** button for offline analysis.

### Trade Plans Review (trade_plans_live.html)

Each signal card shows:
- **Entry zone** — price to buy above
- **Pivot** — the breakout reference level
- **Stop loss** — exact price, with % below entry
- **T1 / T2 / T3** — targets at +1.5R / +2.5R / +4.0R with estimated ₹ profit
- **Position size** — shares at 1% account risk
- **Sparkline** — 60-bar price history

Filter by **Setup**, **Rating**, or **Sector** using the control bar.  
Export all visible signals as CSV with the ⬇ Export button.

---

## Scope Variants

### Scan Only

```bash
./run_master.sh                           # India + US, daily + weekly, all setups
./run_master.sh --markets india           # India only (faster)
./run_master.sh --markets us              # US only
./run_master.sh --timeframes daily        # Daily only
./run_master.sh --setups vcp              # VCP only
./run_master.sh --skip-fundamentals       # Skip yfinance (fastest, ~1 min)
./run_master.sh --account-size 2000000    # ₹20L portfolio sizing
./run_master.sh --workers 8 --batch 50    # More parallelism
./run_master.sh --force-us-refresh        # Force fresh US ticker download
```

### Dashboards Only (after scan is already done)

```bash
./run_analysis_dashboards.sh                        # Full 2,000-stock backtest (~40 sec)
./run_analysis_dashboards.sh --max-stocks 300       # Quick test run (~4 sec)
./run_analysis_dashboards.sh --account-size 2000000 # ₹20L position sizing
```

### Individual dashboard generators

```bash
# 3-year backtest dashboard only
python3 apps/python/cli/generate_backtest_dashboard.py
python3 apps/python/cli/generate_backtest_dashboard.py --max-stocks 500
python3 apps/python/cli/generate_backtest_dashboard.py --account-size 2000000

# Live trade plans page only (fast — no backtest needed)
python3 apps/python/cli/generate_trade_plans_page.py

# Sector heatmaps + macro analysis only
python3 apps/python/cli/generate_sector_macro_page.py
```

---

## Backtest — Standalone Run

The 3-year backtest engine is separate from the daily scan. It replays
historical breakout detection over **all 1,935 India NSE stocks** using the
**900-bar cache files** (~Apr 2023 – Mar 2026).

```bash
# Full 3-year backtest (all stocks, ~25 sec)
python3 apps/python/cli/generate_backtest_dashboard.py

# Specify custom account size or output path
python3 apps/python/cli/generate_backtest_dashboard.py \
  --account-size 2000000 \
  --output output/backtest_custom.html

# Quick run on a subset (for testing)
python3 apps/python/cli/generate_backtest_dashboard.py --max-stocks 200
```

→ Full backtest guide: `docs/runbooks/BACKTEST_RUNBOOK.md`

---

## End-of-Day Checklist

```
[ ] ./run_master.sh completed successfully
[ ] output/master_report_LATEST.html opens in browser
[ ] ./run_analysis_dashboards.sh completed
[ ] Reviewed OPEN_TRADE positions — any stops triggered?
[ ] Reviewed BREAKOUT list — any A+/A setups to action?
[ ] Checked regime on backtest dashboard — FAVORABLE/UNFAVORABLE?
[ ] Sector rotation tab — which sectors leading this week?
[ ] Noted any macro events due in next 7 days
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Java compile error | `javac src/*.java` → fix error → rerun |
| Stale US symbols | `./run_master.sh --force-us-refresh` |
| Fundamentals slow | 20 parallel workers — ~15 sec for 1,674 symbols; cached 24 h |
| 401 yfinance errors | Rate-limit noise — cached results used; retries next run |
| Scan killed / timeout | Run step-by-step with explicit commands — see §Scope Variants |
| Backtest shows 0 trades | Check `cache/*.NS_900.csv` exist; run `./run_full_scan.sh` first |
| Dashboard HTML too large | Use `--max-stocks 500` to reduce scope |
| Sector heatmap empty | Only 14 mapped sectors shown — unmapped stocks appear as "Other" |
