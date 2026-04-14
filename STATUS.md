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
- `scripts/fix_misclassifications2.py` — fixed 68 misclassifications
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

## ✅ Cache & Performance Fixes (April 14, 2026)

### Fix 1 — Best-Cache-File Selection (Python Dashboards)
- **Root cause**: `_load_prices()` in `generate_breadth_dashboard.py`, `generate_trade_plans_page.py`, `generate_sector_macro_page.py` returned the **first found** cache file instead of the most recently-dated one. Symbols with stale `_3528.csv` (March data) were used even when fresh `_900.csv` (April data) existed.
- **Fix**: All three dashboard generators now read **ALL candidate cache files** per symbol and return the one with the **most recent last date**. Added `_5096` to the search list.
- **Result**: Breadth dashboard now shows RECOVERY regime with April 2026 data instead of MIXED with March data.

### Fix 2 — Yahoo Finance Cookie+Crumb Auth (Java)
- **Root cause**: Yahoo Finance API requires cookie+crumb authentication since ~2024. Without it, requests get HTTP 401 or connection reset.
- **Fix** (`src/YahooFinanceProvider.java`):
  - Added `CookieManager` with `ACCEPT_ALL` to `HttpClient` for session cookies
  - Added `getCrumb()` method: visits Yahoo homepage → fetches crumb from `/v1/test/getcrumb`
  - Crumb cached for 20 minutes, thread-safe via `ReentrantLock`
  - Crumb appended as `&crumb=TOKEN` to all chart API requests

### Fix 3 — Circuit Breaker (Java + Python)
- **Root cause**: When Yahoo Finance is unreachable (IP block), the scan tried 8s × 2 hosts × 3 retries **per symbol** with retry sleep delays (400+800+1200ms = 2.4s each). With 2119 symbols, this caused **~10 minute** scan times.
- **Fix** (`src/YahooFinanceProvider.java`):
  - Added `_yahooBlockedUntil` static field — after first network failure, Yahoo is skipped for 30 minutes
  - `fetchFromYahoo()` returns `List.of()` (empty = "no new data") when circuit is open → retry loop breaks immediately without sleeping
  - `getCrumb()` trips circuit breaker if homepage/crumb endpoints fail
  - Request timeout reduced from 20s → 8s for fast failure
- **Fix** (`scripts/refresh_cache.py`):
  - Added `_yahoo_blocked_until` + `_is_yahoo_blocked()` + `_trip_circuit_breaker()`
  - `_fetch_crumb()` trips circuit breaker on connection error
  - `_get_session_and_crumb()` checks circuit before any retries (eliminates 5+10+15s sleep delays)
  - `_fetch_bars()` checks circuit at start + before each retry → returns `[]` immediately when blocked
  - `_do_refresh()` in parallel executor checks circuit → skips all remaining symbols instantly
  - `_fetch_crumb` and chart request timeouts reduced from 20s → 8s
- **Result**: India daily scan: **342s for batch 1** → **9s for batch 1**, total scan **~2 minutes** vs **~10 minutes**

### Fix 3b — Variable Name Bug (Java)
- Fixed `lastDate.plusDays(d)` → `lastValidDate.plusDays(d)` in `isDataCurrentEnough()` (was causing `javac` compile error)

### Fix 4 — Auto Cache Refresh Pipeline
- Added `scripts/refresh_cache.py` — Python-based incremental Yahoo Finance cache refresher
  - Uses cookie+crumb auth (same mechanism as Java)
  - Detects stale symbols by reading last date from each symbol's BEST cache file
  - Parallel workers (default 8) with rate limiting
  - Circuit breaker: stops immediately when Yahoo is unreachable instead of trying all 2119 symbols
- Added **Step 0** to `run_master.sh` — runs `refresh_cache.py` before Java scan
- Added cache refresh step to `run_analysis_dashboards.sh`

### Fix 5 — `check_cache_freshness.py` Utility
- New script to quickly check how many NSE symbols have fresh vs stale cache
- Shows stale symbols with last date and count

---

## ✅ Bug Fixes Applied (April 14, 2026 — Trade Board Field Name Audit)

### Fix H — Frontend Field Name Mismatch (trade_board.html)
- **Root cause**: JS sent `stop_loss`/`target_1`/`target_2`/`target_3` to the API, but the Pydantic model stores as `sl`/`t1`/`t2`/`t3`. Result: SL and targets were silently dropped (defaulted to 0).
- **Fixed in `submitAdd()`**: now sends `sl`, `t1`, `t2`, `t3`.
- **Fixed in `submitUpdate()`**: now sends `sl` (was `stop_loss`).
- **Fixed in `renderClosedTable()`**: reads `p.sl || p.stop_loss || e` (backward-compatible).

### Fix I — importSig() Missing Fields
- **Root cause**: `importSig()` didn't pre-fill T3, uppercase scan JSON fields (`T1`/`T2`/`T3`), `rating`, or `notes`.
- **Fix**: Added `fT3`, `s.T1||s.t1`, `s.T2||s.t2`, `s.T3||s.t3`, `rating`, and `notes` population.

---
- [ ] Quarterly review trigger, IPO auto-flagging, historical breadth tracking
- [ ] NSE holiday calendar integration for accurate stale detection (currently counts all weekdays, may flag holiday weeks as stale)
- [ ] Update stale symbols with `&` in name (M&M, ARE&M, GMRP&UI etc.) when Yahoo Finance becomes accessible again

---

## ✅ Cache Migration & Hardening (April 14, 2026)

### Fix J — Cache File Consolidation (`migrate_cache.sh`)
- **Problem**: Each symbol had multiple cache files (`SYMBOL_900.csv`, `SYMBOL_3528.csv`, `SYMBOL_5096.csv`) causing slow lookups and disk bloat.
- **Solution**: `scripts/migrate_cache.sh` merges all legacy `SYMBOL_N.csv` files into a single `SYMBOL.csv` per symbol (deduped by date, sorted chronologically).
- **Integration**: `run_master.sh` Step 0a auto-detects legacy files and runs migration before cache refresh. One-time operation — once migrated, no legacy files remain.

### Fix K — Unified Cache File Support (All Readers)
- **Problem**: After migration to `SYMBOL.csv`, all cache readers only looked for `_N.csv` suffixed files.
- **Fixed in**: `main.py` `_read_ohlcv()`, `generate_trade_plans_page.py`, `generate_breadth_dashboard.py`, `performance_tracker.py`, `refresh_cache.py`, `check_cache_freshness.py`
- **Change**: Added `""` (no suffix) as first candidate in all `for suffix in [...]` loops, so unified files are found before legacy files.

### Fix L — `.gitignore` Hardening
- **Added**: `*.class` (root .class files were untracked), `.venv/`, `trade_data/`, `*.log`
- **Removed**: 58 stale `.class` files from project root

### Fix M — Watchlist → Position Import (`importFromWL`)
- **Problem**: `importFromWL()` only populated symbol, name, and setup — scan data (entry, SL, targets) was lost.
- **Fix**: Now pre-fills entry, SL, rating, notes, and alert price as T1 from watchlist scan data.

---

## ✅ Bug Fixes Applied (April 14, 2026 — Full Repo Audit)

### Fix A — Duplicate Keys in SECTOR_MAP / INDUSTRY_MAP
- **Root cause**: `generate_trade_plans_page.py` had 11 SECTOR_MAP + 22 INDUSTRY_MAP duplicate keys. Python silently keeps the LAST value, causing wrong stock classifications.
- **Fixed entries (SECTOR_MAP)**:
  - `AAVAS` Pharma → **NBFC** (Aavas Financiers is a housing finance NBFC)
  - `SUDARSCHEM` Pharma → **Chemicals** (Sudarshan Chemicals is Specialty Chemicals)
  - `VOLTAMP` Electronics → **Cap Goods** (Voltamp Transformers is electrical equipment)
  - `TDPOWERSYS` Electronics → **Cap Goods** (TD Power Systems makes AC motors)
  - `KNRCON` Cap Goods → **Infra** (KNR Constructions is road/infra)
  - `KALYANKJIL` Metals → **Consumer** (Kalyan Jewellers is jewelry retail)
  - Removed duplicate entries for `APARINDS`, `AAVAS`, `SUDARSCHEM`, `DCMSHRIRAM`, `BALRAMCHIN`, `KALYANKJIL`, `PKTEA`, `PATANJALI`, `KNRCON`
- **Fixed entries (INDUSTRY_MAP)**:
  - `JUBLFOOD/DEVYANI/WESTLIFE` generic "QSR" → specific "QSR - Domino's/KFC/McDonald's"
  - `KALYANKJIL/SENCO/THANGAMAYL` "Jewellery" → **Gold Jewelry** (more specific)
  - Removed 22 duplicates from large stale block at bottom of INDUSTRY_MAP

### Fix B — SyntaxWarnings (Invalid Escape Sequences)
- `generate_trade_plans_page.py:2890` — JS regex `\w\s` inside Python string → `\\w\\s`
- `generate_performance_tracker.py:1247` — JS regex `\.` inside Python string → `\\.`
- **Result**: All 40+ Python files now compile cleanly with `-W error`

### Fix C — sortTable() JavaScript Bug (generate_master_report.py)
- **Root cause**: `sortTable()` only re-appended visible rows to tbody. Hidden rows migrated to the wrong position in DOM after every sort.
- **Fix**: Sort ALL rows (ROWS array), re-append all to tbody. Hidden rows stay hidden but in correct sorted order.

### Fix D — CORS Bug (apps/web/api/main.py)
- **Root cause**: `allow_origins=["*"]` with `allow_credentials=True` is invalid per CORS spec (browsers reject it).
- **Fix**: Changed `allow_credentials=False`. Credentials (cookies) are not needed for this public JSON API.

### Fix E — JobStore Persistence (apps/web/api/main.py)
- **Root cause**: `JobStore` kept all jobs in memory only — all job history lost on API restart.
- **Fix**: Added `JOBS_PERSIST_FILE = output/web_jobs/jobs_store.json` that persists job state to disk. On restart, in-flight jobs are marked `failed` with reason "API restarted".

### Fix F — Shell Script set -e Blocking Dashboard Generation
- **Root cause**: `run_analysis_dashboards.sh` has `set -e`. When `refresh_cache.py` exits with code 2 (Yahoo blocked, non-fatal), the shell exits before generating any dashboards.
- **Fix**: Wrapped `refresh_cache.py` call in `set +e ... set -e` in both `run_analysis_dashboards.sh` and `run_master.sh`.

### Fix G — NaN Close Propagation in Lib Files
- **Root cause**: `float(x or 0)` pattern doesn't catch `float('nan')` (NaN is truthy). NaN close values from partially-downloaded Yahoo bars propagated into indicators and caused incorrect signals.
- **Fixed in**: `apps/python/lib/setup_detector.py` and `apps/python/lib/performance_tracker.py` — now use `math.isnan()` guards on close values.

---

## 📊 Current Market (April 14, 2026)
- **Regime**: RECOVERY (Score: 67/100) · **Oscillator**: STRONG BUY (+10.3)
- **Cache**: 2099/2119 NSE symbols fresh to **April 10–13, 2026** · 20 symbols stale (Yahoo blocked)
- **Daily Scan**: **~49 signals** — scanned 2101 stocks in **~2 minutes**
- **Top Accelerating**: Renewable Energy, Optical Fiber Cables, Construction, Medical Devices, Power Towers
- **Custom Themes**: Data Center & AI (3M: +20.5%, α +28.9%), India Manufacturing (+13.0%, α +21.4%), Metals (+7.6%, α +16.0%), Sugar (+11.5%, α +19.9%)
- **Taxonomy**: 1,360 stocks · 380 industries · 24 sectors

---

## 🚀 How to Run
```bash
# Daily scan + dashboards (auto-refreshes cache, scans, generates HTML)
./run_master.sh --markets india --skip-performance-tracker

# Or just the dashboards (trade plans + breadth + sector/macro):
./run_analysis_dashboards.sh

# Start the full web console (includes Trade Board)
source .venv/bin/activate && uvicorn apps.web.api.main:app --host 0.0.0.0 --port 8000

# Open Trade Board
open http://localhost:8000/board

# Quick utilities
python3 check_cache_freshness.py          # Check how many symbols have fresh data
python3 scripts/refresh_cache.py --dry-run  # See what would be refreshed
python3 scripts/refresh_cache.py            # Force refresh all stale cache files
python3 apps/python/cli/generate_breadth_dashboard.py  # Breadth only (fast)
python3 scripts/add_missing_stocks.py       # Add new stocks to taxonomy
python3 scripts/fix_misclassifications2.py  # Fix sector/industry errors
```
