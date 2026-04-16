import java.util.List;

/**
 * Detects market regime (TAILWIND / NEUTRAL / HEADWIND) from benchmark index.
 * Used to gate low-quality signals during weak markets in live scanning.
 */
public class MarketRegimeDetector {
    private final MarketDataProvider marketDataProvider;

    public MarketRegimeDetector(MarketDataProvider marketDataProvider) {
        this.marketDataProvider = marketDataProvider;
    }

    public enum Regime { TAILWIND, NEUTRAL, HEADWIND }

    public static class RegimeContext {
        public final Regime regime;
        public final double marketMomentum20;
        public final double marketMomentum50;
        public final boolean aboveMA50;
        public final boolean aboveMA200;
        public final double marketScore;
        public final String benchmarkSymbol;

        public RegimeContext(Regime regime, double m20, double m50, boolean aboveMA50,
                             boolean aboveMA200, double score, String benchmark) {
            this.regime = regime;
            this.marketMomentum20 = m20;
            this.marketMomentum50 = m50;
            this.aboveMA50 = aboveMA50;
            this.aboveMA200 = aboveMA200;
            this.marketScore = score;
            this.benchmarkSymbol = benchmark;
        }

        @Override
        public String toString() {
            return String.format("MarketRegime[%s bench=%s m20=%.1f%% m50=%.1f%% >MA50=%b >MA200=%b score=%.1f]",
                    regime, benchmarkSymbol, marketMomentum20, marketMomentum50, aboveMA50, aboveMA200, marketScore);
        }
    }

    public RegimeContext detectRegime(List<String> symbols, String timeframe, AppConfig config) {
        String benchmark = inferBenchmark(symbols);
        boolean weekly = "weekly".equalsIgnoreCase(timeframe);
        int lookback = weekly ? 104 : 300;
        try {
            List<Candle> candles = weekly
                    ? marketDataProvider.getWeeklyCandles(benchmark, lookback)
                    : marketDataProvider.getDailyCandles(benchmark, lookback);
            if (candles == null || candles.size() < 55) {
                return new RegimeContext(Regime.NEUTRAL, 0, 0, true, true, 0, benchmark);
            }
            int last = candles.size() - 1;
            double close = candles.get(last).getClose();
            int m20Idx = Math.max(0, last - (weekly ? 4 : 20));
            int m50Idx = Math.max(0, last - (weekly ? 10 : 50));
            double m20 = candles.get(m20Idx).getClose() > 0
                    ? ((close / candles.get(m20Idx).getClose()) - 1.0) * 100.0 : 0.0;
            double m50 = candles.get(m50Idx).getClose() > 0
                    ? ((close / candles.get(m50Idx).getClose()) - 1.0) * 100.0 : 0.0;
            double ma50 = Indicators.movingAverage(candles, last, weekly ? 10 : 50);
            double ma200 = Indicators.movingAverage(candles, last, weekly ? 40 : 200);
            boolean abMA50 = ma50 > 0 && close >= ma50;
            boolean abMA200 = ma200 > 0 && close >= ma200;
            double score = m20 + (abMA50 ? 2.0 : -2.0) + (abMA200 ? 1.5 : -1.5) + (m50 > 0 ? 1.0 : -1.0);
            Regime regime;
            if (score >= config.strongTrendMarketScoreThreshold) regime = Regime.TAILWIND;
            else if (score <= -2.0) regime = Regime.HEADWIND;
            else regime = Regime.NEUTRAL;
            return new RegimeContext(regime, m20, m50, abMA50, abMA200, score, benchmark);
        } catch (Exception ex) {
            return new RegimeContext(Regime.NEUTRAL, 0, 0, true, true, 0, benchmark);
        }
    }

    public boolean shouldFilterSignal(RegimeContext regime, VcpSetup setup, double rsPercentile) {
        if (regime.regime != Regime.HEADWIND) return false;
        String rating = setup.getSetupRating() == null ? "" : setup.getSetupRating().trim().toUpperCase();
        boolean topRated = "A".equals(rating) || "A+".equals(rating);
        return !topRated || rsPercentile < 60.0;
    }

    private String inferBenchmark(List<String> symbols) {
        if (symbols == null || symbols.isEmpty()) return "SPY";
        int india = 0;
        for (String s : symbols) {
            if (s != null && (s.trim().toUpperCase().endsWith(".NS") || s.trim().toUpperCase().endsWith(".BO"))) india++;
        }
        return india > symbols.size() / 2 ? "^NSEI" : "SPY";
    }
}

