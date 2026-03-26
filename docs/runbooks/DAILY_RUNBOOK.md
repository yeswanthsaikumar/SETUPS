# Daily Runbook — SETUPS Scanner

## System Overview

```
run_master.sh
  ├─ run_vcp_system.py          ← orchestrator (markets × timeframes)
  │    └─ run_full_us_scan.py   ← per scan (India daily/weekly, US daily/weekly)
  │         ├─ Java  → VCP · Range Expansion · Breakout Pullback
  │         └─ Python → Mean Reversion (on cached OHLCV bars)
  └─ generate_master_report.py
       ├─ merges all *_LATEST.json (BREAKOUT · WATCHLIST · OPEN_TRADE · PORTFOLIO)
       ├─ enriches with fundamentals via yfinance (parallel 20 workers, cached 24 h)
       └─ output/master_report_LATEST.html  ← single daily review file
```

**Setup families:** `VCP` · `RANGE_EXPANSION` · `MEAN_REVERSION` · `BREAKOUT_PULLBACK`  
**List types:** `BREAKOUT` (fresh signal) · `WATCHLIST` (near trigger) · `OPEN_TRADE` (entered) · `PORTFOLIO` (shortlist)

---

## 1. Standard Daily Run

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
```

Runs all 4 scans (India+US × daily+weekly), fetches fundamentals, builds master report, opens it automatically.

**Full explicit form** (same as above):
```bash
source .venv/bin/activate
python3 apps/python/cli/run_vcp_system.py \
  --markets india,us --timeframes daily,weekly \
  --setups full --workers 6 --batch 40 \
  --skip-us-refresh --daily-lookback 252 --weekly-lookback 104 \
  --output-dir output

python3 apps/python/cli/generate_master_report.py \
  --output-dir output --cache-dir cache \
  --account-size 1000000 --risk-pct 0.01

open output/master_report_LATEST.html
```

---

## 2. Common Variants

| Goal | Command |
|---|---|
| Default run | `./run_master.sh` |
| Skip fundamentals (faster) | `./run_master.sh --skip-fundamentals` |
| India only | `./run_master.sh --markets india` |
| US only | `./run_master.sh --markets us` |
| Daily only | `./run_master.sh --timeframes daily` |
| VCP only | `./run_master.sh --setups vcp` |
| Larger portfolio | `./run_master.sh --account-size 2000000` |
| More parallelism | `./run_master.sh --workers 8 --batch 50` |
| Force-refresh US tickers | `./run_master.sh --force-us-refresh` |

---

## 3. Reading the Master Report

Open: `output/master_report_LATEST.html`

**Review order:** `OPEN_TRADE` → `BREAKOUT` → `WATCHLIST`

| Column | What to look for |
|---|---|
| Rating | Focus `A+` / `A` first |
| Rank Score | Higher = better quality + fundamentals |
| Entry / SL | Entry level and stop loss |
| Shares / Pos Value | Pre-sized at your risk% |
| % Gain / Days Held | Performance of open positions |
| Regime | Prefer `STRONG` or `FAVORABLE` |
| Dist Pivot | Closer to 0% = tighter entry |
| Fundamentals | EPS/Rev growth, Debt trend, PE, MCap |

**Available filters:** List Type · Setup · Market · Timeframe · Rating · Sector · Min Score · Symbol  
**CSV export** button for offline analysis.

---

## 4. Output Files

| File | Description |
|---|---|
| `output/master_report_LATEST.html` | **Primary review file** — all markets/setups merged |
| `output/vcp_hits_*_LATEST.json` | Raw hits per market × timeframe |
| `output/open_trades_*_LATEST.json` | Active position tracking |
| `output/watchlist_*_LATEST.json` | Near-trigger watchlist |
| `output/portfolio_shortlist_*_LATEST.csv` | Top picks by portfolio heat |
| `output/breakout_performance_*_LATEST.html` | % gain & days held per open trade |
| `output/rejections_*_LATEST.csv` | Rejection diagnostics |
| `output/system_run_*/summary.md` | Orchestrator run summary |

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| Java compile error | `javac src/*.java` → fix error → rerun |
| Stale US symbols | `./run_master.sh --force-us-refresh` |
| Fundamentals slow | Parallel (20 workers) — ~15 s for 1674 symbols |
| 401 yfinance errors | Rate-limit noise — cached results used; retries next run |
| Scan process killed / timeout | Run step-by-step using explicit commands in §1 |
