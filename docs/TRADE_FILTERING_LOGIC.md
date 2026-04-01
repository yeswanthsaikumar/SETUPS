# Complete Trade Filtering Logic Documentation

## 📊 System Overview

Your trading system employs a **4-stage multi-layered filtering approach** to ensure only high-quality breakouts are presented. Each stage progressively filters out lower-quality setups while maintaining opportunities for strong trades.

---

## STAGE 1️⃣: SETUP DETECTION — Volatility Contraction Pattern Analysis

### Purpose
Identify consolidation bases showing strong volume and range contraction characteristics that precede explosive breakouts.

### Process

#### Window Scanning
- **Multiple Windows Tested**: 20, 30, 45, 60 bars
- **Best Score Kept**: System retains highest-scoring window for each symbol
- **Why Multiple Windows?**: Different stocks have different consolidation rhythms; testing multiple captures the optimal compression point

#### Wave Division
```
Consolidation Window (60 bars example)
├── Wave 1 (bars 1-20)
├── Wave 2 (bars 21-40)
└── Wave 3 (bars 41-60)
```

Each window is divided into 3 equal waves to measure:
1. **Volume progression** from early to late consolidation
2. **Range progression** to confirm tightening

#### Range Contraction Metric
```
rangeContraction = (Wave₁ High-Low Range - Wave₃ High-Low Range) / Wave₁ High-Low Range

Example:
Wave 1 range: $5.00 (10% of price)
Wave 3 range: $2.50 (5% of price)
rangeContraction = (5 - 2.5) / 5 = 0.50 (50% range squeeze)
```

**What it means**: A 50% range contraction shows the stock is **tightening dramatically**, setting up for a potential breakout.

#### Volume Contraction Metric
```
volumeContraction = (Wave₁ Avg Volume - Wave₃ Avg Volume) / Wave₁ Avg Volume

Example:
Wave 1 avg: 1,000,000 shares
Wave 3 avg: 800,000 shares
volumeContraction = (1M - 0.8M) / 1M = 0.20 (20% volume contraction)
```

**What it means**: A 20% volume reduction shows the market is **pausing before the move** — less traders are playing the consolidation.

#### Dynamic Thresholds (Window-Based)

The system applies **adaptive requirements** based on consolidation length:

| Window Length | Volume Contraction Minimum | Reason |
|---|---|---|
| ≤ 15 bars | 22% | Short, recent bases need stricter standards |
| 16-30 bars | 20% | Moderately strict for recent compressions |
| 31-120 bars | 10% | Default threshold for typical bases |
| 121-180 bars | 8% | Relaxed for longer-term consolidations |
| ≥ 180 bars | 5% | Most relaxed for multi-quarter bases |

**Why adaptive?** Short 15-bar bases can show false contractions; longer bases need lower thresholds because volume naturally spreads over time.

### Gate Checks (Pre-Filtering)

Before any setup detection occurs, the system applies **4 critical gates**:

#### Gate 1: Minimum Price
```
latestClose ≥ config.minPrice (typically $1.00 daily, $0.50 weekly)
```
**Filters out**: Penny stocks with unreliable volume/pricing data

#### Gate 2: 52-Week High Proximity
```
distanceFromHigh = (52wkHigh - currentPrice) / 52wkHigh

Required: distanceFromHigh ≤ config.maxDistanceFrom52WkHighPct (typically 15-20%)

Example:
52-week high: $100
Current price: $92
Distance: 8% ✓ PASS (still in uptrend region)

Current price: $75
Distance: 25% ✗ FAIL (too far below high, likely downtrend)
```
**Filters out**: Stocks far below recent highs (indicating downtrend)

#### Gate 3: Trend Filter (Price Above Moving Average)
```
If config.requireAboveMA = true:
  baseEndClose > movingAverage(config.maPeriod)
```
**Default**: 200-period MA confirms long-term uptrend
**Filters out**: Stocks below their major support/trend line

#### Gate 4: Data Sufficiency
```
candles.size() ≥ minBarsForWindow(config)
```
**Typical minimum**: 70 bars for 60-bar window detection
**Filters out**: Insufficient historical data for reliable analysis

### Volume Contraction Pairs (Wave-to-Wave Analysis)

Beyond first-to-last ratios, the system also tracks **intermediate contractions**:

```
Wave 1 → Wave 2: Does vol contract? ✓ or ✗
Wave 2 → Wave 3: Does vol contract? ✓ or ✗

Contraction Pair Requirements:
├── Short windows (≤30 days): 100% of transitions must contract
├── Medium windows (31-120 days): ≥75% must contract
└── Long windows (≥120 days): ≥50% can contract
```

**Example - 60-bar window:**
```
Wave 1 Vol: 1.2M shares
Wave 2 Vol: 1.0M shares → Contracted ✓ (1.0M < 1.2M × 1.05 tolerance)
Wave 3 Vol: 0.9M shares → Contracted ✓ (0.9M < 1.0M × 1.05 tolerance)

Result: 2/2 contractions (100%) = PASSES requirement for medium window
```

---

## STAGE 2️⃣: QUALITY SCORING — Setup Strength Evaluation

### Purpose
Quantify setup quality using weighted metrics so that the strongest bases rank highest.

### VCP (Volatility Contraction Pattern) Score

```
VCP Score = [(rangeContraction × 0.60) + (volumeContraction × 0.40)] × 100
            + baseBonus + wickBodyAdjustment
```

**Weight Breakdown:**
- **Range Contraction: 60%** — Price tightening is the core pattern
- **Volume Contraction: 40%** — Volume drying up confirms buyers are patient

**Example Calculation:**
```
Metrics:
  rangeContraction = 0.40 (40% squeeze)
  volumeContraction = 0.25 (25% volume drop)
  baseBonus = +2 (medium window, 25 bars)
  wickBodyAdjustment = +6 (clean daily bar structure)

Score = [(0.40 × 0.60) + (0.25 × 0.40)] × 100 + 2 + 6
      = [(0.24) + (0.10)] × 100 + 8
      = 34 + 8
      = 42 points (STRONG setup)
```

### Range Expansion Score

For **RANGE_EXPANSION** setups (breakouts with unusual intraday range):

```
Expansion Score = [
    (rangeContraction × 0.35)
    + (volumeContraction × 0.15)
    + (min(rangeExpansion / requiredExpansion, 2.0) × 0.35)
    + (min(expansionVolume / requiredExpansionVol, 2.0) × 0.15)
] × 100 + wickBodyAdjustment
```

**Weight Breakdown:**
- **Range Contraction: 35%** — Still important, but secondary
- **Volume Contraction: 15%** — Less critical for expansion setups
- **Range Expansion: 35%** — The breakout range dominates the score
- **Expansion Volume: 15%** — Volume on the breakout matters

**Why different weights?** Range expansion setups rely more on the **size of the breakout bar** than the preceding consolidation.

### Quality Score Bonuses

#### Base Length Bonus
```
Short windows (≤20 bars): +5 points
Medium windows (≤30 bars): +2 points
Long windows (>30 bars): 0 points
```
**Rationale**: Shorter, tighter bases suggest more organized consolidation

#### Wick/Body Adjustment (Daily Candles)
```
Wide-body, small-wick candles: +12 points
  Example: 2% body, 0.1% wick (clean sellers exhaustion)
  
Mixed candle structure: 0 points
  Example: 1.5% body, 1% wick

Long-wick, small-body candles: -12 points
  Example: 0.5% body, 2% wick (indecision)
```

**Weekly candles**: ±8 points (more tolerance for longer timeframe)

### Minimum Quality Score Gate
```
Final Score ≥ config.minQualityScore (typically 35-40 points)
```

**If score < 35**: Setup rejected before even checking for breakout
**If score ≥ 35**: Setup enters watchlist and awaits breakout confirmation

---

## STAGE 3️⃣: BREAKOUT CONFIRMATION — Price & Volume Validation

### Purpose
Verify that a setup has actually broken out with sufficient volume and price conviction.

### Volume Confirmation

The breakout candle must show **elevated volume** relative to recent trading:

```
breakoutVolume ≥ (20-day averageVolume) × volumeMultiplier
```

**Volume Multipliers by Context:**

#### Fresh Pivot Breakout (First Break Above Consolidation)
```
Daily:   1.25x (25% above 20-day average)
Weekly:  1.10x (10% above 20-day average)
```

**Example:**
```
20-day avg volume: 1,000,000 shares
Breakout volume: 1,300,000 shares

1,300,000 ≥ 1,000,000 × 1.25 (1,250,000) ✓ PASS
```

#### Near-Breakout Continuation (3-8% Above Pivot)
```
Daily:   1.05x (5% above 20-day average)
Weekly:  1.00x (no requirement, already elevated)
```

**Rationale**: If price is already slightly extended, volume bar just needs to sustain (lighter requirement)

### Price Confirmation (Daily Timeframe)

Three conditions must ALL be met:

#### Condition 1: Close Above Pivot + Buffer
```
closingPrice > pivotPrice × (1.0 + breakoutBufferPct)

Default breakoutBufferPct = 0.3% (0.003)

Example:
Pivot: $100.00
Buffer: 0.3%
Requirement: Close > $100.30

Closes at $100.25: ✗ FAIL (too close to pivot)
Closes at $100.35: ✓ PASS
```

**Why the buffer?** Prevents false breakouts from tiny above-pivot closes

#### Condition 2: Intraday High Pierces Pivot
```
barHigh > pivotPrice
```

**Example:**
```
Pivot: $100.00
Bar high: $100.50, Close: $100.35
$100.50 > $100.00 ✓ PASS (intraday break confirmed)

Bar high: $100.25, Close: $100.20
$100.25 > $100.00 ✓ PASS (even though close failed!)
```

**Why this matters?** Confirms the breakout actually occurred intraday, not just a gap-up at open

#### Condition 3: Close Above Pivot (Simple)
```
closingPrice > pivotPrice
```

### Range Expansion Validation (For RANGE_EXPANSION Setups Only)

If setup type is **RANGE_EXPANSION**, additional checks apply:

#### Breakout Range Check
```
breakoutRange = barHigh - barLow

Required: breakoutRange ≥ 20-bar ATR × minRangeExpansionMultiplier

Example:
20-bar ATR: $2.00
multiplier: 1.30
Requirement: $2.60

Breakout range: $3.00 ✓ PASS (exceeds ATR threshold)
```

#### Close Position in Range
```
closeInRange = (barClose - barLow) / (barHigh - barLow)

Required: closeInRange ≥ minExpansionClosePosition (typically 0.50 = 50%)

Example:
Bar low: $100, Bar high: $103, Close: $102
closeInRange = (102 - 100) / (103 - 100) = 2/3 = 67%

67% ≥ 50% ✓ PASS (strong close in upper half)
```

### Rejection Decision Tree

If breakout volume is INSUFFICIENT:
```
Return: RejectionDiagnostic.Reason.INSUFFICIENT_VOLUME
Action: Removed from breakout candidates
```

If price check fails:
```
Return: RejectionDiagnostic.Reason.NO_BREAKOUT
Action: Removed from breakout candidates
```

If range expansion check fails:
```
Return: RejectionDiagnostic.Reason.ATR_EXPANDING
Action: Removed from breakout candidates (specific to expansion setups)
```

---

## STAGE 4️⃣: BREAKOUT QUALITY ANALYSIS — Strength Rating System

### Purpose
After confirmation, rank breakout quality from **WEAK** to **EXCELLENT** based on institutional volume support.

### Volume Percentile Scoring (0-10 points)

The system examines the **prior 50 bars** to assess how the breakout volume ranks:

```
volumePercentile = count(bars with volume < breakoutVolume) / 50

Score Table:
≥ 80th percentile: 10.0 pts → EXCELLENT
≥ 60th percentile: 8.0 pts  → STRONG
≥ 50th percentile: 6.0 pts  → GOOD
≥ 40th percentile: 5.0 pts  → FAIR
≥ 30th percentile: 3.0 pts  → WEAK
< 30th percentile: 1.0 pts  → VERY WEAK
```

**Example:**
```
Prior 50 bars volumes: [800K, 900K, 950K, 1M, 1.1M, ...]
Breakout volume: 1.3M

Count of bars < 1.3M: 48 out of 50
Percentile: 48/50 = 96%

Score: 10.0 points (EXCELLENT - breakout volume highest in 50 bars!)
```

### Additional Quality Factors (0-30 points total)

#### Pivot Freshness (0-10 points)
```
How recent is the consolidation setup?

Fresh (≤5 bars old): 10 pts   → Immediate, hot setup
Recent (6-10 bars): 8 pts     → Still warm
Moderate (11-20 bars): 6 pts  → Lukewarm
Stale (>20 bars): 2 pts       → Cold setup
```

#### Distance Efficiency (0-10 points)
```
How close is entry to optimal pivot?

Same day as setup: 10 pts     → Perfect timing
1-2 days after: 8 pts         → Good entry window
3-5 days after: 5 pts         → Acceptable
6+ days after: 2 pts          → Delayed entry
```

#### Tightness Quality (0-10 points)
```
How tight was the consolidation relative to price?

Ratio of range contraction to volume contraction:
Excellent balance: 10 pts     → Both contracted well
Good balance: 7 pts           → One stronger than other
Fair balance: 4 pts           → Uneven contractions
Weak balance: 1 pt            → Poor consolidation quality
```

### Overall Quality Rating

```
Total Points = volumePercentile (0-10) + pivotFreshness (0-10) + distanceEfficiency (0-10) + tightnessQuality (0-10)

Rating Scale:
35-40 points: A+ → EXCELLENT (Institutional quality breakout)
30-34 points: A  → STRONG (High-confidence setup)
25-29 points: B  → GOOD (Solid trade opportunity)
20-24 points: C  → FAIR (Acceptable risk/reward)
15-19 points: D  → WEAK (Marginal, proceed with caution)
```

---

## 🔴 REJECTION REASONS — Why Trades Get Filtered Out

Each rejected trade receives a **specific rejection reason** for analysis and improvement:

### INSUFFICIENT_VOLUME
**Trigger**: `breakoutVolume < (20-day avgVolume × volumeMultiplier)`

**Example:**
```
20-day avg: 1M shares
Required (1.25x): 1.25M
Actual breakout: 1.1M

1.1M < 1.25M → REJECTED
```

**Implication**: Without volume, breakout is likely to fail or reverse quickly

---

### NO_BREAKOUT
**Trigger**: Price fails ANY of three conditions:
- Close not > pivot + buffer
- High didn't pierce pivot
- Close not > pivot (simple check)

**Example:**
```
Pivot: $100.00
Close: $100.25 (meets minimum)
High: $100.15 (didn't pierce pivot!)

High condition fails → REJECTED
```

**Implication**: Intraday rejection at pivot level

---

### LOW_QUALITY_SETUP
**Trigger**: Setup quality score < minimum threshold

**Example:**
```
Setup score: 32 points
Minimum: 35 points

32 < 35 → REJECTED before breakout even checked
```

**Implication**: Consolidation wasn't tight enough or volume didn't contract sufficiently

---

### PRICE_BELOW_MA
**Trigger**: `baseEndClose < movingAverage(config.maPeriod)` AND `config.requireAboveMA = true`

**Example:**
```
200-day MA: $95
Close at base end: $92
92 < 95 → REJECTED
```

**Implication**: Stock not in confirmed uptrend

---

### FAR_FROM_52WK_HIGH
**Trigger**: `distanceFromHigh > config.maxDistanceFrom52WkHighPct`

**Example:**
```
52-week high: $100
Current price: $70
Distance: 30%
Max allowed: 20%

30% > 20% → REJECTED
```

**Implication**: Stock likely in downtrend, consolidation is intermediate bounce

---

### PENNY_STOCK
**Trigger**: `latestClose < config.minPrice`

**Example:**
```
Close: $0.45
Min price: $1.00

$0.45 < $1.00 → REJECTED
```

**Implication**: Volume and pricing unreliable for this strategy

---

### ATR_EXPANDING (Range Expansion Setups Only)
**Trigger**: `breakoutRange < (20-bar ATR × minRangeExpansionMultiplier)`

**Example:**
```
20-bar ATR: $1.50
Multiplier: 1.30
Requirement: $1.95

Breakout range: $1.80
$1.80 < $1.95 → REJECTED
```

**Implication**: Breakout bar didn't expand enough for range expansion pattern

---

### INSUFFICIENT_DATA
**Trigger**: `candles.size() < minimumBarsRequired`

**Example:**
```
Available bars: 50
Minimum for 60-bar window: 70

50 < 70 → REJECTED
```

**Implication**: Not enough history to validate setup

---

## ✅ ACCEPTANCE CRITERIA — What Makes a Trade Get Selected

For a trade to be **ACCEPTED** and presented, it must pass ALL of these gates:

### ✓ Setup Quality Gate
```
qualityScore ≥ 35-40 points
```

### ✓ Volume Contraction Gate
```
volumeContraction ≥ dynamic threshold (5-22% based on window)
```

### ✓ Range Contraction Gate
```
rangeContraction ≥ 0.15 (15% minimum squeeze)
```

### ✓ Price Gate
```
latestClose > pivotPrice × 1.003
```

### ✓ Breakout Volume Gate
```
latestVolume ≥ avgVolume20 × 1.25 (daily) or 1.10 (weekly)
```

### ✓ Trend Gate
```
latestClose ≥ movingAverage(200-period) OR config.requireAboveMA = false
```

### ✓ 52-Week High Gate
```
(52wkHigh - latestClose) / 52wkHigh ≤ 0.20 (20% max distance)
```

### ✓ Price Floor Gate
```
latestClose ≥ 1.00 (daily) or 0.50 (weekly)
```

### ✓ Data Sufficiency Gate
```
candles.size() ≥ 70 minimum
```

---

## 📈 Configuration Parameters

All these thresholds are configurable in `AppConfig.java`:

```java
// Volume gates
this.breakoutVolumeMultiplier = 1.25;           // Fresh breakouts need 1.25x
this.nearBreakoutVolumeMultiplier = 1.05;       // Near-breakouts need 1.05x
this.minVolumeContraction = 0.10;               // 10% volume contraction default

// Price gates
this.breakoutBufferPct = 0.003;                 // 0.3% above pivot
this.minPrice = 1.00;                           // Don't trade below $1

// Trend gates
this.requireAboveMA = true;                     // Require above 200-MA
this.maPeriod = 200;                            // 200-period moving average

// 52-week gate
this.maxDistanceFrom52WkHighPct = 0.20;         // Within 20% of 52-week high

// Quality gates
this.minQualityScore = 35;                      // 35-point minimum for watchlist

// Watchlist gate (pre-breakout candidates only)
this.watchlistMaxDistanceToPivotPct = 0.05;     // Must be within 5% below pivot

// Range expansion gates
this.minRangeExpansionMultiplier = 1.30;        // 1.30x ATR for range expansion
this.minExpansionClosePosition = 0.50;          // Close in upper 50% of bar
```

### Weekly vs Daily Adjustments

```java
if (config.isWeekly()) {
    config.breakoutVolumeMultiplier = 1.10;     // Lighter on weekly
    config.minVolumeContraction = 0.08;          // Relaxed to 8%
    config.minPrice = 0.50;                      // Allow lower prices
} else {
    // Daily defaults (shown above)
}
```

---

## 🎯 Real-World Trade Example

## 👀 Pre-Breakout Watchlist Rule

The watchlist is intentionally **pre-breakout only**:

```text
distanceToPivotPct = (pivot - close) / pivot
Valid watchlist band: 0.00 to 0.05  (0% to 5% below pivot)
```

- `distanceToPivotPct < 0`: already above pivot (belongs to breakout/open-trades flow)
- `distanceToPivotPct > 0.05`: base may be valid, but it is too early/far from trigger
- Applies to both `VCP` and `RANGE_EXPANSION` watchlist candidates

Let's trace a complete trade through all 4 stages:

### Setup Details
- **Symbol**: AAPL
- **Date**: 2026-03-15
- **Timeframe**: Daily

### Stage 1: Setup Detection
```
Window tested: 60 bars
Wave 1 (bars 1-20):   Range $5.00, Volume 50M
Wave 2 (bars 21-40):  Range $3.50, Volume 45M
Wave 3 (bars 41-60):  Range $2.50, Volume 35M

rangeContraction = (5 - 2.5) / 5 = 50% ✓
volumeContraction = (50M - 35M) / 50M = 30% ✓
Both exceed thresholds → SETUP DETECTED
```

### Stage 2: Quality Scoring
```
VCP Score = [(0.50 × 0.60) + (0.30 × 0.40)] × 100
          = [0.30 + 0.12] × 100
          = 42 points

baseBonus (60-bar window): +2
wickBodyAdjustment: +8

Total: 42 + 2 + 8 = 52 points ✓ (exceeds 35 minimum)
```

### Stage 3: Breakout Confirmation
```
Day 61 (2026-03-16):
  Volume: 65M
  20-day avg: 48M
  65M ≥ 48M × 1.25 (60M) ✓ PASS volume

  Pivot: $150.00
  Close: $150.60
  High: $151.00
  $150.60 > $150.45 (pivot + 0.3%) ✓ PASS price
  $151.00 > $150.00 ✓ PASS high

All conditions met → BREAKOUT CONFIRMED
```

### Stage 4: Quality Analysis
```
Prior 50 bars analysis:
  Only 8 bars had volume > 65M
  43 out of 50 bars had volume < 65M
  Percentile: 43/50 = 86% ✓ EXCELLENT

Pivot freshness: Same day → 10 pts
Distance efficiency: Entry at start → 10 pts
Tightness quality: 50% range, 30% volume balance → 8 pts

Total quality: 10 + 10 + 10 + 8 = 38 pts

Rating: A (STRONG breakout)
```

### Final Output
```
✓ ACCEPTED
  Setup: VCP
  Quality Score: 52.0
  Quality Rating: A
  Entry: $150.60
  Stop: $148.50 (Pivot - range)
  Target 1: $152.50
  Risk/Reward: 2.1:1
  Volume Percentile: 86%
```

---

## 🔍 How to Use This Information

### For Trade Selection
1. Review trades that **cleared ALL 4 stages**
2. Prioritize those with:
   - Higher quality scores (A+ vs D)
   - Better volume percentiles (>80th vs <30th)
   - Fresher setups (same day vs 20+ days old)

### For Rejected Trade Analysis
1. Look at your **rejection reason frequency**:
   - High "INSUFFICIENT_VOLUME" → Reduce volume multiplier in config
   - High "LOW_QUALITY_SETUP" → Setups aren't tight enough
   - High "NO_BREAKOUT" → Price action too choppy in the consolidation

2. Adjust parameters if rejection patterns don't match your market:
   ```java
   // If rejecting too many high-quality-looking setups:
   config.minQualityScore = 32;  // Lower from 35
   config.minVolumeContraction = 0.08;  // Relax from 0.10
   ```

### For Strategy Optimization
1. **Tighten volume requirements** if slippage is high:
   ```java
   config.breakoutVolumeMultiplier = 1.50;  // From 1.25
   ```

2. **Relax range requirements** if missing good setups:
   ```java
   config.minQualityScore = 32;  // From 35
   ```

3. **Adjust 52-week proximity** for different market regimes:
   ```java
   config.maxDistanceFrom52WkHighPct = 0.30;  // From 0.20 (more relaxed)
   ```

---

## Summary Table

| Stage | Component | Weight | Pass Criteria | Rejection |
|---|---|---|---|---|
| **1** | Volume Contraction | 40% | ≥ 5-22% | LOW_QUALITY_SETUP |
| **1** | Range Contraction | 60% | ≥ 15% | LOW_QUALITY_SETUP |
| **1** | Trend (MA) | N/A | Close ≥ MA | PRICE_BELOW_MA |
| **1** | 52-Wk High | N/A | ≤ 20% away | FAR_FROM_52WK_HIGH |
| **2** | Quality Score | 100% | ≥ 35 points | LOW_QUALITY_SETUP |
| **3** | Breakout Volume | 100% | ≥ 1.25x avg | INSUFFICIENT_VOLUME |
| **3** | Breakout Price | 100% | > Pivot + 0.3% | NO_BREAKOUT |
| **3** | Intraday High | 100% | > Pivot | NO_BREAKOUT |
| **4** | Volume Percentile | 25% | ≥ 30th % | Rating: D-F |
| **4** | Pivot Freshness | 25% | ≤ 5 bars | Rating: C-F |
| **4** | Distance Efficiency | 25% | Same day | Rating: C-F |
| **4** | Tightness Quality | 25% | Balanced | Rating: C-F |

