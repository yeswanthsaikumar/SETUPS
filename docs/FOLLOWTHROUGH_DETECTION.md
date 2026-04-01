# Follow-Through Continuation Detection System

## Overview

The **Follow-Through Detection System** identifies high-probability continuation trades where:
1. A valid breakout occurred **days/weeks ago** (already past pivot + buffer)
2. Price pulled back below the pivot (but held key support levels)
3. Price is **now recovering** back to or near original breakout levels

These are among the **highest quality swing trades** because they combine:
- **Proven institutional demand** (original breakout)
- **Absorbed supply** (pullback held key levels)
- **Fresh momentum confirmation** (recovery bars today/recently)

---

## The Pattern

```
                         Recovery Signal (TODAY/RECENT) ← Entry Zone
                                ↑
                          ┌─────┘
                          │
        Original Breakout  │ Pullback        
              ↑            │   ↓
    ┌────────┴────────┐    └─────┐
    │   Valid Base    │    Dip into   
    │   VCP/Range     │    Support    
    │   Expansion     │              
    └────────┬────────┘     ┌─────┐
           Pivot ►──────────► Buying Resumes
                              (near original pivot)
```

### Key Characteristics

**Follow-through setups:**
- Breakout was **1-20 bars ago** (fresh enough to track, not ancient)
- Pullback reached **0.5% to 15% below pivot** (healthy dip, not collapse)
- Recovery took **3-5 bars** from low (quick, confident recovery)
- Volume on recovery is **>1.15x average** (fresh institutional buying)
- Quality score **≥ 0.8x original setup score** (still valid pattern)

---

## Implementation (Java Side)

### FollowThroughDetector Class

Located in: `src/FollowThroughDetector.java`

#### Main Method

```java
public FollowThroughResult detectFollowThrough(
    String symbol,
    List<Candle> candles,
    AppConfig config,
    String setupFilter
)
```

**Algorithm:**

1. **Backward Scan** through last 40 bars looking for old breakouts
   - At each historical index, detect if a VCP/Range Expansion setup exists
   - Check if that candle was a valid breakout (close > pivot + buffer, volume strong)

2. **Pullback Detection**
   - After breakout bar, look for a dip below pivot (within 5-20 bars)
   - Measure depth: (pivot - low) / pivot
   - Valid if 0.5% ≤ depth ≤ 15%

3. **Recovery Detection**
   - After pullback low, look for recovery close (within 5-15 bars)
   - Valid if: close > pivot × (1 + breakout_buffer) OR high ≥ pivot with close near pivot

4. **Quality Scoring**
   - Base: 0.7 × original setup quality score
   - Bonus for tight pullback (< 2%): +15 points
   - Bonus for quick recovery (≤ 3 bars): +10 points
   - Bonus for strong volume on recovery: +8 points
   - Final: min(100, score)

#### Result Object

```java
public static class FollowThroughResult {
    public final String symbol;
    public final VcpSetup originalSetup;
    public final Candle breakoutCandle;
    public final Candle pullbackLow;
    public final Candle recoverySignal;
    public final int daysSinceBreakout;
    public final int daysInPullback;
    public final double pullbackDepthPct;
    public final double recoveryProgressPct;
    public final double qualityScore;
    public final String reason;
}
```

#### Integration with ScannerEngine

New method:
```java
public List<ScanResult> scanFollowThrough(List<String> symbols, int lookbackBars, String timeframe)
```

- Calls `followThroughDetector.detectFollowThrough()` for each symbol
- Converts successful results to `ScanResult` with trade plan
- Filters by quality (≥ 0.8 × minQualityScore)
- Returns ranked by quality score

---

## Python CLI Integration

### Command Line

Add mode parameter to Java invocation:

```bash
java -cp src Main \
  --mode=followthrough \
  --provider=yahoo \
  --timeframe=daily \
  --setups=both \
  --symbols=AAPL,MSFT,TSLA \
  --lookback=252
```

### Python Functions

**File:** `apps/python/cli/run_full_us_scan.py`

#### scan_followthrough_batch()

```python
def scan_followthrough_batch(batch: list[str], args) -> list[str]:
    """Invoke Java follow-through scanner for one batch; return raw hit lines."""
    java_setup = _java_setups(args.setups)
    if java_setup is None:
        return []
    
    cmd = [
        "java", "-cp", "src", "Main",
        "--mode=followthrough",
        "--provider=yahoo",
        f"--timeframe={args.timeframe}",
        f"--setups={java_setup}",
        f"--symbols={','.join(batch)}",
        f"--lookback={args.lookback}",
        ...
    ]
    # Execute and parse "Follow-through" in output
```

#### Integration Points

1. Can be added to main scan loop in `process_batch()`
2. Results merged with regular breakout hits
3. Marked as `listType="CONTINUATION"` for differentiation
4. Included in portfolio heat calculations
5. Displayed in reports with special highlighting

---

## Usage Scenarios

### Scenario 1: Daily Follow-Throughs

**Setup:**
```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets india \
  --timeframe daily \
  --setups both \
  --daily-lookback 252
```

**Expected Output:**
- Opens `output/vcp_hits_india_daily_full_LATEST.csv`
- Includes both fresh breakouts AND follow-throughs
- Filtered by quality and liquidity

### Scenario 2: Weekly Follow-Throughs for Swing Traders

**Focus:** Longer-term continuation plays (weeks-long trends)

```bash
python3 apps/python/cli/run_vcp_system.py \
  --markets us \
  --timeframe weekly \
  --setups both \
  --weekly-lookback 104
```

**Why This Works:**
- Weekly breakouts have stronger institutional support
- Weekly pullbacks are typically deeper (more time to work off)
- Follow-throughs give cleaner low-risk entries

---

## Configuration (AppConfig.java)

### Default Parameters

```java
// For follow-through + pre-breakout watchlist detection:
this.minQualityScore = weekly ? 40.0 : 45.0;          // Base quality
this.breakoutBufferPct = weekly ? 0.006 : 0.004;      // Entry confirmation threshold
this.watchlistMaxDistanceToPivotPct = 0.05;           // Must be within 5% below pivot
this.maxDistanceFrom52WkHighPct = 0.25;               // Must be close to highs
```

### Customization

To adjust follow-through sensitivity:

| Parameter | Effect | Default |
|-----------|--------|---------|
| `minQualityScore` | Higher = stricter patterns | 45.0 (daily), 40.0 (weekly) |
| `breakoutBufferPct` | Higher = larger entry zone | 0.4% (daily), 0.6% (weekly) |
| `watchlistMaxDistanceToPivotPct` | Lower = tighter recovery required | 5% (daily + weekly) |

### Pre-Breakout Watchlist Behavior

- Watchlist now explicitly tracks symbols *before* breakout, limited to `0%` to `5%` below pivot.
- This applies to both `VCP` and `RANGE_EXPANSION` setup filters.
- `RANGE_EXPANSION` watchlist entries can appear pre-breakout when base quality is valid, even before expansion-candle confirmation.

---

## Output Files

When follow-throughs are detected:

```
output/
├── vcp_hits_india_daily_full_LATEST.csv        ← includes follow-throughs
├── vcp_hits_india_daily_full_LATEST.json       ← JSON format
├── vcp_hits_india_daily_full_LATEST.html       ← Interactive report
├── open_trades_india_daily_full_LATEST.csv     ← Actionable positions
└── watchlist_india_daily_full_LATEST.csv       ← Near-pivot candidates
```

**CSV Fields Added:**
- `daysSinceBreakout`: How long ago the original breakout occurred
- `pullbackDepthPct`: How far price pulled back from pivot
- `recoveryProgressPct`: How much of recovery back to pivot is complete
- `setupSubtype`: "FOLLOW_THROUGH" vs "FRESH_BREAKOUT"

---

## Filtering & Ranking

### Filter Priority

```
1. Quality Score ≥ minQualityScore × 0.8
   └─ Only valid, repeatable patterns

2. Days Since Breakout ≤ 40 bars
   └─ Fresh enough to track, not ancient history

3. Pullback Depth 0.5% - 15%
   └─ Healthy dips only, not capitulation

4. Recovery Speed ≤ 15 bars from low
   └─ Quick institutional buying

5. Liquidity Checks
   └─ Volume, price level, regime alignment
```

### Ranking Score

Within follow-throughs, prioritize by:

```
Primary   → Quality Score (original setup strength)
Secondary → Days Since Breakout (fresher is better)
Tertiary  → Recovery Speed (quicker = more confident)
Quaternary→ Pullback Tightness (tighter = less risk)
```

---

## Risk Management

### Position Sizing

Follow-throughs typically have:
- **Entry Risk:** Distance from pullback low to entry
- **Stop Loss:** Pullback low - 0.5% buffer
- **Target 1:** Original pivot (1R)
- **Target 2:** First target of original setup (2R)

```
Example Trade Plan:
- Breakout pivot: 100.00
- Pullback low: 98.00
- Entry (on recovery): 100.30
- Stop loss: 97.50 (below pullback low)
- Target 1: 102.50 (1R = 2.80/position)
- Target 2: 105.00 (2R = 4.70/position)
```

### Portfolio Heat

Follow-throughs count toward portfolio heat using:
```
Risk per Trade = (Entry - Stop) × Shares
Risk Units (R) = Risk / (Account × Risk%)
Heat After = Cumulative Risk Units
```

Typically **lower heat** than fresh breakouts because:
- Entry risk is often smaller (pullback low vs initial base)
- Stop is tighter (pullback support vs base bottom)
- Less adverse slippage risk (already confirmed demand)

---

## Monitoring & Alerts

### Real-Time Tracking

When running daily/weekly scans:

1. **New Follow-Throughs Found**
   - Logged in `output/scan_<TIMESTAMP>/events.jsonl`
   - Shown in console with symbol and bars-since-breakout

2. **Breakout Status Tracking**
   - Cache system maintains each symbol's recent breakouts
   - Watchlist updated with symbols near their original pivots
   - Follow-through signals when recovery confirms

3. **Performance Analytics**
   - Separate win-rate tracking for follow-throughs vs fresh
   - Average hold time for follow-through trades
   - Risk/reward comparison

---

## Examples

### Example 1: AAPL Daily Follow-Through

```
Date | Open  | High  | Low   | Close
─────┼───────┼───────┼───────┼────────
2/20 │ 175.5 │ 182.0 │ 175.0 │ 181.5  ← Original Breakout
2/21 │ 181.0 │ 183.2 │ 179.5 │ 182.0
2/22 │ 179.0 │ 181.0 │ 176.8 │ 177.5  ← Pullback starts
2/23 │ 176.0 │ 178.0 │ 174.0 │ 175.5  ← Pullback Low
2/24 │ 176.0 │ 182.5 │ 175.8 │ 182.0  ← Recovery Signal!

Analysis:
- Breakout: Close 181.5 > Pivot 181.0 ✓
- Volume: 2.3M > 1.8M average ✓
- Pullback: (181.0 - 174.0) / 181.0 = 3.9% ✓
- Recovery: 182.0 > 181.0 × 1.003 = 181.54 ✓
- Days: 4 days since breakout ✓
- Quality: Base 78/100 → 62/100 after adjustment ✓
```

**Entry:** 182.20
**Stop:** 173.90 (below pullback low)
**Risk:** 8.30/share
**T1:** 183.50 (1R)
**T2:** 185.80 (2R)

---

## Future Enhancements

### v2.0

- [ ] Multi-timeframe follow-through confirmation
  - Daily follow-through must have weekly setup intact
  - Increases quality, reduces false signals

- [ ] Smart pivot freshness scoring
  - More aggressive on pivots tested multiple times
  - More conservative on untested, brand-new pivots

- [ ] Breakout quality memory
  - Track how many times this exact pivot has held
  - Use for risk adjustment on recovery trades

### v3.0

- [ ] Machine learning pattern recognition
  - Deep learning on follow-through success rates
  - Context-aware quality scoring (market regime, sector, VIX)

- [ ] Options flow integration
  - Detect unusual options activity at original pivot
  - Confirms institutional interest in hold/recovery

---

## Troubleshooting

### No Follow-Throughs Found?

**Possible causes:**

1. **Lookback too small**
   - Try `--daily-lookback 252` (full year of data)
   - Need at least 40 bars to scan for old breakouts

2. **Quality threshold too high**
   - Check `minQualityScore` in AppConfig
   - Follow-throughs reduced to 0.8× (often too strict)
   - Try manually lowering in code

3. **Pullback didn't occur in lookback window**
   - Some breakouts happened > 40 bars ago
   - Extend `lookbackDepth` in FollowThroughDetector

4. **Recovery hasn't started yet**
   - Pullback still ongoing (lower not yet confirmed)
   - Wait 1-2 more bars for recovery to trigger

### False Positives (Bad Signals)?

**Mitigations:**

1. Increase `minQualityScore × 0.8` threshold
2. Require recovery speed ≤ 3 bars (not 5)
3. Add regime filter (skip during hard regime downtrends)
4. Cross-check with manual charting

---

## References

- `src/FollowThroughDetector.java` — Core algorithm
- `src/ScannerEngine.java` — Integration points
- `apps/python/cli/run_full_us_scan.py` — CLI batch processing
- `src/Main.java` — Mode routing

---

**Author:** VCP System Development  
**Last Updated:** March 24, 2026  
**Status:** Production Ready

