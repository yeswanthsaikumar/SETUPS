# SETUPS System — Completion Checklist

> Last Updated: April 14, 2026

## ✅ Core Infrastructure

- [x] Java scanner engine (VCP, Range Expansion, Breakout Pullback, Bull Flag)
- [x] Python scan orchestrator (`run_vcp_system.py`)
- [x] Yahoo Finance cookie+crumb auth (Java + Python)
- [x] Circuit breaker for Yahoo Finance (Java + Python) — scan in ~2min vs ~10min
- [x] NSE stock taxonomy — 1,360 stocks, 380 industries, 24 sectors
- [x] Cache refresh pipeline (`scripts/refresh_cache.py`)
- [x] Cache migration tool (`scripts/migrate_cache.sh`) — merges `SYMBOL_N.csv` → `SYMBOL.csv`
- [x] Cache freshness checker (`check_cache_freshness.py`)

## ✅ Dashboards & Reports

- [x] Market Breadth Dashboard — regime banner, breadth pulse, 12 custom themes
- [x] Trade Plans Page — MF/institutional holdings enrichment
- [x] Sector Macro Analysis page
- [x] Master Report with fundamentals
- [x] Performance Tracker
- [x] Best-cache-file selection fix (all generators)

## ✅ Web Console (`apps/web/`)

- [x] FastAPI backend with CORS, persistent job store
- [x] Stock Analyzer — single-stock deep-dive
- [x] Trade Plan Assistant — scan brief
- [x] Watchlist Pattern Lab — RS Leader detection
- [x] MF/Institutional Holdings API
- [x] Performance API

## ✅ Trade Board (`/board`)

- [x] Position CRUD with persistent JSON store (`trade_data/`)
- [x] Live CMP, gain %, gain ₹ from cached OHLCV
- [x] Day P&L — real-time from prev_close → cmp × qty
- [x] Position cards — mini charts, EMA/RSI/Vol badges, progress to T1
- [x] Detail panel — full candlestick chart with EMA20/50, SMA150/200, RSI, volume
- [x] Trade plan grid — T1/T2/T3 with R:R ratios, risk summary
- [x] Closed position gain from exit_price
- [x] Status-aware card footer (Holding / SL HIT / T1 HIT / T3 HIT)
- [x] Scan signals drawer — import with entry/SL/T1/T2/T3 pre-fill
- [x] Equity curve + closed trade stats (win rate, avg win/loss, expectancy)
- [x] Trade Journal — per-symbol notes with mood tracking
- [x] Watchlist — CMP + day change, scan signal enrichment, mini charts
- [x] Import from watchlist → position with scan data pre-fill
- [x] Embedded reports (Trade Plans, Breadth, Sector, Scan) via iframe
- [x] Export all data as JSON bundle
- [x] Auto-refresh every 30 seconds
- [x] Partial exits — book partial position exits with qty/price/reason, auto-compute realized P&L
- [x] PARTIAL status — positions with partial exits shown with remaining/total qty badge
- [x] Enriched position endpoint — 20EMA extension, quarterly/yearly volume records
- [x] Enriched watchlist endpoint — 20EMA extension + volume analysis
- [x] Equity curve includes partial exit events

## ✅ Bug Fixes & Hardening

- [x] Fix H — Frontend field name mismatch (`stop_loss`→`sl`)
- [x] Fix I — `importSig()` missing T3, uppercase field mapping
- [x] Fix A — Duplicate keys in SECTOR_MAP/INDUSTRY_MAP
- [x] Fix B — SyntaxWarnings (invalid escape sequences)
- [x] Fix C — `sortTable()` DOM bug
- [x] Fix D — CORS bug (`allow_credentials` with wildcard)
- [x] Fix E — JobStore persistence to disk
- [x] Fix F — `set -e` blocking dashboards on non-fatal exits
- [x] Fix G — NaN close propagation
- [x] `.gitignore` updated — covers `.class`, `.venv/`, `trade_data/`
- [x] Root `.class` files cleaned up
- [x] Unified cache file support in `_read_ohlcv`

## 🔲 Remaining / Future

- [ ] NSE holiday calendar for accurate stale detection
- [ ] Quarterly review trigger, IPO auto-flagging
- [ ] Historical breadth tracking (time-series)
- [ ] Update stale symbols with `&` in name (M&M, ARE&M)
- [ ] Price/SL proximity alerting system
- [ ] Multi-account portfolio tracking

