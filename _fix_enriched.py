#!/usr/bin/env python3
"""Fix garbled basic_industry values in both enriched and taxonomy CSVs."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for fname in ["data/nse_stock_enriched.csv", "data/nse_stock_taxonomy.csv"]:
    fpath = ROOT / fname
    if not fpath.exists():
        continue
    rows = []
    fixed = 0
    with open(fpath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            bi = row.get("basic_industry", "")
            if bi and "Dealers" in bi:
                is_ascii = all(ord(c) < 128 for c in bi)
                if not is_ascii or "\ufffd" in bi:
                    row["basic_industry"] = "Auto Dealer"
                    fixed += 1
            rows.append(row)
    with open(fpath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{fname}: fixed {fixed} garbled rows")

