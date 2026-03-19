# Breakout Scanner (VCP + Range Expansion)

Scans US or Indian stocks for breakout entries using either:

- `VCP` (volatility/range contraction base + breakout), or
- `RANGE_EXPANSION` (contraction base followed by expansion breakout), or
- both in one run.

Each hit includes a full trade plan (`entry`, `stop`, `shares`, `T1/T2/T3`).

New: each scan now also builds a **watchlist of potential breakouts** near pivot and a separate **open-trades list**.

**🎉 NEW - Milestone 2**: Interactive HTML reports with real-time filtering, sorting, searching, and fundamentals data enrichment!

## What The Latest System Does

- Scans both `us` and `india` universes using Yahoo data + local cache.
- Runs both timeframes with your defaults:
  - Daily: `252` bars (~1 year)
  - Weekly: `104` bars (~2 years)
- Detects both setup families:
  - `VCP` breakout
  - `RANGE_EXPANSION` breakout
- Evaluates multiple window variations per symbol:
  - Daily: short-term + quarter-style windows (`Q1/Q2/Q3/Q4`)
  - Weekly: few-weeks + quarter-style windows (`Q1/Q2/Q3/Q4`)
- Picks the best-scoring valid setup and builds a full trade plan.
- **Milestone 2**: Produces interactive HTML reports with:
  - **Client-side filtering**: Search by symbol, filter by score slider, quick-filter by setup type
  - **Column sorting**: Click any column to sort (numeric or text)
  - **CSV export**: Export currently filtered results as CSV
  - **Analytics dashboard**: Summary stats and distribution charts
  - **Fundamentals data**: Market cap, PE ratio, sector, dividend yield (cached for 24h)
  - Setup/window tags, range height, contraction depth, contraction count, and rating badges
  - Price chart links (Yahoo + TradingView)
  - Fundamentals links (Yahoo statistics, financials, balance sheet, cash flow)

## Latest System Snapshot

- IPO-friendly: short windows and adaptive breakout volume lookback allow newer listings to be scanned.
- Dynamic filtering is active per window length:
  - range base height caps vary by short/long windows
  - VCP contraction depth thresholds vary by window length
  - VCP contraction count requirement varies by window (`Ctr` pairs)
  - range-expansion thresholds vary by window length
- Hit output fields now include: `window`, `height%`, `depth%`, `len`, `ctr`, `rating`, full trade plan.
- Outputs now include three list types per scan run:
  - breakout hits (confirmed)
  - open trades (same as confirmed hits, saved separately for execution tracking)
  - watchlist candidates (near-pivot setups not yet broken out)

## Defaults You Asked For

- **Daily scans:** last ~1 year (`252` bars)
- **Weekly scans:** last ~2 years (`104` bars)

## ✨ Milestone 2: Interactive Features (NEW!)

### Dashboard Analytics
See summary statistics immediately:
- Total hits count
- Average quality score
- Average risk/reward ratio

### Distribution Charts
- **Rating Distribution**: Visual breakdown of A+/A/B/C/D ratings
- **Setup Distribution**: VCP vs Range Expansion split

### Real-Time Filtering
- **Search Box**: Find symbols or setup types instantly
- **Score Slider**: Filter by quality score (0-100)
- **Setup Buttons**: Quick filter by VCP or Range Expansion
- **Row Counter**: Shows "Showing X of Y rows" as you filter

### Column Sorting
- Click any table header to sort
- Numeric columns sort by value
- Text columns sort alphabetically
- Visual indicator (↑/↓) shows sort direction

### Export Filtered Results
- "📥 Export Filtered" button downloads visible rows as CSV
- Preserves your current filter selections
- One-click download via browser

### Fundamentals Data (Cached)
- Market cap in billions
- P/E ratio (trailing and forward)
- Sector and industry
- Dividend yield percentage
- 24-hour cache to minimize API calls

---
- Works for `us` and `india` universes
- Setup filter via `--setups=both|vcp|range_expansion`

## Main Commands

Run full system (US + India, Daily + Weekly, both setups):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py
```

Run explicitly with your requested configuration:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --markets us,india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both
```

Run only VCP setup:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --setups vcp
```

Run only range-expansion setup:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --setups range_expansion
```

Run weekly only (2-year weekly bars):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --timeframes weekly
```

## Output Files

Per group latest outputs:

- `output/vcp_hits_us_daily_LATEST.csv|json|html`
- `output/vcp_hits_us_weekly_LATEST.csv|json|html`
- `output/vcp_hits_india_daily_LATEST.csv|json|html`
- `output/vcp_hits_india_weekly_LATEST.csv|json|html`
- `output/open_trades_<market>_<timeframe>[_<setups>]_LATEST.csv|json|html`
- `output/watchlist_<market>_<timeframe>[_<setups>]_LATEST.csv|json|html`

When `--setups both`, split setup lists are also written:

- `output/vcp_hits_<market>_<timeframe>_vcp_LATEST.csv|json`
- `output/vcp_hits_<market>_<timeframe>_range_expansion_LATEST.csv|json`

System summary files:

- `output/system_latest_summary.md`
- `output/system_latest_summary.json`

Open latest HTML reports directly:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
open output/vcp_hits_us_daily_LATEST.html
open output/vcp_hits_us_weekly_LATEST.html
open output/vcp_hits_india_daily_LATEST.html
open output/vcp_hits_india_weekly_LATEST.html
open output/open_trades_india_daily_LATEST.html
open output/watchlist_india_daily_LATEST.html
```

## Direct Scanner Usage

Single Java run:

```bash
javac src/*.java
java -cp src Main --mode=scan --provider=yahoo --timeframe=daily --setups=both --symbols=AAPL,MSFT --lookback=252 --cache-dir=cache --cache-ttl-min=360
```

Python batch run for one universe:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_full_us_scan.py --symbols us_stock_tickers.csv --market-label us --timeframe daily --setups both --lookback 252
python3 run_full_us_scan.py --symbols indian_stock_tickers.csv --market-label india --timeframe weekly --setups range_expansion --lookback 104
```

## Key Files

- `run_vcp_system.py` - daily orchestrator for markets/timeframes/setups
- `run_full_us_scan.py` - parallel batch scanner and report writer
- `src/VcpDetector.java` - setup detection logic
- `src/BreakoutEvaluator.java` - breakout confirmation logic
- `src/TradePlanner.java` - trade plan builder
- `DAILY_RUNBOOK.md` - daily operational steps

## Everyday Run (Recommended)

Use one command after market close:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --skip-us-refresh
```

Optional wrapper:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./daily_vcp.sh --skip-us-refresh
```

Quick verification:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
cat output/system_latest_summary.md
ls -lh output/vcp_hits_*_LATEST.csv
```

## India Triggered Scan (Daily + Weekly, Variation Filters Active)

Run India only with both setups and all dynamic window/depth/height/contraction variations:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --markets india --timeframes daily,weekly --setups both --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
```

Run setup-specific passes (optional):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 run_vcp_system.py --markets india --timeframes daily,weekly --setups vcp --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
python3 run_vcp_system.py --markets india --timeframes daily,weekly --setups range_expansion --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
```

## Suggested Next Improvements

- Add sortable/filterable HTML tables (by setup, score, window, risk/reward).
- Add extra fundamentals links (financials, balance sheet, cash flow).
- Add a small daily quality gate in summary (for example: min score + min liquidity).
- Add automated schedule via macOS `launchd` for hands-free daily scans.

