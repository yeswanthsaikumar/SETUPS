# Data Quality Checks - Quick Reference

**5 Critical Checks | Automatic Validation | Production Ready**

---

## The 5 Checks at a Glance

| # | Check | Severity | Detects | Impact |
|---|-------|----------|---------|--------|
| 1 | **Duplicate Dates** | ❌ ERROR | Multiple candles same date | Double-counted volume, invalid analysis |
| 2 | **Missing Bars** | ⚠️ WARNING | Gaps >4 days in sequence | Inaccurate lookback windows |
| 3 | **Broken Volume** | ⚠️ WARNING / ❌ ERROR | Spikes >5x or <0.1x, zero volume | False breakout signals |
| 4 | **Split Issues** | ⚠️ WARNING | Price ±30% but volume stable | Unadjusted split invalidates analysis |
| 5 | **Abnormal Candles** | ⚠️ WARNING / ❌ ERROR | Reversed OHLC, extreme wicks, zero range | Bad setup detection, wrong pivots |

---

## How It Works

### Automatic Checking
```
Data loads from Yahoo Finance
    ↓
DataQualityChecker validates
    ↓
Issues logged with severity level
    ↓
Data cached (if not critical error)
    ↓
Scanner proceeds with analysis
```

### Console Output Examples

**Clean:**
```
✅ AAPL: CLEAN (252 candles)
```

**With Warnings:**
```
⚠️  MSFT: VALID (with warnings) (2 issues)
  • VOLUME_SPIKE_UP: 1
  • MISSING_BARS: 1
```

**Invalid (Critical Error):**
```
❌ GOOG: INVALID (4 issues)
  • DUPLICATE_DATE: 1
  • REVERSED_CANDLE: 2
  • INVALID_VOLUME: 1
```

---

## Key Thresholds

| Check | Threshold | Meaning |
|-------|-----------|---------|
| Missing bars | >4 days gap | Weekends OK, >4 days = flag |
| Volume spike | >5x median | 5x or more = warning |
| Volume drought | <0.1x median | Less than 1/10th normal = warning |
| Split detection | Price ±30% | Major price move without volume = suspect split |
| Extreme wick | >10x body | Wick 10x larger than body = suspicious |

---

## Quick Troubleshooting

### Seeing DUPLICATE_DATE errors?
→ Data provider issue. Switch providers or request corrected data.

### Seeing MISSING_BARS warnings?
→ Probably holidays. Check calendar. If unexpected, investigate provider.

### Seeing VOLUME_SPIKE_UP on earnings day?
→ Totally normal. This is expected behavior on earnings announcements.

### Seeing SUSPECTED_SPLIT warning?
→ Verify manually. Request adjusted prices from data provider.

### Seeing ABNORMAL_CANDLE errors?
→ Data corruption. Skip symbol or request re-download.

---

## Usage

### See All Data Quality Issues
```bash
java Main -m scan -t daily
# Look for quality report output
```

### Check Specific Symbol
```java
DataQualityChecker checker = new DataQualityChecker();
DataQualityChecker.DataQualityReport report = checker.validate("AAPL", candles);
System.out.println(report);
```

### Get Quick Summary
```java
String summary = checker.getSummary(report);
System.out.println(summary);
```

---

## When to Take Action

| Issue | Action | Urgency |
|-------|--------|---------|
| ERROR severity | Skip symbol or re-download | HIGH |
| WARNING on single day | Investigate / monitor | MEDIUM |
| WARNING recurring | Monitor trend / switch provider | MEDIUM |
| INFO severity | Just log / ignore | LOW |

---

## Impact on Your Analysis

### If data has ERRORS:
- ❌ VCP detection unreliable
- ❌ Pivot prices wrong
- ❌ Volume confirmation invalid
- ❌ Entry/exit prices incorrect

### If data has WARNINGS:
- ⚠️ Results valid but check assumptions
- ⚠️ Monitor for patterns
- ⚠️ May be legitimate market events

### If data is CLEAN:
- ✅ Full confidence in analysis
- ✅ Proceed with backtesting
- ✅ Ready for live trading

---

## Files Involved

| File | Role |
|------|------|
| `DataQualityChecker.java` | Validation engine |
| `YahooFinanceProvider.java` | Checks after fetch |
| `ScannerEngine.java` | Checks before analysis |

---

## Documentation

- **DATA_QUALITY_CHECKS.md** (this file) - Quick reference
- **DATA_QUALITY_FULL.md** - Complete documentation with examples

---

**Status: ✅ Automatic | Production Ready | Zero Configuration Needed**

