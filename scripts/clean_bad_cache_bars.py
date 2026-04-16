#!/usr/bin/env python3
"""
clean_bad_cache_bars.py
────────────────────────
Remove NaN-close / zero-volume bars from all NSE/BSE cache files.

These bars appear when Yahoo Finance publishes volume data before the
closing price is finalised (typically within 1-2 hours after market close).
Running this script cleans up any provisional bars that were accidentally
written to the cache.

Usage:
    python3 scripts/clean_bad_cache_bars.py          # scan all cache files
    python3 scripts/clean_bad_cache_bars.py --dry-run  # show without fixing
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"


def clean_file(path: Path, dry_run: bool = False) -> int:
    """Remove bad bars from a single CSV file.  Returns number of bad bars removed."""
    good_rows: list[dict] = []
    bad_count = 0
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return 0
            for row in reader:
                try:
                    close_val = float(row.get("close", "nan"))
                    vol = float(row.get("volume", "0"))
                    if math.isnan(close_val) or close_val <= 0:
                        bad_count += 1
                        if not dry_run:
                            print(
                                f"  Removing bad bar: {row.get('date','')} "
                                f"close={row.get('close','')} vol={row.get('volume','')} "
                                f"[{path.name}]"
                            )
                        continue
                    good_rows.append(row)
                except Exception:
                    continue
    except Exception as exc:
        print(f"  Error reading {path}: {exc}")
        return 0

    if bad_count == 0:
        return 0

    if dry_run:
        print(f"  [DRY-RUN] {path.name}: would remove {bad_count} bad bar(s)")
        return bad_count

    if not good_rows:
        print(f"  {path.name}: all bars were bad — keeping original file unchanged")
        return 0

    # Rewrite file without bad bars
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(good_rows)
    print(f"  {path.name}: removed {bad_count} bad bar(s), {len(good_rows)} bars kept")
    return bad_count


def main():
    parser = argparse.ArgumentParser(description="Clean NaN/zero-close bars from cache files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without writing")
    args = parser.parse_args()

    csv_files = sorted(CACHE_DIR.glob("*.csv"))
    total_bad = 0
    files_fixed = 0
    for path in csv_files:
        n = clean_file(path, dry_run=args.dry_run)
        if n > 0:
            total_bad += n
            files_fixed += 1

    print(f"\n{'='*50}")
    if args.dry_run:
        print(f"DRY RUN — {total_bad} bad bar(s) in {files_fixed} file(s) would be removed")
    else:
        print(f"Done — {total_bad} bad bar(s) removed from {files_fixed} file(s)")


if __name__ == "__main__":
    main()

