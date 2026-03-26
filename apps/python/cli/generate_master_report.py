#!/usr/bin/env python3
"""
generate_master_report.py
─────────────────────────
Reads all *_LATEST.json scan outputs, merges them across markets/timeframes,
recalculates position sizes for a ₹10 lakh (₹10,00,000) portfolio, enriches
with fundamentals, and writes a single master HTML report.

Best-buy-point logic per setup:
  VCP (Consolidation Breakout)  → buy above pivot on volume confirmation
  RANGE_EXPANSION               → buy on open of next bar after wide-range breakout
  MEAN_REVERSION                → buy as price reclaims the mean (SMA20 / lower BB)
  BREAKOUT_PULLBACK             → buy on first pullback holding above breakout level
  BREAKOUT (Python)             → buy on breakout retest / confirmation bar

Usage:
    python3 apps/python/cli/generate_master_report.py
    python3 apps/python/cli/generate_master_report.py --account-size 1000000 --output-dir output
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

try:
    from fundamentals_provider import FundamentalsProvider, compact_summary as _fund_summary
    _FUND_AVAILABLE = True
except Exception:
    _FUND_AVAILABLE = False

from utils import to_float as _f

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_ACCOUNT_SIZE  = 1_000_000   # ₹10 lakh
DEFAULT_RISK_PCT      = 0.01        # 1% risk per trade = ₹10,000
CURRENCY_SYMBOL       = "₹"

SETUP_LABELS = {
    "VCP":               "📈 Consolidation Breakout (VCP)",
    "RANGE_EXPANSION":   "🚀 Range Expansion Breakout",
    "MEAN_REVERSION":    "🔄 Mean Reversion",
    "BREAKOUT_PULLBACK": "🎯 Breakout First Pullback",
    "BREAKOUT":          "⚡ Python Breakout",
}

BEST_BUY_NOTES = {
    "VCP":               "Buy above pivot on volume ≥1.5× avg; stop below base low",
    "RANGE_EXPANSION":   "Buy open of next session after wide-range candle clears base",
    "MEAN_REVERSION":    "Buy as price reclaims SMA20 / bounces lower BB; stop 2×ATR below",
    "BREAKOUT_PULLBACK": "Buy pullback to breakout support zone on dried-up volume; stop below BO level",
    "BREAKOUT":          "Buy on confirmation close above prior high or retest; stop below swing low",
}


def _recompute_shares(entry: float, sl: float, account: float, risk_pct: float) -> int:
    risk = entry - sl
    if risk <= 0 or entry <= 0:
        return 0
    return max(1, int(math.floor(account * risk_pct / risk)))


def _rr(entry: float, sl: float, t1: float) -> str:
    risk = entry - sl
    reward = t1 - entry
    if risk <= 0:
        return "—"
    return f"{reward / risk:.1f}R"


def _regime_badge(state: str) -> str:
    state = (state or "").upper()
    color = {"FAVORABLE": "#22c55e", "NEUTRAL": "#f59e0b", "UNFAVORABLE": "#ef4444"}.get(state, "#94a3b8")
    label = {"FAVORABLE": "🟢 Favorable", "NEUTRAL": "🟡 Neutral", "UNFAVORABLE": "🔴 Unfavorable"}.get(state, state or "—")
    return f"<span style='color:{color};font-weight:600'>{label}</span>"


def _dist_badge(dist: float) -> str:
    if dist <= 0:
        color, label = "#22c55e", f"{dist:+.1f}% AT PIVOT"
    elif dist <= 2:
        color, label = "#22c55e", f"+{dist:.1f}% near"
    elif dist <= 5:
        color, label = "#f59e0b", f"+{dist:.1f}%"
    else:
        color, label = "#ef4444", f"+{dist:.1f}% extended"
    return f"<span style='color:{color}'>{label}</span>"


def load_latest_files(output_dir: Path) -> list[dict]:
    """Load all *_LATEST.json scan files and tag each row with market+timeframe."""
    all_rows: list[dict] = []
    patterns = [
        ("india", "daily"),
        ("india", "weekly"),
        ("us",    "daily"),
        ("us",    "weekly"),
    ]
    for market, tf in patterns:
        p = output_dir / f"vcp_hits_{market}_{tf}_full_LATEST.json"
        if not p.exists():
            p = output_dir / f"vcp_hits_{market}_{tf}_LATEST.json"
        if not p.exists():
            continue
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                continue
            for row in rows:
                row["_market"]    = market
                row["_timeframe"] = tf
                all_rows.append(row)
        except Exception:
            continue
    return all_rows


def build_master_report(
    output_dir: Path,
    account_size: float,
    risk_pct: float,
    cache_dir: Path,
    skip_fundamentals: bool,
) -> str:
    rows = load_latest_files(output_dir)
    if not rows:
        return "<h2>No scan output found. Run the scan first.</h2>"

    # Recalculate position sizes for the specified portfolio
    is_india_row = lambda r: r.get("_market") == "india"
    for row in rows:
        entry = _f(row.get("entry"))
        sl    = _f(row.get("sl"))
        if entry > 0 and sl > 0 and entry > sl:
            row["_shares_10L"] = _recompute_shares(entry, sl, account_size, risk_pct)
            row["_position_val"] = round(row["_shares_10L"] * entry)
            row["_risk_amount"]  = round(row["_shares_10L"] * (entry - sl))
            row["_rr_t1"]        = _rr(entry, sl, _f(row.get("T1")))
        else:
            row["_shares_10L"]   = 0
            row["_position_val"] = 0
            row["_risk_amount"]  = 0
            row["_rr_t1"]        = "—"

    # Fetch fundamentals
    if _FUND_AVAILABLE and not skip_fundamentals:
        syms = list({r.get("symbol", "") for r in rows if r.get("symbol")})
        print(f"  Fetching fundamentals for {len(syms)} symbols …", flush=True)
        fp = FundamentalsProvider(cache_dir=str(cache_dir))
        fund_data = fp.fetch_batch(syms, delay_s=0.1)
        for row in rows:
            sym = row.get("symbol", "")
            fd  = fund_data.get(sym, {})
            row["_fund"] = _fund_summary(fd, is_india=is_india_row(row)) if fd else "—"
    else:
        for row in rows:
            row["_fund"] = row.get("fundSummary") or "—"

    # Sort: setup priority then ranking score
    SETUP_ORDER = {"VCP": 0, "RANGE_EXPANSION": 1, "BREAKOUT_PULLBACK": 2, "MEAN_REVERSION": 3, "BREAKOUT": 4}
    rows.sort(key=lambda r: (
        SETUP_ORDER.get(r.get("setup", "").upper(), 9),
        -_f(r.get("rankingScore") or r.get("score") or 0),
    ))

    # Build HTML
    now = datetime.now().strftime("%d %b %Y %H:%M")
    setup_counts: dict[str, int] = {}
    for r in rows:
        s = r.get("setup", "?").upper()
        setup_counts[s] = setup_counts.get(s, 0) + 1

    SETUP_COLORS = {"VCP":"#6366f1","RANGE_EXPANSION":"#f59e0b","BREAKOUT_PULLBACK":"#22c55e","MEAN_REVERSION":"#06b6d4","BREAKOUT":"#8b5cf6"}
    summary_pills = " ".join(
        f"<span style='background:{SETUP_COLORS.get(s,'#94a3b8')};color:#fff;padding:3px 10px;border-radius:12px;font-size:0.82em'>{SETUP_LABELS.get(s,s)} ({v})</span>"
        for s, v in sorted(setup_counts.items(), key=lambda x: SETUP_ORDER.get(x[0], 9))
    )

    rows_html = ""
    for r in rows:
        setup     = r.get("setup", "").upper()
        market    = r.get("_market", "?")
        tf        = r.get("_timeframe", "?")
        sym       = html.escape(r.get("symbol", ""))
        rating    = r.get("rating", "")
        score     = _f(r.get("rankingScore") or r.get("score") or 0)
        close_v   = _f(r.get("close"))
        pivot_v   = _f(r.get("pivot"))
        entry_v   = _f(r.get("entry"))
        sl_v      = _f(r.get("sl"))
        t1_v      = _f(r.get("T1"))
        t2_v      = _f(r.get("T2"))
        t3_v      = _f(r.get("T3"))
        dist_v    = _f(r.get("dist%") or r.get("distFromPivot%") or 0)
        shares    = r.get("_shares_10L", 0)
        pos_val   = r.get("_position_val", 0)
        risk_amt  = r.get("_risk_amount", 0)
        rr_t1     = r.get("_rr_t1", "—")
        fund      = html.escape(r.get("_fund") or "—")
        regime    = r.get("regimeSupport") or r.get("regimeState") or "—"
        rs_score  = r.get("rsScore") or "—"
        vol_ratio = r.get("volumeDryUpRatio") or r.get("vol%") or "—"
        weekly_ag = r.get("weeklyAgreement") or "—"
        window    = r.get("window") or tf.upper()
        best_buy  = html.escape(BEST_BUY_NOTES.get(setup, "—"))

        # Rating colour
        rc = {"A+": "#16a34a", "A": "#22c55e", "B": "#f59e0b", "C": "#f97316", "D": "#ef4444"}.get(rating.upper(), "#94a3b8")
        setup_color = {"VCP":"#6366f1","RANGE_EXPANSION":"#f59e0b","BREAKOUT_PULLBACK":"#22c55e","MEAN_REVERSION":"#06b6d4","BREAKOUT":"#8b5cf6"}.get(setup,"#94a3b8")

        # Yahoo / TV links
        yf_sym = sym.replace(".NS", "").replace(".BO", "") + (".NS" if ".NS" in sym else (".BO" if ".BO" in sym else ""))
        tv_sym = f"NSE:{sym[:-3]}" if sym.endswith(".NS") else (f"BSE:{sym[:-3]}" if sym.endswith(".BO") else sym)
        links  = (f"<a href='https://finance.yahoo.com/quote/{yf_sym}/chart' target='_blank'>YF</a> "
                  f"<a href='https://www.tradingview.com/chart/?symbol={tv_sym}' target='_blank'>TV</a>")

        cur = "₹" if market == "india" else "$"

        rows_html += f"""<tr data-setup="{setup}" data-market="{market}" data-tf="{tf}">
  <td><b>{sym}</b><br><small style='color:#888'>{market.upper()} {tf}</small></td>
  <td><span style='background:{setup_color};color:#fff;padding:2px 7px;border-radius:8px;font-size:0.8em'>{SETUP_LABELS.get(setup, setup)}</span></td>
  <td style='font-size:0.8em;color:#555'>{best_buy}</td>
  <td style='color:{rc};font-weight:700'>{html.escape(rating)}</td>
  <td style='font-weight:600'>{score:.1f}</td>
  <td>{html.escape(window)}</td>
  <td style='font-weight:600'>{cur}{close_v:,.2f}</td>
  <td style='color:#6366f1;font-weight:700'>{cur}{pivot_v:,.2f}</td>
  <td style='color:#22c55e;font-weight:700'>{cur}{entry_v:,.2f}</td>
  <td style='color:#ef4444;font-weight:700'>{cur}{sl_v:,.2f}</td>
  <td>{cur}{t1_v:,.2f}</td>
  <td>{cur}{t2_v:,.2f}</td>
  <td>{cur}{t3_v:,.2f}</td>
  <td style='font-weight:700'>{rr_t1}</td>
  <td style='color:#16a34a;font-weight:700'>{shares:,}</td>
  <td>{cur}{pos_val:,}</td>
  <td style='color:#ef4444'>{cur}{risk_amt:,}</td>
  <td>{_dist_badge(dist_v)}</td>
  <td style='font-size:0.78em'>{html.escape(str(rs_score))}</td>
  <td style='font-size:0.78em'>{html.escape(str(vol_ratio))}</td>
  <td style='font-size:0.78em'>{html.escape(str(weekly_ag))}</td>
  <td>{_regime_badge(regime)}</td>
  <td style='font-size:0.75em;color:#444;max-width:220px'>{fund}</td>
  <td>{links}</td>
</tr>
"""

    header_cells = [
        "Symbol", "Setup Type", "Best Buy Point", "Rating", "Score", "Window",
        "Close", "Pivot/Support", "Entry", "Stop Loss", "T1", "T2", "T3",
        "R:R (T1)", f"Shares<br><small>({CURRENCY_SYMBOL}10L @1%)</small>",
        "Position Value", "Risk Amount",
        "Dist from Pivot", "RS Score", "Vol Dry-Up", "Weekly Align",
        "Market Regime", "Fundamentals (EPS|Rev|Debt)", "Chart",
    ]
    th = "".join(f"<th onclick=\"sortTable({i})\">{c}</th>" for i, c in enumerate(header_cells))

    total_risk = sum(r.get("_risk_amount", 0) for r in rows)
    total_pos  = sum(r.get("_position_val", 0) for r in rows)
    avg_rr     = [_f(r.get("T1")) - _f(r.get("entry")) for r in rows if _f(r.get("T1")) > _f(r.get("entry")) > 0]
    avg_sl_rr  = [(_f(r.get("T1")) - _f(r.get("entry"))) / max(0.001, _f(r.get("entry")) - _f(r.get("sl"))) for r in rows
                  if _f(r.get("entry")) > _f(r.get("sl")) > 0 and _f(r.get("T1")) > 0]
    avg_rr_str = f"{sum(avg_sl_rr)/len(avg_sl_rr):.1f}R" if avg_sl_rr else "—"

    setup_filter_opts = "".join(
        f'<option value="{s}">{SETUP_LABELS.get(s, s)}</option>'
        for s in sorted(setup_counts, key=lambda x: SETUP_ORDER.get(x, 9))
    )

    setup_stat_pills = "".join(
        f'<div class="stat"><div class="label">{SETUP_LABELS.get(s,s)}</div><div class="val">{v}</div></div>'
        for s, v in sorted(setup_counts.items(), key=lambda x: SETUP_ORDER.get(x[0], 9))
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Master Setup Report — {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 24px 32px; border-bottom: 1px solid #1e293b; }}
  .header h1 {{ font-size: 1.6em; font-weight: 800; color: #f8fafc; }}
  .header .meta {{ color: #94a3b8; font-size: 0.88em; margin-top: 6px; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; padding: 16px 32px; background: #0f172a; border-bottom: 1px solid #1e293b; }}
  .stat {{ background: #1e293b; border-radius: 10px; padding: 12px 20px; min-width: 150px; }}
  .stat .label {{ font-size: 0.75em; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .val {{ font-size: 1.4em; font-weight: 800; color: #f1f5f9; }}
  .filters {{ padding: 12px 32px; background: #0f172a; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
  .filters label {{ color: #94a3b8; font-size: 0.85em; }}
  select, input {{ background: #1e293b; border: 1px solid #334155; color: #e2e8f0; padding: 6px 10px; border-radius: 6px; font-size: 0.85em; }}
  .pill-row {{ padding: 0 32px 10px; }}
  .table-wrap {{ overflow-x: auto; padding: 0 16px 40px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.82em; }}
  th {{ background: #1e293b; color: #94a3b8; padding: 8px 10px; text-align: left; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; white-space: nowrap; position: sticky; top: 0; z-index: 10; user-select: none; }}
  th:hover {{ color: #f1f5f9; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #1e293b; vertical-align: middle; white-space: nowrap; }}
  tr:hover td {{ background: #1e293b44; }}
  tr[data-setup="VCP"] td:first-child {{ border-left: 3px solid #6366f1; }}
  tr[data-setup="RANGE_EXPANSION"] td:first-child {{ border-left: 3px solid #f59e0b; }}
  tr[data-setup="BREAKOUT_PULLBACK"] td:first-child {{ border-left: 3px solid #22c55e; }}
  tr[data-setup="MEAN_REVERSION"] td:first-child {{ border-left: 3px solid #06b6d4; }}
  tr[data-setup="BREAKOUT"] td:first-child {{ border-left: 3px solid #8b5cf6; }}
  a {{ color: #60a5fa; text-decoration: none; margin-right: 6px; font-size: 0.82em; }}
  a:hover {{ text-decoration: underline; }}
  .hidden {{ display: none; }}
  #count {{ color: #94a3b8; font-size: 0.85em; padding: 6px 32px; }}
  .note {{ color: #64748b; font-size: 0.75em; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 Master Setup Report — All Markets &amp; Timeframes</h1>
  <div class="meta">Generated {now} &nbsp;|&nbsp; Portfolio: {CURRENCY_SYMBOL}{account_size:,.0f} &nbsp;|&nbsp; Risk/Trade: {risk_pct*100:.0f}% = {CURRENCY_SYMBOL}{account_size*risk_pct:,.0f}</div>
</div>
  <div class="stats">
  <div class="stat"><div class="label">Total Setups</div><div class="val">{len(rows)}</div></div>
  {setup_stat_pills}
  <div class="stat"><div class="label">Avg R:R (T1)</div><div class="val">{avg_rr_str}</div></div>
  <div class="stat"><div class="label">Total Position Value</div><div class="val">{CURRENCY_SYMBOL}{total_pos:,}</div></div>
  <div class="stat"><div class="label">Total Risk Deployed</div><div class="val">{CURRENCY_SYMBOL}{total_risk:,}</div></div>
</div>
<div class="filters">
  <label>Setup:</label>
  <select id="fSetup" onchange="applyFilters()">
    <option value="">All</option>
    {setup_filter_opts}
  </select>
  <label>Market:</label>
  <select id="fMarket" onchange="applyFilters()">
    <option value="">All</option><option value="india">India</option><option value="us">US</option>
  </select>
  <label>Timeframe:</label>
  <select id="fTF" onchange="applyFilters()">
    <option value="">All</option><option value="daily">Daily</option><option value="weekly">Weekly</option>
  </select>
  <label>Min Score:</label>
  <input type="number" id="fScore" value="0" min="0" max="100" step="5" onchange="applyFilters()" style="width:70px">
  <label>Symbol:</label>
  <input type="text" id="fSym" placeholder="Search…" oninput="applyFilters()" style="width:120px">
</div>
<div class="pill-row">{summary_pills}</div>
<div id="count"></div>
<div class="table-wrap">
<table id="masterTable">
<thead><tr>{th}</tr></thead>
<tbody id="tbody">{rows_html}</tbody>
</table>
</div>
<script>
let sortCol = 4, sortDir = -1;
function applyFilters() {{
  const setup  = document.getElementById('fSetup').value;
  const market = document.getElementById('fMarket').value;
  const tf     = document.getElementById('fTF').value;
  const minScore = parseFloat(document.getElementById('fScore').value) || 0;
  const sym    = document.getElementById('fSym').value.toUpperCase();
  let vis = 0;
  document.querySelectorAll('#tbody tr').forEach(tr => {{
    const s  = tr.dataset.setup   || '';
    const m  = tr.dataset.market  || '';
    const t  = tr.dataset.tf      || '';
    const sc = parseFloat(tr.cells[4]?.textContent) || 0;
    const nm = (tr.cells[0]?.textContent || '').toUpperCase();
    const show = (!setup||s===setup) && (!market||m===market) && (!tf||t===tf) && sc>=minScore && (!sym||nm.includes(sym));
    tr.classList.toggle('hidden', !show);
    if (show) vis++;
  }});
  document.getElementById('count').textContent = `Showing ${{vis}} of {len(rows)} setups`;
}}
function sortTable(col) {{
  if (sortCol === col) sortDir *= -1; else {{ sortCol = col; sortDir = -1; }}
  const tbody = document.getElementById('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {{
    const av = a.cells[col]?.textContent.trim().replace(/[₹$,]/g,'') || '';
    const bv = b.cells[col]?.textContent.trim().replace(/[₹$,]/g,'') || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
    return cmp * sortDir;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
applyFilters();
</script>
</body>
</html>"""
    return html_doc

def main():
    p = argparse.ArgumentParser(description="Generate master report from all LATEST scan outputs")
    p.add_argument("--output-dir",    default=str(ROOT / "output"))
    p.add_argument("--cache-dir",     default=str(ROOT / "cache"))
    p.add_argument("--account-size",  type=float, default=DEFAULT_ACCOUNT_SIZE)
    p.add_argument("--risk-pct",      type=float, default=DEFAULT_RISK_PCT)
    p.add_argument("--skip-fundamentals", action="store_true")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    cache_dir  = Path(args.cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═'*60}")
    print(f"  Master Report Generator")
    print(f"  Portfolio: ₹{args.account_size:,.0f}  Risk: {args.risk_pct*100:.0f}%/trade")
    print(f"  Output dir: {output_dir}")
    print(f"{'═'*60}\n")

    html_content = build_master_report(
        output_dir=output_dir,
        account_size=args.account_size,
        risk_pct=args.risk_pct,
        cache_dir=cache_dir,
        skip_fundamentals=args.skip_fundamentals,
    )

    out_path = output_dir / "master_report_LATEST.html"
    out_path.write_text(html_content, encoding="utf-8")
    print(f"\n  ✅ Master report written → {out_path.resolve()}")
    print(f"  Open in browser: file://{out_path.resolve()}")


if __name__ == "__main__":
    main()

