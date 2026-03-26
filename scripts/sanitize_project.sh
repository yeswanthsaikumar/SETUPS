#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PRUNE_OUTPUT=true

for arg in "$@"; do
  case "$arg" in
    --no-prune-output) PRUNE_OUTPUT=false ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Sanitizing project workspace"
echo "Root: $ROOT_DIR"

echo "==> Cleaning generated Java artifacts"
find src -type f -name "*.class" -delete || true
find bin -type f -name "*.class" -delete || true

if [ "$PRUNE_OUTPUT" = true ]; then
  echo "==> Pruning stale runtime folders under output/"
  rm -rf output/scan_* output/system_run_* || true
else
  echo "==> Skipping output pruning (--no-prune-output)"
fi

echo "==> Ensuring runtime directories exist"
mkdir -p output cache

echo "==> Compiling Java sources"
javac src/*.java

echo "==> Running scan smoke test"
java -cp src Main --mode=scan --provider=sample --timeframe=daily --symbols=NVCP,VCPX > /tmp/setups_scan_smoke.log

echo "==> Running backtest smoke test"
java -cp src Main --mode=backtest --provider=sample --timeframe=daily --symbols=NVCP,VCPX --backtest-years=2 > /tmp/setups_backtest_smoke.log

echo "==> Smoke test outputs"
head -n 5 /tmp/setups_scan_smoke.log || true
head -n 5 /tmp/setups_backtest_smoke.log || true

echo "==> Sanitization complete"

