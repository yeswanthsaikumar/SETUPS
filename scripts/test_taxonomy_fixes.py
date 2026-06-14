#!/usr/bin/env python3
"""Test that taxonomy fixes were applied correctly."""
import sys
sys.path.insert(0, "apps/python")

from lib.nse_taxonomy import get_basic_industry

tests = {
    "SWELECTES":  "Solar & Renewable Equipment",
    "EXICOM":     "EV Charging & Battery Tech",
    "WAAREEENER": "Solar & Renewable Equipment",
    "SAATVIKGL":  "Solar & Renewable Equipment",
    "ENRIN":      "Industrial Boilers & Engineering",
    "DIVISLAB":   "CDMO & API",
    "MUTHOOTCAP": "NBFC - Vehicle & Equipment Finance",
    "AARTIIND":   "Specialty Chemicals - Intermediates",
    "LAURUSLABS": "CDMO & API",
}

ok = 0
for t, expected in tests.items():
    actual = get_basic_industry(t)
    status = "OK" if actual == expected else "FAIL"
    if status == "FAIL":
        print(f"  {status}: {t} => {actual!r} (expected {expected!r})")
    else:
        ok += 1
        print(f"  {status}: {t} => {actual!r}")

print(f"\n{ok}/{len(tests)} passed")
if ok < len(tests):
    sys.exit(1)

