import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ScannerEngine {
    private final MarketDataProvider marketDataProvider;
    private final VcpDetector vcpDetector;
    private final BreakoutEvaluator breakoutEvaluator;
    private final TradePlanner tradePlanner;
    private final AppConfig config;
    private final String setupFilter;

    public ScannerEngine(
            MarketDataProvider marketDataProvider,
            VcpDetector vcpDetector,
            BreakoutEvaluator breakoutEvaluator,
            TradePlanner tradePlanner,
            AppConfig config,
            String setupFilter
    ) {
        this.marketDataProvider = marketDataProvider;
        this.vcpDetector = vcpDetector;
        this.breakoutEvaluator = breakoutEvaluator;
        this.tradePlanner = tradePlanner;
        this.config = config;
        this.setupFilter = setupFilter == null ? "both" : setupFilter.toLowerCase();
    }

    public List<ScanResult> scan(List<String> symbols) {
        return scan(symbols, config.lookbackDays, config.timeframe);
    }

    public List<ScanResult> scan(List<String> symbols, int lookbackDays) {
        return scan(symbols, lookbackDays, config.timeframe);
    }

    public List<ScanResult> scan(List<String> symbols, int lookbackBars, String timeframe) {
        List<ScanResult> results = new ArrayList<>();

        for (String symbol : symbols) {
            try {
                List<Candle> candles = loadCandles(symbol, lookbackBars, timeframe);
                ScanResult result = evaluateAtIndex(symbol, candles, candles.size() - 1);
                if (result != null) {
                    results.add(result);
                }
            } catch (RuntimeException ex) {
                System.err.println("Skipping symbol due to data error: " + symbol + " | " + ex.getMessage());
            }
        }

        results.sort(Comparator.comparingDouble(ScanResult::getQualityScore).reversed());
        return results;
    }

    public List<WatchlistResult> scanWatchlist(List<String> symbols, int lookbackBars, String timeframe) {
        List<WatchlistResult> results = new ArrayList<>();

        for (String symbol : symbols) {
            try {
                List<Candle> candles = loadCandles(symbol, lookbackBars, timeframe);
                WatchlistResult result = evaluateWatchlistAtIndex(symbol, candles, candles.size() - 1);
                if (result != null) {
                    results.add(result);
                }
            } catch (RuntimeException ex) {
                System.err.println("Skipping symbol due to data error: " + symbol + " | " + ex.getMessage());
            }
        }

        results.sort(
                Comparator.comparingDouble(WatchlistResult::getQualityScore).reversed()
                        .thenComparingDouble(WatchlistResult::getDistanceToPivotPct)
        );
        return results;
    }

    private List<Candle> loadCandles(String symbol, int lookbackBars, String timeframe) {
        if ("weekly".equalsIgnoreCase(timeframe)) {
            return marketDataProvider.getWeeklyCandles(symbol, lookbackBars);
        }
        return marketDataProvider.getDailyCandles(symbol, lookbackBars);
    }

    public ScanResult evaluateAtIndex(String symbol, List<Candle> candles, int endIndexInclusive) {
        if (candles == null || candles.isEmpty() || endIndexInclusive < 0 || endIndexInclusive >= candles.size()) {
            return null;
        }

        List<Candle> slice = new ArrayList<>(candles.subList(0, endIndexInclusive + 1));
        VcpSetup setup = vcpDetector.detect(slice, config, setupFilter);
        if (setup == null || setup.getQualityScore() < config.minQualityScore) {
            return null;
        }

        boolean breakout = breakoutEvaluator.isBullishBreakout(slice, setup, config);
        boolean nearBreakout = !breakout && breakoutEvaluator.isNearBreakoutContinuation(slice, setup, config);
        if (!breakout && !nearBreakout) {
            return null;
        }

        Candle signalCandle = slice.get(slice.size() - 1);
        TradePlan plan = tradePlanner.buildPlan(signalCandle.getClose(), setup, config);
        if (plan == null) {
            return null;
        }

        String signalType = nearBreakout ? "NEAR_BREAKOUT" : "BREAKOUT";
        return new ScanResult(symbol, setup, signalCandle, plan, signalType);
    }

    public WatchlistResult evaluateWatchlistAtIndex(String symbol, List<Candle> candles, int endIndexInclusive) {
        if (candles == null || candles.isEmpty() || endIndexInclusive < 0 || endIndexInclusive >= candles.size()) {
            return null;
        }

        List<Candle> slice = new ArrayList<>(candles.subList(0, endIndexInclusive + 1));
        VcpSetup setup = vcpDetector.detect(slice, config, setupFilter);
        if (setup == null || setup.getQualityScore() < config.minQualityScore) {
            return null;
        }

        if (breakoutEvaluator.isBullishBreakout(slice, setup, config)) {
            return null; // breakout already triggered; this belongs in open trades, not watchlist
        }

        Candle signalCandle = slice.get(slice.size() - 1);
        double pivot = setup.getPivotPrice();
        if (pivot <= 0.0) {
            return null;
        }

        double distanceToPivotPct = (pivot - signalCandle.getClose()) / pivot;
        if (distanceToPivotPct < 0.0 || distanceToPivotPct > config.watchlistMaxDistanceToPivotPct) {
            return null;
        }

        double plannedEntry = pivot * (1.0 + config.breakoutBufferPct);
        TradePlan plan = tradePlanner.buildPlan(plannedEntry, setup, config);
        if (plan == null) {
            return null;
        }

        return new WatchlistResult(symbol, setup, signalCandle, plan, distanceToPivotPct);
    }
}
