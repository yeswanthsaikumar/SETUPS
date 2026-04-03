#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run_analysis_dashboards.sh
# Generates all 4 HTML analysis dashboards in sequence:
#   1. 3-Year Backtest Dashboard  → output/backtest_3yr_dashboard.html
#   2. Live Trade Plans           → output/trade_plans_live.html
#   3. Sector & Macro Analysis    → output/sector_macro_analysis.html
#   4. Hub Index                  → output/index.html (static, already written)
#
# Usage:
#   ./run_analysis_dashboards.sh
#   ./run_analysis_dashboards.sh --max-stocks 500        (faster test run)
#   ./run_analysis_dashboards.sh --account-size 2000000  (larger account)
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MAX_STOCKS=""
ACCOUNT_SIZE=""

for arg in "$@"; do
  case $arg in
    --max-stocks=*) MAX_STOCKS="${arg#*=}" ;;
    --account-size=*) ACCOUNT_SIZE="${arg#*=}" ;;
    --max-stocks) shift; MAX_STOCKS="$1" ;;
    --account-size) shift; ACCOUNT_SIZE="$1" ;;
  esac
done

echo "========================================================"
echo "  SETUPS Analysis Dashboard Generator"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
echo ""

# ── 2-3. Dashboards (parallel) ───────────────────────────────────────────────
echo "[2/3] Generating Live Trade Plans + Sector & Macro pages (parallel)..."
python3 apps/python/cli/generate_trade_plans_page.py &
PID_TRADE_PLANS=$!
python3 apps/python/cli/generate_sector_macro_page.py &
PID_SECTOR_MACRO=$!

STATUS_TRADE_PLANS=0
STATUS_SECTOR_MACRO=0
wait "$PID_TRADE_PLANS" || STATUS_TRADE_PLANS=$?
wait "$PID_SECTOR_MACRO" || STATUS_SECTOR_MACRO=$?

if [ "$STATUS_TRADE_PLANS" -ne 0 ] || [ "$STATUS_SECTOR_MACRO" -ne 0 ]; then
  echo "Dashboard generation failed."
  exit 1
fi

echo "      → output/trade_plans_live.html"
echo "      → output/sector_macro_analysis.html"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  All dashboards generated successfully!"
echo ""
echo "  Open in browser:"
echo "  output/index.html                   (Hub)"
echo "  output/backtest_3yr_dashboard.html  (Backtest)"
echo "  output/trade_plans_live.html        (Trade Plans)"
echo "  output/sector_macro_analysis.html   (Sectors)"
echo "========================================================"

# Auto-open index in browser (macOS)
if command -v open &>/dev/null; then
  open output/index.html
fi

