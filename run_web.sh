#!/usr/bin/env bash
# run_web.sh
# ─────────────────────────────────────────────────────────────────────────────
# Starts the SETUPS FastAPI web console (apps/web/ui/index.html)
# OHLCV cache refresh runs in the BACKGROUND — server starts immediately.
#
# Usage:
#   ./run_web.sh              # default: port 8000, auto-opens browser
#   ./run_web.sh --port 8080  # custom port
#   ./run_web.sh --no-open    # skip auto-opening browser
#   ./run_web.sh --reload     # enable hot-reload (dev mode)
#   ./run_web.sh --skip-refresh  # skip cache refresh entirely
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

cd "$(dirname "$0")"

PORT=8000
AUTO_OPEN=true
RELOAD_FLAG=""
SKIP_REFRESH=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)    PORT="$2";  shift 2 ;;
        --no-open) AUTO_OPEN=false; shift ;;
        --reload)  RELOAD_FLAG="--reload"; shift ;;
        --skip-refresh) SKIP_REFRESH=true; shift ;;
        *) echo "Unknown option: $1"; shift ;;
    esac
done

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# ── Load .env file if present (for GROWW_API_KEY etc.) ────────────────────────
if [ -f ".env" ]; then
    set -a; source .env; set +a
fi

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║        SETUPS Web Console                          ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${RESET}"
echo -e "  URL     : ${YELLOW}http://localhost:${PORT}${RESET}"
echo -e "  API Docs: ${YELLOW}http://localhost:${PORT}/docs${RESET}"
echo -e ""
echo -e "  ${CYAN}Features available:${RESET}"
echo -e "   ▶ Run Scan / Backtest jobs"
echo -e "   🔍 Stock Analyzer (auto + live mode)"
echo -e "   📊 Performance Tracker with MF Holdings"
echo -e "   🏦 Institutional / Mutual Fund data (Screener.in + yfinance)"
echo -e "   📈 Live report links"
echo -e ""

# ── Background OHLCV cache refresh ──────────────────────────────────────────
# Cache refresh runs INSIDE the FastAPI server process (non-blocking background thread).
# This means the server starts instantly and refresh progress is visible via:
#   GET /api/cache/refresh-status
#   POST /api/cache/refresh  (trigger manually)
# The UI shows a live cache refresh indicator in the top bar.

if [ "$SKIP_REFRESH" = false ]; then
    echo -e "${BOLD}▶ OHLCV cache will refresh in-process (background thread)${RESET}"
    echo -e "   Status: ${YELLOW}http://localhost:${PORT}/api/cache/refresh-status${RESET}"
    echo ""
else
    echo -e "  ${YELLOW}⏭  Cache refresh skipped${RESET}"
    echo ""
fi

echo -e "  Press ${YELLOW}Ctrl+C${RESET} to stop"
echo ""

# Auto-open browser
if [ "$AUTO_OPEN" = true ]; then
    (sleep 1.5 && open "http://localhost:${PORT}" 2>/dev/null || \
     xdg-open "http://localhost:${PORT}" 2>/dev/null || \
     echo "Open browser at: http://localhost:${PORT}") &
fi

# Start the server — runs immediately, cache refresh happens inside
# Set GROWW_API_KEY + GROWW_API_SECRET for live prices via Groww Developer API
# Or set GROWW_ACCESS_TOKEN directly if you already have one
# Get credentials at: https://developer.groww.in/
GROWW_API_KEY="${GROWW_API_KEY:-}" \
GROWW_API_SECRET="${GROWW_API_SECRET:-}" \
GROWW_ACCESS_TOKEN="${GROWW_ACCESS_TOKEN:-}" \
SETUPS_SKIP_STARTUP_REFRESH="${SKIP_REFRESH}" \
PYTHONPATH="$(pwd)/apps/python/lib" \
uvicorn apps.web.api.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info \
    $RELOAD_FLAG

