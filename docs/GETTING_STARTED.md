# 📖 Breakout Scanner - Complete Documentation Guide (March 2026)

**System Version:** Milestone 3 (Interactive HTML Reports + 2-Year Historical Backtest)  
**Last Updated:** March 22, 2026  
**Status:** ✅ Production Ready

---

## 🎯 Quick Start (60 Seconds)

```bash
# Run full scan (US + India, Daily + Weekly)
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh

# View reports in browser
open output/vcp_hits_us_daily_LATEST.html
open output/vcp_hits_india_daily_LATEST.html

# Run backtest (all 4 combinations)
python3 apps/python/cli/run_backtest.py --matrix-all
open output/backtest_matrix_LATEST.html
```

---

## 📚 Documentation by Purpose

### 🚀 **First Time Setup?**
Start here in this order:

1. **[INDEX.md](INDEX.md)** ← You are here! System documentation map
2. **[README.md](README.md)** - System overview (5 min read)
3. **[DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)** → Default Daily Workflow section
4. Run your first scan!

---

### 🔍 **Want to Understand How It Works?**
Deep technical dive (1-2 hours):

1. **[HLD_SWING_TRADING_SYSTEM.md](reference/HLD_SWING_TRADING_SYSTEM.md)** - High-level architecture (30 min)
   - System capabilities and context
   - Component responsibilities
   - Data flow overview

2. **[SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md)** - Complete technical spec (60 min)
   - Quality scoring rules and formulas
   - Dynamic thresholds
   - Breakout detection logic
   - Trade planning mechanics
   - **Single source of truth for all system behavior**

3. **[LLD_SWING_TRADING_SYSTEM.md](reference/LLD_SWING_TRADING_SYSTEM.md)** - Implementation details (30 min)
   - Module contracts
   - Data structures
   - Runtime behavior

---

### 💹 **Running Scans Daily?**
Operational reference:

1. **[DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)** - Your daily playbook
   - Default workflow
   - Market-specific scans
   - Setup-specific scans
   - Output verification
   - Troubleshooting
   - **All commands you need in one place**

2. **[BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)** - Rating system
   - A+/A/B/C/D rating definitions
   - Quality score ranges
   - Signal confidence levels

---

### 📊 **Trading Decisions?**
Signal evaluation and confirmation:

1. **[BREAKOUT_QUALITY_FILTERS.md](guides/BREAKOUT_QUALITY_FILTERS.md)** - Quality scoring
   - Candle anatomy weighting (wick/body)
   - Quality gates
   - Signal types (BREAKOUT vs NEAR_BREAKOUT)

2. **[BREAKOUT_QUALITY_USAGE_EXAMPLES.md](guides/BREAKOUT_QUALITY_USAGE_EXAMPLES.md)** - Real trade examples
   - Setup analysis
   - Score breakdown
   - Trading decisions

3. **[MULTI_TIMEFRAME_ALIGNMENT.md](guides/MULTI_TIMEFRAME_ALIGNMENT.md)** - Multi-timeframe confluence
   - Daily/weekly alignment patterns
   - Confluence scoring
   - Signal confirmation boost

4. **[BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)** - Quick lookup
   - Rating interpretation
   - Confidence levels

---

### 📈 **Backtesting & Performance?**
Historical analysis:

1. **[MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md)** - Complete backtest guide
   - How backtest system works
   - Walk-forward analysis
   - Monte Carlo robustness
   - Parameter stability maps
   - Trade reasoning
   - **All backtest features explained**

2. **[DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)** → Backtest section
   - All backtest commands
   - Realistic cost simulation
   - Robustness analysis

3. **[README.md](README.md)** → Milestone 3 section
   - Backtest quick start
   - Output files

---

### 🔧 **Custom Analysis or Integration?**
Working with exported data:

1. **[STRUCTURED_EXPORTS.md](guides/STRUCTURED_EXPORTS.md)** - Data format specification
   - JSON/CSV structure
   - Field definitions
   - Usage patterns

2. **[DATA_QUALITY_CHECKS.md](guides/DATA_QUALITY_CHECKS.md)** - Validation rules
   - Symbol validation
   - Bar/price validation
   - Rejection reason codes

3. **[DATA_QUALITY_QUICK_REF.md](guides/DATA_QUALITY_QUICK_REF.md)** - Quick reference
   - Rejection codes
   - Interpretation guide

---

### 🌍 **Multi-Timeframe Scanning?**
Daily + Weekly alignment:

1. **[MULTI_TIMEFRAME_ALIGNMENT.md](guides/MULTI_TIMEFRAME_ALIGNMENT.md)** - MTF theory
   - How signals align across timeframes
   - Confluence patterns
   - Quality boost calculation

2. **[MTF_QUICK_START.md](guides/MTF_QUICK_START.md)** - MTF examples
   - When to use MTF scanning
   - Command examples
   - Output interpretation

3. **[MTF_IMPLEMENTATION_DETAILS.md](guides/MTF_IMPLEMENTATION_DETAILS.md)** - Technical details
   - Signal combination algorithms
   - Weight calculations
   - Edge cases

---

### 🎁 **Interactive HTML Features?**
Understanding Milestone 2:

1. **[MILESTONE_2.md](archive/MILESTONE_2.md)** - Complete feature guide
   - Client-side filtering
   - Column sorting
   - Analytics dashboard
   - Distribution charts
   - Export functionality
   - Fundamentals data enrichment

2. **[README.md](README.md)** → Milestone 2 section
   - Feature overview
   - Quick start

---

### 📋 **Symbol Universe Management?**
Updating tickers:

1. **[US_UNIVERSE_REFRESH.md](guides/US_UNIVERSE_REFRESH.md)** - Universe updates
   - How to add new symbols
   - Format requirements
   - Validation rules

---

## 📂 Complete Documentation Map

```
docs/
├── README.md ⭐ MAIN ENTRY POINT
│   └─ System overview, all features, quick commands
│
├── INDEX.md ⭐ YOU ARE HERE
│   └─ Complete documentation index with suggested reading order
│
├── DOCUMENTATION_UPDATE_SUMMARY.md ⭐ NEW
│   └─ Summary of all updates and latest features (this file)
│
├── runbooks/
│   └─ DAILY_RUNBOOK.md ⭐ DAILY OPERATIONS
│      └─ All commands, profiles, monitoring, troubleshooting
│
├── reference/
│   ├─ SYSTEM_DESIGN.md ⭐ TECHNICAL SPEC
│   │  └─ Complete system specification (1000+ lines)
│   ├─ HLD_SWING_TRADING_SYSTEM.md
│   │  └─ High-level architecture and capabilities
│   ├─ LLD_SWING_TRADING_SYSTEM.md
│   │  └─ Low-level implementation details
│   └─ SWING_TRADING_ADVANCED_IMPROVEMENTS.md
│      └─ Roadmap and future enhancements
│
├── guides/
│   ├─ BREAKOUT_QUALITY_FILTERS.md
│   │  └─ Wick/body weighting and quality gates
│   ├─ BREAKOUT_QUALITY_QUICK_REFERENCE.md ⭐ QUICK LOOKUP
│   │  └─ Rating system at a glance
│   ├─ BREAKOUT_QUALITY_USAGE_EXAMPLES.md
│   │  └─ Real trade examples with scoring
│   ├─ MULTI_TIMEFRAME_ALIGNMENT.md
│   │  └─ Daily/weekly confluence and alignment
│   ├─ MTF_QUICK_START.md
│   │  └─ Multi-timeframe scanning examples
│   ├─ MTF_IMPLEMENTATION_DETAILS.md
│   │  └─ MTF signal combination algorithms
│   ├─ DATA_QUALITY_CHECKS.md
│   │  └─ Validation rules and rejection codes
│   ├─ DATA_QUALITY_QUICK_REF.md
│   │  └─ Quick reference for rejection codes
│   ├─ STRUCTURED_EXPORTS.md
│   │  └─ JSON/CSV export format specification
│   └─ US_UNIVERSE_REFRESH.md
│      └─ Symbol universe management
│
└── archive/
    ├─ MILESTONE_2.md
    │  └─ Interactive HTML reports with filters/sorting/analytics
    ├─ MILESTONE_2_SUMMARY.md
    │  └─ Executive summary of M2 features
    ├─ MILESTONE_3_BACKTEST.md ⭐ BACKTEST GUIDE
    │  └─ 2-year backtest with walk-forward and Monte Carlo
    └─ 2026-03-cleanup/
       └─ Historical implementation snapshots
```

---

## 🎯 Finding Information Quickly

### By Task

| Task | Document | Section |
|------|----------|---------|
| **Run daily scan** | DAILY_RUNBOOK.md | Default Daily Workflow |
| **Backtest a strategy** | DAILY_RUNBOOK.md | Backtest Recent Performance |
| **Understand a rating** | BREAKOUT_QUALITY_QUICK_REFERENCE.md | Rating definitions |
| **Evaluate signal quality** | BREAKOUT_QUALITY_USAGE_EXAMPLES.md | Real trade examples |
| **Find rejection reason** | DATA_QUALITY_CHECKS.md | Rejection reason codes |
| **Learn how system works** | SYSTEM_DESIGN.md | Complete specification |
| **Export data for analysis** | STRUCTURED_EXPORTS.md | Export types |
| **Update symbol list** | US_UNIVERSE_REFRESH.md | How to add symbols |
| **Use multi-timeframe** | MULTI_TIMEFRAME_ALIGNMENT.md | Confluence patterns |
| **Debug failed run** | DAILY_RUNBOOK.md | Troubleshooting section |

---

## 🔑 Key Commands Quick Reference

### **Scan Commands**
```bash
# Full system (US+India, Daily+Weekly)
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh

# Specific market/timeframe
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily

# Specific setup type
python3 apps/python/cli/run_vcp_system.py --setups vcp

# With strict filters
python3 apps/python/cli/run_vcp_system.py \
  --skip-us-refresh \
  --min-avg-volume 200000 \
  --min-avg-dollar-volume 5000000 \
  --regime-mode soft
```

### **Backtest Commands**
```bash
# Single backtest
python3 apps/python/cli/run_backtest.py

# Full matrix (US+India, Daily+Weekly)
python3 apps/python/cli/run_backtest.py --matrix-all

# With realistic costs
python3 apps/python/cli/run_backtest.py \
  --commission-bps 5 \
  --slippage-bps 5 \
  --fixed-cost 10

# With robustness analysis
python3 apps/python/cli/run_backtest.py \
  --walk-forward-folds 6 \
  --monte-carlo-iterations 2000 \
  --stability-lookbacks 504,728,900
```

See **[DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)** for complete command reference.

---

## 📊 Latest System Features (March 2026)

### **Milestone 2: Interactive HTML Reports**
✅ Real-time filtering by symbol, score, setup type  
✅ Column sorting (numeric and text)  
✅ Analytics dashboard (totals, averages)  
✅ Distribution charts (rating, setup split)  
✅ CSV export (currently filtered results)  
✅ Fundamentals data (market cap, PE, sector, yield)  
✅ Trade reasoning hover tooltips  

### **Milestone 3: 2-Year Historical Backtest**
✅ Walk-forward fold analysis  
✅ Monte Carlo robustness (2000+ iterations)  
✅ Parameter stability maps (lookback × hold-bars)  
✅ Realistic execution costs  
✅ Performance metrics (win rate, avg R, max drawdown, profit factor)  
✅ Trade log with MAE/MFE  
✅ RR filtering (1:2, 1:3)  

### **Top-5 Overlays**
✅ Rejection diagnostics (always on)  
✅ Liquidity filters (volume, dollar volume)  
✅ Market regime filter (soft/hard penalty)  
✅ Relative strength ranking (3M/6M/12M)  
✅ Portfolio heat control (top-6 shortlist)  

### **Quality Scoring**
✅ Wick/body candle anatomy weighting  
✅ Bullish body bonus, lower wick demand bonus, upper wick penalty  
✅ Breakout bar receives strongest weighting  
✅ Smooth capping to prevent scoring distortion  

### **Output Formats**
✅ Interactive HTML (all features)  
✅ CSV (flat structure for analysis)  
✅ JSON (structured for integration)  
✅ Timestamped archives (historical retention)  
✅ Rejection reports (diagnostic data)  
✅ Scan manifests (metadata per run)  

---

## 📈 Documentation Statistics

| Section | Files | Purpose |
|---------|-------|---------|
| **Core** | 3 | Main docs (README, INDEX, Summary) |
| **Runbooks** | 1 | Daily operations |
| **Reference** | 4 | Technical specifications |
| **Guides** | 10 | Feature documentation |
| **Archive** | 3+ | Historical milestones |
| **Total** | ~25 | Comprehensive system coverage |

---

## 🎓 Suggested Learning Path

### **Path 1: I Just Want to Run Scans** (30 min)
1. [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) → Default Daily Workflow
2. Run first scan
3. [BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md) → Understand ratings
4. Done!

### **Path 2: I Want to Understand the System** (2 hours)
1. [HLD_SWING_TRADING_SYSTEM.md](reference/HLD_SWING_TRADING_SYSTEM.md) → Architecture (30 min)
2. [SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md) → Technical spec (60 min)
3. [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) → Operations reference (30 min)

### **Path 3: I Want to Make Trading Decisions** (1 hour)
1. [BREAKOUT_QUALITY_FILTERS.md](guides/BREAKOUT_QUALITY_FILTERS.md) → How quality is scored (20 min)
2. [BREAKOUT_QUALITY_USAGE_EXAMPLES.md](guides/BREAKOUT_QUALITY_USAGE_EXAMPLES.md) → Real examples (20 min)
3. [MULTI_TIMEFRAME_ALIGNMENT.md](guides/MULTI_TIMEFRAME_ALIGNMENT.md) → Confirmation patterns (20 min)

### **Path 4: I Want to Backtest** (1 hour)
1. [MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md) → How it works (30 min)
2. [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) → Backtest Commands (20 min)
3. Run backtest, explore results (10 min)

---

## 💡 Pro Tips

1. **Bookmark [BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)** - You'll reference this daily
2. **Keep [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) handy** - All operational commands in one place
3. **Refer to [SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md) when curious** - Answers almost any "how does it work?" question
4. **Use [STRUCTURED_EXPORTS.md](guides/STRUCTURED_EXPORTS.md) for custom analysis** - Understand data structure before building tools

---

## 🚨 Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| Scan failed to run | [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) → Debugging section |
| Don't understand a rating | [BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md) |
| Symbol was rejected | [DATA_QUALITY_CHECKS.md](guides/DATA_QUALITY_CHECKS.md) → Rejection codes |
| Want to understand quality score | [BREAKOUT_QUALITY_FILTERS.md](guides/BREAKOUT_QUALITY_FILTERS.md) |
| Backtest results confusing | [MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md) → Metrics section |
| Need all commands | [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md) |
| Want to know how system works | [SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md) |

---

## ✅ All Documentation Updated

As of **March 22, 2026**, all documentation has been reviewed, updated, and cross-referenced:

- ✅ Main README updated
- ✅ INDEX completely reorganized
- ✅ DAILY_RUNBOOK expanded (400+ lines)
- ✅ All reference docs current
- ✅ All guides verified
- ✅ Archive docs link to current system
- ✅ Cross-references added throughout

**Status**: System is fully documented and production-ready. 🚀

---

## 📞 Support

For questions about:
- **What command to run** → [DAILY_RUNBOOK.md](runbooks/DAILY_RUNBOOK.md)
- **How the system works** → [SYSTEM_DESIGN.md](reference/SYSTEM_DESIGN.md)
- **Why a signal has this rating** → [BREAKOUT_QUALITY_QUICK_REFERENCE.md](guides/BREAKOUT_QUALITY_QUICK_REFERENCE.md)
- **What a rejection code means** → [DATA_QUALITY_CHECKS.md](guides/DATA_QUALITY_CHECKS.md)
- **How to use backtest** → [MILESTONE_3_BACKTEST.md](archive/MILESTONE_3_BACKTEST.md)
- **Data format for integration** → [STRUCTURED_EXPORTS.md](guides/STRUCTURED_EXPORTS.md)

**Everything is documented.** Start with [INDEX.md](INDEX.md) to find what you need.

