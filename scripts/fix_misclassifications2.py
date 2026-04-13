#!/usr/bin/env python3
"""
fix_misclassifications2.py
Fix known misclassifications in nse_stock_taxonomy.csv including:
  - VIMTALABS (Diagnostics/CRO, NOT electronic components)
  - BOROSIL (Scientific Glassware, NOT electronic components)
  - INOXINDIA (Cryogenic Equipment, NOT electronic components)
  - KRN (Heat Exchangers, NOT electronic components)
  - RAJESHEXPO (Jewellery, NOT electronics)
  - BHEL (Power Equipment, should be Cap Goods)
  - VOLTAMP (Transformers, should be Cap Goods)
  - Many more pharma, auto, consumer etc.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV  = ROOT / "data" / "nse_stock_taxonomy.csv"

FIXES = {
    # ── WRONG: Pharma/Diagnostics companies in Electronics ───────────────────
    "VIMTALABS":   ("Pharma", "CRO & Testing Labs"),        # Vimta Labs — clinical CRO, pharma testing labs
    "DIVI":        ("Pharma", "API & Bulk Drugs"),          # Divi's Laboratories — API manufacturer

    # ── WRONG: Industrial/Engg companies in Electronics ─────────────────────
    "BOROSIL":     ("Consumer", "Scientific Glassware"),    # Borosil — lab glass & cookware, not electronics
    "INOXINDIA":   ("Cap Goods", "Cryogenic Equipment"),    # Inox India — cryogenic tanks/equipment
    "KRN":         ("Cap Goods", "Heat Exchangers"),        # KRN Heat Exchanger — industrial heat mgmt
    "BHEL":        ("Cap Goods", "Power Equipment"),        # BHEL — power transformers, boilers, turbines
    "VOLTAMP":     ("Cap Goods", "Transformers"),           # Voltamp Transformers
    "TDPOWERSYS":  ("Cap Goods", "Power Systems"),          # TD Power Systems — motors, generators
    "AXISCADES":   ("IT", "Engineering Services"),          # Axiscades — IT/engineering design services
    "TEJAS":       ("Telecom", "Optical Networking"),       # Tejas Networks — telecom networking equipment

    # ── WRONG: Jewellery/Metals company in Electronics ───────────────────────
    "RAJESHEXPO":  ("Consumer", "Jewellery"),               # Rajesh Exports — gold jewellery exporter

    # ── WRONG: HALONIX — Lighting not Electronics ────────────────────────────
    "HALONIX":     ("Consumer", "Lighting & Fixtures"),     # Halonix — LED & lighting products

    # ── WRONG: Telecom companies in wrong sectors ─────────────────────────────
    "TATACOMM":    ("Telecom", "Telecom Services"),
    "RAILTEL":     ("Telecom", "Telecom Infrastructure"),
    "INDUS":       ("Telecom", "Telecom Infrastructure"),
    "GTLINFRA":    ("Telecom", "Telecom Infrastructure"),
    "HATHWAY":     ("Telecom", "Cable TV & Broadband"),
    "GTPL":        ("Telecom", "Cable TV & Broadband"),

    # ── WRONG: Power/Electrical companies misclassified ──────────────────────
    "POWERINDIA":  ("Cap Goods", "Electrical Equipment"),   # Hitachi Energy India (ex-ABB Power)
    "SCHNEIDER":   ("Cap Goods", "Electrical Equipment"),   # Schneider Electric India
    "ABB":         ("Cap Goods", "Automation & Drives"),    # ABB India
    "SIEMENS":     ("Cap Goods", "Automation & Drives"),    # Siemens India

    # ── WRONG: Consumer/FMCG misclassified ───────────────────────────────────
    "BAJAJELEC":   ("Consumer", "Consumer Electronics"),    # Bajaj Electricals — fans, lights, appliances
    "HAVELLS":     ("Cap Goods", "Electrical Equipment"),   # Havells — wires, switchgear, appliances
    "POLYCAB":     ("Cables", "Cables & Wires"),            # Polycab — cables and wires
    "KEI":         ("Cables", "Cables & Wires"),            # KEI Industries — cables
    "FINOLEX":     ("Cables", "Cables & Wires"),            # Finolex Cables
    "APARINDS":    ("Cables", "Cables & Wires"),            # APar Industries — cables

    # ── WRONG: Real estate companies misclassified ────────────────────────────
    "OBEROIRLTY":  ("RealEstate", "Residential RE"),        # Oberoi Realty
    "OBEROIREAL":  ("RealEstate", "Residential RE"),        # Oberoi Realty (alt ticker)

    # ── WRONG: Pharma companies in wrong sectors ──────────────────────────────
    "NATCOPHARMA": ("Pharma", "Formulations"),
    "ALKEM":       ("Pharma", "Formulations"),
    "TORNTPHARM":  ("Pharma", "Formulations"),
    "GRANULES":    ("Pharma", "API & Bulk Drugs"),
    "LAURUSLABS":  ("Pharma", "API & Bulk Drugs"),
    "NEULANDLAB":  ("Pharma", "API & Bulk Drugs"),

    # ── Fix: Sugar companies in wrong categories ───────────────────────────────
    "PRAJIND":     ("Sugar", "Ethanol & Sugar"),            # Praj Industries — ethanol plant tech
    "SHREERENUKA": ("Sugar", "Sugar"),                      # Shree Renuka Sugars

    # ── Fix: Logistics companies ──────────────────────────────────────────────
    "DELHIVERY":   ("Shipping", "Logistics"),               # Delhivery — express logistics
    "BLUEDART":    ("Shipping", "Express Logistics"),       # Blue Dart — express delivery
    "CONCOR":      ("Shipping", "Rail Logistics"),          # Container Corp — rail freight

    # ── Fix: Auto companies ───────────────────────────────────────────────────
    "BOSCH":       ("Auto", "Auto Ancillaries"),            # Bosch India
    "SCHAEFFLER":  ("Auto", "Bearings"),                    # Schaeffler India
    "SKFINDIA":    ("Auto", "Bearings"),                    # SKF India
    "TIMKEN":      ("Auto", "Bearings"),                    # Timken India
    "SONACOMS":    ("Auto", "Auto Ancillaries"),            # Sona BLW — auto components
    "BALKRISIND":  ("Auto", "Tyres"),                       # Balkrishna Industries
    "APOLLOTYRE":  ("Auto", "Tyres"),                       # Apollo Tyres
    "MRF":         ("Auto", "Tyres"),                       # MRF
    "CEATLTD":     ("Auto", "Tyres"),                       # CEAT

    # ── Fix: IT companies ─────────────────────────────────────────────────────
    "CYIENT":      ("IT", "Engineering Services"),          # Cyient — engineering & technology services
    "TATAELXSI":   ("IT", "Engineering Services"),          # Tata Elxsi — design & technology

    # ── Fix: Defense companies ────────────────────────────────────────────────
    "MIDHANI":     ("Defense", "Aerospace Alloys"),         # Mishra Dhatu Nigam — superalloys for aerospace
    "DATAPATTNS":  ("Defense", "Defense Electronics"),      # Data Patterns — defense electronics
    "IDEAFORGE":   ("Defense", "Drones"),                   # ideaForge — military drones
    "SOLARIND":    ("Defense", "Aerospace & Defense"),      # Solar Industries — defence explosives

    # ── Fix: Chemicals misclassified ──────────────────────────────────────────
    "NAVINFLUOR":  ("Chemicals", "Specialty Chemicals"),    # Navin Fluorine
    "DEEPAKNITR":  ("Chemicals", "Specialty Chemicals"),    # Deepak Nitrite
    "VINATI":      ("Chemicals", "Specialty Chemicals"),    # Vinati Organics
    "ATUL":        ("Chemicals", "Specialty Chemicals"),    # Atul Ltd
    "ROSSARI":     ("Chemicals", "Specialty Chemicals"),    # Rossari Biotech
    "ALKYLAMINE":  ("Chemicals", "Specialty Chemicals"),    # Alkyl Amines
    "FINEORG":     ("Chemicals", "Specialty Chemicals"),    # Fine Organics
    "PCBL":        ("Chemicals", "Carbon Black"),           # PCBL — carbon black
    "NEOGEN":      ("Chemicals", "Specialty Chemicals"),    # Neogen Chemicals

    # ── Fix: Banking/Finance ──────────────────────────────────────────────────
    "ABCAPITAL":   ("Financials", "NBFC"),                  # Aditya Birla Capital
    "PNBHOUSING":  ("Financials", "Housing Finance"),       # PNB Housing Finance
    "IBULHSGFIN":  ("Financials", "Housing Finance"),       # Indiabulls Housing Finance
    "HOMEFIRST":   ("Financials", "Housing Finance"),       # Home First Finance
    "BAJAJHFL":    ("Financials", "Housing Finance"),       # Bajaj Housing Finance
}

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
            print(f"  FIXED  {ticker:<16} {old_sec}/{old_ind}  →  {new_sec}/{new_ind}")
        rows.append(row)

with open(CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerows(rows)

print(f"\n✅ Applied {changed} fixes to {CSV.name}")

