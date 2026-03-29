#!/usr/bin/env python3
"""
generate_performance_tracker.py
────────────────────────────────
Generates a rich HTML "Performance Tracker" page showing how qualifying
breakout setups are performing on current prices.

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
import re
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


def extract_pct(text: str, keys: list[str]) -> float | None:
    source = str(text or "")
    for key in keys:
        m = re.search(rf"{re.escape(key)}\s*[:=]\s*([+-]?\d+(?:\.\d+)?)%", source, flags=re.IGNORECASE)
        if m:
            return _f(m.group(1), 0.0)
    return None


def extract_debt_change(text: str) -> float | None:
    source = str(text or "")
    m = re.search(r"Debt[^\d+-]*([+-]?\d+(?:\.\d+)?)%", source, flags=re.IGNORECASE)
    if not m:
        return None
    val = _f(m.group(1), 0.0)
    if "↑" in source or "UP" in source.upper():
        return abs(val)
    if "↓" in source or "DOWN" in source.upper():
        return -abs(val)
    return val


def fmt_metric(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def classify_trigger(text: str) -> str:
    t = str(text or "").upper()
    if any(k in t for k in ["POSITIVE", "TAILWIND", "STRONG", "IMPROVING", "SUPPORTIVE"]):
        return "pill-pos"
    if any(k in t for k in ["WEAK", "RISK", "HEADWIND", "UNFAVORABLE", "NEGATIVE"]):
        return "pill-neg"
    return "pill-neu"


def _extract_trigger_block(summary: str, label: str) -> str:
    source = str(summary or "")
    if not source:
        return ""
    m = re.search(
        rf"(?:^|\|\s*){re.escape(label)}\s*:\s*(.*?)(?=\s*\|\s*[A-Za-z]+\s*:|$)",
        source,
        flags=re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _trade_trigger_value(trade: dict, field: str, label: str) -> str:
    direct = str(trade.get(field, "") or "").strip()
    if direct:
        return direct
    return _extract_trigger_block(str(trade.get("triggerSummary", "") or ""), label)


def _has_any(text: str, tokens: list[str]) -> bool:
    up = str(text or "").upper()
    return any(tok in up for tok in tokens)


def evaluate_trade_quality(trade: dict) -> dict:
    """Compute confidence score and enforce noise/fundamental quality gates."""
    score = _f(trade.get("score"))
    rating = str(trade.get("rating", "")).upper().strip()
    regime = str(trade.get("regimeAtScan", "") or "")
    rs3m = _f(trade.get("rs3mAtScan"))
    rs6m = _f(trade.get("rs6mAtScan"))

    eps_trigger  = _trade_trigger_value(trade, "triggerEarningsGrowth", "Earnings")
    debt_trigger = _trade_trigger_value(trade, "triggerDebtReduction",  "Debt")
    macro_trigger  = _trade_trigger_value(trade, "triggerMacroTailwind",  "Macro")
    market_trigger = _trade_trigger_value(trade, "triggerMarketTailwind", "Market")

    eps_yoy  = extract_pct(eps_trigger,  ["EPS_YOY",  "EPS YOY"])
    eps_qoq  = extract_pct(eps_trigger,  ["EPS_QOQ",  "EPS QOQ"])
    debt_yoy = extract_pct(debt_trigger, ["DEBT_YOY", "DEBT YOY"])
    debt_qoq = extract_pct(debt_trigger, ["DEBT_QOQ", "DEBT QOQ"])
    if debt_yoy is None and debt_qoq is None:
        debt_yoy = extract_debt_change(debt_trigger)

    # ── Hard-reject gates (noise killers) ──────────────────────────────────
    # Gate 1: both EPS YoY AND QoQ negative → fundamentally broken
    both_eps_neg = (eps_yoy is not None and eps_yoy < -5.0) and \
                   (eps_qoq is not None and eps_qoq < -5.0)
    # Gate 2: EPS weak label AND debt rising → double negative
    eps_weak_label  = _has_any(eps_trigger, ["WEAK", "NEGATIVE"])
    debt_rising     = _has_any(debt_trigger, ["RISK", "DEBT↑"]) or \
                      (debt_yoy is not None and debt_yoy > 10.0)
    fund_double_neg = eps_weak_label and debt_rising
    # Gate 3: unfavorable regime AND both RS negative → no tailwind at all
    regime_unfav    = "UNFAV" in regime.upper()
    both_rs_neg     = rs3m <= 0 and rs6m <= 0
    no_tailwind     = regime_unfav and both_rs_neg
    # Gate 4: B rating + both EPS and RS negative → low-conviction noise
    b_rating_weak   = rating == "B" and both_eps_neg and both_rs_neg

    weak_fundamentals = both_eps_neg or fund_double_neg or no_tailwind or b_rating_weak
    exclude_reason = ""
    if both_eps_neg:
        exclude_reason = "Both EPS YoY & QoQ negative"
    elif fund_double_neg:
        exclude_reason = "Weak earnings + rising debt"
    elif no_tailwind:
        exclude_reason = "Unfavorable regime + negative RS"
    elif b_rating_weak:
        exclude_reason = "B rating with weak EPS & RS"

    # ── Positive scoring ───────────────────────────────────────────────────
    confidence = 50
    reasons: list[str] = []

    if rating == "A+":
        confidence += 20
        reasons.append("A+ setup rating — elite structure")
    elif rating == "A":
        confidence += 13
        reasons.append("A setup rating — high quality")
    elif rating == "B":
        confidence += 4
        reasons.append("B setup rating")

    if score >= 110:
        confidence += 14
        reasons.append(f"Excellent quality score ({score:.1f})")
    elif score >= 90:
        confidence += 10
        reasons.append(f"Strong quality score ({score:.1f})")
    elif score >= 75:
        confidence += 5
    elif score < 65:
        confidence -= 10

    if rs3m > 5 and rs6m > 5:
        confidence += 10
        reasons.append("Strong 3M & 6M relative strength")
    elif rs3m > 0 and rs6m > 0:
        confidence += 6
        reasons.append("Positive 3M & 6M relative strength")
    elif rs3m > 0 or rs6m > 0:
        confidence += 2
    else:
        confidence -= 8

    if "UNFAV" in regime.upper():
        confidence -= 12
    elif "FAV" in regime.upper():
        confidence += 6
        reasons.append("Favorable market regime at scan")

    if _has_any(macro_trigger, ["TAILWIND", "POSITIVE", "SUPPORTIVE"]):
        confidence += 5
        reasons.append("Macro tailwind present")
    if _has_any(market_trigger, ["TAILWIND", "POSITIVE", "SUPPORTIVE"]):
        confidence += 5
        reasons.append("Market trigger supportive")

    # Reward genuinely strong fundamentals
    if eps_yoy is not None and eps_yoy >= 20 and eps_qoq is not None and eps_qoq >= 10:
        confidence += 10
        reasons.append(f"Strong EPS growth (YoY +{eps_yoy:.1f}%, QoQ +{eps_qoq:.1f}%)")
    elif eps_yoy is not None and eps_yoy >= 10:
        confidence += 5
        reasons.append(f"Positive EPS YoY (+{eps_yoy:.1f}%)")

    if debt_yoy is not None and debt_yoy <= -10:
        confidence += 5
        reasons.append("Debt being reduced")

    if weak_fundamentals:
        confidence -= 30

    confidence = max(0, min(100, confidence))
    # Require confidence >= 65 (raised from 60)
    include = (not weak_fundamentals) and confidence >= 65

    if not include and not exclude_reason:
        exclude_reason = f"Low confidence ({confidence}/100 < 65 threshold)"

    return {
        "confidence":       confidence,
        "pickReasons":      reasons[:5],
        "weakFundamentals": weak_fundamentals,
        "include":          include,
        "excludeReason":    exclude_reason,
    }


def build_monthly_sector_rows(trades: list[dict]) -> str:
    bucket: dict[tuple[str, str], dict] = {}
    for t in trades:
        td = str(t.get("tradeDate", ""))
        if len(td) < 7:
            continue
        month = td[:7]
        sector = get_sector(str(t.get("symbol", "")))
        key = (month, sector)
        stat = bucket.setdefault(key, {"count": 0, "wins": 0, "sum": 0.0, "best": -999.0, "worst": 999.0})
        gain = _f(t.get("gainPct"))
        stat["count"] += 1
        stat["sum"] += gain
        if gain > 0:
            stat["wins"] += 1
        stat["best"] = max(stat["best"], gain)
        stat["worst"] = min(stat["worst"], gain)

    rows: list[tuple[str, str, int, float, float, float, float]] = []
    for (month, sector), s in bucket.items():
        cnt = max(1, s["count"])
        win_rate = s["wins"] / cnt * 100.0
        avg_gain = s["sum"] / cnt
        rows.append((month, sector, s["count"], win_rate, avg_gain, s["best"], s["worst"]))

    rows.sort(key=lambda r: (r[0], -r[3], -r[4], -r[2]), reverse=True)
    if not rows:
        return "<tr><td colspan='7' style='color:#8b949e'>No monthly sector data available.</td></tr>"

    html_rows = []
    for month, sector, cnt, wr, avg, best, worst in rows[:36]:
        wr_col = "#3fb950" if wr >= 55 else ("#e3b341" if wr >= 40 else "#f85149")
        ag_col = "#3fb950" if avg >= 0 else "#f85149"
        html_rows.append(
            f"<tr><td>{escape(month)}</td><td>{escape(sector)}</td><td>{cnt}</td>"
            f"<td style='color:{wr_col};font-weight:700'>{wr:.1f}%</td>"
            f"<td style='color:{ag_col};font-weight:700'>{avg:+.2f}%</td>"
            f"<td style='color:#3fb950'>{best:+.2f}%</td><td style='color:#f85149'>{worst:+.2f}%</td></tr>"
        )
    return "\n".join(html_rows)


def build_symbol_frequency_rows(trades: list[dict]) -> str:
    """Build per-symbol appearance summary table sorted by appearances descending."""
    from collections import defaultdict
    sym_data: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "dates": set(), "gains": [],
        "statuses": [], "sector": "Other", "timeframes": set(),
        "ratings": set(), "maxConf": 0,
    })
    for t in trades:
        sym = str(t.get("symbol", "")).strip()
        if not sym:
            continue
        d = sym_data[sym]
        d["count"] += 1
        td = str(t.get("tradeDate", "")).strip()
        if td:
            d["dates"].add(td)
        d["gains"].append(_f(t.get("gainPct")))
        d["statuses"].append(str(t.get("status", "OPEN")))
        d["sector"] = get_sector(sym)
        d["timeframes"].add(str(t.get("timeframe", "")).lower())
        d["ratings"].add(str(t.get("rating", "")).upper().strip())
        d["maxConf"] = max(d["maxConf"], int(_f(t.get("confidence", 0))))

    if not sym_data:
        return "<tr><td colspan='8' style='color:#8b949e'>No symbol data.</td></tr>"

    rows: list[str] = []
    sorted_syms = sorted(sym_data.items(), key=lambda x: (-x[1]["count"], x[0]))
    for sym, d in sorted_syms:
        cnt = d["count"]
        gains = d["gains"]
        avg = sum(gains) / len(gains) if gains else 0.0
        wr = sum(1 for g in gains if g > 0) * 100.0 / len(gains) if gains else 0.0
        tgt = sum(1 for s in d["statuses"] if s in ("T1_HIT", "T2_HIT", "T3_HIT"))
        sl = sum(1 for s in d["statuses"] if s == "SL_HIT")
        dates_sorted = sorted(d["dates"])
        dates_str = " → ".join(dates_sorted[:3])
        if len(dates_sorted) > 3:
            dates_str += f" … +{len(dates_sorted) - 3} more"
        tfs = "/".join(sorted(d["timeframes"])).upper()
        ratings_str = "/".join(sorted(d["ratings"]))
        conf_col = "#3fb950" if d["maxConf"] >= 80 else ("#e3b341" if d["maxConf"] >= 60 else "#f85149")
        wr_col = "#3fb950" if wr >= 55 else ("#e3b341" if wr >= 40 else "#f85149")
        ag_col = "#3fb950" if avg >= 0 else "#f85149"
        sym_clean = escape(sym.replace(".NS", "").replace(".BO", ""))
        rows.append(
            f"<tr data-sym='{escape(sym)}' style='cursor:pointer' onclick=\"filterBySym('{escape(sym)}')\""
            f" title='Click to filter cards to {sym_clean}'>"
            f"<td><span style='color:#79c0ff;font-weight:700'>{sym_clean}</span>"
            f" <span style='color:#444;font-size:.75em'>{escape(d['sector'])}</span></td>"
            f"<td style='text-align:center'><span style='background:#1a2a3a;color:#58a6ff;"
            f"padding:2px 8px;border-radius:999px;font-weight:700;font-size:.85em'>{cnt}×</span></td>"
            f"<td style='font-size:.72em;color:#8b949e'>{escape(dates_str)}</td>"
            f"<td>{escape(tfs)}</td>"
            f"<td>{escape(ratings_str)}</td>"
            f"<td style='color:{conf_col};font-weight:700'>{d['maxConf']}</td>"
            f"<td style='color:{wr_col};font-weight:700'>{wr:.1f}%</td>"
            f"<td style='color:{ag_col};font-weight:700'>{avg:+.2f}%</td>"
            f"<td style='color:#ffd700'>{tgt} T / <span style='color:#f85149'>{sl} SL</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def build_symbol_frequency_rows(trades: list[dict]) -> str:  # type: ignore[no-redef]
    pass  # placeholder duplicate removed — handled above


# Remove the duplicate placeholder immediately
del build_symbol_frequency_rows


def _build_symbol_frequency_rows(trades: list[dict]) -> str:
    """Actual implementation referenced in build_html."""
    from collections import defaultdict
    sym_data: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "dates": set(), "gains": [],
        "statuses": [], "sector": "Other", "timeframes": set(),
        "ratings": set(), "maxConf": 0,
    })
    for t in trades:
        sym = str(t.get("symbol", "")).strip()
        if not sym:
            continue
        d = sym_data[sym]
        d["count"] += 1
        td = str(t.get("tradeDate", "")).strip()
        if td:
            d["dates"].add(td)
        d["gains"].append(_f(t.get("gainPct")))
        d["statuses"].append(str(t.get("status", "OPEN")))
        d["sector"] = get_sector(sym)
        d["timeframes"].add(str(t.get("timeframe", "")).lower())
        d["ratings"].add(str(t.get("rating", "")).upper().strip())
        d["maxConf"] = max(d["maxConf"], int(_f(t.get("confidence", 0))))

    if not sym_data:
        return "<tr><td colspan='9' style='color:#8b949e'>No symbol data.</td></tr>"

    rows: list[str] = []
    sorted_syms = sorted(sym_data.items(), key=lambda x: (-x[1]["count"], x[0]))
    for sym, d in sorted_syms:
        cnt = d["count"]
        gains = d["gains"]
        avg = sum(gains) / len(gains) if gains else 0.0
        wr = sum(1 for g in gains if g > 0) * 100.0 / len(gains) if gains else 0.0
        tgt = sum(1 for s in d["statuses"] if s in ("T1_HIT", "T2_HIT", "T3_HIT"))
        sl = sum(1 for s in d["statuses"] if s == "SL_HIT")
        dates_sorted = sorted(d["dates"])
        dates_str = " → ".join(dates_sorted[:3])
        if len(dates_sorted) > 3:
            dates_str += f" +{len(dates_sorted) - 3} more"
        tfs = "/".join(sorted(d["timeframes"])).upper()
        ratings_str = "/".join(sorted(d["ratings"]))
        conf_col = "#3fb950" if d["maxConf"] >= 80 else ("#e3b341" if d["maxConf"] >= 60 else "#f85149")
        wr_col = "#3fb950" if wr >= 55 else ("#e3b341" if wr >= 40 else "#f85149")
        ag_col = "#3fb950" if avg >= 0 else "#f85149"
        sym_clean = escape(sym.replace(".NS", "").replace(".BO", ""))
        rows.append(
            f"<tr data-sym='{escape(sym)}' style='cursor:pointer' onclick=\"filterBySym('{escape(sym)}')\""
            f" title='Click to filter cards to {sym_clean}'>"
            f"<td><span style='color:#79c0ff;font-weight:700'>{sym_clean}</span>"
            f"  <span style='color:#555;font-size:.75em'>{escape(d['sector'])}</span></td>"
            f"<td style='text-align:center'><span style='background:#1a2a3a;color:#58a6ff;"
            f"padding:2px 8px;border-radius:999px;font-weight:700;font-size:.85em'>{cnt}×</span></td>"
            f"<td style='font-size:.72em;color:#8b949e'>{escape(dates_str)}</td>"
            f"<td style='font-size:.78em'>{escape(tfs)}</td>"
            f"<td style='font-size:.78em'>{escape(ratings_str)}</td>"
            f"<td style='color:{conf_col};font-weight:700'>{d['maxConf']}</td>"
            f"<td style='color:{wr_col};font-weight:700'>{wr:.1f}%</td>"
            f"<td style='color:{ag_col};font-weight:700'>{avg:+.2f}%</td>"
            f"<td><span style='color:#ffd700'>{tgt}T</span> / <span style='color:#f85149'>{sl}SL</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def build_confidence_cut_rows(trades: list[dict]) -> str:
    cuts = [60, 70, 80, 90]
    rows: list[str] = []
    for cut in cuts:
        subset = [t for t in trades if _f(t.get("confidence")) >= cut]
        stats = pt.compute_summary_stats(subset)
        total = max(1, len(subset))
        sl_rate = sum(1 for t in subset if t.get("status") == "SL_HIT") / total * 100 if subset else 0.0
        target_rate = sum(1 for t in subset if t.get("status") in ("T1_HIT", "T2_HIT", "T3_HIT")) / total * 100 if subset else 0.0
        wr_col = "#3fb950" if stats["winRate"] >= 55 else ("#e3b341" if stats["winRate"] >= 40 else "#f85149")
        ag_col = "#3fb950" if stats["avgGainPct"] >= 0 else "#f85149"
        rows.append(
            f"<tr><td>{cut}+</td><td>{stats['total']}</td>"
            f"<td style='color:{wr_col};font-weight:700'>{stats['winRate']:.1f}%</td>"
            f"<td style='color:{ag_col};font-weight:700'>{stats['avgGainPct']:+.2f}%</td>"
            f"<td>{target_rate:.1f}%</td><td>{sl_rate:.1f}%</td></tr>"
        )
    return "\n".join(rows)


def build_confidence_headline(trades: list[dict]) -> str:
    elite = [t for t in trades if _f(t.get("confidence")) >= 80]
    strict = [t for t in trades if _f(t.get("confidence")) >= 90]
    elite_stats = pt.compute_summary_stats(elite)
    strict_stats = pt.compute_summary_stats(strict)
    return (
        f"<div class='conf-card'><div class='conf-title'>80+ Confidence Picks</div>"
        f"<div class='conf-value'>{elite_stats['total']}</div>"
        f"<div class='conf-sub'>Win rate {elite_stats['winRate']:.1f}% &bull; Avg gain {elite_stats['avgGainPct']:+.2f}%</div></div>"
        f"<div class='conf-card'><div class='conf-title'>90+ Confidence Picks</div>"
        f"<div class='conf-value'>{strict_stats['total']}</div>"
        f"<div class='conf-sub'>Win rate {strict_stats['winRate']:.1f}% &bull; Avg gain {strict_stats['avgGainPct']:+.2f}%</div></div>"
    )


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
    fund_sum_raw = str(trade.get("fundSummary", "") or "")
    fund_sum    = escape(fund_sum_raw or "No online fundamentals snapshot available")
    entry_instr = escape(trade.get("entryInstruction", "") or "—")
    sparkline   = trade.get("sparkline", [])
    sector      = get_sector(sym)
    cur_sym     = _currency_sym(market)
    eps_trigger_raw = _trade_trigger_value(trade, "triggerEarningsGrowth", "Earnings")
    debt_trigger_raw = _trade_trigger_value(trade, "triggerDebtReduction", "Debt")
    macro_trigger_raw = _trade_trigger_value(trade, "triggerMacroTailwind", "Macro")
    market_trigger_raw = _trade_trigger_value(trade, "triggerMarketTailwind", "Market")

    eps_yoy = extract_pct(eps_trigger_raw, ["EPS_YOY", "EPS YOY"])
    eps_qoq = extract_pct(eps_trigger_raw, ["EPS_QOQ", "EPS QOQ"])
    debt_yoy = extract_pct(debt_trigger_raw, ["DEBT_YOY", "DEBT YOY"])
    debt_qoq = extract_pct(debt_trigger_raw, ["DEBT_QOQ", "DEBT QOQ"])
    if debt_yoy is None and debt_qoq is None:
        debt_yoy = extract_debt_change(debt_trigger_raw)

    eps_yoy_text = fmt_metric(eps_yoy)
    eps_qoq_text = fmt_metric(eps_qoq)
    debt_yoy_text = fmt_metric(debt_yoy)
    debt_qoq_text = fmt_metric(debt_qoq)

    eps_cls = (
        "metric-na" if eps_yoy is None and eps_qoq is None
        else "metric-pos" if ((eps_yoy or 0) >= 0 or (eps_qoq or 0) >= 0)
        else "metric-neg"
    )
    debt_cls = (
        "metric-na" if debt_yoy is None and debt_qoq is None
        else "metric-neg" if ((debt_yoy or 0) > 0 or (debt_qoq or 0) > 0)
        else "metric-pos"
    )

    eps_trigger = escape(eps_trigger_raw or "N/A")
    debt_trigger = escape(debt_trigger_raw or "N/A")
    macro_trigger = escape(macro_trigger_raw or "N/A")
    market_trigger = escape(market_trigger_raw or "N/A")

    conf = int(_f(trade.get("confidence"), 0))
    conf_cls = "conf-high" if conf >= 80 else ("conf-mid" if conf >= 60 else "conf-low")
    pick_reasons = trade.get("pickReasons", []) or []
    pick_reason_html = "".join(f"<li>{escape(str(r))}</li>" for r in pick_reasons)

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
<div class="sig-card" data-symbol="{escape(sym)}" data-setup="{escape(setup)}" data-timeframe="{escape(timeframe)}"
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
    <div class="sig-stat">
      <span class="sstat-label">Confidence</span>
      <span class="{conf_cls}">{conf}/100</span>
    </div>
  </div>

  <div class="insight-chip">Fundamentals &amp; Entry</div>
  <div class="sig-insight">
    <div class="insight-grid">
      <div class="insight-item">
        <div class="insight-label">EPS Growth</div>
        <div class="insight-value {eps_cls}">YoY {eps_yoy_text} &nbsp;|&nbsp; QoQ {eps_qoq_text}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Debt Change</div>
        <div class="insight-value {debt_cls}">YoY {debt_yoy_text} &nbsp;|&nbsp; QoQ {debt_qoq_text}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Macro Trigger</div>
        <div class="insight-pill {classify_trigger(macro_trigger_raw)}">{macro_trigger}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Market Trigger</div>
        <div class="insight-pill {classify_trigger(market_trigger_raw)}">{market_trigger}</div>
      </div>
    </div>
    <div class="insight-summary">{fund_sum}</div>
    {f'<div class="pick-reasons"><div class="pick-reasons-title">Why Picked</div><ul>{pick_reason_html}</ul></div>' if pick_reason_html else ''}
    <div class="insight-raw">
      <div><b>Entry:</b> {entry_instr}</div>
      <div><b>EPS:</b> {eps_trigger}</div>
      <div><b>Debt:</b> {debt_trigger}</div>
    </div>
  </div>
</div>"""


def build_html(trades: list[dict], market: str, timeframe_label: str, last_updated: str, excluded: dict[str, int]) -> str:
    now      = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats    = pt.compute_summary_stats(trades)
    cur_sym  = _currency_sym(market)

    # Sort: open first, then by gain desc, expired last
    status_order = {"OPEN": 0, "T3_HIT": 1, "T2_HIT": 2, "T1_HIT": 3, "SL_HIT": 4, "EXPIRED": 5}
    sorted_trades = sorted(trades, key=lambda t: (status_order.get(t.get("status", "OPEN"), 9),
                                                   -_f(t.get("gainPct"))))

    rows_html = "".join(build_trade_card(t) for t in sorted_trades)
    total     = stats["total"]
    monthly_sector_rows = build_monthly_sector_rows(sorted_trades)
    confidence_cut_rows = build_confidence_cut_rows(sorted_trades)
    confidence_headline = build_confidence_headline(sorted_trades)
    symbol_freq_rows    = _build_symbol_frequency_rows(sorted_trades)

    win_rate_color  = "#3fb950" if stats["winRate"] >= 60 else ("#e3b341" if stats["winRate"] >= 40 else "#f85149")
    avg_gain_color  = "#3fb950" if stats["avgGainPct"] > 0 else "#f85149"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 Performance Tracker — {market.upper()} {timeframe_label.upper()} | {now}</title>
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
.summary-wrap{{padding:16px 28px;background:#0f141a;border-bottom:1px solid #21262d}}
.summary-head{{font-size:.95em;color:#8b949e;margin-bottom:8px}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px}}
.conf-card{{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:12px 14px}}
.conf-title{{font-size:.8em;color:#79c0ff;text-transform:uppercase;letter-spacing:.4px}}
.conf-value{{font-size:1.6em;font-weight:800;color:#c9d1d9;margin-top:4px}}
.conf-sub{{font-size:.78em;color:#8b949e;margin-top:3px;line-height:1.4}}
.monthly-table{{width:100%;border-collapse:collapse;background:#0d1117;border:1px solid #21262d;border-radius:8px;overflow:hidden}}
.monthly-table th,.monthly-table td{{border-bottom:1px solid #21262d;padding:7px 8px;font-size:.78em;text-align:left}}
.monthly-table th{{color:#79c0ff;background:#111827;font-weight:700}}
.sym-freq-wrap{{padding:16px 28px;background:#0a0f14;border-bottom:1px solid #21262d}}
.sym-freq-search{{padding:6px 10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:.83em;min-width:200px;margin-bottom:8px}}
.sym-freq-table{{width:100%;border-collapse:collapse;background:#0d1117;border:1px solid #21262d;border-radius:8px;overflow:hidden}}
.sym-freq-table th,.sym-freq-table td{{border-bottom:1px solid #21262d;padding:7px 9px;font-size:.78em;text-align:left}}
.sym-freq-table th{{color:#79c0ff;background:#0f1824;font-weight:700;position:sticky;top:0}}
.sym-freq-table tr:hover{{background:#0f1824}}

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
.conf-high{{color:#3fb950;font-weight:700;font-size:.82em}}
.conf-mid{{color:#e3b341;font-weight:700;font-size:.82em}}
.conf-low{{color:#f85149;font-weight:700;font-size:.82em}}

/* HOVER INSIGHTS */
.insight-chip{{margin:6px 16px 0;display:inline-flex;padding:2px 8px;border:1px solid #2f3b4b;
  border-radius:12px;color:#7dd3fc;font-size:.68em;background:#0f1a26;cursor:pointer}}
.sig-insight{{max-height:0;opacity:0;overflow:hidden;padding:0 16px;
  transition:max-height .25s ease,opacity .2s ease,padding .2s ease;border-top:0 solid #21262d}}
.sig-card:hover .sig-insight{{max-height:220px;opacity:1;padding:8px 16px 10px;border-top:1px solid #21262d}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px 12px;margin-bottom:8px}}
.insight-item{{min-width:0}}
.insight-label{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.insight-value{{font-size:.74em;font-weight:600}}
.metric-pos{{color:#3fb950}}
.metric-neg{{color:#f85149}}
.metric-na{{color:#8b949e}}
.insight-pill{{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;border:1px solid #30363d;
  font-size:.68em;font-weight:600;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pill-pos{{background:#0f2418;color:#3fb950;border-color:#1f6b36}}
.pill-neg{{background:#2a1215;color:#ff7b72;border-color:#8b2d2d}}
.pill-neu{{background:#161b22;color:#c9d1d9;border-color:#30363d}}
.insight-summary{{font-size:.72em;color:#94a3b8;line-height:1.4;margin-bottom:4px}}
.insight-raw{{font-size:.68em;color:#7f8a98;line-height:1.4}}
.pick-reasons{{margin:4px 0 6px;padding:6px 8px;background:#0f1824;border:1px solid #233247;border-radius:6px}}
.pick-reasons-title{{font-size:.66em;color:#7dd3fc;text-transform:uppercase;letter-spacing:.35px;margin-bottom:3px}}
.pick-reasons ul{{margin:0;padding-left:16px}}
.pick-reasons li{{font-size:.7em;line-height:1.35;color:#c9d1d9}}

/* NO RESULTS */
.no-results{{text-align:center;padding:60px;color:#8b949e;font-size:1.1em}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">📊 Breakout Performance Tracker — {market.upper()} {timeframe_label.upper()}</div>
    <div class="topbar-sub">Daily tracker keeps ~1 month of scan sessions &bull; Weekly tracker keeps ~7 weeks &bull; Updated: {now}
      &bull; Last scan ingested: {escape(last_updated or "—")}</div>
    <div class="topbar-sub">Quality gate applied: weak fundamentals removed, confidence score must be 60+.
      Excluded: {excluded.get('weak_fundamentals', 0)} weak-fundamentals, {excluded.get('low_confidence', 0)} low-confidence.</div>
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

<div class="summary-wrap">
  <div class="summary-head">How the most confident picks are performing</div>
  <div class="summary-grid">{confidence_headline}</div>
  <table class="monthly-table" style="margin-bottom:16px">
    <thead>
      <tr><th>Confidence Cut</th><th>Picks</th><th>Win Rate</th><th>Avg Gain</th><th>Target-Hit Rate</th><th>SL-Hit Rate</th></tr>
    </thead>
    <tbody>
      {confidence_cut_rows}
    </tbody>
  </table>
  <div class="summary-head">Monthly sector-wise breakout performance (filtered picks)</div>
  <table class="monthly-table">
    <thead>
      <tr><th>Month</th><th>Sector</th><th>Trades</th><th>Win Rate</th><th>Avg Gain</th><th>Best</th><th>Worst</th></tr>
    </thead>
    <tbody>
      {monthly_sector_rows}
    </tbody>
  </table>
</div>

<div class="sym-freq-wrap">
  <div class="summary-head">Symbol appearances — how many times each stock showed up in filtered scans
    <span style="color:#555;font-size:.8em;margin-left:8px">(click a row to filter cards below)</span>
  </div>
  <input class="sym-freq-search" id="symFreqSearch" placeholder="🔍 Filter symbols…" oninput="filterSymTable()">
  <div style="max-height:360px;overflow-y:auto;border-radius:8px;border:1px solid #21262d">
    <table class="sym-freq-table" id="symFreqTable">
      <thead>
        <tr>
          <th onclick="sortSymTable(0)" style="cursor:pointer">Symbol ↕</th>
          <th onclick="sortSymTable(1)" style="cursor:pointer;text-align:center">Appearances ↕</th>
          <th>Scan Dates</th>
          <th>Timeframe</th>
          <th>Rating</th>
          <th onclick="sortSymTable(5)" style="cursor:pointer">Max Conf ↕</th>
          <th onclick="sortSymTable(6)" style="cursor:pointer">Win Rate ↕</th>
          <th onclick="sortSymTable(7)" style="cursor:pointer">Avg Gain ↕</th>
          <th>Targets / SL</th>
        </tr>
      </thead>
      <tbody id="symFreqBody">
        {symbol_freq_rows}
      </tbody>
    </table>
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
  <select class="sel" id="timeframeFilter" onchange="applyFilters()">
    <option value="">All Timeframes</option>
    <option value="daily">Daily</option>
    <option value="weekly">Weekly</option>
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
  const tf     = document.getElementById('timeframeFilter').value;
  const rating = document.getElementById('ratingFilter').value;
  let visible = 0;
  document.querySelectorAll('.sig-card').forEach(card => {{
    const sym    = (card.dataset.symbol || '').toLowerCase();
    const sec    = (card.dataset.sector || '').toLowerCase();
    let show = !q || sym.includes(q) || sec.includes(q);
    if (status && card.dataset.status !== status) show = false;
    if (setup  && card.dataset.setup  !== setup)  show = false;
    if (tf     && card.dataset.timeframe !== tf)  show = false;
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
  a.download = 'perf_tracker_{market}_{timeframe_label}_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}

document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('filterCount').textContent = '{total} shown';
}});

function filterBySym(sym) {{
  const box = document.getElementById('searchBox');
  const clean = sym.replace(/\.(NS|BO)$/i,'');
  box.value = clean;
  applyFilters();
  document.getElementById('signalsGrid').scrollIntoView({{behavior:'smooth',block:'start'}});
}}

function filterSymTable() {{
  const q = document.getElementById('symFreqSearch').value.toLowerCase();
  document.querySelectorAll('#symFreqBody tr').forEach(row => {{
    row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

let _symSortState = {{col: 1, asc: false}};
function sortSymTable(col) {{
  const tbody = document.getElementById('symFreqBody');
  const rows = [...tbody.querySelectorAll('tr')];
  const asc = _symSortState.col === col ? !_symSortState.asc : false;
  _symSortState = {{col, asc}};
  rows.sort((a, b) => {{
    const av = a.cells[col] ? a.cells[col].textContent.trim() : '';
    const bv = b.cells[col] ? b.cells[col].textContent.trim() : '';
    const an = parseFloat(av.replace(/[^0-9.+-]/g,''));
    const bn = parseFloat(bv.replace(/[^0-9.+-]/g,''));
    const cmp = (!isNaN(an) && !isNaN(bn)) ? (an - bn) : av.localeCompare(bv);
    return asc ? cmp : -cmp;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
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
    parser.add_argument("--daily-backfill-sessions", type=int, default=20,
                        help="Daily timeframe: import the latest N trading sessions from backtest (default: 20)")
    parser.add_argument("--weekly-backfill-sessions", type=int, default=7,
                        help="Weekly timeframe: import the latest N weekly sessions from backtest (default: 7)")
    parser.add_argument("--backtest-workers", type=int, default=4,
                        help="Worker count to use when simulating historical backfill runs")
    parser.add_argument("--backtest-batch", type=int, default=20,
                        help="Batch size to use when simulating historical backfill runs")
    parser.add_argument("--backtest-setups", choices=["both", "vcp", "range_expansion"], default="both",
                        help="Setup family to use for historical breakout backfill simulation")
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
        daily_backfill_sessions = max(0, args.daily_backfill_sessions),
        weekly_backfill_sessions = max(0, args.weekly_backfill_sessions),
        backtest_workers = max(1, args.backtest_workers),
        backtest_batch = max(1, args.backtest_batch),
        backtest_setups = args.backtest_setups,
    )

    all_trades   = data.get("trades", [])
    last_updated = data.get("lastUpdated", "")
    stats        = pt.compute_summary_stats(all_trades)
    print(f"  Tracked: {stats['total']} | Open: {stats['open']} | "
          f"SL Hit: {stats['slHits']} | Win rate: {stats['winRate']}% | "
          f"Avg gain: {stats['avgGainPct']:+.2f}%")

    timeframe_label = "_".join(timeframes) if timeframes else "all"
    for market in markets:
        raw_subset = [
            dict(t) for t in all_trades
            if t.get("market") == market and t.get("timeframe") in timeframes
        ]
        if not raw_subset:
            print(f"  No trades for {market} in [{', '.join(timeframes)}] — skipping HTML")
            continue

        excluded = {"weak_fundamentals": 0, "low_confidence": 0}
        subset: list[dict] = []
        for trade in raw_subset:
            q = evaluate_trade_quality(trade)
            trade.update(q)
            if q["include"]:
                subset.append(trade)
            elif q["weakFundamentals"]:
                excluded["weak_fundamentals"] += 1
            else:
                excluded["low_confidence"] += 1

        if not subset:
            print(f"  All {len(raw_subset)} trades filtered by quality gate for {market} — skipping HTML")
            continue

        html = build_html(subset, market, timeframe_label, last_updated, excluded)
        out_latest = output_dir / f"performance_tracker_{market}_LATEST.html"
        out_latest.write_text(html, encoding="utf-8")
        print(
            f"  Written → {out_latest}  ({len(subset)} picks kept / {len(raw_subset)} total, "
            f"excluded weak={excluded['weak_fundamentals']}, low_conf={excluded['low_confidence']})"
        )

    print("Performance tracker generation complete.")


if __name__ == "__main__":
    main()

