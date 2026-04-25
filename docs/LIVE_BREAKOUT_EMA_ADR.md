# Live Breakout Trade Plans — EMA & ADR Display

## Overview
The "Live Breakout Trade Plans" page now displays **EMA (Exponential Moving Average)** and **ADR (Average Daily Range)** metrics on every stock setup card. This provides quick, visual feedback on price momentum and volatility for each trading signal.

## New Features

### 1. EMA Metrics Row
Located directly above the Regime/RS footer, each card now shows:

- **EMA 21**: Price distance from 21-period EMA (%)
  - Green (+): Price above 21-day EMA (bullish)
  - Red (-): Price below 21-day EMA (bearish)
  
- **EMA 50**: Price distance from 50-period EMA (%)
  - Helps identify intermediate-term trend direction
  
- **EMA 200**: Price distance from 200-period EMA (%)
  - Helps identify long-term trend structure
  
- **ADR%**: 14-day Average Daily Range as percentage
  - Blue: Low volatility (<2.5%) — Lower R/R potential
  - Yellow: Medium volatility (2.5-5%) — Balanced R/R
  - Red: High volatility (>5%) — Higher R/R potential

### 2. Visual Design
- **Prominent green border**: EMA-ADR row sits above footer stats with enhanced visibility
- **Dark background**: Distinct from other rows for easy scanning
- **Color-coded values**: Instant visual feedback
  - Green text: Price above EMA (bullish positioning)
  - Red text: Price below EMA (bearish positioning)
  - ADR colors based on volatility level

### 3. Sorting & Filtering (Controls Bar)
- **Sort by ADR%**: `📊 Sort: ADR%` button
  - Order signals by volatility (high ADR first for swing traders)
- **Sort by EMA21**: `📈 Sort: EMA21` button
  - Order by proximity to 21-day EMA
- **Filter by EMA Position**: `All EMA` dropdown
  - Options: Above EMA 21, Above EMA 50, Above EMA 200, Above All EMAs, Below EMA 21, Below EMA 50

### 4. Data Attributes on Cards
For programmatic access and advanced filtering:
- `data-ema21`: EMA21 % value (for JavaScript filtering)
- `data-ema50`: EMA50 % value
- `data-ema200`: EMA200 % value
- `data-adr`: ADR% value

## Use Cases

### For Swing Traders
1. **Sort by ADR%** to find high-volatility stocks with better R/R potential
2. **Filter "Above EMA 21"** to focus on stocks still in uptrend
3. **Check EMA 50 proximity** to find consolidation patterns

### For Position Traders
1. **Filter "Above EMA 200"** for stocks in long-term uptrend
2. **Look at EMA 200 distance** to gauge extension from long-term support
3. **ADR helps size positions** — higher ADR allows tighter stops

### For Risk Management
1. **High ADR stocks** may require smaller position sizes (tighter stops)
2. **Low ADR stocks** indicate consolidation (watch for breakout trigger)
3. **EMA alignment (all 3 stacked)** indicates strong trend structure

## How It's Calculated

### EMA Formula
- **EMA = EMA(previous) + multiplier × (price - EMA(previous))**
- Multiplier = 2 / (period + 1)
- Seeded with SMA of first N bars

### ADR% Formula
- **Daily Range = (High - Low) / Close × 100**
- **ADR% = Average of last 14 daily ranges**

### Price vs EMA%
- **Distance = (Price / EMA - 1) × 100**
- Positive = Price above EMA
- Negative = Price below EMA

## Technical Details

### File Location
- Script: `/apps/python/cli/generate_trade_plans_page.py`
- Output: `/output/trade_plans_live.html`

### Key Functions
- `compute_ema(closes, period)` — Calculate exponential moving average
- `compute_ema_adr(rows)` — Compute all EMA and ADR metrics from OHLCV data
- `fmt_ema_vs(value)` — Format EMA distance with HTML styling
- `fmt_adr(value)` — Format ADR% with volatility-based colors

### Data Source
Metrics are computed from cached daily OHLCV (Open, High, Low, Close, Volume) data:
- Located in `/cache/SYMBOL.csv` or `/cache/SYMBOL.NS.csv`
- Updated during each `./run_master.sh` execution

## How to Update

The EMA and ADR metrics are **automatically computed** each time you run:

```bash
./run_master.sh --markets india --skip-performance-tracker && ./run_analysis_dashboards.sh
```

Or just the trade plans page:

```bash
python3 apps/python/cli/generate_trade_plans_page.py
```

## Example Card Display

```
┌─ TATATECH Daily [Bull Flag] A Rating 11/11 Recurr ────────────────────┐
│                                                    [60 min sparkline] ┤
├─ Score 75.0 ──────────────────────────────────────────────────────────┤
│ Entry: ₹570.84 | Stop: ₹542.70 | Position: 365 shares | Capital: ₹2L │
├─ 🟢 EMA 21: +0.9% │ EMA 50: +3.3% │ EMA 200: +8.8% │ ADR%: 3.4% 🟡 ─┤
│ Regime: Unfavorable | RS3M: -13.7% | RS6M: -21.2% | Vol: -63.9% | Rexp: 0.69x
│ 1W: +3.1% | 1M: -1.3% | 3M: -13.7% | 6M: -21.2% | Seen: 11/11 ────┤
│ [📊 Bull Flag Metrics, 🏦 Institutional, ...] ─────────────────────┘
```

## Notes

- **Missing Data**: If a stock has <50 bars of history, EMA/ADR will show as "—"
- **Real-time Updates**: Metrics update daily with new price data
- **Performance**: Computing EMA/ADR for 700+ stocks takes ~30-60 seconds per run
- **Accuracy**: Uses latest close price and daily OHLCV bars from cache

## Future Enhancements

- [ ] Add EMA Ribbon (13, 21, 50 all displayed)
- [ ] Show ATR (Average True Range) instead of/alongside ADR
- [ ] Add RSI indicator row
- [ ] Add MACD signal
- [ ] Real-time updates via WebSocket (for live monitoring)

