#!/usr/bin/env python3
"""
export_maps_to_csv.py
─────────────────────
Exports the hardcoded SECTOR_MAP and INDUSTRY_MAP from generate_trade_plans_page.py
into the master nse_stock_taxonomy.csv, adding any tickers not already there.

Run: python3 scripts/export_maps_to_csv.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "python" / "cli"))
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))

CSV_PATH = ROOT / "data" / "nse_stock_taxonomy.csv"

try:
    from generate_trade_plans_page import SECTOR_MAP, INDUSTRY_MAP
    print(f"Loaded {len(SECTOR_MAP)} sector entries, {len(INDUSTRY_MAP)} industry entries from generate_trade_plans_page.py")
except Exception as e:
    print(f"Could not import from generate_trade_plans_page.py: {e}")
    sys.exit(1)

# Read existing CSV entries
existing: dict[str, dict] = {}
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        t = row.get("nse_ticker", "").strip().upper()
        if t:
            existing[t] = row

# Merge: add tickers that exist in the Python maps but not in CSV
added = 0
for ticker, sector in SECTOR_MAP.items():
    t = ticker.upper()
    if t not in existing:
        industry = INDUSTRY_MAP.get(ticker, sector)
        existing[t] = {
            "nse_ticker": ticker,
            "sector":     sector,
            "industry":   industry,
            "notes":      "auto-exported from generate_trade_plans_page.py",
        }
        added += 1

print(f"Added {added} new tickers from Python maps to CSV")

# Write back sorted by ticker
with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["nse_ticker", "sector", "industry", "notes"])
    w.writeheader()
    for row in sorted(existing.values(), key=lambda r: r["nse_ticker"].upper()):
        w.writerow(row)

print(f"✅ nse_stock_taxonomy.csv updated — {len(existing)} total entries")

