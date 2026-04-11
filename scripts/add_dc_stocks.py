#!/usr/bin/env python3
import csv
from pathlib import Path

CSV = Path(__file__).resolve().parents[1] / "data" / "nse_stock_taxonomy.csv"
rows = {}
with open(CSV) as f:
    for r in csv.DictReader(f):
        rows[r["nse_ticker"].strip().upper()] = dict(r)

adds = [
    ("CGPOWER", "Cap Goods", "Electrical Equipment"),
    ("NETWEB", "IT", "IT Services"),
    ("SANGHIIND", "Infra", "Cement"),
]
added = 0
for t, s, i in adds:
    if t not in rows:
        rows[t] = {"nse_ticker": t, "sector": s, "industry": i, "notes": ""}
        added += 1

sorted_rows = sorted(rows.values(), key=lambda r: r.get("nse_ticker", "").upper())
with open(CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["nse_ticker", "sector", "industry", "notes"])
    w.writeheader()
    w.writerows(sorted_rows)
print(f"Added {added}. Total: {len(sorted_rows)}")

