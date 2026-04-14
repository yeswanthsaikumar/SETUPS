#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run_analysis_dashboards.sh
# Generates all HTML analysis dashboards in parallel:
#   1. Live Trade Plans + MF/Institutional holdings → output/trade_plans_live.html
#   2. Sector & Macro Analysis                      → output/sector_macro_analysis.html
#   3. Market Breadth + Trend Detection             → output/market_breadth.html
#
# Usage:
#   ./run_analysis_dashboards.sh
#   ./run_analysis_dashboards.sh --skip-mf   (skip MF holdings fetch, faster)
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
echo "  Generating 3 dashboards in parallel:"
echo "  • Trade Plans + MF Holdings"
echo "  • Sector & Macro Analysis"
echo "  • Market Breadth + Trend Detection"
if [ "$SKIP_MF" = false ]; then
  echo "  Note: MF data fetched from Screener.in (cached 6h). May take 30-60s."
fi
echo ""

# ── 0. Auto-refresh stale cache ─────────────────────────────────────────────
if [ -f "scripts/refresh_cache.py" ]; then
  echo "Refreshing stale Yahoo Finance cache files…"
  python3 scripts/refresh_cache.py --workers 8 || echo "  ⚠ Cache refresh had issues (non-fatal)"
  echo ""
fi

# ── 1. Live Trade Plans (with MF holdings) + Sector & Macro + Market Breadth ───────
if [ "$SKIP_MF" = true ]; then
  echo "[1/1] Generating Trade Plans (MF skipped) + Sector & Macro + Market Breadth..."
else
  echo "[1/1] Generating Trade Plans + MF/Institutional Holdings + Sector & Macro + Market Breadth..."
  echo "      Note: First run fetches MF data from Screener.in (cached 6h). May take 30-60s."
fi

python3 apps/python/cli/generate_trade_plans_page.py &
PID_TRADE_PLANS=$!
python3 apps/python/cli/generate_sector_macro_page.py &
PID_SECTOR_MACRO=$!
python3 apps/python/cli/generate_breadth_dashboard.py &
PID_BREADTH=$!

STATUS_TRADE_PLANS=0
STATUS_SECTOR_MACRO=0
STATUS_BREADTH=0
wait "$PID_TRADE_PLANS"  || STATUS_TRADE_PLANS=$?
wait "$PID_SECTOR_MACRO" || STATUS_SECTOR_MACRO=$?
wait "$PID_BREADTH"      || STATUS_BREADTH=$?

echo ""
if [ "$STATUS_TRADE_PLANS" -ne 0 ] || [ "$STATUS_SECTOR_MACRO" -ne 0 ]; then
  echo "  ✖ Dashboard generation failed (trade_plans=$STATUS_TRADE_PLANS, sector_macro=$STATUS_SECTOR_MACRO)"
  exit 1
fi
[ "$STATUS_BREADTH" -ne 0 ] && echo "  ⚠ Market breadth dashboard failed (non-fatal)"

echo "========================================================"
echo "  ✅ All dashboards generated successfully!"
echo ""
echo "  output/trade_plans_live.html      (Trade Plans + MF Holdings)"
echo "  output/sector_macro_analysis.html (Sectors & Macro)"
echo "  output/market_breadth.html        (📊 Market Breadth + Trend Detection)"
echo ""
echo "  Web Console:  ./run_web.sh   →   http://localhost:8000"
echo "========================================================"

# Auto-open in browser (macOS)
if command -v open &>/dev/null; then
  open output/trade_plans_live.html
  sleep 0.4
  open output/market_breadth.html
  sleep 0.4
  open output/sector_macro_analysis.html
fi

