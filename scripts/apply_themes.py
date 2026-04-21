#!/usr/bin/env python3
"""
apply_themes.py
───────────────
Merge the NSE-official 4-level industry taxonomy (from
data/nse_industry_taxonomy.csv) with curated thematic rules (from
data/themes.json) to produce two artefacts:

  1. data/nse_stock_enriched.csv
        Full 5-column enriched taxonomy per ticker:
        nse_ticker, company_name, macro, sector, industry, basic_industry,
        themes (semicolon-separated theme keys)

  2. data/stock_themes.csv
        Long-format membership table — one row per (ticker, theme).
        Useful for SQL-style analytics / debugging.

A single stock can belong to multiple themes.

Run:
    python scripts/apply_themes.py            # stdout summary
    python scripts/apply_themes.py --verbose  # print every (ticker,theme)

Themes layered on top of NSE's authoritative fields support RELATIVE-STRENGTH
and SECTOR-ROTATION analyses that cut across NSE's rigid industry buckets
(e.g. "EV" spans Auto, Batteries, and Electrical Equipment).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NSE_CSV   = ROOT / "data" / "nse_industry_taxonomy.csv"
THEMES_JSON = ROOT / "data" / "themes.json"
ENRICHED_CSV = ROOT / "data" / "nse_stock_enriched.csv"
STOCK_THEMES_CSV = ROOT / "data" / "stock_themes.csv"


def _matches_regex(value: str, patterns: list[str]) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    for p in patterns:
        if re.search(p, v, re.IGNORECASE):
            return True
    return False


def _load_themes() -> list[dict]:
    data = json.loads(THEMES_JSON.read_text(encoding="utf-8"))
    themes = data.get("themes", [])
    # Normalise each rule's fields into lists + pre-compile regex for name_regex
    normed = []
    for t in themes:
        spec = dict(t)
        for k in ("basic_industry", "industry", "sector", "macro"):
            v = spec.get(k)
            if isinstance(v, str):
                spec[k] = [v]
            elif not isinstance(v, list):
                spec[k] = []
        # Tickers may arrive as comma-separated string
        tickers = spec.get("ticker") or spec.get("tickers") or ""
        if isinstance(tickers, str):
            tickers = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        spec["ticker_set"] = set(tickers)
        nr = spec.get("name_regex")
        spec["name_regex_compiled"] = (
            re.compile(nr, re.IGNORECASE) if nr else None
        )
        normed.append(spec)
    return normed


def _row_matches_theme(row: dict, theme: dict) -> bool:
    t = (row.get("nse_ticker") or "").upper()
    if t and t in theme["ticker_set"]:
        return True
    for col in ("basic_industry", "industry", "sector", "macro"):
        patterns = theme.get(col) or []
        if patterns and _matches_regex(row.get(col, ""), patterns):
            return True
    nr = theme.get("name_regex_compiled")
    if nr and row.get("company_name") and nr.search(row["company_name"]):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not NSE_CSV.exists():
        print(f"❌ Missing {NSE_CSV} — run scripts/build_nse_industry_taxonomy.py first",
              file=sys.stderr)
        return 2
    if not THEMES_JSON.exists():
        print(f"❌ Missing {THEMES_JSON}", file=sys.stderr)
        return 2

    themes = _load_themes()
    print(f"Loaded {len(themes)} themes from {THEMES_JSON.name}")

    # Load NSE rich taxonomy
    rows: list[dict] = []
    with NSE_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"Loaded {len(rows)} tickers from {NSE_CSV.name}")

    # Match
    ticker_to_themes: dict[str, list[str]] = defaultdict(list)
    theme_to_tickers: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        sym = (row.get("nse_ticker") or "").upper()
        if not sym:
            continue
        for theme in themes:
            if _row_matches_theme(row, theme):
                ticker_to_themes[sym].append(theme["key"])
                theme_to_tickers[theme["key"]].append(sym)

    # Write enriched CSV (wide format)
    enriched_cols = ["nse_ticker", "company_name", "macro", "sector",
                     "industry", "basic_industry", "themes"]
    ENRICHED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with ENRICHED_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=enriched_cols)
        w.writeheader()
        for row in sorted(rows, key=lambda r: (r.get("nse_ticker") or "")):
            sym = (row.get("nse_ticker") or "").upper()
            w.writerow({
                "nse_ticker":     sym,
                "company_name":   row.get("company_name", ""),
                "macro":          row.get("macro", ""),
                "sector":         row.get("sector", ""),
                "industry":       row.get("industry", ""),
                "basic_industry": row.get("basic_industry", ""),
                "themes":         ";".join(ticker_to_themes.get(sym, [])),
            })
    print(f"✅ Wrote {ENRICHED_CSV.relative_to(ROOT)}")

    # Write long-format membership
    with STOCK_THEMES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nse_ticker", "theme_key", "theme_name"])
        theme_names = {t["key"]: t["name"] for t in themes}
        for sym in sorted(ticker_to_themes):
            for k in ticker_to_themes[sym]:
                w.writerow([sym, k, theme_names.get(k, k)])
    print(f"✅ Wrote {STOCK_THEMES_CSV.relative_to(ROOT)}")

    # Summary
    print("\nTheme membership counts:")
    for t in sorted(themes, key=lambda x: -len(theme_to_tickers.get(x["key"], []))):
        n = len(theme_to_tickers.get(t["key"], []))
        print(f"  {t['key']:<20} {t['name']:<35} {n:>4}")

    multi = sum(1 for v in ticker_to_themes.values() if len(v) > 1)
    mono = sum(1 for v in ticker_to_themes.values() if len(v) == 1)
    none = len(rows) - len(ticker_to_themes)
    print(f"\nTickers with ≥2 themes : {multi}")
    print(f"Tickers with  1 theme  : {mono}")
    print(f"Tickers with  0 themes : {none}")

    if args.verbose:
        print("\n(verbose) membership detail:")
        for sym in sorted(ticker_to_themes):
            print(f"  {sym}: {ticker_to_themes[sym]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

