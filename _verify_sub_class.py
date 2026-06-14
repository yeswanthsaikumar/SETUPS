#!/usr/bin/env python3
"""Verify custom sub-classifications are applied correctly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "python" / "lib"))
import nse_taxonomy as t

tests = {
    "ABB": "Electrical Equipments/HVDC",
    "SIEMENS": "Electrical Equipments/HVDC",
    "VOLTAMP": "Transformers & Switchgear",
    "SUZLON": "Wind Energy Equipment",
    "HINDLATAN": "Contraceptives/Protectives",
    "TTKHLTCARE": "Contraceptives/Protectives",
    "DENORA": "Electrodes - Welding Equipment",
    "HEG": "Graphite Electrodes",
    "GRAPHITE": "Graphite Electrodes",
    "POLYCAB": "Wires & Cables",
    "THERMAX": "Industrial Boilers & Engineering",
    "TRANSRAILL": "Power EPC & Towers",
    "SUNPHARMA": "Pharma - Large Cap Formulations",
    "DIVI": "CDMO & API",
    "APOLLOTYRE": "Tyres",
    "SCHAEFFLER": "Bearings",
}

print("Custom sub-classification verification:")
ok = 0
for sym, expected in tests.items():
    actual = t.get_basic_industry(sym)
    status = "OK" if actual == expected else "FAIL"
    if status == "OK":
        ok += 1
    print(f"  {sym:15s} -> {actual:40s} [{status}]")

print(f"\n{ok}/{len(tests)} passed")
print(f"\nUnique basic_industries now: {len(set(t._BASIC_INDUSTRY_MAP.values()))}")

