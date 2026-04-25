# Breakout Performance Tracking Report

## Overview
This report tracks all stocks that have already broken out, monitoring their post-breakout performance. The data is generated automatically by the scan pipeline and is available in both CSV and HTML formats.

## Columns Explained
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

## How to Use
- Use this report to monitor the progress of all open breakout trades.
- Quickly identify which trades are performing well after breakout and which are lagging.
- Use the distance and % gain columns to assess momentum and risk.
- Days since breakout helps you track trade maturity.

## File Locations
- CSV: `output/breakout_performance_<scan_label>_LATEST.csv`
- HTML: `output/breakout_performance_report.html` (if enabled)

## Example Table
| symbol | breakoutDate | entry | close | distance_from_breakout | pct_gain_since_breakout | days_since_breakout | max_after_breakout | min_after_breakout | setup | rating | window | listType |
|--------|--------------|-------|-------|-----------------------|------------------------|--------------------|--------------------|--------------------|-------|--------|--------|----------|
| AETHER | 2024-06-14   | 1250  | 1325  | 75                    | 6.0                    | 10                 | 1350               | 1240               | VCP   | A+     | 12w    | OPEN_TRADE |

## Notes
- The report is updated automatically after each scan.
- Max/min after breakout require historical price tracking and may be blank if not available.
- For more details, see the scan pipeline documentation.

