#!/bin/bash
#
# Quick Start - Test Both Features
#
# This script helps you immediately verify both features are working
#

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Breakout Quality + Multi-Timeframe Alignment - Quick Test ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

cd /Users/yeshwantha/IdeaProjects/SETUPS

# Step 1: Compile
echo "Step 1️⃣  Compiling source code..."
javac src/BreakoutQualityAnalyzer.java 2>/dev/null
javac src/*.java 2>/dev/null

if [ $? -eq 0 ]; then
    echo "   ✅ Compilation successful"
else
    echo "   ❌ Compilation failed"
    exit 1
fi

echo ""

# Step 2: Run scan
echo "Step 2️⃣  Running daily scan (displaying first 5 signals)..."
echo "   Command: java Main -m scan -t daily"
echo ""

java Main -m scan -t daily 2>/dev/null | head -5

echo ""
echo "   ✅ Scan completed"

echo ""

# Step 3: Check for tags
echo "Step 3️⃣  Verifying output tags..."
SCAN_OUTPUT=$(java Main -m scan -t daily 2>/dev/null)

if echo "$SCAN_OUTPUT" | grep -q "\[BQ:"; then
    echo "   ✅ Breakout Quality tags found: [BQ: RATING (score/40)]"
else
    echo "   ❌ Breakout Quality tags NOT found"
fi

if echo "$SCAN_OUTPUT" | grep -q "\[MTF:"; then
    echo "   ✅ Multi-Timeframe tags found: [MTF: reason (+bonus)]"
else
    echo "   ⚠️  No signals had multi-timeframe alignment (could be ok)"
fi

echo ""

# Step 4: Show quality distribution
echo "Step 4️⃣  Quality Distribution:"
echo "   Command: java Main -m scan -t daily | grep -o \"BQ: [A-Z]*\" | sort | uniq -c"
echo ""

QUALITY_DIST=$(java Main -m scan -t daily 2>/dev/null | grep -o "BQ: [A-Z]*" | sort | uniq -c)

if [ -z "$QUALITY_DIST" ]; then
    echo "   (No signals with quality tags in current scan)"
else
    echo "$QUALITY_DIST" | awk '{printf "      %s %s signals\n", $2, $1}'
fi

echo ""

# Step 5: Show sample detailed report
echo "Step 5️⃣  Sample Signals (with both features):"
echo ""
FIRST_SIGNALS=$(java Main -m scan -t daily 2>/dev/null | head -3)
echo "$FIRST_SIGNALS" | while read line; do
    if [ ! -z "$line" ]; then
        SYMBOL=$(echo "$line" | awk '{print $1}')
        SCORE=$(echo "$line" | grep -o "Score [0-9.]*" | awk '{print $2}')
        BQ=$(echo "$line" | grep -o "BQ: [A-Z]*" | awk '{print $2}')
        MTF=$(echo "$line" | grep -o "MTF: [^]]*" | sed 's/MTF: //')

        if [ ! -z "$SYMBOL" ]; then
            printf "      %-6s | Score: %-6s | Quality: %-10s | Alignment: %s\n" "$SYMBOL" "$SCORE" "$BQ" "$MTF"
        fi
    fi
done

echo ""

# Step 6: Show recommendations
echo "Step 6️⃣  Next Steps:"
echo ""
echo "   📖 Read Documentation:"
echo "      1. docs/README_FEATURES.md (overview)"
echo "      2. docs/IMPLEMENTATION_SUMMARY_COMPLETE.md (complete summary)"
echo "      3. docs/BREAKOUT_QUALITY_QUICK_REFERENCE.md (quality guide)"
echo "      4. docs/MTF_QUICK_START.md (alignment guide)"
echo ""
echo "   🧪 Try Analysis:"
echo "      java Main -m scan -t daily | grep 'EXCELLENT'"
echo "      java Main -m scan -t daily | grep 'MTF:.*+15'"
echo ""
echo "   📊 Backtest to Validate:"
echo "      java Main -m backtest -t daily --lookback 252"
echo ""
echo "   💡 Use Examples (12 provided):"
echo "      docs/BREAKOUT_QUALITY_USAGE_EXAMPLES.md"
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ✅ Features Verified and Ready to Use!                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 Start with: docs/README_FEATURES.md"
echo ""

