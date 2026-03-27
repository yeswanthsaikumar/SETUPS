#!/usr/bin/env python3
"""
generate_sector_macro_page.py
Generates a standalone Sector Rotation + Macro Impact HTML page with:
  - Sector quarterly and monthly return heatmaps
  - Sector momentum rank (3M/6M/12M relative strength)
  - Macro event timeline with market impact analysis
  - Fundamentals signals affecting breakout performance
  - Market regime history
Run: python3 apps/python/cli/generate_sector_macro_page.py
"""
from __future__ import annotations
import csv, json, math, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[3]
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache"
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

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
    "IPCALAB":"Pharma","GLENMARK":"Pharma","GRANULES":"Pharma",
    "MARUTI":"Auto","TATAMOTORS":"Auto","HEROMOTOCO":"Auto","EICHERMOT":"Auto",
    "TVSMOTOR":"Auto","ASHOKLEY":"Auto","TIINDIA":"Auto","M&M":"Auto",
    "RELIANCE":"Energy","ONGC":"Energy","BPCL":"Energy","IOC":"Energy","HINDPETRO":"Energy",
    "GAIL":"Energy","COALINDIA":"Energy","ADANIGREEN":"Energy","NTPC":"Energy","POWERGRID":"Energy",
    "TATASTEEL":"Metals","HINDALCO":"Metals","JSWSTEEL":"Metals","SAIL":"Metals",
    "VEDL":"Metals","NMDC":"Metals","HINDZINC":"Metals","APLAPOLLO":"Metals",
    "ADANIENT":"Infra","ADANIPORTS":"Infra","L&T":"Infra","ADANIPOWER":"Infra",
    "BAJFINANCE":"NBFC","BAJAJFINSV":"NBFC","CHOLAFIN":"NBFC","M&MFIN":"NBFC",
    "MUTHOOTFIN":"NBFC","MANAPPURAM":"NBFC","PFC":"NBFC","RECLTD":"NBFC",
    "TITAN":"Consumer","ASIANPAINT":"Consumer","PIDILITIND":"Consumer","HAVELLS":"Consumer",
    "VOLTAS":"Consumer","DIXON":"Consumer","CROMPTON":"Consumer",
    "NAUKRI":"Internet","ZOMATO":"Internet","PAYTM":"Internet","IRCTC":"Internet",
    "DLF":"RealEstate","GODREJPROP":"RealEstate","OBEROIRLTY":"RealEstate","PRESTIGE":"RealEstate",
    "SIEMENS":"Cap Goods","ABB":"Cap Goods","BHEL":"Cap Goods","BEL":"Cap Goods",
    "CUMMINSIND":"Cap Goods","THERMAX":"Cap Goods",
    "HDFCLIFE":"Insurance","SBILIFE":"Insurance","ICICIPRU":"Insurance",
}

MACRO_EVENTS = [
    {"date":"2023-04-06","type":"RBI","label":"RBI Hold 6.5%","impact":"NEUTRAL","desc":"RBI pauses rate hikes. Markets absorb with resilience. Breakout setups active in Banking and Auto."},
    {"date":"2023-05-10","type":"EARNINGS","label":"Q4FY23 Results","impact":"POSITIVE","desc":"Strong quarterly results across IT, Banking, FMCG. Broad-based rally. High breakout success rate."},
    {"date":"2023-07-26","type":"FED","label":"US Fed +25bps 5.25%","impact":"NEGATIVE","desc":"Fed rate hike causes brief FII outflow. Dollar strengthens. IT sector and export stocks see selling."},
    {"date":"2023-08-24","type":"GLOBAL","label":"Jackson Hole Hawkish","impact":"NEGATIVE","desc":"Fed signals higher-for-longer rates. EM capital outflow risk. Cautious breakout environment."},
    {"date":"2023-10-15","type":"GLOBAL","label":"Israel-Hamas Conflict","impact":"NEGATIVE","desc":"Crude oil spike. Energy sector volatile. Defense stocks rally. Breakout success falls in broader market."},
    {"date":"2023-12-13","type":"FED","label":"US Fed Pivot Signal","impact":"POSITIVE","desc":"Fed signals potential rate cuts. Global risk-on rally. FII buying resumes. Strong bull breakouts in Jan 2024."},
    {"date":"2024-02-01","type":"BUDGET","label":"Interim Budget FY25","impact":"POSITIVE","desc":"No tax changes. Capex focus maintained. Infrastructure, Railways, Defense see re-rating. Strong setup environment."},
    {"date":"2024-04-19","type":"GLOBAL","label":"Iran-Israel Escalation","impact":"NEGATIVE","desc":"Crude surge. Risk-off globally. Many breakouts fail. Metals rally due to supply concerns."},
    {"date":"2024-05-23","type":"ELECTION","label":"India Election BJP Win","impact":"POSITIVE","desc":"Continuity of policy. Market euphoria. Infrastructure, PSU, Banking rally strongly. Best breakout period."},
    {"date":"2024-07-23","type":"BUDGET","label":"Budget LTCG Hike 12.5%","impact":"NEGATIVE","desc":"LTCG hike and STT increase cause FII selling. Market correction. Small/midcap hit hardest. Avoid new entries."},
    {"date":"2024-08-05","type":"GLOBAL","label":"Yen Carry Trade Unwind","impact":"NEGATIVE","desc":"Global selloff. Nifty drops 2% in a day. Most breakouts fail. Wait for dust to settle."},
    {"date":"2024-09-18","type":"FED","label":"US Fed Cut 50bps","impact":"POSITIVE","desc":"Aggressive Fed cut. FII buying returns. EM markets rally. Strong breakout window Oct 2024."},
    {"date":"2024-10-03","type":"MARKET","label":"FII Sell-off Begins","impact":"NEGATIVE","desc":"Sustained FII selling through Oct-Nov 2024. Nifty drops from 26K to 23K. Bear market for breakouts."},
    {"date":"2024-11-05","type":"ELECTION","label":"Trump Wins US Election","impact":"NEGATIVE","desc":"Dollar strengthens. EM outflows. Tariff fears. India IT sector faces headwinds. Reduce long exposure."},
    {"date":"2024-12-18","type":"FED","label":"US Fed Cut 25bps + Hawkish","impact":"NEGATIVE","desc":"Fed cuts but signals fewer cuts ahead. Dollar spikes. Global risk-off. EM selling continues."},
    {"date":"2025-02-01","type":"BUDGET","label":"Budget FY26 Capex Focus","impact":"POSITIVE","desc":"Middle-class tax relief. Infra spending up. Market gap-up. Infrastructure, NBFC, Consumer see buying."},
    {"date":"2025-02-07","type":"RBI","label":"RBI Cut 25bps 6.25%","impact":"POSITIVE","desc":"First RBI rate cut since 2020. Positive for Banking, NBFC, RealEstate. Sentiment turns positive."},
    {"date":"2025-04-09","type":"GLOBAL","label":"US Tariff Liberation Day","impact":"NEGATIVE","desc":"Massive tariff escalation. Global trade war fears. India IT, Pharma, Metals under pressure."},
    {"date":"2025-04-09","type":"RBI","label":"RBI Emergency Cut 6.0%","impact":"POSITIVE","desc":"RBI cuts to offset tariff shock. Dovish pivot. Banking and rate-sensitives rally."},
    {"date":"2025-06-06","type":"RBI","label":"RBI Cut 25bps 5.75%","impact":"POSITIVE","desc":"Continued rate cut cycle. Liquidity improves. NBFC, Housing Finance, Consumer Durables benefit."},
    {"date":"2025-09-17","type":"FED","label":"US Fed Cut 25bps 4.0%","impact":"POSITIVE","desc":"Global easing continues. Dollar weakens. FII inflows to EM markets. India re-rating potential."},
    {"date":"2025-12-10","type":"RBI","label":"RBI Cut 25bps 5.5%","impact":"POSITIVE","desc":"4th rate cut of the cycle. Strong liquidity. Credit growth accelerating. Bull setup brewing."},
    {"date":"2026-02-01","type":"BUDGET","label":"Budget FY27","impact":"POSITIVE","desc":"Continued capex. GST reforms. Agricultural support. Infrastructure supercycle intact."},
    {"date":"2026-02-05","type":"RBI","label":"RBI Cut 25bps 5.25%","impact":"POSITIVE","desc":"5th consecutive cut. Repo at 5.25%. Banking sector re-rating. Real estate revival. Setup environment improves."},
]

SECTOR_ROTATION_INSIGHT = {
    "2023-Q2": {"leader":"Banking","laggard":"IT","note":"RBI pause → Banking rally; US rate fears hurt IT"},
    "2023-Q3": {"leader":"Auto","laggard":"IT","note":"Urban demand surge; IT weak on US macro"},
    "2023-Q4": {"leader":"Consumer","laggard":"FMCG","note":"Festival demand; FMCG margin pressure"},
    "2024-Q1": {"leader":"Infrastructure","laggard":"FMCG","note":"Budget infra push; FMCG rural slowdown"},
    "2024-Q2": {"leader":"PSU/Energy","laggard":"IT","note":"Election rally; IT weak on weak US demand"},
    "2024-Q3": {"leader":"Metals","laggard":"Consumer","note":"China stimulus; Consumer demand slowing"},
    "2024-Q4": {"leader":"Pharma","laggard":"Banking","note":"Defensive rotation; FII selling Banks"},
    "2025-Q1": {"leader":"Pharma","laggard":"IT","note":"Defensive; IT under tariff uncertainty"},
    "2025-Q2": {"leader":"NBFC","laggard":"IT","note":"RBI cuts benefit NBFC; IT still uncertain"},
    "2025-Q3": {"leader":"Banking","laggard":"Metals","note":"Rate cuts + FII return → Banking; China slow → Metals"},
    "2025-Q4": {"leader":"Consumer","laggard":"Energy","note":"Lower rates boost consumer; Oil prices weak"},
    "2026-Q1": {"leader":"Banking","laggard":"FMCG","note":"Re-rating underway; FMCG still rangebound"},
}

def _f(v, d=0.0):
    try: return float(v) if v not in (None,"","N/A") else d
    except: return d

def get_sector(symbol: str) -> str:
    base = symbol.replace(".NS","").replace(".BO","")
    return SECTOR_MAP.get(base, None)

def load_sector_prices() -> dict:
    """Load price data for mapped sectors only."""
    sector_data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    files = sorted(CACHE_DIR.glob("*.NS_900.csv"))
    count = 0
    for f in files:
        sym = f.stem.replace("_900", "")
        sector = get_sector(sym)
        if sector is None:
            continue
        try:
            with open(f) as fh:
                for row in csv.DictReader(fh):
                    d = row.get("date","")
                    if not d: continue
                    try:
                        close = float(row["close"])
                        sector_data[sector][d].append((sym, close))
                        count += 1
                    except: pass
        except Exception:
            pass
    print(f"  Loaded {count:,} price points for {len(sector_data)} sectors")
    return sector_data

def compute_returns(sector_data: dict) -> tuple[dict, dict, dict]:
    """Compute monthly and quarterly returns per sector."""
    sector_monthly: dict[str, dict[str, float]] = {}
    sector_quarterly: dict[str, dict[str, float]] = {}
    sector_rs: dict[str, dict[str, float]] = {}   # 3M/6M/12M RS

    for sector, date_prices in sector_data.items():
        # Group by month/quarter
        by_month: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for d, pairs in date_prices.items():
            ym = d[:7]
            try:
                dt = datetime.strptime(d[:10], "%Y-%m-%d")
                q  = f"{dt.year}-Q{(dt.month-1)//3+1}"
            except: q = "unknown"
            for sym, close in pairs:
                by_month[ym][sym].append(close)

        # Monthly return = avg of (last/first - 1) across all stocks in sector
        monthly_rets: dict[str, float] = {}
        # We need full month data, so group by month then compute each stock's monthly return
        sym_month: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for d, pairs in date_prices.items():
            ym = d[:7]
            for sym, close in pairs:
                sym_month[sym][ym].append(close)

        all_months = sorted({d[:7] for d in date_prices.keys()})
        for ym in all_months:
            rets = []
            for sym, months in sym_month.items():
                prices = months.get(ym,[])
                if len(prices) >= 5:
                    rets.append((prices[-1] - prices[0]) / prices[0] * 100)
            if rets:
                monthly_rets[ym] = round(sum(rets)/len(rets), 2)
        sector_monthly[sector] = monthly_rets

        # Quarterly
        quarterly_rets: dict[str, float] = {}
        sym_q: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for d, pairs in date_prices.items():
            try:
                dt = datetime.strptime(d[:10], "%Y-%m-%d")
                q  = f"{dt.year}-Q{(dt.month-1)//3+1}"
            except: q = "unknown"
            for sym, close in pairs:
                sym_q[sym][q].append(close)

        all_quarters = sorted({q for sym_qs in sym_q.values() for q in sym_qs.keys()})
        for q in all_quarters:
            rets = []
            for sym, qs in sym_q.items():
                prices = qs.get(q,[])
                if len(prices) >= 10:
                    rets.append((prices[-1] - prices[0]) / prices[0] * 100)
            if rets:
                quarterly_rets[q] = round(sum(rets)/len(rets), 2)
        sector_quarterly[sector] = quarterly_rets

        # RS: compare last 3M, 6M, 12M performance
        all_sorted_months = sorted(monthly_rets.keys())
        if len(all_sorted_months) >= 3:
            rs3m  = sum(monthly_rets.get(m,0) for m in all_sorted_months[-3:])
            rs6m  = sum(monthly_rets.get(m,0) for m in all_sorted_months[-6:]) if len(all_sorted_months) >= 6 else rs3m * 2
            rs12m = sum(monthly_rets.get(m,0) for m in all_sorted_months[-12:]) if len(all_sorted_months) >= 12 else rs3m * 4
            sector_rs[sector] = {"rs3m": round(rs3m,2), "rs6m": round(rs6m,2), "rs12m": round(rs12m,2)}

    return sector_monthly, sector_quarterly, sector_rs

def heatmap_color(val, vmin=-15, vmax=15):
    if val is None: return "#161b22"
    if val > 0:
        intensity = min(1.0, val / max(vmax, 0.01))
        g = int(50 + intensity * 150)
        return f"rgba(30,{g},50,0.9)"
    else:
        intensity = min(1.0, abs(val) / max(abs(vmin), 0.01))
        r = int(50 + intensity * 150)
        return f"rgba({r},30,50,0.9)"

def text_color_for_val(val):
    if val is None: return "#6e7681"
    if abs(val) >= 8: return "#f0f6fc"
    if abs(val) >= 3: return "#c9d1d9"
    return "#8b949e"

def build_html(sector_monthly, sector_quarterly, sector_rs) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sectors = sorted(sector_monthly.keys())

    # ── Quarterly heatmap
    all_quarters = sorted({q for s in sector_quarterly.values() for q in s.keys()
                           if q != "unknown"})
    q_rows = []
    for sec in sectors:
        cells = [f'<td class="row-lbl">{sec}</td>']
        for q in all_quarters:
            val = sector_quarterly[sec].get(q)
            if val is None:
                cells.append('<td style="color:#333;background:#0d1117">—</td>')
            else:
                bg  = heatmap_color(val, -20, 20)
                tc  = text_color_for_val(val)
                cells.append(f'<td style="background:{bg};color:{tc}" title="{q}: {val:+.1f}%">{val:+.1f}%</td>')
        q_rows.append(f'<tr>{"".join(cells)}</tr>')

    q_headers = '<th class="row-lbl">Sector</th>' + "".join(f'<th>{q}</th>' for q in all_quarters)
    quarterly_table = f"""<div class="htable-wrap">
<table class="htable">
<thead><tr>{q_headers}</tr></thead>
<tbody>{"".join(q_rows)}</tbody>
</table></div>"""

    # ── Monthly heatmap (last 24)
    all_months = sorted({m for s in sector_monthly.values() for m in s.keys()})[-24:]
    m_rows = []
    for sec in sectors:
        cells = [f'<td class="row-lbl">{sec}</td>']
        for m in all_months:
            val = sector_monthly[sec].get(m)
            if val is None:
                cells.append('<td style="color:#333;background:#0d1117">—</td>')
            else:
                bg = heatmap_color(val, -12, 12)
                tc = text_color_for_val(val)
                cells.append(f'<td style="background:{bg};color:{tc}" title="{m}: {val:+.1f}%">{val:+.1f}%</td>')
        m_rows.append(f'<tr>{"".join(cells)}</tr>')

    m_headers = '<th class="row-lbl">Sector</th>' + "".join(f'<th>{m[2:]}</th>' for m in all_months)
    monthly_table = f"""<div class="htable-wrap">
<table class="htable">
<thead><tr>{m_headers}</tr></thead>
<tbody>{"".join(m_rows)}</tbody>
</table></div>"""

    # ── Sector RS ranking table
    rs_rows = []
    rs_sorted = sorted(sectors, key=lambda s: -sector_rs.get(s, {}).get("rs3m", -999))
    for rank, sec in enumerate(rs_sorted, 1):
        rs = sector_rs.get(sec, {})
        r3  = rs.get("rs3m",  0)
        r6  = rs.get("rs6m",  0)
        r12 = rs.get("rs12m", 0)
        momentum = "RISING" if r3 > 0 and r3 > r6/2 else "FALLING" if r3 < 0 else "FLAT"
        mom_cls  = "mom-rising" if momentum == "RISING" else "mom-falling" if momentum == "FALLING" else "mom-flat"
        rs_rows.append(f"""<tr>
          <td style="color:#8b949e;font-weight:700">#{rank}</td>
          <td style="font-weight:700;color:#c9d1d9">{sec}</td>
          <td class="{'rpl' if r3>0 else 'rmi'}">{r3:+.1f}%</td>
          <td class="{'rpl' if r6>0 else 'rmi'}">{r6:+.1f}%</td>
          <td class="{'rpl' if r12>0 else 'rmi'}">{r12:+.1f}%</td>
          <td><span class="{mom_cls}">{momentum}</span></td>
        </tr>""")

    # ── Sector rotation insights
    rotation_rows = []
    for q, info in sorted(SECTOR_ROTATION_INSIGHT.items()):
        rotation_rows.append(f"""<tr>
          <td style="color:#8b949e;font-weight:600">{q}</td>
          <td style="color:#3fb950;font-weight:600">{info['leader']}</td>
          <td style="color:#f85149;font-weight:600">{info['laggard']}</td>
          <td style="color:#8b949e;font-size:.82em">{info['note']}</td>
        </tr>""")

    # ── Macro events
    macro_cards = []
    type_css = {"RBI":"ev-rbi","FED":"ev-fed","BUDGET":"ev-budget","ELECTION":"ev-election",
                "GLOBAL":"ev-global","MARKET":"ev-market","EARNINGS":"ev-earnings"}
    for ev in MACRO_EVENTS:
        imp = ev["impact"]
        imp_cls = "imp-pos" if imp == "POSITIVE" else "imp-neg" if imp == "NEGATIVE" else "imp-neu"
        type_cls = type_css.get(ev["type"], "ev-global")
        macro_cards.append(f"""<div class="macro-card {imp_cls}-border">
  <div class="mc-header">
    <span class="ev-tag {type_cls}">{ev['type']}</span>
    <span class="ev-date">{ev['date']}</span>
    <span class="{imp_cls}">{imp}</span>
  </div>
  <div class="mc-title">{ev['label']}</div>
  <div class="mc-desc">{ev['desc']}</div>
</div>""")

    # ── Fundamentals & Macro Framework
    fund_framework = """
<div class="framework-grid">
  <div class="fw-card fw-positive">
    <div class="fw-title">&#128200; Bull Trigger Checklist</div>
    <ul class="fw-list">
      <li>RBI rate cut cycle active (repo below 6%)</li>
      <li>FII net buyers for 3+ consecutive weeks</li>
      <li>Nifty above 200-DMA with rising slope</li>
      <li>Q-o-Q earnings growth &gt;15% in 2+ sectors</li>
      <li>USD/INR below 84 (FII-friendly)</li>
      <li>Crude oil stable below $80/bbl</li>
      <li>US Fed in cutting cycle</li>
      <li>India PMI Manufacturing &gt;53</li>
    </ul>
  </div>
  <div class="fw-card fw-negative">
    <div class="fw-title">&#128201; Bear Warning Checklist</div>
    <ul class="fw-list">
      <li>FII net sellers for 2+ consecutive weeks</li>
      <li>Nifty below 200-DMA</li>
      <li>US Fed hawkish or hiking</li>
      <li>Crude oil above $90/bbl</li>
      <li>USD/INR above 85</li>
      <li>Earnings misses in Banking &amp; IT</li>
      <li>Global risk events (war, trade war)</li>
      <li>Credit events / NBFC stress</li>
    </ul>
  </div>
  <div class="fw-card fw-neutral">
    <div class="fw-title">&#127942; Best Sector Rotations</div>
    <ul class="fw-list">
      <li><b>Rate Cut Cycle:</b> Banking &rarr; NBFC &rarr; RealEstate</li>
      <li><b>Budget Rally:</b> Infra &rarr; Defence &rarr; Railways</li>
      <li><b>Global Rally:</b> IT &rarr; Pharma &rarr; Metals</li>
      <li><b>Earnings Season:</b> Banking &rarr; Auto &rarr; FMCG</li>
      <li><b>Risk-Off:</b> Pharma &rarr; FMCG &rarr; IT</li>
      <li><b>FII Buying:</b> Large-Cap &rarr; Midcap &rarr; Smallcap</li>
      <li><b>Election Year:</b> PSU &rarr; Defence &rarr; Infra</li>
      <li><b>Monsoon:</b> FMCG &rarr; Agro &rarr; Rural Consumer</li>
    </ul>
  </div>
  <div class="fw-card fw-info">
    <div class="fw-title">&#127757; Current Macro Assessment (Mar 2026)</div>
    <ul class="fw-list">
      <li>&#128994; RBI Rate: 5.25% (Cutting cycle active)</li>
      <li>&#128308; Market Regime: UNFAVORABLE (Nifty weak)</li>
      <li>&#128994; US Fed: 3.75% (Easing)</li>
      <li>&#128993; Crude Oil: ~$72/bbl (Manageable)</li>
      <li>&#128308; FII: Net sellers YTD 2026</li>
      <li>&#128994; India GDP: 6.8% (Resilient)</li>
      <li>&#128993; USD/INR: ~86 (Mild pressure)</li>
      <li>&#128308; Global: Tariff uncertainty persists</li>
    </ul>
  </div>
</div>"""

    macro_html = "\n".join(macro_cards)

    # ── Chart data for JS
    sector_q_js = {}
    for sec in sectors:
        sector_q_js[sec] = [sector_quarterly[sec].get(q, None) for q in all_quarters]

    sector_q_json  = json.dumps(sector_q_js)
    quarters_json  = json.dumps(all_quarters)
    rs_labels_json = json.dumps(rs_sorted[:10])
    rs3m_json      = json.dumps([sector_rs.get(s,{}).get("rs3m",0) for s in rs_sorted[:10]])
    rs6m_json      = json.dumps([sector_rs.get(s,{}).get("rs6m",0) for s in rs_sorted[:10]])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sector Analysis &amp; Macro Impact | {now}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:#0d1117;color:#c9d1d9}}

.topbar{{background:linear-gradient(135deg,#0d1117,#1a2433);border-bottom:1px solid #21262d;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:50;backdrop-filter:blur(8px)}}
.topbar-title{{color:#79c0ff;font-size:1.3em;font-weight:700}}
.topbar-sub{{color:#8b949e;font-size:.82em;margin-top:3px}}

.tabs{{display:flex;gap:0;border-bottom:1px solid #21262d;background:#161b22;padding:0 28px;position:sticky;top:65px;z-index:40}}
.tab{{padding:12px 18px;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;font-size:.88em;font-weight:500;transition:all .2s;white-space:nowrap}}
.tab:hover{{color:#c9d1d9}}
.tab.active{{color:#58a6ff;border-bottom-color:#58a6ff;background:rgba(88,166,255,.04)}}
.tab-content{{display:none;padding:24px 28px;max-width:1600px;margin:0 auto}}
.tab-content.active{{display:block}}

.section-title{{color:#c9d1d9;font-size:1.05em;font-weight:700;margin:24px 0 14px;display:flex;align-items:center;gap:10px;letter-spacing:-.2px}}
.section-title::after{{content:'';flex:1;height:1px;background:#21262d}}
.info-box{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 18px;margin-bottom:20px;font-size:.83em;color:#8b949e;line-height:1.7}}
.info-box strong{{color:#79c0ff}}

/* HEATMAP */
.htable-wrap{{overflow-x:auto;border:1px solid #21262d;border-radius:10px;margin-bottom:24px}}
.htable{{border-collapse:collapse;width:100%;font-size:.78em;white-space:nowrap}}
.htable th{{background:#161b22;color:#8b949e;padding:9px 10px;text-align:center;font-weight:600;border:1px solid #21262d;position:sticky;top:0;z-index:2}}
.htable td{{padding:9px 10px;text-align:center;border:1px solid #0d1117;font-weight:600;min-width:65px}}
.row-lbl{{text-align:left!important;color:#c9d1d9;font-weight:700;background:#161b22;position:sticky;left:0;z-index:1;min-width:100px!important;padding-left:12px!important}}

/* LEGEND */
.heatmap-legend{{display:flex;align-items:center;gap:8px;font-size:.75em;color:#8b949e;margin-bottom:12px}}
.hl-gradient{{width:200px;height:12px;border-radius:4px;background:linear-gradient(to right,rgba(200,30,50,.9),rgba(20,20,20,.5),rgba(30,180,50,.9))}}
.hl-labels{{display:flex;justify-content:space-between;width:200px;font-size:.9em}}

/* RS TABLE */
.data-table-wrap{{overflow-x:auto;border:1px solid #21262d;border-radius:10px;margin-bottom:24px}}
.data-table{{border-collapse:collapse;width:100%;font-size:.84em}}
.data-table th{{background:#161b22;color:#8b949e;padding:10px 14px;font-weight:600;border-bottom:1px solid #21262d;text-align:left}}
.data-table td{{padding:10px 14px;border-bottom:1px solid #161b22}}
.data-table tr:hover td{{background:rgba(88,166,255,.04)}}
.rpl{{color:#3fb950;font-weight:600}}
.rmi{{color:#f85149;font-weight:600}}
.mom-rising{{color:#3fb950;font-weight:600;font-size:.82em}}
.mom-falling{{color:#f85149;font-weight:600;font-size:.82em}}
.mom-flat{{color:#e3b341;font-weight:600;font-size:.82em}}

/* MACRO */
.macro-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-bottom:24px}}
.macro-card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px}}
.imp-pos-border{{border-left:3px solid #3fb950}}
.imp-neg-border{{border-left:3px solid #f85149}}
.imp-neu-border{{border-left:3px solid #e3b341}}
.mc-header{{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}}
.ev-tag{{padding:2px 8px;border-radius:4px;font-size:.72em;font-weight:700}}
.ev-rbi{{background:#1a2a3a;color:#58a6ff}}
.ev-fed{{background:#2a1a3a;color:#d2a8ff}}
.ev-budget{{background:#1a2a1a;color:#3fb950}}
.ev-election{{background:#2a1a1a;color:#ffa657}}
.ev-global{{background:#2a2a1a;color:#e3b341}}
.ev-market{{background:#1a2a2a;color:#79c0ff}}
.ev-earnings{{background:#2a1a2a;color:#f0883e}}
.ev-date{{color:#8b949e;font-size:.78em}}
.imp-pos{{color:#3fb950;font-weight:600;font-size:.8em}}
.imp-neg{{color:#f85149;font-weight:600;font-size:.8em}}
.imp-neu{{color:#e3b341;font-weight:600;font-size:.8em}}
.mc-title{{color:#c9d1d9;font-weight:700;font-size:.9em;margin-bottom:6px}}
.mc-desc{{color:#8b949e;font-size:.8em;line-height:1.5}}

/* FRAMEWORK */
.framework-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-bottom:24px}}
.fw-card{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:16px}}
.fw-positive{{border-top:3px solid #3fb950}}
.fw-negative{{border-top:3px solid #f85149}}
.fw-neutral{{border-top:3px solid #58a6ff}}
.fw-info{{border-top:3px solid #e3b341}}
.fw-title{{font-weight:700;color:#c9d1d9;margin-bottom:12px;font-size:.92em}}
.fw-list{{list-style:none;padding:0}}
.fw-list li{{padding:5px 0;border-bottom:1px solid #21262d;font-size:.82em;color:#8b949e;display:flex;align-items:center;gap:8px}}
.fw-list li:last-child{{border-bottom:none}}

/* CHARTS */
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}
.chart-box{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:18px}}
.chart-title{{color:#79c0ff;font-size:.9em;font-weight:600;margin-bottom:14px}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">&#127968; Sector Rotation &amp; Macro Impact Analysis</div>
    <div class="topbar-sub">NSE India | Apr 2023 &ndash; Mar 2026 | {now}</div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('quarterly',this)">&#128197; Quarterly Returns</div>
  <div class="tab" onclick="showTab('monthly',this)">&#128200; Monthly Returns</div>
  <div class="tab" onclick="showTab('rotation',this)">&#127942; Sector Rotation</div>
  <div class="tab" onclick="showTab('macro',this)">&#127758; Macro Events</div>
  <div class="tab" onclick="showTab('framework',this)">&#128240; Fundamentals Framework</div>
</div>

<!-- TAB 1: QUARTERLY -->
<div id="tab-quarterly" class="tab-content active">
  <div class="info-box">
    <strong>Quarterly Returns Heatmap</strong> &mdash;
    Average quarterly price return (%) across all mapped NSE stocks per sector.
    Green = outperformance, Red = underperformance. Values are equal-weighted averages.
  </div>
  <div class="heatmap-legend">
    <span style="color:#f85149">-20%</span>
    <div class="hl-gradient"></div>
    <span style="color:#3fb950">+20%</span>
    &nbsp;&nbsp;
    <span style="color:#8b949e">Darker = stronger magnitude</span>
  </div>
  {quarterly_table}

  <div class="section-title">&#128202; Sector Quarterly Returns Chart</div>
  <div class="chart-box" style="margin-bottom:24px">
    <div class="chart-title">Sector Average Quarterly Returns (%) &mdash; Last 8 Quarters</div>
    <canvas id="qReturnChart" height="80"></canvas>
  </div>
</div>

<!-- TAB 2: MONTHLY -->
<div id="tab-monthly" class="tab-content">
  <div class="info-box">
    <strong>Monthly Returns Heatmap (Last 24 months)</strong> &mdash;
    Average monthly price return (%) per sector. Useful for identifying seasonal patterns,
    budget rallies, earnings season effects, and macro event reactions.
  </div>
  <div class="heatmap-legend">
    <span style="color:#f85149">-12%</span>
    <div class="hl-gradient"></div>
    <span style="color:#3fb950">+12%</span>
  </div>
  {monthly_table}
</div>

<!-- TAB 3: ROTATION -->
<div id="tab-rotation" class="tab-content">
  <div class="section-title">&#127942; Sector Relative Strength Ranking (Current)</div>
  <div class="info-box">
    Sectors ranked by 3-Month relative strength. RISING = accelerating momentum.
    FALLING = decelerating. Use this to align trade entries with sector momentum.
  </div>
  <div class="chart-grid">
    <div class="chart-box">
      <div class="chart-title">3M vs 6M Sector Relative Strength (%)</div>
      <canvas id="rsChart" height="200"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">Sector Momentum Ranking (3M RS)</div>
      <canvas id="momChart" height="200"></canvas>
    </div>
  </div>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Rank</th><th>Sector</th><th>3M RS</th><th>6M RS</th><th>12M RS</th><th>Momentum</th>
      </tr></thead>
      <tbody>{"".join(rs_rows)}</tbody>
    </table>
  </div>

  <div class="section-title">&#127760; Quarterly Sector Rotation History</div>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Quarter</th><th>Leader Sector</th><th>Laggard Sector</th><th>Key Driver</th>
      </tr></thead>
      <tbody>{"".join(rotation_rows)}</tbody>
    </table>
  </div>
</div>

<!-- TAB 4: MACRO -->
<div id="tab-macro" class="tab-content">
  <div class="info-box">
    <strong>Macro Events Impact Analysis</strong> &mdash;
    Each card shows a key macro event and its impact on breakout trading.
    <span style="color:#3fb950">Green border</span> = POSITIVE for markets.
    <span style="color:#f85149">Red border</span> = NEGATIVE.
    <span style="color:#e3b341">Yellow border</span> = NEUTRAL.
  </div>
  <div class="macro-grid">
    {macro_html}
  </div>
</div>

<!-- TAB 5: FRAMEWORK -->
<div id="tab-framework" class="tab-content">
  <div class="info-box">
    <strong>Fundamentals &amp; Macro Framework for Breakout Trading</strong> &mdash;
    A systematic checklist for evaluating market conditions before taking breakout trades.
    Always trade WITH the macro backdrop, not against it.
  </div>
  {fund_framework}

  <div class="section-title">&#128196; How Fundamentals Affect Breakout Performance</div>
  <div class="framework-grid">
    <div class="fw-card" style="border-top:3px solid #58a6ff">
      <div class="fw-title">&#127968; Earnings Season Impact</div>
      <ul class="fw-list">
        <li>Q1 results (Jul-Aug): Best breakouts in Banking, IT, Auto</li>
        <li>Q2 results (Oct-Nov): Check festive season data for Consumer</li>
        <li>Q3 results (Jan-Feb): Pre-budget positioning creates setups</li>
        <li>Q4 results (Apr-May): Year-end cleanup; fresh cycle begins</li>
        <li>EPS growth &gt;25% QoQ = high-probability breakout candidate</li>
        <li>Revenue miss even with beat = caution on breakout</li>
      </ul>
    </div>
    <div class="fw-card" style="border-top:3px solid #e3b341">
      <div class="fw-title">&#128176; Valuation &amp; PE Context</div>
      <ul class="fw-list">
        <li>Nifty PE &lt;18 = cheap, breakouts more reliable</li>
        <li>Nifty PE 18-22 = fair value, normal breakout rules</li>
        <li>Nifty PE &gt;24 = expensive, only A+ setups with catalyst</li>
        <li>Individual stock PE expansion = high RS momentum driver</li>
        <li>Sector PE re-rating = strongest breakout catalyst</li>
        <li>PEG ratio &lt;1 = growth at reasonable price</li>
      </ul>
    </div>
    <div class="fw-card" style="border-top:3px solid #3fb950">
      <div class="fw-title">&#128201; FII/DII Flow Analysis</div>
      <ul class="fw-list">
        <li>FII net buyers 5+ days = strong breakout environment</li>
        <li>FII selling &gt;Rs5000 Cr/week = reduce new entries</li>
        <li>DII buying offsetting FII = floor but no momentum</li>
        <li>Both FII + DII buying = strongest breakout regime</li>
        <li>Futures long buildup = confirms breakout direction</li>
        <li>Delivery % &gt;50% = institutional conviction breakout</li>
      </ul>
    </div>
    <div class="fw-card" style="border-top:3px solid #f85149">
      <div class="fw-title">&#127758; Global Macro Risks</div>
      <ul class="fw-list">
        <li>US 10-yr yield &gt;4.5% = EM outflows, reduce India longs</li>
        <li>VIX &gt;20 = avoid new breakouts, wait for calm</li>
        <li>DXY (USD index) &gt;105 = FII outflows from India</li>
        <li>Crude &gt;$90 = inflation risk, RBI hawkish = bearish</li>
        <li>China slowdown = Metals, Chemical sector headwind</li>
        <li>US recession risk = IT sector export headwind</li>
      </ul>
    </div>
  </div>
</div>

<script>
function showTab(id, el) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  el.classList.add('active');
  if(id === 'rotation' && !window._rotBuilt) buildRotCharts();
  if(id === 'quarterly' && !window._qBuilt) buildQChart();
}}

const sectorsQ = {sector_q_json};
const quartersAll = {quarters_json};
const rsLabels = {rs_labels_json};
const rs3mData = {rs3m_json};
const rs6mData = {rs6m_json};

const CHART_DEFAULTS = {{
  responsive: true,
  plugins: {{ legend: {{ labels: {{ color:'#8b949e', font:{{size:11}} }} }} }},
  scales: {{
    x: {{ ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:'#21262d'}} }},
    y: {{ ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:'#21262d'}} }}
  }}
}};

window._qBuilt  = false;
window._rotBuilt = false;

function buildQChart() {{
  window._qBuilt = true;
  const lastQ = quartersAll.slice(-8);
  const colors = ['#58a6ff','#3fb950','#f85149','#e3b341','#d2a8ff','#79c0ff','#ffa657','#86efac','#ff7b72','#ffd700'];
  const datasets = Object.keys(sectorsQ).map((sec, i) => ({{
    label: sec,
    data: lastQ.map(q => {{
      const idx = quartersAll.indexOf(q);
      return idx >= 0 ? sectorsQ[sec][idx] : null;
    }}),
    borderColor: colors[i % colors.length],
    backgroundColor: 'transparent',
    borderWidth: 2,
    pointRadius: 3,
    tension: 0.3,
    spanGaps: true
  }}));
  new Chart(document.getElementById('qReturnChart'), {{
    type: 'line',
    data: {{ labels: lastQ, datasets }},
    options: {{
      ...CHART_DEFAULTS,
      scales: {{
        x: {{ ticks:{{color:'#8b949e'}}, grid:{{color:'#21262d'}} }},
        y: {{ ticks:{{color:'#8b949e',callback:v=>v+'%'}}, grid:{{color:'#21262d'}} }}
      }}
    }}
  }});
}}

function buildRotCharts() {{
  window._rotBuilt = true;
  new Chart(document.getElementById('rsChart'), {{
    type: 'bar',
    data: {{
      labels: rsLabels,
      datasets: [
        {{ label:'3M RS%', data:rs3mData, backgroundColor:'rgba(88,166,255,0.6)', borderRadius:3 }},
        {{ label:'6M RS%', data:rs6mData, backgroundColor:'rgba(63,185,80,0.4)',  borderRadius:3 }}
      ]
    }},
    options: {{...CHART_DEFAULTS,
      scales:{{
        x:{{ticks:{{color:'#8b949e',font:{{size:10}}}},grid:{{color:'#21262d'}}}},
        y:{{ticks:{{color:'#8b949e',callback:v=>v+'%'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});
  const momColors = rs3mData.map(v => v >= 0 ? 'rgba(63,185,80,0.7)' : 'rgba(248,81,73,0.7)');
  new Chart(document.getElementById('momChart'), {{
    type: 'bar',
    data: {{
      labels: rsLabels,
      datasets: [{{ label:'3M Return%', data:rs3mData, backgroundColor:momColors, borderRadius:4 }}]
    }},
    options: {{...CHART_DEFAULTS,
      indexAxis: 'y',
      plugins:{{legend:{{display:false}}}},
      scales:{{
        y:{{ticks:{{color:'#c9d1d9',font:{{size:10}}}},grid:{{color:'#21262d'}}}},
        x:{{ticks:{{color:'#8b949e',callback:v=>v+'%'}},grid:{{color:'#21262d'}}}}
      }}
    }}
  }});
}}

document.addEventListener('DOMContentLoaded', () => buildQChart());
</script>
</body>
</html>"""

def main():
    print("Generating Sector + Macro Analysis page...")
    print("[1/3] Loading sector prices...")
    sector_data = load_sector_prices()
    print("[2/3] Computing returns...")
    sec_monthly, sec_quarterly, sec_rs = compute_returns(sector_data)
    print(f"  Sectors: {len(sec_monthly)}, Quarters: {len(next(iter(sec_quarterly.values()),{}))}")
    print("[3/3] Building HTML...")
    html = build_html(sec_monthly, sec_quarterly, sec_rs)
    out = OUTPUT / "sector_macro_analysis.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Output: {out}")
    print(f"  Size: {out.stat().st_size/1024:.1f} KB")

if __name__ == "__main__":
    main()

