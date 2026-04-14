#!/usr/bin/env python3
"""
generate_master_report.py — Enhanced Master Report
───────────────────────────────────────────────────
Reads ALL *_LATEST.json outputs (breakout hits, watchlist, open trades,
portfolio shortlist), merges them across markets/timeframes, enriches with
fundamentals (EPS, Rev, Debt, MCap, Sector) and writes a single master HTML
report with:

  ✅ All list types: BREAKOUT / WATCHLIST / OPEN_TRADE / PORTFOLIO
  ✅ Fundamentals panel (📊 click to add notes, score, tailwinds)
  ✅ Breakout performance tracking (% since entry, days held)
  ✅ Interactive column legend (all 25+ columns explained)
  ✅ Filters: market, timeframe, setup, list type, min score, rating, symbol
  ✅ Score weighting: fundamentals score boosts rank by up to +13.5%

Usage:
    python3 apps/python/cli/generate_master_report.py
    python3 apps/python/cli/generate_master_report.py --skip-fundamentals
    python3 apps/python/cli/generate_master_report.py --account-size 2000000 --risk-pct 0.01
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

try:
    from fundamentals_provider import FundamentalsProvider, compact_summary as _fund_summary
    _FUND_AVAILABLE = True
except Exception:
    _FUND_AVAILABLE = False

try:
    from utils import to_float as _f
except Exception:
    def _f(v, default=0.0):
        try: return float(v) if v not in (None, "", "N/A") else default
        except Exception: return default

# ── Config ─────────────────────────────────────────────────────────────────
DEFAULT_ACCOUNT_SIZE = 1_000_000   # ₹10 lakh
DEFAULT_RISK_PCT     = 0.01        # 1% risk per trade
CURRENCY_SYMBOL      = "₹"

SETUP_LABELS = {
    "VCP":               "📈 VCP Breakout",
    "RANGE_EXPANSION":   "🚀 Range Expansion",
    "MEAN_REVERSION":    "🔄 Mean Reversion",
    "BREAKOUT_PULLBACK": "🎯 First Pullback",
    "BREAKOUT":          "⚡ Breakout",
}

SETUP_COLORS = {
    "VCP":               "#6366f1",
    "RANGE_EXPANSION":   "#f59e0b",
    "BREAKOUT_PULLBACK": "#22c55e",
    "MEAN_REVERSION":    "#06b6d4",
    "BREAKOUT":          "#8b5cf6",
}

SETUP_ORDER = {"VCP": 0, "RANGE_EXPANSION": 1, "BREAKOUT_PULLBACK": 2, "MEAN_REVERSION": 3, "BREAKOUT": 4}

LIST_COLORS = {
    "OPEN_TRADE": "#22c55e",
    "WATCHLIST":  "#f59e0b",
    "BREAKOUT":   "#8b5cf6",
    "PORTFOLIO":  "#06b6d4",
}

BEST_BUY_NOTES = {
    "VCP":               "Buy above pivot on volume ≥1.5× avg; stop below base low",
    "RANGE_EXPANSION":   "Buy open of next session after wide-range candle clears base",
    "MEAN_REVERSION":    "Buy as price reclaims SMA20 / bounces lower BB; stop 2×ATR below",
    "BREAKOUT_PULLBACK": "Buy pullback to BO support on dry-up volume; stop below BO level",
    "BREAKOUT":          "Buy on confirmation close above prior high; stop below swing low",
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _shares(entry, sl, account, risk_pct):
    risk = entry - sl
    if risk <= 0 or entry <= 0: return 0
    return max(1, int(math.floor(account * risk_pct / risk)))


def _rr_str(entry, sl, t1):
    risk = entry - sl
    if risk <= 0: return "—"
    return f"{(t1 - entry)/risk:.1f}R"


def _days_since(date_str) -> int | None:
    try:
        d0 = datetime.fromisoformat(str(date_str)).date()
        return (date.today() - d0).days
    except Exception:
        return None


def _pct_gain(entry, close) -> float | None:
    try:
        if entry and close and float(entry) > 0:
            return round((float(close) - float(entry)) / float(entry) * 100, 2)
    except Exception:
        pass
    return None


def _dist_badge(dist: float) -> str:
    if dist <= 0:   color, label = "#22c55e", f"{dist:+.1f}% AT"
    elif dist <= 2: color, label = "#22c55e", f"+{dist:.1f}%"
    elif dist <= 5: color, label = "#f59e0b", f"+{dist:.1f}%"
    else:           color, label = "#ef4444", f"+{dist:.1f}% ext"
    return f"<span style='color:{color}'>{label}</span>"


def _rating_css(r):
    return {"A+":"#16a34a","A":"#22c55e","B":"#f59e0b","C":"#f97316","D":"#ef4444"}.get((r or "").upper(), "#94a3b8")


def _chart_links(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if sym.endswith(".NS"):
        tv = f"NSE:{sym[:-3]}"
    elif sym.endswith(".BO"):
        tv = f"BSE:{sym[:-3]}"
    else:
        tv = sym
    yf_url = f"https://finance.yahoo.com/quote/{html.escape(sym)}/chart"
    tv_url = f"https://www.tradingview.com/chart/?symbol={html.escape(tv)}"
    fin_url = f"https://finance.yahoo.com/quote/{html.escape(sym)}/financials"
    stat_url = f"https://finance.yahoo.com/quote/{html.escape(sym)}/key-statistics"
    return (
        f"<a href='{yf_url}' target='_blank' title='Yahoo Chart'>📈YF</a> "
        f"<a href='{tv_url}' target='_blank' title='TradingView Chart'>📊TV</a> "
        f"<a href='{stat_url}' target='_blank' title='Key Stats'>📋</a> "
        f"<a href='{fin_url}' target='_blank' title='Financials'>💰</a>"
    )



# ── Load all LATEST JSON outputs ────────────────────────────────────────────

def load_all_latest(output_dir: Path) -> list[dict]:
    patterns = [
        ("india", "daily"),
        ("india", "weekly"),
        ("us",    "daily"),
        ("us",    "weekly"),
    ]
    # (file_glob_prefix, list_type_tag)
    file_types = [
        ("vcp_hits",           "BREAKOUT"),
        ("open_trades",        "OPEN_TRADE"),
        ("watchlist",          "WATCHLIST"),
        ("portfolio_shortlist","PORTFOLIO"),
    ]
    seen: set[tuple] = set()
    all_rows: list[dict] = []

    for market, tf in patterns:
        for prefix, default_list_type in file_types:
            for suffix in ("full", None):
                if suffix:
                    p = output_dir / f"{prefix}_{market}_{tf}_{suffix}_LATEST.json"
                else:
                    p = output_dir / f"{prefix}_{market}_{tf}_LATEST.json"
                if not p.exists():
                    continue
                try:
                    rows = json.loads(p.read_text(encoding="utf-8"))
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        sym   = str(row.get("symbol", ""))
                        setup = str(row.get("setup", "")).upper()
                        lt    = str(row.get("listType", default_list_type)).upper()
                        key   = (sym, setup, lt, market, tf)
                        if key in seen:
                            continue
                        seen.add(key)
                        row["_market"]    = market
                        row["_timeframe"] = tf
                        row["_listType"]  = lt
                        row["_source"]    = p.name
                        all_rows.append(row)
                except Exception:
                    continue
    return all_rows


# ── Build the HTML report ────────────────────────────────────────────────────

def build_master_report(
    output_dir: Path,
    account_size: float,
    risk_pct: float,
    cache_dir: Path,
    skip_fundamentals: bool,
) -> str:
    rows = load_all_latest(output_dir)
    if not rows:
        return "<h2 style='color:#f87171;padding:40px'>No scan output found. Run the scan first.</h2>"

    # ── Recalculate position sizes ─────────────────────────────────────────
    for row in rows:
        entry = _f(row.get("entry"))
        sl    = _f(row.get("sl"))
        if entry > 0 and sl > 0 and entry > sl:
            row["_shares"]   = _shares(entry, sl, account_size, risk_pct)
            row["_pos_val"]  = round(row["_shares"] * entry)
            row["_risk_amt"] = round(row["_shares"] * (entry - sl))
            row["_rr"]       = _rr_str(entry, sl, _f(row.get("T1")))
        else:
            row["_shares"]   = 0
            row["_pos_val"]  = 0
            row["_risk_amt"] = 0
            row["_rr"]       = "—"

        # Breakout performance
        bd = row.get("breakoutDate") or row.get("abfpBreakoutDate") or row.get("date")
        row["_days_held"] = _days_since(bd) if bd else None
        row["_pct_gain"]  = _pct_gain(row.get("entry"), row.get("close"))

    # ── Fetch fundamentals ─────────────────────────────────────────────────
    if _FUND_AVAILABLE and not skip_fundamentals:
        syms = list({r.get("symbol","") for r in rows if r.get("symbol")})
        fp = FundamentalsProvider(cache_dir=str(cache_dir))
        fund_data = fp.fetch_batch(syms, workers=20, show_progress=True)
        for row in rows:
            sym = row.get("symbol","")
            fd  = fund_data.get(sym, {})
            is_india = row.get("_market") == "india"
            row["_fund"]    = _fund_summary(fd, is_india=is_india) if fd else "—"
            row["_sector"]  = (fd or {}).get("sector") or "—"
            row["_mcap"]    = (fd or {}).get("market_cap")
            row["_pe"]      = (fd or {}).get("pe")
            row["_eps_yoy"] = (fd or {}).get("eps_yoy")
            row["_rev_yoy"] = (fd or {}).get("rev_yoy")
            row["_debt"]    = (fd or {}).get("debt_trend_pct")
    else:
        for row in rows:
            row["_fund"]    = row.get("fundSummary") or "—"
            row["_sector"]  = row.get("sector") or "—"
            row["_mcap"]    = row.get("marketCap")
            row["_pe"]      = None
            row["_eps_yoy"] = None
            row["_rev_yoy"] = None
            row["_debt"]    = None

    # ── Sort ───────────────────────────────────────────────────────────────
    LIST_ORDER = {"OPEN_TRADE": 0, "PORTFOLIO": 1, "WATCHLIST": 2, "BREAKOUT": 3}
    rows.sort(key=lambda r: (
        LIST_ORDER.get(r["_listType"], 9),
        SETUP_ORDER.get(r.get("setup","").upper(), 9),
        -_f(r.get("rankingScore") or r.get("watchlistQualityScore") or r.get("score") or 0),
    ))

    # ── Analytics ──────────────────────────────────────────────────────────
    now_str = datetime.now().strftime("%d %b %Y %H:%M")
    setup_counts:     dict[str, int] = {}
    list_type_counts: dict[str, int] = {}
    market_counts:    dict[str, int] = {}
    sector_counts:    dict[str, int] = {}
    scores = []
    for r in rows:
        s = r.get("setup","?").upper()
        setup_counts[s] = setup_counts.get(s, 0) + 1
        lt = r["_listType"]
        list_type_counts[lt] = list_type_counts.get(lt, 0) + 1
        m = r["_market"]
        market_counts[m] = market_counts.get(m, 0) + 1
        sec = r["_sector"] or "—"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        sc = _f(r.get("rankingScore") or r.get("watchlistQualityScore") or r.get("score") or 0)
        scores.append(sc)

    avg_score = sum(scores) / len(scores) if scores else 0
    top_score = max(scores) if scores else 0
    total_pos = sum(r["_pos_val"] for r in rows)
    total_risk = sum(r["_risk_amt"] for r in rows)
    open_trades = [r for r in rows if r["_listType"] == "OPEN_TRADE"]
    winning = [r for r in open_trades if (r["_pct_gain"] or 0) > 0]

    cur = CURRENCY_SYMBOL

    # ── Stat cards ─────────────────────────────────────────────────────────
    def _stat(label, value, sub=""):
        return f"<div class='stat-card'><div class='stat-label'>{label}</div><div class='stat-value'>{value}</div>{'<div class=stat-sub>'+sub+'</div>' if sub else ''}</div>"

    stats_html = "".join([
        _stat("Total Setups", len(rows)),
        _stat("Open Trades", list_type_counts.get("OPEN_TRADE",0), f"{len(winning)} winning"),
        _stat("Watchlist",   list_type_counts.get("WATCHLIST",0)+list_type_counts.get("PORTFOLIO",0), "ready-to-trade"),
        _stat("Breakout Signals", list_type_counts.get("BREAKOUT",0), "fresh triggers"),
        _stat("Avg Quality Score", f"{avg_score:.1f}", f"Top: {top_score:.1f}"),
        _stat("Total Position Value", f"{cur}{total_pos:,}", f"Risk deployed: {cur}{total_risk:,}"),
    ])

    # ── Setup / list type distribution bars ────────────────────────────────
    max_lt = max(list_type_counts.values()) if list_type_counts else 1
    _lc_def, _lc_fill = "#94a3b8", "#6366f1"
    lt_bars = "".join(
        f"<div class='bar-row'><span class='bar-lbl' style='color:{LIST_COLORS.get(lt, _lc_def)}'>{lt}</span>"
        f"<div class='bar-track'><div class='bar-fill' style='width:{cnt/max_lt*100:.0f}%;background:{LIST_COLORS.get(lt, _lc_fill)}'></div></div>"
        f"<span class='bar-cnt'>{cnt}</span></div>"
        for lt, cnt in sorted(list_type_counts.items())
    )

    max_sc = max(setup_counts.values()) if setup_counts else 1
    _sc_def = "#94a3b8"
    sc_bars = "".join(
        f"<div class='bar-row'><span class='bar-lbl' style='color:{SETUP_COLORS.get(s, _sc_def)}'>{SETUP_LABELS.get(s, s)}</span>"
        f"<div class='bar-track'><div class='bar-fill' style='width:{cnt/max_sc*100:.0f}%;background:{SETUP_COLORS.get(s, _lc_fill)}'></div></div>"
        f"<span class='bar-cnt'>{cnt}</span></div>"
        for s, cnt in sorted(setup_counts.items(), key=lambda x: SETUP_ORDER.get(x[0], 9))
    )

    top_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])[:10]
    sector_html = "".join(
        f"<div class='pie-row'><span>{sec}</span><span class='pie-cnt'>{cnt}</span></div>"
        for sec, cnt in top_sectors
    )

    # ── Build table rows ───────────────────────────────────────────────────
    # Filter dropdowns
    all_setups   = sorted(setup_counts.keys(), key=lambda x: SETUP_ORDER.get(x,9))
    all_markets  = sorted(market_counts.keys())
    all_tfs      = sorted({r["_timeframe"] for r in rows})
    all_lt       = sorted(list_type_counts.keys(), key=lambda x: LIST_ORDER.get(x,9))
    all_sectors  = sorted({r["_sector"] for r in rows if r["_sector"] and r["_sector"] != "—"})

    table_rows = ""
    for r in rows:
        setup    = (r.get("setup") or "").upper()
        lt       = r["_listType"]
        market   = r["_market"]
        tf       = r["_timeframe"]
        sym_raw  = r.get("symbol","")
        sym      = html.escape(sym_raw)
        rating   = (r.get("rating") or "").upper()
        score    = _f(r.get("rankingScore") or r.get("watchlistQualityScore") or r.get("score") or 0)
        q_score  = _f(r.get("score") or r.get("qualityScore") or 0)
        close_v  = _f(r.get("close"))
        pivot_v  = _f(r.get("pivot"))
        entry_v  = _f(r.get("entry"))
        sl_v     = _f(r.get("sl"))
        t1_v     = _f(r.get("T1"))
        t2_v     = _f(r.get("T2"))
        t3_v     = _f(r.get("T3"))
        entry_plan = html.escape(str(r.get("entryInstruction") or BEST_BUY_NOTES.get(setup, "—")))
        entry_trigger = html.escape(str(r.get("entryTriggerCondition") or "—"))
        trig_earnings = html.escape(str(r.get("triggerEarningsGrowth") or "—"))
        trig_debt = html.escape(str(r.get("triggerDebtReduction") or "—"))
        trig_macro = html.escape(str(r.get("triggerMacroTailwind") or "—"))
        trig_market = html.escape(str(r.get("triggerMarketTailwind") or "—"))
        trig_summary = html.escape(str(r.get("triggerSummary") or "—"))
        dist_v   = _f(r.get("dist%") or r.get("distFromPivot%") or 0)
        window   = r.get("window") or tf.upper()
        sector   = html.escape(r["_sector"] or "—")
        fund_raw = r["_fund"] or "—"
        fund_esc = html.escape(fund_raw)

        # Breakout performance
        pct_g = r.get("_pct_gain")
        days_h = r.get("_days_held")
        pct_g_str = f"{'+' if pct_g > 0 else ''}{pct_g:.1f}%" if pct_g is not None else "—"
        pct_g_color = "#22c55e" if (pct_g or 0) > 0 else ("#ef4444" if (pct_g or 0) < 0 else "#94a3b8")

        # Indicators
        rs     = r.get("rsScore") or "—"
        regime = (r.get("regimeSupport") or "—").upper()
        vol_du = r.get("volumeDryUpScore") or r.get("volumeDryUpRatio") or "—"
        weekly = r.get("weeklyAgreement") or "—"
        prox   = r.get("pivotProximityScore") or "—"
        fresh  = r.get("pivotFreshness") or "—"

        regime_color = {"STRONG":"#22c55e","FAVORABLE":"#22c55e","NEUTRAL":"#f59e0b","WEAK":"#ef4444","UNFAVORABLE":"#ef4444"}.get(regime,"#94a3b8")

        cur_sym = "₹" if market == "india" else "$"
        lt_color = LIST_COLORS.get(lt, "#94a3b8")
        sc_color = SETUP_COLORS.get(setup, "#94a3b8")
        rc = _rating_css(rating)

        table_rows += (
            f"<tr data-symbol='{html.escape(sym_raw)}' data-setup='{setup}' data-lt='{lt}' "
            f"data-market='{market}' data-tf='{tf}' data-sector='{html.escape(r['_sector'] or '')}' "
            f"data-score='{score:.2f}' data-base-score='{score:.2f}' data-rating='{rating}'>\n"
            f"  <td class='col-sym'><b>{sym}</b><br><small style='color:#4a6070'>{market.upper()} {tf}</small></td>\n"
            f"  <td><span class='lt-badge' style='background:{lt_color}22;color:{lt_color};border:1px solid {lt_color}55'>{lt}</span></td>\n"
            f"  <td><span class='setup-badge' style='background:{sc_color}22;color:{sc_color};border:1px solid {sc_color}55'>{SETUP_LABELS.get(setup,setup)}</span></td>\n"
            f"  <td style='color:#79c0ff;font-size:0.82em'>{html.escape(window)}</td>\n"
            f"  <td style='color:{rc};font-weight:700'>{html.escape(rating)}</td>\n"
            f"  <td><span class='score-chip'>{q_score:.1f}</span></td>\n"
            f"  <td style='font-weight:600'>{score:.1f}</td>\n"
            f"  <td style='font-weight:600'>{cur_sym}{close_v:,.2f}</td>\n"
            f"  <td style='color:#6366f1;font-weight:700'>{cur_sym}{pivot_v:,.2f}</td>\n"
            f"  <td style='color:#22c55e;font-weight:700'>{cur_sym}{entry_v:,.2f}</td>\n"
            f"  <td style='color:#ef4444;font-weight:700'>{cur_sym}{sl_v:,.2f}</td>\n"
            f"  <td style='max-width:260px;white-space:normal;line-height:1.35'>{entry_plan}</td>\n"
            f"  <td style='max-width:240px;white-space:normal;line-height:1.35;color:#9ecbff'>{entry_trigger}</td>\n"
            f"  <td>{cur_sym}{t1_v:,.2f}</td>\n"
            f"  <td>{cur_sym}{t2_v:,.2f}</td>\n"
            f"  <td>{cur_sym}{t3_v:,.2f}</td>\n"
            f"  <td style='font-weight:700'>{r['_rr']}</td>\n"
            f"  <td style='max-width:220px;white-space:normal;line-height:1.35'>{trig_earnings}</td>\n"
            f"  <td style='max-width:220px;white-space:normal;line-height:1.35'>{trig_debt}</td>\n"
            f"  <td style='max-width:160px;white-space:normal;line-height:1.35'>{trig_macro}</td>\n"
            f"  <td style='max-width:160px;white-space:normal;line-height:1.35'>{trig_market}</td>\n"
            f"  <td style='max-width:260px;white-space:normal;line-height:1.35;color:#94a3b8'>{trig_summary}</td>\n"
            f"  <td>{_dist_badge(dist_v)}</td>\n"
            f"  <td style='color:{pct_g_color};font-weight:700'>{pct_g_str}</td>\n"
            f"  <td style='color:#94a3b8'>{days_h if days_h is not None else '—'}</td>\n"
            f"  <td style='color:#22c55e;font-weight:600'>{r['_shares']:,}</td>\n"
            f"  <td>{cur_sym}{r['_pos_val']:,}</td>\n"
            f"  <td style='color:#ef4444'>{cur_sym}{r['_risk_amt']:,}</td>\n"
            f"  <td style='font-size:0.78em;color:#8b949e'>{html.escape(str(rs))}</td>\n"
            f"  <td style='color:{regime_color};font-size:0.78em;font-weight:600'>{html.escape(regime)}</td>\n"
            f"  <td style='font-size:0.78em;color:#8b949e'>{html.escape(str(vol_du))}</td>\n"
            f"  <td style='font-size:0.78em;color:#8b949e'>{html.escape(str(weekly))}</td>\n"
            f"  <td style='font-size:0.78em;color:#8b949e'>{html.escape(str(prox))}</td>\n"
            f"  <td style='font-size:0.78em;color:#8b949e'>{html.escape(str(fresh))}</td>\n"
            f"  <td style='color:#79c0ff;font-size:0.78em'>{sector}</td>\n"
            f"  <td class='fund-cell' data-auto='{fund_esc}'>"
            f"<button class='fund-btn' onclick=\"openFundCard(this,'{html.escape(sym_raw)}')\""
            f" title='Edit fundamentals notes &amp; score'>📊</button>"
            f"<span class='fund-snip'>{fund_esc[:55]}{'…' if len(fund_esc)>55 else ''}</span></td>\n"
            f"  <td class='col-links'>{_chart_links(sym_raw)}</td>\n"
            f"</tr>\n"
        )

    # ── Table headers ──────────────────────────────────────────────────────
    headers = [
        ("Symbol",          "Stock ticker symbol and market"),
        ("List Type",       "OPEN_TRADE=active position, WATCHLIST=candidate, BREAKOUT=fresh signal, PORTFOLIO=shortlisted"),
        ("Setup",           "Pattern: VCP, Range Expansion, Mean Reversion, Breakout Pullback"),
        ("Window",          "Analysis timeframe (WEEKLY, DAILY, WEEK(N))"),
        ("Rating",          "A+=elite, A=strong, B=moderate, C=marginal, D=weak"),
        ("Quality Score",   "Composite score 0-100: contraction + volume + timing"),
        ("Rank Score",      "Weighted sort score = Quality + MTF bonus + proximity bonus"),
        ("Close",           "Most recent closing price"),
        ("Pivot",           "Key breakout/support level price"),
        ("Entry",           "Recommended entry price"),
        ("Stop Loss",       "Stop-loss price. Risk = Entry - Stop"),
        ("Entry Plan",      "When to act: breakout confirmation, watchlist alert, or open-trade management guidance"),
        ("Entry Trigger",   "Specific event that confirms the entry is valid"),
        ("T1 (1R)",         "Target 1: 1R profit. First scale-out point"),
        ("T2 (2R)",         "Target 2: 2R profit"),
        ("T3 (3R)",         "Target 3: 3R profit. Trail stop here"),
        ("R:R",             "Risk-to-reward ratio at T1 (e.g. 2.5R means reward is 2.5x risk)"),
        ("Earnings Trigger", "Segregated catalyst bucket for earnings or revenue acceleration"),
        ("Debt Trigger",    "Segregated catalyst bucket for debt reduction / balance-sheet improvement"),
        ("Macro Trigger",   "Macro tailwind/headwind context for the setup"),
        ("Market Trigger",  "Market-structure and relative-strength tailwind bucket"),
        ("Trigger Summary", "Combined catalyst summary across earnings, debt, macro, and market"),
        ("Dist Pivot",      "Current price distance above (+) or below (-) the pivot level"),
        ("% Gain",          "% gain/loss since entry date (positive=winning trade)"),
        ("Days Held",       "Calendar days since the breakout/entry date"),
        ("Shares",          f"Position size for {cur}10L portfolio @1% risk"),
        ("Pos Value",       "Total position value in portfolio currency"),
        ("Risk Amount",     "Max risk on this trade (Shares × Risk/share)"),
        ("RS Score",        "Relative Strength vs index benchmark. Higher=outperforming"),
        ("Regime",          "Market regime: STRONG=best for breakouts, NEUTRAL=selective, WEAK=avoid"),
        ("Vol Dry-Up",      "Volume contraction score into pivot (higher=better coiling)"),
        ("Weekly Align",    "Whether weekly chart agrees with entry timeframe signal"),
        ("Pivot Prox",      "Proximity to pivot (100=at pivot, lower=extended)"),
        ("Freshness",       "FRESH=just formed, ACTIVE=holding, RETESTED=confirmed support"),
        ("Sector",          "Company sector from fundamentals data"),
        ("Fundamentals ✏️", "Click 📊 to add earnings notes, debt trend, sector tailwinds. Score boosts rank."),
        ("Charts",          "Yahoo Finance and TradingView chart links"),
    ]
    th_html = "".join(
        f"<th onclick='sortTable({i})' title='{desc}'>{label}</th>"
        for i, (label, desc) in enumerate(headers)
    )

    # ── Filter dropdowns ───────────────────────────────────────────────────
    def _opts(vals):
        return "".join(f"<option value='{html.escape(v)}'>{html.escape(v)}</option>" for v in vals)


    # ── Assemble HTML ──────────────────────────────────────────────────────
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 Master Setup Report — {now_str}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#0f172a; color:#e2e8f0; }}
.header {{ background:linear-gradient(135deg,#1e3a5f 0%,#0f172a 100%); padding:20px 32px; border-bottom:1px solid #1e293b; }}
.header h1 {{ font-size:1.5em; font-weight:800; color:#f8fafc; }}
.header p  {{ color:#94a3b8; font-size:0.85em; margin-top:4px; }}
.stat-grid {{ display:flex; gap:12px; flex-wrap:wrap; padding:14px 32px; background:#0f172a; border-bottom:1px solid #1e293b; }}
.stat-card {{ background:#1e293b; border-radius:10px; padding:12px 18px; min-width:140px; }}
.stat-label {{ font-size:0.72em; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }}
.stat-value {{ font-size:1.35em; font-weight:800; color:#f1f5f9; }}
.stat-sub   {{ font-size:0.75em; color:#64748b; margin-top:2px; }}
.charts-row {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; padding:14px 32px; }}
.mini-chart {{ background:#1e293b; border-radius:8px; padding:12px; }}
.mini-chart h4 {{ color:#79c0ff; font-size:0.82em; font-weight:600; margin-bottom:8px; text-transform:uppercase; }}
.bar-row {{ display:flex; gap:8px; align-items:center; margin-bottom:5px; font-size:0.78em; }}
.bar-lbl  {{ min-width:120px; color:#8b949e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.bar-track {{ flex:1; height:14px; background:#0f172a; border-radius:3px; overflow:hidden; }}
.bar-fill  {{ height:100%; border-radius:3px; }}
.bar-cnt   {{ min-width:28px; text-align:right; color:#f1f5f9; font-weight:600; }}
.pie-row   {{ display:flex; justify-content:space-between; padding:3px 0; font-size:0.78em; border-bottom:1px solid #1e293b; }}
.pie-cnt   {{ color:#22c55e; font-weight:600; }}
.filters   {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; padding:12px 32px; background:#0a1323; border-bottom:1px solid #1e293b; position:sticky; top:0; z-index:20; backdrop-filter:blur(4px); }}
.filters label {{ color:#94a3b8; font-size:0.8em; white-space:nowrap; }}
select,input {{ background:#1e293b; border:1px solid #334155; color:#e2e8f0; padding:5px 8px; border-radius:6px; font-size:0.82em; }}
.btn {{ padding:5px 12px; border-radius:6px; border:1px solid #334155; background:transparent; color:#7dd3fc; cursor:pointer; font-size:0.82em; }}
.btn:hover {{ background:#1e3a5f; }}
.btn-green {{ color:#4ade80; }}
.col-legend {{ padding:10px 32px; border-bottom:1px solid #1e293b; }}
.legend-toggle {{ background:none; border:none; color:#58a6ff; cursor:pointer; font-size:0.82em; font-weight:600; padding:0; }}
.legend-body {{ display:none; padding-top:8px; }}
.legend-body.open {{ display:block; }}
.legend-body dl {{ display:grid; grid-template-columns:160px 1fr; gap:3px 12px; font-size:0.77em; max-width:1400px; }}
.legend-body dt {{ color:#79c0ff; font-weight:600; padding-top:2px; }}
.legend-body dd {{ color:#64748b; margin:0; padding-top:2px; border-bottom:1px solid #1a2233; }}
.table-wrap {{ overflow-x:auto; padding:0 16px 60px; }}
table {{ border-collapse:collapse; width:100%; font-size:0.80em; min-width:2800px; }}
th {{ background:#111827; color:#7dd3fc; padding:8px 10px; text-align:left; font-size:0.75em; text-transform:uppercase; letter-spacing:0.4px; cursor:pointer; white-space:nowrap; position:sticky; top:47px; z-index:10; user-select:none; border-bottom:2px solid #1e293b; }}
th:hover {{ color:#f1f5f9; }}
th::after {{ content:' ↕'; font-size:0.7em; opacity:0.3; }}
th.sort-asc::after {{ content:' ↑'; opacity:1; }}
th.sort-desc::after {{ content:' ↓'; opacity:1; }}
td {{ padding:8px 10px; border-bottom:1px solid #1e293b; vertical-align:middle; white-space:nowrap; }}
tr:hover td {{ background:#1e293b44; }}
.col-sym {{ min-width:130px; }}
.col-links {{ white-space:nowrap; }}
.col-links a {{ color:#60a5fa; text-decoration:none; margin-right:5px; font-size:0.82em; }}
.lt-badge {{ border-radius:12px; padding:2px 8px; font-size:0.74em; font-weight:700; white-space:nowrap; }}
.setup-badge {{ border-radius:6px; padding:2px 8px; font-size:0.74em; white-space:nowrap; }}
.score-chip {{ background:#0f1b2a; border:1px solid #2f445a; border-radius:6px; padding:1px 7px; color:#a5d6ff; }}
.hidden {{ display:none; }}
#rowCount {{ color:#64748b; font-size:0.82em; padding:6px 32px; }}
/* Fundamentals Card */
.fund-cell {{ text-align:left; min-width:130px; }}
.fund-btn  {{ background:none; border:1px solid #2a3f5a; border-radius:5px; color:#58a6ff; cursor:pointer; padding:2px 7px; font-size:0.80em; margin-right:4px; transition:background 0.2s; }}
.fund-btn:hover {{ background:#1f6feb22; }}
.fund-btn.has-notes {{ border-color:#3fb95099; color:#7ee787; }}
.fund-btn.score-high {{ background:#23863622; }}
.fund-btn.score-mid  {{ background:#9e6a0322; }}
.fund-btn.score-low  {{ background:#da363322; }}
.fund-snip {{ font-size:0.70em; color:#4a6070; display:inline-block; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; vertical-align:middle; }}
.e-pill {{ display:inline-block; background:#1e2f4a; border:1px solid #2f445a; border-radius:5px; padding:1px 5px; color:#79c0ff; font-size:0.70em; margin-left:3px; }}
.fund-overlay {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,.6); z-index:998; }}
.fund-card {{ display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); z-index:999; background:#111926; border:1px solid #30363d; border-radius:14px; padding:22px; width:480px; max-width:95vw; max-height:92vh; overflow-y:auto; box-shadow:0 20px 60px rgba(0,0,0,.75); }}
.fund-card h3 {{ color:#9ecbff; font-size:1em; margin:0 0 4px; }}
.fund-sym-lbl {{ color:#7ee787; font-weight:700; font-size:1.1em; }}
.auto-box {{ background:#0d1117; border:1px solid #21262d; border-radius:6px; padding:8px; font-size:0.76em; color:#6e7f8d; margin:8px 0 12px; word-break:break-word; }}
.fund-card label {{ color:#8b949e; font-size:0.80em; display:block; margin-top:8px; margin-bottom:2px; font-weight:600; }}
.fund-card textarea {{ width:100%; background:#0d1117; border:1px solid #30363d; border-radius:6px; color:#c9d1d9; padding:7px; font-size:0.80em; resize:vertical; min-height:42px; font-family:inherit; }}
.fund-card textarea:focus {{ border-color:#58a6ff; outline:none; }}
.score-row {{ display:flex; align-items:center; gap:10px; margin-top:10px; }}
.score-row input {{ flex:1; }}
.score-badge {{ background:#0f1b2a; border:1px solid #2f445a; border-radius:6px; padding:3px 10px; color:#f2cc60; font-weight:700; font-size:1em; min-width:36px; text-align:center; }}
.score-prev {{ color:#79c0ff; font-size:0.80em; margin-top:5px; }}
.btn-row {{ display:flex; gap:8px; margin-top:12px; }}
.save-btn {{ flex:1; background:#1f6feb; color:#fff; border:none; border-radius:7px; padding:7px; cursor:pointer; font-weight:700; font-size:0.88em; }}
.save-btn:hover {{ background:#388bfd; }}
.close-btn {{ background:transparent; color:#8b949e; border:1px solid #30363d; border-radius:7px; padding:7px 14px; cursor:pointer; font-size:0.88em; }}
.clear-btn {{ background:transparent; color:#f85149; border:1px solid #da363322; border-radius:7px; padding:7px 10px; cursor:pointer; font-size:0.82em; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 Master Setup Report — All Markets &amp; Timeframes</h1>
  <p>Generated {now_str} &nbsp;|&nbsp; Portfolio: {cur}{account_size:,.0f} &nbsp;|&nbsp;
     Risk/Trade: {risk_pct*100:.0f}% = {cur}{account_size*risk_pct:,.0f} &nbsp;|&nbsp;
     {len(rows)} setups across {', '.join(all_markets).upper()}</p>
</div>

<div class="stat-grid">{stats_html}</div>

<div class="charts-row">
  <div class="mini-chart"><h4>📂 By List Type</h4>{lt_bars}</div>
  <div class="mini-chart"><h4>📈 By Setup</h4>{sc_bars}</div>
  <div class="mini-chart"><h4>🏭 Top Sectors</h4>{sector_html}</div>
</div>

<!-- Filters (sticky) -->
<div class="filters">
  <label>List Type:</label>
  <select id="fLT" onchange="applyFilters()"><option value="">All</option>{_opts(all_lt)}</select>
  <label>Setup:</label>
  <select id="fSetup" onchange="applyFilters()"><option value="">All</option>{_opts(all_setups)}</select>
  <label>Market:</label>
  <select id="fMarket" onchange="applyFilters()"><option value="">All</option>{_opts(all_markets)}</select>
  <label>Timeframe:</label>
  <select id="fTF" onchange="applyFilters()"><option value="">All</option>{_opts(all_tfs)}</select>
  <label>Rating:</label>
  <select id="fRating" onchange="applyFilters()">
    <option value="">All</option><option>A+</option><option>A</option><option>B</option><option>C</option>
  </select>
  <label>Sector:</label>
  <select id="fSector" onchange="applyFilters()"><option value="">All</option>{_opts(all_sectors)}</select>
  <label>Min Score:</label>
  <input type="number" id="fScore" value="0" min="0" max="100" step="5" onchange="applyFilters()" style="width:60px">
  <label>Symbol:</label>
  <input type="text" id="fSym" placeholder="Search…" oninput="applyFilters()" style="width:110px">
  <button class="btn btn-green" onclick="resetFilters()">↺ Reset</button>
  <button class="btn" onclick="exportCSV()">📥 CSV</button>
</div>
<div id="rowCount"></div>

<!-- Column Legend -->
<div class="col-legend">
  <button class="legend-toggle" onclick="document.getElementById('legendBody').classList.toggle('open')">
    📖 Column Guide — hover any header for tooltip, or click here to see all {len(headers)} column definitions
  </button>
  <div class="legend-body" id="legendBody">
    <dl>
      {''.join(f'<dt>{label}</dt><dd>{desc}</dd>' for label, desc in headers)}
    </dl>
  </div>
</div>


<!-- Fund Card Modal -->
<div class="fund-overlay" id="fundOverlay" onclick="closeFundCard()"></div>
<div class="fund-card" id="fundCard">
  <h3>📊 Fundamentals — <span class="fund-sym-lbl" id="fCardSym"></span></h3>
  <div class="auto-box" id="fCardAuto">—</div>
  <label>📈 Earnings Growth (EPS / Revenue trend):</label>
  <textarea id="fEarnings" placeholder="e.g. EPS +35% YoY; Rev +22% YoY; margins expanding…" rows="2"></textarea>
  <label>💳 Debt / Balance Sheet:</label>
  <textarea id="fDebt" placeholder="e.g. D/E ratio falling; net cash positive; debt paid down…" rows="2"></textarea>
  <label>🌊 Sector Tailwinds:</label>
  <textarea id="fTailwinds" placeholder="e.g. Pharma US tariff benefit; capex cycle revival; China+1…" rows="2"></textarea>
  <label>🚀 Major Triggers / Catalysts:</label>
  <textarea id="fTriggers" placeholder="e.g. Order win Rs500Cr; new product launch; guidance raised…" rows="2"></textarea>
  <div class="score-row">
    <label style="margin:0;min-width:150px;font-weight:600">Fundamentals Score (1-10):</label>
    <input type="range" id="fScore2" min="1" max="10" value="5">
    <div class="score-badge" id="fScoreDisp">5</div>
  </div>
  <div class="score-prev" id="fScorePrev"></div>
  <div class="btn-row">
    <button class="save-btn" onclick="saveFund()">💾 Save to Browser</button>
    <button class="clear-btn" onclick="clearFund()">🗑 Clear</button>
    <button class="close-btn" onclick="closeFundCard()">✕ Close</button>
  </div>
  <p style="font-size:0.70em;color:#4a6070;margin-top:8px">Saved in browser per symbol. Enhanced Score = Base×(1+(S-1)×1.5%)</p>
</div>

<div class="table-wrap">
<table id="masterTable">
<thead><tr>{th_html}</tr></thead>
<tbody id="tbody">{table_rows}</tbody>
</table>
</div>

<script>
const ROWS = Array.from(document.querySelectorAll('#tbody tr'));
let sortDir = -1, sortCol = 6;
const FUND = 'mr2_fund_';
let _fSym = null;

function applyFilters() {{
  const lt     = document.getElementById('fLT').value;
  const setup  = document.getElementById('fSetup').value;
  const mkt    = document.getElementById('fMarket').value;
  const tf     = document.getElementById('fTF').value;
  const rat    = document.getElementById('fRating').value;
  const sec    = document.getElementById('fSector').value;
  const minSc  = parseFloat(document.getElementById('fScore').value) || 0;
  const sym    = document.getElementById('fSym').value.toUpperCase();
  let vis = 0;
  ROWS.forEach(tr => {{
    const d = tr.dataset;
    const sc = parseFloat(d.score) || 0;
    const nm = (d.symbol || '').toUpperCase();
    const ok = (!lt||d.lt===lt) && (!setup||d.setup===setup) && (!mkt||d.market===mkt)
            && (!tf||d.tf===tf) && (!rat||d.rating===rat) && (!sec||d.sector===sec)
            && sc >= minSc && (!sym||nm.includes(sym));
    tr.classList.toggle('hidden', !ok);
    if (ok) vis++;
  }});
  document.getElementById('rowCount').textContent = 'Showing ' + vis + ' of {len(rows)} setups';
}}

function resetFilters() {{
  ['fLT','fSetup','fMarket','fTF','fRating','fSector'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('fScore').value = 0;
  document.getElementById('fSym').value = '';
  applyFilters();
}}

function sortTable(col) {{
  if (sortCol === col) sortDir *= -1; else {{ sortCol = col; sortDir = -1; }}
  document.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
  document.querySelectorAll('th')[col].classList.add(sortDir === -1 ? 'sort-desc' : 'sort-asc');
  const tbody = document.getElementById('tbody');
  // Sort ALL rows (including hidden) so filter+sort always gives correct order
  ROWS.sort((a,b) => {{
    const av = a.cells[col]?.textContent.trim().replace(/[₹$,+%R]/g,'') || '';
    const bv = b.cells[col]?.textContent.trim().replace(/[₹$,+%R]/g,'') || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = (!isNaN(an)&&!isNaN(bn)) ? an-bn : av.localeCompare(bv);
    return cmp * sortDir;
  }});
  ROWS.forEach(r => tbody.appendChild(r));
}}

function exportCSV() {{
  const headers = [{','.join('"'+l+'"' for l,_ in headers)}];
  const visible = ROWS.filter(r => !r.classList.contains('hidden'));
  let csv = headers.join(',') + '\\n';
  visible.forEach(row => {{
    const cells = Array.from(row.cells).slice(0, headers.length).map(c => {{
      let t = c.textContent.trim().replace(/"/g,'""');
      return t.includes(',') || t.includes('"') ? '"' + t + '"' : t;
    }});
    csv += cells.join(',') + '\\n';
  }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {{type:'text/csv'}}));
  a.download = 'master_report_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}


// ── Fundamentals Card ────────────────────────────────────────────────────────
function openFundCard(btn, sym) {{
  _fSym = sym;
  const saved = JSON.parse(localStorage.getItem(FUND+sym)||'{{}}');
  const auto  = btn.closest('td').dataset.auto || '—';
  document.getElementById('fCardSym').textContent = sym;
  document.getElementById('fCardAuto').textContent = auto;
  document.getElementById('fEarnings').value  = saved.earnings  || '';
  document.getElementById('fDebt').value      = saved.debt      || '';
  document.getElementById('fTailwinds').value = saved.tailwinds || '';
  document.getElementById('fTriggers').value  = saved.triggers  || '';
  const sc = saved.score || 5;
  document.getElementById('fScore2').value = sc;
  document.getElementById('fScoreDisp').textContent = sc;
  _updatePrev(sym, sc);
  document.getElementById('fundOverlay').style.display='block';
  document.getElementById('fundCard').style.display='block';
  document.getElementById('fEarnings').focus();
}}
function _updatePrev(sym, sc) {{
  const row = document.querySelector('tr[data-symbol="'+sym+'"]');
  const base = row ? parseFloat(row.dataset.baseScore||row.dataset.score||0) : 0;
  const enh  = (base*(1+(sc-1)*0.015)).toFixed(1);
  document.getElementById('fScorePrev').textContent = 'Base '+base.toFixed(1)+' \u2192 Enhanced '+enh+' (+'+(((sc-1)*1.5).toFixed(0))+'%)';
}}
document.getElementById('fScore2').addEventListener('input', function() {{
  document.getElementById('fScoreDisp').textContent = this.value;
  if (_fSym) _updatePrev(_fSym, parseInt(this.value));
}});
function closeFundCard() {{
  document.getElementById('fundOverlay').style.display='none';
  document.getElementById('fundCard').style.display='none';
  _fSym=null;
}}
document.addEventListener('keydown', e => {{ if(e.key==='Escape') {{ closeFundCard(); }} }});
function saveFund() {{
  if (!_fSym) return;
  localStorage.setItem(FUND+_fSym, JSON.stringify({{
    earnings: document.getElementById('fEarnings').value.trim(),
    debt:     document.getElementById('fDebt').value.trim(),
    tailwinds:document.getElementById('fTailwinds').value.trim(),
    triggers: document.getElementById('fTriggers').value.trim(),
    score:    parseInt(document.getElementById('fScore2').value),
    updated:  new Date().toISOString().slice(0,10)
  }}));
  applyFundScores();
  const b = document.querySelector('.save-btn');
  if(b){{ b.textContent='\u2705 Saved!'; setTimeout(()=>b.textContent='\uD83D\uDCBE Save to Browser',1500); }}
  closeFundCard();
}}
function clearFund() {{
  if(!_fSym||!confirm('Clear notes for '+_fSym+'?')) return;
  localStorage.removeItem(FUND+_fSym);
  ['fEarnings','fDebt','fTailwinds','fTriggers'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('fScore2').value=5;
  document.getElementById('fScoreDisp').textContent='5';
  applyFundScores(); closeFundCard();
}}
function applyFundScores() {{
  ROWS.forEach(row => {{
    const sym = row.dataset.symbol; if(!sym) return;
    const saved = JSON.parse(localStorage.getItem(FUND+sym)||'{{}}');
    const sc = saved.score||0;
    const base = parseFloat(row.dataset.baseScore||row.dataset.score||0);
    const enh  = sc>0 ? base*(1+(sc-1)*0.015) : base;
    row.dataset.score = enh.toFixed(2);
    const btn = row.querySelector('.fund-btn'); if(!btn) return;
    btn.classList.remove('has-notes','score-high','score-mid','score-low');
    if(sc>=8) btn.classList.add('score-high');
    else if(sc>=5) btn.classList.add('score-mid');
    else if(sc>=1) btn.classList.add('score-low');
    if(saved.earnings||saved.debt||saved.tailwinds||saved.triggers) btn.classList.add('has-notes');
    let pill = btn.parentNode.querySelector('.e-pill');
    if(sc>0) {{
      if(!pill){{ pill=document.createElement('span'); pill.className='e-pill'; btn.after(pill); }}
      pill.textContent='\u2605'+sc+' \u2192 '+enh.toFixed(1);
    }} else if(pill) pill.remove();
  }});
}}
applyFundScores();
applyFilters();
</script>
</body>
</html>"""
    return html_doc


def main():
    p = argparse.ArgumentParser(description="Generate master report from all LATEST scan outputs")
    p.add_argument("--output-dir",         default=str(ROOT / "output"))
    p.add_argument("--cache-dir",          default=str(ROOT / "cache"))
    p.add_argument("--account-size",       type=float, default=DEFAULT_ACCOUNT_SIZE)
    p.add_argument("--risk-pct",           type=float, default=DEFAULT_RISK_PCT)
    p.add_argument("--skip-fundamentals",  action="store_true")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    cache_dir  = Path(args.cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═'*62}")
    print(f"  Master Report Generator")
    print(f"  Portfolio: {CURRENCY_SYMBOL}{args.account_size:,.0f}  Risk: {args.risk_pct*100:.0f}%/trade")
    print(f"  Output dir: {output_dir}")
    print(f"  Fundamentals: {'SKIP' if args.skip_fundamentals else 'ENABLED (yfinance)'}")
    print(f"{'═'*62}\n")

    html_content = build_master_report(
        output_dir=output_dir,
        account_size=args.account_size,
        risk_pct=args.risk_pct,
        cache_dir=cache_dir,
        skip_fundamentals=args.skip_fundamentals,
    )

    out_path = output_dir / "master_report_LATEST.html"
    # Sanitise any surrogate characters from malformed data before writing
    html_content = html_content.encode("utf-8", errors="replace").decode("utf-8")
    out_path.write_text(html_content, encoding="utf-8")
    print(f"\n  ✅ Master report → {out_path.resolve()}")
    print(f"  Open: file://{out_path.resolve()}")


if __name__ == "__main__":
    main()

