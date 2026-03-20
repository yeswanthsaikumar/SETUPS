#!/bin/bash
# MILESTONE_2_QUICKSTART.sh
# Quick start guide for Milestone 2 interactive HTML + fundamentals enrichment
# Execute this to set up and test the new features

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ Milestone 2: Interactive HTML + Fundamentals Enrichment       ║"
echo "║ Quick Start Setup                                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Install dependencies
echo "📦 Step 1: Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install yfinance --quiet 2>/dev/null && echo "✓ yfinance installed" || echo "⚠ yfinance install may need manual review"
else
    echo "❌ pip3 not found. Please install yfinance manually:"
    echo "   pip3 install yfinance"
fi
echo ""

# Step 2: Compile Java
echo "🔨 Step 2: Compiling Java code..."
if [ -d "src" ]; then
    cd src
    javac *.java && echo "✓ Java compilation successful"
    cd ..
else
    echo "⚠ src directory not found"
fi
echo ""

# Step 3: Test fundamentals provider
echo "🧪 Step 3: Testing fundamentals provider..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str((Path('.').resolve() / 'apps' / 'python' / 'lib')))
from fundamentals_provider import FundamentalsProvider
provider = FundamentalsProvider(cache_dir='cache')
print('Testing AAPL fetch...')
fund = provider.fetch_fundamentals('AAPL')
if fund.get('error'):
    print(f'  ⚠ Note: {fund.get(\"error\")}')
else:
    print(f'  ✓ Market Cap: {fund.get(\"market_cap_b\")}B')
    print(f'  ✓ PE Ratio: {fund.get(\"pe_ratio\")}')
    print(f'  ✓ Sector: {fund.get(\"sector\")}')
" 2>&1 || echo "⚠ Fundamentals provider test skipped"
echo ""

# Step 4: Quick scan test
echo "🚀 Step 4: Running test scan with interactive HTML..."
echo "   This will scan a few US stocks and generate an interactive HTML report"
echo ""

if [ -f "data/universes/us_stock_tickers.csv" ]; then
    # Extract first 10 symbols for quick test
    echo "   Extracting first 10 symbols for quick test..."
    head -11 data/universes/us_stock_tickers.csv > /tmp/test_symbols.csv

    python3 apps/python/cli/run_full_us_scan.py \
        --symbols /tmp/test_symbols.csv \
        --batch 5 \
        --workers 1 \
        --lookback 252 \
        --timeframe daily \
        --market-label test_sample \
        --output-dir output 2>&1 | tail -20

    # Find the latest HTML report
    LATEST_HTML=$(ls -t output/vcp_hits_*_LATEST.html 2>/dev/null | head -1 || echo "")

    if [ -f "$LATEST_HTML" ]; then
        echo ""
        echo "✅ Test scan complete!"
        echo "📊 Interactive HTML Report: $LATEST_HTML"
        echo ""
        echo "📖 Features to try in the HTML report:"
        echo "   • Search: Type a symbol in the search box"
        echo "   • Filter: Drag the score slider to filter by quality"
        echo "   • Setup: Click 'VCP' or 'Range Exp' buttons to filter by type"
        echo "   • Sort: Click any column header to sort"
        echo "   • Export: Click 'Export Filtered' to download filtered CSV"
        echo "   • Analytics: Check the summary cards and distribution charts"
        echo ""
        echo "📂 To open in browser:"
        echo "   open '$LATEST_HTML'"
        echo ""
    else
        echo "⚠ HTML report not found. Check output directory."
    fi
else
    echo "⚠ data/universes/us_stock_tickers.csv not found. Skipping test scan."
fi

echo "📖 Documentation:"
echo "   Read docs/MILESTONE_2.md for complete feature documentation"
echo "   Read docs/SYSTEM_DESIGN.md for architecture overview"
echo ""

echo "🎉 Milestone 2 setup complete!"
echo ""

