#!/usr/bin/env python3
"""Refresh industry-group / sector performance tables from the current taxonomy.

Reads:
  - data/nse_stock_taxonomy.csv   (authoritative sector/industry mapping)
  - cache/<TICKER>.NS.csv         (daily OHLC cache)

For a given [start, end] window (defaults: Feb 1 → Feb 28 2026), computes:
  - per-ticker % return using last close on/before start vs last close on/before end
  - per-industry aggregates (count, avg % return)
  - per-sector  aggregates (count, avg % return, winners/total)

Writes:
  - output/industry_performance_<tag>.csv
  - output/sector_performance_<tag>.csv
  - output/industry_performance_<tag>.md   (markdown block ready to paste)

Usage:
  python scripts/refresh_industry_performance.py
  python scripts/refresh_industry_performance.py --start 2026-03-01 --end 2026-03-31 --tag mar_2026
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "data" / "nse_stock_taxonomy.csv"
CACHE = ROOT / "cache"
OUTDIR = ROOT / "output"


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_taxonomy() -> dict[str, tuple[str, str]]:
    m: dict[str, tuple[str, str]] = {}
    with TAXONOMY.open() as f:
        r = csv.DictReader(f)
        for row in r:
            t = (row.get("nse_ticker") or "").strip().upper()
            s = (row.get("sector") or "").strip()
            i = (row.get("industry") or "").strip()
            if t and s and i:
                m[t] = (s, i)
    return m


def window_return(csv_path: Path, start: date, end: date) -> float | None:
    """Return pct change between last close <= start and last close <= end."""
    start_close: float | None = None
    end_close: float | None = None
    try:
        with csv_path.open() as f:
            r = csv.DictReader(f)
            for row in r:
                ds = row.get("date")
                cs = row.get("close")
                if not ds or not cs:
                    continue
                try:
                    d = datetime.strptime(ds, "%Y-%m-%d").date()
                    c = float(cs)
                except ValueError:
                    continue
                if d <= start:
                    start_close = c
                if d <= end:
                    end_close = c
                if d > end:
                    break
    except FileNotFoundError:
        return None
    if start_close is None or end_close is None or start_close <= 0:
        return None
    # Require start_close to be *before* end_close trading-wise (different days)
    if start_close == end_close:
        # could still be legit if flat, but more likely missing data around start
        pass
    return (end_close / start_close - 1.0) * 100.0


def fmt_pct(x: float) -> str:
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-02-28")
    ap.add_argument("--tag", default=None, help="output filename tag (default derived from window)")
    ap.add_argument("--min-industry-count", type=int, default=3,
                    help="minimum # tickers per industry to appear in hot/cold tables")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)
    tag = args.tag or f"{start.strftime('%b_%Y').lower()}"

    OUTDIR.mkdir(parents=True, exist_ok=True)

    tax = load_taxonomy()
    print(f"[info] taxonomy entries: {len(tax)}", file=sys.stderr)

    # Per-ticker returns
    rows: list[dict] = []
    missing_cache = 0
    for ticker, (sector, industry) in tax.items():
        # NS tickers are stored with .NS suffix in cache; US tickers without
        candidates = [CACHE / f"{ticker}.NS.csv", CACHE / f"{ticker}.csv"]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            missing_cache += 1
            continue
        ret = window_return(path, start, end)
        if ret is None:
            continue
        rows.append({
            "ticker": ticker,
            "sector": sector,
            "industry": industry,
            "return_pct": ret,
        })

    print(f"[info] tickers with returns: {len(rows)} (missing cache: {missing_cache})", file=sys.stderr)

    # Aggregate by industry
    by_ind: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_sec: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_ind[(r["sector"], r["industry"])].append(r["return_pct"])
        by_sec[r["sector"]].append(r["return_pct"])

    ind_summary = [
        {"sector": s, "industry": i, "count": len(v), "avg_pct": mean(v)}
        for (s, i), v in by_ind.items()
    ]
    ind_summary.sort(key=lambda x: x["avg_pct"], reverse=True)

    sec_summary = [
        {
            "sector": s,
            "count": len(v),
            "avg_pct": mean(v),
            "winners": sum(1 for x in v if x > 0),
        }
        for s, v in by_sec.items()
    ]
    sec_summary.sort(key=lambda x: x["avg_pct"], reverse=True)

    # Write CSVs
    ind_csv = OUTDIR / f"industry_performance_{tag}.csv"
    with ind_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sector", "industry", "count", "avg_pct"])
        w.writeheader()
        for row in ind_summary:
            w.writerow({**row, "avg_pct": f"{row['avg_pct']:.2f}"})

    sec_csv = OUTDIR / f"sector_performance_{tag}.csv"
    with sec_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sector", "count", "avg_pct", "winners"])
        w.writeheader()
        for row in sec_summary:
            w.writerow({**row, "avg_pct": f"{row['avg_pct']:.2f}"})

    # Markdown block
    md_lines: list[str] = []
    md_lines.append(f"<!-- Regenerated {datetime.now().strftime('%Y-%m-%d %H:%M')} "
                    f"window={start}..{end} universe={len(rows)} stocks -->")
    md_lines.append("## 🏭 Industry Performance — Hot vs Cold")
    md_lines.append("")

    hot = [r for r in ind_summary if r["count"] >= args.min_industry_count][: args.top]
    cold = [r for r in reversed(ind_summary) if r["count"] >= args.min_industry_count][: args.top]

    md_lines.append(f"### 🔥 Top {args.top} Industries — Best Performers")
    md_lines.append("")
    md_lines.append("| Industry | # Stocks | Avg Month% |")
    md_lines.append("|---|---:|---:|")
    for r in hot:
        md_lines.append(f"| {r['industry']} | {r['count']} | {fmt_pct(r['avg_pct'])} |")
    md_lines.append("")

    md_lines.append(f"### ❄️ Bottom {args.top} Industries — Worst Performers")
    md_lines.append("")
    md_lines.append("| Industry | # Stocks | Avg Month% |")
    md_lines.append("|---|---:|---:|")
    for r in cold:
        md_lines.append(f"| {r['industry']} | {r['count']} | {fmt_pct(r['avg_pct'])} |")
    md_lines.append("")

    md_lines.append("### 📊 Sector Summary")
    md_lines.append("")
    md_lines.append("| Sector | # | Avg Month% | Winners |")
    md_lines.append("|---|---:|---:|---:|")
    for r in sec_summary:
        md_lines.append(
            f"| {r['sector']} | {r['count']} | {fmt_pct(r['avg_pct'])} | {r['winners']}/{r['count']} |"
        )
    md_lines.append("")

    md_path = OUTDIR / f"industry_performance_{tag}.md"
    md_path.write_text("\n".join(md_lines))

    # Stdout summary
    print(f"[ok] wrote {ind_csv}")
    print(f"[ok] wrote {sec_csv}")
    print(f"[ok] wrote {md_path}")
    print()
    print("Top 10 hot industries:")
    for r in hot[:10]:
        print(f"  {r['industry']:<35} {r['count']:>3}  {fmt_pct(r['avg_pct']):>7}")
    print()
    print("Bottom 10 cold industries:")
    for r in cold[:10]:
        print(f"  {r['industry']:<35} {r['count']:>3}  {fmt_pct(r['avg_pct']):>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

