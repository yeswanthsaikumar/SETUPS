#!/bin/bash
# migrate_cache.sh — Merge all legacy SYMBOL_N.csv cache files into single SYMBOL.csv files.
#
# This script:
#   1. Finds all unique symbols in the cache directory
#   2. For each symbol, merges all SYMBOL_N.csv files into one SYMBOL.csv
#      (deduplicates by date, sorts chronologically, newest date is last row)
#   3. Removes the old SYMBOL_N.csv files
#
# Usage: ./scripts/migrate_cache.sh [cache_dir]
#   Default cache_dir: ./cache

set -euo pipefail

CACHE_DIR="${1:-./cache}"

if [ ! -d "$CACHE_DIR" ]; then
    echo "Cache directory not found: $CACHE_DIR"
    exit 1
fi

echo "=== Cache Migration: Merging redundant files into single-file-per-symbol ==="
echo "Cache directory: $CACHE_DIR"

# Count legacy files before migration
LEGACY_COUNT=$(find "$CACHE_DIR" -maxdepth 1 -name '*_[0-9]*.csv' | wc -l | tr -d ' ')
echo "Legacy files (SYMBOL_N.csv): $LEGACY_COUNT"

if [ "$LEGACY_COUNT" -eq 0 ]; then
    echo "No legacy files found. Nothing to migrate."
    exit 0
fi

# Extract unique symbol prefixes from legacy files.
# Pattern: SYMBOL_NUMBER.csv -> SYMBOL
# Handle symbols with dots (e.g., RELIANCE.NS) and hyphens (e.g., BAJAJ-AUTO.NS)
SYMBOLS=$(find "$CACHE_DIR" -maxdepth 1 -name '*.csv' -exec basename {} \; \
    | grep -E '_[0-9]+\.csv$' \
    | sed -E 's/_[0-9]+\.csv$//' \
    | sort -u)

SYMBOL_COUNT=$(echo "$SYMBOLS" | wc -l | tr -d ' ')
echo "Unique symbols to migrate: $SYMBOL_COUNT"
echo ""

MIGRATED=0
DELETED=0
ERRORS=0

while IFS= read -r SYMBOL; do
    [ -z "$SYMBOL" ] && continue

    UNIFIED_FILE="$CACHE_DIR/${SYMBOL}.csv"

    # Collect all legacy files for this symbol, sorted by N descending (largest first)
    LEGACY_FILES=$(find "$CACHE_DIR" -maxdepth 1 -name "${SYMBOL}_[0-9]*.csv" \
        | sort -t_ -k2 -n -r)

    if [ -z "$LEGACY_FILES" ]; then
        continue
    fi

    # Use Python to merge CSV files: dedup by date, sort chronologically
    python3 -c "
import csv, sys, os

cache_dir = '$CACHE_DIR'
symbol = '$SYMBOL'
unified = '$UNIFIED_FILE'
legacy_files = '''$LEGACY_FILES'''.strip().split('\n')

rows_by_date = {}

# Also read existing unified file if it exists
if os.path.exists(unified):
    try:
        with open(unified, 'r') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 6:
                    rows_by_date[row[0]] = row
    except Exception:
        pass

# Read all legacy files (largest first = most authoritative)
for legacy_file in legacy_files:
    legacy_file = legacy_file.strip()
    if not legacy_file or not os.path.exists(legacy_file):
        continue
    try:
        with open(legacy_file, 'r') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 6 and row[0] not in rows_by_date:
                    rows_by_date[row[0]] = row
    except Exception as e:
        print(f'  Warning: Could not read {legacy_file}: {e}', file=sys.stderr)

if not rows_by_date:
    sys.exit(1)

# Sort by date (ascending) — newest date is last row
sorted_rows = sorted(rows_by_date.values(), key=lambda r: r[0])

# Write unified file
with open(unified, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['date','open','high','low','close','volume'])
    for row in sorted_rows:
        writer.writerow(row[:6])

print(f'  {symbol}: {len(sorted_rows)} bars merged from {len(legacy_files)} files -> {os.path.basename(unified)}')
" 2>&1

    if [ $? -eq 0 ]; then
        MIGRATED=$((MIGRATED + 1))

        # Delete legacy files
        while IFS= read -r LEGACY_FILE; do
            [ -z "$LEGACY_FILE" ] && continue
            rm -f "$LEGACY_FILE"
            DELETED=$((DELETED + 1))
        done <<< "$LEGACY_FILES"
    else
        echo "  ERROR: Failed to migrate $SYMBOL"
        ERRORS=$((ERRORS + 1))
    fi

done <<< "$SYMBOLS"

# Count remaining files
REMAINING=$(find "$CACHE_DIR" -maxdepth 1 -name '*.csv' | wc -l | tr -d ' ')
UNIFIED_COUNT=$(find "$CACHE_DIR" -maxdepth 1 -name '*.csv' ! -name '*_[0-9]*.csv' | wc -l | tr -d ' ')

echo ""
echo "=== Migration Complete ==="
echo "Symbols migrated: $MIGRATED"
echo "Legacy files deleted: $DELETED"
echo "Errors: $ERRORS"
echo "Unified CSV files: $UNIFIED_COUNT"
echo "Total remaining files: $REMAINING"
echo ""
echo "Disk usage: $(du -sh "$CACHE_DIR" | cut -f1)"

