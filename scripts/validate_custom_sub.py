#!/usr/bin/env python3
"""Validate custom_sub_classification.csv against nse_stock_enriched.csv."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Load enriched tickers
valid = set()
empty = set()
with open(ROOT / "data/nse_stock_enriched.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        t = (row.get("nse_ticker") or "").strip().upper()
        sector = (row.get("sector") or "").strip()
        if t and sector:
            valid.add(t)
        elif t:
            empty.add(t)

# Load custom sub-classification tickers
custom_tickers = []
with open(ROOT / "data/custom_sub_classification.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        t = (row.get("nse_ticker") or "").strip().upper()
        if t and not t.startswith("#"):
            custom_tickers.append(t)

# Find issues
print("=== Tickers in custom_sub_classification with EMPTY/MISSING enriched data ===")
issues = []
for t in sorted(set(custom_tickers)):
    if t in empty:
        issues.append(t)
        print(f"  {t} (in enriched but no sector data)")
    elif t not in valid:
        issues.append(t)
        print(f"  {t} (NOT in enriched CSV at all)")

# Check duplicates
from collections import Counter
counts = Counter(custom_tickers)
dupes = {t: c for t, c in counts.items() if c > 1}
if dupes:
    print("\n=== DUPLICATE tickers (appears >1 time) ===")
    for t, c in sorted(dupes.items()):
        print(f"  {t}: {c} times")

print(f"\nTotal unique custom tickers: {len(set(custom_tickers))}")
print(f"Valid in enriched: {len(set(custom_tickers) - set(issues))}")
print(f"Empty/missing: {len(issues)}")

