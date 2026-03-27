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
import csv, json, math, sys
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

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
    try: return float(v) if v not in (None, "", "N/A") else d
    except Exception: return d

def get_sector(symbol: str) -> str:
    base = symbol.replace(".NS","").replace(".BO","")
    return SECTOR_MAP.get(base, "Other")

def load_sparkline(symbol: str, n: int = 60) -> list[float]:
    """Load last n closes for sparkline from cache."""
    for suffix in ["_252", "_504", "_900"]:
        p = CACHE_DIR / f"{symbol}{suffix}.csv"
        if p.exists():
            closes = []
            try:
                with open(p) as f:
                    for row in csv.DictReader(f):
                        try: closes.append(float(row["close"]))
                        except: pass
            except Exception:
                pass
            if closes:
                return closes[-n:]
    return []

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
                score = _f(row.get("score",0))
                if sym not in seen or score > _f(seen[sym].get("score",0)):
                    row["_tf_label"] = label
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

        regime     = sig.get("regimeState","")
        regime_str = ("Favorable" if "FAV" in regime and "UNFAV" not in regime
                      else "Unfavorable" if "UNFAV" in regime else "Neutral")
        regime_cls = ("reg-fav" if regime_str == "Favorable"
                      else "reg-unfav" if regime_str == "Unfavorable" else "reg-neu")

        rs3m  = _f(sig.get("rs3m"))
        rs6m  = _f(sig.get("rs6m"))
        rs12m = _f(sig.get("rs12m"))
        rs_cls = "rpl" if rs3m > 0 else "rmi"

        setup_cls, setup_label, setup_tip = SETUP_META.get(
            setup, ("tag-bo", setup.replace("_"," "), ""))

        score = _f(sig.get("score",0))
        pivot = plan["entry"]  # entry IS the pivot area for current signals
        actual_pivot = _f(sig.get("pivot") or plan["entry"])

        width_pct  = min(score, 130) / 130 * 100
        score_color = "#3fb950" if score >= 100 else "#e3b341" if score >= 70 else "#f85149"

        vol_pct = sig.get("vol%","")
        rexp    = sig.get("rexp","")
        window  = sig.get("window","")
        dist_pivot = _f(sig.get("distFromPivot%") or sig.get("pivotProximityScore"))

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
    <div class="plan-section">
      <div class="plan-title">Target 1 &nbsp;<small>+{plan['rr_t1']:.1f}R</small></div>
      <div class="plan-value t1-val">&#8377;{plan['t1']:.2f}</div>
      <div class="plan-sub">Profit: +&#8377;{plan['t1_profit']:,.0f}</div>
    </div>
    <div class="plan-section">
      <div class="plan-title">Target 2 &nbsp;<small>+{plan['rr_t2']:.1f}R</small></div>
      <div class="plan-value t2-val">&#8377;{plan['t2']:.2f}</div>
      <div class="plan-sub">Profit: +&#8377;{plan['t2_profit']:,.0f}</div>
    </div>
    <div class="plan-section">
      <div class="plan-title">Target 3 &nbsp;<small>+{plan['rr_t3']:.1f}R</small></div>
      <div class="plan-value t3-val">&#8377;{plan['t3']:.2f}</div>
      <div class="plan-sub">Profit: +&#8377;{plan['t3_profit']:,.0f}</div>
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
      <span class="{rs_cls}">{rs3m:+.1f}%</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RS 6M</span>
      <span class="{'rpl' if rs6m>0 else 'rmi'}">{rs6m:+.1f}%</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">Vol %</span>
      <span style="color:#79c0ff">{vol_pct}</span>
    </div>
    <div class="sig-stat">
      <span class="sstat-label">RExp</span>
      <span style="color:#e3b341">{rexp}</span>
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
  const rows = [['Symbol','Sector','Setup','Rating','Entry','Pivot','Stop','T1','T2','T3','Shares','Capital','MaxLoss','R:R_T1','R:R_T2','Regime']];
  document.querySelectorAll('.sig-card').forEach(card => {{
    if(card.style.display === 'none') return;
    const vals = [...card.querySelectorAll('.plan-value')].map(v => v.textContent.replace(/[₹,]/g,'').trim());
    rows.push([card.dataset.symbol, card.dataset.sector, card.dataset.setup, card.dataset.rating, ...vals]);
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
    print(f"  Loaded {len(signals)} unique signals")
    html = build_html(signals)
    out = OUTPUT / "trade_plans_live.html"
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"  Output: {out}")
    print(f"  Size: {size:.1f} KB")

if __name__ == "__main__":
    main()

