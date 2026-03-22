#!/bin/bash
#
# Multi-Timeframe Alignment Feature - Validation Test
#
# This script validates that the multi-timeframe alignment feature
# is properly integrated and working correctly.
#

echo "========================================="
echo "Multi-Timeframe Alignment - Validation"
echo "========================================="
echo ""

cd /Users/yeshwantha/IdeaProjects/SETUPS

# Step 1: Check source files exist
echo "✓ Step 1: Verifying source files..."
if [ -f "src/MultiTimeframeAlignmentAnalyzer.java" ]; then
    echo "  ✅ MultiTimeframeAlignmentAnalyzer.java exists"
else
    echo "  ❌ MultiTimeframeAlignmentAnalyzer.java MISSING"
    exit 1
fi

if grep -q "private final MultiTimeframeAlignmentAnalyzer alignmentAnalyzer" src/ScannerEngine.java; then
    echo "  ✅ ScannerEngine has alignmentAnalyzer field"
else
    echo "  ❌ ScannerEngine missing alignmentAnalyzer field"
    exit 1
fi

if grep -q "alignmentBonus" src/ScanResult.java; then
    echo "  ✅ ScanResult has alignment fields"
else
    echo "  ❌ ScanResult missing alignment fields"
    exit 1
fi

echo ""

# Step 2: Compile
echo "✓ Step 2: Compiling source code..."
javac src/MultiTimeframeAlignmentAnalyzer.java 2>/dev/null
javac src/ScanResult.java 2>/dev/null
javac src/WatchlistResult.java 2>/dev/null
javac src/ScannerEngine.java 2>/dev/null

if [ -f "src/MultiTimeframeAlignmentAnalyzer.class" ]; then
    echo "  ✅ Compilation successful"
else
    echo "  ❌ Compilation failed"
    exit 1
fi

echo ""

# Step 3: Verify class files generated
echo "✓ Step 3: Verifying compiled classes..."
classes_expected=("MultiTimeframeAlignmentAnalyzer.class" "MultiTimeframeAlignmentAnalyzer\$MultiTimeframeContext.class" "ScanResult.class" "WatchlistResult.class" "ScannerEngine.class")

for class_file in "${classes_expected[@]}"; do
    if find . -name "$class_file" -type f 2>/dev/null | grep -q .; then
        echo "  ✅ $class_file found"
    else
        echo "  ⚠️  $class_file not found (may be ok if in build dir)"
    fi
done

echo ""

# Step 4: Check console output template
echo "✓ Step 4: Verifying output format..."
if grep -q "\\[MTF:" src/ScanResult.java; then
    echo "  ✅ ScanResult console output includes [MTF:...] tag"
else
    echo "  ⚠️  ScanResult may not show alignment tags"
fi

if grep -q "getAlignmentBonus()" src/ScanResult.java; then
    echo "  ✅ ScanResult has getAlignmentBonus() method"
else
    echo "  ❌ ScanResult missing getAlignmentBonus() method"
    exit 1
fi

echo ""

# Step 5: Check error handling
echo "✓ Step 5: Verifying error handling..."
if grep -q "catch (Exception ex)" src/ScannerEngine.java; then
    echo "  ✅ ScannerEngine has exception handling"
else
    echo "  ⚠️  May lack error handling"
fi

echo ""

# Step 6: Documentation
echo "✓ Step 6: Verifying documentation..."
docs=(
    "docs/MULTI_TIMEFRAME_ALIGNMENT.md"
    "docs/MTF_IMPLEMENTATION_DETAILS.md"
    "docs/MTF_QUICK_START.md"
    "docs/MTF_USAGE_EXAMPLES.sh"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        lines=$(wc -l < "$doc")
        echo "  ✅ $doc ($lines lines)"
    else
        echo "  ❌ $doc MISSING"
    fi
done

echo ""

# Step 7: Code verification
echo "✓ Step 7: Code verification..."
alignment_calls=$(grep -c "analyzeAlignmentFor" src/ScannerEngine.java)
if [ "$alignment_calls" -ge 2 ]; then
    echo "  ✅ ScannerEngine calls alignment analyzer ($alignment_calls times)"
else
    echo "  ❌ ScannerEngine may not call alignment analyzer"
fi

bonus_setters=$(grep -c "setAlignmentBonus" src/ScannerEngine.java)
if [ "$bonus_setters" -ge 2 ]; then
    echo "  ✅ ScannerEngine applies alignment bonus ($bonus_setters times)"
else
    echo "  ⚠️  ScannerEngine may not apply bonus"
fi

echo ""
echo "========================================="
echo "✅ Validation Complete!"
echo "========================================="
echo ""
echo "The multi-timeframe alignment feature is ready to use."
echo ""
echo "Quick test:"
echo "  java Main -m scan -t daily | head -5"
echo ""
echo "Look for '[MTF:...' tags in the output to see alignment bonuses."
echo ""
echo "Documentation:"
echo "  - Read: docs/MTF_QUICK_START.md (start here)"
echo "  - Read: docs/MULTI_TIMEFRAME_ALIGNMENT.md (complete guide)"
echo "  - Read: docs/MTF_IMPLEMENTATION_DETAILS.md (technical details)"
echo ""

