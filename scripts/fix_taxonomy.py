#!/usr/bin/env python3
"""Fix miscategorized stocks in the taxonomy CSV."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "data" / "nse_stock_taxonomy.csv"

fixes = {
    "AAVAS":     ("Financials", "Housing Finance"),
    "APTUS":     ("Financials", "Housing Finance"),
    "SUDARSCHEM":("Chemicals",  "Specialty Chemicals"),
    "DCMSHRIRAM":("Chemicals",  "Agri Chemicals & Fertilisers"),
}

rows = []
changed = 0

with open(path, newline="", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    # Find column indices
    ti = header.index("nse_ticker")
    si = header.index("sector")
    ii = header.index("industry")
    rows.append(header)
    for row in reader:
        if row and row[ti].strip().upper() in fixes:
            sec, ind = fixes[row[ti].strip().upper()]
            row[si] = sec
            row[ii] = ind
            changed += 1
        rows.append(row)

with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerows(rows)

print(f"Fixed {changed} entries in taxonomy CSV")

