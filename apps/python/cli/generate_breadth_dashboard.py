#!/usr/bin/env python3
"""
generate_breadth_dashboard.py
─────────────────────────────
Standalone Market Breadth & Trend Detection Dashboard — NSE India

Scans ALL cached price data to answer:
  • Which industries have stocks breaking out early? (EMERGING stage)
  • Where are volume clusters forming? (institutional accumulation signal)
  • Which industries have the most new 52-week highs?
  • How does each sector's RS vs Nifty look? (rotation tracker)
  • What stage of the cycle is each sector in?

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

ROOT      = Path(__file__).resolve().parents[3]   # SETUPS/
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"

sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))
sys.path.insert(0, str(ROOT / "apps" / "python" / "cli"))

# ── Import the full classification maps ───────────────────────────────────────
# generate_trade_plans_page has the most complete hardcoded INDUSTRY_MAP/SECTOR_MAP
# nse_taxonomy.py then overlays the CSV overrides on top
try:
    from generate_trade_plans_page import INDUSTRY_MAP as _TP_IND, SECTOR_MAP as _TP_SEC, _f
except Exception:
    _TP_IND, _TP_SEC = {}, {}
    def _f(v, d=0.0):
        try:
            return float(str(v or "").strip().replace("%","").replace(",",""))
        except Exception:
            return d

# Merge: CSV (nse_taxonomy) wins over hardcoded
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
                if t and s:
                    _CSV_SEC[t] = s
                if t and i:
                    _CSV_IND[t] = i
    except Exception:
        pass

INDUSTRY_MAP: dict[str, str] = {**_TP_IND, **_CSV_IND}   # CSV overrides
SECTOR_MAP:   dict[str, str] = {**_TP_SEC, **_CSV_SEC}

# Derive sector for each industry (first stock wins)
_IND_TO_SEC: dict[str, str] = {}
for _t, _ind in INDUSTRY_MAP.items():
    if _ind not in _IND_TO_SEC:
        _IND_TO_SEC[_ind] = SECTOR_MAP.get(_t, "Other")

NOW = datetime.now().strftime("%Y-%m-%d %H:%M")


# ── Price-data helpers ────────────────────────────────────────────────────────

def _load_prices(ticker: str) -> list[dict]:
    """
    Load OHLCV rows for a ticker from the cache directory.
    Tries: {TICKER}.NS_*.csv then {TICKER}_*.csv, longest first.
    Returns rows sorted oldest→newest.
    """
    candidates = []
    for suffix in ["_900", "_728", "_504", "_252", "_60", "_30"]:
        for name in (f"{ticker}.NS{suffix}.csv", f"{ticker}{suffix}.csv"):
            p = CACHE_DIR / name
            if p.exists():
                candidates.append(p)
                break   # take longest suffix found for each naming pattern

    # Also try without .NS suffix variants
    for suffix in ["_900", "_728", "_504", "_252", "_60", "_30"]:
        p = CACHE_DIR / f"{ticker}{suffix}.csv"
        if p.exists() and p not in candidates:
            candidates.append(p)
            break

    if not candidates:
        return []

    # pick the file with the most rows = best history
    best: list[dict] = []
    for p in candidates[:3]:
        rows: list[dict] = []
        try:
            with open(p, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    c = _f(row.get("close"))
                    if c > 0:
                        rows.append({
                            "date":   row.get("date",""),
                            "open":   _f(row.get("open", c)),
                            "high":   _f(row.get("high", c)),
                            "low":    _f(row.get("low",  c)),
                            "close":  c,
                            "volume": _f(row.get("volume", 0)),
                        })
        except Exception:
            pass
        if len(rows) > len(best):
            best = rows
    return best


def _load_nifty() -> list[float]:
    """Load ^NSEI closing prices (longest available)."""
    for suffix in ["_900", "_728", "_504", "_252"]:
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


# ── Metric computation ────────────────────────────────────────────────────────

def _rs_vs_benchmark(stock_closes: list[float],
                     bench_closes: list[float],
                     periods: int = 63) -> float | None:
    """Return % outperformance of stock vs benchmark over `periods` trading days."""
    if len(stock_closes) <= periods or len(bench_closes) <= periods:
        return None
    s_ret = (stock_closes[-1] / stock_closes[-(periods + 1)] - 1.0) * 100.0
    b_ret = (bench_closes[-1] / bench_closes[-(periods + 1)] - 1.0) * 100.0
    return round(s_ret - b_ret, 1)


def _new_52w_highs_last_n(closes: list[float], n: int = 5) -> int:
    """Count sessions in the last `n` bars that set a new 52-week high."""
    if len(closes) < 252 + n:
        return 0
    count = 0
    for i in range(-n, 0):
        window = closes[max(0, i - 252): i]
        if window and closes[i] >= max(window):
            count += 1
    return count


def compute_industry_metrics(industry: str,
                              nifty_closes: list[float]) -> dict | None:
    """Compute comprehensive breadth metrics for one industry."""
    peers = [t for t, ind in INDUSTRY_MAP.items() if ind == industry]
    if not peers:
        return None

    a20 = a50 = a200 = at_52wh = vol_spike = new_52wh_total = total = 0
    rs3m_list: list[float] = []
    rs1m_list: list[float] = []

    for ticker in peers:
        rows = _load_prices(ticker)
        if len(rows) < 20:
            continue
        closes  = [r["close"]  for r in rows]
        volumes = [r["volume"] for r in rows]
        last    = closes[-1]
        total  += 1

        # MA breadth
        if last > sum(closes[-20:]) / 20:
            a20 += 1
        if len(closes) >= 50 and last > sum(closes[-50:]) / 50:
            a50 += 1
        if len(closes) >= 200 and last > sum(closes[-200:]) / 200:
            a200 += 1

        # 52W high proximity (within 5 %)
        hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        if last >= hi52 * 0.95:
            at_52wh += 1

        # New 52W highs in last 5 sessions
        new_52wh_total += _new_52w_highs_last_n(closes, n=5)

        # Volume spike — any of last 5 bars > 1.5× 20-day avg (excluding last 5)
        if len(volumes) >= 25:
            avg_vol = sum(volumes[-25:-5]) / 20
            if avg_vol > 0 and any(v > avg_vol * 1.5 for v in volumes[-5:]):
                vol_spike += 1

        # RS vs Nifty
        rs3m = _rs_vs_benchmark(closes, nifty_closes, 63)
        rs1m = _rs_vs_benchmark(closes, nifty_closes, 21)
        if rs3m is not None:
            rs3m_list.append(rs3m)
        if rs1m is not None:
            rs1m_list.append(rs1m)

    if total == 0:
        return None

    pct_20  = round(a20  / total * 100)
    pct_50  = round(a50  / total * 100)
    pct_200 = round(a200 / total * 100)
    pct_52w = round(at_52wh / total * 100)
    avg_rs3m = round(sum(rs3m_list) / len(rs3m_list), 1) if rs3m_list else None
    avg_rs1m = round(sum(rs1m_list) / len(rs1m_list), 1) if rs1m_list else None
    vol_spike_pct = round(vol_spike / total * 100)

    # Stage classification
    if pct_20 >= 80:
        stage, sc, se = "EXTENDED",  "#f85149", "🔴"
    elif pct_20 >= 65:
        stage, sc, se = "BUILDING",  "#e3b341", "🟡"
    elif pct_20 >= 25:
        stage, sc, se = "EMERGING",  "#3fb950", "🟢"
    else:
        stage, sc, se = "WEAK",      "#475569", "⚫"

    # Composite breadth score
    score = round(pct_20 * 0.3 + pct_50 * 0.4 + pct_200 * 0.3)

    # Momentum: is RS improving (1M RS vs 3M RS)?
    rs_momentum = "UP" if (avg_rs1m is not None and avg_rs3m is not None
                           and avg_rs1m > avg_rs3m) else "FLAT"

    return {
        "industry":       industry,
        "sector":         _IND_TO_SEC.get(industry, "Other"),
        "total":          total,
        "pct_20ma":       pct_20,
        "pct_50ma":       pct_50,
        "pct_200ma":      pct_200,
        "pct_52wh":       pct_52w,
        "new_52wh":       new_52wh_total,
        "vol_spike_pct":  vol_spike_pct,
        "avg_rs3m":       avg_rs3m,
        "avg_rs1m":       avg_rs1m,
        "rs_momentum":    rs_momentum,
        "stage":          stage,
        "stage_color":    sc,
        "stage_emoji":    se,
        "breadth_score":  score,
    }


def compute_sector_metrics(sector: str,
                            industry_data: list[dict]) -> dict:
    """Roll up industry metrics to sector level."""
    rows = [d for d in industry_data if d.get("sector") == sector]
    if not rows:
        return {}
    n = sum(r["total"] for r in rows)
    if n == 0:
        return {}

    # Weighted averages (weighted by stock count)
    def _wavg(key: str) -> float:
        vals = [(r[key], r["total"]) for r in rows if r.get(key) is not None]
        if not vals:
            return 0.0
        return round(sum(v * w for v, w in vals) / sum(w for _, w in vals), 1)

    p20  = _wavg("pct_20ma")
    p50  = _wavg("pct_50ma")
    p200 = _wavg("pct_200ma")
    rs3m = _wavg("avg_rs3m")
    rs1m = _wavg("avg_rs1m")

    if p20 >= 80:
        stage, sc, se = "EXTENDED",  "#f85149", "🔴"
    elif p20 >= 65:
        stage, sc, se = "BUILDING",  "#e3b341", "🟡"
    elif p20 >= 25:
        stage, sc, se = "EMERGING",  "#3fb950", "🟢"
    else:
        stage, sc, se = "WEAK",      "#475569", "⚫"

    # Cycle position heuristic
    EARLY_SECTORS  = {"Financials", "Consumer", "Internet", "RealEstate"}
    MID_SECTORS    = {"IT", "Cap Goods", "Electronics", "Cables", "Defense", "Metals"}
    LATE_SECTORS   = {"Energy", "Renewable", "Chemicals", "Infra"}
    DEF_SECTORS    = {"FMCG", "Pharma", "Banking", "Agri", "Sugar"}

    if sector in EARLY_SECTORS:
        cycle_phase = "Early Cycle"
    elif sector in MID_SECTORS:
        cycle_phase = "Mid Cycle"
    elif sector in LATE_SECTORS:
        cycle_phase = "Late Cycle"
    elif sector in DEF_SECTORS:
        cycle_phase = "Defensive"
    else:
        cycle_phase = "Other"

    return {
        "sector":       sector,
        "industry_cnt": len(rows),
        "stock_count":  n,
        "pct_20ma":     p20,
        "pct_50ma":     p50,
        "pct_200ma":    p200,
        "avg_rs3m":     rs3m,
        "avg_rs1m":     rs1m,
        "stage":        stage,
        "stage_color":  sc,
        "stage_emoji":  se,
        "cycle_phase":  cycle_phase,
    }


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _color_pct(pct: int | None, invert: bool = False) -> str:
    if pct is None:
        return "#475569"
    v = (100 - pct) if invert else pct
    if v >= 75:
        return "#f85149"
    if v >= 55:
        return "#e3b341"
    if v >= 30:
        return "#3fb950"
    return "#475569"


def _fmt_rs(v: float | None) -> str:
    if v is None:
        return '<span style="color:#475569">—</span>'
    color = "#3fb950" if v >= 0 else "#f85149"
    sign  = "+" if v >= 0 else ""
    return f'<span style="color:{color};font-weight:700">{sign}{v:.1f}%</span>'


def _pct_cell(v: int | None, stage_color: str = "#475569") -> str:
    if v is None:
        return '<td style="color:#475569;text-align:center">—</td>'
    return f'<td style="color:{stage_color};text-align:center;font-weight:700">{v}%</td>'


def _stage_badge(stage: str, color: str, emoji: str) -> str:
    bg = {"EXTENDED": "#2a1a1a", "BUILDING": "#2a2200",
          "EMERGING": "#0a2a14", "WEAK": "#1a1a1a"}.get(stage, "#1a1a1a")
    return (f'<span style="background:{bg};color:{color};border:1px solid {color}44;'
            f'padding:1px 7px;border-radius:99px;font-size:.72em;font-weight:700;'
            f'white-space:nowrap">{emoji} {stage}</span>')


def build_html(industry_data: list[dict], sector_data: list[dict]) -> str:
    now_str = NOW

    # ── Summary stats ──────────────────────────────────────────────────────────
    total_industries = len(industry_data)
    total_stocks     = sum(d["total"] for d in industry_data)
    emerging_cnt = sum(1 for d in industry_data if d["stage"] == "EMERGING")
    building_cnt = sum(1 for d in industry_data if d["stage"] == "BUILDING")
    extended_cnt = sum(1 for d in industry_data if d["stage"] == "EXTENDED")
    weak_cnt     = sum(1 for d in industry_data if d["stage"] == "WEAK")

    # Top volume-cluster industries (vol_spike_pct >= 20%)
    vol_clusters = sorted(
        [d for d in industry_data if d.get("vol_spike_pct", 0) >= 20],
        key=lambda x: -x.get("vol_spike_pct", 0)
    )[:12]

    # Top 52W-high momentum industries
    hi52_leaders = sorted(
        [d for d in industry_data if d.get("new_52wh", 0) > 0],
        key=lambda x: -x.get("new_52wh", 0)
    )[:12]

    # Emerging + building sorted by RS3M
    early_trends = sorted(
        [d for d in industry_data if d["stage"] in ("EMERGING", "BUILDING")],
        key=lambda x: -(x.get("avg_rs3m") or -99)
    )[:20]

    # ── Sector rotation table ──────────────────────────────────────────────────
    sector_rows_html = ""
    for sd in sorted(sector_data, key=lambda x: -(x.get("avg_rs3m") or -99)):
        sec   = sd["sector"]
        p20   = sd.get("pct_20ma")
        p50   = sd.get("pct_50ma")
        p200  = sd.get("pct_200ma")
        rs3m  = sd.get("avg_rs3m")
        rs1m  = sd.get("avg_rs1m")
        stage = sd["stage"]
        sc    = sd["stage_color"]
        se    = sd["stage_emoji"]
        n     = sd["stock_count"]
        cycle = sd.get("cycle_phase", "")
        cycle_cls_map = {
            "Early Cycle": "cycle-early",
            "Mid Cycle":   "cycle-mid",
            "Late Cycle":  "cycle-late",
            "Defensive":   "cycle-def",
        }
        cycle_cls = cycle_cls_map.get(cycle, "")
        rs_dir = "↑" if sd.get("avg_rs1m", 0) >= (sd.get("avg_rs3m") or 0) else "↓"
        rs_dir_color = "#3fb950" if rs_dir == "↑" else "#f85149"

        sector_rows_html += f"""<tr>
          <td style="font-weight:700;color:#c9d1d9">{escape(sec)}</td>
          <td><span class="{cycle_cls} cycle-badge">{cycle}</span></td>
          <td style="text-align:center;color:{sc};font-weight:700">{se} {stage}</td>
          <td style="text-align:center;color:{_color_pct(p20)}">{p20 if p20 is not None else '—'}%</td>
          <td style="text-align:center;color:{_color_pct(p50)}">{p50 if p50 is not None else '—'}%</td>
          <td style="text-align:center;color:{_color_pct(p200)}">{p200 if p200 is not None else '—'}%</td>
          <td style="text-align:center">{_fmt_rs(rs3m)}</td>
          <td style="text-align:center">{_fmt_rs(rs1m)} <span style="color:{rs_dir_color}">{rs_dir}</span></td>
          <td style="text-align:center;color:#8b949e">{n}</td>
        </tr>"""

    # ── Full industry table ────────────────────────────────────────────────────
    ind_rows_html = ""
    for d in industry_data:
        ind    = d["industry"]
        sec    = d.get("sector", "")
        p20    = d.get("pct_20ma")
        p50    = d.get("pct_50ma")
        p200   = d.get("pct_200ma")
        p52    = d.get("pct_52wh")
        rs3m   = d.get("avg_rs3m")
        rs1m   = d.get("avg_rs1m")
        vs     = d.get("vol_spike_pct", 0)
        n52    = d.get("new_52wh", 0)
        n      = d.get("total", 0)
        stage  = d["stage"]
        sc     = d["stage_color"]
        se     = d["stage_emoji"]
        score  = d.get("breadth_score", 0)

        vs_color  = "#f85149" if vs >= 40 else "#e3b341" if vs >= 20 else "#475569"
        n52_color = "#3fb950" if n52 >= 3 else "#e3b341" if n52 >= 1 else "#475569"

        ind_rows_html += f"""<tr class="ind-row" data-stage="{stage}" data-sector="{escape(sec)}" data-score="{score}">
          <td style="font-weight:600;color:#c9d1d9;white-space:nowrap">{escape(ind)}</td>
          <td style="color:#8b949e;font-size:.78em">{escape(sec)}</td>
          <td>{_stage_badge(stage, sc, se)}</td>
          <td style="text-align:center;color:{_color_pct(p20)};font-weight:700">{p20 if p20 is not None else '—'}%</td>
          <td style="text-align:center;color:{_color_pct(p50)}">{p50 if p50 is not None else '—'}%</td>
          <td style="text-align:center;color:{_color_pct(p200)}">{p200 if p200 is not None else '—'}%</td>
          <td style="text-align:center;color:#7dd3fc">{p52 if p52 is not None else '—'}%</td>
          <td style="text-align:center">{_fmt_rs(rs3m)}</td>
          <td style="text-align:center">{_fmt_rs(rs1m)}</td>
          <td style="text-align:center;color:{vs_color};font-weight:{'700' if vs >= 20 else '400'}">{vs}%</td>
          <td style="text-align:center;color:{n52_color};font-weight:{'700' if n52 >= 1 else '400'}">{n52}</td>
          <td style="text-align:center;color:#e3b341;font-weight:700">{score}</td>
          <td style="text-align:center;color:#8b949e">{n}</td>
        </tr>"""

    # ── Volume cluster chips ───────────────────────────────────────────────────
    vol_chips_html = ""
    for d in vol_clusters:
        ind   = d["industry"]
        sec   = d.get("sector", "")
        vs    = d.get("vol_spike_pct", 0)
        p20   = d.get("pct_20ma", 0)
        stage = d["stage"]
        sc    = d["stage_color"]
        se    = d["stage_emoji"]
        intensity = "🔥🔥" if vs >= 60 else "🔥"
        vol_chips_html += f"""
          <div class="cluster-chip" onclick="filterIndustry('{escape(ind.replace("'",""))}')"
               title="{escape(ind)} — {vs}% of stocks had vol spike in last 5 days | >20MA: {p20}%">
            <div class="cluster-name">{escape(ind)}</div>
            <div class="cluster-sec">{escape(sec)}</div>
            <div class="cluster-vol">{intensity} {vs}% vol spikes</div>
            <div class="cluster-stage" style="color:{sc}">{se} {stage}</div>
          </div>"""

    # ── 52W High leaders chips ────────────────────────────────────────────────
    hi52_chips_html = ""
    for d in hi52_leaders:
        ind  = d["industry"]
        sec  = d.get("sector", "")
        n52  = d.get("new_52wh", 0)
        p52  = d.get("pct_52wh", 0)
        stage = d["stage"]
        sc    = d["stage_color"]
        se    = d["stage_emoji"]
        hi52_chips_html += f"""
          <div class="hi52-chip" onclick="filterIndustry('{escape(ind.replace("'",""))}')"
               title="{escape(ind)} — {n52} new 52W highs in last 5 sessions | {p52}% near 52W high">
            <div class="cluster-name">{escape(ind)}</div>
            <div class="cluster-sec">{escape(sec)}</div>
            <div class="cluster-vol">🏔 {n52} new 52W highs (5d)</div>
            <div class="cluster-stage" style="color:{sc}">{se} {stage} | {p52}% near hi</div>
          </div>"""

    # ── Early trend chips ─────────────────────────────────────────────────────
    early_chips_html = ""
    for d in early_trends:
        ind   = d["industry"]
        sec   = d.get("sector", "")
        p20   = d.get("pct_20ma", 0)
        rs3m  = d.get("avg_rs3m")
        n     = d.get("total", 0)
        stage = d["stage"]
        sc    = d["stage_color"]
        se    = d["stage_emoji"]
        badge = "⚡ EMERGING" if stage == "EMERGING" else "🟡 BUILDING"
        badge_cls = "chip-emerging" if stage == "EMERGING" else "chip-building"
        rs_str = f"+{rs3m:.1f}%" if rs3m is not None and rs3m >= 0 else (f"{rs3m:.1f}%" if rs3m is not None else "—")
        early_chips_html += f"""
          <div class="trend-chip {badge_cls}" onclick="filterIndustry('{escape(ind.replace("'",""))}')"
               title="{escape(ind)} — {p20}% above 20MA | RS3M: {rs_str}">
            <span class="chip-badge">{badge}</span>
            <span class="chip-name">{escape(ind)}</span>
            <span class="chip-meta">{p20}% &gt;20MA · RS {rs_str}</span>
            <span class="chip-n">{n} stocks</span>
          </div>"""

    # ── Build the active industry dropdown ────────────────────────────────────
    all_sectors = sorted({d.get("sector","") for d in industry_data if d.get("sector")})
    sector_options = "\n".join(
        f'<option value="{s}">{escape(s)}</option>' for s in all_sectors
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Breadth Dashboard — NSE India | {now_str}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:0}}

/* TOPBAR */
.topbar{{background:linear-gradient(135deg,#0d1117,#1a2433);border-bottom:1px solid #21262d;padding:16px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.topbar-title{{color:#79c0ff;font-size:1.25em;font-weight:700}}
.topbar-sub{{color:#8b949e;font-size:.8em;margin-top:3px}}
.stats-row{{display:flex;gap:16px;flex-wrap:wrap}}
.stat-box{{text-align:center;min-width:60px}}
.stat-v{{font-size:1.3em;font-weight:700}}
.stat-l{{font-size:.68em;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}}

/* CONTROLS */
.ctrl-bar{{background:#161b22;border-bottom:1px solid #21262d;padding:10px 28px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:68px;z-index:40}}
.sel,.search-box{{padding:7px 11px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:.82em}}
.search-box{{min-width:180px}}
.btn{{padding:6px 13px;border:1px solid #30363d;border-radius:6px;background:transparent;color:#79c0ff;cursor:pointer;font-size:.8em;transition:all .15s}}
.btn:hover,.btn.active{{background:#1f6feb;border-color:#58a6ff;color:#fff}}
.btn-link{{color:#58a6ff;text-decoration:none;font-size:.82em;padding:6px 10px;border:1px solid #21262d;border-radius:6px;cursor:pointer}}
.btn-link:hover{{background:#1f6feb22;border-color:#58a6ff}}

/* SECTIONS */
.section{{padding:18px 28px;border-bottom:1px solid #21262d}}
.sec-title{{font-size:1em;font-weight:700;color:#79c0ff;margin-bottom:4px}}
.sec-sub{{font-size:.78em;color:#8b949e;margin-bottom:12px}}

/* STAGE BREADTH LEGEND */
.legend-row{{display:flex;gap:12px;flex-wrap:wrap;font-size:.78em;margin-bottom:12px}}
.leg{{display:flex;align-items:center;gap:6px;color:#8b949e}}
.leg-dot{{width:10px;height:10px;border-radius:2px}}

/* SECTOR ROTATION TABLE */
.tbl{{width:100%;border-collapse:collapse;font-size:.82em}}
.tbl th{{background:#0a0f16;border-bottom:2px solid #21262d;padding:7px 10px;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;font-size:.72em;white-space:nowrap;cursor:pointer;user-select:none}}
.tbl th:hover{{color:#58a6ff}}
.tbl td{{padding:6px 10px;border-bottom:1px solid #1a1f2a;white-space:nowrap}}
.tbl tr:hover td{{background:#0f141a}}

/* CYCLE BADGES */
.cycle-badge{{padding:2px 8px;border-radius:99px;font-size:.72em;font-weight:700;white-space:nowrap}}
.cycle-early{{background:#0a2a14;color:#4ade80;border:1px solid #16a34a44}}
.cycle-mid{{background:#0f1f3a;color:#60a5fa;border:1px solid #1d4ed844}}
.cycle-late{{background:#2a2200;color:#e3b341;border:1px solid #92400e44}}
.cycle-def{{background:#1a1a2e;color:#a5b4fc;border:1px solid #4c1d9544}}

/* CHIP GRIDS */
.chip-row{{display:flex;gap:10px;flex-wrap:wrap}}

.cluster-chip{{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:10px 14px;min-width:180px;cursor:pointer;transition:all .15s}}
.cluster-chip:hover{{border-color:#e3b341;background:#1a1500}}
.cluster-name{{font-weight:700;color:#c9d1d9;font-size:.85em;margin-bottom:2px}}
.cluster-sec{{color:#8b949e;font-size:.72em;margin-bottom:4px}}
.cluster-vol{{color:#e3b341;font-size:.78em;font-weight:600;margin-bottom:2px}}
.cluster-stage{{font-size:.72em;font-weight:600}}

.hi52-chip{{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:10px 14px;min-width:180px;cursor:pointer;transition:all .15s}}
.hi52-chip:hover{{border-color:#3fb950;background:#0a1a0a}}

.trend-chip{{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:10px 14px;cursor:pointer;transition:all .15s;display:flex;flex-direction:column;gap:3px;min-width:190px}}
.chip-emerging{{border-color:#3fb95044}}
.chip-emerging:hover{{border-color:#3fb950;background:#0a1a0a}}
.chip-building{{border-color:#e3b34144}}
.chip-building:hover{{border-color:#e3b341;background:#1a1500}}
.chip-badge{{font-size:.68em;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e}}
.chip-emerging .chip-badge{{color:#3fb950}}
.chip-building .chip-badge{{color:#e3b341}}
.chip-name{{font-weight:700;color:#c9d1d9;font-size:.85em}}
.chip-meta{{color:#8b949e;font-size:.72em}}
.chip-n{{color:#475569;font-size:.68em}}

/* FULL BREADTH TABLE */
.ind-tbl-wrap{{overflow-x:auto}}
.ind-row.hidden{{display:none}}
.sort-icon::after{{content:" ↕";color:#475569}}
.sort-asc::after{{content:" ↑";color:#58a6ff}}
.sort-desc::after{{content:" ↓";color:#58a6ff}}

/* NAV LINKS */
.nav-pills{{display:flex;gap:8px;flex-wrap:wrap;padding:12px 28px;background:#0d1117;border-bottom:1px solid #21262d}}
.nav-pill{{padding:5px 14px;border:1px solid #30363d;border-radius:99px;color:#8b949e;font-size:.8em;cursor:pointer;text-decoration:none;transition:all .15s}}
.nav-pill:hover{{border-color:#58a6ff;color:#58a6ff}}

/* FOOTER */
.footer{{padding:20px 28px;color:#475569;font-size:.75em;border-top:1px solid #21262d;margin-top:8px}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">📊 Market Breadth &amp; Trend Detection — NSE India</div>
    <div class="topbar-sub">Generated {now_str} &bull; Scans ALL cached price data, no signal filter</div>
  </div>
  <div class="stats-row">
    <div class="stat-box"><div class="stat-v">{total_stocks}</div><div class="stat-l">Stocks Tracked</div></div>
    <div class="stat-box"><div class="stat-v">{total_industries}</div><div class="stat-l">Industries</div></div>
    <div class="stat-box"><div class="stat-v" style="color:#3fb950">{emerging_cnt}</div><div class="stat-l">🟢 Emerging</div></div>
    <div class="stat-box"><div class="stat-v" style="color:#e3b341">{building_cnt}</div><div class="stat-l">🟡 Building</div></div>
    <div class="stat-box"><div class="stat-v" style="color:#f85149">{extended_cnt}</div><div class="stat-l">🔴 Extended</div></div>
    <div class="stat-box"><div class="stat-v" style="color:#475569">{weak_cnt}</div><div class="stat-l">⚫ Weak</div></div>
  </div>
</div>

<div class="nav-pills">
  <a class="nav-pill" href="#rotation">🔄 Sector Rotation</a>
  <a class="nav-pill" href="#trends">⚡ Emerging Trends</a>
  <a class="nav-pill" href="#volume">🔥 Volume Clusters</a>
  <a class="nav-pill" href="#highs">🏔 52W High Leaders</a>
  <a class="nav-pill" href="#fullmap">📋 Full Breadth Map</a>
  <a class="nav-pill btn-link" href="trade_plans_live.html">↩ Trade Plans</a>
</div>

<div class="ctrl-bar">
  <input class="search-box" id="indSearch" placeholder="🔍 Filter industry..." oninput="applyFilter()">
  <select class="sel" id="stageFilter" onchange="applyFilter()">
    <option value="">All Stages</option>
    <option value="EMERGING">🟢 Emerging</option>
    <option value="BUILDING">🟡 Building</option>
    <option value="EXTENDED">🔴 Extended</option>
    <option value="WEAK">⚫ Weak</option>
  </select>
  <select class="sel" id="sectorFilter" onchange="applyFilter()">
    <option value="">All Sectors</option>
    {sector_options}
  </select>
  <button class="btn" onclick="sortTable('score')">Sort: Score ↕</button>
  <button class="btn" onclick="sortTable('pct_20ma')">Sort: >20MA ↕</button>
  <button class="btn" onclick="sortTable('avg_rs3m')">Sort: RS3M ↕</button>
  <button class="btn" onclick="sortTable('new_52wh')">Sort: 52W Hi ↕</button>
  <button class="btn" onclick="sortTable('vol_spike_pct')">Sort: Vol Spike ↕</button>
  <button class="btn" onclick="resetFilter()" style="color:#f85149">↺ Reset</button>
  <span id="rowCount" style="color:#8b949e;font-size:.8em;margin-left:4px"></span>
</div>

<!-- ── SECTOR ROTATION ──────────────────────────────────────────────────────── -->
<div class="section" id="rotation">
  <div class="sec-title">🔄 Sector Rotation Tracker</div>
  <div class="sec-sub">
    Sectors sorted by 3-Month RS vs Nifty. RS momentum (1M vs 3M arrow) shows if strength is accelerating ↑ or fading ↓.
    <b>Early Cycle</b> sectors lead at market bottoms; <b>Late Cycle</b> sectors lag at peaks.
  </div>
  <div class="legend-row">
    <div class="leg"><span class="cycle-badge cycle-early">Early Cycle</span> Financials, Consumer — lead at market bottom</div>
    <div class="leg"><span class="cycle-badge cycle-mid">Mid Cycle</span> IT, Cap Goods, Defense — peak growth phase</div>
    <div class="leg"><span class="cycle-badge cycle-late">Late Cycle</span> Energy, Chemicals, Metals — commodity inflation</div>
    <div class="leg"><span class="cycle-badge cycle-def">Defensive</span> FMCG, Pharma, Banking — recession shelter</div>
  </div>
  <div style="overflow-x:auto">
    <table class="tbl">
      <thead><tr>
        <th>Sector</th>
        <th>Cycle Phase</th>
        <th>Breadth Stage</th>
        <th title=">20MA">%&gt;20MA</th>
        <th title=">50MA">%&gt;50MA</th>
        <th title=">200MA">%&gt;200MA</th>
        <th>RS 3M vs Nifty</th>
        <th>RS 1M (trend)</th>
        <th>Stocks</th>
      </tr></thead>
      <tbody>{sector_rows_html}</tbody>
    </table>
  </div>
</div>

<!-- ── EMERGING TRENDS ────────────────────────────────────────────────────── -->
<div class="section" id="trends">
  <div class="sec-title">⚡ Emerging &amp; Building Trends</div>
  <div class="sec-sub">
    Industries in the <b style="color:#3fb950">EMERGING</b> (25–65% above 20MA) or
    <b style="color:#e3b341">BUILDING</b> (65–80%) stage, sorted by RS vs Nifty.
    These are the best setup zones — not yet extended, with leadership vs the index.
  </div>
  {"<div class='chip-row'>" + early_chips_html + "</div>" if early_chips_html else
   "<div style='color:#475569;font-size:.85em;padding:12px 0'>No emerging/building industries with enough tracked stocks right now.</div>"}
</div>

<!-- ── VOLUME CLUSTERS ────────────────────────────────────────────────────── -->
<div class="section" id="volume">
  <div class="sec-title">🔥 Volume Cluster Radar</div>
  <div class="sec-sub">
    Industries where ≥20% of stocks had a volume spike (&gt;1.5× 20-day avg) in the last 5 sessions.
    Multiple stocks spiking together = probable institutional accumulation signal.
  </div>
  {"<div class='chip-row'>" + vol_chips_html + "</div>" if vol_chips_html else
   "<div style='color:#475569;font-size:.85em;padding:12px 0'>No volume clusters detected (threshold: 20%+ of industry stocks with vol &gt;1.5× avg in last 5 days).</div>"}
</div>

<!-- ── 52W HIGH LEADERS ────────────────────────────────────────────────────── -->
<div class="section" id="highs">
  <div class="sec-title">🏔 52-Week High Momentum Leaders</div>
  <div class="sec-sub">
    Industries with the most new all-time / 52-week highs in the last 5 sessions.
    These are the <b>strongest breadth leaders</b> — money is rotating in.
  </div>
  {"<div class='chip-row'>" + hi52_chips_html + "</div>" if hi52_chips_html else
   "<div style='color:#475569;font-size:.85em;padding:12px 0'>No new 52-week highs detected in the last 5 sessions across tracked stocks.</div>"}
</div>

<!-- ── FULL BREADTH MAP ───────────────────────────────────────────────────── -->
<div class="section" id="fullmap">
  <div class="sec-title">📋 Full Industry Breadth Map</div>
  <div class="sec-sub">
    All {total_industries} tracked industries sorted by composite breadth score.
    Click column headers to sort. Use the filter bar above to narrow down.
    <br><b>Breadth Score</b> = 30%×(>20MA) + 40%×(>50MA) + 30%×(>200MA). Higher = stronger.
    <b>Vol Spike %</b> = % of industry stocks with unusual volume in last 5 sessions.
    <b>52W Hi (5d)</b> = count of new 52W highs in last 5 sessions.
  </div>
  <div class="legend-row">
    <div class="leg"><div class="leg-dot" style="background:#3fb950"></div>EMERGING (25–65% >20MA) — Early accumulation ← best buy zone</div>
    <div class="leg"><div class="leg-dot" style="background:#e3b341"></div>BUILDING (65–80%) — Momentum building</div>
    <div class="leg"><div class="leg-dot" style="background:#f85149"></div>EXTENDED (>80%) — Watch for pullback</div>
    <div class="leg"><div class="leg-dot" style="background:#475569"></div>WEAK (<25%) — Avoid</div>
  </div>
  <div class="ind-tbl-wrap">
    <table class="tbl" id="indTable">
      <thead><tr>
        <th class="sort-icon" data-col="industry" onclick="sortTable('industry')">Industry</th>
        <th class="sort-icon" data-col="sector" onclick="sortTable('sector')">Sector</th>
        <th>Stage</th>
        <th class="sort-icon" data-col="pct_20ma" onclick="sortTable('pct_20ma')" title="% stocks above 20-day MA">%&gt;20MA</th>
        <th class="sort-icon" data-col="pct_50ma" onclick="sortTable('pct_50ma')" title="% stocks above 50-day MA">%&gt;50MA</th>
        <th class="sort-icon" data-col="pct_200ma" onclick="sortTable('pct_200ma')" title="% stocks above 200-day MA">%&gt;200MA</th>
        <th class="sort-icon" data-col="pct_52wh" onclick="sortTable('pct_52wh')" title="% within 5% of 52W high">%@52W</th>
        <th class="sort-icon" data-col="avg_rs3m" onclick="sortTable('avg_rs3m')" title="Avg RS vs Nifty, 3 months">RS 3M</th>
        <th class="sort-icon" data-col="avg_rs1m" onclick="sortTable('avg_rs1m')" title="Avg RS vs Nifty, 1 month">RS 1M</th>
        <th class="sort-icon" data-col="vol_spike_pct" onclick="sortTable('vol_spike_pct')" title="% stocks with vol spike (>1.5x avg) in last 5 days">Vol Spike%</th>
        <th class="sort-icon" data-col="new_52wh" onclick="sortTable('new_52wh')" title="New 52W highs in last 5 sessions">52W Hi (5d)</th>
        <th class="sort-icon" data-col="breadth_score" onclick="sortTable('breadth_score')">Score</th>
        <th class="sort-icon" data-col="total" onclick="sortTable('total')">Stocks</th>
      </tr></thead>
      <tbody id="indTbody">{ind_rows_html}</tbody>
    </table>
  </div>
</div>

<div class="footer">
  Market Breadth Dashboard · Generated {now_str} ·
  Data from locally cached OHLCV CSVs — no live data fetched.
  Rerun after new scan to refresh breadth metrics.
</div>

<script>
// ── Row data (embedded) ───────────────────────────────────────────────────────
const rowData = {json.dumps([
    {
        "industry":      d["industry"],
        "sector":        d.get("sector",""),
        "stage":         d["stage"],
        "pct_20ma":      d.get("pct_20ma",0),
        "pct_50ma":      d.get("pct_50ma",0),
        "pct_200ma":     d.get("pct_200ma",0),
        "pct_52wh":      d.get("pct_52wh",0),
        "avg_rs3m":      d.get("avg_rs3m") or -999,
        "avg_rs1m":      d.get("avg_rs1m") or -999,
        "vol_spike_pct": d.get("vol_spike_pct",0),
        "new_52wh":      d.get("new_52wh",0),
        "breadth_score": d.get("breadth_score",0),
        "total":         d.get("total",0),
    }
    for d in industry_data
])};

let sortCol   = 'breadth_score';
let sortDir   = -1;   // -1 = desc, 1 = asc
let curFilter = '';
let curStage  = '';
let curSector = '';

function applyFilter() {{
  curFilter = document.getElementById('indSearch').value.toLowerCase();
  curStage  = document.getElementById('stageFilter').value;
  curSector = document.getElementById('sectorFilter').value;
  renderTable();
}}

function filterIndustry(ind) {{
  document.getElementById('indSearch').value = ind;
  curFilter = ind.toLowerCase();
  renderTable();
  document.getElementById('fullmap').scrollIntoView({{behavior:'smooth'}});
}}

function resetFilter() {{
  document.getElementById('indSearch').value = '';
  document.getElementById('stageFilter').value = '';
  document.getElementById('sectorFilter').value = '';
  curFilter = ''; curStage = ''; curSector = '';
  renderTable();
}}

function sortTable(col) {{
  if (sortCol === col) sortDir = -sortDir;
  else {{ sortCol = col; sortDir = -1; }}
  document.querySelectorAll('.tbl th').forEach(th => {{
    th.className = th.dataset.col === col
      ? (sortDir === -1 ? 'sort-desc' : 'sort-asc')
      : (th.dataset.col ? 'sort-icon' : '');
  }});
  renderTable();
}}

function renderTable() {{
  const filtered = rowData.filter(d => {{
    if (curFilter && !d.industry.toLowerCase().includes(curFilter) &&
        !d.sector.toLowerCase().includes(curFilter)) return false;
    if (curStage  && d.stage  !== curStage)  return false;
    if (curSector && d.sector !== curSector) return false;
    return true;
  }});
  filtered.sort((a, b) => {{
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'string') return sortDir * va.localeCompare(vb);
    return sortDir * ((vb || -999) - (va || -999));
  }});
  const ids = new Set(filtered.map(d => d.industry));
  document.querySelectorAll('#indTbody .ind-row').forEach(tr => {{
    const show = ids.has(tr.cells[0].textContent.trim());
    tr.classList.toggle('hidden', !show);
  }});
  // Re-sort DOM
  const tbody = document.getElementById('indTbody');
  filtered.forEach(d => {{
    const tr = [...tbody.querySelectorAll('.ind-row')].find(
      r => r.cells[0].textContent.trim() === d.industry
    );
    if (tr) tbody.appendChild(tr);
  }});
  document.getElementById('rowCount').textContent = filtered.length + ' industries';
}}

// Init
document.addEventListener('DOMContentLoaded', () => renderTable());
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Generating Market Breadth Dashboard…", flush=True)
    print(f"  INDUSTRY_MAP: {len(INDUSTRY_MAP)} stocks · SECTOR_MAP: {len(SECTOR_MAP)} stocks", flush=True)

    # Load Nifty benchmark
    nifty_closes = _load_nifty()
    if nifty_closes:
        print(f"  Nifty benchmark loaded: {len(nifty_closes)} sessions", flush=True)
    else:
        print("  ⚠ Nifty (^NSEI) price data not found — RS metrics will be empty", flush=True)

    # Compute per-industry metrics
    all_industries = sorted(set(INDUSTRY_MAP.values()))
    print(f"  Computing breadth for {len(all_industries)} industries…", flush=True)

    industry_data: list[dict] = []
    for i, ind in enumerate(all_industries, 1):
        metrics = compute_industry_metrics(ind, nifty_closes)
        if metrics and metrics.get("total", 0) >= 2:   # need ≥2 stocks to be meaningful
            industry_data.append(metrics)

    # Sort by breadth score descending
    industry_data.sort(key=lambda x: -x.get("breadth_score", 0))

    print(f"  {len(industry_data)} industries with ≥2 stocks of price data", flush=True)

    # Compute sector-level aggregates
    all_sectors = sorted(set(d["sector"] for d in industry_data))
    sector_data = [compute_sector_metrics(s, industry_data) for s in all_sectors]
    sector_data = [s for s in sector_data if s]

    # Generate HTML
    html = build_html(industry_data, sector_data)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out = OUTPUT / "market_breadth.html"
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(f"  ✅ Output: {out}  ({size_kb:.0f} KB)", flush=True)

    # Print summary
    stage_counts = {}
    for d in industry_data:
        stage_counts[d["stage"]] = stage_counts.get(d["stage"], 0) + 1
    for stage, cnt in sorted(stage_counts.items()):
        print(f"     {stage}: {cnt} industries", flush=True)

    # Top emerging
    emerging = [d for d in industry_data if d["stage"] == "EMERGING"][:5]
    if emerging:
        print("  Top EMERGING industries:", flush=True)
        for d in emerging:
            rs = d.get("avg_rs3m")
            rs_str = f"RS={rs:+.1f}%" if rs is not None else ""
            print(f"     {d['industry']} ({d['sector']}) — {d['pct_20ma']}% >20MA {rs_str}", flush=True)


if __name__ == "__main__":
    main()

