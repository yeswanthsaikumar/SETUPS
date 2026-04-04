#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run_analysis_dashboards.sh
# Generates all HTML analysis dashboards:
#   1. Live Trade Plans + MF/Institutional holdings → output/trade_plans_live.html
#   2. Sector & Macro Analysis                      → output/sector_macro_analysis.html
#   3. Hub Index                                    → output/index.html
#
# Usage:
#   ./run_analysis_dashboards.sh
#   ./run_analysis_dashboards.sh --skip-mf          (skip MF holdings fetch, faster)
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SKIP_MF=false
for arg in "$@"; do
  case $arg in
    --skip-mf) SKIP_MF=true ;;
  esac
done

# Activate venv
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

echo "========================================================"
echo "  SETUPS Analysis Dashboard Generator"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
echo ""

# ── 1. Live Trade Plans (with MF holdings) + Sector & Macro (parallel) ───────
if [ "$SKIP_MF" = true ]; then
  echo "[1/2] Generating Trade Plans (MF skipped) + Sector & Macro (parallel)..."
else
  echo "[1/2] Generating Trade Plans + MF/Institutional Holdings + Sector & Macro (parallel)..."
  echo "      Note: First run fetches MF data from Screener.in (cached 6h). May take 30-60s."
fi

python3 apps/python/cli/generate_trade_plans_page.py &
PID_TRADE_PLANS=$!
python3 apps/python/cli/generate_sector_macro_page.py &
PID_SECTOR_MACRO=$!

STATUS_TRADE_PLANS=0
STATUS_SECTOR_MACRO=0
wait "$PID_TRADE_PLANS"  || STATUS_TRADE_PLANS=$?
wait "$PID_SECTOR_MACRO" || STATUS_SECTOR_MACRO=$?

if [ "$STATUS_TRADE_PLANS" -ne 0 ] || [ "$STATUS_SECTOR_MACRO" -ne 0 ]; then
  echo "Dashboard generation failed (trade_plans=$STATUS_TRADE_PLANS, sector_macro=$STATUS_SECTOR_MACRO)."
  exit 1
fi

echo "      → output/trade_plans_live.html  (🏦 includes MF/institutional holdings)"
echo "      → output/sector_macro_analysis.html"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  All dashboards generated successfully!"
echo ""
echo "  Open in browser:"
echo "  output/trade_plans_live.html        (Trade Plans + MF Holdings)"
echo "  output/sector_macro_analysis.html   (Sectors & Macro)"
echo "  output/index.html                   (Hub)"
echo ""
echo "  Web Console (scan/backtest/analyze):"
echo "  ./run_web.sh                         (starts at http://localhost:8000)"
echo "========================================================"

# Auto-open in browser (macOS)
if command -v open &>/dev/null; then
  open output/trade_plans_live.html
fi

