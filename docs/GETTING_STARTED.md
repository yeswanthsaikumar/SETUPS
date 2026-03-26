# Getting Started

## One Command to Run Everything

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./run_master.sh
```

This runs India + US, daily + weekly, all four setups (VCP · Range Expansion · Mean Reversion · Breakout Pullback), enriches results with fundamentals, and opens the master HTML report automatically.

---

## What You Get

`output/master_report_LATEST.html` — a single interactive report with:
- All signals across markets and timeframes in one table
- Entry price and pre-calculated position size (at 1% risk)
- Fundamentals (EPS, Revenue, Debt, Sector via yfinance)
- Filters by list type, setup, market, rating, sector, score
- CSV export button

---

## Verify Outputs

```bash
ls -1t output | head -15
open output/master_report_LATEST.html
cat output/system_latest_summary.md
```

---

## Scope Variants

```bash
./run_master.sh --markets india          # India only
./run_master.sh --timeframes daily       # daily only
./run_master.sh --setups vcp             # VCP only
./run_master.sh --skip-fundamentals      # faster run
./run_master.sh --account-size 2000000   # ₹20L portfolio
```

---

## If the Run Fails at Java Compile

Run the direct scanner as a fallback:

```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india --timeframe daily \
  --setups full --lookback 252 \
  --workers 4 --batch 25 \
  --cache-dir cache --output-dir output
```

Then generate the report manually:

```bash
python3 apps/python/cli/generate_master_report.py \
  --output-dir output --cache-dir cache
```

Fix the Java source, recompile with `javac src/*.java`, then rerun `./run_master.sh`.

---

## Next Steps

- Daily workflow → `docs/runbooks/DAILY_RUNBOOK.md`
- Troubleshooting → `docs/runbooks/TROUBLESHOOTING.md`
- System design → `docs/reference/SYSTEM_DESIGN.md`
