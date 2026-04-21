"""Emit data/nse_industry_taxonomy.csv from the cache JSON (no network)."""
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cache = json.loads((ROOT / "data" / ".nse_industry_cache.json").read_text())
out = ROOT / "data" / "nse_industry_taxonomy.csv"

cols = ["nse_ticker", "company_name", "macro", "sector", "industry", "basic_industry", "source"]
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for sym in sorted(cache):
        row = cache[sym]
        w.writerow({c: row.get(c, "") for c in cols})
print(f"Wrote {len(cache)} rows to {out}")

