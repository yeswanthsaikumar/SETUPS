#!/usr/bin/env bash
# run_master.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-command full pipeline:
#   1. Full scan  — India + US, Daily + Weekly, ALL setups (VCP, Range, MR, ABFP)
#   2. Fundamentals — EPS, Revenue, Debt, MCap, PE via yfinance (cached 24 h)
#   3. Master HTML report — breakout performance, trade plans, filters, CSV export
#   4. Opens report in default browser automatically
#
# Usage:
#   chmod +x run_master.sh
#   ./run_master.sh                                 # defaults (₹10L portfolio, 1% risk)
#   ./run_master.sh --account-size 2000000          # ₹20L portfolio
#   ./run_master.sh --risk-pct 0.02                 # 2% risk/trade
#   ./run_master.sh --skip-fundamentals             # faster, no yfinance calls
#   ./run_master.sh --skip-performance-tracker       # faster, skip backtest refresh during scan
#   ./run_master.sh --workers 8 --batch 50          # more parallel workers
#   ./run_master.sh --markets india                 # India only
#   ./run_master.sh --markets us                    # US only
#   ./run_master.sh --timeframes daily              # daily only
#   ./run_master.sh --timeframes weekly             # weekly only
#   ./run_master.sh --setups vcp                    # VCP only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

cd "$(dirname "$0")"

# ── Parse args (split scan args vs report args) ───────────────────────────────
MARKETS="india,us"
TIMEFRAMES="daily,weekly"
SETUPS="full"
WORKERS=8
BATCH=60
DAILY_LB=252
WEEKLY_LB=104
ACCOUNT_SIZE=1000000
RISK_PCT=0.01
SKIP_FUNDAMENTALS=false
SKIP_PERF_TRACKER=false
DAILY_BACKFILL_SESSIONS=10
WEEKLY_BACKFILL_SESSIONS=4
SKIP_US_REFRESH="--skip-us-refresh"
OUTPUT_DIR="output"
CACHE_DIR="cache"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --markets)         MARKETS="$2";       shift 2 ;;
        --timeframes)      TIMEFRAMES="$2";    shift 2 ;;
        --setups)          SETUPS="$2";        shift 2 ;;
        --workers)         WORKERS="$2";       shift 2 ;;
        --batch)           BATCH="$2";         shift 2 ;;
        --daily-lookback)  DAILY_LB="$2";      shift 2 ;;
        --weekly-lookback) WEEKLY_LB="$2";     shift 2 ;;
        --account-size)    ACCOUNT_SIZE="$2";  shift 2 ;;
        --risk-pct)        RISK_PCT="$2";       shift 2 ;;
        --skip-fundamentals) SKIP_FUNDAMENTALS=true; shift ;;
        --skip-performance-tracker) SKIP_PERF_TRACKER=true; shift ;;
        --daily-backfill-sessions) DAILY_BACKFILL_SESSIONS="$2"; shift 2 ;;
        --weekly-backfill-sessions) WEEKLY_BACKFILL_SESSIONS="$2"; shift 2 ;;
        --force-us-refresh)  SKIP_US_REFRESH=""; shift ;;
        --output-dir)      OUTPUT_DIR="$2";    shift 2 ;;
        --cache-dir)       CACHE_DIR="$2";     shift 2 ;;
        *) echo "Unknown option: $1"; shift ;;
    esac
done

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

mkdir -p "$OUTPUT_DIR" "$CACHE_DIR"

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║         MASTER SCAN + REPORT PIPELINE                          ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════════╝${RESET}"
echo -e "  Markets    : ${YELLOW}${MARKETS}${RESET}"
echo -e "  Timeframes : ${YELLOW}${TIMEFRAMES}${RESET}"
echo -e "  Setups     : ${YELLOW}${SETUPS}${RESET}"
echo -e "  Workers    : ${YELLOW}${WORKERS}${RESET}  Batch: ${YELLOW}${BATCH}${RESET}"
echo -e "  Portfolio  : ${YELLOW}₹${ACCOUNT_SIZE}${RESET}  Risk/trade: ${YELLOW}$(echo "$RISK_PCT * 100" | bc)%${RESET}"
echo -e "  Fundamentals: ${YELLOW}$([ "$SKIP_FUNDAMENTALS" = true ] && echo 'SKIP' || echo 'ENABLED (yfinance)')${RESET}"
echo -e "  Perf tracker: ${YELLOW}$([ "$SKIP_PERF_TRACKER" = true ] && echo 'SKIP' || echo "ON (daily ${DAILY_BACKFILL_SESSIONS}, weekly ${WEEKLY_BACKFILL_SESSIONS})")${RESET}"
echo -e "  Output dir : ${YELLOW}${OUTPUT_DIR}${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Full scan (India + US, Daily + Weekly, all setups)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}▶ Step 1/2 — Running full breakout scan…${RESET}"
START_SCAN=$SECONDS

SCAN_CMD=(
  python3 apps/python/cli/run_vcp_system.py
  --markets "$MARKETS"
  --timeframes "$TIMEFRAMES"
  --setups "$SETUPS"
  --workers "$WORKERS"
  --batch "$BATCH"
  --daily-lookback "$DAILY_LB"
  --weekly-lookback "$WEEKLY_LB"
  --output-dir "$OUTPUT_DIR"
  --cache-dir "$CACHE_DIR"
  --daily-backfill-sessions "$DAILY_BACKFILL_SESSIONS"
  --weekly-backfill-sessions "$WEEKLY_BACKFILL_SESSIONS"
)

if [ -n "$SKIP_US_REFRESH" ]; then
  SCAN_CMD+=("$SKIP_US_REFRESH")
fi
if [ "$SKIP_PERF_TRACKER" = true ]; then
  SCAN_CMD+=("--skip-performance-tracker")
fi

"${SCAN_CMD[@]}"

SCAN_TIME=$((SECONDS - START_SCAN))
echo -e "${GREEN}   ✅ Scan complete in ${SCAN_TIME}s${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Generate master HTML report
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}▶ Step 2/2 — Generating master report…${RESET}"
START_RPT=$SECONDS

FUND_FLAG=""
if [ "$SKIP_FUNDAMENTALS" = true ]; then
    FUND_FLAG="--skip-fundamentals"
fi

python3 apps/python/cli/generate_master_report.py \
    --output-dir  "$OUTPUT_DIR" \
    --cache-dir   "$CACHE_DIR" \
    --account-size "$ACCOUNT_SIZE" \
    --risk-pct    "$RISK_PCT" \
    $FUND_FLAG

RPT_TIME=$((SECONDS - START_RPT))
echo -e "${GREEN}   ✅ Report generated in ${RPT_TIME}s${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Trade Plans page with MF/Institutional holdings
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}▶ Step 3/3 — Generating Trade Plans page (with MF holdings)…${RESET}"
START_TP=$SECONDS

python3 apps/python/cli/generate_trade_plans_page.py || true   # non-fatal

TP_TIME=$((SECONDS - START_TP))
echo -e "${GREEN}   ✅ Trade Plans page done in ${TP_TIME}s${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Open reports
# ─────────────────────────────────────────────────────────────────────────────
REPORT="${OUTPUT_DIR}/master_report_LATEST.html"
TRADE_PLANS="${OUTPUT_DIR}/trade_plans_live.html"

if [ -f "$REPORT" ]; then
    ABS_REPORT="$(cd "$(dirname "$REPORT")" && pwd)/$(basename "$REPORT")"
    echo -e "${BOLD}${GREEN}📊 Master Report     → file://${ABS_REPORT}${RESET}"
    open "$ABS_REPORT" 2>/dev/null || xdg-open "$ABS_REPORT" 2>/dev/null || true
fi
if [ -f "$TRADE_PLANS" ]; then
    ABS_TP="$(cd "$(dirname "$TRADE_PLANS")" && pwd)/$(basename "$TRADE_PLANS")"
    echo -e "${BOLD}${GREEN}🏦 Trade Plans + MF  → file://${ABS_TP}${RESET}"
    sleep 0.5
    open "$ABS_TP" 2>/dev/null || xdg-open "$ABS_TP" 2>/dev/null || true
fi
BREADTH="${OUTPUT_DIR}/market_breadth.html"
if [ -f "$BREADTH" ]; then
    ABS_BR="$(cd "$(dirname "$BREADTH")" && pwd)/$(basename "$BREADTH")"
    echo -e "${BOLD}${GREEN}📊 Market Breadth    → file://${ABS_BR}${RESET}"
    sleep 0.3
    open "$ABS_BR" 2>/dev/null || xdg-open "$ABS_BR" 2>/dev/null || true
fi

TOTAL=$((SCAN_TIME + RPT_TIME + TP_TIME))
echo ""
echo -e "${BOLD}${GREEN}Pipeline complete. Total time: ${TOTAL}s${RESET}"
echo -e "${YELLOW}  Tip: Run ./run_web.sh to open the live web console (scan, analyze, MF holdings)${RESET}"
echo ""

