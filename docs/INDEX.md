# Documentation Index

---

## 🚀 Start Here

### Main Entry Points
- **[README.md](README.md)** - Complete system overview, all commands, all output formats, Milestone 2 & 3 features
- **[Quick Start](#quick-start)** (below) - Fastest way to run a scan

---

## Quick Start

### One-Command Scan (Recommended)
```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```
Runs US + India daily/weekly scans, both setup types. Reports open in HTML browser instantly.

### Backtest Latest Trades
```bash
python3 apps/python/cli/run_backtest.py --matrix-all
```
Generates 4 interactive backtests (US/India × Daily/Weekly) with performance metrics, trade logs, and parameter stability maps.

### View Reports
```bash
open output/vcp_hits_us_daily_LATEST.html
open output/backtest_us_daily_LATEST.html
```

---

## 📚 Documentation Structure

### System Architecture & Design
- **[SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md)** ⭐
  - Complete design specification for all features
  - Quality scoring rules and formulas
  - Dynamic thresholds per window size
  - Breakout detection criteria
  - Trade planning mechanics
  - Backtesting simulation model
  - **Start here for understanding the "how"**

- **[HLD_SWING_TRADING_SYSTEM.md](reference/HLD_SWING_TRADING_SYSTEM.md)**
  - High-level architecture overview
  - System context, dependencies, and capabilities
  - Component responsibilities

- **[LLD_SWING_TRADING_SYSTEM.md](reference/LLD_SWING_TRADING_SYSTEM.md)**
  - Low-level implementation details
  - Python/Java module contracts
  - Data flow and I/O specifications

- **[SWING_TRADING_ADVANCED_IMPROVEMENTS.md](reference/SWING_TRADING_ADVANCED_IMPROVEMENTS.md)**
  - Future enhancement roadmap
  - Performance optimization ideas
  - Feature gap analysis

---

### Operational Runbooks
- **[DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)** ⭐
  - Daily workflow after market close
  - Setup-specific and market-specific scan variants
  - Output file checking and cleanup
  - Top-5 overlay configuration
  - Recommended profiles for different trading styles

---

### Feature Guides
- **[STRUCTURED_EXPORTS.md](guides/STRUCTURED_EXPORTS.md)**
  - JSON/CSV export format specification
  - Field definitions for scan hits, watchlist, open trades
  - Machine-readable data for custom analysis

- **[MULTI_TIMEFRAME_ALIGNMENT.md](guides/MULTI_TIMEFRAME_ALIGNMENT.md)**
  - How daily/weekly signals align
  - Confluence patterns and setup quality boost

- **[MTF_QUICK_START.md](guides/MTF_QUICK_START.md)**
  - Multi-timeframe scanning examples
  - When to use MTF scanning

- **[MTF_IMPLEMENTATION_DETAILS.md](guides/MTF_IMPLEMENTATION_DETAILS.md)**
  - Technical details of MTF signal combination

- **[BREAKOUT_QUALITY_FILTERS.md](guides/BREAKOUT_QUALITY_FILTERS.md)**
  - Candle anatomy weighting (wick/body scoring)
  - Quality gates and rejection diagnostics
  - Signal type classification (BREAKOUT vs NEAR_BREAKOUT)

- **[BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)**
  - One-page summary of quality scoring
  - Rating system (A+/A/B/C/D)

- **[BREAKOUT_QUALITY_USAGE_EXAMPLES.md](guides/BREAKOUT_QUALITY_USAGE_EXAMPLES.md)**
  - Real trade examples with scoring breakdown

- **[DATA_QUALITY_CHECKS.md](guides/DATA_QUALITY_CHECKS.md)**
  - Validation rules for symbols, bars, and prices
  - Rejection reason codes
  - How to interpret rejection reports

- **[DATA_QUALITY_QUICK_REF.md](guides/DATA_QUALITY_QUICK_REF.md)**
  - Quick reference for data validation

- **[US_UNIVERSE_REFRESH.md](guides/US_UNIVERSE_REFRESH.md)**
  - How to update the US stock universe
  - Adding new tickers to the scan

---

### Milestone & Feature Documentation
- **[MILESTONE_2.md](archive/MILESTONE_2.md)**
  - Interactive HTML reports with real-time filtering
  - Client-side sorting, searching, exporting
  - Analytics dashboard and distribution charts
  - Fundamentals data enrichment (market cap, PE, sector, yield)
  - Candle anatomy weighting introduction

- **[MILESTONE_2_SUMMARY.md](archive/MILESTONE_2_SUMMARY.md)**
  - Executive summary of M2 features

- **[MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md)** ⭐
  - 2-year historical backtest system
  - Walk-forward fold analysis
  - Monte Carlo robustness simulation
  - Parameter stability maps
  - Trade reasoning hover tooltips
  - Exit model (target cascade, ATR trail, swing-low trail)
  - Performance metrics (win rate, Avg R, max drawdown, profit factor, MAE/MFE)

---

### Additional Resources
- **[2026-03-cleanup/](archive/2026-03-cleanup/)** - Historical implementation snapshots and cleanup notes

---

## 🎯 Suggested Reading Order

### For First-Time Setup
1. [README.md](README.md) - understand what the system does
2. [Quick Start](#quick-start) - run your first scan
3. [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) - daily operations

### For Understanding How It Works
1. [HLD_SWING_TRADING_SYSTEM.md](reference/HLD_SWING_TRADING_SYSTEM.md) - 30-min overview
2. [SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md) - deep dive (1-2 hours)
3. [LLD_SWING_TRADING_SYSTEM.md](reference/LLD_SWING_TRADING_SYSTEM.md) - implementation details

### For Trading Decisions
1. [BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md) - rating system
2. [BREAKOUT_QUALITY_USAGE_EXAMPLES.md](guides/BREAKOUT_QUALITY_USAGE_EXAMPLES.md) - real examples
3. [MULTI_TIMEFRAME_ALIGNMENT.md](guides/MULTI_TIMEFRAME_ALIGNMENT.md) - signal confirmation

### For Performance Analysis
1. [MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md) - backtest system
2. [README.md](README.md) - backtest commands

### For Custom Analysis
1. [STRUCTURED_EXPORTS.md](guides/STRUCTURED_EXPORTS.md) - data format
2. [DATA_QUALITY_CHECKS.md](guides/DATA_QUALITY_CHECKS.md) - validation rules

---

## 📂 Project Structure Map

```
SETUPS/
├── docs/                          # This documentation
│   ├── README.md                  # 👈 Main entry point
│   ├── INDEX.md                   # 👈 You are here
│   ├── reference/
│   │   ├── SYSTEM_DESIGN.md       # Complete spec
│   │   ├── HLD_*.md               # Architecture
│   │   ├── LLD_*.md               # Implementation
│   │   └── SWING_TRADING_*.md     # Roadmap
│   ├── runbooks/
│   │   └── DAILY_RUNBOOK.md       # Daily workflow
│   ├── guides/
│   │   ├── STRUCTURED_EXPORTS.md  # Data formats
│   │   ├── BREAKOUT_QUALITY_*.md  # Signal quality
│   │   ├── MULTI_TIMEFRAME_*.md   # MTF scanning
│   │   ├── DATA_QUALITY_*.md      # Validation
│   │   └── US_UNIVERSE_REFRESH.md # Symbol updates
│   └── archive/
│       ├── MILESTONE_2.md         # Interactive HTML
│       ├── MILESTONE_3_BACKTEST.md # Backtest system
│       └── 2026-03-cleanup/
│
├── apps/python/cli/               # Python entry points
│   ├── run_vcp_system.py          # Daily orchestrator
│   ├── run_full_us_scan.py        # Batch scanner
│   ├── run_backtest.py            # Backtest runner
│   └── fetch_us_stocks.py         # Universe updater
│
├── apps/python/lib/               # Python libraries
│   └── fundamentals_provider.py   # Market data
│
├── src/                           # Java engine
│   ├── Main.java
│   ├── ScannerEngine.java
│   ├── VcpDetector.java
│   ├── BreakoutEvaluator.java
│   ├── TradePlanner.java
│   ├── BacktestEngine.java
│   ├── Indicators.java
│   └── AppConfig.java
│
├── data/universes/                # Symbol lists
│   ├── us_stock_tickers.csv
│   └── indian_stock_tickers.csv
│
├── cache/                         # Market data cache
│   └── <ticker>_<lookback>.csv
│
├── output/                        # Generated reports
│   ├── vcp_hits_*_LATEST.html|csv|json
│   ├── open_trades_*_LATEST.html|csv|json
│   ├── watchlist_*_LATEST.html|csv|json
│   ├── backtest_*_LATEST.html|csv|json
│   ├── portfolio_shortlist_*_LATEST.csv|json
│   ├── rejections_*_LATEST.csv|json
│   ├── system_latest_summary.md|json
│   └── scan_manifest_*_LATEST.json
│
└── scripts/                       # Shell wrappers
    ├── daily_vcp.sh
    ├── full_scan.sh
    └── milestone_2_quickstart.sh
```

---

## 🔗 Key Commands Reference

### Full System Scan
```bash
python3 apps/python/cli/run_vcp_system.py
```

### Specific Market/Timeframe
```bash
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily
python3 apps/python/cli/run_vcp_system.py --markets us --timeframes weekly
```

### Specific Setup Type
```bash
python3 apps/python/cli/run_vcp_system.py --setups vcp
python3 apps/python/cli/run_vcp_system.py --setups range_expansion
```

### Backtest
```bash
python3 apps/python/cli/run_backtest.py --market india --timeframe daily
python3 apps/python/cli/run_backtest.py --matrix-all  # All 4 combinations
```

### With Advanced Overlays
```bash
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

See [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) for more variations.
