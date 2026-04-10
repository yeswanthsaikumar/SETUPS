#!/usr/bin/env python3
"""
Export current SECTOR_MAP + INDUSTRY_MAP to a CSV master file.
Run once to bootstrap the editable taxonomy CSV.

Usage:
    cd /Users/yeshwantha/IdeaProjects/SETUPS
    python3 scripts/export_taxonomy_to_csv.py
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "apps" / "python" / "cli" / "generate_trade_plans_page.py"
OUT  = ROOT / "data" / "nse_stock_taxonomy.csv"

# ── Extract maps from source ──────────────────────────────────────────────────
src = SRC.read_text()

sector_match   = re.search(r'SECTOR_MAP\s*=\s*\{(.+?)\n\}',   src, re.DOTALL)
industry_match = re.search(r'INDUSTRY_MAP\s*=\s*\{(.+?)\n\}', src, re.DOTALL)

if not sector_match or not industry_match:
    print("ERROR: Could not find SECTOR_MAP or INDUSTRY_MAP in source file")
    sys.exit(1)

ns: dict = {}
exec("SECTOR_MAP = {" + sector_match.group(1) + "\n}", ns)
exec("INDUSTRY_MAP = {" + industry_match.group(1) + "\n}", ns)

SECTOR_MAP:   dict[str, str] = ns["SECTOR_MAP"]
INDUSTRY_MAP: dict[str, str] = ns["INDUSTRY_MAP"]

# All tickers from both maps
all_tickers = sorted(set(SECTOR_MAP) | set(INDUSTRY_MAP))

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "nse_ticker",       # e.g. BHARATFORG (no .NS suffix)
        "sector",           # broad: Metals, IT, Pharma…
        "industry",         # sub-sector: Metal Forgings & Castings, IT Services…
        "notes",            # optional: why classified here, or if auto-classified
    ])
    for ticker in all_tickers:
        sector   = SECTOR_MAP.get(ticker, "Other")
        industry = INDUSTRY_MAP.get(ticker, SECTOR_MAP.get(ticker, "Other"))
        w.writerow([ticker, sector, industry, ""])

print(f"✅ Exported {len(all_tickers)} stocks to {OUT}")
print(f"   Sectors:    {len(set(SECTOR_MAP.values()))} unique")
print(f"   Industries: {len(set(INDUSTRY_MAP.values()))} unique")

