# Example Case Study: Understanding a Row in the Enhanced HTML Report (All CSV Columns)

Suppose you see the following row in the HTML report:

| Symbol | Signal Type | Base Score | Alignment Bonus | Final Score | Quality Rating | Quality Score | Setup Type | Window | Window Bars | Range Height % | Contraction Depth % | Range Contraction | Volume Contraction | Range Expansion | Setup Rating | Pivot Price | Close Price | Entry Price | Close-Pivot Dist % | Pivot Test Count | MultiTF Align | Weekly Align Bonus | Weekly Structure | Trade Entry | Stop Loss | Shares | Target 1 | Target 2 | Target 3 | R:R T1 | R:R T2 | R:R T3 | Data Quality | Data Errors | Data Warnings |
|--------|-------------|------------|----------------|-------------|---------------|--------------|------------|--------|-------------|----------------|---------------------|-------------------|--------------------|------------------|--------------|-------------|------------|------------|-------------------|------------------|--------------|-------------------|------------------|------------|-----------|--------|----------|----------|----------|--------|--------|--------|-------------|-------------|--------------|
| AETHER | BREAKOUT    | 32.5       | 2.0            | 34.5        | A+            | 38.0         | VCP        | 12w    | 60          | 18.5%          | 12.0%               | 22.5%             | 15.0%              | 8.0%             | A+           | 1250.00     | 1158.55    | 1251.00    | 7.89%             | 3                | STRONG       | 2.0               | Aligned          | 1251.00    | 1190.00   | 100    | 1350.00  | 1450.00  | 1550.00  | 1.67:1 | 2.67:1 | 3.67:1 | OK          |             |              |

### Column Explanations

- **Symbol**: Stock ticker (e.g., AETHER)
- **Signal Type**: Type of breakout signal (e.g., BREAKOUT)
- **Base Score**: Raw quality score for the setup
- **Alignment Bonus**: Bonus for multi-timeframe alignment
- **Final Score**: Base Score + Alignment Bonus
- **Quality Rating**: Letter grade for setup quality (A+, A, B, etc.)
- **Quality Score**: Final numeric quality score
- **Setup Type**: Type of setup detected (VCP, RANGE_EXPANSION, etc.)
- **Window**: Label for the base window (e.g., 12w = 12 weeks)
- **Window Bars**: Number of bars in the base window
- **Range Height %**: Height of the base range as a percent
- **Contraction Depth %**: Depth of contraction as a percent
- **Range Contraction**: Range contraction percent
- **Volume Contraction**: Volume contraction percent
- **Range Expansion**: Range expansion percent
- **Setup Rating**: Letter grade for the setup
- **Pivot Price**: Price level for breakout
- **Close Price**: Closing price on signal day
- **Entry Price**: Suggested entry price
- **Close-Pivot Dist %**: Distance between close and pivot as a percent
- **Pivot Test Count**: Number of times pivot was tested
- **MultiTF Align**: Multi-timeframe alignment reason/label
- **Weekly Align Bonus**: Bonus for weekly alignment
- **Weekly Structure**: Weekly structure status
- **Trade Entry**: Entry price for trade plan
- **Stop Loss**: Stop loss price
- **Shares**: Number of shares for position sizing
- **Target 1/2/3**: Price targets
- **R:R T1/2/3**: Risk/reward ratio to each target
- **Data Quality**: Data quality status (OK, Warning, etc.)
- **Data Errors**: Any critical data errors (if present)
- **Data Warnings**: Any non-critical data warnings (if present)

### How to Interpret

- Look for high **Quality Rating** (A+, A) and high **Final Score** for best setups.
- **Entry Price** and **Stop Loss** define your risk; **R:R** columns show potential reward.
- **MultiTF Align** and **Weekly Structure** indicate if higher timeframes support the breakout.
- **Data Quality** should be OK for reliable signals. If **Data Errors** or **Data Warnings** are present, review them before acting.


---

## Breakout Performance Tracking (NEW)

A new report now tracks all stocks that have already broken out, monitoring their post-breakout performance. This data is available in a segregated CSV and HTML file for easy review.

### Columns Explained
- **symbol**: Stock ticker symbol.
- **breakoutDate**: Date when the breakout was detected.
- **entry**: Breakout price (entry price).
- **close**: Most recent closing price.
- **distance_from_breakout**: Difference between current price and breakout price.
- **pct_gain_since_breakout**: Percentage gain/loss since breakout.
- **days_since_breakout**: Number of days since breakout was detected.
- **max_after_breakout**: Maximum price reached after breakout (if available).
- **min_after_breakout**: Minimum price reached after breakout (if available).
- **setup**: Setup type (e.g., VCP, Range Expansion).
- **rating**: Quality rating of the setup.
- **window**: Time window or pattern window.
- **listType**: Should be 'OPEN_TRADE' for these rows.

### How to Use
- Use this report to monitor the progress of all open breakout trades.
- Quickly identify which trades are performing well after breakout and which are lagging.
- Use the distance and % gain columns to assess momentum and risk.
- Days since breakout helps you track trade maturity.

### File Locations
- CSV: `output/breakout_performance_<scan_label>_LATEST.csv`
- HTML: `output/breakout_performance_report.html` (if enabled)

---

#### Note on Example Update (March 2026)
The example row for AETHER has been updated to reflect a realistic pivot price and related values based on actual recent data. The pivot price (1250.00) is set at the most recent significant high before the breakout, following standard VCP (Volatility Contraction Pattern) breakout methodology. Entry price is set just above the pivot, and stop loss/targets are illustrative. This ensures the example matches real-world price levels for Aether Industries Limited.

This table now gives you a comprehensive view of each breakout candidate, matching the CSV export and making it easy to compare setups at a glance.
