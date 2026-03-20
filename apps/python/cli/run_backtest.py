#!/usr/bin/env python3
"""
run_backtest.py
───────────────
Replays 2-year historical breakout signals across Indian (or US) markets and
produces an interactive HTML performance report.

The Java BacktestEngine walks every historical bar in the lookback window,
fires the same VCP/Range-Expansion detector at each bar, and simulates the
trade forward until: T1/T2/T3 hit, stop hit, or max-hold reached.

Usage:
    python3 apps/python/cli/run_backtest.py                               # India daily, 728 bars
    python3 apps/python/cli/run_backtest.py --market india --timeframe weekly
    python3 apps/python/cli/run_backtest.py --market us   --timeframe daily
    python3 apps/python/cli/run_backtest.py --market india --hold-bars 30 --setups vcp
"""

import argparse, csv, html, json, os, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_DAILY_LOOKBACK  = 728   # ~2 years of daily bars
DEFAULT_WEEKLY_LOOKBACK = 104   # ~2 years of weekly bars
DEFAULT_HOLD_BARS_DAILY  = 20
DEFAULT_HOLD_BARS_WEEKLY = 8
DEFAULT_WORKERS = 4
DEFAULT_BATCH   = 20
JAVA_TIMEOUT    = 300
CACHE_TTL       = 9999          # never re-fetch during backtest run

INDIA_CSV = ROOT / "data" / "universes" / "indian_stock_tickers.csv"
US_CSV    = ROOT / "data" / "universes" / "us_stock_tickers.csv"
YAHOO_SUFFIXES = (".NS", ".BO")

lock = threading.Lock()


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="2-year historical backtest")
    p.add_argument("--market",    choices=["india", "us"], default="india")
    p.add_argument("--timeframe", choices=["daily", "weekly"], default="daily")
    p.add_argument("--matrix-all", action="store_true",
                   help="Run backtests for all four groups: us/india x daily/weekly")
    p.add_argument("--setups",    choices=["both", "vcp", "range_expansion"], default="both")
    p.add_argument("--lookback",  type=int, default=None,
                   help="Lookback bars (default: 728 daily / 104 weekly)")
    p.add_argument("--hold-bars", type=int, default=None,
                   help="Max hold bars before time-exit (default: 20 daily / 8 weekly)")
    p.add_argument("--workers",   type=int, default=DEFAULT_WORKERS)
    p.add_argument("--batch",     type=int, default=DEFAULT_BATCH)
    p.add_argument("--cache-dir", default=str(ROOT / "cache"))
    p.add_argument("--output-dir", default=str(ROOT / "output"))
    args = p.parse_args()
    return args


def effective_lookback(timeframe: str, override: int | None) -> int:
    if override is not None:
        return override
    return DEFAULT_DAILY_LOOKBACK if timeframe == "daily" else DEFAULT_WEEKLY_LOOKBACK


def effective_hold_bars(timeframe: str, override: int | None) -> int:
    if override is not None:
        return override
    return DEFAULT_HOLD_BARS_DAILY if timeframe == "daily" else DEFAULT_HOLD_BARS_WEEKLY


# ── Symbol loading ────────────────────────────────────────────────────────────
def load_symbols(market: str) -> list[str]:
    path = INDIA_CSV if market == "india" else US_CSV
    symbols, seen = [], set()
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw = (
                row.get("SYMBOL")
                or row.get("symbol")
                or row.get("Symbol")
                or row.get("ticker_symbol")
                or row.get("ticker")
                or ""
            ).strip().upper()
            series = (row.get("SERIES") or row.get(" SERIES") or "").strip().upper()
            company_name = (row.get("company_name") or row.get("name") or "").strip().lower()
            if not raw:
                continue
            if market == "india":
                if series and series not in {"EQ", "SM", "ST"}:
                    continue
                sym = raw + ".NS" if not any(raw.endswith(s) for s in YAHOO_SUFFIXES) else raw
            else:
                # Keep US backtest universe focused on common stock symbols.
                if company_name and any(k in company_name for k in ("warrant", "rights", "unit", "preferred", "etf", "fund", "trust")):
                    continue
                sym = raw
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return symbols


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ── Java batch runner ─────────────────────────────────────────────────────────
def run_batch(
    batch_syms: list[str],
    batch_num: int,
    timeframe: str,
    lookback: int,
    hold_bars: int,
    setups: str,
    cache_dir: str,
    work_dir: Path,
) -> Path | None:
    out_prefix = str(work_dir / f"batch_{batch_num:04d}")
    cmd = [
        "java", "-cp", "src", "Main",
        "--mode=backtest",
        "--provider=yahoo",
        f"--timeframe={timeframe}",
        f"--symbols={','.join(batch_syms)}",
        f"--lookback={lookback}",
        f"--cache-dir={cache_dir}",
        f"--cache-ttl-min={CACHE_TTL}",
        f"--setups={setups}",
        "--export=json",
        f"--out={out_prefix}",
        f"--backtest-hold-days={hold_bars}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=JAVA_TIMEOUT, cwd=ROOT)
        if proc.returncode != 0:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    json_path = Path(out_prefix + "_backtest.json")
    return json_path if json_path.exists() else None


# ── Aggregation ───────────────────────────────────────────────────────────────
def aggregate(json_paths: list[Path]) -> tuple[int, list[dict]]:
    total_signals = 0
    all_trades: list[dict] = []
    for p in json_paths:
        if p is None:
            continue
        try:
            data = json.loads(p.read_text())
            total_signals += data.get("signals", 0)
            all_trades.extend(data.get("items", []))
        except Exception:
            pass
    return total_signals, all_trades


# ── Metrics ───────────────────────────────────────────────────────────────────
def compute_metrics(trades: list[dict], signals: int) -> dict:
    if not trades:
        return {}

    n       = len(trades)
    rs      = [t["rMultiple"] for t in trades]
    wins    = [r for r in rs if r > 0]
    losses  = [r for r in rs if r <= 0]
    total_r = sum(rs)
    pos_r   = sum(wins)
    neg_r   = abs(sum(losses))

    # Drawdown
    peak, cum_r, max_dd = 0.0, 0.0, 0.0
    cumulative_r = []
    for r in rs:
        cum_r += r
        cumulative_r.append(round(cum_r, 4))
        if cum_r > peak:
            peak = cum_r
        dd = cum_r - peak
        if dd < max_dd:
            max_dd = dd

    # Monthly net R
    monthly: dict[str, float] = {}
    for t in trades:
        ym = str(t.get("entryDate", ""))[:7]
        monthly[ym] = monthly.get(ym, 0.0) + t["rMultiple"]

    # Group metrics helper
    def group_stats(key: str) -> dict:
        g: dict[str, list] = {}
        for t in trades:
            k = str(t.get(key, "?"))
            g.setdefault(k, []).append(t["rMultiple"])
        return {
            k: {
                "trades": len(v),
                "wins":   sum(1 for r in v if r > 0),
                "winRate": round(sum(1 for r in v if r > 0) / len(v) * 100, 1),
                "avgR":   round(sum(v) / len(v), 3),
                "totalR": round(sum(v), 3),
            }
            for k, v in sorted(g.items())
        }

    exit_counts: dict[str, int] = {}
    for t in trades:
        r = t.get("exitReason", "?")
        exit_counts[r] = exit_counts.get(r, 0) + 1

    return {
        "signals":      signals,
        "trades":       n,
        "wins":         len(wins),
        "losses":       len(losses),
        "winRate":      round(len(wins) / n * 100, 1) if n else 0,
        "avgR":         round(total_r / n, 3) if n else 0,
        "totalR":       round(total_r, 2),
        "maxDrawdown":  round(max_dd, 3),
        "profitFactor": round(pos_r / neg_r, 2) if neg_r > 0 else 99.0,
        "avgMae":       round(sum(t["mae"] for t in trades) / n, 2),
        "avgMfe":       round(sum(t["mfe"] for t in trades) / n, 2),
        "avgHoldBars":  round(sum(t["holdBars"] for t in trades) / n, 1),
        "t1HitRate":    round(sum(1 for t in trades if t.get("hitT1")) / n * 100, 1),
        "t2HitRate":    round(sum(1 for t in trades if t.get("hitT2")) / n * 100, 1),
        "t3HitRate":    round(sum(1 for t in trades if t.get("hitT3")) / n * 100, 1),
        "cumulativeR":  cumulative_r,
        "monthlyR":     monthly,
        "bySetup":      group_stats("setupType"),
        "byRating":     group_stats("setupRating"),
        "byWindow":     group_stats("windowLabel"),
        "exitReasons":  exit_counts,
    }


# ── HTML report ───────────────────────────────────────────────────────────────
def build_cumulative_svg(cum_r: list[float], width=700, height=160) -> str:
    if not cum_r:
        return "<p style='color:#8b949e'>No trades.</p>"
    mn, mx = min(cum_r), max(cum_r)
    span = mx - mn if mx != mn else 1.0
    pad = 10
    w, h = width - 2 * pad, height - 2 * pad
    pts = []
    for i, v in enumerate(cum_r):
        x = pad + i / max(len(cum_r) - 1, 1) * w
        y = pad + (1 - (v - mn) / span) * h
        pts.append(f"{x:.1f},{y:.1f}")
    zero_y = pad + (1 - (0 - mn) / span) * h
    zero_y = max(pad, min(height - pad, zero_y))
    poly = " ".join(pts)
    color = "#3fb950" if cum_r[-1] >= 0 else "#f85149"
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{width-pad}" y2="{zero_y:.1f}" '
        f'stroke="#30363d" stroke-width="1" stroke-dasharray="4,4"/>'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<circle cx="{width-pad}" cy="{pts[-1].split(",")[1]}" r="4" fill="{color}"/>'
        f'</svg>'
    )


def build_monthly_heatmap(monthly: dict[str, float]) -> str:
    if not monthly:
        return ""
    sorted_months = sorted(monthly.keys())
    cells = ""
    for ym in sorted_months:
        v = monthly[ym]
        intensity = min(abs(v) / 5.0, 1.0)
        if v >= 0:
            r, g, b = int(35 * (1 - intensity)), int(180 * intensity + 80), int(35 * (1 - intensity))
        else:
            r, g, b = int(200 * intensity + 55), int(35 * (1 - intensity)), int(35 * (1 - intensity))
        bg = f"rgb({r},{g},{b})"
        label = f"{v:+.1f}R"
        cells += (
            f"<div class='hm-cell' style='background:{bg}' title='{ym}: {v:+.2f}R'>"
            f"<div class='hm-month'>{ym[2:]}</div>"
            f"<div class='hm-val'>{label}</div>"
            f"</div>\n"
        )
    return f"<div class='heatmap'>{cells}</div>"


def build_trade_reason(t: dict) -> str:
    """Build a short plain-text trade reasoning description for tooltip hover."""
    setup = t.get("setupType", "?")
    rating = t.get("setupRating", "?")
    window = t.get("windowLabel", "?")
    score = t.get("qualityScore", 0)
    entry_date = t.get("entryDate", "?")
    exit_date  = t.get("exitDate",  "?")
    entry = t.get("entryPrice", 0)
    exit_p = t.get("exitPrice", 0)
    stop  = t.get("stopPrice", 0)
    r     = t.get("rMultiple", 0)
    hold  = t.get("holdBars", 0)
    exit_reason = t.get("exitReason", "?")
    mae   = t.get("mae", 0)
    mfe   = t.get("mfe", 0)
    hit_t1 = t.get("hitT1", False)
    hit_t2 = t.get("hitT2", False)
    hit_t3 = t.get("hitT3", False)

    setup_desc = (
        "Volatility Contraction Pattern (VCP) — multiple tightening waves into pivot"
        if setup == "VCP"
        else "Range Expansion Breakout — narrow consolidation base followed by wide-range breakout candle"
    )

    targets_hit = ", ".join(
        t for t, h in [("T1 (1R)", hit_t1), ("T2 (2R)", hit_t2), ("T3 (3R)", hit_t3)] if h
    ) or "None"

    rr_label = "1:3 (3R)" if hit_t3 else ("1:2 (2R)" if hit_t2 else ("1:1 (1R)" if hit_t1 else f"1:{abs(r):.1f}"))

    lines = [
        f"Setup: {setup_desc}",
        f"Rating: {rating}  |  Window: {window}  |  Quality Score: {score:.1f}",
        f"Entry: {entry_date} @ {entry:.2f}  |  Stop: {stop:.2f}",
        f"Exit:  {exit_date} @ {exit_p:.2f}  ({exit_reason})",
        f"Result: {r:+.2f}R  |  Risk/Reward achieved: {rr_label}",
        f"Targets hit: {targets_hit}",
        f"Hold: {hold} bars  |  MAE: {mae:.1f}%  |  MFE: {mfe:.1f}%",
    ]
    return " &#10; ".join(lines)   # &#10; = newline in HTML title attribute


def bar_rows(group: dict, color="#58a6ff") -> str:
    if not group:
        return "<p style='color:#8b949e'>No data.</p>"
    max_t = max(v["trades"] for v in group.values()) or 1
    rows = ""
    for k, v in group.items():
        pct = v["trades"] / max_t * 100
        win_color = "#3fb950" if v["avgR"] >= 0 else "#f85149"
        rows += (
            f"<div class='brow'>"
            f"<span class='blabel'>{html.escape(str(k))}</span>"
            f"<div class='bbar'><div class='bfill' style='width:{pct:.0f}%;background:{color}'></div></div>"
            f"<span class='bstat'>{v['trades']}T "
            f"<span style='color:{win_color}'>{v['winRate']}%W "
            f"avgR {v['avgR']:+.2f}</span></span>"
            f"</div>\n"
        )
    return rows


def rating_badge(r: str) -> str:
    css_map = {"A+":"rating-a-plus","A":"rating-a","B":"rating-b","C":"rating-c","D":"rating-d"}
    css = css_map.get(r.upper(), "rating-na")
    return f"<span class='rb {css}'>{html.escape(r)}</span>"


def rcolor(r: float) -> str:
    if r >= 2.0:  return "#2ea043"
    if r >= 1.0:  return "#3fb950"
    if r >= 0.0:  return "#7ee787"
    if r >= -0.5: return "#f0883e"
    return "#f85149"


def build_trade_rows(trades: list[dict]) -> str:
    rows = ""
    for t in trades:
        r = t.get("rMultiple", 0)
        rc = rcolor(r)
        rb = rating_badge(t.get("setupRating", "?"))
        hit_t1 = t.get("hitT1", False)
        hit_t2 = t.get("hitT2", False)
        hit_t3 = t.get("hitT3", False)
        t1 = "✅" if hit_t1 else "—"
        t2 = "✅" if hit_t2 else "—"
        t3 = "✅" if hit_t3 else "—"
        er = html.escape(t.get("exitReason", "?"))

        # RR badge: highlight 1:2 and 1:3
        if hit_t3:
            rr_badge = "<span style='background:#2ea04330;color:#3fb950;padding:1px 6px;border-radius:999px;border:1px solid #2ea043;font-size:.78em;font-weight:700'>1:3</span>"
        elif hit_t2:
            rr_badge = "<span style='background:#1f6feb30;color:#58a6ff;padding:1px 6px;border-radius:999px;border:1px solid #1f6feb;font-size:.78em;font-weight:700'>1:2</span>"
        else:
            rr_badge = "<span style='color:#8b949e;font-size:.78em'>—</span>"

        reason = build_trade_reason(t)

        rows += (
            f"<tr data-r='{r:.3f}' data-setup='{html.escape(t.get('setupType',''))}' "
            f"data-rating='{html.escape(t.get('setupRating',''))}' "
            f"data-symbol='{html.escape(t.get('symbol',''))}'>"
            f"<td><b>{html.escape(t.get('symbol',''))}</b></td>"
            f"<td>{html.escape(t.get('entryDate',''))}</td>"
            f"<td>{html.escape(t.get('exitDate',''))}</td>"
            f"<td>{html.escape(t.get('setupType',''))}</td>"
            f"<td>{rb}</td>"
            f"<td>{html.escape(t.get('windowLabel',''))}</td>"
            f"<td>{t.get('qualityScore',0):.1f}</td>"
            f"<td>{t.get('entryPrice',0):.2f}</td>"
            f"<td>{t.get('exitPrice',0):.2f}</td>"
            f"<td style='color:{rc};font-weight:700'>{r:+.2f}R</td>"
            f"<td>{rr_badge}</td>"
            f"<td>{t.get('holdBars',0)}</td>"
            f"<td>{t.get('mae',0):.1f}%</td>"
            f"<td>{t.get('mfe',0):.1f}%</td>"
            f"<td>{t1}</td><td>{t2}</td><td>{t3}</td>"
            f"<td style='color:#8b949e;font-size:.8em'>{er}</td>"
            f"<td style='text-align:center'>"
            f"<span class='reason-icon' title='{reason}' style='cursor:help;font-size:1.1em'>💡</span>"
            f"</td>"
            f"</tr>\n"
        )
    return rows


def save_html(m: dict, trades: list[dict], args, path: Path):
    title = f"Backtest — India {args.timeframe.title()}" if args.market == "india" \
            else f"Backtest — US {args.timeframe.title()}"
    now   = datetime.now().isoformat(timespec="seconds")
    cum_svg  = build_cumulative_svg(m.get("cumulativeR", []))
    heatmap  = build_monthly_heatmap(m.get("monthlyR", {}))
    by_setup  = bar_rows(m.get("bySetup", {}), "#58a6ff")
    by_rating = bar_rows(m.get("byRating", {}), "#d29922")
    by_window = bar_rows(m.get("byWindow", {}), "#7ee787")
    exit_rows = bar_rows({k: {"trades": v, "winRate": 0, "avgR": 0}
                          for k, v in m.get("exitReasons", {}).items()}, "#f0883e")
    trade_rows = build_trade_rows(trades)
    n = m.get("trades", 0)
    t1r = f"{m.get('t1HitRate',0):.1f}%"
    t2r = f"{m.get('t2HitRate',0):.1f}%"
    t3r = f"{m.get('t3HitRate',0):.1f}%"
    dd_color = "#f85149" if m.get("maxDrawdown",0) < 0 else "#7ee787"
    pf_color = "#3fb950" if m.get("profitFactor",0) >= 1.5 else ("#d29922" if m.get("profitFactor",0) >= 1 else "#f85149")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    *{{box-sizing:border-box;}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#0d1117;color:#c9d1d9;margin:0;padding:24px;}}
    h1{{color:#58a6ff;margin:0 0 4px 0;font-size:1.8em;}}
    h2{{color:#79c0ff;font-size:1.05em;margin:24px 0 10px 0;border-bottom:1px solid #21262d;padding-bottom:6px;}}
    .meta{{color:#8b949e;font-size:0.88em;margin-bottom:20px;}}

    /* Stat cards */
    .cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:20px;}}
    .card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px;}}
    .card-label{{color:#8b949e;font-size:0.78em;margin-bottom:4px;}}
    .card-value{{font-size:1.5em;font-weight:700;}}
    .card-sub{{color:#8b949e;font-size:0.75em;margin-top:4px;}}

    /* Cumulative curve */
    .curve-wrap{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-bottom:20px;overflow-x:auto;}}

    /* Monthly heatmap */
    .heatmap{{display:flex;flex-wrap:wrap;gap:4px;}}
    .hm-cell{{width:54px;height:50px;border-radius:6px;display:flex;flex-direction:column;
              align-items:center;justify-content:center;cursor:default;}}
    .hm-month{{font-size:0.65em;color:#fff;opacity:.7;}}
    .hm-val{{font-size:0.75em;font-weight:700;color:#fff;}}

    /* Bar charts */
    .brow{{display:flex;gap:8px;align-items:center;margin-bottom:8px;}}
    .blabel{{width:110px;color:#8b949e;font-size:0.82em;text-align:right;flex-shrink:0;}}
    .bbar{{flex:1;height:18px;background:#0d1117;border-radius:3px;overflow:hidden;}}
    .bfill{{height:100%;border-radius:3px;transition:width .3s;}}
    .bstat{{width:200px;font-size:0.8em;color:#79c0ff;flex-shrink:0;}}

    /* Grid layout for breakdown panels */
    .grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:20px;}}
    .panel{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;}}
    .panel-title{{color:#79c0ff;font-weight:600;font-size:0.9em;margin-bottom:12px;}}

    /* T1/T2/T3 hit bar */
    .target-row{{display:flex;gap:12px;margin-bottom:20px;}}
    .target-card{{flex:1;background:#161b22;border:1px solid #21262d;border-radius:8px;
                  padding:12px;text-align:center;}}
    .target-label{{color:#8b949e;font-size:.8em;margin-bottom:6px;}}
    .target-val{{font-size:1.6em;font-weight:700;color:#58a6ff;}}
    .target-sub{{color:#8b949e;font-size:.75em;margin-top:4px;}}

    /* Controls */
    .controls{{display:flex;gap:12px;flex-wrap:wrap;align-items:center;
               background:#161b22;border:1px solid #21262d;border-radius:8px;
               padding:10px 14px;margin-bottom:12px;}}
    .ctrl-label{{color:#8b949e;font-size:.85em;font-weight:600;}}
    .ctrl-input{{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;
                 padding:5px 8px;border-radius:6px;font-size:.85em;}}
    .filter-btn{{padding:5px 10px;border:1px solid #30363d;border-radius:6px;
                 background:transparent;color:#58a6ff;cursor:pointer;font-size:.8em;}}
    .filter-btn.active{{background:#1f6feb;border-color:#58a6ff;}}
    .export-btn{{padding:5px 10px;border:1px solid #30363d;border-radius:6px;
                 background:transparent;color:#7ee787;cursor:pointer;font-size:.8em;}}

    /* Table */
    .table-wrap{{overflow-x:auto;border:1px solid #21262d;border-radius:8px;}}
    table{{border-collapse:collapse;width:100%;font-size:0.82em;min-width:1400px;}}
    th{{background:#161b22;color:#58a6ff;padding:8px 10px;position:sticky;top:0;
        text-align:right;cursor:pointer;user-select:none;border-bottom:1px solid #21262d;}}
    th:first-child{{text-align:left;}}
    th::after{{content:' ↕';font-size:.7em;opacity:.3;}}
    th.sort-asc::after{{content:' ↑';opacity:1;}}
    th.sort-desc::after{{content:' ↓';opacity:1;}}
    th:hover{{background:#1f6feb22;}}
    td{{padding:6px 10px;border-bottom:1px solid #21262d;text-align:right;}}
    td:first-child{{text-align:left;}}
    tr:hover td{{background:#161b22;}}
    tr.hidden{{display:none;}}
    .rb{{display:inline-block;min-width:28px;text-align:center;padding:2px 6px;
         border-radius:999px;font-weight:700;font-size:.75em;border:1px solid transparent;}}
    .rating-a-plus{{color:#2ea043;background:#23863633;border-color:#2ea04399;}}
    .rating-a{{color:#3fb950;background:#2ea0432b;border-color:#3fb95099;}}
    .rating-b{{color:#d29922;background:#9e6a032d;border-color:#d2992299;}}
    .rating-c{{color:#f0883e;background:#bc4c002d;border-color:#f0883e99;}}
    .rating-d{{color:#f85149;background:#da36332d;border-color:#f8514999;}}
    .rating-na{{color:#8b949e;background:#6e768133;border-color:#8b949e99;}}
    .row-count{{color:#8b949e;font-size:.85em;margin-top:8px;}}
    .reason-icon:hover{{opacity:.7;}}
    [title]{{position:relative;}}
  </style>
</head>
<body>
  <h1>🧪 {html.escape(title)}</h1>
  <div class="meta">
    Generated: {now} &nbsp;|&nbsp;
    Lookback: {args.lookback} bars &nbsp;|&nbsp;
    Max hold: {args.hold_bars} bars &nbsp;|&nbsp;
    Setups: {args.setups.upper()} &nbsp;|&nbsp;
    Symbols: {args.market.upper()}
  </div>

  <!-- ── Summary Cards ─────────────────────────────────────────────── -->
  <div class="cards">
    <div class="card">
      <div class="card-label">Signals Detected</div>
      <div class="card-value" style="color:#79c0ff">{m.get('signals',0):,}</div>
      <div class="card-sub">{n:,} trades simulated</div>
    </div>
    <div class="card">
      <div class="card-label">Win Rate</div>
      <div class="card-value" style="color:{'#3fb950' if m.get('winRate',0)>=50 else '#f0883e'}">{m.get('winRate',0):.1f}%</div>
      <div class="card-sub">{m.get('wins',0)}W / {m.get('losses',0)}L</div>
    </div>
    <div class="card">
      <div class="card-label">Avg R-Multiple</div>
      <div class="card-value" style="color:{'#3fb950' if m.get('avgR',0)>=0 else '#f85149'}">{m.get('avgR',0):+.3f}R</div>
      <div class="card-sub">per trade</div>
    </div>
    <div class="card">
      <div class="card-label">Total R</div>
      <div class="card-value" style="color:{'#3fb950' if m.get('totalR',0)>=0 else '#f85149'}">{m.get('totalR',0):+.1f}R</div>
      <div class="card-sub">cumulative</div>
    </div>
    <div class="card">
      <div class="card-label">Max Drawdown</div>
      <div class="card-value" style="color:{dd_color}">{m.get('maxDrawdown',0):.2f}R</div>
      <div class="card-sub">peak → trough</div>
    </div>
    <div class="card">
      <div class="card-label">Profit Factor</div>
      <div class="card-value" style="color:{pf_color}">{m.get('profitFactor',0):.2f}</div>
      <div class="card-sub">gross profit / loss</div>
    </div>
    <div class="card">
      <div class="card-label">Avg MAE</div>
      <div class="card-value" style="color:#f0883e">{m.get('avgMae',0):.1f}%</div>
      <div class="card-sub">max adverse excursion</div>
    </div>
    <div class="card">
      <div class="card-label">Avg MFE</div>
      <div class="card-value" style="color:#7ee787">{m.get('avgMfe',0):.1f}%</div>
      <div class="card-sub">max favorable excursion</div>
    </div>
    <div class="card">
      <div class="card-label">Avg Hold</div>
      <div class="card-value" style="color:#58a6ff">{m.get('avgHoldBars',0):.1f}</div>
      <div class="card-sub">bars per trade</div>
    </div>
  </div>

  <!-- ── Target Hit Rates ───────────────────────────────────────────── -->
  <h2>🎯 Target Milestone Hit Rates</h2>
  <div class="target-row">
    <div class="target-card">
      <div class="target-label">T1 Hit Rate (1R)</div>
      <div class="target-val">{t1r}</div>
      <div class="target-sub">{m.get('t1HitCount',0):,} trades reached T1</div>
    </div>
    <div class="target-card">
      <div class="target-label">T2 Hit Rate (2R)</div>
      <div class="target-val">{t2r}</div>
      <div class="target-sub">{m.get('t2HitCount',0):,} trades reached T2</div>
    </div>
    <div class="target-card">
      <div class="target-label">T3 Hit Rate (3R)</div>
      <div class="target-val">{t3r}</div>
      <div class="target-sub">{m.get('t3HitCount',0):,} trades reached T3</div>
    </div>
  </div>

  <!-- ── Cumulative R Curve ─────────────────────────────────────────── -->
  <h2>📈 Cumulative R Curve</h2>
  <div class="curve-wrap">{cum_svg}</div>

  <!-- ── Monthly Heatmap ───────────────────────────────────────────── -->
  <h2>📅 Monthly P&L Heatmap (net R per month)</h2>
  <div class="panel" style="margin-bottom:20px">{heatmap}</div>

  <!-- ── Breakdown Panels ──────────────────────────────────────────── -->
  <h2>📊 Breakdown Analysis</h2>
  <div class="grid3">
    <div class="panel">
      <div class="panel-title">By Setup Type</div>
      {by_setup}
    </div>
    <div class="panel">
      <div class="panel-title">By Setup Rating</div>
      {by_rating}
    </div>
    <div class="panel">
      <div class="panel-title">By Window</div>
      {by_window}
    </div>
    <div class="panel">
      <div class="panel-title">Exit Reason Distribution</div>
      {exit_rows}
    </div>
  </div>

  <!-- ── Trade-level Table ─────────────────────────────────────────── -->
  <h2>📋 Trade-Level Details</h2>
  <div class="panel" style="margin-bottom:12px">
    <div class="panel-title">🎯 1:2 / 1:3 Quality Trades</div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px">
      <div style="background:#161b22;border:1px solid #2ea043;border-radius:8px;padding:10px 18px;text-align:center">
        <div style="color:#8b949e;font-size:.78em">1:2 Trades (hit T2)</div>
        <div style="color:#58a6ff;font-size:1.5em;font-weight:700" id="t2CountCard">{m.get('t2HitCount',0):,}</div>
        <div style="color:#8b949e;font-size:.72em">{m.get('t2HitRate',0):.1f}% of trades</div>
      </div>
      <div style="background:#161b22;border:1px solid #3fb950;border-radius:8px;padding:10px 18px;text-align:center">
        <div style="color:#8b949e;font-size:.78em">1:3 Trades (hit T3)</div>
        <div style="color:#3fb950;font-size:1.5em;font-weight:700" id="t3CountCard">{m.get('t3HitCount',0):,}</div>
        <div style="color:#8b949e;font-size:.72em">{m.get('t3HitRate',0):.1f}% of trades</div>
      </div>
    </div>
    <div style="font-size:.82em;color:#8b949e;line-height:1.5;margin-top:10px">
      <b style="color:#c9d1d9">RR</b>: Risk/Reward achieved (1:2 = T2 hit, 1:3 = T3 hit). &nbsp;|&nbsp;
      <b style="color:#c9d1d9">💡 Reasoning</b>: Hover the icon to see setup details, entry logic, and outcome.
    </div>
  </div>
  <div class="controls">
    <span class="ctrl-label">Search:</span>
    <input class="ctrl-input" id="searchBox" placeholder="Symbol..." style="width:130px" autocomplete="off">
    <span class="ctrl-label">Min R:</span>
    <input class="ctrl-input" id="minR" type="number" step="0.5" value="-99" style="width:80px">
    <span class="ctrl-label">RR:</span>
    <div id="rrBtns" style="display:flex;gap:6px">
      <button class="filter-btn active" data-rr="all">All</button>
      <button class="filter-btn" data-rr="1:2">1:2+</button>
      <button class="filter-btn" data-rr="1:3">1:3</button>
    </div>
    <span class="ctrl-label">Setup:</span>
    <div id="setupBtns" style="display:flex;gap:6px">
      <button class="filter-btn active" data-setup="all">All</button>
      <button class="filter-btn" data-setup="VCP">VCP</button>
      <button class="filter-btn" data-setup="RANGE_EXPANSION">Range Exp</button>
    </div>
    <button class="export-btn" id="exportBtn">📥 Export CSV</button>
  </div>
  <div class="table-wrap">
    <table id="tradeTable">
      <thead>
        <tr>
          <th onclick="sortT(0)">Symbol</th>
          <th onclick="sortT(1)">Entry Date</th>
          <th onclick="sortT(2)">Exit Date</th>
          <th onclick="sortT(3)">Trade Setup</th>
          <th onclick="sortT(4)">Setup Rating</th>
          <th onclick="sortT(5)">Setup Window</th>
          <th onclick="sortT(6)">Quality Score</th>
          <th onclick="sortT(7)">Entry Price</th>
          <th onclick="sortT(8)">Exit Price</th>
          <th onclick="sortT(9)">R Multiple</th>
          <th onclick="sortT(10)">RR</th>
          <th onclick="sortT(11)">Hold Bars</th>
          <th onclick="sortT(12)">MAE (%)</th>
          <th onclick="sortT(13)">MFE (%)</th>
          <th>T1</th><th>T2</th><th>T3</th>
          <th onclick="sortT(17)">Exit Reason</th>
          <th>Reasoning</th>
        </tr>
      </thead>
      <tbody id="tradeBody">{trade_rows}</tbody>
    </table>
  </div>
  <div class="row-count">Showing <span id="visCount">{n}</span> of <span id="totCount">{n}</span> trades</div>

  <script>
    const allRows = Array.from(document.querySelectorAll('#tradeBody tr'));
    let sortState = {{col: null, asc: true}};

    document.getElementById('searchBox').addEventListener('input', applyFilters);
    document.getElementById('minR').addEventListener('input', applyFilters);

    document.querySelectorAll('#rrBtns .filter-btn').forEach(b => {{
      b.addEventListener('click', () => {{
        document.querySelectorAll('#rrBtns .filter-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active'); applyFilters();
      }});
    }});

    document.querySelectorAll('#setupBtns .filter-btn').forEach(b => {{
      b.addEventListener('click', () => {{
        document.querySelectorAll('#setupBtns .filter-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active'); applyFilters();
      }});
    }});

    function applyFilters() {{
      const search = document.getElementById('searchBox').value.toLowerCase();
      const minR   = parseFloat(document.getElementById('minR').value) || -99;
      const setup  = document.querySelector('#setupBtns .filter-btn.active').dataset.setup;
      const rr     = document.querySelector('#rrBtns .filter-btn.active').dataset.rr;
      let vis = 0;
      allRows.forEach(row => {{
        const sym   = row.dataset.symbol.toLowerCase();
        const r     = parseFloat(row.dataset.r);
        const st    = row.dataset.setup;
        const t2hit = row.cells[15] && row.cells[15].textContent.trim() === '✅';
        const t3hit = row.cells[16] && row.cells[16].textContent.trim() === '✅';
        let rrOk = true;
        if (rr === '1:2') rrOk = t2hit || t3hit;
        if (rr === '1:3') rrOk = t3hit;
        const ok = (!search || sym.includes(search))
                 && r >= minR
                 && (setup === 'all' || st === setup)
                 && rrOk;
        row.classList.toggle('hidden', !ok);
        if (ok) vis++;
      }});
      document.getElementById('visCount').textContent = vis;
    }}

    function sortT(col) {{
      const asc = sortState.col === col ? !sortState.asc : true;
      sortState = {{col, asc}};
      document.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      document.querySelectorAll('th')[col].classList.add(asc ? 'sort-asc' : 'sort-desc');
      const tbody = document.getElementById('tradeBody');
      const vis = Array.from(tbody.querySelectorAll('tr:not(.hidden)'));
      vis.sort((a, b) => {{
        const av = a.cells[col].textContent.trim();
        const bv = b.cells[col].textContent.trim();
        const an = parseFloat(av.replace(/[^\\d.+-]/g,''));
        const bn = parseFloat(bv.replace(/[^\\d.+-]/g,''));
        const cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
        return asc ? cmp : -cmp;
      }});
      vis.forEach(r => tbody.appendChild(r));
    }}

    document.getElementById('exportBtn').addEventListener('click', () => {{
      const vis = allRows.filter(r => !r.classList.contains('hidden'));
      if (!vis.length) {{ alert('No rows to export'); return; }}
      const headers = ['Symbol','EntryDate','ExitDate','Setup','Rating','Window',
                       'QualityScore','EntryPrice','ExitPrice','RMultiple','RR',
                       'HoldBars','MAEPercent','MFEPercent',
                       'HitT1','HitT2','HitT3','ExitReason'];
      let csv = headers.join(',') + '\\n';
      vis.forEach(row => {{
        const cols = Array.from(row.cells).slice(0,18).map(c => {{
          let t = c.textContent.trim().replace(/"/g, '""');
          return `"${{t}}"`;
        }});
        csv += cols.join(',') + '\\n';
      }});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], {{type:'text/csv'}}));
      a.download = 'backtest_trades.csv'; a.click();
    }});
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc)
    print(f"  HTML → {path.resolve()}")


# ── Progress bar ──────────────────────────────────────────────────────────────
def progress(done, total, width=40):
    pct  = done / total if total else 0
    fill = int(width * pct)
    bar  = "█" * fill + "░" * (width - fill)
    return f"[{bar}] {done}/{total} ({pct*100:.1f}%)"


def compile_java_sources():
    java_files = sorted(str(p) for p in (ROOT / "src").glob("*.java"))
    if not java_files:
        raise RuntimeError("No Java source files found under src/")
    print("\nCompiling Java sources for backtest...")
    proc = subprocess.run(["javac", *java_files], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "Java compilation failed").strip()
        raise RuntimeError(f"Java compilation failed: {msg[:500]}")


def run_single_backtest(args, market: str, timeframe: str) -> dict:
    lookback = effective_lookback(timeframe, args.lookback)
    hold_bars = effective_hold_bars(timeframe, args.hold_bars)
    symbols = load_symbols(market)
    if not symbols:
        raise RuntimeError(f"No symbols found for market={market}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    label = f"{market}_{timeframe}"
    out_dir = Path(args.output_dir) / f"backtest_{label}_{timestamp}"
    work_dir = out_dir / "batch_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    out_html = out_dir / f"backtest_{label}_{timestamp}.html"
    out_csv = out_dir / f"backtest_{label}_{timestamp}.csv"
    latest_h = Path(args.output_dir) / f"backtest_{label}_LATEST.html"
    latest_c = Path(args.output_dir) / f"backtest_{label}_LATEST.csv"

    batches = list(chunks(symbols, args.batch))
    total = len(symbols)

    print(f"\n{'═'*70}")
    print(f"  BACKTEST  {label.upper()}  ·  {total} symbols  ·  {len(batches)} batches")
    print(f"  Lookback: {lookback} bars  ·  Hold: {hold_bars} bars  ·  Setups: {args.setups}")
    print(f"  Workers: {args.workers}  ·  Batch: {args.batch}")
    print(f"  Output: {out_dir.resolve()}")
    print(f"{'═'*70}\n")

    done_count = 0
    json_paths: list[Path | None] = [None] * len(batches)
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                run_batch,
                batches[i],
                i,
                timeframe,
                lookback,
                hold_bars,
                args.setups,
                args.cache_dir,
                work_dir,
            ): i
            for i in range(len(batches))
        }
        for future in as_completed(futures):
            i = futures[future]
            res = future.result()
            json_paths[i] = res
            with lock:
                done_count += 1
                print(
                    f"\r  {progress(done_count, len(batches))}  "
                    f"ETA={timedelta(done_count, len(batches), start)}",
                    end="",
                    flush=True,
                )

    print()
    print("\n  Aggregating results...")
    total_signals, all_trades = aggregate(json_paths)
    successful_batches = sum(1 for p in json_paths if p is not None)
    if successful_batches == 0:
        raise RuntimeError(
            f"All Java backtest batches failed for {market}_{timeframe}. "
            "Verify Java compilation and data-provider connectivity."
        )
    metrics = compute_metrics(all_trades, total_signals)

    if all_trades:
        flat_keys = [
            "symbol",
            "setupType",
            "setupRating",
            "windowLabel",
            "qualityScore",
            "entryDate",
            "exitDate",
            "entryPrice",
            "exitPrice",
            "stopPrice",
            "rMultiple",
            "pnl",
            "holdBars",
            "mae",
            "mfe",
            "hitT1",
            "hitT2",
            "hitT3",
            "exitReason",
        ]
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=flat_keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_trades)
        shutil.copy(out_csv, latest_c)

    run_ctx = SimpleNamespace(
        market=market,
        timeframe=timeframe,
        lookback=lookback,
        hold_bars=hold_bars,
        setups=args.setups,
    )
    save_html(metrics, all_trades, run_ctx, out_html)
    shutil.copy(out_html, latest_h)

    elapsed = time.time() - start
    print(f"\n{'═'*70}")
    print(f"  BACKTEST COMPLETE  ·  Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s")
    print(f"  Signals : {metrics.get('signals',0):,}")
    print(f"  Trades  : {metrics.get('trades',0):,}")
    print(f"  Win Rate: {metrics.get('winRate',0):.1f}%")
    print(f"  Avg R   : {metrics.get('avgR',0):+.3f}R")
    print(f"  Total R : {metrics.get('totalR',0):+.1f}R")
    print(f"  Max DD  : {metrics.get('maxDrawdown',0):.2f}R")
    print(f"  Profit F: {metrics.get('profitFactor',0):.2f}")
    print(
        f"  T1/T2/T3: {metrics.get('t1HitRate',0):.1f}% / {metrics.get('t2HitRate',0):.1f}% / {metrics.get('t3HitRate',0):.1f}%"
    )
    print(f"{'═'*70}")
    print(f"  HTML → {latest_h.resolve()}")
    print(f"  CSV  → {latest_c.resolve()}")

    return {
        "market": market,
        "timeframe": timeframe,
        "lookback": lookback,
        "holdBars": hold_bars,
        "metrics": metrics,
        "latestHtml": str(latest_h),
        "latestCsv": str(latest_c),
    }


def write_matrix_summary(output_dir: Path, runs: list[dict]) -> tuple[Path, Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    md_path = output_dir / f"backtest_matrix_{ts}.md"
    html_path = output_dir / f"backtest_matrix_{ts}.html"
    latest_json = output_dir / "backtest_matrix_LATEST.json"
    latest_md = output_dir / "backtest_matrix_LATEST.md"
    latest_html = output_dir / "backtest_matrix_LATEST.html"

    lines = [
        "# Backtest Matrix Summary",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Runs: {len(runs)}",
        "",
        "| Market | Timeframe | Trades | Win Rate | Avg R | Total R | Max DD | Profit Factor | HTML | CSV |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in runs:
        m = r.get("metrics", {})
        lines.append(
            f"| {r['market']} | {r['timeframe']} | {m.get('trades',0)} | {m.get('winRate',0):.1f}% | {m.get('avgR',0):+.3f} | {m.get('totalR',0):+.1f} | {m.get('maxDrawdown',0):.2f} | {m.get('profitFactor',0):.2f} | `{r['latestHtml']}` | `{r['latestCsv']}` |"
        )
    md_path.write_text("\n".join(lines) + "\n")

    html_rows = ""
    for r in runs:
        m = r.get("metrics", {})
        html_rows += (
            f"<tr><td>{html.escape(r['market'].upper())}</td>"
            f"<td>{html.escape(r['timeframe'].title())}</td>"
            f"<td>{m.get('trades',0)}</td>"
            f"<td>{m.get('winRate',0):.1f}%</td>"
            f"<td>{m.get('avgR',0):+.3f}</td>"
            f"<td>{m.get('totalR',0):+.1f}</td>"
            f"<td>{m.get('maxDrawdown',0):.2f}</td>"
            f"<td>{m.get('profitFactor',0):.2f}</td>"
            f"<td><a href='{html.escape(Path(r['latestHtml']).name)}'>{html.escape(Path(r['latestHtml']).name)}</a></td>"
            f"<td><a href='{html.escape(Path(r['latestCsv']).name)}'>{html.escape(Path(r['latestCsv']).name)}</a></td></tr>\n"
        )
    html_doc = f"""<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Backtest Matrix Summary</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:24px}}h1{{color:#58a6ff}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #30363d;padding:8px 10px;text-align:right}}th:first-child,td:first-child{{text-align:left}}th{{background:#161b22;color:#79c0ff}}a{{color:#58a6ff}}</style>
</head><body><h1>Backtest Matrix Summary</h1><p>Generated {datetime.now().isoformat(timespec='seconds')}</p>
<table><thead><tr><th>Market</th><th>Timeframe</th><th>Trades</th><th>Win Rate</th><th>Avg R</th><th>Total R</th><th>Max DD</th><th>Profit Factor</th><th>HTML</th><th>CSV</th></tr></thead><tbody>{html_rows}</tbody></table>
</body></html>"""
    html_path.write_text(html_doc)

    latest_md.write_text(md_path.read_text())
    latest_html.write_text(html_path.read_text())
    latest_json.write_text(json.dumps({"generatedAt": datetime.now().isoformat(timespec="seconds"), "runs": runs}, indent=2))
    return latest_md, latest_html, latest_json


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    compile_java_sources()

    if args.matrix_all:
        combos = [
            ("us", "daily"),
            ("us", "weekly"),
            ("india", "daily"),
            ("india", "weekly"),
        ]
        runs = [run_single_backtest(args, market, timeframe) for market, timeframe in combos]
        latest_md, latest_html, latest_json = write_matrix_summary(Path(args.output_dir), runs)
        print(f"\nMatrix summary markdown: {latest_md.resolve()}")
        print(f"Matrix summary html    : {latest_html.resolve()}")
        print(f"Matrix summary json    : {latest_json.resolve()}")
        return

    run_single_backtest(args, args.market, args.timeframe)


def timedelta(done, total, start):
    elapsed = time.time() - start
    if done == 0:
        return "?"
    eta = elapsed / done * (total - done)
    return f"{int(eta//60)}m{int(eta%60)}s"


if __name__ == "__main__":
    main()

