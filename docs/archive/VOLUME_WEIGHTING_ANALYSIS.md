# Volume Weighting Analysis - Your System

## Overview

Your system uses **dual-layered volume weighting**:

1. **Tier 1: Setup Detection (Quality Score)** - Volume contraction as a core detection metric
2. **Tier 2: Breakout Confirmation** - Volume expansion verification on the breakout candle

---

## Tier 1: Volume Contraction (Setup Detection)

### Location
- **File**: `src/VcpDetector.java`
- **Method**: `detectForWindow()` (lines ~165-195)
- **Key Metric**: `volumeContraction`

### How It Works

Your system divides the consolidation window into **3 waves** and measures volume contraction:

```
Consolidation Window (e.g., 60 bars)
├── Wave 1 (bars 1-20)   → avgVolume[1]
├── Wave 2 (bars 21-40)  → avgVolume[2]
└── Wave 3 (bars 41-60)  → avgVolume[3]

volumeContraction = (avgVolume[1] - avgVolume[3]) / avgVolume[1]
```

**Example**: 
- Wave 1 average volume: 1,000,000 shares
- Wave 3 average volume: 900,000 shares
- volumeContraction = (1,000,000 - 900,000) / 1,000,000 = **0.10 (10%)**

### Volume Contraction Requirements (by Window Length)

The system applies **dynamic thresholds** that adapt based on consolidation window size:

| Window Length | Dynamic Threshold | Reason |
|---|---|---|
| ≤ 15 days | Min 0.22 (22% contraction) | Stricter for short, recent windows |
| 16-30 days | Min 0.20 (20% contraction) | Moderately strict |
| 31-120 days | Min 0.10 (10% contraction) | Default from `AppConfig` |
| 121-180 days | Min 0.08 (8% contraction) | Relaxed for very long bases |
| ≥ 180 days | Min 0.05 (5% contraction) | Most relaxed for multi-quarter bases |

**Default Config Values** (from `src/AppConfig.java`):
```java
this.minVolumeContraction = weekly ? 0.08 : 0.10;  // 8% weekly, 10% daily
```

### Volume Contraction Pairs (Wave-to-Wave)

Your system also tracks **wave-to-wave volume contractions**:

```java
for (int i = 1; i < waveVolumes.length; i++) {
    if (waveVolumes[i] <= waveVolumes[i-1] * 1.05) {  // 5% tolerance
        stats.volumeContractions++;  // This wave contracted vs previous
    } else {
        stats.volumeMisses++;  // This wave expanded vs previous
    }
}
```

**Required Contraction Pairs** (must contract on both transitions):

| Window Type | Required Pairs | Total Pairs |
|---|---|---|
| Short (≤ 30 days) | 100% of pairs | Must contract on all transitions |
| Medium (31-120 days) | 75% of pairs | Allow 1 expansion allowed |
| Long (≥ 120 days) | 50% of pairs | Allow more flexibility |

---

## Tier 2: Setup Quality Score

### VCP Setup Score Calculation

```
VCP Quality Score = [(rangeContraction × 0.6) + (volumeContraction × 0.4)] × 100 + baseBonus + wickBodyAdjustment
```

**Weightage Breakdown**:
- **Range Contraction**: 60% weight
- **Volume Contraction**: 40% weight
- **Base Bonus**: +5 points for short windows (≤20 days), +2 for medium (≤30 days)
- **Wick/Body Adjustment**: ±12 points (daily) or ±8 points (weekly) based on candle structure

**Code Reference** (VcpDetector.java, line ~182):
```java
double vcpScore = ((rangeContraction * 0.6) + (volumeContraction * 0.4)) * 100.0 + baseBonus + wickBodyAdjustment;
```

### Range Expansion Setup Score Calculation

```
Range Expansion Score = [
    (rangeContraction × 0.35)
    + (volumeContraction × 0.15)
    + (min(rangeExpansion / required, 2.0) × 0.35)
    + (min(expansionVolume / required, 2.0) × 0.15)
] × 100 + wickBodyAdjustment
```

**Weightage Breakdown**:
- **Range Contraction**: 35% weight
- **Volume Contraction**: 15% weight
- **Range Expansion**: 35% weight
- **Expansion Volume**: 15% weight
- **Wick/Body Adjustment**: ±12 points (daily) or ±8 points (weekly)

**Code Reference** (VcpDetector.java, line ~197):
```java
double expansionScore = (
    (rangeContraction * 0.35)
    + (volumeContraction * 0.15)
    + (Math.min(rangeExpansion / requiredRangeExpansion, 2.0) * 0.35)
    + (Math.min(expansionVolume / requiredExpansionVolume, 2.0) * 0.15)
) * 100.0 + wickBodyAdjustment;
```

**Key Insight**: Volume has **40% weight in VCP** but only **15% in Range Expansion** because expansion setups rely more heavily on price range expansion (35%).

---

## Tier 3: Breakout Volume Confirmation

### Location
- **File**: `src/BreakoutEvaluator.java`
- **Methods**: `isBullishBreakout()`, `classifyBreakoutRejection()`, `isNearBreakoutContinuation()`

### Volume Confirmation Rules

#### Rule 1: Standard Breakout (Fresh Pivot Break)
```
breakoutVolume >= 20-day average volume × multiplier
```

**Multiplier by Timeframe**:
- **Daily**: 1.25x (from `AppConfig.java`)
- **Weekly**: 1.10x

**Code Reference** (BreakoutEvaluator.java, line ~19):
```java
double volume20 = Indicators.averageVolume(candles, volumeStart, baseEnd);
boolean volumeBreakout = latest.getVolume() >= volume20 * config.breakoutVolumeMultiplier;
```

#### Rule 2: Near-Breakout Continuation (3-8% Above Pivot)
```
breakoutVolume >= 20-day average volume × nearBreakoutVolumeMultiplier
```

**Multiplier by Timeframe**:
- **Daily**: 1.05x (lighter requirement, already elevated)
- **Weekly**: 1.00x (no extra volume needed, confirmation)

**Code Reference** (BreakoutEvaluator.java, line ~110):
```java
boolean volumeHealthy = latest.getVolume() >= avgVolume * config.nearBreakoutVolumeMultiplier;
```

### Rejection Reason for Low Volume

If breakout volume is insufficient:
```
Return: RejectionDiagnostic.Reason.INSUFFICIENT_VOLUME
```

**Code Reference** (BreakoutEvaluator.java, line ~20):
```java
if (!volumeBreakout) {
    return RejectionDiagnostic.Reason.INSUFFICIENT_VOLUME;
}
```

---

## Tier 4: Advanced Breakout Quality Analysis

### Location
- **File**: `src/BreakoutQualityAnalyzer.java`
- **Method**: `analyzeBreakoutQuality()` (lines ~40-71)

### Volume Percentile Scoring (0-10 points)

Your system measures how the **breakout volume ranks** against the prior 50 bars:

```
volumePercentile = count(bars with volume < breakoutVolume) / 50-bar lookback
```

| Percentile | Score | Quality |
|---|---|---|
| ≥ 80% | 10.0 pts | Breakout volume higher than 80% of recent bars |
| ≥ 60% | 8.0 pts | Higher than 60% |
| ≥ 50% | 6.0 pts | Higher than 50% (median) |
| ≥ 40% | 5.0 pts | Higher than 40% |
| ≥ 30% | 3.0 pts | Higher than 30% |
| < 30% | 1.0 pts | Lower than 30% (weak volume breakout) |

**Code Reference** (BreakoutQualityAnalyzer.java, lines ~76-104):
```java
private void analyzeVolumePercentile(List<Candle> candles, Candle breakoutCandle, BreakoutQualityContext ctx) {
    // Counts how many of the prior 50 bars had volume < breakout volume
    int countBelowBreakout = 0;
    for (int i = lookbackStart; i < candles.size() - 1; i++) {
        if (candles.get(i).getVolume() < breakoutVolume) {
            countBelowBreakout++;
        }
    }
    ctx.volumePercentile = (double) countBelowBreakout / volumeLookback;
    
    // Assign score based on percentile
    if (ctx.volumePercentile >= 0.80) {
        ctx.volumePercentileScore = 10.0;
    } else if (ctx.volumePercentile >= 0.60) {
        ctx.volumePercentileScore = 8.0;
    } // ... etc
}
```

---

## Complete Volume Weighting Flow (Visual)

```
┌─ STAGE 1: SETUP DETECTION ────────────────────────────┐
│                                                        │
│  Input: 60-bar consolidation window                   │
│  ├─ Split into 3 waves (20 bars each)                │
│  ├─ Calculate avg volume per wave                     │
│  ├─ volumeContraction = (Wave1 - Wave3) / Wave1      │
│  │                                                     │
│  └─ WEIGHT: VCP = 40%, RangeExp = 15%                │
│      Score: if volumeContraction >= threshold         │
│              → Setup qualifies for detection           │
│                                                        │
└────────────────────────────────────────────────────────┘

┌─ STAGE 2: QUALITY SCORING ────────────────────────────┐
│                                                        │
│  Input: Qualified setup + breakout candle             │
│  ├─ VCP Score = (0.6 × rangeContraction +             │
│  │              0.4 × volumeContraction) × 100         │
│  │                                                     │
│  ├─ If Score ≥ minQualityScore (35-40)               │
│  │  → Setup enters output list                        │
│  │                                                     │
│  └─ Volume contribution: 40-60% of total score        │
│                                                        │
└────────────────────────────────────────────────────────┘

┌─ STAGE 3: BREAKOUT CONFIRMATION ─────────────────────┐
│                                                        │
│  Input: Latest candle price action                    │
│  ├─ Calculate 20-day avg volume                       │
│  ├─ Check: latestVolume >= avgVol20 × (1.25x daily / 1.10x weekly) │
│  │                                                     │
│  ├─ If volume ✓ + price ✓ → BREAKOUT confirmed       │
│  ├─ If volume ✗ → REJECTED (INSUFFICIENT_VOLUME)      │
│  │                                                     │
│  └─ Volume must pass before price confirmation        │
│                                                        │
└────────────────────────────────────────────────────────┘

┌─ STAGE 4: BREAKOUT QUALITY ANALYSIS ──────────────────┐
│                                                        │
│  Input: Confirmed breakout                            │
│  ├─ Volume Percentile (50-bar lookback):              │
│  │  volumeScore = how many prior bars had             │
│  │                lower volume? (1-10 pts)            │
│  │                                                     │
│  ├─ Pivot Freshness (10 pts)                          │
│  ├─ Distance Efficiency (10 pts)                       │
│  ├─ Tightness Quality (10 pts)                         │
│  │                                                     │
│  └─ Total = Volume + 3 other factors (0-40 pts max)   │
│      Rating: EXCELLENT/STRONG/GOOD/FAIR/WEAK         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## Real-World Example

Let's trace a **Daily VCP setup** with volume weighting:

### Example: AAPL Daily VCP Setup

```
Consolidation Window: 60 bars (3 months)

Wave 1 (bars 1-20):     Avg Volume = 50M shares
Wave 2 (bars 21-40):    Avg Volume = 45M shares  
Wave 3 (bars 41-60):    Avg Volume = 35M shares

── STAGE 1: Volume Contraction ──
volumeContraction = (50M - 35M) / 50M = 0.30 (30%)
Required: ≥ 0.10 (10%) ✓ PASS

── STAGE 2: Quality Score ──
Let's say rangeContraction = 0.25

VCP Score = ((0.25 × 0.6) + (0.30 × 0.4)) × 100
          = ((0.15) + (0.12)) × 100
          = 0.27 × 100
          = 27 points (before bonuses)

With baseBonus (+2) + wickBodyAdjustment (+8):
Total Score = 27 + 2 + 8 = 37 points
Required: ≥ 35 ✓ PASS

── STAGE 3: Breakout Confirmation ──
Day 61 (breakout):
  Volume = 65M shares
  Avg 20-day volume = 48M shares
  Required: 48M × 1.25 = 60M shares
  
  65M ≥ 60M ✓ VOLUME CONFIRMED

── STAGE 4: Quality Analysis ──
50-bar lookback volume study:
  - 42 bars had volume < 65M
  - Percentile = 42/50 = 84%
  - Score: 10 points (EXCELLENT)

+ Pivot Freshness: 8 pts
+ Distance Efficiency: 7 pts
+ Tightness: 8 pts

Total Quality = 10 + 8 + 7 + 8 = 33/40 (EXCELLENT)

── OUTPUT ──
✓ Setup detected
✓ Setup scored: 37 points
✓ Breakout confirmed on volume
✓ Quality: EXCELLENT (volume percentile: 84%)
```

---

## Configuration Parameters (Summary)

**Daily Defaults** (from `AppConfig.java`):
```java
breakoutVolumeMultiplier = 1.25        // Breakout bar must be 1.25x avg vol
nearBreakoutVolumeMultiplier = 1.05    // Near-breakout is lighter (1.05x)
minVolumeContraction = 0.10            // Bases must show 10% volume contraction
minExpansionVolumeMultiplier = 1.10    // Range expansion breakout needs 1.10x
```

**Weekly Defaults**:
```java
breakoutVolumeMultiplier = 1.10        // Lighter for weekly
nearBreakoutVolumeMultiplier = 1.00    // No extra volume required
minVolumeContraction = 0.08            // Relaxed to 8% weekly
minExpansionVolumeMultiplier = 1.05    // Relaxed to 1.05x
```

---

## Summary: How Volume Is Weighted

| Stage | Component | Weight | Role |
|---|---|---|---|
| **1. Setup Detection** | Volume Contraction | 40% (VCP) / 15% (RangeExp) | Gates whether setup qualifies |
| **2. Quality Score** | Base volume profile | 40-60% of total | Directly impacts quality score |
| **3. Breakout** | Breakout bar volume | 100% gate | Must clear 1.25x/1.10x hurdle |
| **4. Quality Analysis** | Volume percentile | 10/40 pts | Ranks breakout quality as EXCELLENT/STRONG/etc |

**Key Insight**: Your system uses a **4-stage volume filter**:
1. Detect bases with volume contraction
2. Score setups partly on that contraction
3. Reject breakouts without volume expansion
4. Rank final breakout quality by volume strength

This ensures you only trade **quality breakouts with sustained institutional volume support**.

---

## How to Adjust Volume Weighting

If you want to make the system stricter or looser on volume:

### Make Volume Stricter (Fewer Signals, Higher Quality)
Edit `AppConfig.java`:
```java
this.breakoutVolumeMultiplier = 1.50;  // Instead of 1.25 (daily)
this.minVolumeContraction = 0.15;      // Instead of 0.10 (daily)
```

### Make Volume Looser (More Signals, More Setups)
```java
this.breakoutVolumeMultiplier = 1.15;  // Instead of 1.25 (daily)
this.minVolumeContraction = 0.08;      // Instead of 0.10 (daily)
```

### Adjust Setup Score Weight (More Volume-Focused)
```java
double vcpScore = ((rangeContraction * 0.5) + (volumeContraction * 0.5)) * 100.0;
// Instead of 0.6/0.4, now it's 0.5/0.5 (equal weight)
```

---

## Files Reference

- **Core Volume Logic**: `src/VcpDetector.java` (setup detection)
- **Breakout Volume Check**: `src/BreakoutEvaluator.java` (confirmation)
- **Quality Volume Scoring**: `src/BreakoutQualityAnalyzer.java` (analysis)
- **Config Parameters**: `src/AppConfig.java` (thresholds)
- **Indicators**: `src/Indicators.java` (averageVolume calculation)


