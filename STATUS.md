# SETUPS System Status

**Last Updated:** April 11, 2026  
**Dashboard:** `output/market_breadth.html` · `output/trade_plans_live.html`

---

## ✅ Completed Features

### Phase 1 — NSE Stock Taxonomy (nse_stock_taxonomy.csv)
- **898 NSE stocks** classified with sector + industry (2-level taxonomy)
- CSV is the single source of truth — editable without touching Python
- Auto-deduplication on append via `scripts/add_taxonomy_stocks.py`

### Phase 3 — Classification Engine
- `apps/python/lib/nse_taxonomy.py` — loads from CSV, auto-classify via yfinance
- `scripts/export_maps_to_csv.py` — merge Python maps → CSV
- `scripts/add_taxonomy_stocks.py` — batch add new stocks without duplicates
- `scripts/fix_taxonomy.py` — fix miscategorizations in batch

### Phase 4 — Market Breadth Dashboard (generate_breadth_dashboard.py)
**New Sections (v2):**
- 🎯 **Market Regime Banner** — Bull/Recovery/Mixed/Correction/Bear (score 0-100 + action advice)
- 📊 **Breadth Pulse Bar** — Oscillator, RS improving %, advance/decline, new highs
- 🎯 **Best Opportunity Screener** — Top 20 pre-extended setups by opportunity score
- 🚀 **Momentum Trajectories** — Accelerating / Improving / Decelerating / Collapsing
- 💰 **Smart Money Footprint** — Vol + RS + new highs institutional signal (0-100 score)
- ⚠️ **Divergence Alerts** — Bullish (early entry) + Bearish (risk warning)
- 🔄 **Sector Rotation Matrix** — Early/Mid/Late/Defensive cycle phases

**New Custom Themes (12 total):**
Data Center, Defense, EV, Spec Chems, Cap Markets, Railway,
PSU Banks, Pharma, Metals, Real Estate, India Manufacturing, Sugar

### Phase 5 — Sector Rotation Tracker
- Rotation Score (-100 to +100) per sector
- Signals: ROTATING IN / BUILDING / NEUTRAL / FADING / ROTATING OUT

### New Library: `apps/python/lib/market_breadth.py`
9 analytics functions: compute_market_regime, compute_breadth_pulse, detect_divergences,
compute_trajectories, compute_smart_money_footprint, compute_rotation_signals,
compute_breadth_oscillator, compute_sector_momentum_matrix, screen_best_opportunities

---

## 🔴 Pending (Phase 6)
- [ ] Quarterly review trigger, IPO auto-flagging, historical breadth tracking

---

## 📊 Current Market (April 11, 2026)
- **Regime**: MIXED (Score: 41/100) · **Oscillator**: STRONG BUY (+10.6)
- **Top Accelerating**: Packaging - Films, Renewable Energy, Defense Electronics, EV Vehicles, Shipbuilding

## 🚀 How to Run
```bash
./run_analysis_dashboards.sh                          # Full scan + all dashboards
python3 apps/python/cli/generate_breadth_dashboard.py # Breadth only (fast)
python3 scripts/add_taxonomy_stocks.py                # Add new stocks to taxonomy
```

