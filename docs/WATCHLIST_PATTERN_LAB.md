# 🔬 Watchlist Pattern Lab — Documentation

## Overview

The **Watchlist Pattern Lab** is an advanced daily-use stock analysis interface that identifies **RS Leader** stocks — stocks that outperform the market during corrections, consolidate tightly, and then lead the next upmove.

### The Pattern (Real Example)
> Stocks like **SLTTECH, AEROFLEX, PFOCUS, AVANTIFEED, BAJAJCON, CENTUM, ATLANTAELE, POWERINDIA** gave **30-50% returns Jan-Feb 2026**, then **held/consolidated while the entire market fell in March** (Iran-US tensions), then **flew high once the macro situation cleared**. This is the RS Leader pattern.

---

## How to Use (Daily Workflow)

### 1. Open the Dashboard
```
http://localhost:8000
```
Scroll down to the **🔬 Watchlist Pattern Lab** section.

### 2. Enter Your Watchlist
Paste any comma or newline-separated list of NSE stock symbols:
```
SLTTECH, AEROFLEX, PFOCUS, AVANTIFEED, BAJAJCON, CENTUM, ATLANTAELE, POWERINDIA
```
Or click **"Load Example List"** to use the default RS Leaders.

### 3. Configure Options
- **Market**: India (NSE) or US
- **Workers**: Parallel analysis threads (4 recommended)
- **Include News / Fundamentals / FII-DII**: Toggle for faster/deeper analysis

### 4. Click "🔍 Analyze Watchlist"
Results appear in ~20-60 seconds depending on list size.

### 5. Review Results

**Market Context Bar** — Nifty phase timeline (decline / consolidation / recovery)

**🌟 RS Leaders** — Cards for stocks passing the pattern criteria, sorted by pattern score

**Full Summary Table** — All stocks ranked, sortable by any column

**🔎 Deep Dive** — Click any symbol for detailed tabs:
- 📊 Trade Thesis
- 🎯 Pattern Analysis  
- 📈 Fundamentals
- 🏦 FII/DII
- 📰 News
- 📉 Phase Behavior

---

## Metrics Explained

### RS Score (1-99, IBD-style)
Weighted relative return vs Nifty50 across multiple time periods:
- **3-month** (40% weight) — most recent, most important
- **6-month** (20%)
- **9-month** (20%)
- **12-month** (20%)

| Score | Label | Meaning |
|-------|-------|---------|
| 90-99 | 🚀 Elite Leader | Top 1-10% of stocks |
| 80-89 | 💪 Strong RS | Well above average |
| 65-79 | ✅ Above Avg | Outperforming |
| 50-64 | 🔵 Average | In line with market |
| 35-49 | ⚠️ Below Avg | Underperforming |
| 1-34  | 🔴 Laggard | Avoid |

**Target**: RS > 75 before entering any trade.

### ADR% (Average Daily Range)
```
ADR = mean(High - Low) / Close × 100  (last 20 days)
```
| ADR | Label | Use Case |
|-----|-------|----------|
| >6% | 🔥 Very High | Intraday only, high risk |
| 4-6% | ⚡ High | Good for aggressive swings |
| 2.5-4% | ✅ Good | Ideal for swing trades |
| 1.5-2.5% | 🔵 Moderate | Conservative swings |
| <1.5% | 😴 Low | Institutional / avoid |

### Stage Analysis (Weinstein)
| Stage | Label | What it means |
|-------|-------|--------------|
| 2 | Stage 2 — Uptrend ✅ | **Buy here** — trending above all MAs |
| 1 | Stage 1 — Basing 🔵 | Accumulation — watch for breakout |
| 3 | Stage 3 — Topping ⚠️ | Distribution — reduce exposure |
| 4 | Stage 4 — Downtrend 🔴 | Avoid — wait for Stage 1 |

Stage 2 requires: Price > MA50 > MA150 > MA200, MA200 rising.

### Consolidation Quality
| Metric | Ideal | Meaning |
|--------|-------|---------|
| Base Depth | <15% | How much stock corrected from pivot high |
| Tightness (CV) | <5% | Std dev / mean of closes in base |
| Vol Dry-up | <0.7x | Recent vol / prior avg vol |
| Up/Dn Vol Ratio | >1.3 | Accumulation on up days |
| Consolidation Score | >70/100 | Overall base quality |

### RS Leader Pattern Score (0-100)
Composite score from:
1. **Held during market declines** (+30 pts max) — stock declined less than Nifty
2. **Led during market recoveries** (+25 pts max) — stock rose more than Nifty  
3. **Quality consolidation** (+25 pts max) — tight base, vol dry-up
4. **Near breakout pivot** (+20 pts max) — within 5% of base high
5. **RS Score bonus** (+10 pts max) — RS > 80 adds extra points

| Score | Label |
|-------|-------|
| 85-100 | 🌟 ELITE RS LEADER |
| 70-84 | 🚀 Strong RS Leader |
| 55-69 | ✅ RS Leader |
| 40-54 | 🔵 Potential Leader |
| 0-39 | ⚠️ Not a Leader Pattern |

### Trade Plan
Generated automatically per stock:
- **Entry (Breakout)**: 0.1% above the base high (pivot point)
- **Entry (Pullback)**: Near MA20 + 0.5% buffer
- **Stop Loss**: Max of (base low × 0.98) or (price - 1.5× ATR)
- **Target 1**: Entry + 1.5× risk
- **Target 2**: Entry + 2.5× risk  
- **Target 3**: Entry + 4.0× risk
- **Position Size**: Shown for 1% capital risk on ₹10 Lakh portfolio

---

## Market Phase Detection

The system auto-detects Nifty50 phases:

| Phase | Criteria | What to do |
|-------|----------|-----------|
| 📉 Decline | -3%+ over 10-day window | Monitor RS leaders — they should hold |
| 📊 Consolidation | ±3% sideways | Wait for resolution — look for tight bases |
| 📈 Recovery | +3%+ over 10-day window | Buy RS leaders breaking out |

**Key insight**: During market declines, RS Leaders decline less (excess return > 0%). During recoveries, they lead the move (excess return >> 0%). This is the core signal.

---

## FII/DII Analysis

Data from Screener.in (shareholding pattern) + yfinance:

| Signal | Meaning |
|--------|---------|
| ACCUMULATING | Smart money buying — DII ↑ and/or FII ↑ |
| DISTRIBUTING | Smart money selling — DII ↓ and FII ↓ |
| NEUTRAL | No clear institutional direction |

**Best setups**: DII accumulating + FII stable/up + Promoters stable.

---

## Fundamentals

Key metrics tracked:
- **EPS QoQ%**: Quarterly earnings growth (look for > 15%)
- **Revenue YoY%**: Annual revenue growth (look for > 20%)
- **Debt/Equity**: < 0.5 is clean balance sheet
- **ROE%**: Return on equity (> 15% is healthy)
- **Earnings Quality**: Net income + Free Cash Flow both positive

**Earnings catalyst**: Stocks that just posted strong earnings + technical setup = highest conviction setups.

---

## News & Catalysts

News scraped from multiple sources per stock:
1. **Yahoo Finance** — fastest, most current
2. **Economic Times Markets** (RSS) — India market news
3. **Moneycontrol** (RSS) — stock-specific analysis
4. **LiveMint** (RSS) — business news
5. **NSE Announcements API** — corporate announcements
6. **Screener.in** — announcements section

News cached for 15 minutes to avoid rate limits.

---

## API Endpoints

### Analyze Watchlist
```
POST /api/watchlist/analyze
Content-Type: application/json

{
  "symbols": ["AEROFLEX", "CENTUM", "SLTTECH"],
  "market": "india",
  "workers": 4,
  "include_news": true,
  "include_fundamentals": true,
  "include_mf": true
}
```

### Analyze Single Stock
```
GET /api/watchlist/analyze-single?symbol=AEROFLEX&market=india
```

### Market Phases
```
GET /api/watchlist/market-phases?days=252
```

### Default List
```
GET /api/watchlist/default-list
```

---

## Performance Considerations

| Operation | Time |
|-----------|------|
| Nifty50 data fetch | ~2s (cached 30 min) |
| Single stock price | ~2-3s (cached 30 min) |
| Full analysis per stock | ~5-8s |
| 10-stock watchlist (4 workers) | ~15-25s |
| Fundamentals | ~3s per stock (cached 24h) |
| News | ~2-5s per stock (cached 15 min) |
| FII/DII from Screener | ~5-8s per stock (cached 6h) |

All data is cached in `cache/wpe_*.json` files. Second runs are near-instant.

---

## Daily Use Workflow

**Morning (Pre-market)**:
1. Open dashboard → Pattern Lab
2. Paste your watchlist / use saved list
3. Check "Include News + Fundamentals + FII"
4. Click Analyze (~30-60 sec for 10 stocks)
5. Review Leaders section — stocks with pattern score > 70
6. Check Phase Behavior tab — how each held during recent Nifty declines
7. Set price alerts at entry/pivot levels

**During Market**:
1. Uncheck "Include Fundamentals" for faster refresh
2. Re-run every 1-2 hours
3. Monitor conviction scores — rising = bullish setup developing

**Evening Review**:
1. Full run with all options enabled
2. Check news tab for earnings / announcements
3. Update watchlist based on new setups forming

---

## Files

| File | Purpose |
|------|---------|
| `apps/python/lib/watchlist_pattern_engine.py` | Core analysis engine |
| `apps/web/api/main.py` | FastAPI endpoints |
| `apps/web/ui/index.html` | Pattern Lab UI |
| `cache/wpe_*.json` | Cached price/fund/news data |
| `docs/WATCHLIST_PATTERN_LAB.md` | This documentation |

