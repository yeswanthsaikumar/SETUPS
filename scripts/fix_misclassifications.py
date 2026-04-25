#!/usr/bin/env python3
"""
fix_misclassifications.py
Apply all fixes identified in audit_taxonomy.py:
  CAT-1 : 9 Telecom stocks moved from IT → Telecom
  CAT-2 : 3 Cable TV stocks moved from Consumer → Telecom
  CAT-3 : 1 Cables stock moved from Auto → Cables (APARINDS)
  CAT-4 : 1 Logistics stock moved from Internet → Shipping (DELHIVERY)
  CAT-5 : 1 Industry label fixed (AGANORA)
  CAT-7 : 20 "Other" stocks classified where known
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV  = ROOT / "data" / "nse_stock_taxonomy.csv"

# ─────────────────────────────────────────────────────────────────────────────
# Master fixes dict: ticker → (sector, industry)
# ─────────────────────────────────────────────────────────────────────────────
FIXES = {
    # CAT-1 — Telecom placed under IT
    "BHARTIARTL": ("Telecom", "Telecom Services"),
    "BIRLATELE":  ("Telecom", "Telecom Services"),
    "BSNL":       ("Telecom", "Telecom Services"),
    "GTLINFRA":   ("Telecom", "Telecom Infrastructure"),
    "IDEA":       ("Telecom", "Telecom Services"),
    "INDUS":      ("Telecom", "Telecom Infrastructure"),
    "RAILTEL":    ("Telecom", "Telecom Infrastructure"),
    "TATACOMM":   ("Telecom", "Telecom Services"),
    "TTML":       ("Telecom", "Telecom Services"),

    # CAT-2 — Cable TV placed under Consumer
    "HATHWAY":    ("Telecom", "Cable TV & Broadband"),
    "GTPL":       ("Telecom", "Cable TV & Broadband"),
    "NXTDIGITAL": ("Telecom", "Cable TV"),

    # CAT-3 — Cables stock placed under Auto
    "APARINDS":   ("Cables", "Cables & Wires"),

    # CAT-4 — Logistics placed under Internet
    "DELHIVERY":  ("Shipping", "Logistics"),

    # CAT-5 — Industry label inconsistency (sector already correct)
    "AGANORA":    ("Pharma", "Pharma Formulations"),

    # CAT-7 — "Other" stocks classified based on known business activity
    # (only the ones that are identifiable with confidence)
    "AERONEU":    ("Defense",    "Aerospace & Defense"),   # Aeroneu Technologies
    "AVL":        ("Auto",       "Auto Ancillaries"),       # AVL India (auto testing)
    "DBOL":       ("Financials", "Capital Markets"),        # DB (international) Corp / holding
    "DCI":        ("Infra",      "Construction"),           # D.C. Infrastructures
    "GRMOVER":    ("Consumer",   "E-Commerce"),             # GRM Overseas / e-com related
    "JPOLYINVST": ("Financials", "Investment Companies"),   # J Poly Invest (investment vehicle)
    "LEMERITE":   ("Financials", "Investment Companies"),   # Le Merite Exports / holding
    "LGEINDIA":   ("Consumer",   "Consumer Electronics"),   # LG Electronics India
    "MEGASTAR":   ("Consumer",   "Entertainment"),          # Megastar Leisure
    "MWL":        ("Cap Goods",  "Engineering"),            # Manugraph / MW Luxury
    "NARMADA":    ("Chemicals",  "Specialty Chemicals"),    # Narmada Gelatines
    "NDLVENTURE": ("Financials", "Investment Companies"),   # NDL Ventures
    "PASHUPATI":  ("Textiles",   "Cotton / Agri"),          # Pashupati Cotspin
    "PRIVISCL":   ("Financials", "Investment Companies"),   # Privi Speciality Chemicals (holding)
    "SAKAR":      ("Pharma",     "Pharma Formulations"),    # Sakar Healthcare
    "SBC":        ("Financials", "Investment Companies"),   # SBC Exports / holding
    "SGMART":     ("Agri",       "Agri Products"),          # Sagar Mart (agri commodities)
    "SOUTHWEST":  ("Consumer",   "Aviation"),               # Southwest Air (if listed)
    "STAR":       ("Infra",      "Cement"),                 # Star Cement (NE India)
    "TEAMGTY":    ("Financials", "Investment Companies"),   # Team (GT) / holding co.
}

# ─────────────────────────────────────────────────────────────────────────────
# Apply fixes
# ─────────────────────────────────────────────────────────────────────────────
rows = []
changed = 0

with open(CSV, newline="", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    ti = header.index("nse_ticker")
    si = header.index("sector")
    ii = header.index("industry")
    rows.append(header)
    for row in reader:
        if not row:
            rows.append(row)
            continue
        ticker = row[ti].strip().upper()
        if ticker in FIXES:
            old_sec, old_ind = row[si], row[ii]
            new_sec, new_ind = FIXES[ticker]
            row[si] = new_sec
            row[ii] = new_ind
            changed += 1
            print(f"  FIXED  {ticker:<14} {old_sec}/{old_ind}  →  {new_sec}/{new_ind}")
        rows.append(row)

with open(CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerows(rows)

print(f"\n✅ Applied {changed} fixes to {CSV.name}")

