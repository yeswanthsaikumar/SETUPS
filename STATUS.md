# SETUPS System Status

**Last Updated:** April 13, 2026  
**Dashboard:** `output/market_breadth.html` · `output/trade_plans_live.html`

---

## ✅ Completed Features

### Phase 1 — NSE Stock Taxonomy (nse_stock_taxonomy.csv)
- **1,360 NSE/BSE stocks** classified with sector + industry (2-level taxonomy)
- CSV is the single source of truth — editable without touching Python
- Auto-deduplication on append via `scripts/add_taxonomy_stocks.py`
- 380 unique industries across 24 sectors

### Phase 3 — Classification Engine
- `apps/python/lib/nse_taxonomy.py` — loads from CSV, auto-classify via yfinance
- `scripts/fix_misclassifications2.py` — fixed 68 misclassifications (VIMTALABS→Pharma/CRO, BHEL→Cap Goods, KRN→Heat Exchangers, BOROSIL→Scientific Glassware, INOXINDIA→Cryogenic Equipment, TEJAS→Telecom, RAJESHEXPO→Jewellery, etc.)
- `scripts/add_missing_stocks.py` — added 123 new stocks (Nifty500, IPOs 2023-26)

### Phase 4 — Market Breadth Dashboard (generate_breadth_dashboard.py)
**v2 Sections:**
- 🎯 **Market Regime Banner** — Bull/Recovery/Mixed/Correction/Bear
- 📊 **Breadth Pulse Bar** — Oscillator, RS improving %, advance/decline, new highs
- 🎯 **Best Opportunity Screener** — Top 20 pre-extended setups
- 🚀 **Momentum Trajectories** — Accelerating / Improving / Decelerating / Collapsing (with stock chips)
- 💰 **Smart Money Footprint** — Vol + RS + new highs signal (with stock chips)
- ⚠️ **Divergence Alerts** — Bullish + Bearish
- 🔄 **Sector Rotation Matrix** — cycle phases
- 📊 **Sector Scorecard** — now shows TOP STOCKS per sector
- ⚡ **Emerging Trends** — now shows ALL STOCKS with 20MA color coding
- 🔥 **Volume Clusters** — now shows ALL STOCKS sorted by volume rank
- 🏔 **52W High Momentum** — now shows ALL STOCKS sorted by new high status

**"Full Detail" button FIXED:**
- Modal always opens (even for untracked stocks without cache data)
- Untracked stocks shown with "No cache" indicator at bottom of table
- Sortable by Ticker, Price, 20MA, 1M/3M returns, RS 3M

**Custom Themes (12):**
Data Center & AI, Defense, EV, Spec Chems, Cap Markets, Railway,
PSU Banks, Pharma, Metals, Real Estate, India Manufacturing, Sugar

### Phase 5 — Sector Rotation Tracker
- Rotation Score per sector · ROTATING IN/OUT signals

### Live Trades UI Enhancement
- Added **Market Breadth ↗** and **Trade Plans ↗** quick links in Performance Tracker panel

---

## 🔴 Pending (Phase 6)
- [ ] Quarterly review trigger, IPO auto-flagging, historical breadth tracking

---

## 📊 Current Market (April 13, 2026)
- **Regime**: CORRECTION (Score: 37/100) · **Oscillator**: STRONG BUY (+9.6)
- **Top Accelerating**: Packaging - Films, Renewable Energy, Defense Electronics, EV Vehicles, Shipbuilding
- **Taxonomy**: 1,360 stocks · 380 industries · 24 sectors

## 🚀 How to Run
```bash
./run_analysis_dashboards.sh                          # Full dashboards (all)
python3 apps/python/cli/generate_breadth_dashboard.py # Breadth only (fast)
python3 scripts/add_missing_stocks.py                 # Add new stocks to taxonomy
python3 scripts/fix_misclassifications2.py            # Fix sector/industry errors
```

