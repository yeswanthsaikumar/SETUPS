# Multi-Timeframe Alignment Feature

## Overview

The multi-timeframe alignment feature enhances your trading system by analyzing daily and weekly setups together. When a daily breakout signal is supported by a strong weekly structure, the signal receives a score bonus, prioritizing high-confidence setups.

**Philosophy:** Conservative approach using score bonuses first (not hard filters). If backtests confirm the alignment improves returns, it can later be made into a hard requirement for lower-rated setups.

---

## How It Works

### Score Bonuses

The system awards alignment bonuses based on how daily and weekly structures support each other:

#### For Daily Breakout Signals:
| Scenario | Bonus | Reason |
|----------|-------|--------|
| Daily breakout + **Weekly breakout** | **+15.0 pts** | Strongest alignment; both timeframes confirming |
| Daily breakout + **Weekly near-breakout** | **+10.0 pts** | Strong alignment; weekly in continuation zone |
| Daily breakout + **Weekly valid base** | **+5.0 pts** | Moderate alignment; weekly has setup but no breakout |
| Daily breakout + **No weekly setup** | **0.0 pts** | No alignment bonus |

#### For Watchlist Signals (pre-breakout):
| Scenario | Bonus | Reason |
|----------|-------|--------|
| Watchlist + **Weekly breakout** | **+12.0 pts** | Good opportunity; weekly already moving |
| Watchlist + **Weekly near-breakout** | **+8.0 pts** | Moderate opportunity; weekly in continuation |
| Watchlist + **Weekly valid base** | **+5.0 pts** | Reasonable; weekly setup in place |
| Watchlist + **No weekly setup** | **0.0 pts** | No alignment bonus |

### Implementation Details

The feature is implemented in three main components:

#### 1. **MultiTimeframeAlignmentAnalyzer** (New Class)
Analyzes multi-timeframe alignment:
- Loads weekly candles for each daily signal
- Detects weekly VCP setups at the same timepoint
- Checks for weekly breakouts and near-breakout continuations
- Returns alignment context with bonus score and reason code

```java
MultiTimeframeContext alignment = 
    alignmentAnalyzer.analyzeAlignmentForDaily(symbol, setup, dailyCandles);
if (alignment.alignmentBonus > 0.0) {
    result.setAlignmentBonus(alignment.alignmentBonus, alignment.alignmentReason, true);
}
```

#### 2. **ScanResult & WatchlistResult** (Enhanced)
Updated to track and report alignment metadata:
- `alignmentBonus`: Score boost applied (0-15 points)
- `alignmentReason`: Reason code (e.g., "DAILY_BREAKOUT_WEEKLY_BREAKOUT")
- `weeklyAligned`: Boolean flag for easy filtering

```java
// Quality score now includes alignment bonus
public double getQualityScore() {
    return setup.getQualityScore() + alignmentBonus;
}
```

#### 3. **ScannerEngine** (Modified)
Now calls alignment analyzer when evaluating signals:
- Only applies to daily scans (weekly scans skip alignment to avoid double-counting)
- Graceful error handling (if weekly data unavailable, continues without bonus)
- Non-breaking (existing signals without alignment still work)

---

## Console Output

Results now show alignment information at the end:

```
AAPL | Type BREAKOUT | Setup VCP | Window 60(60) | ... | Score 47.3 | ... [MTF: DAILY_BREAKOUT_WEEKLY_BREAKOUT (+15.0)]
```

**Tags Explained:**
- `[MTF: DAILY_BREAKOUT_WEEKLY_BREAKOUT (+15.0)]` → Both timeframes aligned, strong entry
- `[MTF: DAILY_BREAKOUT_WEEKLY_VALID_BASE (+5.0)]` → Daily confirmed, weekly supportive
- No tag → Daily signal without weekly alignment

---

## Bonus Structure Justification

### Why These Bonus Values?

**15-point bonus (Daily + Weekly breakout):**
- Both timeframes showing breakout confirmation = maximum confidence
- Eliminates one common false breakout scenario: daily breakout against weekly resistance
- Recommended: prioritize trades with this alignment in live trading

**10-point bonus (Daily + Weekly near-breakout):**
- Daily has momentum; weekly in intermediate continuation zone
- Slightly lower confidence than full alignment but still strong
- Good for portfolios targeting higher volume of quality setups

**5-point bonus (Daily + Weekly valid base):**
- Daily breakout confirmed; weekly has structure but no breakout yet
- Conservative bonus; weekly may still provide support
- Useful for stocks in early breakout phase across both timeframes

**0-point bonus (No weekly setup):**
- Daily signal exists but weekly has no qualifying setup
- Not filtered out (maintains backward compatibility)
- Can still trade, but lower confidence; track separately in backtests

---

## Usage Examples

### Example 1: Viewing Aligned Signals
```bash
java Main -m scan -t daily -s all 2>&1 | grep "MTF:"
```
Shows only signals with multi-timeframe alignment.

### Example 2: Backtesting With Alignment
```bash
java Main -m backtest -t daily -s all --lookback 252
```
Backtest results now include alignment-boosted scores, showing if aligned trades perform better.

### Example 3: Filtering Watchlist
Filter your watchlist to show only items with weekly support:
```bash
# Results with "[MTF:" suffix indicate weekly alignment
java Main -m watchlist -t daily -s all
```

---

## Data Flow

```
┌─ Daily Scan ────────────────────────────┐
│ Detect daily VCP setup                   │
│ Check for daily breakout/near-breakout   │
│                                          │
│ ↓ (if valid daily signal)                │
│                                          │
│ ┌─ MultiTimeframeAlignmentAnalyzer      │
│ │ Load weekly candles (double lookback)  │
│ │ Detect weekly VCP setup                │
│ │ Check for weekly breakout/near-breakout│
│ │ Calculate alignment bonus              │
│ │                                        │
│ │ Returns:                               │
│ │  - weeklyAvailable (bool)              │
│ │  - weeklySetupExists (bool)            │
│ │  - weeklyBreakout (bool)               │
│ │  - alignmentBonus (0-15 pts)           │
│ │  - alignmentReason (enum)              │
│ └────────────────────────────────────────┘
│                                          │
│ ↓ (if bonus > 0)                         │
│                                          │
│ Apply bonus to ScanResult:               │
│ result.setAlignmentBonus(bonus, reason)  │
│                                          │
└──────────────────────────────────────────┘
      ↓
Results sorted by getQualityScore()
(which includes alignment bonus)
      ↓
Output with MTF tag in console
```

---

## Safety & Backward Compatibility

✅ **Safe Approach:**
- No hard filters; bonuses only (scores are additive)
- Existing workflows unaffected
- If weekly data unavailable, signal still trades (no bonus)
- Errors in alignment calculation caught and logged

✅ **Non-Breaking:**
- Old code that doesn't set alignment bonus still works
- Quality score calculation includes zero bonus automatically
- Weekly scans skip alignment (avoids double-analysis)

---

## Future Enhancements

Once backtests confirm alignment improves performance:

1. **Hard Filter (Optional):**
   ```java
   // Require weekly alignment for low-confidence daily setups
   if (dailyScore < 40.0 && !weeklyAligned) {
       return null; // Filter out
   }
   ```

2. **Configurable Bonuses:**
   ```java
   // Adjust bonuses via AppConfig for different strategies
   public final double mtfStrongBonus = 15.0;
   public final double mtfModerateBonus = 10.0;
   ```

3. **Advanced Alignment:**
   - Intra-week correlation scores
   - Volume profile alignment
   - Support/resistance level alignment across timeframes

---

## Files Modified

| File | Change |
|------|--------|
| `ScanResult.java` | Added alignment fields, getter/setter, updated console output |
| `WatchlistResult.java` | Added alignment fields, getter/setter, updated console output |
| `ScannerEngine.java` | Initialize analyzer, call alignment analysis in evaluation methods |
| `MultiTimeframeAlignmentAnalyzer.java` | **New** - Implements alignment logic |

---

## Testing Recommendations

1. **Sanity Check:**
   ```bash
   java Main -m scan -t daily | head -5
   # Verify console output shows [MTF:...] tags for aligned signals
   ```

2. **Bonus Validation:**
   Run scan and confirm score = base_setup_score + alignment_bonus

3. **Backtest Comparison:**
   - Backtest with alignment-boosted scores
   - Backtest with original scores (disable bonus)
   - Compare Win% and R-multiple distribution

4. **Weekly Data Robustness:**
   - Test with stocks missing weekly data
   - Verify graceful fallback (no bonus, no error)

---

## Integration Notes

The alignment analyzer runs automatically in ScannerEngine.scan() and ScannerEngine.scanWatchlist().

**Performance:**
- Minimal overhead (one additional weekly data load per signal)
- ~100-200ms per signal for remote data providers
- Cached data providers much faster

**Configuration:**
- Uses existing `config.lookbackDays` for weekly data window
- Applies global `config.minQualityScore` to weekly setups
- No new config values required (conservative defaults used)

