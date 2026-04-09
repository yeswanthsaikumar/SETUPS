# Bull Flag Detection — Logic & Reference

## Overview

The **Bull Flag** (`BULL_FLAG`) detector identifies one of the most reliable momentum-continuation patterns in technical analysis. A textbook bull flag consists of three distinct phases that together signal institutional accumulation, controlled profit-taking, and a high-probability continuation breakout.

```
           ┌── Pole Top (peak of impulse)
    ▲      │\
    │  ┌───┘ \___________________________
    │  │      Flag channel (slight drift │
    │  │      down / sideways, tight     │
    │  │      candles, volume dries up)  │
    │  │                                 └── Breakout ──► T1 / T2 / T3
    │  │
    └──┘
    Pole Bottom (impulse start)
```

---

## Three Phases

### Phase 1 — Flagpole (Impulse)

| Parameter | Rule |
|---|---|
| Minimum gain | ≥ 10 % from pole bottom to pole top |
| Pole duration | 3 – 25 bars |
| Directional quality | ≥ 50 % of pole bars close higher than previous bar |
| Volume | Pole average volume ideally above 20-bar average (scored) |

The flagpole is the **sharp vertical move** that initiates the pattern. It represents institutional buying or a catalyst-driven surge. The pole is identified by finding the most recent local high (pole top) that is **above the current price** (meaning the stock has since paused/pulled back) and tracing back to find the origin of the move.

**Why the up-bar ratio matters:** A genuine impulse has predominantly up-closes. A series of alternating up/down bars is drift, not an impulse.

---

### Phase 2 — Flag (Consolidation Channel)

| Parameter | Rule |
|---|---|
| Duration | 5 – 30 bars after the pole top |
| Slope (linear regression) | −1.5 % to +0.5 % per bar (gently down or flat) |
| Maximum pole retrace | ≤ 50 % of pole height |
| Max decline from pole top | ≤ 15 % |
| Volume dry-up | Flag average volume < 85 % of 20-bar average |
| Candle tightness | Flag avg range < 80 % of pre-flag avg range |

The flag is the **tight consolidation** after the impulse. Weak hands exit, institutions hold or add quietly. The key signatures are:

- **Volume contraction** — the most important signal. Volume should visibly decline from the pole. This shows supply is exhausted; no major selling.
- **Range contraction** — individual candles get narrower. Price is coiling, energy is building.
- **Slight downward slope** — a true flag drifts gently against the pole direction (down for a bull flag). A flat flag (pennant) is also accepted. A sharply declining flag or an ascending flag is rejected.
- **No deep retrace** — the flag must hold above 50 % of the pole height. Deeper retraces suggest the original move was a distribution spike, not an impulse.

**Slope gate in code:**
```python
slope_pct_per_bar = slope / current_close
# Accepted range: -0.015 (−1.5 %/bar) to +0.005 (+0.5 %/bar)
```

---

### Phase 3 — Breakout Signal

| Condition | Rule |
|---|---|
| Price position | Current close ≥ midpoint of flag channel, OR within 3 % of flag high |
| Subtype `FLAG_FORMING` | Price approaching but not yet at flag high |
| Subtype `FLAG_BREAKOUT` | Price at or through the flag high (≥ 99.8 % of flag high) |

The detector flags the stock **just before or at the moment of breakout** so you can plan your entry:

- **FLAG_FORMING** — ideal alert: price is near the top of the flag, volume is drying up. Enter a buy-stop order just above the flag high.
- **FLAG_BREAKOUT** — price has already reached the breakout level. Enter on confirmation (volume spike preferred).

---

## Scoring

The score (0 – 100) quantifies setup quality. The `_rating_from_score` function maps scores to letter grades.

| Component | Max Points | Description |
|---|---|---|
| Base score | 45 | Every pattern that passes all gates starts here |
| Pole gain | +5 / +10 / +15 | ≥ 10 % / ≥ 25 % / ≥ 40 % |
| Volume dry-up | +5 / +10 / +15 | Flag vol < 85 % / 75 % / 60 % of avg |
| Candle tightness | +3 / +6 / +10 | Tightness ratio < 0.80 / 0.70 / 0.50 |
| Shallow flag decline | +4 / +8 | Decline < 10 % / < 5 % |
| Near flag high | +5 | Current close ≥ 97 % of flag high |
| Trend (above SMA200) | +5 | Confirms long-term uptrend |
| Trend (above SMA50) | +3 | Confirms intermediate uptrend |
| Pole volume quality | +1 / +3 / +5 | Pole avg vol ≥ 1.2× / 1.5× / 2.0× avg |

**Grade mapping:**

| Score | Rating |
|---|---|
| ≥ 80 | A+ |
| ≥ 65 | A |
| ≥ 50 | B |
| ≥ 35 | C |
| < 35 | D (filtered out by default `min_score = 35`) |

---

## Trade Plan

```
Entry  = max(current_close + 0.10 × ATR,  flag_high × 1.002)
Stop   = flag_low − 0.50 × ATR
Risk   = Entry − Stop

T1 = Entry + pole_height × 0.50   ← Conservative (50 % of pole)
T2 = Entry + pole_height × 0.75   ← Intermediate  (75 % of pole)
T3 = Entry + pole_height × 1.00   ← Full measured move (100 % of pole)
```

- **Entry** is placed just above the flag high to confirm the breakout. The 0.10 × ATR buffer avoids triggering on a thin poke above the high.
- **Stop** is placed below the flag low with a half-ATR buffer to absorb intraday noise.
- **Targets** use the classic flagpole measured-move projection: the height of the pole is added to the breakout level.

---

## CSV Output Fields

When the signal is serialised via `_signal_to_dict`, the following BF-specific columns are written in addition to the shared columns:

| Column | Source field | Meaning |
|---|---|---|
| `bfPoleGain%` | `height_pct` | Percentage gain of the flagpole |
| `bfFlagDecline%` | `depth_pct` | Percentage decline of current close from pole top |
| `bfFlagBars` | `length` | Number of bars in the flag phase |
| `bfFlagVolRatio` | `pullback_vol_ratio` | Flag avg volume / 20-bar avg volume (< 1 = dry-up) |
| `bfTightnessRatio` | dynamic attr | Flag avg candle range / pre-flag avg candle range |
| `bfPoleVolRatio` | dynamic attr | Pole avg volume / 20-bar avg volume |
| `bfFlagHigh` | `max_after_breakout` | Highest high during the flag (= breakout trigger) |
| `bfFlagLow` | `min_after_breakout` | Lowest low during the flag (= stop reference) |
| `bfPoleStartDate` | dynamic attr | Date of the pole bottom bar |
| `bfPoleTopDate` | dynamic attr | Date of the pole top bar |

Shared columns (also populated for BULL_FLAG):

| Column | Meaning |
|---|---|
| `pivot` | Flag high = breakout trigger level |
| `entry` | Suggested buy-stop entry price |
| `sl` | Stop-loss price |
| `T1 / T2 / T3` | Measured-move profit targets |
| `score` | Quality score (0 – 100) |
| `rating` | Letter grade (A+ → D) |
| `avgVol20` | 20-bar average volume |
| `lastVol` | Volume on the signal bar |
| `daysAbovePivot` | # of last 20 bars that closed above flag high |
| `distFromPivot%` | % distance of current close from flag high |

---

## Rejection Conditions

A candidate is silently rejected (returns `None`) when **any** of the following fail:

| Gate | Reason |
|---|---|
| Insufficient bars (`< min_bars`) | Not enough history for reliable detection |
| `current_close < min_price_floor` | Penny / micro-cap filter |
| `sma200 == 0` or `close < sma200 × 0.90` | Stock not in a macro uptrend |
| `avg_vol_20 == 0` | Illiquid instrument |
| No qualifying pole found | No sharp recent impulse move |
| `flag_length < 5` or `> 30` | Too short (not yet a flag) or too old (stale) |
| `flag_low < max_allowed_low` | Retrace > 50 % of pole — pattern invalidated |
| `flag_decline_pct > 0.15` | Price dropped > 15 % from pole top — failed flag |
| Slope outside (−1.5 %, +0.5 %) per bar | Too steep down (collapse) or up (not a flag) |
| Price in lower half of flag AND not near flag high | No breakout proximity — too early or too deep |
| `atr_val == 0` | Cannot calculate risk |
| `sl >= entry` or `sl <= 0` | Invalid trade geometry |

---

## How It Fits in the Pipeline

The `BULL_FLAG` setup type is included in the **default `setup_types`** list inside `scan_symbols`:

```python
setup_types = [_SETUP_TYPE_MR, _SETUP_TYPE_BO, _SETUP_TYPE_ABFP, _SETUP_TYPE_BF]
```

It runs after `BREAKOUT_PULLBACK` for every symbol. Signals that score ≥ `min_score` (default 35) are included in the output and appear in the **Live Breakout Trade Plans** report alongside the other breakout-family setups (`BREAKOUT`, `BREAKOUT_PULLBACK`).

---

## Comparison with Related Setups

| Feature | `BREAKOUT` | `BREAKOUT_PULLBACK` | **`BULL_FLAG`** |
|---|---|---|---|
| Trigger event | Break above a prior high | First pullback after a breakout | Break above flag high after impulse + consolidation |
| Entry timing | At / just after breakout | During the pullback | At / just before flag breakout |
| Stop reference | Min since breakout | Original breakout level | Flag low |
| Target method | 2–3 × risk | Peak high / projected | Flagpole measured move |
| Vol dry-up required? | No | Yes (pullback quality) | Yes (flag quality) |
| Pole / impulse required? | No | Yes (breakout preceded) | Yes (explicit flagpole) |
| Typical hold time | Days – weeks | Days – weeks | Days – weeks |

---

## Example (Conceptual)

```
Symbol:  XYZ.NS
Date:    2026-04-09

Pole:  Low ₹100 (day -18) → High ₹145 (day -10)  →  +45% in 8 bars
Flag:  Days -9 to -1 (9 bars), range ₹138–₹145, slope -0.3%/bar
       Avg flag vol: 0.65× 20-bar avg  ← strong dry-up ✓
       Tightness:    0.55               ← candles 45% narrower ✓

Current close: ₹142  (≥ midpoint ₹141.5 ✓, near flag high ₹145 ✓)

Score breakdown:
  Base          : 45.0
  Pole gain 45% : +15.0
  Vol dry-up 65%: +10.0
  Tightness 0.55: +6.0
  Decline 2.1%  : +8.0
  Near flag high: +5.0
  Above SMA200  : +5.0
  Above SMA50   : +3.0
  Pole vol 1.8× : +3.0
  ─────────────────────
  Total         : 100.0  →  Rating: A+

Trade plan:
  Entry : ₹145.30  (flag high × 1.002)
  Stop  : ₹136.20  (flag low ₹137 − 0.5 × ATR ₹1.60)
  T1    : ₹167.80  (+22.5 = 50% of ₹45 pole)
  T2    : ₹179.05  (+33.75 = 75% of pole)
  T3    : ₹190.30  (+45 = full pole projection)
  R:R   : ≈ 2.4 : 1 (to T1)
```

