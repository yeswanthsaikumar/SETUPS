# Getting Started

## The Two Daily Commands

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS

# Step 1 — Daily scan (India + US, all setups, ~3–5 min)
./run_master.sh

# Step 2 — Regenerate analysis dashboards (~30 sec)
./run_analysis_dashboards.sh
```

Or run them together in one shot:

```bash
./run_master.sh && ./run_analysis_dashboards.sh
```

---

## What You Get

### Step 1 — `./run_master.sh`

Produces `output/master_report_LATEST.html` — a single interactive report with:
- All signals across India + US, daily + weekly, all 4 setups
- Entry price and pre-calculated position size (at 1% risk)
- Fundamentals — EPS, Revenue, Debt, Sector via yfinance (cached 24 h)
- Filters by list type, setup, market, rating, sector, score
- CSV export button

### Step 2 — `./run_analysis_dashboards.sh`

Produces 4 HTML pages opened from `output/index.html`:

| Page | What you see |
|------|-------------|
| `index.html` | Hub linking all dashboards |
| `backtest_3yr_dashboard.html` | 5-tab dashboard: equity curve, trade plans, sector heatmap, macro impact, trade log |
| `trade_plans_live.html` | All live signals as cards — entry, stop, T1/T2/T3, shares, sparkline |
| `sector_macro_analysis.html` | Sector quarterly/monthly return heatmaps, RS rankings, macro event analysis |

---

## Verify Outputs

```bash
# Check recent output files
ls -1t output | head -15

# Open hub page (all dashboards linked from here)
open output/index.html

# Check scan summary
cat output/system_latest_summary.md
```

---

## Scope Variants

```bash
./run_master.sh --markets india            # India only (faster)
./run_master.sh --timeframes daily         # Daily scans only
./run_master.sh --setups vcp               # VCP only
./run_master.sh --skip-fundamentals        # Fastest run, no yfinance
./run_master.sh --account-size 2000000     # ₹20L portfolio

./run_analysis_dashboards.sh --max-stocks 300       # Quick dashboard test
./run_analysis_dashboards.sh --account-size 2000000 # ₹20L position sizing
```

---

## Running Just the Backtest

```bash
# Full 3-year backtest across all 1,935 India stocks (~25 sec)
python3 apps/python/cli/generate_backtest_dashboard.py

# Quick test on 300 stocks (~3 sec)
python3 apps/python/cli/generate_backtest_dashboard.py --max-stocks 300

# Open result
open output/backtest_3yr_dashboard.html
```

See `docs/runbooks/BACKTEST_RUNBOOK.md` for full details on how the engine works
and how to interpret the results.

---

## Running Individual Pages

```bash
# Regenerate trade plans page only (uses latest scan output, ~5 sec)
python3 apps/python/cli/generate_trade_plans_page.py
open output/trade_plans_live.html

# Regenerate sector + macro page only (~10 sec)
python3 apps/python/cli/generate_sector_macro_page.py
open output/sector_macro_analysis.html

# Regenerate master report only (~20 sec)
python3 apps/python/cli/generate_master_report.py
open output/master_report_LATEST.html
```

---

## If the Scan Fails at Java Compile

Run the Python scanner directly as a fallback:

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india --timeframe daily \
  --setups full --lookback 252 \
  --workers 4 --batch 25 \
  --cache-dir cache --output-dir output
```

Then regenerate the master report manually:

```bash
python3 apps/python/cli/generate_master_report.py \
  --output-dir output --cache-dir cache
```

Fix the Java source, recompile with `javac src/*.java`, then rerun `./run_master.sh`.

---

## Next Steps

- Full daily workflow → `docs/runbooks/DAILY_RUNBOOK.md`
- Backtest guide → `docs/runbooks/BACKTEST_RUNBOOK.md`
- Troubleshooting → `docs/runbooks/TROUBLESHOOTING.md`
- System design → `docs/reference/SYSTEM_DESIGN.md`
