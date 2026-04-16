#!/usr/bin/env python3
"""
audit_taxonomy.py
Systematically audit nse_stock_taxonomy.csv for misclassifications.
"""
import csv
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
CSV  = ROOT / "data" / "nse_stock_taxonomy.csv"

with open(CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

taxonomy = {r["nse_ticker"]: r for r in rows}

sep = "=" * 70
print(sep)
print("  SYSTEMATIC MISCLASSIFICATION AUDIT — nse_stock_taxonomy.csv")
print(sep)

issues = []  # will collect (ticker, current_sec, current_ind, correct_sec, correct_ind, reason)

# ─────────────────────────────────────────────────────────────────────────────
# CAT-1: Telecom stocks wrongly placed under IT
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-1] Telecom operators/infrastructure incorrectly under IT:\n")
telecom_fixes = [
    ("BHARTIARTL", "Telecom", "Telecom Services"),
    ("BIRLATELE",  "Telecom", "Telecom Services"),
    ("BSNL",       "Telecom", "Telecom Services"),
    ("GTLINFRA",   "Telecom", "Telecom Infrastructure"),
    ("IDEA",       "Telecom", "Telecom Services"),
    ("INDUS",      "Telecom", "Telecom Infrastructure"),
    ("RAILTEL",    "Telecom", "Telecom Infrastructure"),
    ("TATACOMM",   "Telecom", "Telecom Services"),
    ("TTML",       "Telecom", "Telecom Services"),
]
for ticker, cs, ci in telecom_fixes:
    if ticker in taxonomy:
        r = taxonomy[ticker]
        cur = f"{r['sector']} / {r['industry']}"
        fix = f"{cs} / {ci}"
        ok  = r["sector"] == cs
        tag = "✅ OK" if ok else "❌ WRONG"
        print(f"  {tag:<12} {ticker:<14} {cur:<40} → {fix}")
        if not ok:
            issues.append((ticker, r["sector"], r["industry"], cs, ci, "Telecom placed under IT"))
    else:
        print(f"  [MISSING]    {ticker}")

# ─────────────────────────────────────────────────────────────────────────────
# CAT-2: Cable TV / Broadband under Consumer
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-2] Cable TV / Broadband operators incorrectly under Consumer:\n")
cabletv_fixes = [
    ("HATHWAY",    "Telecom", "Cable TV & Broadband"),
    ("GTPL",       "Telecom", "Cable TV & Broadband"),
    ("NXTDIGITAL", "Telecom", "Cable TV"),
]
for ticker, cs, ci in cabletv_fixes:
    if ticker in taxonomy:
        r = taxonomy[ticker]
        cur = f"{r['sector']} / {r['industry']}"
        fix = f"{cs} / {ci}"
        ok  = r["sector"] == cs
        tag = "✅ OK" if ok else "❌ WRONG"
        print(f"  {tag:<12} {ticker:<14} {cur:<40} → {fix}")
        if not ok:
            issues.append((ticker, r["sector"], r["industry"], cs, ci, "Cable TV placed under Consumer"))

# ─────────────────────────────────────────────────────────────────────────────
# CAT-3: APARINDS (Apar Industries — conductors & cables) under Auto
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-3] Cables & wires companies misplaced in Auto sector:\n")
cables_fixes = [
    ("APARINDS", "Cables", "Cables & Wires"),
]
for ticker, cs, ci in cables_fixes:
    if ticker in taxonomy:
        r = taxonomy[ticker]
        cur = f"{r['sector']} / {r['industry']}"
        fix = f"{cs} / {ci}"
        ok  = r["sector"] == cs
        tag = "✅ OK" if ok else "❌ WRONG"
        print(f"  {tag:<12} {ticker:<14} {cur:<40} → {fix}")
        if not ok:
            issues.append((ticker, r["sector"], r["industry"], cs, ci, "Cables stock placed under Auto"))

# ─────────────────────────────────────────────────────────────────────────────
# CAT-4: Logistics under Internet
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-4] Last-mile logistics companies under Internet sector:\n")
logistics_fixes = [
    ("DELHIVERY", "Shipping", "Logistics"),
]
for ticker, cs, ci in logistics_fixes:
    if ticker in taxonomy:
        r = taxonomy[ticker]
        cur = f"{r['sector']} / {r['industry']}"
        fix = f"{cs} / {ci}"
        ok  = r["sector"] == cs
        tag = "✅ OK" if ok else "❌ WRONG"
        print(f"  {tag:<12} {ticker:<14} {cur:<40} → {fix}")
        if not ok:
            issues.append((ticker, r["sector"], r["industry"], cs, ci, "Logistics placed under Internet"))

# ─────────────────────────────────────────────────────────────────────────────
# CAT-5: Industry-label inconsistencies (industry mismatch with sector)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-5] Industry label inconsistencies within existing sector:\n")
label_fixes = [
    # INFY and INFOSYS – both in IT, but INFY may be a stale duplicate ticker
    ("INFY",     "IT",  "IT Services",    "note: legacy ticker, prefer INFOSYS"),
    # AGANORA – Pharma/Formulations should be Pharma Formulations
    ("AGANORA",  "Pharma", "Pharma Formulations", "industry label normalised"),
    # APOLLOPIPES vs APOLLOPIPE — both exist with different industry labels
    ("APOLLOPIPE",  "Infra", "CPVC/PVC Pipes",   "normalise to Pipes & Fittings"),
    ("APOLLOPIPES", "Infra", "Pipes & Fittings",  "canonical entry"),
    # KPITTECH vs KPIT — both in IT
    ("KPITTECH",  "IT", "IT Services",  "note: stale ticker, prefer KPIT"),
    # NIITMTS / NIIT / NIITTECH — duplicated brands
    ("NIITMTS",   "IT", "IT Training",  "note: stale brand, may be delisted"),
    ("NIITTECH",  "IT", "IT Services",  "note: merged into Coforge"),
]
for ticker, cs, ci, note in label_fixes:
    if ticker in taxonomy:
        r = taxonomy[ticker]
        cur = f"{r['sector']} / {r['industry']}"
        fix = f"{cs} / {ci}"
        same = (r["sector"] == cs and r["industry"] == ci)
        tag = "✅ OK" if same else "⚠️  REVIEW"
        print(f"  {tag:<12} {ticker:<14} {cur:<40} ← {note}")

# ─────────────────────────────────────────────────────────────────────────────
# CAT-6: Duplicate tickers
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-6] Duplicate ticker entries:\n")
ticker_counts = Counter(r["nse_ticker"] for r in rows)
dups = {t: c for t, c in ticker_counts.items() if c > 1}
if dups:
    for t, c in sorted(dups.items()):
        entries = [(r["sector"], r["industry"]) for r in rows if r["nse_ticker"] == t]
        print(f"  ❌ DUPLICATE  {t} ({c}x): {entries}")
        issues.append((t, "", "", "", "", f"Duplicate entry x{c}"))
else:
    print("  ✅ No duplicates found.")

# ─────────────────────────────────────────────────────────────────────────────
# CAT-7: Unclassified "Other" stocks that can be resolved
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-7] Stocks stuck in 'Other' sector (need classification):\n")
other_stocks = [(r["nse_ticker"], r["industry"]) for r in rows if r["sector"] == "Other"]
for t, ind in sorted(other_stocks):
    print(f"  ⚠️  {t:<16} industry={ind}")

# ─────────────────────────────────────────────────────────────────────────────
# CAT-8: FINOLEX ticker disambiguation
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CAT-8] FINOLEX ticker disambiguation:\n")
finolex = [(r["nse_ticker"], r["sector"], r["industry"]) for r in rows if "FINOLEX" in r["nse_ticker"]]
for t, s, i in finolex:
    note = "Cables" if "CAB" in t else "Pipes" if "IND" in t else "check ticker"
    print(f"  {t:<18} {s}/{i}  ← {note}")

# ──────────────────────────────────────────────���──────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + sep)
print(f"  SUMMARY: {len(rows)} total stocks — {len(issues)} confirmed misclassifications")
print(sep)
print("\n  Confirmed fixes required:")
for ticker, cs, ci, ns, ni, reason in issues:
    print(f"    {ticker:<14} {cs}/{ci}  →  {ns}/{ni}  [{reason}]")

print()

