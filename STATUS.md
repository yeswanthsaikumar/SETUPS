# SETUPS System Status

**Last Updated:** April 14, 2026  
**Dashboard:** `output/market_breadth.html` · `output/trade_plans_live.html`  
**Trade Board:** http://localhost:8000/board

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

### Phase 7 — Trade Board (`/board`)
Live position tracker with real-time P&L, mini charts, and scan signal import.

**URL:** `http://localhost:8000/board`  
**Data store:** `output/trade_board.json`

#### Position Cards
- 📈 Gain % + ₹ amount (from entry or exit price for closed trades)
- **▲/▼ Day change chip** — live today's move (% and ₹) from previous close vs CMP
- **EMA badge** — injected after mini chart loads: `Above MAs` / `EMA20 ⚠` / `Below MAs ⚠`
- **Status-aware footer** — `⏱ Holding 14d` for open · `🛑 SL HIT · 7d` / `✅ T1 HIT · 5d` / `🏆 T3 HIT` for closed
- Mini candlestick chart with EMA5/20/50 and entry/SL/target price lines

#### Stats Bar (top)
- **Positions** — open count / total / closed
- **Day's P&L** — real-time sum of today's move across all open positions
- **Total P&L** — unrealised (open) + realised (closed) combined
- **Open Risk** — total ₹ at risk to stop-loss across open positions
- **Locked Profit** — cumulative ₹ from T1/T2/T3 exits

#### Position Detail Panel (click any card)
- Full-size 90-day candlestick chart with EMA lines + entry/SL/T1/T2/T3 price lines
- **Trade Plan grid** — T1/T2/T3 targets with Risk:Reward (e.g. `T2 · 2.4R`) and % from entry
- **Risk summary** — risk/share × quantity = total ₹ at risk
- **Today's Move** — `▲ 1.5% · ₹2,400` (open positions only)
- Exit info for closed positions (exit price, exit date, hold duration)

#### Scan Signals Drawer (📡 button)
- Pulls latest `open_trades_india_daily_full_LATEST.json` (falls back to `vcp_hits_*`)
- Shows setup, VOL %, and Dist % per signal
- **One-click import** → pre-fills entry, SL, T1, T2, T3, setup, rating, notes into Add Modal

#### Equity Curve + Performance Summary
- Area chart of cumulative P&L across all closed trades
- **Win Rate · Avg Win · Avg Loss · Expectancy** stats row

#### API Endpoints
| Endpoint | Description |
|---|---|
| `GET /board` | Trade Board HTML page |
| `GET /api/trade-board/positions` | All positions enriched with CMP, gain, day change |
| `POST /api/trade-board/positions` | Add a new position |
| `PUT /api/trade-board/positions/{id}` | Update status, SL, exit price/date |
| `DELETE /api/trade-board/positions/{id}` | Delete a position |
| `GET /api/trade-board/chart/{symbol}` | OHLCV + EMA5/20/50 from cache |
| `GET /api/trade-board/equity` | Equity curve + cumulative P&L |
| `GET /api/trade-board/scan-signals` | Latest scan signals for quick import |

### Live Trades UI Enhancement
- Added **Market Breadth ↗** and **Trade Plans ↗** quick links in Performance Tracker panel

---

## 🔴 Pending (Phase 6)
- [ ] Quarterly review trigger, IPO auto-flagging, historical breadth tracking

---

## 📊 Current Market (April 14, 2026)
- **Regime**: CORRECTION (Score: 37/100) · **Oscillator**: STRONG BUY (+9.6)
- **Top Accelerating**: Packaging - Films, Renewable Energy, Defense Electronics, EV Vehicles, Shipbuilding
- **Taxonomy**: 1,360 stocks · 380 industries · 24 sectors

## 🚀 How to Run
```bash
# Start the full web console (includes Trade Board)
source .venv/bin/activate && uvicorn apps.web.api.main:app --host 0.0.0.0 --port 8000

# Open Trade Board
open http://localhost:8000/board

./run_analysis_dashboards.sh                          # Full dashboards (all)
python3 apps/python/cli/generate_breadth_dashboard.py # Breadth only (fast)
python3 scripts/add_missing_stocks.py                 # Add new stocks to taxonomy
python3 scripts/fix_misclassifications2.py            # Fix sector/industry errors
```
