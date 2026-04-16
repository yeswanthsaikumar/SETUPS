import java.util.*;

/**
 * Computes Relative Strength (RS) rankings for a universe of symbols.
 *
 * RS measures each stock's price performance over multiple lookback windows
 * relative to the entire scanned universe. Stocks are ranked by percentile
 * (0-100) so the top performers float to the top.
 *
 * Inspired by IBD RS Rating and Mansfield Relative Strength.
 */
public class RelativeStrengthCalculator {
    private final MarketDataProvider marketDataProvider;

    public RelativeStrengthCalculator(MarketDataProvider marketDataProvider) {
        this.marketDataProvider = marketDataProvider;
    }

    /**
     * Represents the RS profile for a single symbol.
     */
    public static class RSProfile {
        public final String symbol;
        public final double momentum63d;   // ~3-month return %
        public final double momentum126d;  // ~6-month return %
        public final double momentum252d;  // ~12-month return %  (0 if insufficient data)
        public final double compositeScore; // Weighted composite raw score
        public double percentileRank;       // 0-100 rank within universe (set after ranking)

        public RSProfile(String symbol, double m63, double m126, double m252) {
            this.symbol = symbol;
            this.momentum63d = m63;
            this.momentum126d = m126;
            this.momentum252d = m252;
            // Weight: 40% recent (3m), 35% medium (6m), 25% long (12m) — recency bias
            this.compositeScore = (m63 * 0.40) + (m126 * 0.35) + (m252 * 0.25);
            this.percentileRank = 0.0;
        }

        @Override
        public String toString() {
            return String.format("RS[%s: 3m=%.1f%% 6m=%.1f%% 12m=%.1f%% composite=%.1f rank=%.0f]",
                    symbol, momentum63d, momentum126d, momentum252d, compositeScore, percentileRank);
        }
    }

    /**
     * Compute RS profiles for all symbols, then rank them by percentile.
     *
     * @param symbols   List of tickers to evaluate
     * @param timeframe "daily" or "weekly"
     * @return Map of symbol → RSProfile (with percentileRank set)
     */
    public Map<String, RSProfile> computeRankings(List<String> symbols, String timeframe) {
        boolean weekly = "weekly".equalsIgnoreCase(timeframe);
        int lookbackBars = weekly ? 104 : 300; // ~2 years of data to compute 12-month return

        int period63  = weekly ? 13  : 63;
        int period126 = weekly ? 26  : 126;
        int period252 = weekly ? 52  : 252;

        List<RSProfile> profiles = new ArrayList<>();

        for (String symbol : symbols) {
            try {
                List<Candle> candles = weekly
                        ? marketDataProvider.getWeeklyCandles(symbol, lookbackBars)
                        : marketDataProvider.getDailyCandles(symbol, lookbackBars);

                if (candles == null || candles.size() < period63 + 1) {
                    continue;
                }

                double latestClose = candles.get(candles.size() - 1).getClose();
                if (latestClose <= 0.0) continue;

                double m63 = momentumPct(candles, period63);
                double m126 = candles.size() > period126 ? momentumPct(candles, period126) : m63;
                double m252 = candles.size() > period252 ? momentumPct(candles, period252) : m126;

                profiles.add(new RSProfile(symbol, m63, m126, m252));
            } catch (Exception ex) {
                // Skip symbols with data errors
            }
        }

        // Rank by composite score → assign percentile
        profiles.sort(Comparator.comparingDouble(p -> p.compositeScore));
        int total = profiles.size();
        for (int i = 0; i < total; i++) {
            profiles.get(i).percentileRank = total <= 1 ? 50.0 : (i * 100.0) / (total - 1);
        }

        Map<String, RSProfile> result = new HashMap<>();
        for (RSProfile p : profiles) {
            result.put(p.symbol, p);
        }
        return result;
    }

    /**
     * Compute single-symbol RS vs a benchmark.
     * Returns the stock's excess return over the benchmark for the given period.
     */
    public double computeRelativeStrengthVsBenchmark(
            List<Candle> stockCandles,
            List<Candle> benchmarkCandles,
            int lookbackBars
    ) {
        double stockReturn = momentumPct(stockCandles, lookbackBars);
        double benchReturn = momentumPct(benchmarkCandles, lookbackBars);
        return stockReturn - benchReturn;
    }

    private double momentumPct(List<Candle> candles, int period) {
        if (candles == null || candles.size() <= period) return 0.0;
        double current = candles.get(candles.size() - 1).getClose();
        double past = candles.get(candles.size() - 1 - period).getClose();
        if (past <= 0.0) return 0.0;
        return ((current / past) - 1.0) * 100.0;
    }
}

