#!/usr/bin/env python3
"""
generate_breadth_dashboard.py
─────────────────────────────
Standalone Market Breadth & Trend Detection Dashboard — NSE India

NEW v2 additions (Phase 4 & 5):
  - Market Regime Banner     (Bull/Recovery/Mixed/Correction/Bear)
  - Breadth Oscillator       (advance/decline momentum signal)
  - Best Opportunity Screen  (ranked early-stage setups)
  - Momentum Trajectories    (Accelerating / Improving / Decelerating)
  - Smart Money Footprint    (vol+RS+new-highs institutional signal)
  - Divergence Alerts        (bullish early-entry + bearish warnings)
  - Sector Rotation Matrix   (cycle-phase momentum quadrant)
  - 6 new custom themes      (PSU Banks, Pharma, Metals, Real Estate, Sugar, Auto)

Outputs: output/market_breadth.html
Run:     python3 apps/python/cli/generate_breadth_dashboard.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"

sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))
sys.path.insert(0, str(ROOT / "apps" / "python" / "cli"))

try:
    from generate_trade_plans_page import INDUSTRY_MAP as _TP_IND, SECTOR_MAP as _TP_SEC, _f
except Exception:
    _TP_IND, _TP_SEC = {}, {}
    def _f(v, d=0.0):
        try:
            return float(str(v or "").strip().replace("%","").replace(",",""))
        except Exception:
            return d

# ── Advanced breadth analytics module ────────────────────────────────────────
try:
    from market_breadth import (
        compute_market_regime,
        compute_breadth_pulse,
        detect_divergences,
        compute_trajectories,
        compute_smart_money_footprint,
        compute_rotation_signals,
        compute_breadth_oscillator,
        compute_sector_momentum_matrix,
        screen_best_opportunities,
    )
    _MB_AVAILABLE = True
except Exception as _mb_err:
    _MB_AVAILABLE = False
    # Graceful no-op stubs so the dashboard still renders
    def compute_market_regime(d): return {"regime": "N/A", "regime_score": 50, "color": "#475569", "emoji": "—", "description": "market_breadth module not loaded.", "action": "", "industry_count": 0}
    def compute_breadth_pulse(d): return {}
    def detect_divergences(d):    return {"bullish": [], "bearish": []}
    def compute_trajectories(d):  return {"accelerating": [], "improving": [], "decelerating": [], "collapsing": [], "steady": []}
    def compute_smart_money_footprint(d): return []
    def compute_rotation_signals(d): return d
    def compute_breadth_oscillator(d): return {"oscillator": 0, "signal": "N/A", "signal_color": "#475569"}
    def compute_sector_momentum_matrix(d): return d
    def screen_best_opportunities(d, **kw): return []

_CSV_IND: dict[str, str] = {}
_CSV_SEC: dict[str, str] = {}
_CSV_PATH = ROOT / "data" / "nse_stock_taxonomy.csv"
if _CSV_PATH.exists():
    try:
        with open(_CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("nse_ticker","").strip().upper()
                s = row.get("sector","").strip()
                i = row.get("industry","").strip()
                if t and s: _CSV_SEC[t] = s
                if t and i: _CSV_IND[t] = i
    except Exception:
        pass

INDUSTRY_MAP: dict[str, str] = {**_TP_IND, **_CSV_IND}
SECTOR_MAP:   dict[str, str] = {**_TP_SEC, **_CSV_SEC}

_IND_TO_SEC: dict[str, str] = {}
for _t, _ind in INDUSTRY_MAP.items():
    if _ind not in _IND_TO_SEC:
        _IND_TO_SEC[_ind] = SECTOR_MAP.get(_t, "Other")

NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── Custom Thematic Baskets ────────────────────────────────────────────────────
# Edit freely — add/remove themes or stocks. Performance tracked automatically.
CUSTOM_THEMES: dict[str, dict] = {
    "Data Center & AI Infra": {
        "emoji": "🖥️",
        "color": "#38bdf8",
        "description": (
            "Direct beneficiaries of India's data center capex boom & AI infra build-out — "
            "power systems, transformers, fiber, PCBs, heat exchangers, engineering design"
        ),
        "stocks": [
            "CGPOWER",    # power systems & switchgear — critical for DCs
            "CUMMINSIND", # diesel gensets, power backup for data centers
            "TDPOWERSYS", # power transformers & systems
            "KRN",        # heat exchangers (DC cooling)
            "AEROFLEX",   # specialty cables & connectors
            "STLTECH",    # optical fiber cables (DC connectivity)
            "VOLTAMP",    # power transformers
            "ABB",        # automation, switchgear, UPS
            "SIEMENS",    # electrical systems & automation
            "SCHNEIDER",  # electrical equipment & DCIM
            "KIRLOSENG",  # generators & compressors
            "THERMAX",    # heat exchange & cooling
            "HFCL",       # optical fiber cables
            "POLYCAB",    # power cables to data centers
            "KEI",        # power cables
            "KAYNES",     # PCBs & electronics mfg
            "SYRMA",      # PCBs & electronics mfg
            "CENTUM",     # embedded electronics & modules
            "TATAELXSI",  # engineering design services
            "CYIENT",     # engineering services
            "MTARTECH",   # precision manufacturing for tech infra
            "NETWEB",     # data center servers (listed 2023)
        ],
    },
    "Defense & Aerospace": {
        "emoji": "🛡️",
        "color": "#fb923c",
        "description": (
            "Indian defense indigenization — HAL, BEL, shipbuilding, drones, missiles, "
            "explosives, aerospace alloys. Budget visibility 5+ years."
        ),
        "stocks": [
            "HAL", "BEL", "GRSE", "COCHINSHIP", "MAZDOCK", "MTARTECH",
            "DYNAMATECH", "IDEAFORGE", "SOLARIND", "SOLARBOMB", "GOCLCORP",
            "NAGAFERT", "MIDHANI", "DATAPATTNS", "ZEN", "DRONEACHARYA",
            "BDSL", "ASTRA", "PARAS",
        ],
    },
    "EV & New Energy": {
        "emoji": "⚡",
        "color": "#34d399",
        "description": (
            "Electric vehicle ecosystem, EV batteries, charging infra, solar manufacturing, "
            "wind energy. India's energy transition plays."
        ),
        "stocks": [
            "TATAMOTORS", "OLECTRA", "PMI", "SUZLON", "INOXWIND",
            "WAAREEENER", "ACMESOLAR", "ADANIGREEN", "ADANIENSOL",
            "EXIDEIND", "AMARON", "TATAPOWER", "ATHERENERG",
        ],
    },
    "Specialty Chemicals China+1": {
        "emoji": "🧪",
        "color": "#a78bfa",
        "description": (
            "India specialty chemicals benefiting from China+1 diversification — "
            "fluorine chemistry, pharma intermediates, agri-chem, performance chemicals."
        ),
        "stocks": [
            "NAVINFLUOR", "SRF", "FLUOROCHEM", "AARTIIND", "DEEPAKNITR",
            "VINATI", "ATUL", "ROSSARI", "ALKYLAMINE", "NOCIL",
            "FINEORG", "PCBL", "GALAXYSURF", "NEOGEN", "AETHER",
            "COMSYN", "DEEPINDS", "SUDARSCHEM",
        ],
    },
    "Capital Markets Financialization": {
        "emoji": "💹",
        "color": "#fbbf24",
        "description": (
            "India's rising financialization — exchanges, brokers, AMCs, wealth managers, "
            "fintech. Structural growth from SIP inflows & demat account surge."
        ),
        "stocks": [
            "BSE", "MCX", "ANGELONE", "ICICISEC", "5PAISA", "DBSTOCKBRO",
            "HDFCAMC", "NIPPONAMC", "ABSLAMC", "UTIAMC",
            "CDSL", "CAMS", "KFINTECH", "NSDL",
            "MOFSL", "MOTILALOFS", "NUVAMA", "ANANDRATHI", "SAMMAANCAP",
        ],
    },
    "Railway & Infrastructure": {
        "emoji": "🚄",
        "color": "#f472b6",
        "description": (
            "India's ₹11L Cr railway capex cycle — wagon manufacturers, EPC, "
            "signaling, rail logistics, ports. Long government order visibility."
        ),
        "stocks": [
            "RVNL", "IRCON", "IRFC", "TITAGARH", "TEXRAIL",
            "NBCC", "PSPPROJECT", "RITES", "KNRCON", "ASHOKA",
            "IRB", "L&T", "BHEL", "SIEMENS",
        ],
    },
    "PSU Banks Rally": {
        "emoji": "🏦",
        "color": "#818cf8",
        "description": (
            "Public sector bank ecosystem — beneficiaries of lower NPA cycle, "
            "government capex credit push and CASA improvement. "
            "FII flows returning to PSUs signal structural re-rating."
        ),
        "stocks": [
            "SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK",
            "IDBI", "CENTRALBK", "INDIANB", "UCO", "MAHABANK",
            "BANKINDIA", "IOB", "HDFCBANK", "ICICIBANK", "AXISBANK",
        ],
    },
    "Pharma & Healthcare": {
        "emoji": "💊",
        "color": "#34d399",
        "description": (
            "India's pharma outperformance driven by US generic approvals, "
            "CDMO opportunity and domestic hospital expansion. "
            "Diagnostics + API + Hospitals = full healthcare stack."
        ),
        "stocks": [
            "SUNPHARMA", "DRREDDY", "CIPLA", "LUPIN", "DIVISLAB",
            "TORNTPHARM", "ALKEM", "AUROPHARMA", "GRANULES", "LAURUSLABS",
            "NEULANDLAB", "AKUMS", "METROPOLIS", "DRLALPATH", "THYROCARE",
            "APOLLOHOSP", "FORTIS", "ASTERDM", "NARAYANA", "SHILPAMED",
        ],
    },
    "Metals & Mining Upcycle": {
        "emoji": "⚙️",
        "color": "#f97316",
        "description": (
            "Global commodity supercycle + India infra demand driving metals. "
            "Steel pipes lead (infra + oil), forgings (auto+defense), "
            "graphite (EV batteries globally). Best leverage to capex."
        ),
        "stocks": [
            "TATASTEEL", "JSWSTEEL", "SAIL", "JINDALSTEL",
            "APLAPOLLO", "RATNAMANI", "WELCORP", "JINDALSAW",
            "BHARATFORG", "GNA", "SANSERA", "NELCAST",
            "HINDALCO", "NALCO", "HINDZINC", "NMDC",
            "GRAPHITE", "HEG", "MOIL", "GPIL",
        ],
    },
    "Real Estate & Housing": {
        "emoji": "🏗️",
        "color": "#e879f9",
        "description": (
            "India real estate super-cycle — premium residential launches, "
            "commercial office revival, affordable housing credit. "
            "Best proxy: luxury launches & home building materials."
        ),
        "stocks": [
            "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "MACROTECH",
            "SOBHA", "BRIGADE", "MAHLIFE", "KOLTEPATIL", "ANANTRAJ",
            "CENTURYPLY", "GREENPANEL", "ASTRAL", "APOLLOPIPES", "PRINCEPIPE",
            "ASIANPAINT", "PIDILITIND", "HAVELLS", "CERA",
        ],
    },
    "India Manufacturing Renaissance": {
        "emoji": "🏭",
        "color": "#fb7185",
        "description": (
            "PLI-driven India manufacturing scale-up — electronics, auto parts, "
            "cables, precision engineering. China+1 beneficiaries with "
            "strong order books and margin expansion."
        ),
        "stocks": [
            "DIXON", "AMBER", "KAYNES", "SYRMA", "CENTUM",
            "PGEL", "ELIN", "AVALON", "AEROFLEX", "KRN",
            "KEI", "POLYCAB", "FINOLEX", "STLTECH", "HFCL",
            "MOTHERSON", "ENDURANCE", "MINDA", "CRAFTSMAN", "SANSERA",
        ],
    },
    "Sugar & Ethanol": {
        "emoji": "🌿",
        "color": "#a3e635",
        "description": (
            "Government-mandated ethanol blending (E20 by 2025) + exports "
            "during surplus cycles. Sugar company diversification into ethanol "
            "provides re-rating catalyst. Watch for export policy announcements."
        ),
        "stocks": [
            "RENUKA", "TRIVENI", "BALRAMCHIN", "DALMIASUG", "DHAMPURSUG",
            "AVADHSUGAR", "MAWANASUG", "UTTAMSUGAR", "DHAMPUR", "DWARKESH",
            "PRAJIND", "SHREERENUKA",
        ],
    },
}


# ── Price helpers ──────────────────────────────────────────────────────────────

def _load_prices(ticker: str) -> list[dict]:
    best: list[dict] = []
    for suffix in ["_3528", "_900", "_728", "_504", "_252", "_60"]:
        for name in (f"{ticker}.NS{suffix}.csv", f"{ticker}{suffix}.csv"):
            p = CACHE_DIR / name
            if not p.exists():
                continue
            rows: list[dict] = []
            try:
                with open(p, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        c = _f(row.get("close"))
                        if c > 0:
                            rows.append({"close": c, "volume": _f(row.get("volume", 0))})
            except Exception:
                pass
            if len(rows) > len(best):
                best = rows
            if best:
                break
        if best:
            break
    return best


def _load_nifty() -> list[float]:
    for suffix in ["_3528", "_900", "_728", "_504", "_252"]:
        p = CACHE_DIR / f"^NSEI{suffix}.csv"
        if not p.exists():
            continue
        closes: list[float] = []
        try:
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    c = _f(row.get("close"))
                    if c > 0:
                        closes.append(c)
        except Exception:
            pass
        if closes:
            return closes
    return []


def _rs(stock: list[float], bench: list[float], periods: int = 63) -> float | None:
    if len(stock) <= periods or len(bench) <= periods:
        return None
    return round((stock[-1]/stock[-(periods+1)] - 1)*100 - (bench[-1]/bench[-(periods+1)] - 1)*100, 1)


def _ema(closes: list[float], period: int) -> float | None:
    """Exponential Moving Average — more responsive than SMA."""
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period   # seed with SMA
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _new52wh(closes: list[float], n: int = 5) -> int:
    if len(closes) < 252 + n:
        return 0
    count = 0
    for i in range(-n, 0):
        window = closes[max(0, i-252): i]
        if window and closes[i] >= max(window):
            count += 1
    return count


def _period_return(closes: list[float], sessions: int) -> float | None:
    """% return over last `sessions` trading sessions."""
    if len(closes) <= sessions:
        return None
    return round((closes[-1] / closes[-(sessions + 1)] - 1) * 100, 1)


# ── Theme metrics ──────────────────────────────────────────────────────────────

PERIODS: dict[str, int] = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def compute_theme_metrics(theme_name: str, cfg: dict, nifty_closes: list[float]) -> dict | None:
    stocks = cfg.get("stocks", [])
    if not stocks:
        return None

    # Nifty reference returns
    nifty_rets: dict[str, float | None] = {
        p: _period_return(nifty_closes, n) for p, n in PERIODS.items()
    }

    all_period_rets: dict[str, list[float]] = {p: [] for p in PERIODS}
    a20 = a50 = a200 = at52 = vol_spike = new52w = tracked = 0
    rs3m_list: list[float] = []
    rs1m_list: list[float] = []
    stock_rets_3m: list[tuple[str, float]] = []
    stock_rets_1m: list[tuple[str, float]] = []
    stock_breadth: list[dict] = []

    for ticker in stocks:
        rows = _load_prices(ticker)
        if len(rows) < 20:
            continue
        closes  = [r["close"] for r in rows]
        volumes = [r["volume"] for r in rows]
        last    = closes[-1]
        tracked += 1

        if last > sum(closes[-20:]) / 20:                          a20  += 1
        if len(closes) >= 50  and last > sum(closes[-50:])/50:     a50  += 1
        if len(closes) >= 200 and last > sum(closes[-200:])/200:   a200 += 1
        hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        if last >= hi52 * 0.95:   at52 += 1
        new52w += _new52wh(closes, 5)
        if len(volumes) >= 25:
            avg_vol = sum(volumes[-25:-5]) / 20
            if avg_vol > 0 and any(v > avg_vol * 1.5 for v in volumes[-5:]):
                vol_spike += 1

        r3 = _rs(closes, nifty_closes, 63)
        r1 = _rs(closes, nifty_closes, 21)
        if r3 is not None: rs3m_list.append(r3)
        if r1 is not None: rs1m_list.append(r1)

        for p, n in PERIODS.items():
            ret = _period_return(closes, n)
            if ret is not None:
                all_period_rets[p].append(ret)

        r3m = _period_return(closes, 63)
        r1m = _period_return(closes, 21)
        if r3m is not None: stock_rets_3m.append((ticker, r3m))
        if r1m is not None: stock_rets_1m.append((ticker, r1m))

        stock_breadth.append({
            "ticker": ticker,
            "above20": last > sum(closes[-20:]) / 20,
            "last": last,
            "r1m": r1m,
            "r3m": r3m,
            "rs3m": r3,
        })

    if tracked == 0:
        # Still return something useful with config stocks (for modal)
        all_modal = [{"ticker": t, "above20": False, "last": None,
                      "r1m": None, "r3m": None, "rs3m": None, "no_data": True}
                     for t in stocks]
        return {
            "theme": theme_name, "emoji": cfg.get("emoji","📊"),
            "color": cfg.get("color","#58a6ff"), "description": cfg.get("description",""),
            "stocks_total": len(stocks), "stocks_tracked": 0,
            "theme_rets": {p: None for p in PERIODS}, "nifty_rets": {p: None for p in PERIODS},
            "alphas": {p: None for p in PERIODS},
            "pct_20ma": 0, "pct_50ma": 0, "pct_200ma": 0, "pct_52wh": 0,
            "new_52wh": 0, "vol_spike_pct": 0, "avg_rs3m": None, "avg_rs1m": None,
            "stage": "WEAK", "stage_color": "#475569",
            "top_performers": [], "bottom_performers": [],
            "stock_breadth": [], "all_stocks_modal": all_modal,
        }

    def _avg(lst: list) -> float | None:
        return round(sum(lst) / len(lst), 1) if lst else None

    theme_rets  = {p: _avg(all_period_rets[p]) for p in PERIODS}
    alphas      = {
        p: (round(theme_rets[p] - nifty_rets[p], 1)
            if theme_rets[p] is not None and nifty_rets[p] is not None else None)
        for p in PERIODS
    }

    p20  = round(a20  / tracked * 100)
    p50  = round(a50  / tracked * 100)
    p200 = round(a200 / tracked * 100)

    if p20 >= 80:   stage, sc = "EXTENDED", "#f85149"
    elif p20 >= 65: stage, sc = "BUILDING",  "#e3b341"
    elif p20 >= 25: stage, sc = "EMERGING",  "#3fb950"
    else:           stage, sc = "WEAK",      "#475569"

    stock_rets_3m.sort(key=lambda x: -x[1])

    # Build full modal list: tracked stocks first, then untracked (no_data=True)
    tracked_tickers = {s["ticker"] for s in stock_breadth}
    untracked = [{"ticker": t, "above20": False, "last": None,
                  "r1m": None, "r3m": None, "rs3m": None, "no_data": True}
                 for t in stocks if t not in tracked_tickers]
    all_stocks_modal = sorted(stock_breadth, key=lambda x: -(x.get("r3m") or -999)) + untracked

    return {
        "theme": theme_name,
        "emoji": cfg.get("emoji", "📊"),
        "color": cfg.get("color", "#58a6ff"),
        "description": cfg.get("description", ""),
        "stocks_total": len(stocks),
        "stocks_tracked": tracked,
        "theme_rets": theme_rets,
        "nifty_rets": nifty_rets,
        "alphas": alphas,
        "pct_20ma": p20, "pct_50ma": p50, "pct_200ma": p200,
        "pct_52wh": round(at52 / tracked * 100),
        "new_52wh": new52w,
        "vol_spike_pct": round(vol_spike / tracked * 100),
        "avg_rs3m": _avg(rs3m_list),
        "avg_rs1m": _avg(rs1m_list),
        "stage": stage, "stage_color": sc,
        "top_performers": stock_rets_3m[:5],
        "bottom_performers": list(reversed(stock_rets_3m[-4:])) if len(stock_rets_3m) >= 4 else [],
        "stock_breadth": sorted(stock_breadth, key=lambda x: -(x.get("r3m") or -999)),
        "all_stocks_modal": all_stocks_modal,   # full list including untracked stocks
    }


# ── Metric computation ─────────────────────────────────────────────────────────

def compute_industry_metrics(industry: str, nifty_closes: list[float]) -> dict | None:
    peers = [t for t, ind in INDUSTRY_MAP.items() if ind == industry]
    if not peers:
        return None

    a20 = a50 = a200 = at52 = new52 = total = 0
    vol_spike_cnt = 0
    rs3m_list: list[float] = []
    rs1m_list: list[float] = []
    rs_delta_list: list[float] = []   # RS improvement last 4W
    vol_rank_list: list[float] = []   # vol expansion ratio
    ret1m_list: list[float] = []
    ret3m_list: list[float] = []
    ret6m_list: list[float] = []
    stock_list: list[dict] = []        # ← per-stock detail for UI chips

    for ticker in peers:
        rows = _load_prices(ticker)
        if len(rows) < 22:
            continue
        closes  = [r["close"] for r in rows]
        volumes = [r["volume"] for r in rows]
        last    = closes[-1]
        total  += 1

        # ── EMA breadth ────────────────────────────────────────────────────────
        e20  = _ema(closes, 20)
        e50  = _ema(closes, 50)  if len(closes) >= 50  else None
        e200 = _ema(closes, 200) if len(closes) >= 200 else None
        ab20 = bool(e20  and last > e20)
        ab50 = bool(e50  and last > e50)
        ab200= bool(e200 and last > e200)
        if ab20:  a20  += 1
        if ab50:  a50  += 1
        if ab200: a200 += 1

        # ── 52W ───────────────────────────────────────────────────────────────
        hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        near52 = last >= hi52 * 0.95
        if near52:   at52 += 1
        is_new52 = bool(_new52wh(closes, 5))
        new52 += int(is_new52)

        # ── Volume rank: current 20D avg vs 3M historical avg ─────────────────
        vol_ratio = None
        if len(volumes) >= 63:
            vol_20d  = sum(volumes[-20:]) / 20
            vol_hist = sum(volumes[-63:-20]) / 43
            if vol_hist > 0:
                vr = vol_20d / vol_hist
                vol_rank_list.append(vr)
                vol_ratio = round(vr, 2)
                if vr >= 1.5:
                    vol_spike_cnt += 1

        # ── RS vs Nifty ───────────────────────────────────────────────────────
        r3 = _rs(closes, nifty_closes, 63)
        r1 = _rs(closes, nifty_closes, 21)
        if r3 is not None: rs3m_list.append(r3)
        if r1 is not None: rs1m_list.append(r1)

        # ── RS delta: RS now vs RS 4 weeks ago ────────────────────────────────
        rs_delta = None
        if len(closes) >= 84 and len(nifty_closes) >= 84:
            r3_prev = _rs(closes[:-21], nifty_closes[:-21], 63)
            if r3 is not None and r3_prev is not None:
                rs_delta = round(r3 - r3_prev, 1)
                rs_delta_list.append(rs_delta)

        # ── Period returns ────────────────────────────────────────────────────
        r1m = _period_return(closes, 21)
        r3m = _period_return(closes, 63)
        r6m = _period_return(closes, 126)
        if r1m is not None: ret1m_list.append(r1m)
        if r3m is not None: ret3m_list.append(r3m)
        if r6m is not None: ret6m_list.append(r6m)

        # ── Accumulate per-stock detail for chip display ──────────────────────
        stock_list.append({
            "ticker":   ticker,
            "price":    round(last, 2),
            "above20":  ab20,
            "above50":  ab50,
            "above200": ab200,
            "near52":   near52,
            "new52":    is_new52,
            "r1m":      round(r1m, 1) if r1m is not None else None,
            "r3m":      round(r3m, 1) if r3m is not None else None,
            "r6m":      round(r6m, 1) if r6m is not None else None,
            "rs3m":     round(r3, 1) if r3 is not None else None,
            "rs1m":     round(r1, 1) if r1 is not None else None,
            "rs_delta": rs_delta,
            "vol_ratio":vol_ratio,
        })

    if total == 0:
        return None

    def _avg(lst: list) -> float | None:
        return round(sum(lst) / len(lst), 1) if lst else None

    p20   = round(a20   / total * 100)
    p50   = round(a50   / total * 100)
    p200  = round(a200  / total * 100)
    p52   = round(at52  / total * 100)
    avg_rs3m    = _avg(rs3m_list)
    avg_rs1m    = _avg(rs1m_list)
    avg_rs_delta = _avg(rs_delta_list)   # positive = RS improving
    avg_vol_rank = _avg(vol_rank_list)   # >1 = vol expanding
    vs_pct       = round(vol_spike_cnt / total * 100)
    ind_ret_1m   = _avg(ret1m_list)
    ind_ret_3m   = _avg(ret3m_list)
    ind_ret_6m   = _avg(ret6m_list)

    # Sort stock list: above20 first, then by 3M RS descending
    stock_list.sort(key=lambda s: (not s["above20"], -(s["rs3m"] or -999)))

    # ── Stage — now uses EMA20 + RS delta for better early detection ──────────
    rs_improving = (avg_rs_delta or 0) > 1.0
    vol_expanding = (avg_vol_rank or 1.0) > 1.15
    if p20 >= 80:
        stage, sc, se = ("SURGING" if rs_improving else "EXTENDED"), "#f85149", "🔴"
    elif p20 >= 62:
        stage, sc, se = "BUILDING", "#e3b341", "🟡"
    elif p20 >= 25:
        if rs_improving and vol_expanding:
            stage, sc, se = "EMERGING★", "#22d3ee", "⭐"   # strongest early signal
        else:
            stage, sc, se = "EMERGING",  "#3fb950", "🟢"
    else:
        stage, sc, se = "WEAK",    "#475569", "⚫"

    # ── Composite trend score (0-100) ─────────────────────────────────────────
    ema_s    = p20 * 0.5 + p50 * 0.3 + p200 * 0.2          # 0-100
    rs_s     = min(max((avg_rs3m or 0) + 15, 0), 45) / 45 * 100
    rsd_s    = min(max((avg_rs_delta or 0) + 5, 0), 15) / 15 * 100
    vol_s    = min(max(((avg_vol_rank or 1.0) - 0.7) / 1.3, 0), 1) * 100
    ret3_s   = min(max((ind_ret_3m or 0) + 15, 0), 50) / 50 * 100
    trend_score = round(ema_s * 0.28 + rs_s * 0.25 + rsd_s * 0.22 + vol_s * 0.13 + ret3_s * 0.12)

    # Legacy breadth_score (keep for table column)
    breadth_score = round(p20 * 0.3 + p50 * 0.4 + p200 * 0.3)

    return {
        "industry": industry, "sector": _IND_TO_SEC.get(industry, "Other"),
        "total": total,
        "pct_20ma": p20, "pct_50ma": p50, "pct_200ma": p200, "pct_52wh": p52,
        "new_52wh": new52, "vol_spike_pct": vs_pct,
        "avg_rs3m": avg_rs3m, "avg_rs1m": avg_rs1m,
        "avg_rs_delta": avg_rs_delta,
        "avg_vol_rank": avg_vol_rank,
        "ind_ret_1m": ind_ret_1m, "ind_ret_3m": ind_ret_3m, "ind_ret_6m": ind_ret_6m,
        "stage": stage, "stage_color": sc, "stage_emoji": se,
        "breadth_score": breadth_score, "trend_score": trend_score,
        "stock_list": stock_list,   # ← per-stock data for chip display
    }


def compute_sector_metrics(sector: str, industry_data: list[dict]) -> dict:
    rows = [d for d in industry_data if d.get("sector") == sector]
    if not rows:
        return {}
    n = sum(r["total"] for r in rows)
    if n == 0:
        return {}

    def _wa(key: str) -> float:
        vals = [(r[key], r["total"]) for r in rows if r.get(key) is not None]
        if not vals: return 0.0
        return round(sum(v * w for v, w in vals) / sum(w for _, w in vals), 1)

    p20 = _wa("pct_20ma"); p50 = _wa("pct_50ma"); p200 = _wa("pct_200ma")
    rs3m = _wa("avg_rs3m"); rs1m = _wa("avg_rs1m")
    rs_delta  = _wa("avg_rs_delta")
    vol_rank  = _wa("avg_vol_rank")
    ret1m = _wa("ind_ret_1m"); ret3m = _wa("ind_ret_3m")
    trend_score = round(sum(r.get("trend_score", 0) * r["total"] for r in rows) / n)

    rs_improving  = rs_delta > 1.0
    vol_expanding = vol_rank > 1.15
    if p20 >= 80:
        stage, sc, se = ("SURGING" if rs_improving else "EXTENDED"), "#f85149", "🔴"
    elif p20 >= 62:
        stage, sc, se = "BUILDING", "#e3b341", "🟡"
    elif p20 >= 25:
        stage, sc, se = ("EMERGING★" if rs_improving and vol_expanding else "EMERGING"), \
                        ("#22d3ee" if rs_improving and vol_expanding else "#3fb950"), \
                        ("⭐" if rs_improving and vol_expanding else "🟢")
    else:
        stage, sc, se = "WEAK", "#475569", "⚫"

    EARLY = {"Financials", "Consumer", "Internet", "RealEstate"}
    MID   = {"IT", "Cap Goods", "Electronics", "Cables", "Defense", "Metals"}
    LATE  = {"Energy", "Renewable", "Chemicals", "Infra"}
    DEF   = {"FMCG", "Pharma", "Banking", "Agri", "Sugar"}
    cycle = ("Early Cycle"  if sector in EARLY else "Mid Cycle" if sector in MID
             else "Late Cycle" if sector in LATE else "Defensive" if sector in DEF else "Other")

    return {
        "sector": sector, "industry_cnt": len(rows), "stock_count": n,
        "pct_20ma": p20, "pct_50ma": p50, "pct_200ma": p200,
        "avg_rs3m": rs3m, "avg_rs1m": rs1m,
        "avg_rs_delta": rs_delta, "avg_vol_rank": vol_rank,
        "ind_ret_1m": ret1m, "ind_ret_3m": ret3m,
        "trend_score": trend_score,
        "stage": stage, "stage_color": sc, "stage_emoji": se, "cycle_phase": cycle,
    }


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _stage_cfg(stage: str) -> tuple[str, str, str, str]:
    return {"EXTENDED": ("#f85149","#1f0a0a","#f8514944","🔴"),
            "BUILDING": ("#e3b341","#1a1500","#e3b34144","🟡"),
            "EMERGING": ("#3fb950","#0a1f0e","#3fb95044","🟢"),
            "WEAK":     ("#475569","#0f1117","#47556944","⚫")
            }.get(stage, ("#475569","#0f1117","#47556944","⚫"))


def _rs_badge(v: float | None) -> str:
    if v is None: return '<span class="rs-na">—</span>'
    cls = "rs-strong" if v>=5 else "rs-pos" if v>=0 else "rs-neg" if v>=-5 else "rs-weak"
    sign = "+" if v >= 0 else ""
    return f'<span class="{cls}">{sign}{v:.1f}%</span>'


def _stage_pill(stage: str) -> str:
    c, bg, b, e = _stage_cfg(stage)
    return f'<span class="stage-pill" style="color:{c};background:{bg};border-color:{b}">{e} {stage}</span>'


def _inline_bars(p20, p50, p200) -> str:
    html = ""
    for pct, lbl in ((p20,">20MA"),(p50,">50MA"),(p200,">200MA")):
        v = max(0, min(100, pct or 0))
        clr = "#f85149" if v>=75 else "#e3b341" if v>=55 else "#3fb950" if v>=30 else "#334155"
        bw  = round(v/100*100)
        html += (f'<div class="ibar"><span class="ibar-lbl">{lbl}</span>'
                 f'<div class="ibar-track"><div class="ibar-fill" style="width:{bw}%;background:{clr}"></div></div>'
                 f'<span class="ibar-val" style="color:{clr}">{pct if pct is not None else "—"}%</span></div>')
    return html


def _breadth_strip(p20, p50, p200) -> str:
    html = ""
    for pct, lbl in ((p20,"20MA"),(p50,"50MA"),(p200,"200MA")):
        v = max(0, min(100, pct or 0))
        clr = "#f85149" if v>=75 else "#e3b341" if v>=55 else "#3fb950" if v>=30 else "#334155"
        bw  = round(v/100*100)
        html += (f'<div class="strip-row">'
                 f'<span class="strip-lbl">{lbl}</span>'
                 f'<div class="strip-track"><div class="strip-fill" style="width:{bw}%;background:{clr}"></div></div>'
                 f'<span class="strip-val" style="color:{clr}">{pct if pct is not None else "—"}%</span>'
                 f'</div>')
    return f'<div class="breadth-strip">{html}</div>'


def _pct_bar(pct: int | None, w: int = 52) -> str:
    if pct is None:
        return '<span class="pct-na">—</span>'
    v = max(0, min(100, pct))
    clr = "#f85149" if v>=75 else "#e3b341" if v>=55 else "#3fb950" if v>=30 else "#334155"
    bw  = round(v/100*w)
    return (f'<span style="color:{clr};font-weight:700;font-size:.83em">{pct}%</span>'
            f'<svg width="{w}" height="4" style="vertical-align:middle;margin-left:4px">'
            f'<rect width="{w}" height="4" rx="2" fill="#21262d"/>'
            f'<rect width="{bw}" height="4" rx="2" fill="{clr}"/></svg>')


def _score_ring(score: int) -> str:
    circ = 62.83
    pct  = max(0, min(100, score))
    dash = pct/100*circ
    clr  = "#f85149" if score>=60 else "#e3b341" if score>=40 else "#3fb950" if score>=20 else "#334155"
    return (f'<svg width="26" height="26" style="vertical-align:middle" title="Score: {score}/100">'
            f'<circle cx="13" cy="13" r="10" fill="none" stroke="#21262d" stroke-width="3"/>'
            f'<circle cx="13" cy="13" r="10" fill="none" stroke="{clr}" stroke-width="3" '
            f'stroke-dasharray="{dash:.1f} {circ:.1f}" stroke-dashoffset="{circ/4:.1f}" stroke-linecap="round"/>'
            f'<text x="13" y="17" text-anchor="middle" font-size="7.5" fill="{clr}" font-weight="bold">{score}</text>'
            f'</svg>')


def _vol_display(vs: int) -> str:
    if vs == 0: return '<span class="pct-na">—</span>'
    clr = "#f85149" if vs>=55 else "#e3b341" if vs>=25 else "#7dd3fc"
    bw  = round(vs/100*40)
    return (f'<span style="color:{clr};font-weight:{"700" if vs>=25 else "400"};font-size:.82em">{vs}%</span>'
            f'<svg width="40" height="4" style="vertical-align:middle;margin-left:3px">'
            f'<rect width="40" height="4" rx="2" fill="#21262d"/>'
            f'<rect width="{bw}" height="4" rx="2" fill="{clr}"/></svg>')


def _inline_chips(stock_list: list[dict], max_n: int = 20, show_ret: bool = True) -> str:
    """Render compact stock chips from a stock_list. Green = above 20MA, Red = below."""
    if not stock_list:
        return '<span style="color:#475569;font-size:.7em">No data</span>'
    chips = ""
    sorted_sl = sorted(stock_list, key=lambda s: (not s.get("above20",False), -(s.get("rs3m") or -999)))
    for s in sorted_sl[:max_n]:
        tk  = escape(s["ticker"])
        ab  = s.get("above20", False)
        nr  = s.get("near52", False)
        nw  = s.get("new52", False)
        r3  = s.get("r3m")
        rs  = s.get("rs3m")
        r3t = f" {r3:+.0f}%" if r3 is not None else ""
        chip_clr = "#3fb950" if ab else "#f85149"
        chip_bg  = "#071a0c" if ab else "#1a0707"
        star = "🏔" if nw else ("⭐" if nr else "")
        tip  = f"{tk}: 3M{r3t} RS:{rs:+.0f}%" if rs is not None else tk
        chips += (
            f'<span class="ind-chip" title="{escape(tip)}" '
            f'style="color:{chip_clr};background:{chip_bg};border:1px solid {chip_clr}44">'
            f'{star}{tk}'
            f'{"" if not show_ret or r3t == "" else r3t}</span>'
        )
    if len(sorted_sl) > max_n:
        chips += f'<span style="color:#475569;font-size:.65em"> +{len(sorted_sl)-max_n} more</span>'
    return chips


# ── build_html ─────────────────────────────────────────────────────────────────

def _theme_perf_card(tm: dict) -> str:
    """Render one custom theme performance card."""
    color   = tm.get("color", "#58a6ff")
    stage   = tm["stage"]
    sc, sbg, sb, _ = _stage_cfg(stage)
    theme_rets  = tm["theme_rets"]
    nifty_rets  = tm["nifty_rets"]
    alphas      = tm["alphas"]
    top         = tm.get("top_performers", [])
    bot         = tm.get("bottom_performers", [])
    tracked     = tm["stocks_tracked"]
    total       = tm["stocks_total"]
    p20         = tm["pct_20ma"]; p50 = tm["pct_50ma"]; p200 = tm["pct_200ma"]
    rs3m        = tm.get("avg_rs3m")
    vs          = tm.get("vol_spike_pct", 0)
    n52         = tm.get("new_52wh", 0)

    # ── Performance table ─────────────────────────────────────────────────────
    PERIOD_ORDER = ["1W", "1M", "3M", "6M", "1Y"]
    MAX_BAR = {"1W": 8, "1M": 20, "3M": 50, "6M": 80, "1Y": 150}

    perf_cols = ""
    for p in PERIOD_ORDER:
        tr = theme_rets.get(p)
        nr = nifty_rets.get(p)
        al = alphas.get(p)
        if tr is None:
            perf_cols += f'<div class="tc-period"><div class="tc-per-lbl">{p}</div><div class="tc-per-na">—</div></div>'
            continue
        maxb  = MAX_BAR[p]
        # Theme bar
        t_pct = min(abs(tr) / maxb * 100, 100)
        t_clr = "#3fb950" if tr >= 0 else "#f85149"
        t_dir = "right" if tr >= 0 else "left"
        t_sign = "+" if tr >= 0 else ""
        # Alpha badge
        al_clr = "#3fb950" if (al or 0) >= 0 else "#f85149"
        al_txt = f"{'+' if (al or 0)>=0 else ''}{al:.1f}%" if al is not None else "—"
        nr_txt = f"{'+' if (nr or 0)>=0 else ''}{nr:.1f}%" if nr is not None else "—"
        perf_cols += (
            f'<div class="tc-period">'
            f'<div class="tc-per-lbl">{p}</div>'
            f'<div class="tc-per-val" style="color:{t_clr}">{t_sign}{tr:.1f}%</div>'
            f'<div class="tc-bar-wrap">'
            f'<div class="tc-bar" style="width:{t_pct:.0f}%;background:{t_clr}"></div>'
            f'</div>'
            f'<div class="tc-nifty">Nifty: {nr_txt}</div>'
            f'<div class="tc-alpha" style="color:{al_clr}">α {al_txt}</div>'
            f'</div>'
        )

    # ── Breadth strip ─────────────────────────────────────────────────────────
    breadth_html = _breadth_strip(p20, p50, p200)

    # ── Top / bottom performers ───────────────────────────────────────────────
    def _perf_row(ticker: str, ret: float) -> str:
        clr = "#3fb950" if ret >= 0 else "#f85149"
        sign = "+" if ret >= 0 else ""
        return (f'<div class="tc-stock-row">'
                f'<span class="tc-stock-sym">{ticker}</span>'
                f'<span class="tc-stock-ret" style="color:{clr}">{sign}{ret:.1f}%</span>'
                f'</div>')

    top_html = "".join(_perf_row(t, r) for t, r in top[:5]) if top else '<div class="tc-na">Insufficient data</div>'
    bot_html = "".join(_perf_row(t, r) for t, r in bot[:4]) if bot else ""

    # ── Extras row ────────────────────────────────────────────────────────────
    extras = []
    if vs >= 15:
        extras.append(f'<span class="tc-tag tc-tag-vol">🔥 {vs}% vol spike</span>')
    if n52 > 0:
        extras.append(f'<span class="tc-tag tc-tag-hi">🏔 {n52} new 52W hi</span>')
    extras_html = "".join(extras)

    # ── Stock chips: all stocks color-coded by 20MA status ───────────────────
    stock_breadth_list = tm.get("stock_breadth", [])
    above_chips = [(sb["ticker"], sb.get("r3m"), True)  for sb in stock_breadth_list if sb.get("above20")]
    below_chips = [(sb["ticker"], sb.get("r3m"), False) for sb in stock_breadth_list if not sb.get("above20")]
    all_chips_html = ""
    for ticker_c, r3m_c, above in (
        sorted(above_chips, key=lambda x: -(x[1] or -999)) +
        sorted(below_chips, key=lambda x: -(x[1] or -999))
    ):
        chip_clr = "#3fb950" if above else "#f85149"
        chip_bg  = "#071a0c" if above else "#1a0707"
        r3m_txt  = f" {r3m_c:+.0f}%" if r3m_c is not None else ""
        all_chips_html += (
            f'<span class="tc-chip" title="{escape(ticker_c)}: 3M {r3m_txt.strip() if r3m_txt else "N/A"}" '
            f'style="color:{chip_clr};background:{chip_bg};border:1px solid {chip_clr}44">'
            f'{escape(ticker_c)}{r3m_txt}</span>'
        )
    above_cnt = len(above_chips)
    below_cnt = len(below_chips)
    stocks_section_html = (
        f'<div class="tc-stocks-wrap">'
        f'<div class="tc-stocks-hdr">'
        f'<span class="tc-stocks-title">📋 All {tracked} Stocks</span>'
        f'<span class="tc-stocks-legend">'
        f'<span class="tc-leg-dot" style="background:#3fb950"></span>Above 20MA: {above_cnt}'
        f'&nbsp;&nbsp;<span class="tc-leg-dot" style="background:#f85149"></span>Below: {below_cnt}'
        f'</span>'
        f'</div>'
        f'<div class="tc-chips">{all_chips_html if all_chips_html else "<span class=tc-na>No data</span>"}</div>'
        f'</div>'
    )

    # Use data-theme attribute so browser auto-decodes HTML entities (& vs &amp;)
    # This guarantees showThemeDrilldown receives the same key as in drilldownData JSON
    safe_data_attr = escape(tm["theme"])   # safe for HTML attribute display
    return (
        f'<div class="tc-card" style="border-top:3px solid {color}">'
        f'<div class="tc-hdr">'
        f'<div class="tc-title"><span class="tc-emoji">{tm["emoji"]}</span> {escape(tm["theme"])}</div>'
        f'<div class="tc-hdr-right">'
        f'{_stage_pill(stage)}'
        f'<span class="tc-tracked">{tracked}/{total} stocks</span>'
        f'</div>'
        f'</div>'
        f'<div class="tc-desc">{escape(tm["description"])}</div>'
        f'<div class="tc-perf-row">{perf_cols}</div>'
        f'{breadth_html}'
        f'{stocks_section_html}'
        f'<div class="tc-body">'
        f'<div class="tc-perf-col">'
        f'<div class="tc-col-title">🏆 Top 3M performers</div>'
        f'{top_html}'
        f'</div>'
        f'{"<div class=tc-perf-col><div class=tc-col-title>📉 Laggards</div>" + bot_html + "</div>" if bot_html else ""}'
        f'</div>'
        f'<div class="tc-footer">'
        f'<span class="rs-label">RS 3M</span>{_rs_badge(rs3m)}'
        f'{" &nbsp;" + extras_html if extras_html else ""}'
        f'<button class="tc-drillbtn" data-theme="{safe_data_attr}" onclick="showThemeDrilldown(this.dataset.theme)">🔍 Full Detail</button>'
        f'</div>'
        f'</div>'
    )


def build_html(
    industry_data: list[dict],
    sector_data: list[dict],
    theme_data: list[dict] | None = None,
    *,
    regime: dict | None = None,
    pulse: dict | None = None,
    oscillator: dict | None = None,
    divergences: dict | None = None,
    trajectories: dict | None = None,
    sm_footprint: list[dict] | None = None,
    rotation: list[dict] | None = None,
    mom_matrix: list[dict] | None = None,
    opportunities: list[dict] | None = None,
) -> str:
    total_ind    = len(industry_data)
    total_stocks = sum(d["total"] for d in industry_data)
    ec = sum(1 for d in industry_data if d["stage"]=="EMERGING")
    bc = sum(1 for d in industry_data if d["stage"]=="BUILDING")
    xc = sum(1 for d in industry_data if d["stage"]=="EXTENDED")
    wc = sum(1 for d in industry_data if d["stage"]=="WEAK")

    vol_clusters = sorted([d for d in industry_data if d.get("vol_spike_pct",0)>=15],
                          key=lambda x: -x.get("vol_spike_pct",0))[:12]
    hi52_leaders = sorted([d for d in industry_data if d.get("new_52wh",0)>0],
                          key=lambda x: -x.get("new_52wh",0))[:12]
    early_trends = sorted([d for d in industry_data if d["stage"] in ("EMERGING","BUILDING","EMERGING★","SURGING")],
                          key=lambda x: -(x.get("avg_rs3m") or -99))[:24]

    # ── Custom theme cards ────────────────────────────────────────────────────
    theme_cards_html = ""
    drilldown_data: dict[str, list] = {}
    if theme_data:
        for tm in theme_data:
            theme_cards_html += _theme_perf_card(tm)
            # Use all_stocks_modal so the "Full Detail" modal always has stocks to show
            # (includes untracked stocks marked with no_data=True)
            drilldown_data[tm["theme"]] = tm.get("all_stocks_modal") or tm.get("stock_breadth", [])
    theme_section_count = len(theme_data) if theme_data else 0

    # ── Industry stock lookup for card rendering ──────────────────────────────
    ind_stock_lookup: dict[str, list] = {d["industry"]: d.get("stock_list", []) for d in industry_data}

    # ── Default empty dicts/lists for new analytics ───────────────────────────
    regime       = regime       or {}
    pulse        = pulse        or {}
    oscillator   = oscillator   or {}
    divergences  = divergences  or {"bullish": [], "bearish": []}
    trajectories = trajectories or {"accelerating": [], "improving": [], "decelerating": [], "collapsing": []}
    sm_footprint = sm_footprint or []
    rotation     = rotation     or sector_data
    mom_matrix   = mom_matrix   or sector_data
    opportunities= opportunities or []

    # ── Badge / display helpers (defined early so new sections can use them) ──

    def _ret_badge(v: float | None) -> str:
        if v is None: return '<span class="pct-na">—</span>'
        clr = "#3fb950" if v >= 0 else "#f85149"
        sign = "+" if v >= 0 else ""
        fw = "700" if abs(v) >= 5 else "500"
        return f'<span style="color:{clr};font-weight:{fw};font-size:.82em">{sign}{v:.1f}%</span>'

    def _vol_badge(vr: float | None) -> str:
        if vr is None: return '<span class="pct-na">—</span>'
        if vr >= 1.5:   clr, lbl = "#f85149", "🔥"
        elif vr >= 1.2: clr, lbl = "#e3b341", "↑"
        elif vr >= 0.85:clr, lbl = "#475569", "→"
        else:            clr, lbl = "#7dd3fc", "↓"
        return f'<span style="color:{clr};font-size:.78em;font-weight:600">{lbl} {vr:.2f}x</span>'

    def _rsd_badge(v: float | None) -> str:
        if v is None: return '<span class="pct-na">—</span>'
        clr = "#22d3ee" if v >= 3 else "#3fb950" if v >= 0 else "#f87171" if v > -3 else "#f85149"
        arr = "▲" if v > 0 else "▼"
        return f'<span style="color:{clr};font-size:.8em;font-weight:700">{arr} {v:+.1f}%</span>'

    def _trend_ring(score: int) -> str:
        circ = 62.83
        dash = max(0, min(score, 100)) / 100 * circ
        clr = "#22d3ee" if score >= 65 else "#e3b341" if score >= 45 else "#3fb950" if score >= 30 else "#475569"
        return (f'<svg width="30" height="30" style="vertical-align:middle" title="Trend Score: {score}/100">'
                f'<circle cx="15" cy="15" r="11" fill="none" stroke="#21262d" stroke-width="3.5"/>'
                f'<circle cx="15" cy="15" r="11" fill="none" stroke="{clr}" stroke-width="3.5" '
                f'stroke-dasharray="{dash:.1f} {circ:.1f}" stroke-dashoffset="{circ/4:.1f}" stroke-linecap="round"/>'
                f'<text x="15" y="20" text-anchor="middle" font-size="8.5" fill="{clr}" font-weight="bold">{score}</text>'
                f'</svg>')

    # ── Market Regime Banner ──────────────────────────────────────────────────
    reg_color  = regime.get("color", "#475569")
    reg_score  = regime.get("regime_score", 50)
    reg_label  = regime.get("regime", "N/A")
    reg_emoji  = regime.get("emoji", "—")
    reg_desc   = regime.get("description", "")
    reg_action = regime.get("action", "")
    reg_med20  = regime.get("median_p20", 0)
    reg_med50  = regime.get("median_p50", 0)
    reg_med200 = regime.get("median_p200", 0)
    reg_avgrs  = regime.get("avg_rs", 0)
    reg_rsipct = regime.get("rs_improving_pct", 0)
    reg_vexpct = regime.get("vol_expanding_pct", 0)
    reg_nh     = regime.get("new_highs_total", 0)
    reg_bcnt   = regime.get("pct_bull_industries", 0)
    reg_wcnt   = regime.get("pct_weak_industries", 0)
    reg_ecnt   = regime.get("pct_emerging_industries", 0)

    # Score ring for regime
    def _reg_ring(score: int, color: str) -> str:
        circ = 62.83; dash = score / 100 * circ
        return (f'<svg width="54" height="54" style="vertical-align:middle">'
                f'<circle cx="27" cy="27" r="22" fill="none" stroke="#21262d" stroke-width="5"/>'
                f'<circle cx="27" cy="27" r="22" fill="none" stroke="{color}" stroke-width="5" '
                f'stroke-dasharray="{dash:.1f} {circ:.1f}" stroke-dashoffset="{circ/4:.1f}" stroke-linecap="round"/>'
                f'<text x="27" y="32" text-anchor="middle" font-size="13" fill="{color}" font-weight="900">{score}</text>'
                f'</svg>')

    regime_banner_html = (
        f'<div class="regime-banner" style="border-color:{reg_color}22;background:linear-gradient(135deg,{reg_color}08,#0d1117)">'
        f'<div class="regime-left">'
        f'{_reg_ring(reg_score, reg_color)}'
        f'<div class="regime-info">'
        f'<div class="regime-label" style="color:{reg_color}">{reg_emoji} {reg_label}</div>'
        f'<div class="regime-desc">{escape(reg_desc)}</div>'
        f'<div class="regime-action" style="color:{reg_color}cc">▸ {escape(reg_action)}</div>'
        f'</div>'
        f'</div>'
        f'<div class="regime-stats">'
        f'<div class="rst"><div class="rst-v" style="color:{reg_color}">{reg_med20:.0f}%</div><div class="rst-l">Med&gt;20MA</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:{reg_color}">{reg_med50:.0f}%</div><div class="rst-l">Med&gt;50MA</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:{reg_color}">{reg_med200:.0f}%</div><div class="rst-l">Med&gt;200MA</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:{"#3fb950" if reg_avgrs>=0 else "#f85149"}">{reg_avgrs:+.1f}%</div><div class="rst-l">Avg RS</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:#22d3ee">{reg_rsipct:.0f}%</div><div class="rst-l">RS↑ Inds</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:#e3b341">{reg_vexpct:.0f}%</div><div class="rst-l">Vol↑ Inds</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:#4ade80">{reg_nh}</div><div class="rst-l">New Highs</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:#f85149">{reg_wcnt:.0f}%</div><div class="rst-l">Weak</div></div>'
        f'<div class="rst"><div class="rst-v" style="color:#3fb950">{reg_bcnt:.0f}%</div><div class="rst-l">Bull Inds</div></div>'
        f'</div>'
        f'</div>'
    )

    # ── Breadth Oscillator + Pulse bar ───────────────────────────────────────
    osc_val   = oscillator.get("oscillator", 0)
    osc_sig   = oscillator.get("signal", "—")
    osc_col   = oscillator.get("signal_color", "#475569")
    osc_adv   = oscillator.get("advancing", 0)
    osc_dec   = oscillator.get("declining", 0)
    osc_net   = oscillator.get("adl_net", 0)
    pulse_thr = pulse.get("thrust_signal", "—")
    pulse_tc  = pulse.get("thrust_color", "#475569")
    pulse_tdesc = pulse.get("thrust_desc", "")
    pulse_rsip  = pulse.get("rs_improving_pct", 0)
    pulse_adv   = pulse.get("advancing", 0)
    pulse_dec   = pulse.get("declining", 0)
    pulse_nh    = pulse.get("new_highs_ind", 0)
    pulse_nl    = pulse.get("new_lows_ind", 0)
    pulse_volx  = pulse.get("vol_expanding", 0)
    pulse_adlr  = pulse.get("adl_ratio", 0)

    osc_bar_pct  = min(max((osc_val + 10) / 20 * 100, 0), 100)
    adv_pct = pulse_adv / max(pulse_adv + pulse_dec, 1) * 100

    pulse_html = (
        f'<div class="pulse-bar">'
        f'<div class="pulse-item"><span class="pulse-lbl">🎯 Thrust</span>'
        f'<span class="pulse-val" style="color:{pulse_tc};font-weight:800">{pulse_thr}</span>'
        f'<span class="pulse-sub">{escape(pulse_tdesc[:70])}</span></div>'
        f'<div class="pulse-item"><span class="pulse-lbl">📊 Oscillator</span>'
        f'<span class="pulse-val" style="color:{osc_col}">{osc_sig} ({osc_val:+.1f})</span>'
        f'<span class="pulse-sub">Adv {osc_adv} · Dec {osc_dec} · Net {osc_net:+d}</span></div>'
        f'<div class="pulse-item"><span class="pulse-lbl">📈 RS Improving</span>'
        f'<span class="pulse-val" style="color:{"#3fb950" if pulse_rsip>=50 else "#e3b341" if pulse_rsip>=35 else "#f85149"}">{pulse_rsip:.0f}%</span>'
        f'<span class="pulse-sub">{pulse_adv} adv · {pulse_dec} dec · ratio {pulse_adlr:.1f}x</span></div>'
        f'<div class="pulse-item"><span class="pulse-lbl">🏔 New Highs</span>'
        f'<span class="pulse-val" style="color:#4ade80">{pulse_nh} inds</span>'
        f'<span class="pulse-sub">New lows: {pulse_nl} · Vol expanding: {pulse_volx}</span></div>'
        f'</div>'
    )

    # ── Best Opportunities section ────────────────────────────────────────────
    opp_rows = ""
    for d in opportunities[:15]:
        ind   = d.get("industry",""); sec = d.get("sector","")
        stage = d.get("stage","")
        osc2, sbg, sb, _ = _stage_cfg(stage)
        ts    = d.get("trend_score", 0)
        opp_s = d.get("opportunity_score", 0)
        p20   = d.get("pct_20ma"); rs3m = d.get("avg_rs3m"); rsd = d.get("avg_rs_delta")
        vr    = d.get("avg_vol_rank"); r3m = d.get("ind_ret_3m"); n52 = d.get("new_52wh", 0)
        n     = d.get("total", 0)
        n52_tag = f'<span style="color:#4ade80;font-size:.7em;margin-left:3px">🏔{n52}</span>' if n52 else ""
        opp_bar = round(opp_s)
        ob_clr  = "#22d3ee" if opp_s >= 55 else "#3fb950" if opp_s >= 35 else "#e3b341"
        ind_esc = escape(ind)
        opp_rows += (
            f'<tr class="opp-row" onclick="filterIndustry(\'{escape(ind.replace(chr(39),""))}\')">'
            f'<td class="ldr-name">{ind_esc}{n52_tag}</td>'
            f'<td><span class="sec-badge">{escape(sec)}</span></td>'
            f'<td>{_stage_pill(stage)}</td>'
            f'<td style="text-align:right">{_pct_bar(p20,40)}</td>'
            f'<td style="text-align:right">{_rs_badge(rs3m)}</td>'
            f'<td style="text-align:right">{_rsd_badge(rsd)}</td>'
            f'<td style="text-align:right">{_vol_badge(vr)}</td>'
            f'<td style="text-align:right">{_ret_badge(r3m)}</td>'
            f'<td style="text-align:center">'
            f'<svg width="44" height="8" style="vertical-align:middle"><rect width="44" height="8" rx="4" fill="#21262d"/>'
            f'<rect width="{round(opp_bar*44/100)}" height="8" rx="4" fill="{ob_clr}"/></svg>'
            f'<span style="color:{ob_clr};font-size:.75em;font-weight:700;margin-left:4px">{opp_s:.0f}</span>'
            f'</td>'
            f'<td class="pct-na" style="text-align:right;font-size:.7em">{n}</td>'
            f'</tr>'
        )

    # ── Trajectory section ────────────────────────────────────────────────────
    def _traj_card(d: dict) -> str:
        ind   = d.get("industry",""); sec = d.get("sector","")
        stage = d.get("stage",""); traj = d.get("trajectory",""); emoji = d.get("traj_emoji","")
        color = d.get("traj_color","#475569"); insight = d.get("insight","")
        rsd   = d.get("avg_rs_delta"); vr = d.get("avg_vol_rank"); p20 = d.get("pct_20ma",0)
        rs3m  = d.get("avg_rs3m"); r3m = d.get("ind_ret_3m"); n = d.get("total",0)
        safe  = escape(ind.replace("'",""))
        sl    = d.get("stock_list") or ind_stock_lookup.get(ind, [])
        chips = _inline_chips(sl[:12]) if sl else ""
        above_n = sum(1 for s in sl if s.get("above20")) if sl else 0
        chips_section = (
            f'<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px">'
            f'<span style="font-size:.6em;color:#475569;margin-right:3px">{len(sl)} stocks '
            f'({above_n}▲):</span>{chips}</div>'
        ) if sl else ""
        return (
            f'<div class="traj-card" style="border-left:3px solid {color}" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="traj-top">'
            f'<div><div class="traj-name">{escape(ind)}</div><div class="traj-sec">{escape(sec)} · {n} stocks</div></div>'
            f'<span class="traj-badge" style="color:{color}">{emoji} {traj}</span>'
            f'</div>'
            f'<div class="traj-stats">'
            f'<span class="rs-label">RS Δ</span>{_rsd_badge(rsd)}'
            f'<span class="rs-label" style="margin-left:8px">RS</span>{_rs_badge(rs3m)}'
            f'<span class="rs-label" style="margin-left:8px">Vol</span>{_vol_badge(vr)}'
            f'<span class="rs-label" style="margin-left:8px">3M</span>{_ret_badge(r3m)}'
            f'</div>'
            f'<div class="traj-insight" style="color:{color}aa">{escape(insight)}</div>'
            f'{chips_section}'
            f'</div>'
        )

    acc_cards   = "".join(_traj_card(d) for d in trajectories.get("accelerating", []))
    imp_cards   = "".join(_traj_card(d) for d in trajectories.get("improving", [])[:10])
    dec_cards   = "".join(_traj_card(d) for d in trajectories.get("decelerating", []))
    col_cards   = "".join(_traj_card(d) for d in trajectories.get("collapsing", []))

    # ── Smart Money Footprint ─────────────────────────────────────────────────
    def _sm_card(d: dict) -> str:
        ind   = d.get("industry",""); sec = d.get("sector","")
        stage = d.get("stage",""); score = d.get("institutional_score",0)
        sig   = d.get("signal_label",""); vr = d.get("avg_vol_rank",1.0)
        n52   = d.get("new_52wh",0); vs = d.get("vol_spike_pct",0)
        rsd   = d.get("avg_rs_delta"); rs3m = d.get("avg_rs3m"); n = d.get("total",0)
        p20   = d.get("pct_20ma",0); sc2,sbg,sb,_ = _stage_cfg(stage)
        bar_w = round(score / 100 * 100)
        safe  = escape(ind.replace("'",""))
        bar_c = "#22d3ee" if score >= 50 else "#3fb950" if score >= 30 else "#e3b341"
        sl    = d.get("stock_list") or ind_stock_lookup.get(ind, [])
        chips = _inline_chips(sl[:12]) if sl else ""
        above_n = sum(1 for s in sl if s.get("above20")) if sl else 0
        new52_stocks = [s["ticker"] for s in sl if s.get("new52")] if sl else []
        new52_txt = f' 🏔 {", ".join(new52_stocks[:4])}{"…" if len(new52_stocks)>4 else ""}' if new52_stocks else ""
        chips_section = (
            f'<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:3px">{chips}</div>'
        ) if sl else ""
        return (
            f'<div class="sm-card" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="sm-top"><div class="sm-name">{escape(ind)}</div>'
            f'<div class="sm-score" style="color:{bar_c}">{score:.0f}/100</div></div>'
            f'<div class="sm-sec">{escape(sec)} · {stage} · {n} stocks ({above_n}▲20MA)</div>'
            f'<div class="sm-track"><div class="sm-fill" style="width:{bar_w}%;background:{bar_c}"></div></div>'
            f'<div class="sm-sig">{escape(sig)}{new52_txt}</div>'
            f'<div class="sm-stats">'
            f'<span class="rs-label">RSΔ</span>{_rsd_badge(rsd)}'
            f'<span class="rs-label" style="margin-left:6px">RS</span>{_rs_badge(rs3m)}'
            f'<span class="rs-label" style="margin-left:6px">Vol</span>{_vol_badge(vr)}'
            f'{"<span style=color:#4ade80;font-size:.72em;margin-left:8px>🏔"+str(n52)+"</span>" if n52 else ""}'
            f'</div>'
            f'{chips_section}'
            f'</div>'
        )

    sm_cards = "".join(_sm_card(d) for d in sm_footprint[:12])

    # ── Divergence section ────────────────────────────────────────────────────
    def _div_card(d: dict, div_type: str) -> str:
        ind   = d.get("industry",""); sec = d.get("sector","")
        stage = d.get("stage",""); sig = d.get("signal_label","")
        why   = d.get("why","")
        rsd   = d.get("avg_rs_delta"); vr = d.get("avg_vol_rank",1.0)
        rs3m  = d.get("avg_rs3m"); r3m = d.get("ind_ret_3m"); n = d.get("total",0)
        sc2 = "#22d3ee" if div_type == "BULLISH" else "#f85149"
        bdr = "#22d3ee33" if div_type == "BULLISH" else "#f8514933"
        label = "🔵 BULLISH DIVERGENCE" if div_type == "BULLISH" else "🔴 BEARISH DIVERGENCE"
        score_key = "opportunity_score" if div_type == "BULLISH" else "risk_score"
        score = d.get(score_key, 0)
        safe  = escape(ind.replace("'",""))
        return (
            f'<div class="div-card" style="border-left:3px solid {sc2};background:{bdr}08" '
            f'onclick="filterIndustry(\'{safe}\')">'
            f'<div class="div-top">'
            f'<div><div class="div-name">{escape(ind)}</div><div class="div-sec">{escape(sec)} · {n} stocks</div></div>'
            f'<span class="div-badge" style="color:{sc2};border-color:{sc2}44">{label}</span>'
            f'</div>'
            f'<div class="div-sig">{escape(sig)}</div>'
            f'<div class="div-why">{escape(why)}</div>'
            f'<div class="div-stats">'
            f'<span class="rs-label">RSΔ</span>{_rsd_badge(rsd)}'
            f'<span class="rs-label" style="margin-left:6px">RS</span>{_rs_badge(rs3m)}'
            f'<span class="rs-label" style="margin-left:6px">Vol</span>{_vol_badge(vr)}'
            f'<span class="rs-label" style="margin-left:6px">3M</span>{_ret_badge(r3m)}'
            f'<span style="color:{sc2};font-size:.7em;margin-left:auto;font-weight:700">Score: {score:.0f}</span>'
            f'</div>'
            f'</div>'
        )

    bull_div_html = "".join(_div_card(d, "BULLISH") for d in divergences.get("bullish", []))
    bear_div_html = "".join(_div_card(d, "BEARISH") for d in divergences.get("bearish", []))

    # ── Sector Rotation Matrix ────────────────────────────────────────────────
    CYCLE_SECTION = {"Early Cycle": [], "Mid Cycle": [], "Late Cycle": [], "Defensive": []}
    for sd in (rotation if rotation else sector_data):
        cp = sd.get("cycle_phase", "Other")
        if cp in CYCLE_SECTION:
            CYCLE_SECTION[cp].append(sd)

    def _rot_card(sd: dict) -> str:
        sec    = sd.get("sector","")
        stage  = sd.get("stage","")
        rs     = sd.get("avg_rs3m"); rsd = sd.get("avg_rs_delta")
        rsig   = sd.get("rotation_signal","NEUTRAL"); rc = sd.get("rotation_color","#475569")
        re_    = sd.get("rotation_emoji",""); rscore = sd.get("rotation_score",0)
        ts     = sd.get("trend_score",0); n = sd.get("stock_count",0)
        sc2, *_ = _stage_cfg(stage)
        return (
            f'<div class="rot-card" style="border-top:2px solid {rc}">'
            f'<div class="rot-top"><div class="rot-name">{escape(sec)}</div>'
            f'<span style="color:{rc};font-size:.72em;font-weight:800">{re_} {rsig}</span></div>'
            f'<div class="rot-score" style="color:{rc}">{rscore:+.0f}</div>'
            f'<div style="display:flex;gap:8px;margin-top:6px;flex-wrap:wrap">'
            f'<div><span class="rs-label">RS</span>{_rs_badge(rs)}</div>'
            f'<div><span class="rs-label">RSΔ</span>{_rsd_badge(rsd)}</div>'
            f'</div>'
            f'<div style="margin-top:6px">{_stage_pill(stage)}'
            f'<span class="pct-na" style="margin-left:6px;font-size:.65em">{n} stocks</span></div>'
            f'</div>'
        )

    CYCLE_LABELS = {
        "Early Cycle": ("💹 Early Cycle", "Money rotates here first at cycle bottom — Financials, Consumer, Internet"),
        "Mid Cycle":   ("⚙️ Mid Cycle",    "Growth phase — IT, Electronics, Cap Goods, Defense, Cables"),
        "Late Cycle":  ("🔩 Late Cycle",   "Commodity / capex peak — Metals, Chemicals, Energy, Infra"),
        "Defensive":   ("🛡️ Defensive",    "Safe haven during slowdowns — Pharma, FMCG, Banking"),
    }
    rotation_html = ""
    for phase, (lbl, desc) in CYCLE_LABELS.items():
        cards = "".join(_rot_card(sd) for sd in sorted(
            CYCLE_SECTION[phase], key=lambda x: -x.get("rotation_score", 0)
        ))
        CCLS = {"Early Cycle":"cycle-early","Mid Cycle":"cycle-mid","Late Cycle":"cycle-late","Defensive":"cycle-def"}
        ccls = CCLS.get(phase, "")
        rotation_html += (
            f'<div class="rot-phase">'
            f'<div class="rot-phase-hdr"><span class="{ccls} cycle-badge">{lbl}</span>'
            f'<span class="rot-phase-desc">{escape(desc)}</span></div>'
            f'<div class="rot-phase-cards">{cards if cards else "<span class=pct-na>No data</span>"}</div>'
            f'</div>'
        )

    # ── Trend Leaders table (top 20 by trend_score) ───────────────────────────
    trend_leaders = sorted(industry_data, key=lambda x: -x.get("trend_score", 0))[:20]
    rs_rising = sorted(
        [d for d in industry_data if (d.get("avg_rs_delta") or -99) > 0.5],
        key=lambda x: -(x.get("avg_rs_delta") or 0)
    )[:15]


    leaders_rows = ""
    for d in trend_leaders:
        ind = d["industry"]; sec = d.get("sector","")
        stage = d["stage"]; sc2, sbg, sb, _ = _stage_cfg(stage)
        ts = d.get("trend_score", 0)
        rsd = d.get("avg_rs_delta"); vr = d.get("avg_vol_rank")
        r1m = d.get("ind_ret_1m"); r3m = d.get("ind_ret_3m")
        rs3m = d.get("avg_rs3m"); p20 = d.get("pct_20ma"); n = d.get("total", 0)
        ind_esc = escape(ind)
        leaders_rows += (
            f'<tr style="border-left:3px solid {sc2}33" onclick="filterIndustry(\'{escape(ind.replace(chr(39),""))}\')" class="ldr-row">'
            f'<td class="ldr-name" title="{ind_esc}">{ind_esc}</td>'
            f'<td><span class="sec-badge">{escape(sec)}</span></td>'
            f'<td>{_stage_pill(stage)}</td>'
            f'<td style="text-align:right">{_pct_bar(p20, 40)}</td>'
            f'<td style="text-align:right">{_ret_badge(r1m)}</td>'
            f'<td style="text-align:right">{_ret_badge(r3m)}</td>'
            f'<td style="text-align:right">{_rs_badge(rs3m)}</td>'
            f'<td style="text-align:right">{_rsd_badge(rsd)}</td>'
            f'<td style="text-align:right">{_vol_badge(vr)}</td>'
            f'<td style="text-align:center">{_trend_ring(ts)}</td>'
            f'<td class="pct-na" style="text-align:right;font-size:.75em">{n}</td>'
            f'</tr>'
        )

    rs_rising_rows = ""
    for d in rs_rising:
        ind = d["industry"]; sec = d.get("sector","")
        stage = d["stage"]; sc2, *_ = _stage_cfg(stage)
        rsd = d.get("avg_rs_delta"); rs3m = d.get("avg_rs3m")
        vr = d.get("avg_vol_rank"); r3m = d.get("ind_ret_3m")
        ind_esc = escape(ind)
        rs_rising_rows += (
            f'<tr class="ldr-row" onclick="filterIndustry(\'{escape(ind.replace(chr(39),""))}\')">'
            f'<td class="ldr-name">{ind_esc}</td>'
            f'<td><span class="sec-badge">{escape(sec)}</span></td>'
            f'<td>{_stage_pill(stage)}</td>'
            f'<td style="text-align:right">{_rsd_badge(rsd)}</td>'
            f'<td style="text-align:right">{_rs_badge(rs3m)}</td>'
            f'<td style="text-align:right">{_ret_badge(r3m)}</td>'
            f'<td style="text-align:right">{_vol_badge(vr)}</td>'
            f'</tr>'
        )

    # ── Sector scorecard (enhanced) ───────────────────────────────────────────
    CYCLE_CLS = {"Early Cycle":"cycle-early","Mid Cycle":"cycle-mid",
                 "Late Cycle":"cycle-late","Defensive":"cycle-def"}
    sec_cards = ""
    for sd in sorted(sector_data, key=lambda x: -(x.get("trend_score") or 0)):
        sec   = sd["sector"]
        p20   = sd.get("pct_20ma"); p50 = sd.get("pct_50ma"); p200 = sd.get("pct_200ma")
        rs3m  = sd.get("avg_rs3m"); rs1m = sd.get("avg_rs1m")
        rsd   = sd.get("avg_rs_delta"); vr = sd.get("avg_vol_rank")
        r1m   = sd.get("ind_ret_1m"); r3m = sd.get("ind_ret_3m")
        ts    = sd.get("trend_score", 0)
        stage = sd["stage"]; sc,sbg,sb,se = _stage_cfg(stage)
        n     = sd["stock_count"]; ni = sd.get("industry_cnt",0)
        cycle = sd.get("cycle_phase","Other"); ccls = CYCLE_CLS.get(cycle,"")
        rs_up = (rsd or 0) > 0.5
        rsd_arrow = f'<span style="color:{"#22d3ee" if rs_up else "#f87171"};font-weight:700;font-size:.9em">{"▲" if rs_up else "▼"}</span>'
        # Top stocks in this sector: aggregate from industry data
        sec_stocks = []
        for d in industry_data:
            if d.get("sector") == sec:
                sec_stocks.extend(d.get("stock_list", []))
        sec_stocks_sorted = sorted(sec_stocks, key=lambda s: (not s.get("above20"), -(s.get("rs3m") or -999)))
        above_n = sum(1 for s in sec_stocks_sorted if s.get("above20"))
        chips_html = _inline_chips(sec_stocks_sorted[:16]) if sec_stocks_sorted else ""
        chips_section = (
            f'<div style="margin-top:8px;padding-top:6px;border-top:1px solid #1a2030">'
            f'<div style="font-size:.58em;color:#475569;margin-bottom:4px">'
            f'Top stocks · {above_n}▲ / {len(sec_stocks_sorted)-above_n}▼ 20MA</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:3px">{chips_html}</div>'
            f'</div>'
        ) if chips_html else ""
        sec_cards += (
            f'<div class="sec-card" style="border-top:3px solid {sc}">'
            f'<div class="sec-top"><div class="sec-name">{escape(sec)}</div>'
            f'<div style="display:flex;align-items:center;gap:5px">{_trend_ring(ts)}{_stage_pill(stage)}</div>'
            f'</div>'
            f'<div class="sec-meta"><span class="{ccls} cycle-badge">{cycle}</span>'
            f'<span class="sec-n">{n} stocks · {ni} ind.</span></div>'
            f'<div class="ibar-group">{_inline_bars(p20,p50,p200)}</div>'
            f'<div class="sec-kv-row">'
            f'<div class="sec-kv"><span class="rs-label">1M</span>{_ret_badge(r1m)}</div>'
            f'<div class="sec-kv"><span class="rs-label">3M</span>{_ret_badge(r3m)}</div>'
            f'<div class="sec-kv"><span class="rs-label">RS</span>{_rs_badge(rs3m)}</div>'
            f'<div class="sec-kv"><span class="rs-label">RSΔ</span>{rsd_arrow} {_rsd_badge(rsd)}</div>'
            f'<div class="sec-kv"><span class="rs-label">Vol</span>{_vol_badge(vr)}</div>'
            f'</div>'
            f'{chips_section}'
            f'</div>'
        )

    # ── Emerging trend cards ──────────────────────────────────────────────────
    early_cards = ""
    for d in early_trends:
        ind = d["industry"]; sec = d.get("sector","")
        p20=d.get("pct_20ma",0); p50=d.get("pct_50ma",0); p200=d.get("pct_200ma",0)
        rs3m=d.get("avg_rs3m"); rs1m=d.get("avg_rs1m")
        vs=d.get("vol_spike_pct",0); n52=d.get("new_52wh",0); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,_ = _stage_cfg(stage)
        ecls = "chip-em" if stage in ("EMERGING","EMERGING★") else "chip-bl"
        badge = "⚡ EMERGING★" if stage=="EMERGING★" else "⚡ EMERGING" if stage=="EMERGING" else "🟡 BUILDING"
        notes_html = "".join([
            f'<span class="note-vol">🔥 {vs}% vol</span>' if vs>=15 else "",
            f'<span class="note-hi">🏔 {n52} 52W hi</span>' if n52>0 else "",
        ])
        sl = d.get("stock_list", [])
        above_n = sum(1 for s in sl if s.get("above20"))
        chips_html = _inline_chips(sl[:16])
        safe = escape(ind.replace("'",""))
        early_cards += (
            f'<div class="early-card {ecls}" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="ec-top">'
            f'<div><div class="ec-name">{escape(ind)}</div><div class="ec-sec">{escape(sec)} · {n} stocks</div></div>'
            f'<span class="stage-pill" style="color:{sc};background:{sbg};border-color:{sb}">{badge}</span>'
            f'</div>'
            f'{_breadth_strip(p20,p50,p200)}'
            f'<div class="ec-rs">'
            f'<div><span class="rs-label">RS 3M</span>{_rs_badge(rs3m)}</div>'
            f'<div><span class="rs-label">RS 1M</span>{_rs_badge(rs1m)}</div>'
            f'{("<div class=\"ec-notes\">" + notes_html + "</div>") if notes_html else ""}'
            f'</div>'
            f'<div style="margin-top:6px;padding-top:5px;border-top:1px solid #1a2030">'
            f'<div style="font-size:.6em;color:#475569;margin-bottom:4px">'
            f'{above_n}▲ / {n - above_n}▼ 20MA</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:3px">{chips_html}</div>'
            f'</div>'
            f'</div>'
        )

    # ── Volume cluster cards ──────────────────────────────────────────────────
    vol_cards = ""
    for d in vol_clusters:
        ind=d["industry"]; sec=d.get("sector",""); vs=d.get("vol_spike_pct",0)
        p20=d.get("pct_20ma",0); rs3m=d.get("avg_rs3m"); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,se = _stage_cfg(stage)
        clr  = "#f85149" if vs>=60 else "#e3b341" if vs>=35 else "#7dd3fc"
        icon = "🔥🔥🔥" if vs>=70 else "🔥🔥" if vs>=40 else "🔥"
        bw   = round(vs/100*100)
        safe = escape(ind.replace("'",""))
        sl   = d.get("stock_list", [])
        # Show vol-spiking stocks first
        vol_sl = sorted(sl, key=lambda s: -(s.get("vol_ratio") or 0))
        chips_html = _inline_chips(vol_sl[:12], show_ret=True)
        vol_cards += (
            f'<div class="vol-card" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="vc-top"><span class="vc-icon">{icon}</span>{_stage_pill(stage)}</div>'
            f'<div class="vc-name">{escape(ind)}</div>'
            f'<div class="vc-sec">{escape(sec)} · {n} stocks</div>'
            f'<div class="vc-track"><div class="vc-fill" style="width:{bw}%;background:{clr}"></div></div>'
            f'<div class="vc-val" style="color:{clr}">{vs}% stocks with vol spike</div>'
            f'<div class="vc-foot"><span class="pct-na">{p20}% &gt;20MA</span>{_rs_badge(rs3m)}</div>'
            f'<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:3px">{chips_html}</div>'
            f'</div>'
        )
    if not vol_cards:
        vol_cards = '<div class="empty-state">No volume clusters detected (threshold: ≥15% of industry stocks with vol &gt;1.5× avg, last 5 sessions).</div>'

    # ── 52W High cards ────────────────────────────────────────────────────────
    hi52_cards = ""
    for d in hi52_leaders:
        ind=d["industry"]; sec=d.get("sector",""); n52=d.get("new_52wh",0)
        p52=d.get("pct_52wh",0); rs3m=d.get("avg_rs3m"); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,se = _stage_cfg(stage)
        bw52 = round(p52/100*100)
        safe  = escape(ind.replace("'",""))
        sl    = d.get("stock_list", [])
        # Show stocks near 52W high first
        hi_sl = sorted(sl, key=lambda s: (not s.get("new52",False), not s.get("near52",False)))
        chips_html = _inline_chips(hi_sl[:12], show_ret=True)
        hi52_cards += (
            f'<div class="hi52-card" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="hc-badge">🏔 {n52} new highs <span class="hc-span">(last 5d)</span></div>'
            f'<div class="hc-name">{escape(ind)}</div>'
            f'<div class="hc-sec">{escape(sec)} · {n} stocks</div>'
            f'<div class="hc-track"><div class="hc-fill" style="width:{bw52}%"></div></div>'
            f'<div class="hc-pct">{p52}% near 52W high</div>'
            f'<div class="hc-foot">{_stage_pill(stage)}{_rs_badge(rs3m)}</div>'
            f'<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:3px">{chips_html}</div>'
            f'</div>'
        )
    if not hi52_cards:
        hi52_cards = '<div class="empty-state">No new 52-week highs in the last 5 sessions.</div>'

    # ── Industry table rows ───────────────────────────────────────────────────
    ind_rows = ""
    for d in sorted(industry_data, key=lambda x: -x.get("trend_score", 0)):
        ind=d["industry"]; sec=d.get("sector","")
        p20=d.get("pct_20ma"); p50=d.get("pct_50ma"); p200=d.get("pct_200ma")
        p52=d.get("pct_52wh"); rs3m=d.get("avg_rs3m"); rs1m=d.get("avg_rs1m")
        rsd=d.get("avg_rs_delta"); vr=d.get("avg_vol_rank")
        r1m=d.get("ind_ret_1m"); r3m=d.get("ind_ret_3m")
        n52=d.get("new_52wh",0); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,se = _stage_cfg(stage)
        ts=d.get("trend_score",0)
        n52_clr = "#3fb950" if n52>=3 else "#e3b341" if n52>=1 else "#475569"
        ind_escaped = escape(ind)
        uid = ind.replace(" ","_").replace("/","_").replace("&","and")

        # Build inline stock chips for this industry row
        sl = d.get("stock_list", [])
        chips_html = ""
        for s in sl:
            tk = escape(s["ticker"])
            ab = s.get("above20", False)
            nr = s.get("near52", False)
            nw = s.get("new52", False)
            rs = s.get("rs3m")
            r3 = s.get("r3m")
            rs_txt = f" RS:{rs:+.0f}%" if rs is not None else ""
            r3_txt = f" {r3:+.0f}%" if r3 is not None else ""
            chip_color = "#3fb950" if ab else "#f85149"
            chip_bg    = "#071a0c" if ab else "#1a0707"
            star = "🏔" if nw else ("⭐" if nr else "")
            chips_html += (
                f'<span class="ind-chip" '
                f'title="{tk}: 3M {r3_txt.strip() or "N/A"} | RS {rs_txt.strip() or "N/A"}" '
                f'style="color:{chip_color};background:{chip_bg};border:1px solid {chip_color}44">'
                f'{star}{tk}{r3_txt}</span>'
            )
        above_n = sum(1 for s in sl if s.get("above20"))
        below_n = len(sl) - above_n

        ind_rows += (
            f'<tr class="ind-row" data-industry="{ind_escaped}" '
            f'data-stage="{stage}" data-sector="{escape(sec)}" data-score="{ts}" '
            f'style="border-left:3px solid {sc}33" onclick="toggleIndStocks(\'{uid}\')">'
            f'<td class="ind-name" title="{ind_escaped}">▶ {ind_escaped}</td>'
            f'<td><span class="sec-badge">{escape(sec)}</span></td>'
            f'<td>{_stage_pill(stage)}</td>'
            f'<td class="pct-cell">{_pct_bar(p20, 44)}</td>'
            f'<td class="pct-cell">{_pct_bar(p50, 44)}</td>'
            f'<td class="pct-cell">{_pct_bar(p200, 44)}</td>'
            f'<td class="pct-cell">{_ret_badge(r1m)}</td>'
            f'<td class="pct-cell">{_ret_badge(r3m)}</td>'
            f'<td class="pct-cell">{_rs_badge(rs3m)}</td>'
            f'<td class="pct-cell">{_rsd_badge(rsd)}</td>'
            f'<td class="pct-cell">{_vol_badge(vr)}</td>'
            f'<td class="pct-cell" style="color:{n52_clr};font-weight:{"700" if n52>0 else "400"}">'
            f'{"🏔" if n52>0 else "—"}{n52 if n52>0 else ""}</td>'
            f'<td class="pct-cell">{_trend_ring(ts)}</td>'
            f'<td class="pct-cell pct-na">{n}</td>'
            f'</tr>'
            # ── Expandable stock chips row ─────────────────────────────────────
            f'<tr class="ind-stocks-row" id="istocks-{uid}" style="display:none">'
            f'<td colspan="14" style="padding:6px 10px 10px;background:#0a0f16;border-bottom:1px solid #21262d">'
            f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px">'
            f'<span style="font-size:.72em;font-weight:700;color:#8b949e">{n} stocks</span>'
            f'<span style="display:flex;align-items:center;gap:3px;font-size:.68em">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:#3fb950;display:inline-block"></span>'
            f'<span style="color:#3fb950">{above_n} above 20MA</span>'
            f'&nbsp;<span style="width:7px;height:7px;border-radius:50%;background:#f85149;display:inline-block"></span>'
            f'<span style="color:#f85149">{below_n} below</span>'
            f'</span>'
            f'</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:4px">'
            f'{chips_html if chips_html else "<span style=color:#475569;font-size:.75em>No data</span>"}'
            f'</div>'
            f'</td>'
            f'</tr>'
        )

    all_sectors = sorted({d.get("sector","") for d in industry_data if d.get("sector")})
    sec_opts = "\n".join(f'<option value="{s}">{escape(s)}</option>' for s in all_sectors)

    row_json = json.dumps([
        {"industry": d["industry"], "sector": d.get("sector",""), "stage": d["stage"],
         "pct_20ma": d.get("pct_20ma",0), "pct_50ma": d.get("pct_50ma",0),
         "pct_200ma": d.get("pct_200ma",0), "pct_52wh": d.get("pct_52wh",0),
         "avg_rs3m": d.get("avg_rs3m") or -999, "avg_rs1m": d.get("avg_rs1m") or -999,
         "avg_rs_delta": d.get("avg_rs_delta") or -999,
         "avg_vol_rank": d.get("avg_vol_rank") or 0,
         "ind_ret_1m": d.get("ind_ret_1m") or -999,
         "ind_ret_3m": d.get("ind_ret_3m") or -999,
         "ind_ret_6m": d.get("ind_ret_6m") or -999,
         "vol_spike_pct": d.get("vol_spike_pct",0), "new_52wh": d.get("new_52wh",0),
         "breadth_score": d.get("breadth_score",0),
         "trend_score": d.get("trend_score",0),
         "total": d.get("total",0),
         "stocks": d.get("stock_list", [])}   # ← include per-stock data in JS payload
        for d in industry_data
    ])

    drilldown_json = json.dumps({
        k: [{"ticker": s["ticker"], "above20": s.get("above20", False),
             "last": s.get("last"), "r1m": s.get("r1m"), "r3m": s.get("r3m"),
             "rs3m": s.get("rs3m"), "no_data": s.get("no_data", False)}
            for s in v]
        for k, v in drilldown_data.items()
    })

    css = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d1117;--bg2:#161b22;--bg3:#0a0f16;--border:#21262d;--border2:#30363d;
  --text:#c9d1d9;--muted:#8b949e;--dim:#475569;--blue:#58a6ff;--green:#3fb950;
  --yellow:#e3b341;--red:#f85149;--accent:#79c0ff}
html{scroll-behavior:smooth}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.45}

.topbar{background:linear-gradient(135deg,#0d1117,#111827);border-bottom:1px solid var(--border);
  padding:12px 24px;display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;backdrop-filter:blur(12px)}
.topbar-title{color:var(--accent);font-size:1.1em;font-weight:800;letter-spacing:-.3px}
.topbar-sub{color:var(--muted);font-size:.72em;margin-top:2px}
.stat-pills{display:flex;gap:6px;flex-wrap:wrap}
.sp{display:flex;flex-direction:column;align-items:center;background:var(--bg3);
  border:1px solid var(--border);border-radius:8px;padding:5px 12px;min-width:54px}
.sp-v{font-size:1.15em;font-weight:800}
.sp-l{font-size:.58em;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:1px}

.nav-bar{background:var(--bg2);border-bottom:1px solid var(--border);padding:7px 24px;
  display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.nav-link{padding:3px 11px;border:1px solid var(--border2);border-radius:99px;color:var(--muted);
  font-size:.75em;cursor:pointer;transition:all .15s;text-decoration:none}
.nav-link:hover{border-color:var(--blue);color:var(--blue)}
.nav-ext{color:var(--accent);border-color:#79c0ff33}
.nav-ext:hover{background:#79c0ff11}

.ctrl-bar{background:#0f1621;border-bottom:1px solid var(--border);padding:7px 24px;
  display:flex;gap:7px;align-items:center;flex-wrap:wrap;position:sticky;top:61px;z-index:90}
.ci{padding:5px 9px;background:var(--bg);border:1px solid var(--border2);border-radius:6px;
  color:var(--text);font-size:.78em;outline:none;transition:border .15s}
.ci:focus{border-color:var(--blue)}
.ci.wide{min-width:190px}
.cb{padding:4px 11px;border:1px solid var(--border2);border-radius:6px;background:transparent;
  color:var(--accent);cursor:pointer;font-size:.75em;transition:all .15s;white-space:nowrap}
.cb:hover{background:#1f6feb;border-color:var(--blue);color:#fff}
.cb.reset{color:var(--red);border-color:#f8514933}
.cb.reset:hover{background:#1a0a0a;border-color:var(--red)}
#rowCount{color:var(--muted);font-size:.73em}

.section{padding:18px 24px;border-bottom:1px solid var(--border)}
.sec-hdr{margin-bottom:14px}
.sec-hdr h2{font-size:.92em;font-weight:700;color:var(--accent);margin-bottom:4px}
.sec-hdr p{font-size:.74em;color:var(--muted);line-height:1.6;max-width:900px}

.stage-pill{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;
  border-radius:99px;font-size:.68em;font-weight:700;border:1px solid transparent;white-space:nowrap}
.cycle-badge{display:inline-flex;padding:2px 8px;border-radius:99px;font-size:.68em;font-weight:700;
  white-space:nowrap;border:1px solid transparent}
.cycle-early{background:#0a2a14;color:#4ade80;border-color:#16a34a33}
.cycle-mid{background:#0f1f3a;color:#60a5fa;border-color:#1d4ed833}
.cycle-late{background:#2a2200;color:#e3b341;border-color:#92400e33}
.cycle-def{background:#1a1a2e;color:#a5b4fc;border-color:#4c1d9533}

.rs-strong{font-weight:700;color:#4ade80;font-size:.8em}
.rs-pos{font-weight:600;color:#3fb950;font-size:.8em}
.rs-neg{font-weight:600;color:#f87171;font-size:.8em}
.rs-weak{font-weight:700;color:#f85149;font-size:.8em}
.rs-na{color:var(--dim);font-size:.8em}
.rs-label{color:var(--muted);font-size:.64em;text-transform:uppercase;letter-spacing:.3px;margin-right:4px}

.sec-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.sec-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:14px 15px;transition:box-shadow .2s,transform .2s}
.sec-card:hover{box-shadow:0 6px 20px rgba(0,0,0,.4);transform:translateY(-2px)}
.sec-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:6px}
.sec-name{font-size:1em;font-weight:800;color:var(--text)}
.sec-meta{margin-bottom:10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.sec-n{color:var(--dim);font-size:.68em}
.ibar-group{display:flex;flex-direction:column;gap:5px;margin-bottom:10px}
.ibar{display:flex;align-items:center;gap:5px}
.ibar-lbl{font-size:.6em;color:var(--dim);width:34px;flex-shrink:0;font-weight:600;text-transform:uppercase}
.ibar-track{flex:1;height:5px;background:#1a2030;border-radius:3px;overflow:hidden}
.ibar-fill{height:100%;border-radius:3px;transition:width .4s}
.ibar-val{font-size:.68em;font-weight:700;width:28px;text-align:right;flex-shrink:0}
.sec-rs{display:flex;gap:10px;flex-wrap:wrap}

.early-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.early-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:13px 15px;cursor:pointer;transition:all .2s}
.chip-em{border-color:#3fb95033}
.chip-em:hover{border-color:var(--green);background:#050f07;box-shadow:0 4px 16px rgba(63,185,80,.13)}
.chip-bl{border-color:#e3b34133}
.chip-bl:hover{border-color:var(--yellow);background:#0c0b00;box-shadow:0 4px 16px rgba(227,179,65,.13)}
.ec-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;gap:6px}
.ec-name{font-size:.88em;font-weight:700;color:var(--text);margin-bottom:2px}
.ec-sec{font-size:.68em;color:var(--muted)}
.ec-rs{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap;align-items:center}
.ec-notes{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}

.breadth-strip{display:flex;flex-direction:column;gap:4px;margin:4px 0 6px}
.strip-row{display:flex;align-items:center;gap:5px}
.strip-lbl{font-size:.58em;color:var(--dim);width:32px;flex-shrink:0;font-weight:600;text-transform:uppercase}
.strip-track{flex:1;height:4px;background:#1a2030;border-radius:2px;overflow:hidden}
.strip-fill{height:100%;border-radius:2px;transition:width .4s}
.strip-val{font-size:.67em;font-weight:700;width:28px;text-align:right;flex-shrink:0}

.note-vol{display:inline-flex;padding:1px 6px;border-radius:4px;font-size:.63em;font-weight:600;
  background:#1a1200;color:#e3b341;border:1px solid #e3b34133}
.note-hi{display:inline-flex;padding:1px 6px;border-radius:4px;font-size:.63em;font-weight:600;
  background:#0a1a08;color:#4ade80;border:1px solid #3fb95033}

.vol-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:10px}
.vol-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:12px 13px;cursor:pointer;transition:all .2s}
.vol-card:hover{border-color:var(--yellow);background:#0b0900;box-shadow:0 4px 14px rgba(227,179,65,.12)}
.vc-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.vc-icon{font-size:1.05em}
.vc-name{font-size:.84em;font-weight:700;color:var(--text);margin-bottom:2px}
.vc-sec{font-size:.68em;color:var(--muted);margin-bottom:8px}
.vc-track{height:5px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:4px}
.vc-fill{height:100%;border-radius:3px;transition:width .4s}
.vc-val{font-size:.71em;font-weight:700;margin-bottom:7px}
.vc-foot{display:flex;gap:8px;align-items:center}

.hi52-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:10px}
.hi52-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:12px 13px;cursor:pointer;transition:all .2s}
.hi52-card:hover{border-color:var(--green);background:#050f07;box-shadow:0 4px 14px rgba(63,185,80,.12)}
.hc-badge{font-size:.8em;font-weight:700;color:#4ade80;margin-bottom:7px}
.hc-span{font-size:.82em;color:var(--muted);font-weight:400}
.hc-name{font-size:.84em;font-weight:700;color:var(--text);margin-bottom:2px}
.hc-sec{font-size:.68em;color:var(--muted);margin-bottom:8px}
.hc-track{height:5px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:4px}
.hc-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#3fb950,#4ade80)}
.hc-pct{font-size:.68em;color:var(--muted);margin-bottom:7px}
.hc-foot{display:flex;gap:8px;align-items:center}

.tbl-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
.tbl{width:100%;border-collapse:collapse;font-size:.78em}
.tbl thead{position:sticky;top:0;z-index:10}
.tbl th{background:#080d13;border-bottom:2px solid var(--border);padding:8px 10px;
  color:var(--muted);text-transform:uppercase;letter-spacing:.4px;font-size:.65em;
  white-space:nowrap;cursor:pointer;user-select:none;transition:color .15s}
.tbl th:hover{color:var(--blue)}
.tbl th[data-col].thsort-asc::after{content:" ↑";color:var(--blue)}
.tbl th[data-col].thsort-desc::after{content:" ↓";color:var(--blue)}
.tbl th[data-col]:not(.thsort-asc):not(.thsort-desc)::after{content:" ↕";color:var(--dim)}
.tbl td{padding:7px 10px;border-bottom:1px solid #0f1520;white-space:nowrap}
.tbl tbody tr:hover td{background:#0b1018}
.tbl tbody tr:last-child td{border-bottom:none}
.ind-row.hidden{display:none}
.ind-stocks-row.hidden{display:none}
.ind-row{cursor:pointer}
.ind-row:hover .ind-name{color:#58a6ff}
.ind-chip{display:inline-flex;align-items:center;padding:2px 6px;border-radius:4px;
  font-size:.72em;font-weight:600;cursor:default;font-family:monospace;
  white-space:nowrap;transition:transform .12s}
.ind-chip:hover{transform:scale(1.08);z-index:1;position:relative}
.ind-name{font-weight:600;color:var(--text);max-width:185px;overflow:hidden;text-overflow:ellipsis}
.sec-badge{background:#141a24;color:var(--muted);padding:1px 6px;border-radius:4px;font-size:.7em;white-space:nowrap}
.pct-cell{white-space:nowrap}
.pct-na{color:var(--dim);font-size:.78em}

.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:.72em;color:var(--muted);margin-bottom:12px}
.leg{display:flex;align-items:center;gap:5px}
.leg-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
.empty-state{color:var(--dim);font-size:.8em;padding:14px 16px;background:var(--bg2);
  border-radius:8px;border:1px solid var(--border)}
.footer{padding:14px 24px;color:var(--dim);font-size:.7em;border-top:1px solid var(--border);
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}

/* CUSTOM THEME CARDS */
.nav-leaders{color:#38bdf8!important;border-color:#38bdf844!important;font-weight:700}
.nav-leaders:hover{background:#38bdf811!important}
.sec-kv-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.sec-kv{display:flex;align-items:center;gap:3px;font-size:.7em}
.ldr-tbl{font-size:.77em}
.ldr-tbl th{background:#080d13;border-bottom:2px solid var(--border);padding:7px 9px;
  color:var(--muted);text-transform:uppercase;letter-spacing:.35px;font-size:.62em;
  white-space:nowrap;cursor:pointer;user-select:none;transition:color .15s}
.ldr-tbl th:hover{color:var(--blue)}
.ldr-row{cursor:pointer;transition:background .1s}
.ldr-row:hover td{background:#0d1520}
.opp-row{cursor:pointer;transition:background .1s}
.opp-row:hover td{background:#0a1a0d}
.ldr-name{font-weight:600;color:var(--text);max-width:175px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stage-pill[style*="22d3ee"]{animation:pulse-cyan 2s infinite}
@keyframes pulse-cyan{0%,100%{box-shadow:none}50%{box-shadow:0 0 8px #22d3ee66}}

/* MARKET REGIME BANNER */
.regime-banner{display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:14px 24px;border-bottom:1px solid var(--border);border-left:4px solid transparent;
  flex-wrap:wrap}
.regime-left{display:flex;align-items:center;gap:14px;flex-shrink:0}
.regime-info{display:flex;flex-direction:column;gap:3px}
.regime-label{font-size:1.1em;font-weight:900;letter-spacing:-.3px}
.regime-desc{font-size:.73em;color:var(--muted);max-width:400px;line-height:1.45}
.regime-action{font-size:.7em;font-style:italic;margin-top:2px}
.regime-stats{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.rst{display:flex;flex-direction:column;align-items:center;background:var(--bg3);
  border:1px solid var(--border);border-radius:7px;padding:4px 10px;min-width:56px}
.rst-v{font-size:1.0em;font-weight:800;line-height:1.2}
.rst-l{font-size:.56em;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-top:1px}

/* BREADTH PULSE BAR */
.pulse-bar{display:flex;gap:0;border-bottom:1px solid var(--border);background:#080d13;overflow-x:auto}
.pulse-item{display:flex;flex-direction:column;gap:2px;padding:9px 18px;border-right:1px solid var(--border);
  min-width:185px;flex-shrink:0}
.pulse-lbl{font-size:.58em;color:var(--dim);text-transform:uppercase;letter-spacing:.4px;font-weight:700}
.pulse-val{font-size:.9em;font-weight:800;line-height:1.2}
.pulse-sub{font-size:.63em;color:var(--muted)}

/* TRAJECTORY CARDS */
.traj-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.traj-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:11px 13px;cursor:pointer;transition:all .2s}
.traj-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.3);transform:translateY(-1px)}
.traj-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:5px}
.traj-name{font-size:.85em;font-weight:700;color:var(--text);margin-bottom:2px}
.traj-sec{font-size:.65em;color:var(--muted)}
.traj-badge{font-size:.68em;font-weight:800;white-space:nowrap}
.traj-stats{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:5px}
.traj-insight{font-size:.63em;color:var(--dim);line-height:1.5;font-style:italic}

/* SMART MONEY CARDS */
.sm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.sm-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:11px 13px;cursor:pointer;transition:all .2s}
.sm-card:hover{border-color:#22d3ee44;background:#050f12;box-shadow:0 4px 14px rgba(34,211,238,.1)}
.sm-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.sm-name{font-size:.85em;font-weight:700;color:var(--text)}
.sm-score{font-size:.88em;font-weight:900}
.sm-sec{font-size:.63em;color:var(--muted);margin-bottom:7px}
.sm-track{height:5px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:6px}
.sm-fill{height:100%;border-radius:3px;transition:width .5s}
.sm-sig{font-size:.68em;color:var(--text);margin-bottom:6px;font-weight:600}
.sm-stats{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

/* DIVERGENCE CARDS */
.div-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.div-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:11px 13px;cursor:pointer;transition:all .2s}
.div-card:hover{box-shadow:0 4px 14px rgba(0,0,0,.3)}
.div-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;gap:5px}
.div-name{font-size:.84em;font-weight:700;color:var(--text);margin-bottom:2px}
.div-sec{font-size:.63em;color:var(--muted)}
.div-badge{font-size:.63em;font-weight:800;padding:2px 7px;border-radius:4px;border:1px solid;white-space:nowrap}
.div-sig{font-size:.71em;font-weight:700;color:var(--text);margin-bottom:3px}
.div-why{font-size:.64em;color:var(--muted);line-height:1.5;margin-bottom:7px;font-style:italic}
.div-stats{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

/* SECTOR ROTATION */
.rot-phase{margin-bottom:18px}
.rot-phase-hdr{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.rot-phase-desc{font-size:.71em;color:var(--muted)}
.rot-phase-cards{display:flex;flex-wrap:wrap;gap:8px}
.rot-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
  padding:10px 12px;min-width:155px;max-width:185px}
.rot-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:3px;gap:4px}
.rot-name{font-size:.82em;font-weight:800;color:var(--text)}
.rot-score{font-size:1.1em;font-weight:900;margin:4px 0 6px}

.tc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}
.tc-card{background:var(--bg2);border:1px solid var(--border);border-radius:14px;
  padding:16px 18px;transition:box-shadow .2s,transform .15s}
.tc-card:hover{box-shadow:0 6px 24px rgba(0,0,0,.4);transform:translateY(-2px)}
.tc-hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;gap:6px}
.tc-title{font-size:.95em;font-weight:800;color:var(--text);display:flex;align-items:center;gap:6px}
.tc-emoji{font-size:1.1em}
.tc-hdr-right{display:flex;align-items:center;gap:8px;flex-shrink:0}
.tc-tracked{font-size:.64em;color:var(--dim);background:var(--bg3);padding:2px 7px;
  border-radius:4px;border:1px solid var(--border)}
.tc-desc{font-size:.71em;color:var(--muted);line-height:1.55;margin-bottom:12px}
.tc-perf-row{display:flex;gap:6px;margin-bottom:12px;overflow-x:auto;padding-bottom:2px}
.tc-period{flex:1;min-width:58px;display:flex;flex-direction:column;gap:2px;
  background:#0a0f16;border-radius:8px;padding:7px 8px;border:1px solid var(--border)}
.tc-per-lbl{font-size:.58em;font-weight:700;color:var(--dim);text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:1px}
.tc-per-val{font-size:.9em;font-weight:800;line-height:1}
.tc-per-na{font-size:.75em;color:var(--dim)}
.tc-bar-wrap{height:3px;background:#21262d;border-radius:2px;overflow:hidden;margin:3px 0}
.tc-bar{height:100%;border-radius:2px;min-width:2px;transition:width .5s}
.tc-nifty{font-size:.59em;color:var(--dim)}
.tc-alpha{font-size:.66em;font-weight:700;margin-top:1px}
.tc-body{display:flex;gap:12px;margin:8px 0}
.tc-perf-col{flex:1;min-width:0}
.tc-col-title{font-size:.64em;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.4px;margin-bottom:5px;border-bottom:1px solid var(--border);padding-bottom:3px}
.tc-stock-row{display:flex;justify-content:space-between;align-items:center;
  padding:2px 0;border-bottom:1px solid #0f1520}
.tc-stock-row:last-child{border-bottom:none}
.tc-stock-sym{font-size:.74em;font-weight:700;color:var(--text)}
.tc-stock-ret{font-size:.72em;font-weight:700}
.tc-na{font-size:.72em;color:var(--dim);padding:4px 0}
.tc-footer{display:flex;align-items:center;gap:8px;margin-top:10px;
  padding-top:8px;border-top:1px solid var(--border);flex-wrap:wrap}
.tc-tag{font-size:.63em;font-weight:700;padding:2px 7px;border-radius:4px}
.tc-tag-vol{background:#1a1200;color:#e3b341;border:1px solid #e3b34133}
.tc-tag-hi{background:#0a1a08;color:#4ade80;border:1px solid #3fb95033}
.tc-drillbtn{margin-left:auto;padding:3px 10px;border:1px solid var(--border2);
  border-radius:5px;background:transparent;color:var(--accent);cursor:pointer;
  font-size:.7em;transition:all .12s}
.tc-drillbtn:hover{background:#1f6feb22;border-color:var(--blue)}
.tc-stocks-wrap{margin:10px 0 6px;padding:9px 11px;background:#0a0f16;
  border-radius:9px;border:1px solid var(--border)}
.tc-stocks-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.tc-stocks-title{font-size:.62em;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.tc-stocks-legend{display:flex;align-items:center;gap:4px;font-size:.62em;color:var(--muted)}
.tc-leg-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0}
.tc-chips{display:flex;flex-wrap:wrap;gap:5px}
.tc-chip{display:inline-flex;align-items:center;padding:2px 7px;border-radius:4px;
  font-size:.66em;font-weight:700;white-space:nowrap;cursor:default;
  transition:transform .1s,box-shadow .1s}
.tc-chip:hover{transform:scale(1.07);box-shadow:0 2px 8px rgba(0,0,0,.3)}

/* THEME DRILL-DOWN MODAL */
.tm-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:1000;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px)}
.tm-overlay.open{display:flex}
.tm-box{background:#161b22;border:1px solid #30363d;border-radius:16px;
  max-width:820px;width:100%;max-height:88vh;overflow:hidden;
  display:flex;flex-direction:column;box-shadow:0 24px 72px rgba(0,0,0,.7)}
.tm-modal-hdr{display:flex;justify-content:space-between;align-items:center;
  padding:14px 20px;border-bottom:1px solid var(--border);flex-shrink:0;gap:10px}
.tm-modal-title{font-size:.97em;font-weight:700;color:var(--accent);flex:1}
.tm-modal-actions{display:flex;gap:6px;align-items:center}
.tm-copy-btn{padding:4px 10px;border:1px solid #30363d44;border-radius:5px;background:#0a1a0a;
  color:#4ade80;cursor:pointer;font-size:.72em;font-weight:600;transition:all .12s}
.tm-copy-btn:hover{background:#0f2f0f;border-color:#3fb95088}
.tm-close{background:transparent;border:1px solid var(--border2);border-radius:5px;
  color:var(--muted);cursor:pointer;padding:4px 10px;font-size:.85em;transition:all .12s}
.tm-close:hover{border-color:var(--red);color:var(--red)}
.tm-toolbar{padding:9px 20px;border-bottom:1px solid var(--border);flex-shrink:0;
  display:flex;gap:6px;align-items:center;background:#0d1117;flex-wrap:wrap}
.tm-sort-btn{padding:3px 10px;border:1px solid var(--border2);border-radius:5px;
  background:transparent;color:var(--muted);cursor:pointer;font-size:.7em;transition:all .12s}
.tm-sort-btn:hover,.tm-sort-btn.active{background:#1f6feb22;border-color:var(--blue);color:var(--blue)}
.tm-stats{font-size:.68em;color:var(--muted);margin-left:auto;display:flex;gap:10px}
.tm-stat-grn{color:#4ade80;font-weight:700}
.tm-stat-red{color:#f85149;font-weight:700}
.tm-body{overflow-y:auto;padding:14px 20px;flex:1}
.tm-stock-tbl{width:100%;border-collapse:collapse;font-size:.8em}
.tm-stock-tbl th{color:var(--muted);font-size:.65em;text-transform:uppercase;letter-spacing:.4px;
  padding:6px 8px;border-bottom:2px solid var(--border);text-align:right;white-space:nowrap;
  cursor:pointer;user-select:none;transition:color .12s}
.tm-stock-tbl th:hover{color:var(--blue)}
.tm-stock-tbl th:first-child{text-align:left}
.tm-stock-tbl th.ts-asc::after{content:" ↑";color:var(--blue)}
.tm-stock-tbl th.ts-desc::after{content:" ↓";color:var(--blue)}
.tm-stock-tbl td{padding:6px 8px;border-bottom:1px solid #0f1520;text-align:right;white-space:nowrap}
.tm-stock-tbl td:first-child{text-align:left;font-weight:700;font-size:.85em;color:var(--text)}
.tm-stock-tbl tr:last-child td{border-bottom:none}
.tm-stock-tbl tr.tm-row-above td{background:#060f07}
.tm-stock-tbl tr.tm-row-above:hover td{background:#0a1a0c}
.tm-stock-tbl tr.tm-row-below:hover td{background:#140a0a}
.tm-stock-tbl tr.tm-row-nodata td{background:#0f0f0f;opacity:.55}
.tm-stock-tbl tr.tm-row-nodata:hover td{background:#141414;opacity:.75}
.tm-20ma-yes{color:#4ade80;font-weight:700;font-size:.8em}
.tm-20ma-no{color:#f85149;font-size:.8em}
.tm-price{color:#c9d1d9;font-size:.8em}

@media(max-width:680px){
  .sec-grid{grid-template-columns:1fr 1fr}
  .early-grid,.vol-grid,.hi52-grid,.tc-grid{grid-template-columns:1fr}
  .stat-pills{gap:4px}.sp{padding:4px 8px;min-width:48px}
}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Breadth — NSE India | {NOW}</title>
<style>{css}</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">📊 Market Breadth &amp; Trend Detection — NSE India</div>
    <div class="topbar-sub">{NOW} &bull; All cached price data · no signal filter</div>
  </div>
  <div class="stat-pills">
    <div class="sp"><div class="sp-v">{total_stocks}</div><div class="sp-l">Stocks</div></div>
    <div class="sp"><div class="sp-v">{total_ind}</div><div class="sp-l">Industries</div></div>
    <div class="sp" style="border-color:#3fb95044"><div class="sp-v" style="color:#3fb950">{ec}</div><div class="sp-l">🟢 Emerging</div></div>
    <div class="sp" style="border-color:#e3b34144"><div class="sp-v" style="color:#e3b341">{bc}</div><div class="sp-l">🟡 Building</div></div>
    <div class="sp" style="border-color:#f8514944"><div class="sp-v" style="color:#f85149">{xc}</div><div class="sp-l">🔴 Extended</div></div>
    <div class="sp"><div class="sp-v" style="color:#475569">{wc}</div><div class="sp-l">⚫ Weak</div></div>
  </div>
</div>

{regime_banner_html}
{pulse_html}

<div class="nav-bar">
  <a class="nav-link" href="#opportunities">🎯 Setups</a>
  <a class="nav-link nav-theme" href="#themes">📦 Themes ({theme_section_count})</a>
  <a class="nav-link nav-leaders" href="#leaders">🚀 Leaders</a>
  <a class="nav-link" href="#trajectories">🚀 Trajectories</a>
  <a class="nav-link" href="#smartmoney">💰 Smart Money</a>
  <a class="nav-link" href="#divergences">⚠️ Divergences</a>
  <a class="nav-link" href="#rotation">🔄 Rotation</a>
  <a class="nav-link" href="#trends">⚡ Emerging</a>
  <a class="nav-link" href="#volume">🔥 Vol</a>
  <a class="nav-link" href="#highs">🏔 52W</a>
  <a class="nav-link" href="#fullmap">📋 Full Map</a>
  <a class="nav-link nav-ext" href="trade_plans_live.html">↩ Trade Plans</a>
</div>

<div class="ctrl-bar">
  <input class="ci wide" id="indSearch" placeholder="🔍 Filter industry or sector…" oninput="applyFilter()">
  <select class="ci" id="stageFilter" onchange="applyFilter()">
    <option value="">All Stages</option>
    <option value="EMERGING★">⭐ Emerging★ — RS + Vol accelerating</option>
    <option value="EMERGING">🟢 Emerging (25–62%)</option>
    <option value="BUILDING">🟡 Building (62–80%)</option>
    <option value="SURGING">🔥 Surging (&gt;80% + RS rising)</option>
    <option value="EXTENDED">🔴 Extended (&gt;80%)</option>
    <option value="WEAK">⚫ Weak (&lt;25%)</option>
  </select>
  <select class="ci" id="sectorFilter" onchange="applyFilter()">
    <option value="">All Sectors</option>
    {sec_opts}
  </select>
  <button class="cb" onclick="sortTable('trend_score')">🎯 Trend</button>
  <button class="cb" onclick="sortTable('avg_rs_delta')">RSΔ</button>
  <button class="cb" onclick="sortTable('pct_20ma')">&gt;EMA20</button>
  <button class="cb" onclick="sortTable('avg_rs3m')">RS 3M</button>
  <button class="cb" onclick="sortTable('ind_ret_3m')">3M Ret</button>
  <button class="cb" onclick="sortTable('avg_vol_rank')">Vol</button>
  <button class="cb" onclick="sortTable('new_52wh')">52W↑</button>
  <button class="cb reset" onclick="resetFilter()">↺ Reset</button>
  <span id="rowCount"></span>
</div>

<!-- ── Custom Theme Monitor ──────────────────────────────────────────────── -->
<div class="section" id="themes">
  <div class="sec-hdr">
    <h2>🎯 Custom Theme Monitor</h2>
    <p>Thematic baskets with multi-period performance vs Nifty.
    <b>1W/1M/3M/6M/1Y</b> returns for each basket — <b>α = alpha over Nifty</b>.
    Breadth strip shows % stocks above 20/50/200 MA.
    Click <b>🔍 All stocks</b> to see each stock's status in the theme.
    <span style="color:#475569;font-size:.9em">· Edit <code>CUSTOM_THEMES</code> in <code>generate_breadth_dashboard.py</code> to add your own baskets.</span></p>
  </div>
  {"<div class='tc-grid'>" + theme_cards_html + "</div>" if theme_cards_html
   else '<div class="empty-state">No themes defined. Add them to CUSTOM_THEMES in generate_breadth_dashboard.py</div>'}
</div>

<!-- ── Theme Drill-down Modal ────────────────────────────────────────────── -->
<div id="themeModal" class="tm-overlay" onclick="if(event.target===this)closeModal()">
  <div class="tm-box">
    <div class="tm-modal-hdr">
      <span id="tmTitle" class="tm-modal-title"></span>
      <div class="tm-modal-actions">
        <button class="tm-copy-btn" id="tmCopyBtn" onclick="copyModalTickers()">📋 Copy Tickers</button>
        <button class="tm-close" onclick="closeModal()">✕ Close</button>
      </div>
    </div>
    <div class="tm-toolbar" id="tmToolbar">
      <span style="font-size:.68em;color:var(--muted);font-weight:600">Sort by:</span>
      <button class="tm-sort-btn active" onclick="sortModalBy('r3m')">3M Return</button>
      <button class="tm-sort-btn" onclick="sortModalBy('r1m')">1M Return</button>
      <button class="tm-sort-btn" onclick="sortModalBy('rs3m')">RS 3M</button>
      <button class="tm-sort-btn" onclick="sortModalBy('last')">Price</button>
      <button class="tm-sort-btn" onclick="sortModalBy('ticker')">Ticker A-Z</button>
      <button class="tm-sort-btn" onclick="sortModalBy('above20')">Above 20MA first</button>
      <div class="tm-stats"><span id="tmAboveCnt"></span><span id="tmBelowCnt"></span></div>
    </div>
    <div id="tmBody" class="tm-body"></div>
  </div>
</div>

<!-- ── Best Opportunities Screener ─────────────────────────────────────── -->
<div class="section" id="opportunities">
  <div class="sec-hdr">
    <h2>🎯 Best Opportunity Setups — Pre-Extended Industries</h2>
    <p>Industries in EMERGING or BUILDING stage with <b>positive RS + improving RS delta + volume expanding</b>.
    These represent the best risk/reward entries: smart money is accumulating, retail hasn't noticed yet.
    <b>Opportunity Score</b> combines stage quality, RS level, RS momentum, volume and new 52W highs. Click to filter Full Map.</p>
  </div>
  {"<div class='tbl-wrap'><table class='tbl ldr-tbl'><thead><tr><th>Industry</th><th>Sector</th><th>Stage</th><th>&gt;EMA20</th><th>RS 3M</th><th>RSΔ</th><th>Vol</th><th>3M Ret</th><th>Opp Score</th><th>N</th></tr></thead><tbody>" + opp_rows + "</tbody></table></div>"
   if opp_rows else '<div class="empty-state">No high-conviction setups in current regime. Market may be extended or weak — wait for pullback.</div>'}
</div>

<!-- ── Momentum Trajectories ────────────────────────────────────────────── -->
<div class="section" id="trajectories">
  <div class="sec-hdr">
    <h2>🚀 Momentum Trajectories — Accelerating vs Decelerating</h2>
    <p>Track which industries are <b>gaining RS momentum</b> (buy zone) vs <b>losing momentum</b> (reduce/exit).
    <b>Accelerating</b> = RS delta &gt; +3.5% AND volume &gt; 1.2x — institutional buying confirmed.
    <b>Collapsing</b> = RS delta &lt; -3.5% AND volume shrinking — distribution in progress.</p>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:14px">
    <div>
      <div style="color:#22d3ee;font-weight:800;font-size:.82em;margin-bottom:8px;display:flex;align-items:center;gap:6px">
        🚀 ACCELERATING <span style="color:var(--dim);font-weight:400;font-size:.85em">RS + Vol surging — strongest buy signal</span></div>
      {"<div class='traj-grid'>" + acc_cards + "</div>" if acc_cards else '<div class="empty-state">No accelerating industries detected.</div>'}
    </div>
    <div>
      <div style="color:#3fb950;font-weight:800;font-size:.82em;margin-bottom:8px;display:flex;align-items:center;gap:6px">
        📈 IMPROVING <span style="color:var(--dim);font-weight:400;font-size:.85em">RS momentum building — good entry zone</span></div>
      {"<div class='traj-grid'>" + imp_cards + "</div>" if imp_cards else '<div class="empty-state">No improving industries.</div>'}
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
    <div>
      <div style="color:#f87171;font-weight:800;font-size:.82em;margin-bottom:8px;display:flex;align-items:center;gap:6px">
        📉 DECELERATING <span style="color:var(--dim);font-weight:400;font-size:.85em">RS fading — tighten stops</span></div>
      {"<div class='traj-grid'>" + dec_cards + "</div>" if dec_cards else '<div class="empty-state">No decelerating industries detected.</div>'}
    </div>
    <div>
      <div style="color:#f85149;font-weight:800;font-size:.82em;margin-bottom:8px;display:flex;align-items:center;gap:6px">
        💥 COLLAPSING <span style="color:var(--dim);font-weight:400;font-size:.85em">RS + Vol both falling — exit/avoid</span></div>
      {"<div class='traj-grid'>" + col_cards + "</div>" if col_cards else '<div class="empty-state">No collapsing industries detected.</div>'}
    </div>
  </div>
</div>

<!-- ── Smart Money Footprint ─────────────────────────────────────────────── -->
<div class="section" id="smartmoney">
  <div class="sec-hdr">
    <h2>💰 Smart Money Footprint — Institutional Accumulation Radar</h2>
    <p>Industries showing signs of <b>institutional accumulation</b>: heavy volume expansion + new 52W highs appearing + RS improving —
    while still in pre-extended stage (EMERGING / BUILDING).
    <b>Institutional Score</b> = vol expansion (30pts) + new high ratio (25pts) + vol spike % (25pts) + RS delta (20pts).
    "Smart money in, retail not yet" = highest reward/risk window.</p>
  </div>
  {"<div class='sm-grid'>" + sm_cards + "</div>"
   if sm_cards else '<div class="empty-state">No high institutional score industries — may indicate late-cycle or no clear accumulation patterns.</div>'}
</div>

<!-- ── Divergence Alerts ──────────────────────────────────────────────────── -->
<div class="section" id="divergences">
  <div class="sec-hdr">
    <h2>⚠️ Price–Breadth Divergence Alerts</h2>
    <p><b>🔵 Bullish Divergence</b>: Stage is WEAK/EMERGING but RS + volume are improving —
    smart money accumulating quietly before the breakout. Best early entry opportunity.<br>
    <b>🔴 Bearish Divergence</b>: Stage looks BUILDING/EXTENDED but RS + volume are deteriorating —
    distribution in progress. Reduce positions before the obvious breakdown.</p>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
    <div>
      <div style="color:#22d3ee;font-weight:800;font-size:.82em;margin-bottom:10px">🔵 BULLISH — Early Entry Opportunities</div>
      {"<div class='div-grid'>" + bull_div_html + "</div>"
       if bull_div_html else '<div class="empty-state">No bullish divergences detected. Market may be in sync — breadth matches price.</div>'}
    </div>
    <div>
      <div style="color:#f85149;font-weight:800;font-size:.82em;margin-bottom:10px">🔴 BEARISH — Risk Warnings</div>
      {"<div class='div-grid'>" + bear_div_html + "</div>"
       if bear_div_html else '<div class="empty-state">No bearish divergences. No obvious distribution signals.</div>'}
    </div>
  </div>
</div>

<!-- ── Sector Rotation Matrix ────────────────────────────────────────────── -->
<div class="section" id="rotation">
  <div class="sec-hdr">
    <h2>🔄 Sector Rotation Matrix — Cycle Phase Momentum</h2>
    <p>Sectors mapped to their typical economic cycle phase. <b>Rotation Score</b> = RS delta × 5 + short-term RS acceleration + volume × 20 + stage bonus.
    <b>ROTATING IN</b> (score &gt; +20) = buy the sector. <b>ROTATING OUT</b> (score &lt; -20) = reduce/avoid.
    Watch <b>Early Cycle</b> sectors for first signs of bull market — Financials + Consumer lead every recovery.</p>
  </div>
  {rotation_html}
</div>

<div class="section" id="leaders">
  <div class="sec-hdr">
    <h2>🚀 Trend Leaders — Top 20 by Composite Score</h2>
    <p>Industries ranked by <b>Trend Score</b> = EMA breadth (28%) + RS vs Nifty (25%) + <b>RS Δ momentum (22%)</b> + Volume expansion (13%) + 3M return (12%).
    <b>RS Δ</b> = how much the relative strength has improved vs 4 weeks ago — the earliest leading indicator.
    <b>⭐ EMERGING★</b> = RS improving <i>and</i> volume expanding — highest conviction early-stage signal.
    Click any row to filter the Full Map below.</p>
  </div>
  <div class="tbl-wrap">
    <table class="tbl ldr-tbl">
      <thead><tr>
        <th>Industry</th><th>Sector</th><th>Stage</th>
        <th title="% price above EMA20">&gt;EMA20</th>
        <th title="Avg 1M return of stocks in group">1M Ret</th>
        <th title="Avg 3M return">3M Ret</th>
        <th title="Avg RS vs Nifty 3M">RS 3M</th>
        <th title="RS change vs 4 weeks ago — early trend signal">RS Δ ↑↓</th>
        <th title="Current 20D avg vol / 3M hist avg — >1 = expanding">Vol</th>
        <th title="Composite trend score 0-100">Score</th>
        <th>N</th>
      </tr></thead>
      <tbody>{leaders_rows}</tbody>
    </table>
  </div>
</div>

<div class="section" id="rs-rising">
  <div class="sec-hdr">
    <h2>📈 RS Momentum — Gaining Relative Strength (Early Signal)</h2>
    <p>Industries where RS vs Nifty is <b>actively improving</b> (RS Δ &gt; +0.5% vs 4 weeks ago).
    This is what would have caught the <b>PSU Banks rally in early 2025</b> — RS started rising weeks
    before the breakout was obvious on price charts.
    Green RS Δ with volume expansion = institutional accumulation in progress.</p>
  </div>
  <div class="tbl-wrap">
    <table class="tbl ldr-tbl">
      <thead><tr>
        <th>Industry</th><th>Sector</th><th>Stage</th>
        <th title="RS change vs 4 weeks ago">RS Δ (4W)</th>
        <th title="Current RS vs Nifty 3M">RS 3M</th>
        <th title="Avg 3M return">3M Ret</th>
        <th title="Volume expansion ratio">Vol Rank</th>
      </tr></thead>
      <tbody>{"<tr><td colspan=7 class='pct-na' style='padding:12px'>No industries with rising RS detected — try after a fresh scan.</td></tr>" if not rs_rising_rows else rs_rising_rows}</tbody>
    </table>
  </div>
</div>

<div class="section" id="sector-scorecard">
  <div class="sec-hdr">
    <h2>📊 Sector Scorecard — Ranked by Trend Score</h2>
    <p>Sectors ranked by composite Trend Score. Each card shows EMA breadth, returns, RS, RSΔ and volume expansion.
    <b>RSΔ ▲ with Vol &gt;1.2x</b> = smart money moving in before price shows it.
    <b>Early Cycle</b> leads at bottoms · <b>Mid Cycle</b> peak growth ·
    <b>Late Cycle</b> commodity · <b>Defensive</b> recession shelter.</p>
  </div>
  <div class="sec-grid">{sec_cards}</div>
</div>

<div class="section" id="trends">
  <div class="sec-hdr">
    <h2>⚡ Emerging &amp; Building Trends</h2>
    <p>Industries in <b style="color:#3fb950">EMERGING</b> (25–65% &gt;20MA) or
    <b style="color:#e3b341">BUILDING</b> (65–80%) stage, ranked by RS vs Nifty.
    Breadth strip = 20MA→50MA→200MA participation depth.
    Best entry = EMERGING + positive RS + 🔥 vol spike.</p>
  </div>
  {"<div class='early-grid'>" + early_cards + "</div>" if early_cards
   else '<div class="empty-state">No emerging/building industries with ≥2 tracked stocks right now.</div>'}
</div>

<div class="section" id="volume">
  <div class="sec-hdr">
    <h2>🔥 Volume Cluster Radar</h2>
    <p>Industries where ≥15% of stocks had a volume spike (&gt;1.5× 20-day avg) in the last 5 sessions.
    Simultaneous spikes = probable <b>institutional accumulation</b>.</p>
  </div>
  <div class="vol-grid">{vol_cards}</div>
</div>

<div class="section" id="highs">
  <div class="sec-hdr">
    <h2>🏔 52-Week High Momentum Leaders</h2>
    <p>Industries with the most new 52-week highs in the last 5 sessions.
    Multiple stocks at new highs together = <b>strongest breadth leadership signal</b>.</p>
  </div>
  <div class="hi52-grid">{hi52_cards}</div>
</div>

<div class="section" id="fullmap">
  <div class="sec-hdr">
    <h2>📋 Full Industry Breadth Map</h2>
    <p>All {total_ind} tracked industries, sorted by Trend Score by default. Click headers to re-sort.
    <b>EMA breadth</b> uses Exponential MA (more responsive than SMA).
    <b>RS Δ</b> = 4-week RS momentum — most reliable early trend indicator.
    <b>Vol</b> = current 20D avg / 3M avg (>1.2x = volume expanding). ⭐ = RS rising + Vol expanding.</p>
  </div>
  <div class="legend">
    <div class="leg"><div class="leg-dot" style="background:#22d3ee"></div>⭐ EMERGING★ — RS rising + Vol expanding (strongest early signal)</div>
    <div class="leg"><div class="leg-dot" style="background:#3fb950"></div>EMERGING 25–62% &gt;EMA20</div>
    <div class="leg"><div class="leg-dot" style="background:#e3b341"></div>BUILDING 62–80%</div>
    <div class="leg"><div class="leg-dot" style="background:#f85149"></div>EXTENDED/SURGING &gt;80%</div>
    <div class="leg"><div class="leg-dot" style="background:#334155"></div>WEAK &lt;25%</div>
  </div>
  <div class="tbl-wrap">
    <table class="tbl" id="indTable">
      <thead><tr>
        <th data-col="industry"  onclick="sortTable('industry')">Industry</th>
        <th data-col="sector"    onclick="sortTable('sector')">Sector</th>
        <th>Stage</th>
        <th data-col="pct_20ma"  onclick="sortTable('pct_20ma')"  title="% above EMA20">&gt;EMA20</th>
        <th data-col="pct_50ma"  onclick="sortTable('pct_50ma')"  title="% above EMA50">&gt;EMA50</th>
        <th data-col="pct_200ma" onclick="sortTable('pct_200ma')" title="% above EMA200">&gt;EMA200</th>
        <th data-col="ind_ret_1m" onclick="sortTable('ind_ret_1m')" title="Avg 1M return">1M</th>
        <th data-col="ind_ret_3m" onclick="sortTable('ind_ret_3m')" title="Avg 3M return">3M</th>
        <th data-col="avg_rs3m"  onclick="sortTable('avg_rs3m')"  title="RS vs Nifty 3M">RS 3M</th>
        <th data-col="avg_rs_delta" onclick="sortTable('avg_rs_delta')" title="RS change vs 4W ago — early signal">RS Δ</th>
        <th data-col="avg_vol_rank" onclick="sortTable('avg_vol_rank')" title="Vol expansion ratio">Vol</th>
        <th data-col="new_52wh"  onclick="sortTable('new_52wh')"  title="New 52W highs last 5d">52W↑</th>
        <th data-col="trend_score" onclick="sortTable('trend_score')" title="Composite trend score">Score</th>
        <th data-col="total"     onclick="sortTable('total')">N</th>
      </tr></thead>
      <tbody id="indTbody">{ind_rows}</tbody>
    </table>
  </div>
</div>

<div class="footer">
  <span>📊 Market Breadth Dashboard — NSE India &bull; {NOW}</span>
  <span>Locally cached OHLCV data · No live API · Rerun after scan to refresh</span>
</div>

<script>
const rowData={row_json};
const drilldownData={drilldown_json};
let sortCol='trend_score',sortDir=-1,curFilter='',curStage='',curSector='';
function applyFilter(){{curFilter=document.getElementById('indSearch').value.toLowerCase();curStage=document.getElementById('stageFilter').value;curSector=document.getElementById('sectorFilter').value;renderTable();}}
function filterIndustry(ind){{document.getElementById('indSearch').value=ind;curFilter=ind.toLowerCase();curStage='';curSector='';document.getElementById('stageFilter').value='';document.getElementById('sectorFilter').value='';renderTable();document.getElementById('fullmap').scrollIntoView({{behavior:'smooth'}});}}
function resetFilter(){{document.getElementById('indSearch').value='';document.getElementById('stageFilter').value='';document.getElementById('sectorFilter').value='';curFilter='';curStage='';curSector='';renderTable();}}
function toggleIndStocks(uid){{
  const row=document.getElementById('istocks-'+uid);
  if(!row)return;
  const open=row.style.display==='none'||row.style.display==='';
  row.style.display=open?'table-row':'none';
  const trigger=row.previousElementSibling;
  if(trigger){{const nm=trigger.querySelector('.ind-name');if(nm)nm.textContent=nm.textContent.replace(/^[▶▼][ ]*/,open?'▼ ':'▶ ');}}
}}
function sortTable(col){{sortDir=(sortCol===col)?-sortDir:-1;sortCol=col;document.querySelectorAll('.tbl th[data-col]').forEach(th=>{{th.className=th.dataset.col===col?(sortDir===-1?'thsort-desc':'thsort-asc'):''}});renderTable();}}
function renderTable(){{
  const filtered=rowData.filter(d=>{{
    if(curFilter&&!d.industry.toLowerCase().includes(curFilter)&&!d.sector.toLowerCase().includes(curFilter))return false;
    if(curStage&&d.stage!==curStage)return false;
    if(curSector&&d.sector!==curSector)return false;
    return true;
  }});
  filtered.sort((a,b)=>{{const va=a[sortCol],vb=b[sortCol];if(typeof va==='string')return sortDir*va.localeCompare(vb);return sortDir*((vb??-999)-(va??-999));}});
  const ids=new Set(filtered.map(d=>d.industry));
  const tbody=document.getElementById('indTbody');
  // Toggle main rows and keep their stock-chip expansion rows paired
  tbody.querySelectorAll('.ind-row').forEach(tr=>{{
    const show=ids.has(tr.dataset.industry);
    tr.classList.toggle('hidden',!show);
    // Also hide the paired expansion row when its parent is hidden
    const next=tr.nextElementSibling;
    if(next&&next.classList.contains('ind-stocks-row')&&!show){{
      next.style.display='none';
    }}
  }});
  filtered.forEach(d=>{{const tr=tbody.querySelector('.ind-row[data-industry="'+d.industry.replace(/"/g,'&quot;')+'"]');if(tr)tbody.appendChild(tr);}});
  document.getElementById('rowCount').textContent=filtered.length+' industries shown';
}}

/* ── Theme drill-down modal ── */
let _modalStocks=[], _modalSortCol='r3m', _modalSortDir=-1, _modalName='';
function showThemeDrilldown(name){{
  const stocks=drilldownData[name];
  if(!stocks){{
    alert('No data available for: '+name);
    return;
  }}
  _modalName=name; _modalStocks=stocks; _modalSortCol='r3m'; _modalSortDir=-1;
  document.getElementById('tmTitle').textContent=name+' — '+stocks.length+' Stocks';
  const above=stocks.filter(s=>s.above20&&!s.no_data).length;
  const below=stocks.filter(s=>!s.above20&&!s.no_data).length;
  const noData=stocks.filter(s=>s.no_data).length;
  document.getElementById('tmAboveCnt').innerHTML='<span class="tm-stat-grn">✓ '+above+' above 20MA</span>';
  document.getElementById('tmBelowCnt').innerHTML='<span class="tm-stat-red">✗ '+below+' below</span>'
    +(noData?' <span style="color:#475569;font-size:.85em">· '+noData+' no cache data</span>':'');
  document.querySelectorAll('.tm-sort-btn').forEach(b=>b.classList.remove('active'));
  document.querySelector('.tm-sort-btn').classList.add('active');
  renderModalTable();
  document.getElementById('themeModal').classList.add('open');
}}
function renderModalTable(){{
  const fmt=v=>v==null?'—':(v>=0?'+':'')+v.toFixed(1)+'%';
  const clr=v=>v==null?'#475569':v>=0?'#3fb950':'#f85149';
  const fw=v=>v==null?'400':Math.abs(v)>=5?'800':'600';
  let sorted=[..._modalStocks].sort((a,b)=>{{
    if(_modalSortCol==='ticker') return _modalSortDir*a.ticker.localeCompare(b.ticker);
    if(_modalSortCol==='above20') return _modalSortDir*(Number(b.above20)-Number(a.above20));
    // No-data stocks always go to end
    if(a.no_data && !b.no_data) return 1;
    if(!a.no_data && b.no_data) return -1;
    const va=a[_modalSortCol]??-9999, vb=b[_modalSortCol]??-9999;
    return _modalSortDir*(vb-va);
  }});
  let html='<table class="tm-stock-tbl"><thead><tr>'
    +'<th onclick="clickModalSort(\'ticker\')" title="Sort by ticker">Ticker</th>'
    +'<th onclick="clickModalSort(\'last\')" title="Sort by price">Price ₹</th>'
    +'<th onclick="clickModalSort(\'above20\')" title="Sort by 20MA status">20MA</th>'
    +'<th onclick="clickModalSort(\'r1m\')" title="Sort by 1M return">1M Ret</th>'
    +'<th onclick="clickModalSort(\'r3m\')" title="Sort by 3M return">3M Ret</th>'
    +'<th onclick="clickModalSort(\'rs3m\')" title="Sort by RS vs Nifty">RS 3M</th>'
    +'</tr></thead><tbody>';
  if(!sorted.length){{
    html+='<tr><td colspan="6" style="text-align:center;color:#475569;padding:20px">No stock data available</td></tr>';
  }} else {{
    sorted.forEach(s=>{{
      const rowCls=s.no_data?'tm-row-nodata':(s.above20?'tm-row-above':'tm-row-below');
      const m20=s.no_data
        ?'<span style="color:#475569;font-size:.75em">No cache</span>'
        :(s.above20?'<span class="tm-20ma-yes">✓ Above</span>':'<span class="tm-20ma-no">✗ Below</span>');
      const priceStr=s.last!=null?'₹'+Number(s.last).toLocaleString('en-IN',{{maximumFractionDigits:1}}):
        (s.no_data?'<span style="color:#475569">—</span>':'-');
      html+=`<tr class="${{rowCls}}">`
        +`<td style="${{s.no_data?'color:#64748b':''}}">${{s.ticker}}</td>`
        +`<td class="tm-price">${{priceStr}}</td>`
        +`<td>${{m20}}</td>`
        +`<td style="color:${{clr(s.r1m)}};font-weight:${{fw(s.r1m)}}">${{fmt(s.r1m)}}</td>`
        +`<td style="color:${{clr(s.r3m)}};font-weight:${{fw(s.r3m)}}">${{fmt(s.r3m)}}</td>`
        +`<td style="color:${{clr(s.rs3m)}}">${{fmt(s.rs3m)}}</td></tr>`;
    }});
  }}
  html+='</tbody></table>';
  document.getElementById('tmBody').innerHTML=html;
  // Update th sort arrows
  document.querySelectorAll('.tm-stock-tbl th').forEach(th=>{{
    th.className=th.className.replace(/ts-asc|ts-desc/g,'').trim();
  }});
  const cols=['ticker','last','above20','r1m','r3m','rs3m'];
  const thIdx=cols.indexOf(_modalSortCol);
  if(thIdx>=0){{
    const ths=document.querySelectorAll('.tm-stock-tbl th');
    if(ths[thIdx]) ths[thIdx].classList.add(_modalSortDir===-1?'ts-desc':'ts-asc');
  }}
}}
function clickModalSort(col){{
  if(_modalSortCol===col) _modalSortDir=-_modalSortDir;
  else {{ _modalSortCol=col; _modalSortDir=-1; }}
  const sortLabels={{'r3m':'3M Return','r1m':'1M Return','rs3m':'RS 3M','last':'Price','ticker':'Ticker A-Z','above20':'Above 20MA first'}};
  document.querySelectorAll('.tm-sort-btn').forEach(b=>{{b.classList.toggle('active',b.textContent===sortLabels[col]);}});
  renderModalTable();
}}
function sortModalBy(col){{
  _modalSortCol=col; _modalSortDir=-1; renderModalTable();
  document.querySelectorAll('.tm-sort-btn').forEach(b=>b.classList.remove('active'));
  event.target.classList.add('active');
}}
function copyModalTickers(){{
  if(!_modalStocks.length)return;
  const t=_modalStocks.map(s=>s.ticker).join(',');
  navigator.clipboard.writeText(t)
    .then(()=>{{ const btn=document.getElementById('tmCopyBtn'); const orig=btn.textContent;
      btn.textContent='✅ Copied '+_modalStocks.length+' tickers!'; btn.style.color='#4ade80';
      setTimeout(()=>{{ btn.textContent=orig; btn.style.color=''; }},2000); }})
    .catch(()=>{{}});
}}
function closeModal(){{document.getElementById('themeModal').classList.remove('open');}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeModal();}});
document.addEventListener('DOMContentLoaded',()=>renderTable());
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Generating Market Breadth Dashboard v2…", flush=True)
    print(f"  INDUSTRY_MAP: {len(INDUSTRY_MAP)} · SECTOR_MAP: {len(SECTOR_MAP)}", flush=True)
    nifty_closes = _load_nifty()
    print(f"  Nifty: {len(nifty_closes)} sessions" if nifty_closes else "  ⚠ ^NSEI not found", flush=True)

    all_industries = sorted(set(INDUSTRY_MAP.values()))
    print(f"  Computing {len(all_industries)} industries…", flush=True)
    industry_data: list[dict] = []
    for ind in all_industries:
        m = compute_industry_metrics(ind, nifty_closes)
        if m and m.get("total", 0) >= 2:
            industry_data.append(m)
    industry_data.sort(key=lambda x: -x.get("breadth_score", 0))
    print(f"  {len(industry_data)} industries with ≥2 stocks", flush=True)

    all_sectors = sorted(set(d["sector"] for d in industry_data))
    sector_data = [s for s in (compute_sector_metrics(s, industry_data) for s in all_sectors) if s]

    # ── Advanced analytics (Phase 4 & 5) ─────────────────────────────────────
    print("  Computing advanced analytics…", flush=True)
    regime      = compute_market_regime(industry_data)
    pulse       = compute_breadth_pulse(industry_data)
    oscillator  = compute_breadth_oscillator(industry_data)
    divergences = detect_divergences(industry_data)
    trajectories= compute_trajectories(industry_data)
    sm_footprint= compute_smart_money_footprint(industry_data)
    rotation    = compute_rotation_signals(sector_data)
    mom_matrix  = compute_sector_momentum_matrix(sector_data)
    opps        = screen_best_opportunities(industry_data, regime_score=regime["regime_score"])

    print(f"  Regime: {regime['regime']} (score={regime['regime_score']})", flush=True)
    print(f"  Oscillator: {oscillator.get('signal','—')} ({oscillator.get('oscillator',0):+.1f})", flush=True)
    print(f"  Divergences: {len(divergences['bullish'])} bullish · {len(divergences['bearish'])} bearish", flush=True)
    print(f"  Trajectories: {len(trajectories['accelerating'])} accel · {len(trajectories['improving'])} improving", flush=True)
    print(f"  SM Footprint: {len(sm_footprint)} candidates", flush=True)
    print(f"  Opportunities: {len(opps)} setups", flush=True)

    # ── Custom themes ─────────────────────────────────────────────────────────
    print(f"  Computing {len(CUSTOM_THEMES)} custom themes…", flush=True)
    theme_data: list[dict] = []
    for tname, tcfg in CUSTOM_THEMES.items():
        tm = compute_theme_metrics(tname, tcfg, nifty_closes)
        if tm:
            theme_data.append(tm)
            r3 = tm["theme_rets"].get("3M")
            al = tm["alphas"].get("3M")
            parts = [f"3M: {r3:+.1f}%"] if r3 is not None else []
            if al is not None: parts.append(f"α {al:+.1f}%")
            print(f"     {tm['emoji']} {tname}: {tm['stocks_tracked']}/{tm['stocks_total']} tracked  "
                  f"{tm['stage']}  {' · '.join(parts)}", flush=True)

    html = build_html(
        industry_data, sector_data, theme_data,
        regime=regime, pulse=pulse, oscillator=oscillator,
        divergences=divergences, trajectories=trajectories,
        sm_footprint=sm_footprint, rotation=rotation,
        mom_matrix=mom_matrix, opportunities=opps,
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out  = OUTPUT / "market_breadth.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✅ {out}  ({out.stat().st_size/1024:.0f} KB)", flush=True)

    counts: dict[str, int] = {}
    for d in industry_data: counts[d["stage"]] = counts.get(d["stage"], 0) + 1
    for s, c in sorted(counts.items()): print(f"     {s}: {c}", flush=True)
    print(f"  🚀 Top accelerating: {', '.join(d['industry'] for d in trajectories['accelerating'][:5])}", flush=True)


if __name__ == "__main__":
    main()

