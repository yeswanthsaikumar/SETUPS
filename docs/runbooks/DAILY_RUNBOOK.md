# Daily Breakout Runbook (US + India)

**Last Updated:** March 22, 2026  
**Status:** ✅ Production Ready

---

## Default Daily Workflow

Run once after market close:

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```

This runs:

- US daily (1-year bars, 252)
- US weekly (2-year bars, 104)
- India daily (1-year bars, 252)
- India weekly (2-year bars, 104)
- Setup mode: `both` (`VCP` + `RANGE_EXPANSION`)

**Output:** Interactive HTML reports in `output/` directory + CSV/JSON exports.

---

## Quick Output Verification

```bash
# Check latest summary
cat output/system_latest_summary.md

# List all latest files
ls -lh output/*_LATEST.* | head -20

# Open reports in browser
open output/vcp_hits_us_daily_LATEST.html
open output/vcp_hits_india_daily_LATEST.html
open output/vcp_hits_us_weekly_LATEST.html
open output/vcp_hits_india_weekly_LATEST.html

# View open trades (same as confirmed hits, separate file)
open output/open_trades_india_daily_LATEST.html

# View watchlist (pre-breakout candidates)
open output/watchlist_india_daily_LATEST.html

# View portfolio heat shortlist (top 6 by heat)
open output/portfolio_shortlist_india_daily_LATEST.html
```

---

## Market-Specific Scans

### US Only (Both Timeframes)
```bash
python3 apps/python/cli/run_vcp_system.py --markets us --skip-us-refresh
```

### India Only (Both Timeframes)
```bash
python3 apps/python/cli/run_vcp_system.py --markets india --skip-us-refresh
```

### US Daily Only
```bash
python3 apps/python/cli/run_vcp_system.py --markets us --timeframes daily --skip-us-refresh
```

### India Weekly Only
```bash
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes weekly --skip-us-refresh
```

---

## Setup-Specific Scans

### VCP Only (All Markets & Timeframes)
```bash
python3 apps/python/cli/run_vcp_system.py --setups vcp --skip-us-refresh
```

### Range Expansion Only
```bash
python3 apps/python/cli/run_vcp_system.py --setups range_expansion --skip-us-refresh
```

### VCP Only, India Daily
```bash
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily --setups vcp --skip-us-refresh
```

### Range Expansion, US Weekly
```bash
python3 apps/python/cli/run_vcp_system.py --markets us --timeframes weekly --setups range_expansion --skip-us-refresh
```

---

## Backtest Recent Performance

### Single Market/Timeframe Backtest
```bash
# India daily, 728 bars (3 years), 20-bar hold
python3 apps/python/cli/run_backtest.py

# US daily
python3 apps/python/cli/run_backtest.py --market us

# US weekly
python3 apps/python/cli/run_backtest.py --market us --timeframe weekly

# India weekly
python3 apps/python/cli/run_backtest.py --market india --timeframe weekly
```

### Full Matrix (All 4 Combinations)
```bash
# US + India × Daily + Weekly in one command
python3 apps/python/cli/run_backtest.py --matrix-all
```

### Backtest With Realistic Costs
```bash
# Commission 5 bps, slippage 5 bps, fixed cost $10 per trade
python3 apps/python/cli/run_backtest.py \
  --market india \
  --timeframe daily \
  --setups both \
  --commission-bps 5 \
  --slippage-bps 5 \
  --fixed-cost 10
```

### Advanced Robustness Analysis
```bash
# Walk-forward fold analysis (6 folds, sliding window)
python3 apps/python/cli/run_backtest.py \
  --market india \
  --timeframe daily \
  --walk-forward-folds 6

# Monte Carlo simulation (2000 iterations)
python3 apps/python/cli/run_backtest.py \
  --market india \
  --timeframe daily \
  --monte-carlo-iterations 2000

# Parameter stability map (test lookback × hold-bars grid)
python3 apps/python/cli/run_backtest.py \
  --market india \
  --timeframe daily \
  --stability-lookbacks 504,728,900 \
  --stability-hold-bars 12,16,20,24

# All robustness tools combined
python3 apps/python/cli/run_backtest.py \
  --market india \
  --timeframe daily \
  --commission-bps 5 \
  --slippage-bps 5 \
  --fixed-cost 10 \
  --walk-forward-folds 6 \
  --monte-carlo-iterations 2000
```

### View Backtest Results
```bash
open output/backtest_india_daily_LATEST.html
open output/backtest_us_daily_LATEST.html
open output/backtest_india_weekly_LATEST.html
open output/backtest_us_weekly_LATEST.html
open output/backtest_matrix_LATEST.html
```

---

## Top-5 Overlay Configuration

The top-5 overlays are always active in the scan engine but can be tuned per run.

### Standard Overlays (Active By Default)

1. **Rejection Diagnostics** - Always on, writes `rejections_*_LATEST.csv|json`
2. **Liquidity Filters** - Rejects low-volume/low-dollar-volume symbols
3. **Market Regime Filter** - Soft penalty (not hard block) by default
4. **Relative Strength Ranking** - 3M/6M/12M RS overlays
5. **Portfolio Heat Control** - Shortlist capped to top 6 by heat

### Overlay Flags for Direct Scanning

```bash
# Liquidity thresholds
--min-price-floor 5.0              # Min stock price
--min-avg-volume 100000            # Min average volume (shares)
--min-avg-dollar-volume 5000000    # Min dollar volume
--liquidity-lookback 20            # Lookback window for averages

# Market regime
--regime-mode soft|hard|off        # soft=penalty, hard=block, off=disabled
--regime-sample 63                 # Sample window (bars)
--regime-min-breadth50 0.50        # Min breadth above 50-MA
--regime-min-breadth200 0.30       # Min breadth above 200-MA

# Relative strength
--rs-weight 0.35                   # RS rank weight (0-1)

# Portfolio heat
--max-portfolio-heat-r 6           # Max shortlist size
--account-size 100000              # Account size for heat calc
--base-risk-pct 1.0                # Base risk % per trade
```

---

## Recommended Scanning Profiles

### Profile 1: Quick Daily Check (Default)
```bash
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```
- No filtering restrictions
- Fast execution
- Ideal for opportunistic checking
- ~5-10 min for full 4-run (US/India × daily/weekly)

### Profile 2: Strict Daily Scan (Conservative Filter)
```bash
python3 apps/python/cli/run_vcp_system.py \
  --skip-us-refresh \
  --min-avg-volume 200000 \
  --min-avg-dollar-volume 5000000 \
  --regime-mode soft \
  --rs-weight 0.35 \
  --max-portfolio-heat-r 6
```
- High liquidity requirement
- Market regime penalty active
- Strong relative strength weighting
- Top 6 portfolio heat control
- Ideal for execution-ready lists

### Profile 3: Single Market Detailed Scan (India Daily)
```bash
python3 apps/python/cli/run_full_us_scan.py \
  --symbols data/universes/indian_stock_tickers.csv \
  --market-label india \
  --timeframe daily \
  --setups both \
  --lookback 252 \
  --min-avg-volume 100000 \
  --min-avg-dollar-volume 10000000 \
  --regime-mode soft \
  --rs-weight 0.35 \
  --max-portfolio-heat-r 6
```
- Deep dive on one market/timeframe
- Full observability (logs, manifests, events)
- Tunable overlay parameters
- Best for analysis and troubleshooting

### Profile 4: Full Universe Exploration (No Filters)
```bash
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```
- All overlays defaulted (no thresholds)
- Captures all valid setups
- Ideal for research and discovery

---

## Output Files Reference

### Latest Outputs (Always Updated)

```bash
# Breakout hits (confirmed signals)
output/vcp_hits_us_daily_LATEST.html|csv|json
output/vcp_hits_us_weekly_LATEST.html|csv|json
output/vcp_hits_india_daily_LATEST.html|csv|json
output/vcp_hits_india_weekly_LATEST.html|csv|json

# Open trades (same as confirmed hits, separate file for execution tracking)
output/open_trades_us_daily_LATEST.html|csv|json
output/open_trades_us_weekly_LATEST.html|csv|json
output/open_trades_india_daily_LATEST.html|csv|json
output/open_trades_india_weekly_LATEST.html|csv|json

# Watchlist (pre-breakout candidates near pivot)
output/watchlist_us_daily_LATEST.html|csv|json
output/watchlist_us_weekly_LATEST.html|csv|json
output/watchlist_india_daily_LATEST.html|csv|json
output/watchlist_india_weekly_LATEST.html|csv|json

# Portfolio shortlist (top 6 by heat, ready for execution)
output/portfolio_shortlist_us_daily_LATEST.csv|json
output/portfolio_shortlist_us_weekly_LATEST.csv|json
output/portfolio_shortlist_india_daily_LATEST.csv|json
output/portfolio_shortlist_india_weekly_LATEST.csv|json

# Rejections (symbols/bars that failed validation)
output/rejections_us_daily_LATEST.csv|json
output/rejections_us_weekly_LATEST.csv|json
output/rejections_india_daily_LATEST.csv|json
output/rejections_india_weekly_LATEST.csv|json

# System summary (quick status check)
output/system_latest_summary.md
output/system_latest_summary.json

# Scan manifest (metadata per run)
output/scan_manifest_us_daily_LATEST.json
output/scan_manifest_us_weekly_LATEST.json
output/scan_manifest_india_daily_LATEST.json
output/scan_manifest_india_weekly_LATEST.json

# Backtest results
output/backtest_india_daily_LATEST.html|csv|json
output/backtest_us_daily_LATEST.html|csv|json
output/backtest_india_weekly_LATEST.html|csv|json
output/backtest_us_weekly_LATEST.html|csv|json
output/backtest_matrix_LATEST.html|md|json

# Setup split files (when --setups both)
output/vcp_hits_*_vcp_LATEST.csv|json
output/vcp_hits_*_range_expansion_LATEST.csv|json
```

### Timestamped Outputs (Historical Archive)
All outputs also have timestamped versions:
```
output/vcp_hits_india_daily_2026-03-22_14-30-45.csv
output/backtest_india_daily_2026-03-22_14-30-45.json
```

### Per-Run Observability

Inside `output/scan_<timestamp>/`:

```bash
scan.log               # Human-readable event log
events.jsonl           # Structured event stream (one JSON per line)
batch_log.txt          # Per-batch progress details
```

Check recent logs:
```bash
ls -lh output/scan_*/scan.log | tail -5
tail -50 output/scan_*/scan.log | tail -1
```

---

## Monitoring and Troubleshooting

### Quick Status Check

```bash
# Total hits by market/timeframe
echo "=== Breakout Hits ===" && \
wc -l output/vcp_hits_*_LATEST.csv | tail -1

# Total watchlist items
echo "=== Watchlist ===" && \
wc -l output/watchlist_*_LATEST.csv | tail -1

# Total rejections (quality gates)
echo "=== Rejections ===" && \
wc -l output/rejections_*_LATEST.csv | tail -1

# Latest system summary
cat output/system_latest_summary.md
```

### Debugging Failed Runs

```bash
# Check most recent log
tail -100 output/scan_*/scan.log | tail -1

# Check for errors in event stream
grep -i error output/scan_*/events.jsonl | tail -10

# Verify Java compilation
javac src/*.java

# Check symbol file exists
ls -lh data/universes/

# Check cache directory permissions
ls -lh cache/

# Check output directory permissions
ls -lh output/
```

### Performance Diagnostics

```bash
# Count symbols by market
wc -l data/universes/*_stock_tickers.csv

# Check cache size
du -sh cache/

# Check output size
du -sh output/

# Find largest output files
ls -lahS output/*.csv | head -10
```

---

## Maintenance and Cleanup

### Safe Routine Cleanup (Transient Files)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS

# Remove Java class files
find src -name "*.class" -delete

# Remove Python cache
rm -rf __pycache__
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Verify cleanup
ls src/*.class 2>/dev/null || echo "✓ Java classes cleaned"
find . -name "__pycache__" 2>/dev/null | wc -l || echo "✓ Python cache cleaned"
```

### Market Data Cache Management

```bash
# Clear ALL cache (forces full data refetch on next run)
rm -rf cache/*

# Size of cache
du -sh cache/

# List cached symbols
ls cache/ | sort | uniq | wc -l

# Clear cache older than 30 days
find cache -name "*.csv" -mtime +30 -delete
```

### Output Archive (Long-Term Retention)

```bash
# Create timestamped archive
mkdir -p output/archive_$(date +%Y%m%d)
mv output/*.csv output/*.json output/archive_$(date +%Y%m%d)/

# Keep only latest HTML (browser-viewable)
ls -lh output/*_LATEST.html
```

---

## Shell Script Wrappers (Optional)

### Using daily_vcp.sh

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
./scripts/daily_vcp.sh --skip-us-refresh

# Or with custom options
./scripts/daily_vcp.sh --markets india --timeframes daily --setups vcp
```

---

## Advanced Scenarios

### Multi-Run Batch (VCP and Range Expansion Separately)

```bash
# Run VCP only
python3 apps/python/cli/run_vcp_system.py --setups vcp --skip-us-refresh

# Then run Range Expansion only
python3 apps/python/cli/run_vcp_system.py --setups range_expansion --skip-us-refresh

# Compare outputs
diff <(head -5 output/vcp_hits_india_daily_vcp_LATEST.csv) \
     <(head -5 output/vcp_hits_india_daily_range_expansion_LATEST.csv)
```

### Custom Symbol Subset Scan

```bash
# Create test file with 5 symbols
echo "AAPL
MSFT
GOOGL
AMZN
TSLA" > /tmp/test_symbols.txt

# Scan just these symbols
python3 apps/python/cli/run_full_us_scan.py \
  --symbols /tmp/test_symbols.txt \
  --market-label us \
  --timeframe daily \
  --setups both \
  --lookback 252
```

### Historical Comparison (Backtest vs Today's Signals)

```bash
# Run backtest to understand performance over time
python3 apps/python/cli/run_backtest.py --market india --timeframe daily

# Run live scan to see today's signals
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily --skip-us-refresh

# Compare: Historical trades vs today's opportunities
open output/backtest_india_daily_LATEST.html
open output/vcp_hits_india_daily_LATEST.html
```

---

## Operational Cadence (Recommended)

| Time | Action | Command | Output |
|------|--------|---------|--------|
| 16:00 | US Market Close | `python3 apps/python/cli/run_vcp_system.py --markets us --skip-us-refresh` | US daily + weekly hits |
| 19:30 | India Market Close | `python3 apps/python/cli/run_vcp_system.py --markets india --skip-us-refresh` | India daily + weekly hits |
| Post-Market | Portfolio Review | `open output/vcp_hits_*_LATEST.html` | All reports + watchlists |
| Weekly (Sunday) | Backtest & Robustness | `python3 apps/python/cli/run_backtest.py --matrix-all` | 4 backtest reports |
| Monthly | Data Validation | `python3 apps/python/cli/fetch_us_stocks.py` | Updated US ticker universe |

---

## Support and Documentation

- **Full System Documentation**: See [docs/README.md](../README.md)
- **System Design Details**: See [docs/reference/SYSTEM_DESIGN.md](../reference/SYSTEM_DESIGN.md)
- **Backtest Guide**: See [docs/archive/MILESTONE_3_BACKTEST.md](../archive/MILESTONE_3_BACKTEST.md)
- **Setup Quality Reference**: See [docs/guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md](../guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)
- **Data Export Guide**: See [docs/guides/STRUCTURED_EXPORTS.md](../guides/STRUCTURED_EXPORTS.md)
