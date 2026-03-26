#!/bin/bash
# run_full_scan.sh — launches the full India+US daily+weekly scan
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
mkdir -p output

echo "Starting full scan at $(date)" | tee /tmp/scan_progress.log

python3 apps/python/cli/run_vcp_system.py \
  --markets india,us \
  --timeframes daily,weekly \
  --setups full \
  --workers 6 \
  --batch 40 \
  --skip-us-refresh \
  --daily-lookback 252 \
  --weekly-lookback 104 \
  --output-dir output \
  2>&1 | tee /tmp/scan_progress.log

echo "Scan complete at $(date)" | tee -a /tmp/scan_progress.log

