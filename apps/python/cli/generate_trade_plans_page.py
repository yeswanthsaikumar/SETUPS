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
RUN_HISTORY_JSON = OUTPUT / "trade_plans_run_history.json"
RUN_HISTORY_MAX  = 20   # keep last N runs for appearance tracking
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

try:
    from mutual_funds_provider import MutualFundsProvider, swing_context as mf_swing_context
    _MF_AVAILABLE = True
except Exception:
    MutualFundsProvider = None
    _MF_AVAILABLE = False

    def mf_swing_context(_d: dict) -> dict:
        return {}

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
    "BULL_FLAG":         ("tag-bf",    "Bull Flag",          "Sharp pole + tight flag channel. Enter on breakout above flag high. Targets = flagpole measured move."),
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


# ── Run-history helpers ──────────────────────────────────────────────────────

def load_run_history() -> dict:
    """Load the persisted run-history JSON (last RUN_HISTORY_MAX runs)."""
    if not RUN_HISTORY_JSON.exists():
        return {"runs": []}
    try:
        return json.loads(RUN_HISTORY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": []}


def save_run_history(history: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RUN_HISTORY_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def update_run_history(signals: list[dict]) -> dict:
    """
    Append the current run's symbols to the history, trimming to RUN_HISTORY_MAX.
    Returns the updated history dict.
    """
    history = load_run_history()
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbols": sorted({s.get("symbol", "") for s in signals if s.get("symbol")}),
    }
    runs: list[dict] = history.get("runs", [])
    runs.append(entry)
    # Keep only the most recent RUN_HISTORY_MAX runs
    history["runs"] = runs[-RUN_HISTORY_MAX:]
    save_run_history(history)
    return history


def count_appearances(symbol: str, history: dict) -> tuple[int, int]:
    """
    Return (count, total_runs) where count = number of runs in history
    that contain this symbol.
    """
    runs = history.get("runs", [])
    count = sum(1 for r in runs if symbol in r.get("symbols", []))
    return count, len(runs)


# ── Price-performance helpers ────────────────────────────────────────────────

def compute_price_performance(rows: list[dict]) -> dict:
    """
    Given daily OHLCV rows (sorted oldest→newest), compute price returns
    for 1W (5 bars), 1M (21 bars), 3M (63 bars), 6M (126 bars).
    Returns dict with keys: ret_1w, ret_1m, ret_3m, ret_6m (float|None).
    """
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close")) > 0]
    if not closes:
        return {"ret_1w": None, "ret_1m": None, "ret_3m": None, "ret_6m": None}

    def _ret(bars: int) -> float | None:
        if len(closes) <= bars:
            return None
        base = closes[-(bars + 1)]
        if base <= 0:
            return None
        return (closes[-1] / base - 1.0) * 100.0

    return {
        "ret_1w": _ret(5),
        "ret_1m": _ret(21),
        "ret_3m": _ret(63),
        "ret_6m": _ret(126),
    }


def fmt_perf(value: float | None) -> str:
    """Format a performance return value as coloured HTML span."""
    if value is None:
        return '<span class="perf-na">—</span>'
    cls = "perf-up" if value >= 0 else "perf-dn"
    sign = "+" if value >= 0 else ""
    return f'<span class="{cls}">{sign}{value:.1f}%</span>'


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
    files = [
        ("vcp_hits_india_daily_full_LATEST.json",       "Daily"),
        ("vcp_hits_india_weekly_full_LATEST.json",      "Weekly"),
        ("portfolio_shortlist_india_daily_full_LATEST.json",  "Daily Portfolio"),
        ("vcp_hits_india_daily_vcp_LATEST.json",        "Daily VCP"),
        ("vcp_hits_india_daily_range_expansion_LATEST.json", "Daily RExp"),
    ]
    seen: dict[str, dict] = {}
    # Track all unique (setup_type, tf_label) pairs per symbol
    seen_setups: dict[str, list[tuple[str, str]]] = {}

    for fname, label in files:
        p = OUTPUT / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            if not isinstance(data, list):
                continue
            for row in data:
                sym = row.get("symbol", "")
                if not sym:
                    continue
                row["_tf_label"] = label
                setup = row.get("setup", "")
                if sym in seen:
                    seen[sym] = _pick_better_row(seen[sym], row)
                    # Accumulate additional setups (avoid strict duplicates)
                    existing = seen_setups.setdefault(sym, [])
                    if (setup, label) not in existing:
                        existing.append((setup, label))
                else:
                    seen[sym] = row
                    seen_setups[sym] = [(setup, label)]
        except Exception:
            pass

    # Attach the consolidated multi-setup list to each winning row
    for sym, row in seen.items():
        all_s = seen_setups.get(sym, [(row.get("setup", ""), row.get("_tf_label", ""))])
        # Deduplicate by setup type (keep first occurrence of each type)
        seen_types: set[str] = set()
        unique: list[tuple[str, str]] = []
        for st, lbl in all_s:
            if st and st not in seen_types:
                seen_types.add(st)
                unique.append((st, lbl))
        row["_all_setups"] = unique  # list of (setup_type, tf_label)

    return sorted(seen.values(), key=lambda x: -_f(x.get("score", 0)))

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

def _build_bf_html(sig: dict) -> str:
    """Render the Bull Flag detail panel embedded in a signal card."""
    pole_gain    = _f(sig.get("bfPoleGain%")   or sig.get("height%"))
    flag_decline = _f(sig.get("bfFlagDecline%") or sig.get("depth%"))
    flag_bars    = sig.get("bfFlagBars")   or sig.get("len") or "—"
    flag_vol     = _f(sig.get("bfFlagVolRatio") or sig.get("mrPullbackVolRatio"))
    tightness    = _f(sig.get("bfTightnessRatio") or 0)
    pole_vol     = _f(sig.get("bfPoleVolRatio")   or 0)
    flag_high    = _f(sig.get("bfFlagHigh")  or sig.get("pivot"))
    flag_low     = _f(sig.get("bfFlagLow")   or sig.get("sl"))
    pole_start   = sig.get("bfPoleStartDate", "")
    pole_top     = sig.get("bfPoleTopDate",   "")
    t1           = _f(sig.get("T1"))
    t2           = _f(sig.get("T2"))
    t3           = _f(sig.get("T3"))
    subtype      = str(sig.get("setupSubtype") or "")

    # Subtype badge
    if subtype == "FLAG_BREAKOUT":
        st_cls, st_lbl = "bf-st-breakout", "🚀 Breaking Out"
    else:
        st_cls, st_lbl = "bf-st-forming",  "⏳ Flag Forming"

    # Format helpers
    def pct(v): return f"{v:.1f}%" if v else "—"
    def px(v):  return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"

    vol_color = "#4ade80" if flag_vol and flag_vol < 0.75 else "#e3b341" if flag_vol and flag_vol < 0.9 else "#f87171"

    dates_html = ""
    if pole_start or pole_top:
        dates_html = (
            f'<div style="font-size:.62em;color:#6e7681;margin-top:4px">'
            f'Pole: {escape(str(pole_start))} → {escape(str(pole_top))}</div>'
        )

    return f"""<div class="bf-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#34d399;font-weight:700;letter-spacing:.3px">🏴 BULL FLAG METRICS</span>
    <span class="bf-subtype {st_cls}">{st_lbl}</span>
  </div>
  <div class="bf-row">
    <div class="bf-cell">
      <div class="bf-lbl">Pole Gain</div>
      <div class="bf-val bf-pole">{pct(pole_gain)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Flag Decline</div>
      <div class="bf-val bf-flag">{pct(flag_decline)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Flag Bars</div>
      <div class="bf-val" style="color:#94a3b8">{flag_bars}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Vol Dry-up</div>
      <div class="bf-val" style="color:{vol_color}">{ratio(flag_vol)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Tightness</div>
      <div class="bf-val bf-vol">{ratio(tightness)}</div>
    </div>
    <div class="bf-cell">
      <div class="bf-lbl">Pole Vol</div>
      <div class="bf-val" style="color:#c084fc">{ratio(pole_vol)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>Flag High: <b style="color:#e2e8f0">{px(flag_high)}</b></span>
    <span>Flag Low: <b style="color:#e2e8f0">{px(flag_low)}</b></span>
  </div>
  <div class="bf-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="bf-t bf-t1">T1 {px(t1)}</span>
    <span class="bf-t bf-t2">T2 {px(t2)}</span>
    <span class="bf-t bf-t3">T3 {px(t3)}</span>
  </div>
  {dates_html}
</div>"""


def _build_rexp_html(sig: dict) -> str:
    """Render the Range Expansion detail panel embedded in a signal card."""
    rexp_val     = _f(sig.get("rexp") or 0)
    vol_pct      = _f(sig.get("vol%") or 0)
    range_pct    = _f(sig.get("range%") or sig.get("rangePct") or 0)
    height_pct   = _f(sig.get("height%") or 0)
    base_len     = sig.get("len") or sig.get("windowDays") or "—"
    subtype      = str(sig.get("setupSubtype") or "")
    pivot        = _f(sig.get("pivot") or 0)
    t1           = _f(sig.get("T1") or 0)
    t2           = _f(sig.get("T2") or 0)
    t3           = _f(sig.get("T3") or 0)
    dist_pct     = _f(sig.get("distFromPivot%") or sig.get("dist%") or 0)
    days_above   = sig.get("daysAbovePivot") or "—"

    def pct(v):   return f"{v:.1f}%" if v else "—"
    def px(v):    return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"
    def spct(v, pos_good=True):
        if not v: return "—"
        cls = "rexp-pos" if (v >= 0) == pos_good else "rexp-neg"
        sign = "+" if v >= 0 else ""
        return f'<span class="{cls}">{sign}{v:.1f}%</span>'

    # Colour the RExp ratio: >2x = green, 1.5-2x = yellow, <1.5x = muted
    rexp_color = "#4ade80" if rexp_val >= 2.0 else "#e3b341" if rexp_val >= 1.5 else "#94a3b8"
    vol_color  = "#4ade80" if vol_pct >= 100 else "#e3b341" if vol_pct >= 50 else "#94a3b8"

    # Subtype badge
    st_map = {
        "RANGE_EXPANSION_BREAKOUT": ("rexp-st-bo",  "🚀 Breakout Bar"),
        "WATCHLIST":                ("rexp-st-wl",  "⏳ Pre-Breakout"),
    }
    st_cls, st_lbl = st_map.get(subtype, ("rexp-st-bo", f"📊 {subtype}" if subtype else "📊 Expansion"))

    return f"""<div class="rexp-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#86efac;font-weight:700;letter-spacing:.3px">📊 RANGE EXPANSION METRICS</span>
    <span class="rexp-subtype {st_cls}">{st_lbl}</span>
  </div>
  <div class="rexp-row">
    <div class="rexp-cell">
      <div class="rexp-lbl">RExp Ratio</div>
      <div class="rexp-val" style="color:{rexp_color}">{ratio(rexp_val)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Vol Spike</div>
      <div class="rexp-val" style="color:{vol_color}">{spct(vol_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Bar Range</div>
      <div class="rexp-val" style="color:#94a3b8">{pct(range_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Base Height</div>
      <div class="rexp-val" style="color:#7dd3fc">{pct(height_pct)}</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Base Len</div>
      <div class="rexp-val" style="color:#94a3b8">{base_len}d</div>
    </div>
    <div class="rexp-cell">
      <div class="rexp-lbl">Dist Pivot</div>
      <div class="rexp-val" style="color:#c084fc">{pct(dist_pct)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>Pivot: <b style="color:#e2e8f0">{px(pivot)}</b></span>
    <span>Days above pivot: <b style="color:#86efac">{days_above}</b></span>
  </div>
  <div class="rexp-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="rexp-t rexp-t1">T1 {px(t1)}</span>
    <span class="rexp-t rexp-t2">T2 {px(t2)}</span>
    <span class="rexp-t rexp-t3">T3 {px(t3)}</span>
  </div>
</div>"""


def _build_bp_html(sig: dict) -> str:
    """Render the Breakout Pullback detail panel embedded in a signal card."""
    bo_date       = str(sig.get("abfpBreakoutDate") or "")
    bo_level      = _f(sig.get("pivot") or 0)
    peak_high     = _f(sig.get("abfpPeakHigh") or sig.get("max_after_breakout") or 0)
    pullback_dep  = _f(sig.get("abfpPullbackDepth%") or sig.get("height%") or 0)
    run_from_bo   = _f(sig.get("abfpRunFromBO%")     or sig.get("depth%") or 0)
    bars_since    = sig.get("abfpBarsSincePeak")      or sig.get("len") or "—"
    vol_ratio     = _f(sig.get("abfpPullbackVolRatio") or sig.get("pullback_vol_ratio") or 0)
    days_above    = sig.get("daysAbovePivot") or "—"
    dist_from_bo  = _f(sig.get("distFromPivot%") or 0)
    t1            = _f(sig.get("T1") or 0)
    t2            = _f(sig.get("T2") or 0)
    t3            = _f(sig.get("T3") or 0)
    subtype       = str(sig.get("setupSubtype") or "FIRST_PULLBACK")

    def pct(v):   return f"{v:.1f}%" if v else "—"
    def px(v):    return f"₹{v:.2f}" if v else "—"
    def ratio(v): return f"{v:.2f}×" if v else "—"

    # Volume dry-up quality
    if vol_ratio > 0:
        if vol_ratio < 0.70:
            vol_color = "#4ade80"
            vol_label = "Excellent Dry-up"
        elif vol_ratio < 0.85:
            vol_color = "#86efac"
            vol_label = "Good Dry-up"
        elif vol_ratio < 1.00:
            vol_color = "#e3b341"
            vol_label = "Mild Dry-up"
        else:
            vol_color = "#f87171"
            vol_label = "No Dry-up"
    else:
        vol_color, vol_label = "#94a3b8", "—"

    # Pullback depth quality
    if pullback_dep < 5.0:
        dep_color = "#4ade80"   # very tight
    elif pullback_dep < 8.0:
        dep_color = "#e3b341"   # acceptable
    else:
        dep_color = "#f87171"   # too deep

    return f"""<div class="bp-panel">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:.7em;color:#d8b4fe;font-weight:700;letter-spacing:.3px">🔁 BREAKOUT PULLBACK METRICS</span>
    <span class="bp-subtype">⏪ {subtype.replace('_',' ').title()}</span>
  </div>
  <div class="bp-row">
    <div class="bp-cell">
      <div class="bp-lbl">BO Support</div>
      <div class="bp-val" style="color:#79c0ff">{px(bo_level)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Post-BO Peak</div>
      <div class="bp-val" style="color:#4ade80">{px(peak_high)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Run from BO</div>
      <div class="bp-val" style="color:#86efac">+{pct(run_from_bo)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Pullback</div>
      <div class="bp-val" style="color:{dep_color}">-{pct(pullback_dep)}</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Bars Since Peak</div>
      <div class="bp-val" style="color:#94a3b8">{bars_since}d</div>
    </div>
    <div class="bp-cell">
      <div class="bp-lbl">Vol Dry-up</div>
      <div class="bp-val" style="color:{vol_color}" title="{vol_label}">{ratio(vol_ratio)}</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;font-size:.7em;color:#6e7681">
    <span>BO Date: <b style="color:#e2e8f0">{bo_date or '—'}</b></span>
    <span>Days above BO: <b style="color:#d8b4fe">{days_above}</b></span>
    <span>Dist from BO: <b style="color:#7dd3fc">{pct(dist_from_bo)}</b></span>
  </div>
  <div class="bp-targets">
    <span style="color:#6e7681;font-size:.88em;align-self:center">Targets:</span>
    <span class="bp-t bp-t1">T1 {px(t1)}</span>
    <span class="bp-t bp-t2">T2 {px(t2)}</span>
    <span class="bp-t bp-t3">T3 {px(t3)}</span>
  </div>
</div>"""


def _build_mf_html(mf_ctx: dict, sym: str) -> str:
    """Build the MF/Institutional holdings panel HTML for one signal card."""
    if not mf_ctx:
        return ""
    signal = mf_ctx.get("signal", "UNKNOWN")

    # Determine if we have ANY data worth showing
    dii_pct_val  = (mf_ctx.get("dii") or {}).get("pct")
    fii_pct_val  = (mf_ctx.get("fii") or {}).get("pct")
    pro_pct_val  = (mf_ctx.get("promoters") or {}).get("pct")
    inst_pct_val = mf_ctx.get("inst_held_pct")
    top_mf_val   = mf_ctx.get("top_mf") or []
    has_any_data = any(v is not None for v in (dii_pct_val, fii_pct_val, pro_pct_val, inst_pct_val)) or bool(top_mf_val)

    if not has_any_data:
        err = mf_ctx.get("screener_error", "")
        if err and "not_listed" in str(err):
            return ""   # private/unlisted company — truly no data
        # Show a minimal "data loading" panel for Indian stocks instead of hiding
        if sym.endswith(".NS") or sym.endswith(".BO"):
            return (f'<div class="mf-panel">'
                    f'<div class="mf-hdr" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
                    f'<span class="mf-hdr-lbl">🏦 Institutional</span>'
                    f'<span class="mf-sig mf-sig-neutral">⟳ Fetching</span></div>'
                    f'<div class="mf-body">'
                    f'<div class="mf-swing" style="color:#64748b;font-size:.68em">Shareholding data will appear on next run after Screener.in cache warms up.</div>'
                    f'</div></div>')
        return ""

    sig_labels = {
        "STRONG_BUYING":    ("mf-sig-strong",   "🔥 Strong Buying"),
        "DII_ACCUMULATING": ("mf-sig-dii",      "↑ DIIs Buying"),
        "FII_ACCUMULATING": ("mf-sig-fii",      "↑ FIIs Buying"),
        "DISTRIBUTING":     ("mf-sig-dist",     "⚠ Distributing"),
        "FII_SELLING":      ("mf-sig-dist",     "⚠ FIIs Selling"),
        "NEUTRAL":          ("mf-sig-neutral",  "→ Stable"),
        "INST_HIGH":        ("mf-sig-fii",      "ℹ Inst. Held"),
        "PROMOTER_HELD":    ("mf-sig-neutral",  "🏢 Promoter Held"),
        "UNKNOWN":          ("mf-sig-neutral",  "⟳ Partial Data"),
    }
    sig_cls, sig_label = sig_labels.get(signal, ("mf-sig-neutral", signal))

    dii = mf_ctx.get("dii") or {}
    fii = mf_ctx.get("fii") or {}
    pro = mf_ctx.get("promoters") or {}
    pub = mf_ctx.get("public") or {}
    period      = escape(mf_ctx.get("latest_period") or "")
    conviction  = mf_ctx.get("conviction", "NEUTRAL")
    conv_cls    = {"HIGH": "mf-conv-high", "MEDIUM": "mf-conv-medium",
                   "LOW": "mf-conv-low"}.get(conviction, "mf-conv-neu")
    inst_pct    = mf_ctx.get("inst_held_pct")
    mf_sub_pct  = mf_ctx.get("mutual_funds_pct")
    screener_err = mf_ctx.get("screener_error")

    def fmt(v, suffix="%"):
        return f"{v:.1f}{suffix}" if v is not None else "—"

    def fmt_chg(v):
        if v is None: return ""
        sign = "+" if v >= 0 else ""
        cls  = "mf-up" if v > 0.1 else ("mf-dn" if v < -0.1 else "mf-st")
        return f' <span class="{cls}" style="font-size:.82em">({sign}{v:.1f}%)</span>'

    def trend_arrow(t):
        return {"up": "↑", "down": "↓"}.get(t or "", "→")

    def trend_cls(t):
        return {"up": "mf-up", "down": "mf-dn"}.get(t or "", "mf-st")

    dii_pct  = fmt(dii.get("pct"))
    fii_pct  = fmt(fii.get("pct"))
    pro_pct  = fmt(pro.get("pct"))
    pub_pct  = fmt(pub.get("pct"))

    dii_chg_html = fmt_chg(dii.get("change_2q"))
    fii_chg_html = fmt_chg(fii.get("change_2q"))

    swing_text = escape(mf_ctx.get("text") or mf_ctx.get("summary") or "")

    # Quarterly DII trend mini-bar (last 6 quarters)
    history = mf_ctx.get("dii_trend_history", [])
    trend_bar_html = ""
    if history:
        dii_vals = [h.get("dii") for h in history if h.get("dii") is not None]
        if dii_vals:
            mn, mx = min(dii_vals), max(dii_vals)
            span   = mx - mn if mx != mn else 1.0
            segs   = []
            for v in dii_vals[-6:]:
                h_px = max(4, int((v - mn) / span * 18) + 2)
                clr  = "#2dd4bf"
                segs.append(f'<span class="mf-bar-seg" style="height:{h_px}px;background:{clr}" title="DII {v:.1f}%"></span>')
            trend_bar_html = (
                f'<div style="margin-bottom:5px">'
                f'<div style="font-size:.62em;color:#64748b;margin-bottom:2px">DII trend ({len(dii_vals)}Q)</div>'
                f'<div class="mf-dii-trend-bar">{"".join(segs)}</div>'
                f'</div>'
            )

    # MF sub-% and inst_held note
    extra_html = ""
    if mf_sub_pct is not None:
        extra_html += f'<div style="margin-top:4px;font-size:.65em;color:#7dd3fc">Mutual Funds (of DII): <b>{mf_sub_pct:.1f}%</b></div>'
    if inst_pct is not None:
        extra_html += (
            f'<div style="margin-top:2px;font-size:.62em;color:#64748b">'
            f'Institutional (float): {inst_pct:.1f}%</div>'
        )
    if screener_err and screener_err not in ("not_listed_on_screener",):
        src_label = "yfinance only" if signal in ("INST_HIGH", "NEUTRAL", "UNKNOWN") else "Screener.in"
        extra_html += (
            f'<div style="margin-top:2px;font-size:.58em;color:#475569">'
            f'⚠ Screener error ({screener_err}) — Source: {src_label}</div>'
        )

    top_mf = (mf_ctx.get("top_mf") or [])[:5]
    top_mf_html = ""
    if top_mf:
        items = "".join(
            f'<div class="mf-scheme"><span class="mf-scheme-name">{escape(m["name"])}</span>'
            f'<span class="mf-scheme-pct">{fmt(m.get("pct"))}</span></div>'
            for m in top_mf
        )
        lbl = "Top Shareholders (yfinance)" if mf_ctx.get("_top_holders_source") == "yfinance" else "Top Shareholders"
        top_mf_html = f'<div class="mf-top"><div class="mf-top-lbl">{lbl}</div>{items}</div>'

    src_note = "yfinance" if screener_err else "Screener.in"
    return f"""<div class="mf-panel">
  <div class="mf-hdr" onclick="this.nextElementSibling.classList.toggle('open')">
    <span class="mf-hdr-lbl">🏦 Institutional{' · ' + period if period else ''}</span>
    <span class="mf-sig {sig_cls}">{sig_label}</span>
  </div>
  <div class="mf-body">
    <div class="mf-swing">{swing_text}</div>
    {trend_bar_html}
    <div class="mf-own-grid">
      <div><span class="mf-own-lbl">DIIs</span><span class="{trend_cls(dii.get('trend'))} mf-own-val">{trend_arrow(dii.get('trend'))} {dii_pct}{dii_chg_html}</span></div>
      <div><span class="mf-own-lbl">FIIs</span><span class="{trend_cls(fii.get('trend'))} mf-own-val">{trend_arrow(fii.get('trend'))} {fii_pct}{fii_chg_html}</span></div>
      <div><span class="mf-own-lbl">Promoters</span><span class="{trend_cls(pro.get('trend'))} mf-own-val">{trend_arrow(pro.get('trend'))} {pro_pct}</span></div>
      <div><span class="mf-own-lbl">Public</span><span class="mf-st mf-own-val">→ {pub_pct}</span></div>
    </div>
    {extra_html}
    {top_mf_html}
    <div style="margin-top:4px;font-size:.6em;color:#475569">Conviction: <span class="{conv_cls}">{conviction}</span> · Source: {src_note}</div>
  </div>
</div>"""


def build_html(signals: list[dict], run_history: dict | None = None) -> str:
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

    # ── Appearance stats across stored runs
    _rh = run_history or {}
    _rh_total = len(_rh.get("runs", []))
    recurring_count = sum(
        1 for s in signals
        if count_appearances(s.get("symbol",""), _rh)[0] >= max(1, _rh_total // 2)
    ) if _rh_total > 0 else 0
    run_history_note = (
        f"Run history: {_rh_total}/{RUN_HISTORY_MAX} runs stored"
        if _rh_total > 0 else "First run — history starts now"
    )

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

        # ── Appearance count over last 20 runs
        app_count, app_total = count_appearances(sym, run_history or {})

        # ── Price performance (always use daily rows for consistent periods)
        daily_rows = load_price_rows(sym, weekly=False)
        perf = compute_price_performance(daily_rows)

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

        # ── All setups this symbol appeared in (multi-setup support)
        all_setups = sig.get("_all_setups") or [(setup, tf_lbl)]

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

        # MF / Institutional holdings for this signal (pre-fetched batch)
        mf_ctx = sig.get("_mf_context", {})
        mf_html = _build_mf_html(mf_ctx, sym)

        # Build multi-setup tags HTML
        def _setup_tag_html(st: str, tip: str = "") -> str:
            sc, sl, stip = SETUP_META.get(st, ("tag-bo", st.replace("_", " "), ""))
            tip_attr = f' title="{tip or stip}"' if (tip or stip) else ""
            return f'<span class="{sc} sig-tag"{tip_attr}>{sl}</span>'

        setup_tags_html = "".join(_setup_tag_html(st) for st, _lbl in all_setups)
        # Multi-setup badge if stock shows in more than one setup type
        multi_badge_html = ""
        if len(all_setups) > 1:
            labels_str = " + ".join(SETUP_META.get(st, (None, st.replace("_", " "), None))[1] for st, _ in all_setups)
            multi_badge_html = f'<span class="multi-setup-badge" title="Appears in multiple setups: {labels_str}">🔀 Multi</span>'

        rows_html.append(f"""
<div class="sig-card" data-symbol="{sym}" data-setup="{setup}" data-rating="{rating}" data-sector="{sector}" data-appear="{app_count}" data-appear-total="{app_total}">
  <div class="sig-header">
    <div class="sig-left">
      <div class="sig-sym">{sym.replace('.NS','')}</div>
      <div class="sig-meta">
        <span class="badge-sec">{sector}</span>
        <span class="badge-tf">{tf_lbl}</span>
        {setup_tags_html}
        {multi_badge_html}
      </div>
    </div>
    <div class="sig-right">
      <div class="sig-sparkline">{svg}</div>
      <div style="display:flex;gap:5px;align-items:center;justify-content:flex-end;flex-wrap:wrap;">
        <div class="sig-rating {'rat-aplus' if rating=='A+' else 'rat-a' if rating=='A' else 'rat-b'}">{rating}</div>
        {f'<div class="appear-badge {"appear-hot" if app_count >= 15 else "appear-warm" if app_count >= 8 else "appear-cool"}" title="Appeared {app_count} times in last {app_total} runs">&#128257; {app_count}/{app_total}</div>' if app_total > 0 else ''}
      </div>
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

  <!-- Performance row -->
  <div class="perf-row">
    <div class="perf-cell">
      <span class="perf-label">1W</span>
      {fmt_perf(perf['ret_1w'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">1M</span>
      {fmt_perf(perf['ret_1m'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">3M</span>
      {fmt_perf(perf['ret_3m'])}
    </div>
    <div class="perf-cell">
      <span class="perf-label">6M</span>
      {fmt_perf(perf['ret_6m'])}
    </div>
    {f'<div class="perf-cell appear-cell"><span class="perf-label">Seen (20d)</span><span class="{"appear-hot" if app_count >= 15 else "appear-warm" if app_count >= 8 else "appear-cool"}">{app_count}/{app_total} runs</span></div>' if app_total > 0 else ''}
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
  {mf_html}
  {_build_bf_html(sig) if setup == 'BULL_FLAG' else ''}
  {_build_rexp_html(sig) if setup == 'RANGE_EXPANSION' else ''}
  {_build_bp_html(sig) if setup == 'BREAKOUT_PULLBACK' else ''}
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
.tag-bf{{background:#0a2a1a;color:#34d399;border:1px solid #34d39944}}

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

/* PERFORMANCE ROW */
.perf-row{{display:flex;gap:0;border-top:1px solid #21262d;background:#090e14;flex-wrap:wrap}}
.perf-cell{{flex:1;min-width:60px;padding:7px 10px;text-align:center;border-right:1px solid #21262d}}
.perf-cell:last-child{{border-right:none}}
.perf-cell.appear-cell{{flex:1.3;min-width:90px}}
.perf-label{{display:block;font-size:.62em;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px;font-weight:600}}
.perf-up{{font-size:.82em;font-weight:700;color:#3fb950}}
.perf-dn{{font-size:.82em;font-weight:700;color:#f85149}}
.perf-na{{font-size:.82em;color:#8b949e}}

/* APPEARANCE BADGE */
.appear-badge{{padding:2px 7px;border-radius:4px;font-size:.68em;font-weight:700;white-space:nowrap}}
.appear-hot{{color:#ffd700;background:#2a2a00;border:1px solid #ffd70044}}
.appear-warm{{color:#fb923c;background:#261400;border:1px solid #fb923c44}}
.appear-cool{{color:#60a5fa;background:#0f1f3a;border:1px solid #1d4ed844}}

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

/* MF / INSTITUTIONAL HOLDINGS PANEL */
.mf-panel{{border-top:1px solid #21262d;margin-top:0}}
.mf-hdr{{display:flex;align-items:center;justify-content:space-between;padding:7px 16px 5px;cursor:pointer;user-select:none;background:#0a0f16}}
.mf-hdr:hover{{background:#0d1420}}
.mf-hdr-lbl{{font-size:.71em;color:#7dd3fc;font-weight:700;letter-spacing:.3px}}
.mf-sig{{font-size:.67em;font-weight:700;padding:1px 7px;border-radius:99px}}
.mf-sig-strong{{background:#0a2a14;color:#4ade80;border:1px solid #16a34a44}}
.mf-sig-dii{{background:#0a2220;color:#2dd4bf;border:1px solid #0d948844}}
.mf-sig-fii{{background:#0f1f3a;color:#60a5fa;border:1px solid #1d4ed844}}
.mf-sig-dist{{background:#2a1215;color:#f87171;border:1px solid #dc262644}}
.mf-sig-neutral{{background:#161b22;color:#8b949e;border:1px solid #30363d}}
.mf-body{{display:none;padding:8px 16px 10px;font-size:.7em;background:#080d13}}
.mf-body.open{{display:block}}
.mf-swing{{color:#94a3b8;line-height:1.4;margin-bottom:7px}}
.mf-own-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;margin-bottom:7px}}
.mf-own-lbl{{color:#8b949e;font-size:.88em;display:block;margin-bottom:1px}}
.mf-own-val{{font-weight:700;font-size:.95em}}
.mf-up{{color:#4ade80}}.mf-dn{{color:#f87171}}.mf-st{{color:#94a3b8}}
.mf-conv-high{{color:#ffd700;font-weight:700}}.mf-conv-medium{{color:#60a5fa}}.mf-conv-low{{color:#f87171}}.mf-conv-neu{{color:#94a3b8}}
.mf-top{{margin-top:6px;border-top:1px solid #0f172a;padding-top:5px}}
.mf-top-lbl{{font-size:.68em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:3px}}
.mf-scheme{{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #0f172a}}
.mf-scheme:last-child{{border-bottom:none}}
.mf-scheme-name{{color:#c9d1d9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px}}
.mf-scheme-pct{{color:#7dd3fc;font-weight:700;flex-shrink:0;margin-left:6px}}
.mf-dii-trend-bar{{display:flex;align-items:flex-end;gap:3px;height:22px}}
.mf-bar-seg{{display:inline-block;width:10px;border-radius:2px 2px 0 0;min-height:4px}}

/* BULL FLAG DETAIL PANEL */
.bf-panel{{border-top:1px solid #21262d;background:#070d10;padding:8px 16px 10px}}
.bf-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.bf-cell{{background:#0b1320;border:1px solid #1a2535;border-radius:5px;padding:5px 8px}}
.bf-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.bf-val{{font-size:.82em;font-weight:700}}
.bf-pole{{color:#34d399}}.bf-flag{{color:#fbbf24}}.bf-vol{{color:#60a5fa}}
.bf-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.bf-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.bf-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.bf-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.bf-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.bf-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700}}
.bf-st-forming{{background:#0f1f3a;color:#60a5fa;border:1px solid #1d4ed855}}
.bf-st-breakout{{background:#0a2a14;color:#4ade80;border:1px solid #16a34a55}}

/* RANGE EXPANSION DETAIL PANEL */
.rexp-panel{{border-top:1px solid #21262d;background:#050e08;padding:8px 16px 10px}}
.rexp-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.rexp-cell{{background:#0a1510;border:1px solid #1a3020;border-radius:5px;padding:5px 8px}}
.rexp-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.rexp-val{{font-size:.82em;font-weight:700}}
.rexp-pos{{color:#4ade80}}.rexp-neg{{color:#f87171}}
.rexp-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.rexp-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.rexp-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.rexp-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.rexp-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.rexp-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700}}
.rexp-st-bo{{background:#0a2a14;color:#86efac;border:1px solid #16a34a55}}
.rexp-st-wl{{background:#0f1f3a;color:#7dd3fc;border:1px solid #1d4ed855}}

/* BREAKOUT PULLBACK DETAIL PANEL */
.bp-panel{{border-top:1px solid #21262d;background:#0d0813;padding:8px 16px 10px}}
.bp-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;margin-bottom:6px}}
.bp-cell{{background:#120a1a;border:1px solid #2a1535;border-radius:5px;padding:5px 8px}}
.bp-lbl{{font-size:.62em;color:#6e7681;text-transform:uppercase;letter-spacing:.35px;margin-bottom:2px}}
.bp-val{{font-size:.82em;font-weight:700}}
.bp-targets{{display:flex;gap:6px;flex-wrap:wrap;font-size:.72em}}
.bp-t{{padding:2px 7px;border-radius:4px;font-weight:700}}
.bp-t1{{background:#052e16;color:#4ade80;border:1px solid #16a34a55}}
.bp-t2{{background:#052e16;color:#86efac;border:1px solid #16a34a77}}
.bp-t3{{background:#1a1a00;color:#ffd700;border:1px solid #ffd70055}}
.bp-subtype{{display:inline-flex;padding:1px 7px;border-radius:99px;font-size:.65em;font-weight:700;background:#2a1535;color:#d8b4fe;border:1px solid #7c3aed55}}

/* MULTI-SETUP BADGE */
.multi-setup-badge{{padding:2px 8px;border-radius:4px;font-size:.70em;font-weight:700;background:#1e1b4b;color:#a78bfa;border:1px solid #7c3aed55;white-space:nowrap}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">&#127919; Live Breakout Trade Plans &mdash; NSE India</div>
    <div class="topbar-sub">All active signals from latest scan &bull; {now} &bull; {run_history_note}</div>
  </div>
  <div class="topbar-stats">
    <div class="tstat"><div class="tstat-v">{total}</div><div class="tstat-l">Signals</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#ffd700">{a_plus}</div><div class="tstat-l">A+ Rated</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{a_rate}</div><div class="tstat-l">A &amp; Above</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#fb923c">{recurring_count}</div><div class="tstat-l">Recurring</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#86efac">{setup_counts.get('RANGE_EXPANSION',0)}</div><div class="tstat-l">Range Exp</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#a5b4fc">{setup_counts.get('VCP',0)}</div><div class="tstat-l">VCP</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#d8b4fe">{setup_counts.get('BREAKOUT_PULLBACK',0)}</div><div class="tstat-l">BP</div></div>
    <div class="tstat"><div class="tstat-v" style="color:#34d399">{setup_counts.get('BULL_FLAG',0)}</div><div class="tstat-l">Bull Flag</div></div>
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
    <option value="BULL_FLAG">Bull Flag</option>
  </select>
  <select class="sel" id="ratingFilter" onchange="applyFilters()">
    <option value="">All Ratings</option>
    <option value="A+">A+ Only</option>
    <option value="A">A &amp; Above</option>
    <option value="B">B &amp; Above</option>
  </select>
  <select class="sel" id="appearFilter" onchange="applyFilters()" title="Filter by how many of the last {_rh_total} runs the setup appeared in">
    <option value="">All Appearances</option>
    <option value="50">Seen 50%+ runs</option>
    <option value="75">Seen 75%+ runs</option>
    <option value="high">Seen 15+ runs (Hot)</option>
    <option value="warm">Seen 8+ runs</option>
  </select>
  <button class="btn-filter" onclick="toggleSort('score')" id="btn-sort-score">&#128202; Sort: Score</button>
  <button class="btn-filter" onclick="toggleSort('symbol')" id="btn-sort-sym">&#9776; Sort: Symbol</button>
  <button class="btn-filter" onclick="toggleSort('appear')" id="btn-sort-appear">&#128257; Sort: Recurring</button>
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
  <div class="leg-item"><div class="leg-dot" style="background:#34d399"></div>Bull Flag</div>
  <div class="leg-item"><div class="leg-dot" style="background:#a78bfa"></div>🔀 Multi-Setup</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700"></div>A+ Rating</div>
  <div class="leg-item"><div class="leg-dot" style="background:#3fb950"></div>RS Positive</div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700;border-radius:50%"></div>Hot (15+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#fb923c;border-radius:50%"></div>Warm (8+ runs)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#60a5fa;border-radius:50%"></div>New (&lt;8 runs)</div>
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
  const q      = document.getElementById('searchBox').value.toLowerCase();
  const setup  = document.getElementById('setupFilter').value;
  const rating = document.getElementById('ratingFilter').value;
  const appear = document.getElementById('appearFilter').value;
  let visible = 0;
  document.querySelectorAll('.sig-card').forEach(card => {{
    const sym    = (card.dataset.symbol||'').toLowerCase();
    const sec    = (card.dataset.sector||'').toLowerCase();
    const csetup = card.dataset.setup||'';
    const crate  = card.dataset.rating||'';
    const capp   = parseInt(card.dataset.appear||'0', 10);
    const ctotal = parseInt(card.dataset.appearTotal||'0', 10);
    let show = (sym.includes(q) || sec.includes(q));
    if(setup && csetup !== setup) show = false;
    if(rating === 'A+' && crate !== 'A+') show = false;
    if(rating === 'A'  && crate !== 'A+' && crate !== 'A') show = false;
    if(rating === 'B'  && crate === 'C') show = false;
    if(activeSector && (card.dataset.sector||'') !== activeSector) show = false;
    if(appear) {{
      if(appear === 'high'  && capp < 15) show = false;
      if(appear === 'warm'  && capp < 8)  show = false;
      if(appear === '50'    && ctotal > 0 && capp / ctotal < 0.5) show = false;
      if(appear === '75'    && ctotal > 0 && capp / ctotal < 0.75) show = false;
    }}
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
    if(mode === 'appear') return parseInt(b.dataset.appear||'0',10) - parseInt(a.dataset.appear||'0',10);
    return 0; // score order is default DOM order
  }});
  cards.forEach(c => grid.appendChild(c));
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  const btnMap = {{'score':'btn-sort-score','symbol':'btn-sort-sym','appear':'btn-sort-appear'}};
  const btnId = btnMap[mode];
  if(btnId) document.getElementById(btnId)?.classList.add('active');
}}

function exportCSV() {{
  const rows = [['Symbol','Sector','Setup','Rating','Entry','Stop','Shares','Regime','RS3M','RS6M','VolPct','RExp','1W%','1M%','3M%','6M%','SeenRuns','TotalRuns','EPSGrowth','DebtChange','MacroTrigger','MarketTrigger','FundSummary']];
  document.querySelectorAll('.sig-card').forEach(card => {{
    if(card.style.display === 'none') return;
    const planVals = [...card.querySelectorAll('.plan-value')].map(v => v.textContent.replace(/[₹,]/g,'').trim());
    const stats = [...card.querySelectorAll('.sig-stat span:last-child')].map(v => v.textContent.trim());
    const perfCells = [...card.querySelectorAll('.perf-cell')];
    const p1w = perfCells[0]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p1m = perfCells[1]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p3m = perfCells[2]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const p6m = perfCells[3]?.querySelector('span:last-child')?.textContent?.trim() || '';
    const seenRuns   = card.dataset.appear || '0';
    const totalRuns  = card.dataset.appearTotal || '0';
    const epsGrowth    = card.querySelector('.insight-item:nth-child(1) .insight-value')?.textContent?.trim() || '';
    const debtChange   = card.querySelector('.insight-item:nth-child(2) .insight-value')?.textContent?.trim() || '';
    const macroTrigger = card.querySelector('.insight-item:nth-child(3) .insight-pill')?.textContent?.trim() || '';
    const marketTrigger= card.querySelector('.insight-item:nth-child(4) .insight-pill')?.textContent?.trim() || '';
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
      p1w, p1m, p3m, p6m,
      seenRuns, totalRuns,
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

def _fetch_mf_holdings_for_signals(signals: list[dict]) -> None:
    """Batch-fetch MF/institutional holdings and inject _mf_context into each signal."""
    if not _MF_AVAILABLE or not signals:
        return
    india_signals = [s for s in signals if
                     str(s.get("symbol","")).endswith(".NS") or str(s.get("symbol","")).endswith(".BO")
                     or not str(s.get("symbol","")).isascii()]
    symbols = list({s["symbol"] for s in india_signals if s.get("symbol")})
    if not symbols:
        return

    print(f"  Fetching MF/institutional holdings for {len(symbols)} symbols…", flush=True)
    try:
        provider = MutualFundsProvider(cache_dir=str(CACHE_DIR), cache_ttl_hours=6)
        raw = provider.fetch_batch(symbols, market="india", workers=2)
        sym_map = {s: raw.get(s, {}) for s in symbols}
        for sig in signals:
            sym = sig.get("symbol", "")
            if sym in sym_map:
                sig["_mf_context"] = mf_swing_context(sym_map[sym])
    except Exception as e:
        print(f"  Warning: MF holdings fetch failed: {e}", flush=True)


def main():
    print("Generating Trade Plans page...")
    signals = load_signals()
    print(f"  Loaded {len(signals)} unique signals")

    # ── Record this run in history (for appearance tracking)
    print(f"  Updating run history ({RUN_HISTORY_MAX}-run window)…")
    run_history = update_run_history(signals)
    print(f"  Run history: {len(run_history.get('runs', []))} stored runs")

    hstats = hydrate_missing_fundamentals(signals)
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

    # Fetch MF/institutional holdings (Screener.in + yfinance, 6h cache)
    _fetch_mf_holdings_for_signals(signals)

    html = build_html(signals, run_history=run_history)
    out = OUTPUT / "trade_plans_live.html"
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"  Output: {out}")
    print(f"  Size: {size:.1f} KB")


if __name__ == "__main__":
    main()

