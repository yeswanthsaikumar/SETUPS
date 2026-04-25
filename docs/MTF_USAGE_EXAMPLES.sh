#!/bin/bash
#
# Multi-Timeframe Alignment Feature - Usage Examples
#
# This script demonstrates how to use the new multi-timeframe alignment feature
# to identify high-confidence breakout setups supported by weekly structure.
#

echo "========================================="
echo "Multi-Timeframe Alignment Examples"
echo "========================================="
echo ""

# Example 1: View daily breakouts with weekly alignment
echo "📊 Example 1: View aligned breakouts (daily + weekly support)"
echo "Command: java Main -m scan -t daily -s both"
echo "Expected: Breakouts showing [MTF: DAILY_BREAKOUT_WEEKLY_BREAKOUT (+15.0)] at the end"
echo "          These are highest-confidence setups."
echo ""
echo "📈 Typical output:"
echo "  AAPL | Type BREAKOUT | ... | Score 47.3 [MTF: DAILY_BREAKOUT_WEEKLY_BREAKOUT (+15.0)]"
echo "  MSFT | Type BREAKOUT | ... | Score 42.1 [MTF: DAILY_BREAKOUT_WEEKLY_VALID_BASE (+5.0)]"
echo "  GOOG | Type BREAKOUT | ... | Score 38.5"  # No alignment bonus
echo ""

# Example 2: Filter for strong alignment only
echo "🎯 Example 2: Find only strongest alignments (+15 bonus)"
echo "Command: java Main -m scan -t daily -s both 2>&1 | grep 'DAILY_BREAKOUT_WEEKLY_BREAKOUT'"
echo "Result: Shows only signals where BOTH daily and weekly have breakouts"
echo "        Perfect for conservative traders"
echo ""

# Example 3: View watchlist with weekly support
echo "👀 Example 3: Pre-breakout watchlist with weekly support"
echo "Command: java Main -m watchlist -t daily -s both"
echo "Expected: Entries near pivot showing weekly alignment potential"
echo ""
echo "📈 Typical output:"
echo "  MSFT | Type WATCHLIST | ... | Score 41.2 [MTF: WATCHLIST_WEEKLY_BREAKOUT (+12.0)]"
echo "       ↑ Weekly already breaking out; good entry opportunity"
echo "  GOOG | Type WATCHLIST | ... | Score 36.8 [MTF: WATCHLIST_WEEKLY_STRONG_BASE (+5.0)]"
echo "       ↑ Weekly has base setup; lower urgency but still supportive"
echo ""

# Example 4: Backtest with alignment scoring
echo "📊 Example 4: Backtest to validate alignment improves returns"
echo "Command: java Main -m backtest -t daily --lookback 252"
echo ""
echo "Analysis steps:"
echo "  1. Run backtest (includes alignment bonuses in scoring)"
echo "  2. Export results to CSV"
echo "  3. Filter trades with [MTF: BREAKOUT_WEEKLY_BREAKOUT] tag"
echo "  4. Compare Win%, Avg R-multiple vs. unaligned trades"
echo ""
echo "Expected: Aligned trades should show higher win rates"
echo ""

# Example 5: Combining with other filters
echo "🔍 Example 5: Multi-level filtering"
echo ""
echo "Find high-score aligned breakouts:"
echo "  java Main -m scan -t daily | grep '\\[MTF:' | awk -F'Score ' '{print \$2}' | sort -rn"
echo ""
echo "Export aligned signals for further analysis:"
echo "  java Main -m scan -t daily -o csv | grep 'MTF' > aligned_signals.csv"
echo ""

# Example 6: Understanding the alignment scores
echo "📚 Example 6: Bonus Score Reference"
echo ""
echo "Daily Breakout Scenarios:"
echo "  +15.0  Weekly breakout        → Strongest setup"
echo "  +10.0  Weekly near-breakout   → Strong setup"
echo "   +5.0  Weekly valid base      → Moderate setup"
echo "   +0.0  No weekly setup        → No bonus (still tradeable)"
echo ""
echo "Watchlist Scenarios:"
echo "  +12.0  Weekly breakout        → Good entry timing"
echo "   +8.0  Weekly near-breakout   → Reasonable entry"
echo "   +5.0  Weekly valid base      → Supportive"
echo "   +0.0  No weekly setup        → No bonus"
echo ""

# Example 7: Real-world trading scenario
echo "🎬 Example 7: Real-World Trading Workflow"
echo ""
echo "Step 1: Get aligned daily breakouts"
echo "  $ java Main -m scan -t daily -s both > signals.txt"
echo ""
echo "Step 2: Identify +15 bonus trades (highest confidence)"
echo "  $ grep 'DAILY_BREAKOUT_WEEKLY_BREAKOUT' signals.txt"
echo ""
echo "Step 3: Get watchlist entries (next opportunity)"
echo "  $ java Main -m watchlist -t daily -s both > watchlist.txt"
echo ""
echo "Step 4: Trade the +15 bonus setups first"
echo "Step 5: When ready for more, trade +10 and +5 aligned setups"
echo ""

echo ""
echo "========================================="
echo "💡 Pro Tips"
echo "========================================="
echo ""
echo "1. Prioritize +15 bonus signals for live trading"
echo "   → Both timeframes aligned = highest confidence"
echo ""
echo "2. Use watchlist for position building"
echo "   → Waiting for daily breakout while weekly supports"
echo ""
echo "3. Track alignment in backtests"
echo "   → Measure if alignment improves risk-reward ratio"
echo ""
echo "4. Consider position sizing by alignment strength"
echo "   → +15 bonus: 100% position size"
echo "   → +10 bonus: 75% position size"
echo "   → +5 bonus: 50% position size"
echo ""
echo "5. Make alignment a hard filter if backtests support it"
echo "   → Later phase: require weekly alignment for low-score setups"
echo ""
echo "========================================="
echo ""

