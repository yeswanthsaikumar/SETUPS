# SETUPS Scanner — System Improvements Documentation

**Date:** April 16, 2026  
**Scope:** Core scanning engine, filtering logic, and signal quality improvements

---

## Summary of Changes

This update implements **14 improvements** across the scanning system to dramatically improve signal quality, reduce false breakouts, and provide richer context for watchlist decisions.

---

## 🔴 P0 — Critical Improvements (Highest Impact)

### 1. Relative Strength (RS) Ranking in Live Scanning
**File:** `src/RelativeStrengthCalculator.java` (NEW)

- Computes IBD-style RS percentile rankings for the entire scanned universe
- Uses weighted composite: 40% 3-month return + 35% 6-month + 25% 12-month (recency bias)
- Symbols are ranked 0–100 percentile within the scan universe
- Configurable `minRsPercentile` in AppConfig (default: 0 = disabled; set to 50–70 for strict)
- Low-RS stocks are rejected early in the scan pipeline with `LOW_RS_RANK` rejection reason

**How it helps:** Only shows you stocks that are *already outperforming* their peers. Eliminates laggards that form bases but never break out convincingly.

### 2. Market Regime Gate in Live Scanning
**File:** `src/MarketRegimeDetector.java` (NEW)

- Computes TAILWIND / NEUTRAL / HEADWIND regime from benchmark index (^NSEI or SPY)
- Uses: 20-bar momentum, 50-bar momentum, price vs 50 SMA, price vs 200 SMA
- In **HEADWIND**: only A/A+ rated setups with RS ≥ 60th percentile pass through
- Regime is displayed in scan output header and tagged on each signal
- Replaces the backtest-only `shouldFilterOutSignal()` — now works in live scanning too

**How it helps:** Stops you from taking mediocre breakouts during weak markets. During strong markets, you get the full signal flow.

### 3. Sector/Industry Group Strength
**File:** `src/SectorStrengthAnalyzer.java` (NEW)

- Loads your existing `data/nse_stock_taxonomy.csv` (1360+ NSE stocks mapped to sectors/industries)
- Computes average RS percentile per sector from the scanned universe
- **Score adjustments:** Top-20% sectors get +10 bonus, top-40% get +5, bottom-20% get -5 penalty
- Sector and industry tags appear in scan/watchlist output
- Configurable via `taxonomyPath` in AppConfig

**How it helps:** O'Neil/Minervini principle — buy the leading stock in the leading sector group. Now your scanner automatically boosts stocks in hot sectors and penalizes laggards.

---

## 🔴 P1 — High-Impact Improvements

### 4. Volume Dry-Up Before Breakout
**Files:** `src/Indicators.java`, `src/VcpDetector.java`, `src/AppConfig.java`

- New `Indicators.volumeDryUpRatio()` — measures last 5 bars' average volume vs 50-bar baseline
- If ratio ≤ 0.70 (volume dried up to 70% of normal), setup gets a +6 score bonus
- Configurable: `volumeDryUpLookbackBars`, `volumeDryUpMaxRatio`, `volumeDryUpScoreBonus`
- Tagged as `[VOL_DRY]` in scan output

**How it helps:** The hallmark of institutional accumulation completing. Volume dries up as the last sellers are absorbed, creating a "spring" before the breakout.

### 5. Accumulation/Distribution Ratio in Base
**Files:** `src/Indicators.java`, `src/VcpDetector.java`, `src/AppConfig.java`

- New `Indicators.accumDistRatio()` — counts up-days-on-high-volume vs down-days-on-high-volume in the consolidation range
- Ratio ≥ 1.5 → +5 bonus; ratio ≥ 1.0 → +2.5 bonus; ratio < 1.0 → no bonus (distribution dominant)
- Configurable: `minAccumDistRatio`, `accumDistScoreBonus`

**How it helps:** Ensures the base has more buying pressure than selling pressure on significant volume days. Filters out bases where institutions are distributing (selling into strength).

### 6. Liquidity Filter (Minimum Average Volume)
**Files:** `src/ScannerEngine.java`, `src/AppConfig.java`, `src/RejectionDiagnostic.java`

- New pre-scan gate: rejects symbols with 20-day average volume below `minAvgVolume`
- Defaults: 100,000 shares/day (daily), 50,000 (weekly)
- Rejection reason: `LOW_LIQUIDITY`

**How it helps:** Eliminates illiquid stocks that appear to have "tight bases" simply because nobody trades them. Prevents slippage traps.

---

## 🟡 P2 — Medium-Impact Improvements

### 7. Gap-Up Breakout Detection
**Files:** `src/BreakoutEvaluator.java`, `src/VcpSetup.java`

- Detects when `open > pivot` AND `volume ≥ 2x average` — marks as gap breakout
- Tagged as `[GAP]` in scan output; signal type becomes `GAP_BREAKOUT`
- Configurable: `gapBreakoutVolumeMultiplier`, `gapBreakoutScoreBonus`

**How it helps:** Gap-through-pivot on massive volume is the most powerful breakout type. Now distinguished from grind-through breakouts.

### 8. Tight-Close Count Scoring
**Files:** `src/Indicators.java`, `src/VcpDetector.java`, `src/AppConfig.java`

- New `Indicators.tightCloseCount()` — counts consecutive bars where all closes cluster within 1.5% of each other
- If most bars in the lookback window are tight → +5 bonus; half → +2.5
- Configurable: `tightCloseLookbackBars`, `tightCloseMaxSpreadPct`, `tightCloseScoreBonus`

**How it helps:** Tight closes = extreme compression = spring-loaded for breakout. This is what Minervini calls the "cheat area."

### 9. EMA Fan Alignment
**Files:** `src/Indicators.java`, `src/VcpDetector.java`

- New `Indicators.isEmaFanAligned()` — checks if 10 EMA > 21 EMA > 50 EMA
- Tagged as `[EMA_FAN]` in scan output when true
- Used as metadata enrichment (not a hard filter — too restrictive for early-stage bases)

**How it helps:** EMA fan = strongest possible uptrend structure. Breakouts from EMA-fan-aligned bases have the highest follow-through rate.

### 10. Fixed Pivot Freshness Scoring
**File:** `src/BreakoutQualityAnalyzer.java`

- **Before:** Score peaked at 0–1 tests (untested pivot = highest score)
- **After:** Score peaks at 2–3 tests (proven resistance), lower for 0–1 (untested) and 6+ (exhausted)
- 2–3 tests → 10 points; 4 tests → 9; 0–1 → 7; 5–6 → 5; 7–9 → 3; 10+ → 1

**How it helps:** A pivot that has been tested 2–3 times is *proven* resistance. Breaking through it is more meaningful than breaking an untested level.

### 11. Fixed Backtest Overlapping Positions
**File:** `src/BacktestEngine.java`

- **Before:** Could fire new signals on a symbol while a previous trade was still open
- **After:** Tracks `positionExitIndex` per symbol; skips new entries until previous position exits

**How it helps:** Makes backtest results realistic — no more inflated signal counts from overlapping entries.

---

## 🟢 P3 — Enrichment & Display

### 12. Enriched Scan Output Tags
**Files:** `src/ScanResult.java`, `src/WatchlistResult.java`

New tags in console output:
- `[RS:85]` — Relative Strength percentile rank
- `[Technology]` — Sector name from taxonomy
- `[TAILWIND]` / `[HEADWIND]` — Market regime
- `[VOL_DRY]` — Volume dry-up detected
- `[GAP]` — Gap-up breakout
- `[EMA_FAN]` — EMA fan alignment
- `[MTF: ...]` — Multi-timeframe alignment (existing)
- `[IPO 45d]` — IPO flag (existing)

### 13. New Rejection Reasons
**File:** `src/RejectionDiagnostic.java`

Added: `LOW_RS_RANK`, `WEAK_SECTOR`, `MARKET_HEADWIND`, `LOW_LIQUIDITY`

### 14. Market Regime Display in Scan Header
**File:** `src/Main.java`

Scan output now shows:
```
Market Regime: TAILWIND (score=5.2 bench=^NSEI)
RS Rankings: 1361 symbols ranked
```

---

## New Configuration Parameters (AppConfig.java)

| Parameter | Default (Daily) | Default (Weekly) | Description |
|-----------|-----------------|------------------|-------------|
| `minRsPercentile` | 0.0 | 0.0 | Minimum RS rank (0=disabled, 50-70 recommended) |
| `minAvgVolume` | 100,000 | 50,000 | Minimum 20-day avg volume |
| `taxonomyPath` | `data/nse_stock_taxonomy.csv` | same | Sector/industry taxonomy file |
| `volumeDryUpLookbackBars` | 5 | 3 | Bars to check for volume dry-up |
| `volumeDryUpMaxRatio` | 0.70 | 0.70 | Max ratio for dry-up detection |
| `volumeDryUpScoreBonus` | 6.0 | 6.0 | Score bonus for dry-up |
| `minAccumDistRatio` | 1.0 | 1.0 | Min accum/dist ratio |
| `accumDistScoreBonus` | 5.0 | 5.0 | Score bonus for good accum/dist |
| `gapBreakoutVolumeMultiplier` | 2.0 | 2.0 | Volume threshold for gap detection |
| `gapBreakoutScoreBonus` | 8.0 | 8.0 | Score bonus for gap breakout |
| `tightCloseLookbackBars` | 7 | 4 | Bars to check for tight closes |
| `tightCloseMaxSpreadPct` | 1.5 | 1.5 | Max close spread for tight count |
| `tightCloseScoreBonus` | 5.0 | 5.0 | Score bonus for tight closes |

---

## New Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `src/RelativeStrengthCalculator.java` | 124 | Universe-wide RS percentile ranking |
| `src/MarketRegimeDetector.java` | 94 | TAILWIND/NEUTRAL/HEADWIND detection |
| `src/SectorStrengthAnalyzer.java` | 110 | Sector/industry strength from taxonomy |

---

## Files Modified

| File | Changes |
|------|---------|
| `src/AppConfig.java` | +13 new config fields for RS, liquidity, volume dry-up, accum/dist, gap, tight-close |
| `src/Indicators.java` | +4 new methods: volumeDryUpRatio, accumDistRatio, tightCloseCount, isEmaFanAligned |
| `src/VcpSetup.java` | +8 enrichment fields with getters/setters; getQualityScore() now includes bonuses |
| `src/VcpDetector.java` | +enrichSetupWithBaseQuality() method; enrichment called after setup detection |
| `src/BreakoutEvaluator.java` | +gap-up breakout detection in isBullishBreakout() |
| `src/BreakoutQualityAnalyzer.java` | Fixed pivot freshness: peaks at 2-3 tests not 0-1 |
| `src/ScannerEngine.java` | Major update: RS pre-filter, liquidity gate, regime filter, sector enrichment |
| `src/ScanResult.java` | +RS, sector, regime, sector bonus fields and display tags |
| `src/WatchlistResult.java` | +RS, sector, regime, sector bonus fields and display tags |
| `src/RejectionDiagnostic.java` | +4 new rejection reasons |
| `src/BacktestEngine.java` | Fixed overlapping positions with positionExitIndex tracking |
| `src/Main.java` | +market regime display in scan header; updated follow-through message |

---

## Recommended Next Steps

1. **Tune `minRsPercentile`** — Run backtests with values of 40, 50, 60, 70 to find the sweet spot for your universe
2. **Backtest sector filtering** — Compare win rates with and without sector gating enabled
3. **Add earnings proximity warning** — Flag stocks with earnings ±5 trading days (data source needed)
4. **Implement follow-through mode** — Wire `FollowThroughDetector` into CLI for pullback recovery scanning
5. **Add VWAP reclaim check** — For intraday precision on breakout entries
6. **Configurable scoring weights** — Move hardcoded weights (0.6/0.4 range/volume) to AppConfig for optimization

---

## Architecture Decision: Soft Filters vs Hard Gates

All new features follow the philosophy of **soft scoring + optional hard gates**:

- **Volume dry-up, accum/dist, tight-close, EMA fan:** Score bonuses (not hard gates). A stock without dry-up still passes; it just scores lower.
- **RS ranking, liquidity:** Configurable hard gates (set threshold to 0 to disable).
- **Market regime:** Hard gate only in HEADWIND for non-top-rated setups.
- **Sector strength:** Score adjustment (+10/-5), not a hard gate. Even bottom-sector stocks can pass with strong enough setup quality.

This ensures the scanner doesn't become overly restrictive while still prioritizing the highest-probability setups at the top of the output.

