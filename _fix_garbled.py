#!/usr/bin/env python3
"""Fix garbled basic_industry values in nse_stock_taxonomy.csv."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAXONOMY = ROOT / "data" / "nse_stock_taxonomy.csv"

rows = []
fixed = 0
with open(TAXONOMY, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        bi = row.get("basic_industry", "")
        # Detect garbled text: contains non-ASCII or replacement chars
        # The actual garbled value is "Dealers<garbage>Commercial Vehicles Tractors..."
        if bi and "Dealers" in bi:
            is_ascii = all(ord(c) < 128 for c in bi)
            if not is_ascii or "\ufffd" in bi:
                row["basic_industry"] = "Auto Dealer"
                fixed += 1
        rows.append(row)

with open(TAXONOMY, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Fixed {fixed} garbled rows")

# Verify
with open(TAXONOMY, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        bi = row.get("basic_industry", "")
        if not all(ord(c) < 128 for c in bi) and bi:
            print(f"  Still garbled: {row['nse_ticker']} -> {repr(bi)}")
print("Done")

