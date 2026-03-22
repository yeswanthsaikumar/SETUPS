# Improved Breakout Quality Filters - Quick Summary

## What You Got

Four advanced breakout quality analysis dimensions that work together to identify highest-confidence trades:

### 1. **Volume Percentile** (0-10 pts)
- Where breakout volume ranks in 50-bar distribution
- 80%+ percentile = 10 pts (exceptional)
- <30% percentile = 1 pt (weak)

### 2. **Pivot Freshness** (0-10 pts)  
- How many times price tested the pivot
- Virgin pivot (1 test) = 10 pts
- Exhausted pivot (10+ tests) = 1 pt

### 3. **Distance from Pivot** (0-10 pts)
- How far above pivot the breakout closed
- Close to pivot (0.5%) = 10 pts (pristine)
- Far extended (3.5%+) = 1 pt (missed entry)

### 4. **Tightness Quality** (0-10 pts)
Composite of three sub-metrics:
- **Close Clustering** - recent range vs baseline range
- **ATR Shrinkage** - recent ATR vs baseline ATR (volatility compression)
- **Pullback Depth** - recent pullback depth vs baseline

**Total Score: 0-40 points**

---

## Quality Ratings

| Score | Rating | Meaning |
|-------|--------|---------|
| 32-40 | **EXCELLENT** | Pristine setup ✅ |
| 26-31 | **STRONG** | Good setup ✓ |
| 20-25 | **GOOD** | Tradeable ✓ |
| 14-19 | **FAIR** | Marginal ⚠️ |
| <14 | **WEAK** | Lower confidence ❌ |

---

## Console Output

Each signal now shows breakout quality:

```
AAPL | Type BREAKOUT | ... | Score 47.3 [BQ: EXCELLENT (38.5/40)]
MSFT | Type BREAKOUT | ... | Score 42.1 [BQ: STRONG (28.2/40)]
GOOG | Type BREAKOUT | ... | Score 38.5 [BQ: FAIR (17.8/40)]
```

---

## How to Use

### 1. View Quality in Scans
```bash
java Main -m scan -t daily | head -10
# Look for [BQ: RATING (score/40)] tags
```

### 2. Get Detailed Report
```java
System.out.println(scanResult.getBreakoutQualityReport());
```

### 3. Filter by Quality (Optional)
```java
// Strict mode: only trade high-quality breakouts
if (breakoutEvaluator.passesQualityFilter(quality, strictMode=true)) {
    // Trade it
}
```

Strict mode filters require:
- Volume: ≥50th percentile
- Pivot: <8 tests (not exhausted)
- Distance: ≤2% from pivot
- Tightness: ≥5.0/10

---

## Files Modified

| File | Changes |
|------|---------|
| `BreakoutQualityAnalyzer.java` | **NEW** (220 lines) - Complete analysis engine |
| `BreakoutEvaluator.java` | +50 lines - Initialize analyzer, add quality methods |
| `ScanResult.java` | +30 lines - Track quality context, add report method |
| `ScannerEngine.java` | +5 lines - Call quality analysis |

---

## Why Each Dimension Matters

**Volume Percentile:**
- Adapts to stock's volume profile (not one-size-fits-all 1.25x)
- Identifies high-conviction vs low-conviction breakouts
- Weeds out volume squeezes with insufficient demand

**Pivot Freshness:**
- Market makers know about overworked pivots
- Fresh pivots show institutional rejection hasn't occurred
- Failed test pattern = lower success probability

**Distance from Pivot:**
- Entry timing indicator (pristine vs extended)
- Risk/reward worsens as distance increases
- 2%+ above pivot often means missed best entry

**Tightness Quality:**
- Consolidated bases trade better than loose ones
- Shrinking volatility = controlled breakout
- Shallow pullbacks = strong bidding; deep ones = weakness

---

## Backtest Strategy

### Phase 1: Observe Quality Distribution
```bash
java Main -m scan -t daily | grep BQ
```
Expected: 5-10% EXCELLENT, 15-25% STRONG, 30-40% GOOD, rest FAIR/WEAK

### Phase 2: Measure Performance by Rating
Backtest and compare:
- Win% by quality rating
- Avg R-multiple by rating  
- Total return by rating

### Phase 3: Make Filtering Decision
- If high ratings outperform: Use strict mode
- If all ratings similar: Keep as soft score bonus
- If clear correlation: Adjust thresholds

### Phase 4: Deploy
- Start trading EXCELLENT/STRONG
- Expand to GOOD after validation
- Size down for FAIR/WEAK

---

## Key Features

✅ **Automatic Analysis** - Every breakout gets scored  
✅ **Conservative** - No signals removed, just ranked  
✅ **Visible** - Console shows quality rating  
✅ **Optional Filtering** - Strict mode available  
✅ **Detailed Reports** - Get breakdown for any signal  
✅ **Backward Compatible** - Existing signals unaffected  

---

## Example Output Comparison

**Before (old system):**
```
AAPL | Type BREAKOUT | ... | Score 47.3
MSFT | Type BREAKOUT | ... | Score 42.1
GOOG | Type BREAKOUT | ... | Score 38.5
```
All treated equally by quality.

**After (new system):**
```
AAPL | Type BREAKOUT | ... | Score 47.3 [BQ: EXCELLENT (38.5/40)]
MSFT | Type BREAKOUT | ... | Score 42.1 [BQ: STRONG (28.2/40)]
GOOG | Type BREAKOUT | ... | Score 38.5 [BQ: FAIR (17.8/40)]
```
Quality differences now visible & used for filtering.

---

## Next Steps

1. **Test it:** `java Main -m scan -t daily | grep BQ`
2. **Read full guide:** `docs/BREAKOUT_QUALITY_FILTERS.md`
3. **Backtest:** Compare EXCELLENT vs WEAK performance
4. **Optimize:** Adjust if needed based on results
5. **Deploy:** Use quality ratings in live trading

---

*Version 1.0 | Four-Dimensional Quality Analysis | Production Ready*

