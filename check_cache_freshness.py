#!/usr/bin/env python3
"""Check cache freshness status for all NSE symbols."""
from pathlib import Path
import csv, datetime, math, zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
cache = Path("/Users/yeshwantha/IdeaProjects/SETUPS/cache")
today = datetime.datetime.now(IST).date()
cutoff = today - datetime.timedelta(days=5)

sym_best: dict[str, str] = {}
for p in sorted(cache.glob("*.NS_*.csv")):
    sym = p.name.split("_")[0]
    try:
        last = ""
        with open(p) as f:
            for row in csv.DictReader(f):
                d = row.get("date", "").strip()
                if not d:
                    continue
                # Skip bars with NaN or zero close (provisional/incomplete data)
                try:
                    close_val = float(row.get("close", "nan"))
                    if math.isnan(close_val) or close_val <= 0:
                        continue
                except (ValueError, TypeError):
                    continue
                last = d
        if last > sym_best.get(sym, ""):
            sym_best[sym] = last
    except Exception:
        pass

stale_syms = [(s, d) for s, d in sym_best.items() if d < str(cutoff)]
fresh_syms = [(s, d) for s, d in sym_best.items() if d >= str(cutoff)]

print(f"Today: {today}  Cutoff: {cutoff}")
print(f"Total NSE symbols tracked: {len(sym_best)}")
print(f"Fresh (>= {cutoff}): {len(fresh_syms)}")
print(f"Stale (< {cutoff}): {len(stale_syms)}")
if stale_syms:
    print(f"\nSample stale (first 20):")
    for s, d in sorted(stale_syms, key=lambda x: x[1])[:20]:
        print(f"  {s:<25} last={d}")
if fresh_syms:
    print(f"\nSample fresh (first 5):")
    for s, d in fresh_syms[:5]:
        print(f"  {s:<25} last={d}")

