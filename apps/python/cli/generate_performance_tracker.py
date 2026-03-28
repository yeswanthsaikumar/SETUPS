#!/usr/bin/env python3
"""
generate_performance_tracker.py
────────────────────────────────
Generates a rich HTML "Performance Tracker" page showing how A / A+ rated
breakout setups from the last 14 days (2 weeks) are performing.

Each trade card shows:
  • Original scan data  (entry, stop, targets, setup, rating, regime at scan)
  • Live performance    (current price, % gain, days held, max gain, max drawdown)
  • Status badge        (OPEN / SL_HIT / T1_HIT / T2_HIT / T3_HIT / EXPIRED)
  • Still in scan flag  (🟢 or 🔴)
  • Price sparkline since trade date

Run:
    python3 apps/python/cli/generate_performance_tracker.py
    python3 apps/python/cli/generate_performance_tracker.py \
        --output-dir output --cache-dir cache \
        --markets india --timeframes daily,weekly
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

import performance_tracker as pt


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _f(v, d: float = 0.0) -> float:
    try:
        if v in (None, "", "N/A"):
            return d
        return float(str(v).strip().replace("%", "").replace(",", "").replace("x", ""))
    except Exception:
        return d


def _currency_sym(market: str) -> str:
    return "₹" if market == "india" else "$"


SECTOR_MAP = {
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking","AXISBANK":"Banking",
    "KOTAKBANK":"Banking","INDUSINDBK":"Banking","BANDHANBNK":"Banking","FEDERALBNK":"Banking",
    "IDFCFIRSTB":"Banking","AUBANK":"Banking","CANBK":"Banking","BANKBARODA":"Banking",
    "PNB":"Banking","UNIONBANK":"Banking","IDBI":"Banking","RBLBANK":"Banking",
    "TCS":"IT","INFY":"IT","WIPRO":"IT","HCLTECH":"IT","TECHM":"IT","LTIM":"IT",
    "MPHASIS":"IT","COFORGE":"IT","PERSISTENT":"IT","KPITTECH":"IT","OFSS":"IT",
    "HINDUNILVR":"FMCG","ITC":"FMCG","NESTLEIND":"FMCG","BRITANNIA":"FMCG",
    "DABUR":"FMCG","MARICO":"FMCG","COLPAL":"FMCG","GODREJCP":"FMCG",
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma","DIVISLAB":"Pharma",
    "TORNTPHARM":"Pharma","LUPIN":"Pharma","AUROPHARMA":"Pharma","ALKEM":"Pharma",
    "MARUTI":"Auto","TATAMOTORS":"Auto","HEROMOTOCO":"Auto","EICHERMOT":"Auto",
    "TVSMOTOR":"Auto","ASHOKLEY":"Auto","TIINDIA":"Auto","MOTHERSON":"Auto",
    "RELIANCE":"Energy","ONGC":"Energy","BPCL":"Energy","IOC":"Energy","HINDPETRO":"Energy",
    "GAIL":"Energy","COALINDIA":"Energy","ADANIGREEN":"Energy","NTPC":"Energy","POWERGRID":"Energy",
    "TATASTEEL":"Metals","HINDALCO":"Metals","JSWSTEEL":"Metals","SAIL":"Metals",
    "VEDL":"Metals","NMDC":"Metals","HINDZINC":"Metals","APLAPOLLO":"Metals",
    "ADANIENT":"Infra","ADANIPORTS":"Infra","L&T":"Infra","ADANIPOWER":"Infra",
    "BAJFINANCE":"NBFC","BAJAJFINSV":"NBFC","CHOLAFIN":"NBFC","M&MFIN":"NBFC",
    "MUTHOOTFIN":"NBFC","MANAPPURAM":"NBFC","LICHSGFIN":"NBFC","PFC":"NBFC","RECLTD":"NBFC",
    "TITAN":"Consumer","ASIANPAINT":"Consumer","PIDILITIND":"Consumer","HAVELLS":"Consumer",
    "VOLTAS":"Consumer","DIXON":"Consumer","CROMPTON":"Consumer",
    "NAUKRI":"Internet","ZOMATO":"Internet","PAYTM":"Internet","IRCTC":"Internet",
    "DLF":"RealEstate","GODREJPROP":"RealEstate","OBEROIRLTY":"RealEstate","PRESTIGE":"RealEstate",
    "SIEMENS":"Cap Goods","ABB":"Cap Goods","BHEL":"Cap Goods","BEL":"Cap Goods",
    "M&M":"Auto",
}

SETUP_META = {
    "VCP":               ("tag-vcp",  "VCP Breakout",       "Buy above pivot on volume ≥1.5× avg."),
    "RANGE_EXPANSION":   ("tag-rexp", "Range Expansion",    "Wide-range candle clears base with volume."),
    "MEAN_REVERSION":    ("tag-mr",   "Mean Reversion",     "Bounce from lower BB / SMA on RSI oversold."),
    "BREAKOUT_PULLBACK": ("tag-bp",   "Breakout Pullback",  "First pullback to prior breakout support."),
    "BREAKOUT":          ("tag-bo",   "Breakout",           "Confirmation close above prior high."),
}

STATUS_META = {
    "OPEN":     ("🟢", "status-open",    "Open"),
    "SL_HIT":   ("🔴", "status-sl",      "SL Hit"),
    "T1_HIT":   ("🎯", "status-t1",      "T1 Hit"),
    "T2_HIT":   ("🎯🎯", "status-t2",    "T2 Hit"),
    "T3_HIT":   ("🎯🎯🎯", "status-t3",  "T3 Hit"),
    "EXPIRED":  ("⏰", "status-expired", "Expired"),
}


def get_sector(symbol: str) -> str:
    base = symbol.replace(".NS", "").replace(".BO", "")
    return SECTOR_MAP.get(base, "Other")


def sparkline_svg(closes: list[float], entry: float, sl: float, t1: float,
                  width: int = 120, height: int = 44) -> str:
    if not closes or len(closes) < 2:
        return f'<svg width="{width}" height="{height}"><text x="5" y="22" fill="#555" font-size="10">N/A</text></svg>'

    all_vals = closes[:]
    refs = [v for v in [entry, sl, t1] if v and v > 0]
    all_vals += refs
    mn, mx = min(all_vals), max(all_vals)
    span = mx - mn if mx != mn else 1.0
    pad  = 5

    def _y(v: float) -> float:
        return pad + (1 - (v - mn) / span) * (height - 2 * pad)

    def _x(i: int) -> float:
        return pad + i / max(len(closes) - 1, 1) * (width - 2 * pad)

    pts = [f"{_x(i):.1f},{_y(v):.1f}" for i, v in enumerate(closes)]
    color       = "#3fb950" if closes[-1] >= closes[0] else "#f85149"
    fill_color  = "#3fb95022" if closes[-1] >= closes[0] else "#f8514922"
    fill_pts    = pts + [f"{_x(len(closes)-1):.1f},{pad + height - 2*pad:.1f}", f"{pad:.1f},{pad + height - 2*pad:.1f}"]

    lines = [
        f'<polygon points="{" ".join(fill_pts)}" fill="{fill_color}" stroke="none"/>',
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5"/>',
    ]
    # Horizontal reference lines
    if entry > 0 and mn <= entry <= mx:
        ey = _y(entry)
        lines.append(f'<line x1="{pad}" y1="{ey:.1f}" x2="{width-pad}" y2="{ey:.1f}" stroke="#58a6ff" stroke-width="0.8" stroke-dasharray="3,2" opacity="0.7"/>')
    if sl > 0 and mn <= sl <= mx:
        sy = _y(sl)
        lines.append(f'<line x1="{pad}" y1="{sy:.1f}" x2="{width-pad}" y2="{sy:.1f}" stroke="#f85149" stroke-width="0.8" stroke-dasharray="3,2" opacity="0.6"/>')
    if t1 > 0 and mn <= t1 <= mx:
        ty = _y(t1)
        lines.append(f'<line x1="{pad}" y1="{ty:.1f}" x2="{width-pad}" y2="{ty:.1f}" stroke="#3fb950" stroke-width="0.8" stroke-dasharray="3,2" opacity="0.6"/>')

    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            + "".join(lines)
            + "</svg>")


def _gain_cls(pct: float) -> str:
    if pct > 2.0:
        return "gain-up"
    if pct < -2.0:
        return "gain-dn"
    return "gain-flat"


def _fmt_pct(v: float, signed: bool = True) -> str:
    if abs(v) < 0.01:
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _progress_bar(entry: float, sl: float, t1: float, current: float) -> str:
    """Returns HTML for a small progress bar from SL → Entry → T1."""
    if not (sl > 0 and entry > 0 and t1 > 0 and entry > sl and t1 > entry):
        return ""
    total_range = t1 - sl
    if total_range <= 0:
        return ""
    pct = min(100, max(0, (current - sl) / total_range * 100))
    entry_pct = (entry - sl) / total_range * 100
    color = "#3fb950" if current >= entry else "#f85149"
    return (f'<div class="progress-wrap">'
            f'<div class="progress-track">'
            f'<div class="progress-fill" style="width:{pct:.1f}%;background:{color}"></div>'
            f'<div class="progress-entry-marker" style="left:{entry_pct:.1f}%"></div>'
            f'</div>'
            f'<div class="progress-labels">'
            f'<span style="color:#f85149">SL</span>'
            f'<span style="color:#58a6ff">Entry</span>'
            f'<span style="color:#3fb950">T1</span>'
            f'</div>'
            f'</div>')


def build_trade_card(trade: dict) -> str:
    sym         = trade.get("symbol", "")
    market      = trade.get("market", "india")
    timeframe   = trade.get("timeframe", "daily")
    setup       = trade.get("setup", "")
    rating      = trade.get("rating", "")
    window      = trade.get("window", "")
    trade_date  = trade.get("tradeDate", "")
    entry       = _f(trade.get("entry"))
    sl          = _f(trade.get("stopLoss"))
    t1          = _f(trade.get("target1"))
    t2          = _f(trade.get("target2"))
    t3          = _f(trade.get("target3"))
    pivot       = _f(trade.get("pivot"))
    score       = _f(trade.get("score"))
    current     = _f(trade.get("currentPrice", entry))
    gain_pct    = _f(trade.get("gainPct"))
    max_gain    = _f(trade.get("maxGain"))
    min_gain    = _f(trade.get("minGain"))
    days_held   = int(_f(trade.get("daysHeld")))
    status      = trade.get("status", "OPEN")
    still_in    = trade.get("stillInScan", False)
    sl_hit      = trade.get("slHit", False)
    t1_hit      = trade.get("target1Hit", False)
    t2_hit      = trade.get("target2Hit", False)
    t3_hit      = trade.get("target3Hit", False)
    regime      = trade.get("regimeAtScan", "")
    rs3m        = _f(trade.get("rs3mAtScan"))
    rs6m        = _f(trade.get("rs6mAtScan"))
    fund_sum    = escape(trade.get("fundSummary", "") or "—")
    entry_instr = escape(trade.get("entryInstruction", "") or "—")
    sparkline   = trade.get("sparkline", [])
    sector      = get_sector(sym)
    cur_sym     = _currency_sym(market)

    setup_cls, setup_label, setup_tip = SETUP_META.get(
        setup, ("tag-bo", setup.replace("_", " "), "")
    )
    status_icon, status_cls, status_label = STATUS_META.get(
        status, ("❓", "status-open", status)
    )
    tf_label    = timeframe.upper()
    rating_cls  = "rat-aplus" if rating == "A+" else "rat-a" if rating == "A" else "rat-b"
    gain_cls    = _gain_cls(gain_pct)
    svg         = sparkline_svg(sparkline, entry, sl, t1)

    regime_cls  = ("reg-fav"   if "FAV" in regime.upper() and "UNFAV" not in regime.upper()
                   else "reg-unfav" if "UNFAV" in regime.upper()
                   else "reg-neu")
    regime_str  = ("Favorable" if "FAV" in regime.upper() and "UNFAV" not in regime.upper()
                   else "Unfavorable" if "UNFAV" in regime.upper()
                   else regime or "—")

    rs3m_cls = "rpl" if rs3m > 0 else ("rmi" if rs3m < 0 else "rna")
    rs6m_cls = "rpl" if rs6m > 0 else ("rmi" if rs6m < 0 else "rna")

    width_pct   = min(score, 130) / 130 * 100
    score_color = "#3fb950" if score >= 100 else "#e3b341" if score >= 70 else "#f85149"

    # Risk / risk-reward
    risk = entry - sl if entry > sl > 0 else entry * 0.03
    rr_t1 = round((t1 - entry) / risk, 2) if risk > 0 and t1 > entry else 0.0
    rr_t2 = round((t2 - entry) / risk, 2) if risk > 0 and t2 > entry else 0.0

    # Target hit badges
    t1_badge = "✅" if t1_hit else ("🎯" if current >= t1 > 0 else "⬜")
    t2_badge = "✅" if t2_hit else ("🎯" if current >= t2 > 0 else "⬜")
    t3_badge = "✅" if t3_hit else ("🎯" if current >= t3 > 0 else "⬜")

    prog_bar    = _progress_bar(entry, sl, t1, current)
    still_html  = ('<span class="still-yes">📌 In Scan</span>' if still_in
                   else '<span class="still-no">📤 Left Scan</span>')

    return f"""
<div class="sig-card" data-symbol="{escape(sym)}" data-setup="{escape(setup)}"
     data-rating="{escape(rating)}" data-sector="{escape(sector)}"
     data-status="{escape(status)}" data-gain="{gain_pct:.2f}">
  <div class="sig-header">
    <div class="sig-left">
      <div class="sig-sym">{escape(sym.replace('.NS','').replace('.BO',''))}</div>
      <div class="sig-meta">
        <span class="badge-sec">{escape(sector)}</span>
        <span class="badge-tf">{tf_label}</span>
        <span class="{setup_cls} sig-tag" title="{escape(setup_tip)}">{escape(setup_label)}</span>
        <span class="{rating_cls} sig-tag">{escape(rating)}</span>
      </div>
    </div>
    <div class="sig-right">
      <div class="sig-sparkline">{svg}</div>
      <div class="score-bar-wrap" title="Score: {score:.1f}/130" style="width:100px;margin:4px 0 0">
        <div class="score-bar-fill" style="width:{width_pct:.0f}%;background:{score_color}"></div>
        <span class="score-label">Score {score:.1f}</span>
      </div>
    </div>
  </div>

  <!-- PERFORMANCE BAND -->
  <div class="perf-band">
    <div class="perf-row">
      <div class="perf-main">
        <span class="perf-entry">{cur_sym}{entry:.2f}</span>
        <span class="perf-arrow">→</span>
        <span class="perf-current {gain_cls}">{cur_sym}{current:.2f}</span>
        <span class="perf-gain {gain_cls}">{_fmt_pct(gain_pct)}</span>
      </div>
      <div class="perf-badges">
        <span class="{status_cls} status-badge">{status_icon} {status_label}</span>
        {still_html}
      </div>
    </div>
    <div class="perf-row perf-details">
      <span>📅 {escape(trade_date)} &bull; {days_held}d held</span>
      <span class="perf-range">
        Max: <span style="color:#3fb950">{_fmt_pct(max_gain)}</span>
        &nbsp;Min: <span style="color:#f85149">{_fmt_pct(min_gain)}</span>
      </span>
    </div>
    <div class="target-row">
      <span class="target-hit">T1 {t1_badge}</span>
      <span class="target-hit">T2 {t2_badge}</span>
      <span class="target-hit">T3 {t3_badge}</span>
      <span class="regime-inline {regime_cls}">Regime@scan: {escape(regime_str)}</span>
    </div>
    {prog_bar}
  </div>

  <!-- PLAN GRID (same as trade plans page) -->
  <div class="plan-grid">
    <div class="plan-section">
      <div class="plan-title">Entry Zone</div>
      <div class="plan-value entry-val">{cur_sym}{entry:.2f}</div>
      <div class="plan-sub">Pivot: {pivot:.2f} | Win: {window}</div>
    </div>
    <div class="plan-section">
      <div class="plan-title">Stop Loss{" ⚡" if sl_hit else ""}</div>
      <div class="plan-value {'sl-val-hit' if sl_hit else 'sl-val'}">{cur_sym}{sl:.2f}</div>
      <div class="plan-sub">Risk: {cur_sym}{max(entry-sl,0):.2f} ({max(entry-sl,0)/entry*100:.1f}%)</div>
    </div>
    <div class="plan-section highlight">
      <div class="plan-title">Targets &nbsp;<small>R:R</small></div>
      <div class="plan-value" style="font-size:.85em">
        <span class="{'t1-hit' if t1_hit else 't1-val'}">{cur_sym}{t1:.2f}</span>
        &nbsp;/&nbsp;
        <span class="{'t2-hit' if t2_hit else 't2-val'}">{cur_sym}{t2:.2f}</span>
        &nbsp;/&nbsp;
        <span class="{'t2-hit' if t3_hit else 't3-val'}">{cur_sym}{t3:.2f}</span>
      </div>
      <div class="plan-sub">T1 {rr_t1:.1f}R &nbsp;|&nbsp; T2 {rr_t2:.1f}R</div>
    </div>
  </div>

  <div class="sig-footer">
    <div class="sig-stat">
      <span class="sstat-label">Regime</span>
      <span class="{regime_cls}">{escape(regime_str)}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 3M</span>
      <span class="{rs3m_cls}">{_fmt_pct(rs3m)}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 6M</span>
      <span class="{rs6m_cls}">{_fmt_pct(rs6m)}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Days</span>
      <span style="color:#c9d1d9">{days_held}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Max ↑</span>
      <span class="{_gain_cls(max_gain)}">{_fmt_pct(max_gain)}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Max ↓</span>
      <span class="{_gain_cls(min_gain)}">{_fmt_pct(min_gain)}</span>
    </div>
  </div>

  <div class="insight-chip">Fundamentals &amp; Entry</div>
  <div class="sig-insight">
    <div class="insight-summary">{fund_sum}</div>
    <div class="insight-raw" style="margin-top:4px">{entry_instr}</div>
  </div>
</div>"""


def build_html(trades: list[dict], market: str, timeframe: str, last_updated: str) -> str:
    now      = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats    = pt.compute_summary_stats(trades)
    cur_sym  = _currency_sym(market)

    # Sort: open first, then by gain desc, expired last
    status_order = {"OPEN": 0, "T3_HIT": 1, "T2_HIT": 2, "T1_HIT": 3, "SL_HIT": 4, "EXPIRED": 5}
    sorted_trades = sorted(trades, key=lambda t: (status_order.get(t.get("status", "OPEN"), 9),
                                                   -_f(t.get("gainPct"))))

    rows_html = "".join(build_trade_card(t) for t in sorted_trades)
    total     = stats["total"]

    win_rate_color  = "#3fb950" if stats["winRate"] >= 60 else ("#e3b341" if stats["winRate"] >= 40 else "#f85149")
    avg_gain_color  = "#3fb950" if stats["avgGainPct"] > 0 else "#f85149"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 Performance Tracker — {market.upper()} {timeframe.upper()} | {now}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:0}}

/* TOP BAR */
.topbar{{background:linear-gradient(135deg,#0d1117,#1a2433);border-bottom:1px solid #21262d;
  padding:18px 28px;display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.topbar-title{{color:#79c0ff;font-size:1.3em;font-weight:700}}
.topbar-sub{{color:#8b949e;font-size:.82em;margin-top:3px}}
.topbar-stats{{display:flex;gap:16px;flex-wrap:wrap}}
.tstat{{text-align:center}}
.tstat-v{{font-size:1.4em;font-weight:700;color:#58a6ff}}
.tstat-l{{font-size:.72em;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}}

/* CONTROLS */
.controls-bar{{background:#161b22;border-bottom:1px solid #21262d;padding:14px 28px;
  display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:72px;z-index:40}}
.search-box,.sel{{padding:8px 12px;background:#0d1117;border:1px solid #30363d;
  border-radius:6px;color:#c9d1d9;font-size:.85em}}
.search-box{{min-width:200px}}
.btn-filter{{padding:7px 14px;border:1px solid #30363d;border-radius:6px;background:transparent;
  color:#79c0ff;cursor:pointer;font-size:.82em;transition:all .15s}}
.btn-filter:hover,.btn-filter.active{{background:#1f6feb;border-color:#58a6ff;color:#fff}}
.btn-export{{padding:7px 14px;border:1px solid #2ea043;border-radius:6px;background:transparent;
  color:#3fb950;cursor:pointer;font-size:.82em}}
.btn-export:hover{{background:#2ea04322}}

/* MAIN GRID */
.main{{padding:20px 28px}}
.signals-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:20px}}

/* SIGNAL CARD */
.sig-card{{background:linear-gradient(180deg,#161b22 0%,#0f141a 100%);border:1px solid #21262d;
  border-radius:14px;overflow:hidden;transition:all .2s;cursor:default}}
.sig-card:hover{{border-color:#30363d;box-shadow:0 8px 24px rgba(0,0,0,.35);transform:translateY(-2px)}}
.sig-card[data-status="SL_HIT"]{{border-color:#3a0f0f;background:linear-gradient(180deg,#1a0a0a,#120808)}}
.sig-card[data-status="T1_HIT"],
.sig-card[data-status="T2_HIT"],
.sig-card[data-status="T3_HIT"]{{border-color:#0f3a1f;background:linear-gradient(180deg,#0a1a0f,#080f0a)}}

/* HEADER */
.sig-header{{display:flex;justify-content:space-between;align-items:flex-start;padding:14px 16px 8px}}
.sig-left{{flex:1}}
.sig-sym{{font-size:1.2em;font-weight:800;color:#c9d1d9;letter-spacing:-.3px}}
.sig-meta{{display:flex;gap:6px;margin-top:5px;flex-wrap:wrap}}
.badge-sec{{padding:2px 8px;background:#1a2433;border-radius:4px;font-size:.72em;color:#79c0ff;font-weight:500}}
.badge-tf{{padding:2px 8px;background:#2a1a3a;border-radius:4px;font-size:.72em;color:#d2a8ff;font-weight:500}}
.sig-tag{{padding:2px 8px;border-radius:4px;font-size:.72em;font-weight:600}}
.tag-vcp{{background:#1e1b4b;color:#a5b4fc}}
.tag-rexp{{background:#1a2a0a;color:#86efac}}
.tag-mr{{background:#1a2a3a;color:#7dd3fc}}
.tag-bp{{background:#2a1a2a;color:#d8b4fe}}
.tag-bo{{background:#2a1a0a;color:#fbbf24}}
.rat-aplus{{background:#2a2a0a;color:#ffd700;border:1px solid #ffd70044}}
.rat-a{{background:#1e1b4b;color:#a5b4fc;border:1px solid #a5b4fc44}}
.rat-b{{background:#1a2a3a;color:#7dd3fc;border:1px solid #7dd3fc44}}

.sig-right{{display:flex;flex-direction:column;align-items:flex-end;gap:4px}}
.sig-sparkline svg{{display:block}}
.score-bar-wrap{{background:#0d1117;border-radius:3px;height:5px;position:relative}}
.score-bar-fill{{height:100%;border-radius:3px}}
.score-label{{position:absolute;right:0;top:-14px;font-size:.65em;color:#8b949e}}

/* PERFORMANCE BAND */
.perf-band{{background:#0b1016;border-top:1px solid #21262d;border-bottom:1px solid #21262d;
  padding:10px 16px;display:flex;flex-direction:column;gap:5px}}
.perf-row{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}}
.perf-main{{display:flex;align-items:center;gap:6px;font-weight:700}}
.perf-entry{{color:#8b949e;font-size:.88em}}
.perf-arrow{{color:#8b949e}}
.perf-current{{font-size:1.1em}}
.perf-gain{{font-size:1em;font-weight:800}}
.gain-up{{color:#3fb950}}
.gain-dn{{color:#f85149}}
.gain-flat{{color:#e3b341}}
.perf-badges{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
.status-badge{{padding:2px 8px;border-radius:99px;font-size:.75em;font-weight:700}}
.status-open{{background:#1a2a1a;color:#3fb950;border:1px solid #2ea04366}}
.status-sl{{background:#2a0a0a;color:#f85149;border:1px solid #f8514966}}
.status-t1{{background:#0a2a1a;color:#3fb950;border:1px solid #3fb95066}}
.status-t2{{background:#0a2a1a;color:#3fb950;border:1px solid #3fb95066}}
.status-t3{{background:#0a2a1a;color:#ffd700;border:1px solid #ffd70066}}
.status-expired{{background:#1a1a1a;color:#8b949e;border:1px solid #30363d}}
.still-yes{{padding:2px 8px;border-radius:99px;font-size:.72em;color:#58a6ff;
  background:#0f1f3a;border:1px solid #1f4f8a}}
.still-no{{padding:2px 8px;border-radius:99px;font-size:.72em;color:#8b949e;
  background:#111820;border:1px solid #21262d}}
.perf-details{{font-size:.75em;color:#8b949e}}
.perf-range{{display:flex;gap:8px}}
.target-row{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:.78em}}
.target-hit{{color:#c9d1d9}}
.regime-inline{{margin-left:auto;font-size:.72em;font-weight:600}}
.reg-fav{{color:#3fb950;font-weight:600;font-size:.82em}}
.reg-unfav{{color:#f85149;font-weight:600;font-size:.82em}}
.reg-neu{{color:#e3b341;font-weight:600;font-size:.82em}}

/* PROGRESS BAR */
.progress-wrap{{margin-top:4px}}
.progress-track{{height:5px;background:#21262d;border-radius:3px;position:relative;overflow:visible}}
.progress-fill{{height:100%;border-radius:3px;transition:width .4s}}
.progress-entry-marker{{position:absolute;top:-3px;width:2px;height:11px;
  background:#58a6ff;border-radius:1px}}
.progress-labels{{display:flex;justify-content:space-between;font-size:.62em;
  color:#8b949e;margin-top:2px}}

/* PLAN GRID */
.plan-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:#21262d}}
.plan-section{{background:#0f141a;padding:10px 14px}}
.plan-section.highlight{{background:#111a22}}
.plan-title{{font-size:.7em;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;
  margin-bottom:4px;font-weight:600}}
.plan-title small{{color:#58a6ff;font-size:.9em;text-transform:none;font-weight:600}}
.plan-value{{font-size:.95em;font-weight:700;margin-bottom:2px}}
.plan-sub{{font-size:.7em;color:#6e7681}}
.entry-val{{color:#79c0ff}}
.sl-val{{color:#f85149}}
.sl-val-hit{{color:#f85149;text-decoration:line-through}}
.t1-val{{color:#3fb950}}
.t1-hit{{color:#3fb950;text-decoration:underline}}
.t2-val{{color:#2ea043}}
.t2-hit{{color:#2ea043;text-decoration:underline}}
.t3-val{{color:#1a7431}}
.t3-hit{{color:#ffd700;text-decoration:underline}}

/* FOOTER */
.sig-footer{{display:flex;gap:12px;border-top:1px solid #21262d;padding:10px 16px;flex-wrap:wrap}}
.sig-stat{{display:flex;flex-direction:column;align-items:center}}
.sstat-label{{font-size:.65em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px}}
.rpl{{color:#3fb950;font-weight:600;font-size:.82em}}
.rmi{{color:#f85149;font-weight:600;font-size:.82em}}
.rna{{color:#8b949e;font-weight:600;font-size:.82em}}

/* HOVER INSIGHTS */
.insight-chip{{margin:6px 16px 0;display:inline-flex;padding:2px 8px;border:1px solid #2f3b4b;
  border-radius:12px;color:#7dd3fc;font-size:.68em;background:#0f1a26;cursor:pointer}}
.sig-insight{{max-height:0;opacity:0;overflow:hidden;padding:0 16px;
  transition:max-height .25s ease,opacity .2s ease,padding .2s ease;border-top:0 solid #21262d}}
.sig-card:hover .sig-insight{{max-height:120px;opacity:1;padding:8px 16px 10px;border-top:1px solid #21262d}}
.insight-summary{{font-size:.72em;color:#94a3b8;line-height:1.4;margin-bottom:4px}}
.insight-raw{{font-size:.68em;color:#7f8a98;line-height:1.4}}

/* NO RESULTS */
.no-results{{text-align:center;padding:60px;color:#8b949e;font-size:1.1em}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">📊 Breakout Performance Tracker — {market.upper()} {timeframe.upper()}</div>
    <div class="topbar-sub">A &amp; A+ rated setups from last 14 days &bull; Updated: {now}
      &bull; Last scan ingested: {escape(last_updated or "—")}</div>
  </div>
  <div class="topbar-stats">
    <div class="tstat">
      <div class="tstat-v">{total}</div>
      <div class="tstat-l">Tracked</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:#3fb950">{stats["open"]}</div>
      <div class="tstat-l">Open</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:#f85149">{stats["slHits"]}</div>
      <div class="tstat-l">SL Hit</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:#ffd700">{stats["targetHits"]}</div>
      <div class="tstat-l">Target Hit</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:{win_rate_color}">{stats["winRate"]:.0f}%</div>
      <div class="tstat-l">Win Rate</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:{avg_gain_color}">{stats["avgGainPct"]:+.1f}%</div>
      <div class="tstat-l">Avg Gain</div>
    </div>
    <div class="tstat">
      <div class="tstat-v" style="color:#58a6ff">{stats["stillInScan"]}</div>
      <div class="tstat-l">In Scan</div>
    </div>
  </div>
</div>

<div class="controls-bar">
  <input class="search-box" id="searchBox" placeholder="🔍 Search symbol, sector…"
         oninput="applyFilters()">
  <select class="sel" id="statusFilter" onchange="applyFilters()">
    <option value="">All Statuses</option>
    <option value="OPEN">Open</option>
    <option value="SL_HIT">SL Hit</option>
    <option value="T1_HIT">T1 Hit</option>
    <option value="T2_HIT">T2 Hit</option>
    <option value="T3_HIT">T3 Hit</option>
    <option value="EXPIRED">Expired</option>
  </select>
  <select class="sel" id="setupFilter" onchange="applyFilters()">
    <option value="">All Setups</option>
    <option value="RANGE_EXPANSION">Range Expansion</option>
    <option value="VCP">VCP</option>
    <option value="MEAN_REVERSION">Mean Reversion</option>
    <option value="BREAKOUT_PULLBACK">Breakout Pullback</option>
  </select>
  <select class="sel" id="ratingFilter" onchange="applyFilters()">
    <option value="">A &amp; A+</option>
    <option value="A+">A+ Only</option>
  </select>
  <button class="btn-filter" onclick="toggleSort('gain')" id="btn-sort-gain">📉 Sort: Gain</button>
  <button class="btn-filter" onclick="toggleSort('date')" id="btn-sort-date">📅 Sort: Date</button>
  <button class="btn-export" onclick="exportCSV()">⬇ Export CSV</button>
  <span id="filterCount" style="color:#8b949e;font-size:.83em;margin-left:8px"></span>
</div>

<div class="main">
  <div class="signals-grid" id="signalsGrid">
    {rows_html}
  </div>
  <div class="no-results" id="noResults" style="display:none">No trades match your filters.</div>
</div>

<script>
function applyFilters() {{
  const q      = document.getElementById('searchBox').value.toLowerCase();
  const status = document.getElementById('statusFilter').value;
  const setup  = document.getElementById('setupFilter').value;
  const rating = document.getElementById('ratingFilter').value;
  let visible = 0;
  document.querySelectorAll('.sig-card').forEach(card => {{
    const sym    = (card.dataset.symbol || '').toLowerCase();
    const sec    = (card.dataset.sector || '').toLowerCase();
    let show = !q || sym.includes(q) || sec.includes(q);
    if (status && card.dataset.status !== status) show = false;
    if (setup  && card.dataset.setup  !== setup)  show = false;
    if (rating === 'A+' && card.dataset.rating !== 'A+') show = false;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('filterCount').textContent = visible + ' shown';
  document.getElementById('noResults').style.display = visible === 0 ? '' : 'none';
}}

function toggleSort(mode) {{
  const grid  = document.getElementById('signalsGrid');
  const cards = [...grid.querySelectorAll('.sig-card')];
  cards.sort((a, b) => {{
    if (mode === 'gain')   return parseFloat(b.dataset.gain || 0) - parseFloat(a.dataset.gain || 0);
    if (mode === 'date')   return (a.dataset.symbol || '').localeCompare(b.dataset.symbol || '');
    return 0;
  }});
  cards.forEach(c => grid.appendChild(c));
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('btn-sort-' + mode);
  if (btn) btn.classList.add('active');
}}

function exportCSV() {{
  const rows = [['Symbol','Setup','Rating','TradeDate','Entry','StopLoss','T1','T2','T3',
                  'CurrentPrice','Gain%','MaxGain%','MinGain%','DaysHeld','Status',
                  'StillInScan','SLHit','T1Hit','T2Hit','T3Hit','RegimeAtScan','RS3M','RS6M']];
  document.querySelectorAll('.sig-card').forEach(card => {{
    if (card.style.display === 'none') return;
    const sym  = card.dataset.symbol || '';
    const vals = [...card.querySelectorAll('.plan-value')].map(v =>
      v.textContent.replace(/[₹$,]/g, '').trim());
    const stats = [...card.querySelectorAll('.sig-stat span:last-child')].map(v =>
      v.textContent.trim());
    rows.push([sym, card.dataset.setup, card.dataset.rating, '', vals[0]||'', vals[1]||'',
               '', '', '', '', '', '', '', '', card.dataset.status || '',
               '', '', '', '', '', stats[0]||'', stats[1]||'', stats[2]||'']);
  }});
  const csvStr = rows.map(r => r.map(v => '"' + String(v) + '"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvStr);
  a.download = 'perf_tracker_{market}_{timeframe}_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}

document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('filterCount').textContent = '{total} shown';
}});
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate performance tracker HTML")
    parser.add_argument("--output-dir", default=str(OUTPUT))
    parser.add_argument("--cache-dir",  default=str(CACHE_DIR))
    parser.add_argument("--markets",    default="india")
    parser.add_argument("--timeframes", default="daily,weekly")
    return parser.parse_args()


def main() -> None:
    args       = parse_args()
    output_dir = Path(args.output_dir)
    cache_dir  = Path(args.cache_dir)
    markets    = [m.strip() for m in args.markets.split(",") if m.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print("Updating performance tracker…")
    data = pt.run_performance_update(
        output_dir = output_dir,
        cache_dir  = cache_dir,
        markets    = markets,
        timeframes = timeframes,
    )

    all_trades   = data.get("trades", [])
    last_updated = data.get("lastUpdated", "")
    stats        = pt.compute_summary_stats(all_trades)
    print(f"  Tracked: {stats['total']} | Open: {stats['open']} | "
          f"SL Hit: {stats['slHits']} | Win rate: {stats['winRate']}% | "
          f"Avg gain: {stats['avgGainPct']:+.2f}%")

    for market in markets:
        for timeframe in timeframes:
            subset = [
                t for t in all_trades
                if t.get("market") == market and t.get("timeframe") == timeframe
            ]
            if not subset:
                print(f"  No trades for {market} {timeframe} — skipping HTML")
                continue

            html = build_html(subset, market, timeframe, last_updated)
            out_latest = output_dir / f"performance_tracker_{market}_{timeframe}_LATEST.html"
            out_latest.write_text(html, encoding="utf-8")
            print(f"  Written → {out_latest}  ({len(subset)} trades)")

    print("Performance tracker generation complete.")


if __name__ == "__main__":
    main()

