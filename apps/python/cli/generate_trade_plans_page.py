#!/usr/bin/env python3
"""
generate_trade_plans_page.py
Generates a rich standalone HTML Trade Plans page with:
  - All current breakout/VCP signals (daily + weekly)
  - Price sparklines from cached OHLCV data
  - Pivot zones, entries, stops, T1/T2/T3
  - Position sizing, R:R ratios
  - Sector, regime, RS rank
  - Fundamentals-aware scoring
  - Market context banner
Run: python3 apps/python/cli/generate_trade_plans_page.py
"""
from __future__ import annotations
import csv, json, math, re, sys
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

from utils import aggregate_weekly_bars, safe_return

try:
    from fundamentals_provider import (
        FundamentalsProvider,
        compact_summary as fundamentals_compact_summary,
        HAS_YFINANCE as _HAS_YFINANCE,
    )
    _FUNDAMENTALS_AVAILABLE = True
except Exception:
    FundamentalsProvider = None
    _FUNDAMENTALS_AVAILABLE = False
    _HAS_YFINANCE = False

    def fundamentals_compact_summary(_f: dict, is_india: bool = True) -> str:
        return "\u2014"

ACCOUNT_SIZE = 1_000_000
RISK_PCT     = 0.01

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
    "IPCALAB":"Pharma","GLENMARK":"Pharma","GRANULES":"Pharma","LAURUSLABS":"Pharma",
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
    "CUMMINSIND":"Cap Goods","THERMAX":"Cap Goods",
    "HDFCLIFE":"Insurance","SBILIFE":"Insurance","ICICIPRU":"Insurance",
    "M&M":"Auto",
}

SETUP_META = {
    "VCP":               ("tag-vcp",   "VCP Breakout",       "Buy above pivot on volume >=1.5x avg. Stop below base low."),
    "RANGE_EXPANSION":   ("tag-rexp",  "Range Expansion",    "Buy open next session after wide-range candle clears base. Stop 1 ATR below."),
    "MEAN_REVERSION":    ("tag-mr",    "Mean Reversion",     "Buy as price reclaims SMA20 or bounces off lower BB. Stop 2x ATR below."),
    "BREAKOUT_PULLBACK": ("tag-bp",    "Breakout Pullback",  "Buy first pullback to prior breakout support on dry volume. Stop below BO level."),
    "BREAKOUT":          ("tag-bo",    "Breakout",           "Buy on confirmation close above prior high. Stop below swing low."),
}

def _f(v, d=0.0):
    try:
        if v in (None, "", "N/A"):
            return d
        return float(str(v).strip().replace("%", "").replace(",", "").replace("x", ""))
    except Exception:
        return d

def get_sector(symbol: str) -> str:
    base = symbol.replace(".NS","").replace(".BO","")
    return SECTOR_MAP.get(base, "Other")

def _load_price_rows_uncached(symbol: str) -> list[dict]:
    for suffix in ["_900", "_504", "_252"]:
        p = CACHE_DIR / f"{symbol}{suffix}.csv"
        if not p.exists():
            continue
        rows: list[dict] = []
        try:
            with open(p) as f:
                for row in csv.DictReader(f):
                    rows.append({
                        "date": row.get("date", ""),
                        "open": _f(row.get("open")),
                        "high": _f(row.get("high")),
                        "low": _f(row.get("low")),
                        "close": _f(row.get("close")),
                        "volume": _f(row.get("volume")),
                    })
        except Exception:
            rows = []
        if rows:
            return rows
    return []


@lru_cache(maxsize=8192)
def load_price_rows(symbol: str, weekly: bool = False) -> list[dict]:
    rows = _load_price_rows_uncached(symbol)
    if not rows:
        return []
    return aggregate_weekly_bars(rows) if weekly else rows


def load_sparkline(symbol: str, n: int = 60) -> list[float]:
    """Load last n closes for sparkline from cached daily rows."""
    rows = load_price_rows(symbol, weekly=False)
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    return closes[-n:] if closes else []


def current_expansion_metrics(rows: list[dict], lookback: int = 20) -> tuple[float | None, float | None]:
    if len(rows) < 2:
        return None, None
    current = rows[-1]
    current_close = _f(current.get("close"))
    current_high = _f(current.get("high"), current_close)
    current_low = _f(current.get("low"), current_close)
    if current_close <= 0:
        return None, None

    current_range = max(0.0, current_high - current_low)
    prior = rows[-(lookback + 1):-1]
    prior_ranges = [max(0.0, _f(r.get("high")) - _f(r.get("low"))) for r in prior]
    prior_ranges = [r for r in prior_ranges if r > 0]
    avg_range = (sum(prior_ranges) / len(prior_ranges)) if prior_ranges else 0.0
    rexp = (current_range / avg_range) if avg_range > 0 and current_range > 0 else None

    current_vol = _f(current.get("volume"))
    prior_vols = [_f(r.get("volume")) for r in prior]
    prior_vols = [v for v in prior_vols if v > 0]
    avg_vol = (sum(prior_vols) / len(prior_vols)) if prior_vols else 0.0
    vol_pct = (((current_vol / avg_vol) - 1.0) * 100.0) if avg_vol > 0 and current_vol > 0 else None
    return vol_pct, rexp


def compute_rs_metrics(rows: list[dict], weekly: bool) -> tuple[float | None, float | None]:
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    if not closes:
        return None, None
    rs3_bars, rs6_bars = (13, 26) if weekly else (63, 126)
    rs3 = safe_return(closes, rs3_bars) * 100.0 if len(closes) > rs3_bars else None
    rs6 = safe_return(closes, rs6_bars) * 100.0 if len(closes) > rs6_bars else None
    return rs3, rs6


def pick_metric(primary: float, fallback: float | None, zero_is_missing: bool = True) -> float | None:
    if primary == 0.0 and zero_is_missing:
        return fallback
    return primary if primary == primary else fallback


def fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "&mdash;"
    if abs(value) < 0.05:
        return "&mdash;"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def fmt_x(value: float | None) -> str:
    if value is None:
        return "&mdash;"
    if abs(value) < 0.05:
        return "&mdash;"
    return f"{value:.2f}x"


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


def _has_value(v) -> bool:
    t = str(v or "").strip()
    return t not in {"", "\u2014", "UNKNOWN", "N/A", "NONE", "NULL"}


def _fundamentals_completeness(row: dict) -> tuple[int, float]:
    score = 0
    if _has_value(row.get("fundSummary")):
        score += 2
    if _has_value(row.get("triggerEarningsGrowth")):
        score += 2
    if _has_value(row.get("triggerDebtReduction")):
        score += 2
    if _has_value(row.get("triggerMacroTailwind") or row.get("macroTrigger") or row.get("triggerMacro")):
        score += 1
    if _has_value(row.get("triggerMarketTailwind") or row.get("marketTrigger") or row.get("triggerMarket")):
        score += 1
    return score, _f(row.get("score", 0))


def _pick_better_row(current: dict, candidate: dict) -> dict:
    c_key = _fundamentals_completeness(current)
    n_key = _fundamentals_completeness(candidate)
    return candidate if n_key > c_key else current


def _derive_macro_market(sig: dict) -> tuple[str, str]:
    regime_support = str(sig.get("regimeSupport") or "").upper()
    weekly_agreement = str(sig.get("weeklyAgreement") or "").upper()
    rs_score = _f(sig.get("rsScore"), 0.0)

    macro_trigger = "TAILWIND" if regime_support in {"STRONG", "SUPPORTIVE"} else "NEUTRAL_OR_HEADWIND"
    market_trigger = "TAILWIND" if weekly_agreement in {"STRONG", "SUPPORTIVE"} and rs_score > 0 else "MIXED"
    return macro_trigger, market_trigger


def _format_pct_trigger(prefix: str, value: float | None) -> str:
    if value is None:
        return f"{prefix}:UNKNOWN"
    sign = "+" if value >= 0 else ""
    return f"{prefix}:{sign}{value:.1f}%"


def _earnings_trigger_from_fundamentals(fund: dict | None) -> str:
    if not fund or fund.get("error"):
        return "UNKNOWN"

    eps_yoy = _f(fund.get("eps_yoy"), float("nan"))
    eps_qoq = _f(fund.get("eps_qoq"), float("nan"))
    rev_yoy = _f(fund.get("rev_yoy"), float("nan"))

    eps_yoy = None if eps_yoy != eps_yoy else eps_yoy
    eps_qoq = None if eps_qoq != eps_qoq else eps_qoq
    rev_yoy = None if rev_yoy != rev_yoy else rev_yoy

    strong = (eps_yoy is not None and eps_yoy >= 15.0) or (rev_yoy is not None and rev_yoy >= 12.0)
    weak = (eps_yoy is not None and eps_yoy <= -10.0) or (rev_yoy is not None and rev_yoy <= -5.0)

    parts: list[str] = []
    if eps_yoy is not None:
        parts.append(_format_pct_trigger("EPS_YOY", eps_yoy))
    if eps_qoq is not None:
        parts.append(_format_pct_trigger("EPS_QOQ", eps_qoq))
    if rev_yoy is not None:
        parts.append(_format_pct_trigger("REV_YOY", rev_yoy))

    if not parts:
        return "UNKNOWN"
    if strong:
        return "POSITIVE " + " / ".join(parts)
    if weak:
        return "WEAK " + " / ".join(parts)
    return "MIXED " + " / ".join(parts)


def _debt_trigger_from_fundamentals(fund: dict | None) -> str:
    if not fund or fund.get("error"):
        return "UNKNOWN"
    debt_trend = _f(fund.get("debt_trend_pct"), float("nan"))
    if debt_trend != debt_trend:
        return "UNKNOWN"
    if debt_trend <= -5.0:
        return f"POSITIVE Debt\u2193 {abs(debt_trend):.1f}%"
    if debt_trend >= 5.0:
        return f"RISK Debt\u2191 {debt_trend:.1f}%"
    return f"STABLE Debt {debt_trend:+.1f}%"


def hydrate_missing_fundamentals(signals: list[dict]) -> dict:
    stats = {
        "signals": len(signals or []),
        "needs_fundamentals": 0,
        "fund_summary_filled": 0,
        "earnings_filled": 0,
        "debt_filled": 0,
        "still_missing_summary": 0,
        "still_missing_earnings": 0,
        "still_missing_debt": 0,
        "fundamentals_available": _FUNDAMENTALS_AVAILABLE,
        "yfinance_available": _HAS_YFINANCE,
    }
    if not signals:
        return stats

    for sig in signals:
        if not _has_value(sig.get("triggerMacroTailwind")):
            macro, _ = _derive_macro_market(sig)
            sig["triggerMacroTailwind"] = macro
        if not _has_value(sig.get("triggerMarketTailwind")):
            _, market = _derive_macro_market(sig)
            sig["triggerMarketTailwind"] = market

    if not _FUNDAMENTALS_AVAILABLE:
        return stats

    to_fetch: list[str] = []
    for sig in signals:
        needs_summary = not _has_value(sig.get("fundSummary"))
        needs_eps = not _has_value(sig.get("triggerEarningsGrowth"))
        needs_debt = not _has_value(sig.get("triggerDebtReduction"))
        if needs_summary or needs_eps or needs_debt:
            stats["needs_fundamentals"] += 1
            sym = str(sig.get("symbol", "")).strip().upper()
            if sym:
                to_fetch.append(sym)

    if not to_fetch:
        return stats

    provider = FundamentalsProvider(cache_dir=str(CACHE_DIR), cache_ttl_hours=24)
    fetched = provider.fetch_batch(sorted(set(to_fetch)), workers=min(12, max(1, len(to_fetch))), show_progress=False)

    for sig in signals:
        sym = str(sig.get("symbol", "")).strip().upper()
        fund = fetched.get(sym) or {}
        is_india = sym.endswith(".NS") or sym.endswith(".BO")

        if not _has_value(sig.get("fundSummary")):
            before = sig.get("fundSummary")
            sig["fundSummary"] = fundamentals_compact_summary(fund, is_india=is_india)
            if _has_value(sig.get("fundSummary")) and not _has_value(before):
                stats["fund_summary_filled"] += 1
        if not _has_value(sig.get("triggerEarningsGrowth")):
            before = sig.get("triggerEarningsGrowth")
            sig["triggerEarningsGrowth"] = _earnings_trigger_from_fundamentals(fund)
            if _has_value(sig.get("triggerEarningsGrowth")) and not _has_value(before):
                stats["earnings_filled"] += 1
        if not _has_value(sig.get("triggerDebtReduction")):
            before = sig.get("triggerDebtReduction")
            sig["triggerDebtReduction"] = _debt_trigger_from_fundamentals(fund)
            if _has_value(sig.get("triggerDebtReduction")) and not _has_value(before):
                stats["debt_filled"] += 1

    for sig in signals:
        if not _has_value(sig.get("fundSummary")):
            stats["still_missing_summary"] += 1
        if not _has_value(sig.get("triggerEarningsGrowth")):
            stats["still_missing_earnings"] += 1
        if not _has_value(sig.get("triggerDebtReduction")):
            stats["still_missing_debt"] += 1

    return stats

def load_signals() -> list[dict]:
    signals = []
    files = [
        ("vcp_hits_india_daily_full_LATEST.json",       "Daily"),
        ("vcp_hits_india_weekly_full_LATEST.json",      "Weekly"),
        ("portfolio_shortlist_india_daily_full_LATEST.json",  "Daily Portfolio"),
        ("vcp_hits_india_daily_vcp_LATEST.json",        "Daily VCP"),
        ("vcp_hits_india_daily_range_expansion_LATEST.json", "Daily RExp"),
    ]
    seen = {}
    for fname, label in files:
        p = OUTPUT / fname
        if not p.exists(): continue
        try:
            data = json.loads(p.read_text())
            if not isinstance(data, list): continue
            for row in data:
                sym = row.get("symbol","")
                if not sym:
                    continue
                row["_tf_label"] = label
                if sym in seen:
                    seen[sym] = _pick_better_row(seen[sym], row)
                else:
                    seen[sym] = row
        except Exception:
            pass
    return sorted(seen.values(), key=lambda x: -_f(x.get("score",0)))

def build_position_plan(sig: dict) -> dict:
    entry = _f(sig.get("entry") or sig.get("close"))
    sl    = _f(sig.get("sl"))
    t1    = _f(sig.get("T1"))
    t2    = _f(sig.get("T2"))
    t3    = _f(sig.get("T3"))
    risk  = entry - sl if sl and sl < entry else entry * 0.03
    if risk <= 0: risk = entry * 0.03

    shares  = int(math.floor(ACCOUNT_SIZE * RISK_PCT / risk)) if risk > 0 else 0
    capital = shares * entry
    rr_t1   = (t1 - entry) / risk if risk > 0 and t1 else 0
    rr_t2   = (t2 - entry) / risk if risk > 0 and t2 else 0
    rr_t3   = (t3 - entry) / risk if risk > 0 and t3 else 0
    max_loss = shares * risk
    t1_profit = shares * (t1 - entry) if t1 else 0
    t2_profit = shares * (t2 - entry) if t2 else 0
    t3_profit = shares * (t3 - entry) if t3 else 0

    return {
        "entry": entry, "sl": sl, "t1": t1, "t2": t2, "t3": t3,
        "risk": round(risk, 2), "shares": shares,
        "capital": round(capital, 0), "max_loss": round(max_loss, 0),
        "rr_t1": round(rr_t1, 2), "rr_t2": round(rr_t2, 2), "rr_t3": round(rr_t3, 2),
        "t1_profit": round(t1_profit, 0), "t2_profit": round(t2_profit, 0), "t3_profit": round(t3_profit, 0),
    }

def sparkline_svg(closes: list[float], width=120, height=40) -> str:
    if not closes or len(closes) < 2:
        return f'<svg width="{width}" height="{height}"><text x="5" y="20" fill="#555" font-size="10">N/A</text></svg>'
    mn, mx = min(closes), max(closes)
    span = mx - mn if mx != mn else 1.0
    pad = 4
    w, h = width - 2*pad, height - 2*pad

    pts = []
    for i, v in enumerate(closes):
        x = pad + i / max(len(closes) - 1, 1) * w
        y = pad + (1 - (v - mn) / span) * h
        pts.append(f"{x:.1f},{y:.1f}")

    color = "#3fb950" if closes[-1] >= closes[0] else "#f85149"
    fill_color = "#3fb95022" if closes[-1] >= closes[0] else "#f8514922"

    # Close polygon for fill
    fill_pts = pts + [f"{pad+w:.1f},{pad+h:.1f}", f"{pad:.1f},{pad+h:.1f}"]

    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polygon points="{" ".join(fill_pts)}" fill="{fill_color}" stroke="none"/>'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'</svg>')

def build_html(signals: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(signals)

    # Sector counts for summary
    sector_counts: dict[str, int] = {}
    setup_counts:  dict[str, int] = {}
    for s in signals:
        sec = get_sector(s.get("symbol",""))
        setup = s.get("setup","Other")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        setup_counts[setup] = setup_counts.get(setup, 0) + 1

    top_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])[:8]
    a_plus = sum(1 for s in signals if s.get("rating","") == "A+")
    a_rate  = sum(1 for s in signals if s.get("rating","") in ("A+","A"))

    # ── Build signal rows
    rows_html = []
    for i, sig in enumerate(signals):
        sym    = sig.get("symbol","")
        setup  = sig.get("setup","")
        rating = sig.get("rating","")
        sector = get_sector(sym)
        tf_lbl = sig.get("_tf_label","Daily")
        plan   = build_position_plan(sig)
        sparkline_data = load_sparkline(sym)
        svg = sparkline_svg(sparkline_data)
        is_weekly = tf_lbl.lower().startswith("weekly")
        price_rows = load_price_rows(sym, weekly=is_weekly)

        regime     = sig.get("regimeState","")
        regime_str = ("Favorable" if "FAV" in regime and "UNFAV" not in regime
                      else "Unfavorable" if "UNFAV" in regime else "Neutral")
        regime_cls = ("reg-fav" if regime_str == "Favorable"
                      else "reg-unfav" if regime_str == "Unfavorable" else "reg-neu")

        rs3m_raw = _f(sig.get("rs3m"))
        rs6m_raw = _f(sig.get("rs6m"))
        fallback_rs3m, fallback_rs6m = compute_rs_metrics(price_rows, is_weekly)
        rs3m = pick_metric(rs3m_raw, fallback_rs3m)
        rs6m = pick_metric(rs6m_raw, fallback_rs6m)
        rs3m_cls = "rna" if rs3m is None else ("rpl" if rs3m > 0 else "rmi")
        rs6m_cls = "rna" if rs6m is None else ("rpl" if rs6m > 0 else "rmi")

        setup_cls, setup_label, setup_tip = SETUP_META.get(
            setup, ("tag-bo", setup.replace("_"," "), ""))

        score = _f(sig.get("score",0))
        pivot = plan["entry"]  # entry IS the pivot area for current signals
        actual_pivot = _f(sig.get("pivot") or plan["entry"])

        width_pct  = min(score, 130) / 130 * 100
        score_color = "#3fb950" if score >= 100 else "#e3b341" if score >= 70 else "#f85149"

        vol_raw = _f(sig.get("vol%"))
        rexp_raw = _f(sig.get("rexp"))
        fallback_vol, fallback_rexp = current_expansion_metrics(price_rows)
        vol_pct = pick_metric(vol_raw, fallback_vol)
        rexp = pick_metric(rexp_raw, fallback_rexp)
        vol_pct_text = fmt_pct(vol_pct)
        rexp_text = fmt_x(rexp)
        rs3m_text = fmt_pct(rs3m, signed=True)
        rs6m_text = fmt_pct(rs6m, signed=True)
        window  = sig.get("window","")
        dist_pivot = _f(sig.get("distFromPivot%") or sig.get("pivotProximityScore"))

        eps_trigger = str(
            sig.get("triggerEarningsGrowth")
            or sig.get("earningsTrigger")
            or sig.get("earnings")
            or "UNKNOWN"
        )
        debt_trigger = str(
            sig.get("triggerDebtReduction")
            or sig.get("debtTrigger")
            or sig.get("debt")
            or "UNKNOWN"
        )
        macro_trigger = str(
            sig.get("triggerMacroTailwind")
            or sig.get("macroTrigger")
            or sig.get("triggerMacro")
            or "NEUTRAL_OR_HEADWIND"
        )
        market_trigger = str(
            sig.get("triggerMarketTailwind")
            or sig.get("marketTrigger")
            or sig.get("triggerMarket")
            or "MIXED"
        )
        fund_summary = str(
            sig.get("fundSummary")
            or sig.get("fundamentalSummary")
            or sig.get("fundamentals")
            or "FUNDAMENTALS_UNAVAILABLE"
        )

        eps_yoy = extract_pct(eps_trigger, ["EPS_YOY", "EPS YOY"])
        eps_qoq = extract_pct(eps_trigger, ["EPS_QOQ", "EPS QOQ"])
        debt_yoy = extract_pct(debt_trigger, ["DEBT_YOY", "DEBT YOY"])
        debt_qoq = extract_pct(debt_trigger, ["DEBT_QOQ", "DEBT QOQ"])
        if debt_yoy is None and debt_qoq is None:
            debt_proxy = extract_debt_change(debt_trigger)
            debt_yoy = debt_proxy

        eps_yoy_text = fmt_metric(eps_yoy)
        eps_qoq_text = fmt_metric(eps_qoq)
        debt_yoy_text = fmt_metric(debt_yoy)
        debt_qoq_text = fmt_metric(debt_qoq)

        eps_cls = "metric-na" if eps_yoy is None and eps_qoq is None else ("metric-pos" if ((eps_yoy or 0) >= 0 or (eps_qoq or 0) >= 0) else "metric-neg")
        debt_cls = "metric-na" if debt_yoy is None and debt_qoq is None else ("metric-neg" if ((debt_yoy or 0) > 0 or (debt_qoq or 0) > 0) else "metric-pos")

        eps_trigger_html = escape(eps_trigger)
        debt_trigger_html = escape(debt_trigger)
        macro_trigger_html = escape(macro_trigger)
        market_trigger_html = escape(market_trigger)
        fund_summary_html = escape(fund_summary)

        rows_html.append(f"""
<div class="sig-card" data-symbol="{sym}" data-setup="{setup}" data-rating="{rating}" data-sector="{sector}">
  <div class="sig-header">
    <div class="sig-left">
      <div class="sig-sym">{sym.replace('.NS','')}</div>
      <div class="sig-meta">
        <span class="badge-sec">{sector}</span>
        <span class="badge-tf">{tf_lbl}</span>
        <span class="{setup_cls} sig-tag" title="{setup_tip}">{setup_label}</span>
      </div>
    </div>
    <div class="sig-right">
      <div class="sig-sparkline">{svg}</div>
      <div class="sig-rating {'rat-aplus' if rating=='A+' else 'rat-a' if rating=='A' else 'rat-b'}">{rating}</div>
    </div>
  </div>

  <div class="score-bar-wrap" title="Score: {score:.1f}/130">
    <div class="score-bar-fill" style="width:{width_pct:.0f}%;background:{score_color}"></div>
    <span class="score-label">Score {score:.1f}</span>
  </div>

  <div class="plan-grid">
    <div class="plan-section">
      <div class="plan-title">Entry Zone</div>
      <div class="plan-value entry-val">&#8377;{plan['entry']:.2f}</div>
      <div class="plan-sub">Pivot: {actual_pivot:.2f} &nbsp;|&nbsp; Window: {window}</div>
    </div>
    <div class="plan-section">
      <div class="plan-title">Stop Loss</div>
      <div class="plan-value sl-val">&#8377;{plan['sl']:.2f}</div>
      <div class="plan-sub">Risk/share: &#8377;{plan['risk']:.2f} ({plan['risk']/plan['entry']*100:.1f}%)</div>
    </div>
    <div class="plan-section highlight">
      <div class="plan-title">Position Size</div>
      <div class="plan-value pos-val">{plan['shares']:,} shares</div>
      <div class="plan-sub">Capital: &#8377;{plan['capital']:,.0f} &nbsp;|&nbsp; Max Loss: &#8377;{plan['max_loss']:,.0f}</div>
    </div>
  </div>

  <div class="sig-footer">
    <div class="sig-stat">
      <span class="sstat-label">Regime</span>
      <span class="{regime_cls}">{regime_str}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 3M</span>
      <span class="{rs3m_cls}">{rs3m_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 6M</span>
      <span class="{rs6m_cls}">{rs6m_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Vol %</span>
      <span style="color:#79c0ff">{vol_pct_text}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RExp</span>
      <span style="color:#e3b341">{rexp_text}</span>
    </div>
  </div>

  <div class="insight-chip" title="Hover card for fundamentals and macro trigger details">Fundamentals + Macro</div>
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
        <div class="insight-pill {classify_trigger(macro_trigger)}">{macro_trigger_html}</div>
      </div>
      <div class="insight-item">
        <div class="insight-label">Market Trigger</div>
        <div class="insight-pill {classify_trigger(market_trigger)}">{market_trigger_html}</div>
      </div>
    </div>
    <div class="insight-summary" title="Online fundamentals summary">{fund_summary_html}</div>
    <div class="insight-raw">
      <div><b>EPS:</b> {eps_trigger_html}</div>
      <div><b>Debt:</b> {debt_trigger_html}</div>
    </div>
  </div>
</div>""")

    sector_pills = "".join(
        f'<span class="sector-pill" onclick="filterSector(\'{s}\')">{s} <b>{c}</b></span>'
        for s, c in top_sectors
    )

    rows_str = "\n".join(rows_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Plans - Live Breakout Signals | {now}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:0}}

/* TOP BAR */
.topbar{{background:linear-gradient(135deg,#0d1117,#1a2433);border-bottom:1px solid #21262d;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.topbar-title{{color:#79c0ff;font-size:1.3em;font-weight:700}}
.topbar-sub{{color:#8b949e;font-size:.82em;margin-top:3px}}
.topbar-stats{{display:flex;gap:16px;flex-wrap:wrap}}
.tstat{{text-align:center}}
.tstat-v{{font-size:1.4em;font-weight:700;color:#58a6ff}}
.tstat-l{{font-size:.72em;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}}

/* CONTROLS */
.controls-bar{{background:#161b22;border-bottom:1px solid #21262d;padding:14px 28px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:72px;z-index:40}}
.search-box,.sel{{padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:.85em}}
.search-box{{min-width:200px}}
.btn-filter{{padding:7px 14px;border:1px solid #30363d;border-radius:6px;background:transparent;color:#79c0ff;cursor:pointer;font-size:.82em;transition:all .15s}}
.btn-filter:hover,.btn-filter.active{{background:#1f6feb;border-color:#58a6ff;color:#fff}}
.btn-export{{padding:7px 14px;border:1px solid #2ea043;border-radius:6px;background:transparent;color:#3fb950;cursor:pointer;font-size:.82em}}
.btn-export:hover{{background:#2ea04322}}

/* SECTOR PILLS */
.sector-row{{padding:10px 28px;background:#0d1117;border-bottom:1px solid #21262d;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.sector-pill{{padding:4px 12px;border-radius:99px;border:1px solid #30363d;color:#8b949e;font-size:.78em;cursor:pointer;transition:all .15s}}
.sector-pill:hover,.sector-pill.active{{border-color:#58a6ff;color:#58a6ff;background:#1f6feb1a}}
.sector-pill b{{color:#c9d1d9}}

/* MAIN GRID */
.main{{padding:20px 28px}}
.signals-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}}

/* SIGNAL CARD */
.sig-card{{background:linear-gradient(180deg,#161b22 0%,#0f141a 100%);border:1px solid #21262d;border-radius:14px;overflow:hidden;transition:all .2s}}
.sig-card:hover{{border-color:#30363d;box-shadow:0 8px 24px rgba(0,0,0,.3);transform:translateY(-2px)}}
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

.sig-right{{display:flex;flex-direction:column;align-items:flex-end;gap:6px}}
.sig-sparkline svg{{display:block}}
.sig-rating{{font-size:1em;font-weight:800;padding:2px 8px;border-radius:4px}}
.rat-aplus{{background:#2a2a0a;color:#ffd700;border:1px solid #ffd70044}}
.rat-a{{background:#1e1b4b;color:#a5b4fc;border:1px solid #a5b4fc44}}
.rat-b{{background:#1a2a3a;color:#7dd3fc;border:1px solid #7dd3fc44}}

/* SCORE BAR */
.score-bar-wrap{{margin:0 16px 10px;background:#0d1117;border-radius:4px;height:6px;position:relative}}
.score-bar-fill{{height:100%;border-radius:4px;transition:width .5s}}
.score-label{{position:absolute;right:0;top:-16px;font-size:.7em;color:#8b949e}}

/* PLAN GRID */
.plan-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:#21262d;margin:0 0 0 0}}
.plan-section{{background:#0f141a;padding:10px 14px}}
.plan-section.highlight{{background:#111a22}}
.plan-title{{font-size:.7em;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;font-weight:600}}
.plan-title small{{color:#58a6ff;font-size:.9em;text-transform:none;font-weight:600}}
.plan-value{{font-size:1em;font-weight:700;margin-bottom:2px}}
.plan-sub{{font-size:.72em;color:#6e7681}}
.entry-val{{color:#79c0ff}}
.sl-val{{color:#f85149}}
.t1-val{{color:#3fb950}}
.t2-val{{color:#2ea043}}
.t3-val{{color:#1a7431}}
.pos-val{{color:#e3b341}}

/* FOOTER */
.sig-footer{{display:flex;gap:0;border-top:1px solid #21262d;padding:10px 16px;flex-wrap:wrap;gap:12px}}
.sig-stat{{display:flex;flex-direction:column;align-items:center}}
.sstat-label{{font-size:.68em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px}}
.reg-fav{{color:#3fb950;font-weight:600;font-size:.82em}}
.reg-unfav{{color:#f85149;font-weight:600;font-size:.82em}}
.reg-neu{{color:#e3b341;font-weight:600;font-size:.82em}}
.rpl{{color:#3fb950;font-weight:600;font-size:.82em}}
.rmi{{color:#f85149;font-weight:600;font-size:.82em}}
.rna{{color:#8b949e;font-weight:600;font-size:.82em}}

/* HOVER INSIGHTS */
.insight-chip{{margin:8px 16px 0;display:inline-flex;padding:2px 8px;border:1px solid #2f3b4b;border-radius:12px;color:#7dd3fc;font-size:.7em;background:#0f1a26}}
.sig-insight{{max-height:0;opacity:0;overflow:hidden;padding:0 16px;transition:max-height .25s ease,opacity .2s ease,padding .2s ease;border-top:0 solid #21262d}}
.sig-card:hover .sig-insight,.sig-card:focus-within .sig-insight{{max-height:180px;opacity:1;padding:10px 16px 12px;border-top:1px solid #21262d}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}}
.insight-item{{background:#0d1117;border:1px solid #263344;border-radius:6px;padding:6px 8px}}
.insight-label{{font-size:.64em;color:#8b949e;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px}}
.insight-value{{font-size:.74em;font-weight:600}}
.metric-pos{{color:#3fb950}}
.metric-neg{{color:#f85149}}
.metric-na{{color:#8b949e}}
.insight-pill{{display:inline-block;padding:2px 6px;border-radius:10px;font-size:.7em;border:1px solid transparent;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pill-pos{{color:#86efac;background:#102217;border-color:#1f6f3a}}
.pill-neg{{color:#fda4af;background:#261116;border-color:#7a2232}}
.pill-neu{{color:#cbd5e1;background:#18202c;border-color:#334155}}
.insight-summary{{font-size:.72em;color:#94a3b8;line-height:1.35;margin-bottom:4px}}
.insight-raw{{font-size:.68em;color:#7f8a98;line-height:1.35}}

/* NO RESULTS */
.no-results{{text-align:center;padding:60px;color:#8b949e;font-size:1.1em}}

/* REGIME BANNER */
.regime-banner{{background:linear-gradient(135deg,#1a1a2e,#2a1a1a);border:1px solid #30363d;border-radius:10px;padding:14px 20px;margin:20px 28px 0;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.banner-icon{{font-size:1.5em}}
.banner-text{{flex:1}}
.banner-title{{color:#f85149;font-weight:700;font-size:.95em}}
.banner-desc{{color:#8b949e;font-size:.82em;margin-top:3px;line-height:1.5}}

/* LEGEND */
.legend{{display:flex;gap:16px;flex-wrap:wrap;padding:0 28px;margin-bottom:16px;font-size:.78em}}
.leg-item{{display:flex;align-items:center;gap:6px;color:#8b949e}}
.leg-dot{{width:10px;height:10px;border-radius:2px}}

/* RISK BOX */
.risk-box{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 20px;margin:16px 28px 0;font-size:.82em;color:#8b949e;line-height:1.8}}
.risk-box strong{{color:#79c0ff}}

@media (max-width: 640px){{
  .insight-grid{{grid-template-columns:1fr}}
  .sig-card:hover .sig-insight,.sig-card:focus-within .sig-insight{{max-height:240px}}
}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">&#127919; Live Breakout Trade Plans &mdash; NSE India</div>
    <div class="topbar-sub">All active signals from latest scan &bull; {now}</div>
  </div>
  <div class="topbar-stats">
    <div class="tstat"><div class="tstat-v">{total}</div><div class="tstat-l">Signals</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#ffd700">{a_plus}</div><div class="tstat-l">A+ Rated</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{a_rate}</div><div class="tstat-l">A &amp; Above</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#86efac">{setup_counts.get('RANGE_EXPANSION',0)}</div><div class="tstat-l">Range Exp</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{setup_counts.get('VCP',0)}</div><div class="tstat-l">VCP</div></div>
  </div>
</div>

<div class="regime-banner">
  <div class="banner-icon">&#9888;</div>
  <div class="banner-text">
    <div class="banner-title">Market Regime: UNFAVORABLE &mdash; Operate with Reduced Size</div>
    <div class="banner-desc">
      Current scan shows UNFAVORABLE regime. Nifty below key moving averages. FII net selling.
      Recommended: Reduce position size to 50% of normal. Only trade A+ rated setups.
      Wait for regime to shift to NEUTRAL or FAVORABLE before deploying full capital.
    </div>
  </div>
</div>

<div class="risk-box">
  <strong>Position Sizing (1% Risk, &#8377;{ACCOUNT_SIZE/100000:.0f}L Account):</strong>
  &nbsp;Shares = floor(Account &times; 1%) / (Entry &minus; Stop)
  &nbsp;|&nbsp; <strong>T1</strong> = Entry + 1.5&times;Risk (35% exit)
  &nbsp;|&nbsp; <strong>T2</strong> = Entry + 2.5&times;Risk (40% exit)
  &nbsp;|&nbsp; <strong>T3</strong> = Entry + 4.0&times;Risk (25% exit)
  &nbsp;|&nbsp; Stop = 10-bar swing low (max 4% below entry)
</div>

<div class="controls-bar">
  <input class="search-box" id="searchBox" placeholder="&#128269; Search symbol, sector..." oninput="applyFilters()">
  <select class="sel" id="setupFilter" onchange="applyFilters()">
    <option value="">All Setups</option>
    <option value="RANGE_EXPANSION">Range Expansion</option>
    <option value="VCP">VCP</option>
    <option value="MEAN_REVERSION">Mean Reversion</option>
    <option value="BREAKOUT_PULLBACK">Breakout Pullback</option>
  </select>
  <select class="sel" id="ratingFilter" onchange="applyFilters()">
    <option value="">All Ratings</option>
    <option value="A+">A+ Only</option>
    <option value="A">A &amp; Above</option>
    <option value="B">B &amp; Above</option>
  </select>
  <button class="btn-filter" onclick="toggleSort('score')" id="btn-sort-score">&#128202; Sort: Score</button>
  <button class="btn-filter" onclick="toggleSort('symbol')" id="btn-sort-sym">&#9776; Sort: Symbol</button>
  <button class="btn-export" onclick="exportCSV()">&#8659; Export CSV</button>
  <span id="filterCount" style="color:#8b949e;font-size:.83em;margin-left:8px"></span>
</div>

<div class="sector-row">
  <span style="color:#8b949e;font-size:.8em;font-weight:600">Sector:</span>
  <span class="sector-pill active" onclick="filterSector('')">All</span>
  {sector_pills}
</div>

<div class="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#a5b4fc"></div>VCP Breakout</div>
  <div class="leg-item"><div class="leg-dot" style="background:#86efac"></div>Range Expansion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#7dd3fc"></div>Mean Reversion</div>
  <div class="leg-item"><div class="leg-dot" style="background:#d8b4fe"></div>Breakout Pullback</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700"></div>A+ Rating</div>
  <div class="leg-item"><div class="leg-dot" style="background:#3fb950"></div>RS Positive</div>
</div>

<div class="main">
  <div class="signals-grid" id="signalsGrid">
    {rows_str}
  </div>
  <div class="no-results" id="noResults" style="display:none">No signals match your filters.</div>
</div>

<script>
let activeSector = '';
let sortMode = 'score';

function applyFilters() {{
  const q     = document.getElementById('searchBox').value.toLowerCase();
  const setup = document.getElementById('setupFilter').value;
  const rating= document.getElementById('ratingFilter').value;
  let visible = 0;
  document.querySelectorAll('.sig-card').forEach(card => {{
    const sym    = (card.dataset.symbol||'').toLowerCase();
    const sec    = (card.dataset.sector||'').toLowerCase();
    const csetup = card.dataset.setup||'';
    const crate  = card.dataset.rating||'';
    let show = (sym.includes(q) || sec.includes(q));
    if(setup && csetup !== setup) show = false;
    if(rating === 'A+' && crate !== 'A+') show = false;
    if(rating === 'A'  && crate !== 'A+' && crate !== 'A') show = false;
    if(rating === 'B'  && crate === 'C') show = false;
    if(activeSector && (card.dataset.sector||'') !== activeSector) show = false;
    card.style.display = show ? '' : 'none';
    if(show) visible++;
  }});
  document.getElementById('filterCount').textContent = visible + ' shown';
  document.getElementById('noResults').style.display = visible === 0 ? '' : 'none';
}}

function filterSector(sec) {{
  activeSector = sec;
  document.querySelectorAll('.sector-pill').forEach(p => p.classList.remove('active'));
  const pills = document.querySelectorAll('.sector-pill');
  pills.forEach(p => {{ if(p.onclick.toString().includes("'" + sec + "'") || (sec==='' && p.onclick.toString().includes("''"))) p.classList.add('active'); }});
  applyFilters();
}}

function toggleSort(mode) {{
  sortMode = mode;
  const grid = document.getElementById('signalsGrid');
  const cards = [...grid.querySelectorAll('.sig-card')];
  cards.sort((a, b) => {{
    if(mode === 'symbol') return (a.dataset.symbol||'').localeCompare(b.dataset.symbol||'');
    return 0; // score order is default DOM order
  }});
  cards.forEach(c => grid.appendChild(c));
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-sort-' + (mode==='score'?'score':'sym')).classList.add('active');
}}

function exportCSV() {{
  const rows = [['Symbol','Sector','Setup','Rating','Entry','Stop','Shares','Regime','RS3M','RS6M','VolPct','RExp','EPSGrowth','DebtChange','MacroTrigger','MarketTrigger','FundSummary']];
  document.querySelectorAll('.sig-card').forEach(card => {{
    if(card.style.display === 'none') return;
    const planVals = [...card.querySelectorAll('.plan-value')].map(v => v.textContent.replace(/[₹,]/g,'').trim());
    const stats = [...card.querySelectorAll('.sig-stat span:last-child')].map(v => v.textContent.trim());
    const epsGrowth = card.querySelector('.insight-item:nth-child(1) .insight-value')?.textContent?.trim() || '';
    const debtChange = card.querySelector('.insight-item:nth-child(2) .insight-value')?.textContent?.trim() || '';
    const macroTrigger = card.querySelector('.insight-item:nth-child(3) .insight-pill')?.textContent?.trim() || '';
    const marketTrigger = card.querySelector('.insight-item:nth-child(4) .insight-pill')?.textContent?.trim() || '';
    const fundSummary = card.querySelector('.insight-summary')?.textContent?.trim() || '';
    rows.push([
      card.dataset.symbol,
      card.dataset.sector,
      card.dataset.setup,
      card.dataset.rating,
      planVals[0] || '',
      planVals[1] || '',
      planVals[2] || '',
      stats[0] || '',
      stats[1] || '',
      stats[2] || '',
      stats[3] || '',
      stats[4] || '',
      epsGrowth,
      debtChange,
      macroTrigger,
      marketTrigger,
      fundSummary,
    ]);
  }});
  const csv = rows.map(r => r.map(v => '"'+String(v)+'"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'trade_plans_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}

// Initial count
document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('filterCount').textContent = '{total} shown';
}});
</script>
</body>
</html>"""

def main():
    print("Generating Trade Plans page...")
    signals = load_signals()
    hstats = hydrate_missing_fundamentals(signals)
    print(f"  Loaded {len(signals)} unique signals")
    if hstats.get("needs_fundamentals", 0) > 0:
        print(
            "  Fundamentals hydration: "
            f"needed={hstats.get('needs_fundamentals', 0)} "
            f"summary+={hstats.get('fund_summary_filled', 0)} "
            f"eps+={hstats.get('earnings_filled', 0)} "
            f"debt+={hstats.get('debt_filled', 0)}"
        )
        if not hstats.get("yfinance_available", False):
            print("  Warning: fundamentals provider unavailable (install yfinance)")
        if hstats.get("still_missing_summary", 0) > 0 or hstats.get("still_missing_earnings", 0) > 0:
            print(
                "  Remaining missing fundamentals: "
                f"summary={hstats.get('still_missing_summary', 0)} "
                f"eps={hstats.get('still_missing_earnings', 0)} "
                f"debt={hstats.get('still_missing_debt', 0)}"
            )
    html = build_html(signals)
    out = OUTPUT / "trade_plans_live.html"
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"  Output: {out}")
    print(f"  Size: {size:.1f} KB")

if __name__ == "__main__":
    main()

