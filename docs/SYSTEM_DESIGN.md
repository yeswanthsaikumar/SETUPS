# System Design - Breakout Scanner (VCP + Range Expansion)

## 1) Objective

Build a practical scanner that identifies bullish breakout entries for both:

- `VCP` (contraction base + breakout), and
- `RANGE_EXPANSION` (contraction base + expansion breakout),

then outputs a complete trade plan for each shortlisted symbol.

## 2) Implemented Architecture

```text
Main
  -> ScannerEngine
      -> MarketDataProvider
      -> VcpDetector
          -> Indicators
      -> BreakoutEvaluator
      -> TradePlanner
  -> ScanResult (console output)
  -> WatchlistResult (near-pivot potential breakout output)

Python orchestration
  -> apps/python/cli/run_vcp_system.py (market/timeframe/setup scheduler)
      -> apps/python/cli/run_full_us_scan.py (parallel batch runner)
          -> java -cp src Main ...
  -> output/* (CSV, JSON, HTML, summaries)
  -> run_backtest.py --matrix-all (US/India x daily/weekly batch backtest)
```

### Core responsibilities

- `MarketDataProvider`: candle source abstraction
- `VcpDetector`: identifies contraction structure and quality score
- `BreakoutEvaluator`: confirms breakout quality
- `TradePlanner`: converts signal to position sizing and targets
- `ScannerEngine`: orchestration and ranking
- `apps/python/cli/run_full_us_scan.py`: batch scan orchestration, parsing, report generation
- `apps/python/cli/run_vcp_system.py`: daily automation across US/India and daily/weekly runs
- `WatchlistResult`: potential breakout candidate with trade plan + pivot distance

## 3) Setup Quality Rules and Signal Logic

This section is the implementation-level source of truth for how the system decides whether a setup is high quality enough to become a scan hit, continuation candidate, or watchlist candidate.

Primary code references:

- `src/ScannerEngine.java`
- `src/VcpDetector.java`
- `src/BreakoutEvaluator.java`
- `src/TradePlanner.java`
- `src/AppConfig.java`
- `src/Indicators.java`

The current engine is deterministic and formula-based. It does not use any machine-learning model in the live setup path.

### 3.1 Evaluation pipeline

For each symbol/timeframe combination:

1. Load candles.
2. Build a candle slice up to the evaluation bar.
3. Run `VcpDetector.detect(...)` to find the best valid setup across all configured windows.
4. Reject if no setup is returned or if `qualityScore < minQualityScore`.
5. Run `BreakoutEvaluator.isBullishBreakout(...)`.
6. If breakout is false, run `BreakoutEvaluator.isNearBreakoutContinuation(...)`.
7. Reject if neither breakout nor continuation passes.
8. Build a trade plan with `TradePlanner.buildPlan(...)`.
9. Reject if the risk math is invalid.
10. Emit one of:
   - `BREAKOUT`
   - `NEAR_BREAKOUT`
   - watchlist result (separate mode only)

### 3.2 Indicator formulas used by the detector

From `src/Indicators.java`:

- `averageClose(start, end)` = arithmetic average of close prices
- `averageVolume(start, end)` = arithmetic average of volume
- `highestHigh(start, end)` = maximum high in the range
- `lowestLow(start, end)` = minimum low in the range
- `movingAverage(endIndex, period)` = simple moving average of closes ending at `endIndex`
- `averageTrueRange(endIndexInclusive, period)` where:

```text
TR = max(
  high - low,
  abs(high - previousClose),
  abs(low - previousClose)
)
ATR = arithmetic average of TR values over the period
```

### 3.3 Global quality gates before any window is tested

#### Minimum bars

```text
minimumBars = min(consolidationWindows) + 2
```

The detector rejects the symbol if the available candle count is below that requirement.

#### Minimum price

```text
latestClose >= minPrice
```

Current default:

- daily: `5.0`
- weekly: `5.0`

#### Proximity to annual high

```text
highLookback = min(candleCount, annualHighLookbackBars)
high52w = highestHigh(last highLookback bars)
distanceFromHigh = (high52w - latestClose) / high52w
require distanceFromHigh <= maxDistanceFrom52WkHighPct
```

Current defaults:

- daily annual high lookback: `252`
- weekly annual high lookback: `52`
- max distance from high: `0.35`

#### Trend filter above moving average

The base-end candle is the second-last candle because the last candle is treated as the breakout/evaluation bar.

```text
baseEndIdx = candles.size - 2
ma = movingAverage(baseEndIdx, maPeriod)
require close(baseEndIdx) >= ma
```

Current defaults:

- daily MA period: `50`
- weekly MA period: `10`
- `requireAboveMA = true`

### 3.4 Window universe and labeling

The detector tries multiple window lengths and keeps the highest-scoring valid setup.

#### Daily windows

```text
[12, 15, 20, 30, 45, 60, 90, 120, 180, 240]
```

#### Weekly windows

```text
[6, 8, 10, 13, 16, 20, 26, 39, 52]
```

Window labels used downstream:

```text
Weekly: >=52 Q4, >=39 Q3, >=26 Q2, >=13 Q1, else WEEK
Daily:  >=240 Q4, >=180 Q3, >=120 Q2, >=60 Q1, else WEEK
```

### 3.5 Base construction per window

For each candidate window:

```text
consolidationEnd   = candles.size - 2
consolidationStart = consolidationEnd - windowDays + 1
waveSize           = windowDays / waveCount
```

Current `waveCount = 3`.

Minimum wave size:

- daily: `3` bars
- weekly: `2` bars

If wave size is too small, the window is rejected.

### 3.6 Per-wave measurements

For each wave:

```text
waveHigh     = highestHigh(wave)
waveLow      = lowestLow(wave)
waveAvgClose = averageClose(wave)
waveRange    = (waveHigh - waveLow) / waveAvgClose
waveVolume   = averageVolume(wave)
```

### 3.7 Contraction formulas

The system compares the first wave against the last wave.

#### Range contraction

```text
rangeContraction = max(0, (firstWaveRange - lastWaveRange) / firstWaveRange)
```

#### Volume contraction

```text
volumeContraction = max(0, (firstWaveVolume - lastWaveVolume) / firstWaveVolume)
```

#### Contraction depth

```text
contractionDepthPct = rangeContraction * 100
```

### 3.8 Pairwise contraction counts and misses

Adjacent-wave contraction rules:

```text
range pair passes  if waveRange[i] < waveRange[i-1]
volume pair passes if waveVolume[i] <= waveVolume[i-1] * 1.05
```

The detector tracks:

- `rangeContractions`
- `volumeContractions`
- `rangeMisses`
- `volumeMisses`
- `totalPairs = waveCount - 1`

Wave-miss tolerance rule:

```text
rangeMisses  <= waveContractionMissTolerance
volumeMisses <= waveContractionMissTolerance
```

Current default:

- `waveContractionMissTolerance = 1`

### 3.9 ATR non-expansion gate

The base must not show deteriorating late volatility:

```text
atrEarly = averageTrueRange(consolidationStart + waveSize, 10)
atrLate  = averageTrueRange(consolidationEnd, 10)
require atrLate <= 0 OR atrEarly >= atrLate * 0.90
```

### 3.10 Base geometry

For each candidate window:

```text
pivot              = highestHigh(base)
support            = lowestLow(base)
avgBaseClose       = averageClose(base)
baseRangeHeightPct = ((pivot - support) / avgBaseClose) * 100
```

Stored metadata includes:

- `setupType`
- `pivotPrice`
- `supportPrice`
- `qualityScore`
- `rangeContraction`
- `volumeContraction`
- `rangeExpansion`
- `baseWindowBars`
- `baseWindowLabel`
- `baseRangeHeightPct`
- `contractionDepthPct`
- `setupRating`
- contraction counts and total pair count

### 3.11 Dynamic thresholds by window size

#### Range contraction threshold

Base values:

- daily: `0.15`
- weekly: `0.12`

Rules:

```text
if window >= 180: max(0.10, base - 0.04)
else if window >= 120: max(0.11, base - 0.03)
else if window >= 60: max(0.12, base - 0.02)
else if window <= 15: min(0.30, base + 0.04)
else if window <= 30: min(0.28, base + 0.02)
else: base
```

#### Volume contraction threshold

Base values:

- daily: `0.10`
- weekly: `0.08`

Rules:

```text
if window >= 180: max(0.05, base - 0.03)
else if window >= 120: max(0.06, base - 0.02)
else if window <= 15: min(0.22, base + 0.03)
else if window <= 30: min(0.20, base + 0.02)
else: base
```

#### Range expansion threshold

Base values:

- daily: `1.25`
- weekly: `1.15`

Rules:

```text
if window >= 180: max(1.10, base - 0.10)
else if window >= 120: max(1.12, base - 0.07)
else if window <= 15: base + 0.10
else if window <= 30: base + 0.05
else: base
```

#### Expansion-volume threshold

Base values:

- daily: `1.10`
- weekly: `1.05`

Rules:

```text
if window >= 180: max(1.00, base - 0.05)
else if window >= 120: max(1.02, base - 0.03)
else if window <= 15: base + 0.08
else: base
```

### 3.12 Base-height acceptance rules

Raw defaults:

- daily: `minBaseHeightPct=4`, `maxBaseHeightPct=60`
- weekly: `minBaseHeightPct=6`, `maxBaseHeightPct=75`

Short-window cap:

- daily short window (`<= 30`): `30`
- weekly short window (`<= 13`): `40`

Long-window rules:

- daily long window (`>= 120`): max height `58`, minimum height at least `6`
- weekly long window (`>= 39`): max height `72`, minimum height at least `8`

Range-expansion setups get a slightly wider maximum base:

```text
daily RANGE_EXPANSION: maxHeight += 5
weekly RANGE_EXPANSION: maxHeight += 6
```

Final rule:

```text
minHeight <= baseRangeHeightPct <= maxHeight
```

### 3.13 Required contraction pairs

```text
requiredPairs = ceil(totalPairs * ratio)
requiredPairs = clamp(requiredPairs, 1, totalPairs)
```

Ratios:

- short window:
  - daily `<= 30`: `1.0`
  - weekly `<= 13`: `0.95`
- long window:
  - daily `>= 120`: `0.50`
  - weekly `>= 39`: `0.50`
- all other windows: `0.75`

The VCP path currently enforces:

```text
rangeContractions >= requiredPairs
```

### 3.14 Candle-structure quality adjustment

The detector rewards constructive recent candle anatomy around the breakout bar.

For the last `wickBiasLookbackBars` candles ending at the breakout bar:

```text
range = high - low
bodyDirectional = (close - open) / range
lowerWick = (min(open, close) - low) / range
upperWick = (high - max(open, close)) / range

candleBias =
    bodyDirectional * bodyDirectionalWeight
  + lowerWick      * lowerWickPositiveWeight
  - upperWick      * upperWickNegativeWeight
```

Recency weighting:

```text
normalizedBias = weightedAverage(candleBias, recency weights 1..N)
adjustment = normalizedBias * maxWickBodyScoreAdjustment
adjustment = clamp(adjustment, -maxWickBodyScoreAdjustment, +maxWickBodyScoreAdjustment)
```

Defaults:

| Parameter | Daily | Weekly |
|---|---:|---:|
| wick lookback bars | 3 | 2 |
| body directional weight | 1.0 | 1.0 |
| lower wick positive weight | 1.25 | 1.25 |
| upper wick negative weight | 1.45 | 1.45 |
| max wick/body adjustment | 12.0 | 8.0 |

### 3.15 VCP qualification rules

A VCP setup is accepted only if all of the following pass:

```text
setupFilter allows VCP
base height accepted for VCP
wave misses within tolerance
rangeContractions >= requiredPairs
rangeContraction >= requiredRangeContraction
volumeContraction >= requiredVolumeContraction
```

Score formula:

```text
baseBonus = 5 if window <= 20
          = 2 if window <= 30
          = 0 otherwise

vcpScore = ((rangeContraction * 0.6) + (volumeContraction * 0.4)) * 100
         + baseBonus
         + wickBodyAdjustment
```

Acceptance rule:

```text
vcpScore >= minQualityScore
```

### 3.16 Range-expansion qualification rules

A range-expansion setup is accepted only if all of the following pass:

```text
setupFilter allows RANGE_EXPANSION
base height accepted for RANGE_EXPANSION
rangeContraction >= requiredRangeContraction * 0.75
rangeExpansion >= requiredRangeExpansion
expansionVolume >= requiredExpansionVolume
```

Expansion metrics:

```text
breakoutRange = breakoutHigh - breakoutLow
preBreakAtr = averageTrueRange(consolidationEnd, 10)
rangeExpansion = breakoutRange / preBreakAtr

baseVolume = averageVolume(consolidationEnd - 9, consolidationEnd)
expansionVolume = breakoutVolume / baseVolume
```

Score formula:

```text
expansionScore = (
    rangeContraction * 0.35
  + volumeContraction * 0.15
  + min(rangeExpansion / requiredRangeExpansion, 2.0) * 0.35
  + min(expansionVolume / requiredExpansionVolume, 2.0) * 0.15
) * 100 + wickBodyAdjustment
```

Acceptance rule:

```text
expansionScore >= minQualityScore
```

### 3.17 Best setup wins

Within a window, the detector keeps the highest-scoring valid setup.

Across all windows, the detector returns the setup with the highest `qualityScore`.

### 3.18 Setup rating formula (`A+` to `D`)

Acceptance is controlled by `qualityScore`. Rating is a secondary report label.

```text
lengthBonus = 4 if window >= 60
            = 2 if window >= 30
            = 0 otherwise

compactness = max(0, 35 - baseRangeHeightPct)

ratingScore = qualityScore
            + contractionDepthPct * 0.15
            + compactness * 0.10
            + lengthBonus
```

Rating bands:

- `A+` if `ratingScore >= 85`
- `A` if `ratingScore >= 75`
- `B` if `ratingScore >= 65`
- `C` if `ratingScore >= 55`
- `D` otherwise

### 3.19 Fresh breakout confirmation (`BREAKOUT`)

After setup detection, the latest candle must pass breakout validation.

Shared rules:

```text
priceBreakout  = latestClose > pivot * (1 + breakoutBufferPct)
volumeBreakout = latestVolume >= avgVolume * breakoutVolumeMultiplier
intradayBreak  = latestHigh > pivot
```

Volume baseline:

```text
baseEnd = candles.size - 2
volumeLookback = min(20, baseEnd)
avgVolume = averageVolume(baseEnd - volumeLookback + 1, baseEnd)
```

Defaults:

- daily `breakoutBufferPct = 0.003`
- weekly `breakoutBufferPct = 0.005`
- daily `breakoutVolumeMultiplier = 1.25`
- weekly `breakoutVolumeMultiplier = 1.10`

Extra rules for `RANGE_EXPANSION` breakouts:

```text
breakoutRange = latestHigh - latestLow
atr20 = averageTrueRange(previous bar, 20)
expandedRange = breakoutRange >= atr20 * minRangeExpansionMultiplier

closeInRange = (latestClose - latestLow) / breakoutRange
strongClose = closeInRange >= minExpansionClosePosition
```

### 3.20 Continuation confirmation (`NEAR_BREAKOUT`)

If fresh breakout rules fail, the system checks continuation logic.

```text
abovePivotPct = (latestClose - pivot) / pivot
inContinuationZone = nearBreakoutMinAbovePivotPct <= abovePivotPct <= nearBreakoutMaxAbovePivotPct

volumeHealthy = latestVolume >= avgVolume * nearBreakoutVolumeMultiplier
holdingPivot  = latestLow >= pivot * (1 - breakoutBufferPct)
closeAboveEntry = latestClose >= pivot * (1 + breakoutBufferPct)
```

Defaults:

- `nearBreakoutMinAbovePivotPct = 0.03`
- `nearBreakoutMaxAbovePivotPct = 0.08`
- daily `nearBreakoutVolumeMultiplier = 1.05`
- weekly `nearBreakoutVolumeMultiplier = 1.00`

For range-expansion continuation, the system also requires:

```text
closeInRange >= minExpansionClosePosition
```

### 3.21 Watchlist rules

Watchlist mode uses the same setup detector and quality filter, but excludes already-triggered breakouts.

Rules:

1. Valid setup exists.
2. `qualityScore >= minQualityScore`.
3. `isBullishBreakout(...)` is false.
4. `pivot > 0`.
5. Current close is below pivot but close enough to it.

Distance formula:

```text
distanceToPivotPct = (pivot - latestClose) / pivot
require 0 <= distanceToPivotPct <= watchlistMaxDistanceToPivotPct
```

Defaults:

- daily watchlist max pivot distance: `0.06`
- weekly watchlist max pivot distance: `0.08`

Planned watchlist entry:

```text
plannedEntry = pivot * (1 + breakoutBufferPct)
```

### 3.22 Trade-plan formulas

The trade plan is built from the signal entry price and base support.

```text
stop = support * (1 - stopBufferPct)
riskPerShare = entryPrice - stop
riskCapital = accountSize * riskPerTradePct
shares = floor(riskCapital / riskPerShare)
```

Targets:

```text
T1 = entryPrice + 1 * riskPerShare
T2 = entryPrice + 2 * riskPerShare
T3 = entryPrice + 3 * riskPerShare
```

Defaults:

- `accountSize = 100000`
- `riskPerTradePct = 0.01`
- `stopBufferPct = 0.005`

The trade plan is rejected if:

- `riskPerShare <= 0`
- `shares < 1`

### 3.23 Result routing and ranking

#### Live scan

- If breakout rules pass -> signal type = `BREAKOUT`
- Else if continuation rules pass -> signal type = `NEAR_BREAKOUT`
- Else -> no live signal

Live hits are sorted by `qualityScore` descending.

#### Watchlist

Watchlist hits are sorted by:

```text
qualityScore descending,
distanceToPivotPct ascending
```

### 3.24 Daily vs weekly defaults summary

| Parameter | Daily | Weekly |
|---|---:|---:|
| lookback | 252 | 104 |
| windows | 12,15,20,30,45,60,90,120,180,240 | 6,8,10,13,16,20,26,39,52 |
| min range contraction | 0.15 | 0.12 |
| min volume contraction | 0.10 | 0.08 |
| min quality score | 35 | 30 |
| min range expansion multiplier | 1.25 | 1.15 |
| min expansion volume multiplier | 1.10 | 1.05 |
| breakout buffer | 0.003 | 0.005 |
| breakout volume multiplier | 1.25 | 1.10 |
| continuation volume multiplier | 1.05 | 1.00 |
| watchlist max pivot distance | 0.06 | 0.08 |
| MA period | 50 | 10 |
| annual high lookback | 252 | 52 |

### 3.25 Meaning of a “quality setup” in this system

The system considers a setup high quality only when all of these line up:

- price is above the minimum stock threshold
- the stock is still reasonably close to its annual high
- the base remains above its trend MA
- range and volume contract in an orderly way across waves
- late ATR does not expand inside the base
- the base height is appropriate for the window length and setup type
- recent breakout-candle anatomy is constructive
- the setup score clears `minQualityScore`
- breakout/continuation price and volume behavior confirms the signal
- position sizing remains valid under the risk model

## 4) Runtime Defaults and Modes

- Daily mode: `252` bars (~1 year)
- Weekly mode: `104` bars (~2 years)
- Market coverage: US + India
- Setup filter: `both|vcp|range_expansion`

## 5) Output Design

- CSV/JSON for machine consumption
- HTML for human shortlist review
- HTML includes:
  - full trade plan columns
  - setup and window variation
  - height/depth/length/contraction-count/rating fields
  - color rating badges (`A+/A/B/C/D`)
  - price chart links (Yahoo + TradingView)
  - fundamentals link (Yahoo key statistics)
  - descriptive result column names with inline column guide
- Additional outputs now include:
  - `open_trades_*` (confirmed breakouts, execution list)
  - `watchlist_*` (potential near-breakout candidates)
- System-level summary:
  - `output/system_latest_summary.md`
  - `output/system_latest_summary.json`

## 6) Why This Size Is Reasonable

- Small enough to run in one JVM process quickly
- Components are independent and replaceable
- Easy to add real data and persistence without rewriting strategy logic

## 7) Step-by-Step Improvement Plan (Next)

1. **HTML usability upgrades**
   - Add client-side sort/filter/search in report tables
   - Add setup/window quick filters and score slider
   - Add risk-reward column and color tags

2. **Fundamental enrichment**
   - Add links for financials, balance sheet, and cash flow pages
   - Add optional basic fundamentals columns (market cap, sector, PE)

3. **Signal quality controls**
   - Add liquidity floor and spread/price sanity checks
   - Add optional minimum score and minimum expansion gates per setup

4. **Automation hardening**
   - Add scheduled run templates (macOS launchd)
   - Add retention policy for old scan folders

5. **Backtest alignment**
   - Ensure backtest reuses exact same multi-window setup logic
   - Track results by setup type and window variation

6. **Quality and reliability**
   - Unit tests: detector edge cases, position sizing
   - Integration tests: provider -> scanner
   - Logging with INFO/WARN/ERROR levels

7. **Performance scaling**
   - Scan symbols in parallel batches
   - Cache derived indicators per symbol
   - Keep latest N bars only in memory for scanner mode

## 8) How To Execute

Primary entrypoints now live under `apps/python/cli/`; shell wrappers live under `scripts/`.

### One-time

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
javac src/*.java
```

### Daily run (recommended)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --skip-us-refresh
```

### Explicit full configuration

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --markets us,india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both
```

### India-only triggered scan (variation filters active)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_vcp_system.py --markets india --timeframes daily,weekly --daily-lookback 252 --weekly-lookback 104 --setups both --skip-us-refresh
```

### Verify latest output

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
cat output/system_latest_summary.md
ls -lh output/vcp_hits_*_LATEST.html
```

### Backtest all markets/timeframes (single command)

```bash
cd /Users/yeshwantha/IdeaProjects/SETUPS
python3 apps/python/cli/run_backtest.py --matrix-all --setups both
```

Backtest matrix summary outputs:
- `output/backtest_matrix_LATEST.md`
- `output/backtest_matrix_LATEST.html`
- `output/backtest_matrix_LATEST.json`

## 9) Suggested Milestones

- **Milestone 1 (done)**: multi-setup breakout scanner with trade plan and HTML chart links
- **Milestone 2**: interactive HTML analytics + fundamentals enrichment
- **Milestone 3**: deeper risk controls, backtest analytics, and scheduled alerting

## 10) Config Defaults

See `src/AppConfig.java` for all thresholds and risk defaults.
Tune there first before changing detector internals.

