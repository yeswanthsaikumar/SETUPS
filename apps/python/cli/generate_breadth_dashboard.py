#!/usr/bin/env python3
"""
generate_breadth_dashboard.py
─────────────────────────────
Standalone Market Breadth & Trend Detection Dashboard — NSE India

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


# ── Price helpers ──────────────────────────────────────────────────────────────

def _load_prices(ticker: str) -> list[dict]:
    best: list[dict] = []
    for suffix in ["_900", "_728", "_504", "_252"]:
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


def _rs(stock: list[float], bench: list[float], periods: int = 63) -> float | None:
    if len(stock) <= periods or len(bench) <= periods:
        return None
    return round((stock[-1]/stock[-(periods+1)] - 1)*100 - (bench[-1]/bench[-(periods+1)] - 1)*100, 1)


def _new52wh(closes: list[float], n: int = 5) -> int:
    if len(closes) < 252 + n:
        return 0
    count = 0
    for i in range(-n, 0):
        window = closes[max(0, i-252): i]
        if window and closes[i] >= max(window):
            count += 1
    return count


# ── Metric computation ─────────────────────────────────────────────────────────

def compute_industry_metrics(industry: str, nifty_closes: list[float]) -> dict | None:
    peers = [t for t, ind in INDUSTRY_MAP.items() if ind == industry]
    if not peers:
        return None
    a20 = a50 = a200 = at52 = vol_spike = new52 = total = 0
    rs3m_list: list[float] = []
    rs1m_list: list[float] = []

    for ticker in peers:
        rows = _load_prices(ticker)
        if len(rows) < 20:
            continue
        closes  = [r["close"] for r in rows]
        volumes = [r["volume"] for r in rows]
        last = closes[-1]
        total += 1
        if last > sum(closes[-20:]) / 20:                           a20  += 1
        if len(closes) >= 50  and last > sum(closes[-50:])/50:      a50  += 1
        if len(closes) >= 200 and last > sum(closes[-200:])/200:    a200 += 1
        hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        if last >= hi52 * 0.95:    at52 += 1
        new52 += _new52wh(closes, 5)
        if len(volumes) >= 25:
            avg_vol = sum(volumes[-25:-5]) / 20
            if avg_vol > 0 and any(v > avg_vol*1.5 for v in volumes[-5:]):
                vol_spike += 1
        r3 = _rs(closes, nifty_closes, 63)
        r1 = _rs(closes, nifty_closes, 21)
        if r3 is not None: rs3m_list.append(r3)
        if r1 is not None: rs1m_list.append(r1)

    if total == 0:
        return None
    p20  = round(a20  / total * 100)
    p50  = round(a50  / total * 100)
    p200 = round(a200 / total * 100)
    p52  = round(at52 / total * 100)
    avg_rs3m = round(sum(rs3m_list)/len(rs3m_list), 1) if rs3m_list else None
    avg_rs1m = round(sum(rs1m_list)/len(rs1m_list), 1) if rs1m_list else None
    vs_pct   = round(vol_spike / total * 100)

    if p20 >= 80:   stage, sc, se = "EXTENDED", "#f85149", "🔴"
    elif p20 >= 65: stage, sc, se = "BUILDING",  "#e3b341", "🟡"
    elif p20 >= 25: stage, sc, se = "EMERGING",  "#3fb950", "🟢"
    else:           stage, sc, se = "WEAK",      "#475569", "⚫"

    score = round(p20*0.3 + p50*0.4 + p200*0.3)
    return {
        "industry": industry, "sector": _IND_TO_SEC.get(industry, "Other"),
        "total": total, "pct_20ma": p20, "pct_50ma": p50, "pct_200ma": p200,
        "pct_52wh": p52, "new_52wh": new52, "vol_spike_pct": vs_pct,
        "avg_rs3m": avg_rs3m, "avg_rs1m": avg_rs1m,
        "stage": stage, "stage_color": sc, "stage_emoji": se, "breadth_score": score,
    }


def compute_sector_metrics(sector: str, industry_data: list[dict]) -> dict:
    rows = [d for d in industry_data if d.get("sector") == sector]
    if not rows:
        return {}
    n = sum(r["total"] for r in rows)
    if n == 0:
        return {}
    def _wa(key):
        vals = [(r[key], r["total"]) for r in rows if r.get(key) is not None]
        if not vals: return 0.0
        return round(sum(v*w for v, w in vals) / sum(w for _, w in vals), 1)
    p20 = _wa("pct_20ma"); p50 = _wa("pct_50ma"); p200 = _wa("pct_200ma")
    rs3m = _wa("avg_rs3m"); rs1m = _wa("avg_rs1m")
    if p20 >= 80:   stage, sc, se = "EXTENDED", "#f85149", "🔴"
    elif p20 >= 65: stage, sc, se = "BUILDING",  "#e3b341", "🟡"
    elif p20 >= 25: stage, sc, se = "EMERGING",  "#3fb950", "🟢"
    else:           stage, sc, se = "WEAK",      "#475569", "⚫"
    EARLY = {"Financials","Consumer","Internet","RealEstate"}
    MID   = {"IT","Cap Goods","Electronics","Cables","Defense","Metals"}
    LATE  = {"Energy","Renewable","Chemicals","Infra"}
    DEF   = {"FMCG","Pharma","Banking","Agri","Sugar"}
    cycle = ("Early Cycle" if sector in EARLY else "Mid Cycle" if sector in MID
             else "Late Cycle" if sector in LATE else "Defensive" if sector in DEF else "Other")
    return {"sector": sector, "industry_cnt": len(rows), "stock_count": n,
            "pct_20ma": p20, "pct_50ma": p50, "pct_200ma": p200,
            "avg_rs3m": rs3m, "avg_rs1m": rs1m,
            "stage": stage, "stage_color": sc, "stage_emoji": se, "cycle_phase": cycle}


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


# ── build_html ─────────────────────────────────────────────────────────────────

def build_html(industry_data: list[dict], sector_data: list[dict]) -> str:
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
    early_trends = sorted([d for d in industry_data if d["stage"] in ("EMERGING","BUILDING")],
                          key=lambda x: -(x.get("avg_rs3m") or -99))[:24]

    # ── Sector cards ──────────────────────────────────────────────────────────
    CYCLE_CLS = {"Early Cycle":"cycle-early","Mid Cycle":"cycle-mid",
                 "Late Cycle":"cycle-late","Defensive":"cycle-def"}
    sec_cards = ""
    for sd in sorted(sector_data, key=lambda x: -(x.get("avg_rs3m") or -99)):
        sec   = sd["sector"]
        p20   = sd.get("pct_20ma"); p50 = sd.get("pct_50ma"); p200 = sd.get("pct_200ma")
        rs3m  = sd.get("avg_rs3m"); rs1m = sd.get("avg_rs1m")
        stage = sd["stage"]; sc,sbg,sb,se = _stage_cfg(stage)
        n     = sd["stock_count"]; ni = sd.get("industry_cnt",0)
        cycle = sd.get("cycle_phase","Other"); ccls = CYCLE_CLS.get(cycle,"")
        up = rs1m is not None and rs3m is not None and rs1m > rs3m
        arr = f'<span style="color:{"#3fb950" if up else "#f85149"};font-weight:700">{"↑" if up else "↓"}</span>'
        sec_cards += (
            f'<div class="sec-card" style="border-top:3px solid {sc}">'
            f'<div class="sec-top"><div class="sec-name">{escape(sec)}</div>{_stage_pill(stage)}</div>'
            f'<div class="sec-meta"><span class="{ccls} cycle-badge">{cycle}</span>'
            f'<span class="sec-n">{n} stocks · {ni} ind.</span></div>'
            f'<div class="ibar-group">{_inline_bars(p20,p50,p200)}</div>'
            f'<div class="sec-rs">'
            f'<div><span class="rs-label">RS 3M</span>{_rs_badge(rs3m)}</div>'
            f'<div><span class="rs-label">RS 1M</span>{_rs_badge(rs1m)} {arr}</div>'
            f'</div></div>'
        )

    # ── Emerging trend cards ──────────────────────────────────────────────────
    early_cards = ""
    for d in early_trends:
        ind = d["industry"]; sec = d.get("sector","")
        p20=d.get("pct_20ma",0); p50=d.get("pct_50ma",0); p200=d.get("pct_200ma",0)
        rs3m=d.get("avg_rs3m"); rs1m=d.get("avg_rs1m")
        vs=d.get("vol_spike_pct",0); n52=d.get("new_52wh",0); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,_ = _stage_cfg(stage)
        ecls = "chip-em" if stage=="EMERGING" else "chip-bl"
        badge = "⚡ EMERGING" if stage=="EMERGING" else "🟡 BUILDING"
        notes_html = "".join([
            f'<span class="note-vol">🔥 {vs}% vol</span>' if vs>=15 else "",
            f'<span class="note-hi">🏔 {n52} 52W hi</span>' if n52>0 else "",
        ])
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
            f'</div></div>'
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
        vol_cards += (
            f'<div class="vol-card" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="vc-top"><span class="vc-icon">{icon}</span>{_stage_pill(stage)}</div>'
            f'<div class="vc-name">{escape(ind)}</div>'
            f'<div class="vc-sec">{escape(sec)} · {n} stocks</div>'
            f'<div class="vc-track"><div class="vc-fill" style="width:{bw}%;background:{clr}"></div></div>'
            f'<div class="vc-val" style="color:{clr}">{vs}% stocks with vol spike</div>'
            f'<div class="vc-foot"><span class="pct-na">{p20}% &gt;20MA</span>{_rs_badge(rs3m)}</div>'
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
        hi52_cards += (
            f'<div class="hi52-card" onclick="filterIndustry(\'{safe}\')">'
            f'<div class="hc-badge">🏔 {n52} new highs <span class="hc-span">(last 5d)</span></div>'
            f'<div class="hc-name">{escape(ind)}</div>'
            f'<div class="hc-sec">{escape(sec)} · {n} stocks</div>'
            f'<div class="hc-track"><div class="hc-fill" style="width:{bw52}%"></div></div>'
            f'<div class="hc-pct">{p52}% near 52W high</div>'
            f'<div class="hc-foot">{_stage_pill(stage)}{_rs_badge(rs3m)}</div>'
            f'</div>'
        )
    if not hi52_cards:
        hi52_cards = '<div class="empty-state">No new 52-week highs in the last 5 sessions.</div>'

    # ── Industry table rows ───────────────────────────────────────────────────
    ind_rows = ""
    for d in industry_data:
        ind=d["industry"]; sec=d.get("sector","")
        p20=d.get("pct_20ma"); p50=d.get("pct_50ma"); p200=d.get("pct_200ma")
        p52=d.get("pct_52wh"); rs3m=d.get("avg_rs3m"); rs1m=d.get("avg_rs1m")
        vs=d.get("vol_spike_pct",0); n52=d.get("new_52wh",0); n=d.get("total",0)
        stage=d["stage"]; sc,sbg,sb,se = _stage_cfg(stage); score=d.get("breadth_score",0)
        up  = rs1m is not None and rs3m is not None and rs1m > rs3m
        arr = f'<span style="color:{"#3fb950" if up else "#f85149"};font-size:.85em">{"↑" if up else "↓"}</span>'
        n52_clr = "#3fb950" if n52>=3 else "#e3b341" if n52>=1 else "#475569"
        p52_str = f'<span style="color:#7dd3fc;font-size:.82em">{p52}%</span>' if p52 is not None else '<span class="pct-na">—</span>'
        ind_escaped = escape(ind)
        ind_rows += (
            f'<tr class="ind-row" data-industry="{ind_escaped}" '
            f'data-stage="{stage}" data-sector="{escape(sec)}" data-score="{score}" '
            f'style="border-left:3px solid {sc}33">'
            f'<td class="ind-name" title="{ind_escaped}">{ind_escaped}</td>'
            f'<td><span class="sec-badge">{escape(sec)}</span></td>'
            f'<td>{_stage_pill(stage)}</td>'
            f'<td class="pct-cell">{_pct_bar(p20)}</td>'
            f'<td class="pct-cell">{_pct_bar(p50)}</td>'
            f'<td class="pct-cell">{_pct_bar(p200)}</td>'
            f'<td class="pct-cell">{p52_str}</td>'
            f'<td class="pct-cell">{_rs_badge(rs3m)}</td>'
            f'<td class="pct-cell">{_rs_badge(rs1m)} {arr}</td>'
            f'<td class="pct-cell">{_vol_display(vs)}</td>'
            f'<td class="pct-cell" style="color:{n52_clr};font-weight:{"700" if n52>0 else "400"}">'
            f'{"🏔 " if n52>0 else ""}{n52 if n52>0 else "—"}</td>'
            f'<td class="pct-cell">{_score_ring(score)}</td>'
            f'<td class="pct-cell pct-na">{n}</td>'
            f'</tr>'
        )

    all_sectors = sorted({d.get("sector","") for d in industry_data if d.get("sector")})
    sec_opts = "\n".join(f'<option value="{s}">{escape(s)}</option>' for s in all_sectors)

    row_json = json.dumps([
        {"industry": d["industry"], "sector": d.get("sector",""), "stage": d["stage"],
         "pct_20ma": d.get("pct_20ma",0), "pct_50ma": d.get("pct_50ma",0),
         "pct_200ma": d.get("pct_200ma",0), "pct_52wh": d.get("pct_52wh",0),
         "avg_rs3m": d.get("avg_rs3m") or -999, "avg_rs1m": d.get("avg_rs1m") or -999,
         "vol_spike_pct": d.get("vol_spike_pct",0), "new_52wh": d.get("new_52wh",0),
         "breadth_score": d.get("breadth_score",0), "total": d.get("total",0)}
        for d in industry_data
    ])

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

@media(max-width:680px){
  .sec-grid{grid-template-columns:1fr 1fr}
  .early-grid,.vol-grid,.hi52-grid{grid-template-columns:1fr}
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

<div class="nav-bar">
  <a class="nav-link" href="#rotation">🔄 Sector Rotation</a>
  <a class="nav-link" href="#trends">⚡ Emerging Trends</a>
  <a class="nav-link" href="#volume">🔥 Vol Clusters</a>
  <a class="nav-link" href="#highs">🏔 52W Leaders</a>
  <a class="nav-link" href="#fullmap">📋 Full Map</a>
  <a class="nav-link nav-ext" href="trade_plans_live.html">↩ Trade Plans</a>
</div>

<div class="ctrl-bar">
  <input class="ci wide" id="indSearch" placeholder="🔍 Filter industry or sector…" oninput="applyFilter()">
  <select class="ci" id="stageFilter" onchange="applyFilter()">
    <option value="">All Stages</option>
    <option value="EMERGING">🟢 Emerging (25–65%)</option>
    <option value="BUILDING">🟡 Building (65–80%)</option>
    <option value="EXTENDED">🔴 Extended (&gt;80%)</option>
    <option value="WEAK">⚫ Weak (&lt;25%)</option>
  </select>
  <select class="ci" id="sectorFilter" onchange="applyFilter()">
    <option value="">All Sectors</option>
    {sec_opts}
  </select>
  <button class="cb" onclick="sortTable('breadth_score')">Score</button>
  <button class="cb" onclick="sortTable('pct_20ma')">&gt;20MA</button>
  <button class="cb" onclick="sortTable('avg_rs3m')">RS 3M</button>
  <button class="cb" onclick="sortTable('new_52wh')">52W Hi</button>
  <button class="cb" onclick="sortTable('vol_spike_pct')">Vol Spike</button>
  <button class="cb reset" onclick="resetFilter()">↺ Reset</button>
  <span id="rowCount"></span>
</div>

<div class="section" id="rotation">
  <div class="sec-hdr">
    <h2>🔄 Sector Rotation Tracker</h2>
    <p>Sectors ranked by RS vs Nifty (3M). Inline bars = % stocks above 20/50/200 MA.
    RS 1M arrow shows if momentum is <b>accelerating ↑ or fading ↓</b>.
    <b>Early Cycle</b> leads at bottoms · <b>Mid Cycle</b> peak growth ·
    <b>Late Cycle</b> commodity inflation · <b>Defensive</b> recession shelter.</p>
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
    <p>All {total_ind} tracked industries. Click column headers to sort. Left border = stage color.
    <b>Score ring</b> = 30%×(&gt;20MA) + 40%×(&gt;50MA) + 30%×(&gt;200MA).
    <b>Vol%</b> = vol spike % in last 5 days · <b>52W(5d)</b> = new highs in last 5 sessions.</p>
  </div>
  <div class="legend">
    <div class="leg"><div class="leg-dot" style="background:#3fb950"></div>EMERGING 25–65% &gt;20MA — best entry</div>
    <div class="leg"><div class="leg-dot" style="background:#e3b341"></div>BUILDING 65–80%</div>
    <div class="leg"><div class="leg-dot" style="background:#f85149"></div>EXTENDED &gt;80% — pullback risk</div>
    <div class="leg"><div class="leg-dot" style="background:#334155"></div>WEAK &lt;25% — avoid</div>
  </div>
  <div class="tbl-wrap">
    <table class="tbl" id="indTable">
      <thead><tr>
        <th data-col="industry" onclick="sortTable('industry')">Industry</th>
        <th data-col="sector" onclick="sortTable('sector')">Sector</th>
        <th>Stage</th>
        <th data-col="pct_20ma" onclick="sortTable('pct_20ma')" title="% above 20-day MA">&gt;20MA</th>
        <th data-col="pct_50ma" onclick="sortTable('pct_50ma')" title="% above 50-day MA">&gt;50MA</th>
        <th data-col="pct_200ma" onclick="sortTable('pct_200ma')" title="% above 200-day MA">&gt;200MA</th>
        <th data-col="pct_52wh" onclick="sortTable('pct_52wh')" title="% within 5% of 52W high">@52W</th>
        <th data-col="avg_rs3m" onclick="sortTable('avg_rs3m')" title="RS vs Nifty 3M">RS 3M</th>
        <th data-col="avg_rs1m" onclick="sortTable('avg_rs1m')" title="RS vs Nifty 1M">RS 1M</th>
        <th data-col="vol_spike_pct" onclick="sortTable('vol_spike_pct')" title="Vol spike % last 5d">Vol%</th>
        <th data-col="new_52wh" onclick="sortTable('new_52wh')" title="New 52W highs last 5 sessions">52W(5d)</th>
        <th data-col="breadth_score" onclick="sortTable('breadth_score')" title="Composite score">Score</th>
        <th data-col="total" onclick="sortTable('total')">N</th>
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
let sortCol='breadth_score',sortDir=-1,curFilter='',curStage='',curSector='';
function applyFilter(){{curFilter=document.getElementById('indSearch').value.toLowerCase();curStage=document.getElementById('stageFilter').value;curSector=document.getElementById('sectorFilter').value;renderTable();}}
function filterIndustry(ind){{document.getElementById('indSearch').value=ind;curFilter=ind.toLowerCase();curStage='';curSector='';document.getElementById('stageFilter').value='';document.getElementById('sectorFilter').value='';renderTable();document.getElementById('fullmap').scrollIntoView({{behavior:'smooth'}});}}
function resetFilter(){{document.getElementById('indSearch').value='';document.getElementById('stageFilter').value='';document.getElementById('sectorFilter').value='';curFilter='';curStage='';curSector='';renderTable();}}
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
  tbody.querySelectorAll('.ind-row').forEach(tr=>{{tr.classList.toggle('hidden',!ids.has(tr.dataset.industry));}});
  filtered.forEach(d=>{{const tr=tbody.querySelector('.ind-row[data-industry="'+d.industry.replace(/"/g,'&quot;')+'"]');if(tr)tbody.appendChild(tr);}});
  document.getElementById('rowCount').textContent=filtered.length+' industries shown';
}}
document.addEventListener('DOMContentLoaded',()=>renderTable());
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Generating Market Breadth Dashboard…", flush=True)
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

    html = build_html(industry_data, sector_data)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out  = OUTPUT / "market_breadth.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✅ {out}  ({out.stat().st_size/1024:.0f} KB)", flush=True)

    counts: dict[str, int] = {}
    for d in industry_data: counts[d["stage"]] = counts.get(d["stage"], 0) + 1
    for s, c in sorted(counts.items()): print(f"     {s}: {c}", flush=True)
    for d in [d for d in industry_data if d["stage"]=="EMERGING"][:5]:
        rs = d.get("avg_rs3m")
        suffix = f" RS={rs:+.1f}%" if rs is not None else ""
        print(f"     ⚡ {d['industry']} ({d['sector']}) — {d['pct_20ma']}%>20MA{suffix}", flush=True)


if __name__ == "__main__":
    main()

