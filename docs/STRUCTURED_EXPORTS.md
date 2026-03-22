# Structured Export System - Complete Guide

**Date:** March 22, 2026  
**Status:** ✅ Production Ready  
**Purpose:** Replace fragile console parsing with robust JSON/CSV exports

---

## Overview

The **StructuredExporter** provides machine-readable JSON and CSV exports instead of fragile console output parsing.

**Why this matters:**
- ✅ Python orchestration can parse structured data reliably
- ✅ No hidden bugs from text changes
- ✅ Easy to extend with new fields
- ✅ Foundation for ML/ranking systems
- ✅ Proper separation of concerns

---

## Export Types

### 1. **Scan Hits** (Breakout Signals)
Complete data for each breakout signal found.

```json
{
  "symbol": "AAPL",
  "signalType": "BREAKOUT",
  "baseScore": 45.0,
  "alignmentBonus": 15.0,
  "finalScore": 62.3,
  "qualityRating": "EXCELLENT",
  "qualityScore": 38.5
}
```

**What's included:**
- Symbol and signal type (BREAKOUT / NEAR_BREAKOUT)
- All three score components (base, alignment, quality)
- Quality rating and individual quality score

### 2. **Watchlist Items** (Pre-Breakout)
Opportunities before breakout occurs.

```json
{
  "symbol": "MSFT",
  "baseScore": 42.0,
  "alignmentBonus": 5.0,
  "finalScore": 50.2,
  "qualityRating": "STRONG",
  "qualityScore": 28.2
}
```

### 3. **Rejections** (Signals Skipped)
Why signals were filtered out.

```json
{
  "symbol": "GOOG",
  "rejectionType": "FAILED_QUALITY",
  "reason": "Quality score 38.5 < minimum 40.0"
}
```

**Rejection types:**
- `FAILED_QUALITY` - Score below threshold
- `NO_BREAKOUT` - Setup detected but no breakout
- `DATA_ERROR` - Data quality issues prevent analysis
- `INSUFFICIENT_DATA` - Not enough historical candles

### 4. **Metadata** (Scan Execution Details)
Information about the scan run.

```json
{
  "timestamp": "2026-03-22T14:30:45",
  "mode": "scan",
  "timeframe": "daily",
  "lookbackDays": 252,
  "setupFilter": "both",
  "totalSymbols": 500,
  "executionTimeMs": 12450,
  "version": "1.0"
}
```

### 5. **Data Quality Summary**
Overview of data validation across all symbols.

```json
{
  "totalScanned": 500,
  "clean": 485,
  "warnings": 12,
  "errors": 3
}
```

---

## JSON Export Format

### Single File: `scan.json`

Contains everything: metadata, hits, watchlist, rejections, data quality.

```json
{
  "metadata": { ... },
  "hits": [ ... ],
  "watchlist": [ ... ],
  "rejections": [ ... ],
  "dataQuality": { ... }
}
```

**Usage:**
```bash
java Main -m scan -t daily --export=json --out=output/scan
# Generates: output/scan_scan.json
```

---

## CSV Export Format

### Four Separate Files

#### 1. `hits.csv`
```csv
symbol,signalType,baseScore,alignmentBonus,finalScore,qualityRating,qualityScore
AAPL,BREAKOUT,45.0,15.0,62.3,EXCELLENT,38.5
MSFT,BREAKOUT,42.0,5.0,50.2,STRONG,28.2
```

#### 2. `watchlist.csv`
```csv
symbol,baseScore,alignmentBonus,finalScore,qualityRating,qualityScore
GOOG,38.0,0.0,38.0,FAIR,17.8
TSLA,35.5,8.0,43.5,GOOD,21.2
```

#### 3. `rejections.csv`
```csv
symbol,rejectionType,reason
NVDA,FAILED_QUALITY,"Quality score 38.5 < minimum 40.0"
AMD,DATA_ERROR,"Duplicate dates detected"
INTEL,NO_BREAKOUT,"Setup detected but no breakout signal"
```

#### 4. `metadata.csv`
```csv
key,value
timestamp,2026-03-22T14:30:45
mode,scan
timeframe,daily
lookbackDays,252
setupFilter,both
totalSymbols,500
executionTimeMs,12450
```

**Usage:**
```bash
java Main -m scan -t daily --export=csv --out=output/scan
# Generates: output/scan_hits.csv, output/scan_watchlist.csv, etc.
```

---

## Command Line Usage

### Export as JSON (Recommended)
```bash
java Main -m scan -t daily --export=json --out=output/signals
# Output: output/signals_scan.json
```

### Export as CSV
```bash
java Main -m scan -t daily --export=csv --out=output/signals
# Output: output/signals_hits.csv, output/signals_watchlist.csv, etc.
```

### No Export (Console Only)
```bash
java Main -m scan -t daily --export=none
# Only prints to console
```

---

## Python Integration Examples

### Example 1: Load and Parse JSON

```python
import json
import datetime

# Load export
with open('output/signals_scan.json', 'r') as f:
    data = json.load(f)

# Process metadata
print(f"Scan completed: {data['metadata']['timestamp']}")
print(f"Found {len(data['hits'])} signals")
print(f"Data quality: {data['dataQuality']['clean']}/{data['dataQuality']['totalScanned']} clean")

# Process hits
for signal in data['hits']:
    print(f"{signal['symbol']}: Score {signal['finalScore']:.1f} ({signal['qualityRating']})")
    
    # Apply ML ranking
    ml_score = calculate_ml_score(signal)
    
    # Store in database
    store_signal(signal, ml_score)
```

### Example 2: Load CSV with Pandas

```python
import pandas as pd

# Load all files
hits = pd.read_csv('output/signals_hits.csv')
watchlist = pd.read_csv('output/signals_watchlist.csv')
rejections = pd.read_csv('output/signals_rejections.csv')
metadata = pd.read_csv('output/signals_metadata.csv', index_col='key')

# Filter for strong signals only
strong_hits = hits[hits['qualityRating'].isin(['EXCELLENT', 'STRONG'])]
print(f"Strong signals: {len(strong_hits)}")

# Analyze alignment impact
alignment_avg = hits.groupby('qualityRating')['alignmentBonus'].mean()
print(f"Avg alignment bonus by rating:\n{alignment_avg}")

# Calculate expected returns based on quality
hits['expected_return'] = calculate_expected_return(hits)
hits_sorted = hits.sort_values('expected_return', ascending=False)
```

### Example 3: Real-Time Monitoring

```python
import json
import time
from datetime import datetime

# Monitor scan results over time
results_history = []

while True:
    # Run scan
    os.system('java Main -m scan -t daily --export=json --out=daily_scan')
    
    # Load results
    with open('daily_scan_scan.json', 'r') as f:
        data = json.load(f)
    
    # Track metrics
    metric = {
        'timestamp': data['metadata']['timestamp'],
        'hits': len(data['hits']),
        'watchlist': len(data['watchlist']),
        'excellent': sum(1 for s in data['hits'] if s['qualityRating'] == 'EXCELLENT'),
        'avg_score': sum(s['finalScore'] for s in data['hits']) / len(data['hits']) if data['hits'] else 0
    }
    
    results_history.append(metric)
    
    # Alert if low quality
    if metric['excellent'] < 3:
        send_alert(f"Only {metric['excellent']} EXCELLENT signals today")
    
    # Wait for next scan
    time.sleep(3600)  # 1 hour
```

### Example 4: Database Storage

```python
import json
import sqlite3

conn = sqlite3.connect('signals.db')
cursor = conn.cursor()

# Load export
with open('output/signals_scan.json', 'r') as f:
    data = json.load(f)

# Store metadata
cursor.execute('''
    INSERT INTO scans (timestamp, mode, timeframe, total_symbols, execution_time)
    VALUES (?, ?, ?, ?, ?)
''', (
    data['metadata']['timestamp'],
    data['metadata']['mode'],
    data['metadata']['timeframe'],
    data['metadata']['totalSymbols'],
    data['metadata']['executionTimeMs']
))

scan_id = cursor.lastrowid

# Store signals
for signal in data['hits']:
    cursor.execute('''
        INSERT INTO signals (scan_id, symbol, signal_type, base_score, alignment_bonus, final_score, quality_rating)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        scan_id,
        signal['symbol'],
        signal['signalType'],
        signal['baseScore'],
        signal['alignmentBonus'],
        signal['finalScore'],
        signal['qualityRating']
    ))

conn.commit()
conn.close()
```

---

## Data Schema Reference

### SignalExport
```
symbol: str
signalType: str (BREAKOUT | NEAR_BREAKOUT)
baseQualityScore: float (VCP setup score)
alignmentBonus: float (0-15)
finalScore: float (base + alignment + quality bonus)
breakoutQualityRating: str (EXCELLENT | STRONG | GOOD | FAIR | WEAK)
breakoutQualityScore: float (0-40)
setup: SetupDetails
breakout: BreakoutDetails
tradePlan: TradePlanDetails
dataQuality: DataQualityIssues
```

### WatchlistExport
```
symbol: str
baseQualityScore: float
alignmentBonus: float
finalScore: float
breakoutQualityRating: str
breakoutQualityScore: float
setup: SetupDetails
watchlist: WatchlistDetails
tradePlan: TradePlanDetails
dataQuality: DataQualityIssues
```

### RejectionExport
```
symbol: str
rejectionReason: str
rejectionType: str (FAILED_QUALITY | NO_BREAKOUT | DATA_ERROR | INSUFFICIENT_DATA)
detailedScore: float
details: str
```

---

## Advantages Over Console Parsing

| Aspect | Console Parsing | Structured Export |
|--------|-----------------|-------------------|
| **Robustness** | Fragile (any format change breaks) | Robust (structured schema) |
| **Performance** | Slow (regex parsing) | Fast (direct parsing) |
| **Extensibility** | Hard (change format = rewrite parser) | Easy (add fields to schema) |
| **Error Handling** | Difficult (text is ambiguous) | Clear (structured errors) |
| **ML Integration** | Manual feature extraction | Automatic structured features |
| **Data Quality** | Hidden (parsed manually) | Explicit (included in export) |
| **Debugging** | Hard (parse failures unclear) | Easy (validate against schema) |

---

## Implementation Details

### Export Generation
```
ScanResult objects
  ↓
buildScanExportData() converts to export format
  ↓
StructuredExporter.exportAsJson() or .exportAsCsv()
  ↓
Write to files
  ↓
Python loads and parses structured data
```

### File Locations
```
output/
  ├── signals_scan.json          (JSON: all data)
  ├── signals_hits.csv           (CSV: breakout signals)
  ├── signals_watchlist.csv      (CSV: watchlist)
  ├── signals_rejections.csv     (CSV: why rejected)
  └── signals_metadata.csv       (CSV: scan info)
```

---

## Best Practices

1. **Always use JSON for new integrations**
   - More expressive than CSV
   - Supports nested structures
   - Self-documenting

2. **Use CSV for data analysis**
   - Works with Excel, Pandas, R
   - Easy spreadsheet import
   - Good for quick analysis

3. **Validate before processing**
   ```python
   try:
       data = json.load(f)
       assert 'metadata' in data
       assert 'hits' in data
   except (json.JSONDecodeError, AssertionError) as ex:
       logger.error(f"Invalid export format: {ex}")
   ```

4. **Version your schemas**
   - Check `version` in metadata
   - Handle migrations gracefully

5. **Cache exports**
   - Store exports by timestamp
   - Compare with previous runs
   - Detect changes/anomalies

---

## Troubleshooting

### Export file not created?
- Check permissions on `output/` directory
- Verify `--export` parameter is set
- Look for error messages in console output

### JSON parsing fails?
- Validate JSON: `python -m json.tool signals_scan.json`
- Check for escape characters
- Ensure file is complete (not truncated)

### CSV has extra columns/rows?
- Expected, additional fields added over time
- Use `index_col` in pandas for metadata
- Parse dynamically if schema changes

---

## Version History

### v1.0 (Current)
- Initial release
- JSON and CSV export
- All scan data included

---

*Structured Exports | Machine-Readable | Production Ready | Python-Compatible*

