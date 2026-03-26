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
    private final MultiTimeframeAlignmentAnalyzer alignmentAnalyzer;
    private final List<RejectionDiagnostic> lastRejections;

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
        this.alignmentAnalyzer = new MultiTimeframeAlignmentAnalyzer(
                marketDataProvider, vcpDetector, breakoutEvaluator, config
        );
        this.lastRejections = new ArrayList<>();
    }

    public List<RejectionDiagnostic> getLastRejections() {
        return new ArrayList<>(lastRejections);
    }

    public List<ScanResult> scan(List<String> symbols) {
        return scan(symbols, config.lookbackDays, config.timeframe);
    }

    public List<ScanResult> scan(List<String> symbols, int lookbackDays) {
        return scan(symbols, lookbackDays, config.timeframe);
    }

    public List<ScanResult> scan(List<String> symbols, int lookbackBars, String timeframe) {
        List<ScanResult> results = new ArrayList<>();
        lastRejections.clear();

        for (String symbol : symbols) {
            try {
                List<Candle> candles = loadCandles(symbol, lookbackBars, timeframe);
                ScanResult result = evaluateAtIndex(symbol, candles, candles.size() - 1);
                if (result != null) {
                    results.add(result);
                } else {
                    RejectionDiagnostic rejection = diagnoseScanRejection(symbol, candles, candles.size() - 1, timeframe);
                    if (rejection != null) {
                        lastRejections.add(rejection);
                    }
                }
            } catch (RuntimeException ex) {
                System.err.println("Skipping symbol due to data error: " + symbol + " | " + ex.getMessage());
                lastRejections.add(new RejectionDiagnostic(
                        symbol,
                        "scan",
                        timeframe,
                        RejectionDiagnostic.Reason.DATA_ERROR,
                        ex.getMessage()
                ));
            }
        }

        results.sort(Comparator.comparingDouble(ScanResult::getQualityScore).reversed());
        return results;
    }

    public List<WatchlistResult> scanWatchlist(List<String> symbols, int lookbackBars, String timeframe) {
        List<WatchlistResult> results = new ArrayList<>();
        lastRejections.clear();

        for (String symbol : symbols) {
            try {
                List<Candle> candles = loadCandles(symbol, lookbackBars, timeframe);
                WatchlistResult result = evaluateWatchlistAtIndex(symbol, candles, candles.size() - 1);
                if (result != null) {
                    results.add(result);
                } else {
                    RejectionDiagnostic rejection = diagnoseWatchlistRejection(symbol, candles, candles.size() - 1, timeframe);
                    if (rejection != null) {
                        lastRejections.add(rejection);
                    }
                }
            } catch (RuntimeException ex) {
                System.err.println("Skipping symbol due to data error: " + symbol + " | " + ex.getMessage());
                lastRejections.add(new RejectionDiagnostic(
                        symbol,
                        "watchlist",
                        timeframe,
                        RejectionDiagnostic.Reason.DATA_ERROR,
                        ex.getMessage()
                ));
            }
        }

        results.sort(
                Comparator.comparingDouble(WatchlistResult::getQualityScore).reversed()
                        .thenComparingDouble(WatchlistResult::getDistanceToPivotPct)
        );
        return results;
    }

    public List<AlreadyBreakoutResult> scanAlreadyBreakout(
            List<String> symbols,
            int lookbackBars,
            String timeframe,
            int minBarsSinceBreakout,
            int maxBarsSinceBreakout
    ) {
        List<AlreadyBreakoutResult> results = new ArrayList<>();
        lastRejections.clear();

        int minBars = Math.max(1, minBarsSinceBreakout);
        int maxBars = Math.max(minBars, maxBarsSinceBreakout);

        for (String symbol : symbols) {
            try {
                List<Candle> candles = loadCandles(symbol, lookbackBars, timeframe);
                AlreadyBreakoutResult result = evaluateAlreadyBreakoutAtIndex(
                        symbol,
                        candles,
                        candles.size() - 1,
                        minBars,
                        maxBars
                );
                if (result != null) {
                    results.add(result);
                }
            } catch (RuntimeException ex) {
                System.err.println("Skipping symbol due to data error: " + symbol + " | " + ex.getMessage());
                lastRejections.add(new RejectionDiagnostic(
                        symbol,
                        "already_breakout",
                        timeframe,
                        RejectionDiagnostic.Reason.DATA_ERROR,
                        ex.getMessage()
                ));
            }
        }

        results.sort(Comparator.comparingDouble(AlreadyBreakoutResult::getReturnSinceBreakoutPct).reversed());
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
        ScanResult result = new ScanResult(symbol, setup, signalCandle, plan, signalType);

        // Apply multi-timeframe alignment analysis
        // Only for daily scans; skip for weekly scans
        if (!"weekly".equalsIgnoreCase(config.timeframe)) {
            try {
                MultiTimeframeAlignmentAnalyzer.MultiTimeframeContext alignment = 
                        alignmentAnalyzer.analyzeAlignmentForDaily(symbol, setup, slice);
                if (alignment.alignmentBonus > 0.0) {
                    result.setAlignmentBonus(alignment.alignmentBonus, alignment.alignmentReason, true);
                }
            } catch (Exception ex) {
                // Alignment analysis failed; continue without bonus
                // This is safe—weekly data might be unavailable or have issues
            }
        }

        return result;
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

        WatchlistResult result = new WatchlistResult(symbol, setup, signalCandle, plan, distanceToPivotPct);

        // Apply multi-timeframe alignment analysis
        // Only for daily scans; skip for weekly scans
        if (!"weekly".equalsIgnoreCase(config.timeframe)) {
            try {
                MultiTimeframeAlignmentAnalyzer.MultiTimeframeContext alignment = 
                        alignmentAnalyzer.analyzeAlignmentForWatchlist(symbol, setup, slice);
                if (alignment.alignmentBonus > 0.0) {
                    result.setAlignmentBonus(alignment.alignmentBonus, alignment.alignmentReason, true);
                }
            } catch (Exception ex) {
                // Alignment analysis failed; continue without bonus
                // This is safe—weekly data might be unavailable or have issues
            }
        }

        return result;
    }

    public AlreadyBreakoutResult evaluateAlreadyBreakoutAtIndex(
            String symbol,
            List<Candle> candles,
            int endIndexInclusive,
            int minBarsSinceBreakout,
            int maxBarsSinceBreakout
    ) {
        if (candles == null || candles.isEmpty() || endIndexInclusive < 0 || endIndexInclusive >= candles.size()) {
            return null;
        }

        int minBars = Math.max(1, minBarsSinceBreakout);
        int maxBars = Math.max(minBars, maxBarsSinceBreakout);
        if (endIndexInclusive - minBars < 10) {
            return null;
        }

        int newestBreakoutIndex = endIndexInclusive - minBars;
        int oldestBreakoutIndex = Math.max(10, endIndexInclusive - maxBars);
        for (int breakoutIdx = newestBreakoutIndex; breakoutIdx >= oldestBreakoutIndex; breakoutIdx--) {
            ScanResult historicalSignal = evaluateAtIndex(symbol, candles, breakoutIdx);
            if (historicalSignal == null || !"BREAKOUT".equalsIgnoreCase(historicalSignal.getSignalType())) {
                continue;
            }
            VcpSetup setup = historicalSignal.getSetup();

            Candle breakoutCandle = candles.get(breakoutIdx);
            Candle latestCandle = candles.get(endIndexInclusive);
            double breakoutPrice = breakoutCandle.getClose();
            if (breakoutPrice <= 0.0) {
                continue;
            }

            int barsSinceBreakout = endIndexInclusive - breakoutIdx;
            double returnSinceBreakoutPct = ((latestCandle.getClose() / breakoutPrice) - 1.0) * 100.0;
            double maxGainPct = Double.NEGATIVE_INFINITY;
            double maxDrawdownPct = Double.POSITIVE_INFINITY;
            int pivotHoldBars = 0;
            int observedBars = 0;
            double pivotFloor = setup.getPivotPrice() * (1.0 - config.breakoutBufferPct);

            for (int i = breakoutIdx + 1; i <= endIndexInclusive; i++) {
                Candle c = candles.get(i);
                double gainPct = ((c.getHigh() / breakoutPrice) - 1.0) * 100.0;
                double drawdownPct = ((c.getLow() / breakoutPrice) - 1.0) * 100.0;
                maxGainPct = Math.max(maxGainPct, gainPct);
                maxDrawdownPct = Math.min(maxDrawdownPct, drawdownPct);
                if (c.getLow() >= pivotFloor) {
                    pivotHoldBars++;
                }
                observedBars++;
            }

            if (maxGainPct == Double.NEGATIVE_INFINITY) {
                maxGainPct = returnSinceBreakoutPct;
            }
            if (maxDrawdownPct == Double.POSITIVE_INFINITY) {
                maxDrawdownPct = returnSinceBreakoutPct;
            }
            double pivotHoldRatePct = observedBars == 0 ? 100.0 : (pivotHoldBars * 100.0) / observedBars;

            return new AlreadyBreakoutResult(
                    symbol,
                    setup,
                    breakoutCandle.getDate(),
                    breakoutPrice,
                    latestCandle,
                    barsSinceBreakout,
                    returnSinceBreakoutPct,
                    maxGainPct,
                    maxDrawdownPct,
                    pivotHoldRatePct
            );
        }

        return null;
    }

    private RejectionDiagnostic diagnoseScanRejection(String symbol, List<Candle> candles, int endIndexInclusive, String timeframe) {
        if (candles == null || candles.isEmpty() || endIndexInclusive < 0 || endIndexInclusive >= candles.size()) {
            return new RejectionDiagnostic(symbol, "scan", timeframe, RejectionDiagnostic.Reason.INSUFFICIENT_DATA, "No usable candles");
        }

        List<Candle> slice = new ArrayList<>(candles.subList(0, endIndexInclusive + 1));
        RejectionDiagnostic preGate = diagnosePreSetupGate(symbol, "scan", timeframe, slice);
        if (preGate != null) {
            return preGate;
        }

        VcpSetup setup = vcpDetector.detect(slice, config, setupFilter);
        if (setup == null) {
            return new RejectionDiagnostic(symbol, "scan", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY, "No valid setup detected");
        }
        if (setup.getQualityScore() < config.minQualityScore) {
            return new RejectionDiagnostic(symbol, "scan", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY,
                    String.format("setupScore=%.2f < min=%.2f", setup.getQualityScore(), config.minQualityScore));
        }

        boolean breakout = breakoutEvaluator.isBullishBreakout(slice, setup, config);
        boolean nearBreakout = !breakout && breakoutEvaluator.isNearBreakoutContinuation(slice, setup, config);
        if (!breakout && !nearBreakout) {
            RejectionDiagnostic.Reason reason = breakoutEvaluator.classifyBreakoutRejection(slice, setup, config);
            return new RejectionDiagnostic(symbol, "scan", timeframe, reason, "Failed breakout/near-breakout confirmation");
        }

        Candle signalCandle = slice.get(slice.size() - 1);
        TradePlan plan = tradePlanner.buildPlan(signalCandle.getClose(), setup, config);
        if (plan == null) {
            return new RejectionDiagnostic(symbol, "scan", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY, "Trade plan could not be built");
        }

        return null;
    }

    private RejectionDiagnostic diagnoseWatchlistRejection(String symbol, List<Candle> candles, int endIndexInclusive, String timeframe) {
        if (candles == null || candles.isEmpty() || endIndexInclusive < 0 || endIndexInclusive >= candles.size()) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.INSUFFICIENT_DATA, "No usable candles");
        }

        List<Candle> slice = new ArrayList<>(candles.subList(0, endIndexInclusive + 1));
        RejectionDiagnostic preGate = diagnosePreSetupGate(symbol, "watchlist", timeframe, slice);
        if (preGate != null) {
            return preGate;
        }

        VcpSetup setup = vcpDetector.detect(slice, config, setupFilter);
        if (setup == null) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY, "No valid setup detected");
        }
        if (setup.getQualityScore() < config.minQualityScore) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY,
                    String.format("setupScore=%.2f < min=%.2f", setup.getQualityScore(), config.minQualityScore));
        }

        if (breakoutEvaluator.isBullishBreakout(slice, setup, config)) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.ALREADY_BROKEN_OUT,
                    "Already in breakout state");
        }

        Candle signalCandle = slice.get(slice.size() - 1);
        double pivot = setup.getPivotPrice();
        if (pivot <= 0.0) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY, "Invalid pivot");
        }

        double distanceToPivotPct = (pivot - signalCandle.getClose()) / pivot;
        if (distanceToPivotPct < 0.0 || distanceToPivotPct > config.watchlistMaxDistanceToPivotPct) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.TOO_FAR_FROM_PIVOT,
                    String.format("distanceToPivotPct=%.4f max=%.4f", distanceToPivotPct, config.watchlistMaxDistanceToPivotPct));
        }

        double plannedEntry = pivot * (1.0 + config.breakoutBufferPct);
        TradePlan plan = tradePlanner.buildPlan(plannedEntry, setup, config);
        if (plan == null) {
            return new RejectionDiagnostic(symbol, "watchlist", timeframe, RejectionDiagnostic.Reason.LOW_QUALITY, "Trade plan could not be built");
        }

        return null;
    }

    private RejectionDiagnostic diagnosePreSetupGate(String symbol, String mode, String timeframe, List<Candle> slice) {
        if (slice.size() < 3) {
            return new RejectionDiagnostic(symbol, mode, timeframe, RejectionDiagnostic.Reason.INSUFFICIENT_DATA, "Too few candles");
        }

        double latestClose = slice.get(slice.size() - 1).getClose();
        if (latestClose < config.minPrice) {
            return new RejectionDiagnostic(symbol, mode, timeframe, RejectionDiagnostic.Reason.LOW_PRICE,
                    String.format("close=%.2f minPrice=%.2f", latestClose, config.minPrice));
        }

        int highLookback = Math.min(slice.size(), config.annualHighLookbackBars);
        double high52w = Indicators.highestHigh(slice, slice.size() - highLookback, slice.size() - 1);
        if (high52w > 0) {
            double distanceFromHigh = (high52w - latestClose) / high52w;
            if (distanceFromHigh > config.maxDistanceFrom52WkHighPct) {
                return new RejectionDiagnostic(symbol, mode, timeframe, RejectionDiagnostic.Reason.FAR_FROM_52W_HIGH,
                        String.format("distance=%.4f max=%.4f", distanceFromHigh, config.maxDistanceFrom52WkHighPct));
            }
        }

        if (config.requireAboveMA) {
            int baseEndIdx = slice.size() - 2;
            if (baseEndIdx >= 0) {
                double ma = Indicators.movingAverage(slice, baseEndIdx, config.maPeriod);
                if (ma > 0 && slice.get(baseEndIdx).getClose() < ma) {
                    return new RejectionDiagnostic(symbol, mode, timeframe, RejectionDiagnostic.Reason.BELOW_MA,
                            String.format("close=%.2f ma=%.2f", slice.get(baseEndIdx).getClose(), ma));
                }
            }
        }

        return null;
    }
}
