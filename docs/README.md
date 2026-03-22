# Breakout Scanner (VCP + Range Expansion)

Scans US or Indian stocks for breakout entries using either:

- `VCP` (volatility/range contraction base + breakout), or
- `RANGE_EXPANSION` (contraction base followed by expansion breakout), or
- both in one run.

Each hit includes a full trade plan (`entry`, `stop`, `shares`, `T1/T2/T3`).

## Project Structure (Reorganized)

- `apps/python/cli/` - Python runners (`run_vcp_system.py`, `run_full_us_scan.py`, `run_backtest.py`, `fetch_us_stocks.py`)
- `apps/python/lib/` - Python libraries (`fundamentals_provider.py`)
- `data/universes/` - Symbol universe files (`us_stock_tickers.csv`, `indian_stock_tickers.csv`, `all_us_stocks.txt`)
- `scripts/` - Shell entry scripts (`daily_vcp.sh`, `full_scan.sh`, `milestone_2_quickstart.sh`)
- `docs/guides/` - feature guides (MTF, breakout quality, structured exports, data quality)
- `docs/reference/` - architecture/design references (`HLD`, `LLD`, `SYSTEM_DESIGN`)
- `docs/runbooks/` - operational runbooks (`DAILY_RUNBOOK.md`)
- `docs/archive/` - historical implementation snapshots and one-off notes
- `src/` - Java strategy/scanner engine
- `cache/`, `output/` - runtime data and reports

Primary Python entrypoints now live under `apps/python/cli/`, and shell wrappers live under `scripts/`.

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
- Applies top-5 production overlays:
  - symbol-level rejection diagnostics
  - liquidity filters (min average volume / dollar volume)
  - market regime filter (`off|soft|hard`)
  - relative-strength ranking overlays (3M/6M/12M)
  - portfolio heat control with shortlist output
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
  - breakout candle anatomy is now score-weighted:
    - stronger bullish body + lower wicks add positive score
    - larger upper wicks apply negative score
    - this directly affects setup quality and min-score filtering
- Hit output fields now include: `window`, `height%`, `depth%`, `len`, `ctr`, `rating`, full trade plan.
- Breakout detection now has two hit types:
  - `BREAKOUT`: fresh pivot breakout with breakout-buffer and volume confirmation
  - `NEAR_BREAKOUT`: continuation candidates already 3%-8% above pivot with volume support (for late-but-acceptable entries)
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
python3 apps/python/cli/run_vcp_system.py
```

Run explicitly with your requested configuration:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --markets us,india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both
```

Run only VCP setup:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --setups vcp
```

Run only range-expansion setup:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --setups range_expansion
```

Run weekly only (2-year weekly bars):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --timeframes weekly
```

## Output Files

Per group latest outputs:

- `output/vcp_hits_us_daily_LATEST.csv|json|html`
- `output/vcp_hits_us_weekly_LATEST.csv|json|html`
- `output/vcp_hits_india_daily_LATEST.csv|json|html`
- `output/vcp_hits_india_weekly_LATEST.csv|json|html`
- `output/open_trades_<market>_<timeframe>[_<setups>]_LATEST.csv|json|html`
- `output/watchlist_<market>_<timeframe>[_<setups>]_LATEST.csv|json|html`
- `output/portfolio_shortlist_<market>_<timeframe>[_<setups>]_LATEST.csv|json|html`
- `output/rejections_<market>_<timeframe>[_<setups>]_LATEST.csv|json`
- `output/scan_manifest_<market>_<timeframe>[_<setups>]_LATEST.json`
- `output/scan_bundle_<market>_<timeframe>[_<setups>]_LATEST.json`

## Top-5 Overlay Controls

The top-5 upgrade is implemented in `apps/python/cli/run_full_us_scan.py` and is automatically used by `apps/python/cli/run_vcp_system.py`.

Key flags:

- Rejection diagnostics: always on (writes `rejections_*` outputs)
- Liquidity filters: `--min-price-floor`, `--min-avg-volume`, `--min-avg-dollar-volume`, `--liquidity-lookback`
- Regime filter: `--regime-mode off|soft|hard`, `--regime-sample`, `--regime-min-breadth50`, `--regime-min-breadth200`
- Relative strength ranking: `--rs-weight` (uses 3M/6M/12M RS overlays)
- Portfolio heat control: `--max-portfolio-heat-r`, `--account-size`, `--base-risk-pct`

Operational artifacts generated per scan run:

- Structured exports:
  - full CSV/JSON/HTML for hits, watchlist, open trades, portfolio shortlist, rejections
- Manifests:
  - run-level scan manifest (`scan_manifest_*.json`)
  - structured bundle summary (`scan_bundle_*.json`)
- Data validation:
  - invalid/partial rows are rejected with validation reason codes in `rejections_*`
- Better logging:
  - human-readable log: `scan.log`
  - structured event stream: `events.jsonl`
  - per-batch progress log: `batch_log.txt`

Default behavior:

- Regime mode defaults to `soft` (penalty mode, not hard block)
- Liquidity minimums default to `0` (except min price floor)
- Portfolio shortlist is always produced and capped by `--max-portfolio-heat-r` (default `6`)

Recommended stricter profile (manual scan):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/us_stock_tickers.csv \
  --market-label us \
  --timeframe daily \
  --setups both \
  --lookback 252 \
  --min-avg-volume 200000 \
  --min-avg-dollar-volume 5000000 \
  --regime-mode soft \
  --rs-weight 0.35 \
  --max-portfolio-heat-r 6
```

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
python3 apps/python/cli/run_full_us_scan.py --symbols data/universes/us_stock_tickers.csv --market-label us --timeframe daily --setups both --lookback 252
python3 apps/python/cli/run_full_us_scan.py --symbols data/universes/indian_stock_tickers.csv --market-label india --timeframe weekly --setups range_expansion --lookback 104
# Example with advanced overlays enabled
python3 apps/python/cli/run_full_us_scan.py --symbols data/universes/us_stock_tickers.csv --market-label us --timeframe daily --setups both --lookback 252 --min-avg-volume 200000 --min-avg-dollar-volume 5000000 --regime-mode soft --max-portfolio-heat-r 6
```

## Key Files

- `apps/python/cli/run_vcp_system.py` - daily orchestrator for markets/timeframes/setups
- `apps/python/cli/run_full_us_scan.py` - parallel batch scanner and report writer
- `src/VcpDetector.java` - setup detection logic
- `src/BreakoutEvaluator.java` - breakout confirmation logic
- `src/TradePlanner.java` - trade plan builder
- `docs/runbooks/DAILY_RUNBOOK.md` - daily operational steps

## Everyday Run (Recommended)

Use one command after market close:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```

Optional wrapper:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./scripts/daily_vcp.sh --skip-us-refresh
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
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily,weekly --setups both --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
```

Run setup-specific passes (optional):

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily,weekly --setups vcp --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily,weekly --setups range_expansion --daily-lookback 252 --weekly-lookback 104 --skip-us-refresh
```

## Suggested Next Improvements

- Add automated schedule via macOS `launchd` for hands-free daily scans.

---

## 🧪 Milestone 3: 2-Year Historical Backtest (NEW)

Replay every historical bar over the last 2 years and measure how your breakout signals performed.

Backtest now supports advanced robustness tooling:

- realistic execution costs (commission/slippage/fixed cost)
- walk-forward fold analysis
- Monte Carlo equity robustness simulation
- parameter stability maps (lookback x hold-bars grid)
- upgraded exit model for simulation quality:
  - partial profit-taking (25% at T1, 25% at T2, trail remaining)
  - ATR trailing stop once breakout confirms
  - swing-low trailing stop (structure-aware)
  - setup/timeframe-aware time-stop behavior (VCP vs range expansion, daily vs weekly)

### Quick start
```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_backtest.py                          # India daily, 728 bars, 20-bar hold
python3 apps/python/cli/run_backtest.py --timeframe weekly       # India weekly, 104 bars, 8-bar hold
python3 apps/python/cli/run_backtest.py --market us              # US daily
python3 apps/python/cli/run_backtest.py --matrix-all             # US+India on Daily+Weekly, single command
# Realistic cost + robustness example
python3 apps/python/cli/run_backtest.py --market india --timeframe daily --setups both --commission-bps 5 --slippage-bps 5 --fixed-cost 10 --walk-forward-folds 6 --monte-carlo-iterations 2000
# Parameter stability map example
python3 apps/python/cli/run_backtest.py --market india --timeframe daily --stability-lookbacks 504,728,900 --stability-hold-bars 12,16,20,24
```

### What it measures
| Metric | Description |
|---|---|
| Win Rate | % of trades that hit T1 (1R) or better |
| Avg R | Average R-multiple per trade |
| Total R | Cumulative R across all trades |
| Max Drawdown | Peak-to-trough in running R |
| Profit Factor | Gross wins / gross losses |
| Avg MAE / MFE | Adverse / favorable excursion before exit |
| T1 / T2 / T3 Hit Rate | % of trades reaching each target |

### 1:2 / 1:3 Quality Trade Filtering
The HTML report trade table now includes:
- **RR column** — badge `1:2` (T2 hit) or `1:3` (T3 hit) per trade
- **RR filter buttons** — `All`, `1:2+`, `1:3` — click to isolate trades by achieved risk/reward
- **💡 Trade Reasoning column** — hover the icon to see the full trade story: setup rationale, entry, stop, exit date/price, R achieved, and targets hit

The same **💡 Trade Reasoning** hover column is also present in the daily scan hit HTML pages (breakouts/watchlist).

### Output
- `output/backtest_india_daily_LATEST.html` — interactive report (open in browser)
- `output/backtest_india_daily_LATEST.csv` — all trades flat CSV
- `output/backtest_us_daily_LATEST.html` and `output/backtest_us_weekly_LATEST.html`
- `output/backtest_india_weekly_LATEST.html`
- `output/backtest_matrix_LATEST.md|html|json` — combined 4-run summary index
- `output/backtest_<market>_<timeframe>_walk_forward_LATEST.json` — fold-by-fold forward stats
- `output/backtest_<market>_<timeframe>_monte_carlo_LATEST.json` — Monte Carlo percentile and risk stats
- `output/backtest_stability_<market>_<timeframe>_LATEST.md|html|json` — parameter stability map

### UI Result Columns (Updated Naming)
- Scan report now uses descriptive labels like `Base Height %`, `Contraction Depth %`, `Base Length`, `Contraction Pairs`, `Pivot Distance %`, and `Range Expansion x`.
- Backtest report trade table now uses `Trade Setup`, `Setup Rating`, `Setup Window`, `Quality Score`, `Entry Price`, `Exit Price`, `R Multiple`, `Hold Bars`, `MAE (%)`, and `MFE (%)`.

See `docs/MILESTONE_3_BACKTEST.md` for full architecture details.

## Wick/Body Weighted Filtering (Latest)

Setup scoring now includes a candle-structure adjustment on the most recent bars (recency-weighted, breakout bar strongest):

- `bodyDirectionalWeight`: bullish candle body helps, bearish body hurts
- `lowerWickPositiveWeight`: longer lower wick is treated as demand/support (positive)
- `upperWickNegativeWeight`: longer upper wick is treated as rejection/supply (negative)
- `maxWickBodyScoreAdjustment`: caps total wick/body impact to keep scoring stable

These values are defined in `src/AppConfig.java` and are applied in `src/VcpDetector.java` before setup score thresholds are checked.
