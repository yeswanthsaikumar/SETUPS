# SETUPS System – Improvements Summary

> Last Updated: 2026-04-14

## Overview

This document summarises all major improvements added to the SETUPS breakout-scanning system beyond the initial working baseline.

---

## 1 · Full Setup Mode (`--setups full`)

**Files changed:** `apps/python/cli/run_full_us_scan.py`, `apps/python/cli/run_vcp_system.py`, `apps/web/api/main.py`, `apps/web/ui/index.html`

The system previously had `--setups both` (VCP + Range Expansion via Java) and `--setups mean_reversion` (Python-only). A new `full` mode was added that combines all three setups in a single run:

- Java scanner runs `--setups both` (VCP + RANGE_EXPANSION)
- Python mean-reversion detector appends MEAN_REVERSION hits to the same output
- Combined output is saved as `vcp_hits_{label}_full_LATEST.{csv,json,html}`
- Split per-setup JSON files are also saved: `…_vcp_LATEST.json`, `…_range_expansion_LATEST.json`, `…_mean_reversion_LATEST.json`

`full` is now the default setup mode across the CLI, API, and web UI.

---

## 2 · Stock Analyzer Library

**File:** `apps/python/lib/stock_analyzer.py`

A new single-stock deep-dive analysis engine that searches all scan output files for a given symbol and returns a rich, structured analysis dict. Key outputs:

| Field | Description |
|---|---|
| `status` | `BREAKOUT` / `ACTIVE_TRADE` / `WATCHLIST` / `REJECTED` / `NOT_FOUND` |
| `actionVerdict` | `BUY_NOW` / `WATCH_CLOSELY` / `CAUTION` / `AVOID` / `DATA_MISSING` |
| `confidence` | 0–100 composite confidence score |
| `tradePlan` | Entry, stop-loss, T1/T2/T3 targets, R:R ratios, suggested shares |
| `setupAnalysis` | Pattern description, bullets, quality score |
| `regimeAnalysis` | Regime state (FAVORABLE / NEUTRAL / UNFAVORABLE), score, emoji |
| `rsAnalysis` | RS 3m/6m/12m percentiles, RS score, bullets |
| `volumeAnalysis` | Avg volume, dollar volume, dry-up ratio, bullets |
| `mtfAnalysis` | Weekly agreement (STRONG / MIXED / DISAGREE), score, emoji |
| `reasoning` | Step-by-step reasoning bullet list |
| `rejectionDetail` | Detailed rejection explanation with actionable tips |

---

## 3 · Trade Plan Assistant Library

**File:** `apps/python/lib/trade_plan_assistant.py`

Provides natural-language scan summaries from the latest scan output files:

- `build_scan_brief()` — loads latest hits, ranks by score, generates one-line summaries per symbol
- `brief_as_text()` / `brief_as_json()` — text or JSON output
- Handles all setup modes with fallback file resolution

---

## 4 · New API Endpoints

**File:** `apps/web/api/main.py`

| Endpoint | Description |
|---|---|
| `GET /api/stock/analyze` | Deep-dive single-stock analysis. Params: `symbol`, `market`, `timeframe`, `setups` |
| `GET /api/assistant/scan-brief` | LLM-style scan summary. Params: `market`, `timeframe`, `setups`, `top_n` |

---

## 5 · Stock Analyzer Web UI Panel

**File:** `apps/web/ui/index.html`

A full-width **Stock Analyzer** panel was added to the web console:

- Symbol search box with Enter-key support
- Market / timeframe / setups selectors
- **Verdict banner** with colour-coded action (`🟢 BUY NOW`, `🟡 WATCH CLOSELY`, `🟠 CAUTION`, `🔴 AVOID`, `⚪ DATA MISSING`) and confidence progress bar
- **Status tags** (list type, rating, setup type, window, market/timeframe)
- **Trade Plan grid** — entry, stop, targets, R:R ratios, suggested shares, distance from pivot
- **Setup Analysis** bullets — pattern description, contraction waves, pivot freshness
- **Market Regime & MTF** — regime state/score and weekly agreement emoji
- **Relative Strength** — RS 3m/6m/12m percentiles and RS score
- **Volume Analysis** — avg volume/dollar volume, dry-up ratio assessment
- **Detailed Reasoning** — step-by-step bullet list
- **Rejection Detail** — actionable rejection explanation with tips
- **Raw Scan Data** toggle — show/hide the underlying JSON record

---

## 6 · CLI Trade Plan Assistant

**File:** `apps/python/cli/run_trade_plan_assistant.py`

```bash
# Quick text summary of top 12 india daily full signals
python apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full

# JSON output for programmatic use
python apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full --format json
```

---

## 7 · Java HTML Report Fixes

**File:** `src/HtmlReportGenerator.java`

Fixed string formatting in the HTML report generator:
- The hero stats section and analytics section used string concatenation (`""" + variable + """`) inside Java text blocks. This was replaced with `.formatted(...)` calls to avoid potential conflicts with `%` characters in market/timeframe strings.
- Added pre-computation of `bestScore` variable for the analytics section.

---

## 8 · Split JSON Output for Full Mode

When `--setups full` is used, the scanner saves per-setup split JSON files in addition to the combined `_full_LATEST.json`:

```
output/vcp_hits_india_daily_vcp_LATEST.json
output/vcp_hits_india_daily_range_expansion_LATEST.json
output/vcp_hits_india_daily_mean_reversion_LATEST.json
output/vcp_hits_india_daily_full_LATEST.json   ← combined
```

These are used by the stock analyzer and trade plan assistant for setup-specific lookups.

---

## 9 · Smoke Test Enhancement

**File:** `apps/web/scripts/smoke_test.py`

Extended the API smoke test to cover:
- `GET /api/health` ✅
- `GET /api/jobs` ✅
- `GET /api/assistant/scan-brief` ✅
- `GET /api/stock/analyze` ✅ *(new)*

---

## 10 · Documentation

New documentation added under `docs/`:

| File | Description |
|---|---|
| `docs/guides/TRADE_PLAN_ASSISTANT.md` | How to use the trade plan assistant CLI and API |
| `docs/runbooks/TROUBLESHOOTING.md` | Common issues and solutions |
| `docs/runbooks/UNIFIED_FULL_MODE_RUNBOOK.md` | Full daily workflow using `--setups full` |

---

## How Breakout Stocks and Their Performance Are Stored and Saved in HTML Pages

### 1. Data Preparation
- The scan process collects all breakout hits and stores them as a list of dictionaries (`all_hits`).
- For open trades, the function `as_open_trade_rows(snapshot)` is used to add post-breakout tracking fields (distance from breakout, % gain/loss, days since breakout, etc.).
- This processed list is called `open_trade_snapshot`.

### 2. Saving Performance Data
- The function `save_breakout_performance(open_trade_snapshot, path)` writes the open trade snapshot to a CSV file, including all post-breakout performance metrics.
- The CSV fields include: symbol, breakoutDate, entry, close, distance_from_breakout, pct_gain_since_breakout, days_since_breakout, max_after_breakout, min_after_breakout, setup, rating, window, listType.

### 3. Saving HTML Reports
- The function `save_html(rows, path, meta)` generates an interactive HTML report from the given rows (e.g., `open_trade_snapshot`).
- This HTML includes:
  - A summary of analytics (counts, averages, rating distribution, etc.).
  - A sortable/filterable table with all breakout stocks and their performance fields.
  - Links to Yahoo Finance and TradingView for each symbol.
  - Tooltips and badges for setup type, rating, and other attributes.
- The HTML is saved to files like `breakout_performance_{label}_{timestamp}.html` and `breakout_performance_{label}_LATEST.html`.

### 4. File Locations
- CSV and HTML files are saved in the `output/` directory, with both timestamped and `LATEST` versions for easy access.

### 5. Code References
- Data preparation: `as_open_trade_rows()`
- CSV save: `save_breakout_performance()`
- HTML save: `save_html()`
- Main usage: see lines around 2180–2240 in `apps/python/cli/run_full_us_scan.py`

---

## Quick Reference

```bash
# Run full daily scan (india only, skip US refresh)
python apps/python/cli/run_vcp_system.py --markets india --timeframes daily --setups full --skip-us-refresh

# Get trade plan brief
python apps/python/cli/run_trade_plan_assistant.py --market india --timeframe daily --setups full --top-n 10

# Start the web console (includes Trade Board at /board)
source .venv/bin/activate && uvicorn apps.web.api.main:app --host 0.0.0.0 --port 8000

# Open Trade Board in browser
open http://localhost:8000/board

# Smoke test
source .venv/bin/activate && python apps/web/scripts/smoke_test.py
```

---

## 11 · Trade Board (`/board`) — April 2026

**Files changed:** `apps/web/ui/trade_board.html` *(new)*, `apps/web/api/main.py`

A full-featured live position tracker accessible at `http://localhost:8000/board`.
Trade data is persisted in `output/trade_board.json`.

### Backend additions (`main.py`)

| Item | Detail |
|---|---|
| `TradeBoardPosition` model | id, symbol, name, entry, qty, sl, t1/t2/t3, setup, rating, notes, status, exit_price/date |
| `TradeBoardUpdate` model | Partial update for status, SL, exit price/date, notes |
| `_get_price_info(symbol)` | Returns `(cmp, prev_close)` from cached OHLCV — powers day P&L |
| `_compute_board_stats()` | Aggregates day_pl, total_pl, open_risk, locked_profit |
| `GET /api/trade-board/positions` | Positions enriched with live CMP, gainPct, gainAmt, dayChangePct, dayChangeAmt |
| `GET /api/trade-board/summary` | Aggregate stats only |
| `POST /api/trade-board/positions` | Create position |
| `PUT /api/trade-board/positions/{id}` | Update position |
| `DELETE /api/trade-board/positions/{id}` | Delete position |
| `GET /api/trade-board/chart/{symbol}` | OHLCV + EMA5/20/50 from cache CSV files |
| `GET /api/trade-board/equity` | Equity curve (date, pl, cumPl) for closed trades |
| `GET /api/trade-board/scan-signals` | Top 30 signals from `open_trades_*` or `vcp_hits_*` LATEST JSON |

**Key fixes vs. initial version:**
- `day_pl` was always `0` — now computed from `prev_close → cmp` delta × qty for each open position
- Closed positions had `gainPct = 0` — now computed from `exit_price - entry`
- Scan signals fallback: tries `open_trades_*` first, then `vcp_hits_*`; normalises `score` → `rankingScore`

### Frontend additions (`trade_board.html`)

**Stats Bar**
- Day's P&L now shows real money (sum of today's moves across all open positions)

**Position Cards**
- `▲/▼ X.X% today` chip below the gain — green/red, only on OPEN positions
- Status-aware footer: `⏱ Holding 14d` | `🛑 SL HIT · 7d` | `✅ T1 HIT · 5d` | `🏆 T3 HIT · 3d`
- EMA badge (`Above MAs` / `EMA20 ⚠` / `Below MAs ⚠`) injected into the card *after* the mini chart loads, using EMA5 + EMA20 crossover logic
- Closed position exit label changes dynamically: `SL Exit` / `T1 HIT` / `T2 HIT` etc.

**Detail Panel (click any card)**
- Trade Plan section: T1/T2/T3 boxes showing price + R:R (e.g. `T2 · 2.4R`) + `% from entry`
- Risk summary line: `Risk/share: ₹95 · Total risk: ₹9,500`
- Today's Move row (open positions): `▲ 1.5% · ₹2,400`
- Correct exit info for closed positions (exit price, date, hold duration in days)

**Scan Signals Drawer**
- Signal rows now show `Setup · VOL 69% · Dist 1.2%` sub-info
- `prefillFromSignal()` maps uppercase `T1`/`T2`/`T3` fields from scan JSON → Add Position modal
- Fallback to `vcp_hits_*` if `open_trades_*` doesn't exist

**Equity Curve + Closed Trade Stats**
- After the equity chart: Win Rate · Avg Win · Avg Loss · Expectancy row
- Appears automatically once there is at least one closed trade

### Before vs. After

| Area | Before | After |
|---|---|---|
| Day's P&L | Always `—` / 0 | Real-time from OHLCV prev_close |
| Closed position gain | Always 0% | Computed from exit_price |
| EMA badge | Never shown | Injected after chart load |
| Card footer | "Holding Xd" always | Status icon + hold duration |
| Detail panel targets | Not shown | T1/T2/T3 with R:R + % |
| Signal prefill | Entry + SL only | Entry + SL + T1 + T2 + T3 |
| Signal sub-info | Setup type only | Setup + VOL% + Dist% |
| Performance stats | None | Win rate, avg win/loss, expectancy |

