#!/usr/bin/env bash
# full_scan.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-command pipeline:
#   1. Fetch ~10 000 US stock tickers  →  all_us_stocks.txt (conditional: only if
#      missing or older than 24 hours; use --force-fetch to download fresh)
#   2. Compile Java sources
#   3. Run full breakout scan (VCP and/or range expansion) in parallel batches
#   4. Open the HTML report in the default browser
#
# Usage:
#   chmod +x full_scan.sh
#   ./full_scan.sh                         # uses all defaults (smart refresh)
#   ./full_scan.sh --workers 6 --batch 30  # more parallel workers
#   ./full_scan.sh --skip-fetch            # skip ticker download entirely
#   ./full_scan.sh --force-fetch           # always download fresh tickers
#
# Options forwarded to run_full_us_scan.py:
#   --workers N      parallel Java processes  (default 4)
#   --batch   N      symbols per Java call    (default 25)
#   --lookback N     candlestick lookback     (default daily 252 / weekly 104)
#   --setups MODE    setup filter             (both|vcp|range_expansion)
#   --skip-fetch     don't download tickers (use cached file)
#   --force-fetch    always download fresh tickers
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

SKIP_FETCH=false
FORCE_FETCH=false
SCAN_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --skip-fetch)  SKIP_FETCH=true ;;
        --force-fetch) FORCE_FETCH=true ;;
        *)             SCAN_ARGS+=("$arg") ;;
    esac
done

# ── COLOURS ──────────────────────────────────────────────────────────────────
BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║       US STOCK BREAKOUT (VCP + RANGE) FULL PIPELINE            ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════════╝${RESET}"
echo ""

# ── STEP 1 : Fetch tickers ────────────────────────────────────────────────────
if [ "$SKIP_FETCH" = true ]; then
    echo -e "${BOLD}▶ Step 1/3 — Skipped ticker fetch (--skip-fetch)${RESET}"
    if [ -f data/universes/us_stock_tickers.csv ]; then
        LINES=$(tail -n +2 data/universes/us_stock_tickers.csv | wc -l | tr -d ' ')
        echo "   Using existing data/universes/us_stock_tickers.csv  ($LINES rows)"
    elif [ -f data/universes/all_us_stocks.txt ]; then
        LINES=$(grep -c -v '^#' data/universes/all_us_stocks.txt || true)
        echo "   Using existing data/universes/all_us_stocks.txt  ($LINES symbols)"
    else
        echo "ERROR: no symbols file found. Remove --skip-fetch to download one." >&2
        exit 1
    fi
    echo ""
elif [ "$FORCE_FETCH" = true ]; then
    echo -e "${BOLD}▶ Step 1/3 — Downloading US stock universe (--force-fetch)…${RESET}"
    python3 apps/python/cli/fetch_us_stocks.py
    echo ""
else
    # Smart refresh: only download if file is missing or older than 24 hours
    NEEDS_FETCH=false

    if [ -f data/universes/us_stock_tickers.csv ]; then
        FILE_AGE=$(($(date +%s) - $(stat -f%m data/universes/us_stock_tickers.csv 2>/dev/null || echo 0)))
    elif [ -f data/universes/all_us_stocks.txt ]; then
        FILE_AGE=$(($(date +%s) - $(stat -f%m data/universes/all_us_stocks.txt 2>/dev/null || echo 0)))
    else
        NEEDS_FETCH=true
    fi

    if [ "$NEEDS_FETCH" = false ] && [ -z "${FILE_AGE:-}" ]; then
        NEEDS_FETCH=true
    fi

    if [ "$NEEDS_FETCH" = true ]; then
        echo -e "${BOLD}▶ Step 1/3 — Downloading US stock universe (file missing)…${RESET}"
        python3 apps/python/cli/fetch_us_stocks.py
        echo ""
    else
        # FILE_AGE is in seconds, 24 hours = 86400 seconds
        HOURS_AGE=$((FILE_AGE / 3600))
        if [ $FILE_AGE -lt 86400 ]; then
            echo -e "${BOLD}▶ Step 1/3 — Skipped ticker fetch (file is $HOURS_AGE hours old)${RESET}"
            echo "   Use --force-fetch to download fresh tickers"
            echo ""
        else
            echo -e "${BOLD}▶ Step 1/3 — Downloading US stock universe (file is $HOURS_AGE hours old)…${RESET}"
            python3 apps/python/cli/fetch_us_stocks.py
            echo ""
        fi
    fi
fi

# ── STEP 2 : Compile Java ─────────────────────────────────────────────────────
echo -e "${BOLD}▶ Step 2/3 — Compiling Java sources…${RESET}"
javac src/*.java
echo -e "${GREEN}   Compilation successful.${RESET}"
echo ""

# ── STEP 3 : Run scan ─────────────────────────────────────────────────────────
echo -e "${BOLD}▶ Step 3/3 — Running breakout scan…${RESET}"
python3 apps/python/cli/run_full_us_scan.py "${SCAN_ARGS[@]}"

# ── Open HTML report ─────────────────────────────────────────────────────────
LATEST_HTML=$(ls -t output/scan_*/vcp_hits_*.html 2>/dev/null | head -1 || true)
if [ -n "$LATEST_HTML" ]; then
    echo ""
    echo -e "${GREEN}Opening report: $LATEST_HTML${RESET}"
    open "$LATEST_HTML" 2>/dev/null || xdg-open "$LATEST_HTML" 2>/dev/null || true
fi

echo ""
echo -e "${BOLD}${GREEN}Pipeline complete.${RESET}"

