# Data Quality Checks - Complete Documentation

**Date:** March 22, 2026  
**Status:** ✅ Production Ready  
**Purpose:** Validate market data integrity before analysis

---

## Overview

The **DataQualityChecker** validates market candles for 5 critical data issues that could skew analysis and create false signals.

**Philosophy:** Check data quality automatically, warn about issues, but allow processing to continue (except for critical errors).

---

## Five Data Quality Checks

### 1. **Duplicate Dates** ❌ ERROR

**What it detects:** Multiple candles with the same date.

**Why it matters:**
- Duplicate entries skew volume calculations (counted twice)
- Price analysis becomes unreliable
- Indicators produce incorrect values

**Example:**
```
2024-01-15: OHLC 100/105/98/102, Vol 1M
2024-01-15: OHLC 100/105/98/102, Vol 1M  ← DUPLICATE
```

**Impact:** Immediate error - data unusable as-is
**Action:** System flags and logs duplicate dates

---

### 2. **Missing Bars** ⚠️ WARNING

**What it detects:** Gaps in date sequence beyond expected weekends/holidays.

**Why it matters:**
- Lookback windows become inaccurate
- 50-bar average might only be 45 days of actual data
- Indicators use fewer bars than expected
- Holiday/market closures OK (up to 4-day gaps expected)
- Gaps >4 days indicate missing data

**Example:**
```
2024-01-15: Daily candle
2024-01-16: Daily candle
2024-01-22: Daily candle  ← 6-day gap! (should be 1 day)
```

**Impact:** Moderate - affects lookback accuracy
**Threshold:** Flag gaps >4 days
**Action:** System logs gap size and dates

---

### 3. **Broken Volume Spikes** ⚠️ WARNING / ❌ ERROR

**What it detects:** Abnormal volume patterns.

**Why it matters:**
- Volume spikes used for breakout confirmation
- Abnormal spikes trigger false breakout signals
- Zero volume = no actual trade activity
- Negative volume = data corruption

**Sub-checks:**

**A) Zero or Negative Volume** → ERROR
```
2024-01-15: Vol = 0        ← ERROR: No trading
2024-01-16: Vol = -100000  ← ERROR: Data corruption
```

**B) Volume Spike (>5x median)**  → WARNING
```
20-bar median volume: 1M shares
2024-01-15: Vol = 5.2M shares  ← WARNING: 5.2x spike
```
Potential causes: earnings announcement, stock split event, data error

**C) Volume Drought (<0.1x median)** → WARNING
```
20-bar median volume: 1M shares
2024-01-15: Vol = 50K shares  ← WARNING: 0.05x drought
```
Potential causes: market halt, illiquid period, incomplete data

**Impact:** High - breaks volume analysis
**Threshold:** >5x or <0.1x of 20-bar median
**Action:** System logs volume ratio

---

### 4. **Split-Adjustment Issues** ⚠️ WARNING

**What it detects:** Price changes without corresponding volume change (unadjusted stock split).

**Why it matters:**
- Unadjusted splits break all technical analysis
- Entry/exit prices become wrong (e.g., 2-for-1 split = entry at 50% of actual)
- VCP detection fails
- Pivot prices calculated incorrectly

**How it works:**
```
Detection Logic:
- Compare 5-day price change vs 5-day volume change
- If price changed >30% but volume unchanged (<15% change):
  → Suspect unadjusted stock split
```

**Example:**
```
2024-01-10 through 2024-01-14:
  Price: $50 → $150 (3x increase)
  Volume: 1M, 1M, 1M, 1M, 1M (stable, no change)
  
  → WARNING: Suspected unadjusted 3-for-1 split!
```

**Impact:** Critical - invalidates all analysis after split
**Action:** System logs price change % and recommends data verification

---

### 5. **Abnormal Candles** ❌ ERROR / ⚠️ WARNING

**What it detects:** Impossible or extreme OHLC relationships.

**Why it matters:**
- Impossible relationships = data corruption
- Extreme relationships = incomplete/halted trading
- Affects setup detection and pivot calculation

**Sub-checks:**

**A) Reversed Candle** → ERROR
```
High: 100
Low:  105  ← ERROR: High < Low (impossible!)
```

**B) OHLC Outside Range** → ERROR
```
Range: [98, 102]
Open: 97       ← ERROR: Outside range
Close: 103     ← ERROR: Outside range
```

**C) Extreme Wicks** → WARNING
```
Body: $0.50 (close to open)
Range: $5.00 (high to low)
Wick: 10x body size  ← WARNING: Suspicious extreme wick
```
Potential causes: gap fill, data spike, halt at specific price

**D) Zero-Range Candles** → INFO
```
High: 100
Low:  100  ← Zero range (doji-like)
Close: 100

→ INFO: Zero-range candle (might be incomplete/halted)
```

**E) Negative or Zero Prices** → ERROR
```
Open: 0.00     ← ERROR
Close: -5.00   ← ERROR: Negative price!
```

**Impact:** High - breaks all analysis
**Action:** System logs exact issue and prices

---

## Severity Levels

| Severity | Meaning | Action | Example |
|----------|---------|--------|---------|
| **ERROR** | Data unusable | Skip or quarantine symbol | Duplicate date, reversed candle |
| **WARNING** | Proceed with caution | Log and track | Volume spike, suspected split |
| **INFO** | Note for reference | Document | Zero-range candle |

---

## Console Output

### Clean Data
```bash
$ java Main -m scan -t daily
✅ AAPL: CLEAN (252 candles)
✅ MSFT: CLEAN (252 candles)
```

### Data with Issues
```bash
$ java Main -m scan -t daily
⚠️  AAPL: VALID (with warnings) (3 issues in 252 candles):
  • VOLUME_SPIKE_UP: 2
  • MISSING_BARS: 1

❌ GOOG: INVALID (4 issues in 180 candles):
  • DUPLICATE_DATE: 1
  • REVERSED_CANDLE: 2
  • INVALID_VOLUME: 1
```

---

## Usage Examples

### 1. Basic Validation
```java
// In your code
DataQualityChecker checker = new DataQualityChecker();
DataQualityChecker.DataQualityReport report = checker.validate("AAPL", candles);

if (!report.isValid) {
    System.err.println("Data quality issues found!");
    System.err.println(report);
}
```

### 2. Check Specific Issue Type
```java
for (DataQualityChecker.DataQualityIssue issue : report.issues) {
    if (issue.type.equals("DUPLICATE_DATE")) {
        System.out.println("Duplicate found: " + issue.date);
    }
}
```

### 3. Get Summary
```java
String summary = checker.getSummary(report);
System.out.println(summary);
```

Output:
```
⚠️  AAPL (3 issues):
  • VOLUME_SPIKE_UP: 2
  • MISSING_BARS: 1
```

### 4. Filter Only Errors
```java
List<DataQualityChecker.DataQualityIssue> errors = report.issues.stream()
    .filter(i -> i.severity == DataQualityChecker.DataQualityIssue.Severity.ERROR)
    .collect(Collectors.toList());

if (!errors.isEmpty()) {
    System.err.println("Critical data issues: " + errors.size());
    for (DataQualityChecker.DataQualityIssue error : errors) {
        System.err.println("  " + error.description);
    }
}
```

---

## Integration Points

### Automatic Checks

**1. When loading daily candles (YahooFinanceProvider):**
```
fetchFromYahoo() 
  → parseChartResponse() 
  → validate with DataQualityChecker 
  → log issues if found 
  → cache data
```

**2. When loading candles in scanner (ScannerEngine):**
```
loadCandles() 
  → marketDataProvider.getDailyCandles() / getWeeklyCandles() 
  → validate with DataQualityChecker 
  → log errors 
  → continue with scan
```

### Manual Checks (Optional)

You can also manually check anytime:
```java
DataQualityChecker checker = new DataQualityChecker();
DataQualityChecker.DataQualityReport report = checker.validate(symbol, candles);
System.out.println(report);  // Print full report
```

---

## Thresholds & Tuning

### Current Thresholds

```
Missing Bars:
  - Max expected gap: 4 days (covers weekends)
  
Volume Spike:
  - Spike threshold: 5.0x median
  - Drought threshold: 0.1x median
  
Stock Split Detection:
  - Price change threshold: 30%
  - Volume stability threshold: 15%
  
Extreme Wick:
  - Wick/body ratio: >10.0x
```

### To Adjust Thresholds

Edit DataQualityChecker.java:
```java
// Missing bars check
int maxExpectedGap = 4;  // Change this (in days)

// Volume spike check
if (volumeRatio > 5.0) { ... }     // Change 5.0
if (volumeRatio < 0.1) { ... }     // Change 0.1

// Split detection
if (Math.abs(priceChangeRatio - 1.0) > 0.30) { ... }  // Change 0.30
if (Math.abs(volumeChangeRatio - 1.0) < 0.15) { ... } // Change 0.15

// Extreme wick
if (wickRatio > 10.0) { ... }  // Change 10.0
```

Then recompile: `javac src/DataQualityChecker.java`

---

## Real-World Examples

### Example 1: Clean Data
```
✅ AAPL (252 candles, 1 year of data)
No issues found
→ Ready for analysis
```

### Example 2: Volume Spike (Earnings)
```
⚠️  MSFT with warnings:
  VOLUME_SPIKE_UP on 2024-01-18 (7.2x normal)
  
Reason: Earnings announcement
Action: OK to proceed (market event, not data issue)
```

### Example 3: Suspected Split (Unadjusted)
```
⚠️  GOOG with warning:
  SUSPECTED_SPLIT on 2024-03-22 (price +35%, volume stable)
  
Reason: Possible 2-for-1 split not adjusted in data
Action: Verify with data provider, request adjusted prices
```

### Example 4: Critical Error (Duplicate Date)
```
❌ TSLA: INVALID
  DUPLICATE_DATE on 2024-02-14
  ERROR: Duplicate date found at index 128
  
Reason: Data duplication from provider
Action: Skip symbol, contact provider, or reload data
```

---

## Recommendations by Issue

| Issue | Recommend | Reason |
|-------|-----------|--------|
| Duplicate dates | Skip symbol | Can't fix without redownloading |
| Missing bars | Proceed with caution | Affects accuracy but not fatal |
| Volume spikes | Proceed | Market events are normal |
| Volume drought | Check for halts | May be legitimate |
| Suspected splits | Verify & re-download | Need adjusted prices |
| Zero volume | Skip candle | Invalid data point |
| Extreme wicks | Investigate | May be legitimate or data issue |
| Zero-range candle | Info only | May be halt or incomplete day |

---

## Best Practices

1. **Check at Load Time**
   - Data is validated when loaded
   - Issues are logged automatically
   - No need for manual checks

2. **Monitor Warnings**
   - Volume spikes on earnings days = OK
   - Volume droughts on holidays = OK
   - Repeated errors = investigate

3. **Skip Critical Errors**
   - If DUPLICATE_DATE or REVERSED_CANDLE → skip symbol
   - These indicate data corruption

4. **Track Over Time**
   - Watch for patterns in issues
   - If provider degrading, switch sources

5. **Adjust Thresholds if Needed**
   - Default thresholds work for US equities
   - Crypto might need >5x volume spike threshold
   - Illiquid stocks might need <0.1x threshold

---

## Technical Details

### Data QualityChecker Class

```java
public class DataQualityChecker {
    // Main method
    public DataQualityReport validate(String symbol, List<Candle> candles)
    
    // Individual checkers (private)
    private void checkDuplicateDates(List<Candle> candles, DataQualityReport report)
    private void checkMissingBars(List<Candle> candles, DataQualityReport report)
    private void checkVolumeSpikes(List<Candle> candles, DataQualityReport report)
    private void checkSplitAdjustmentIssues(List<Candle> candles, DataQualityReport report)
    private void checkAbnormalCandles(List<Candle> candles, DataQualityReport report)
    
    // Helpers
    private double getMedian(double[] values)
    public String getSummary(DataQualityReport report)
    
    // Data classes
    public static class DataQualityReport { ... }
    public static class DataQualityIssue { ... }
}
```

### Integration Points

1. **YahooFinanceProvider.getDailyCandles()** - checks after fetch
2. **ScannerEngine.loadCandles()** - checks before analysis

---

## Next Steps

1. **Monitor**
   - Run scans and observe data quality reports
   - Track which symbols have issues

2. **Validate**
   - If seeing many DUPLICATE_DATE errors → switch provider
   - If seeing SUSPECTED_SPLIT → verify with adjusted data

3. **Adjust**
   - Modify thresholds if needed for your universe
   - Recompile and test

4. **Integrate**
   - Can export quality reports to CSV
   - Track data quality trends over time
   - Alert on deteriorating data sources

---

*Data Quality Validation | Production Ready | Automatic Checking*

