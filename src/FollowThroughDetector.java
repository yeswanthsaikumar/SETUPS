import java.util.*;

/**
 * FollowThroughDetector
 * 
 * Identifies follow-through / continuation trades where:
 * 1. A valid breakout occurred days/weeks ago (pivot + buffer)
 * 2. Price pulled back below the pivot (but held key support)
 * 3. Price is now recovering back to or near breakout levels
 * 
 * These are high-probability trades with defined risk and clear structure.
 * Priority: stocks that recovered TODAY or recently (fresher signals).
 */
public class FollowThroughDetector {
    private BreakoutEvaluator breakoutEvaluator;
    private VcpDetector vcpDetector;

    public FollowThroughDetector(BreakoutEvaluator breakoutEvaluator, VcpDetector vcpDetector) {
        this.breakoutEvaluator = breakoutEvaluator;
        this.vcpDetector = vcpDetector;
    }

    public static class FollowThroughResult {
        public final String symbol;
        public final VcpSetup originalSetup;
        public final Candle breakoutCandle;
        public final Candle pullbackLow;
        public final Candle recoverySignal;
        public final int daysSinceBreakout;
        public final int daysInPullback;
        public final double pullbackDepthPct;
        public final double recoveryProgressPct;
        public final double qualityScore;
        public final String reason;

        public FollowThroughResult(
            String symbol,
            VcpSetup originalSetup,
            Candle breakoutCandle,
            Candle pullbackLow,
            Candle recoverySignal,
            int daysSinceBreakout,
            int daysInPullback,
            double pullbackDepthPct,
            double recoveryProgressPct,
            double qualityScore,
            String reason
        ) {
            this.symbol = symbol;
            this.originalSetup = originalSetup;
            this.breakoutCandle = breakoutCandle;
            this.pullbackLow = pullbackLow;
            this.recoverySignal = recoverySignal;
            this.daysSinceBreakout = daysSinceBreakout;
            this.daysInPullback = daysInPullback;
            this.pullbackDepthPct = pullbackDepthPct;
            this.recoveryProgressPct = recoveryProgressPct;
            this.qualityScore = qualityScore;
            this.reason = reason;
        }
    }

    /**
     * Detect follow-through continuation trades from full candle history.
     * Looks back through entire history to find old breakouts that are now recovering.
     * 
     * @param symbol Stock ticker
     * @param candles Full historical candles (many months of data)
     * @param config App configuration
     * @param setupFilter Setup type filter (e.g., "both", "vcp", "range_expansion")
     * @return FollowThroughResult if valid continuation pattern found, null otherwise
     */
    public FollowThroughResult detectFollowThrough(
        String symbol,
        List<Candle> candles,
        AppConfig config,
        String setupFilter
    ) {
        if (candles == null || candles.size() < 60) {
            return null;
        }

        Candle latest = candles.get(candles.size() - 1);
        
        // Scan backwards to find past breakout points (within last ~40 bars for 20-day lookback)
        // For daily: ~40 bars = ~2 months. For weekly: ~40 bars = ~9 months
        int lookbackDepth = Math.min(candles.size() - 1, 40);
        
        for (int breakoutIdx = candles.size() - 2; breakoutIdx >= Math.max(0, candles.size() - lookbackDepth); breakoutIdx--) {
            // Look for a breakout pattern at this index
            VcpSetup setup = vcpDetector.detect(
                new ArrayList<>(candles.subList(0, breakoutIdx + 1)),
                config,
                setupFilter
            );
            
            if (setup == null || setup.getQualityScore() < config.minQualityScore * 0.85) {
                continue; // Not a valid setup at this historical point
            }
            
            Candle candidateBreakout = candles.get(breakoutIdx);
            double pivot = setup.getPivotPrice();
            
            // Was this candle a valid breakout?
            if (candidateBreakout.getClose() <= pivot * (1.0 + config.breakoutBufferPct)) {
                continue; // No breakout at this candle
            }
            
            // Volume check for breakout candle
            int volStart = Math.max(0, breakoutIdx - 19);
            double volAvg = Indicators.averageVolume(candles, volStart, Math.max(0, breakoutIdx - 1));
            if (candidateBreakout.getVolume() < volAvg * config.breakoutVolumeMultiplier * 0.75) {
                continue; // Weak volume
            }
            
            // Now look for pullback after this breakout
            PullbackInfo pullback = findPullbackAfterBreakout(
                candles,
                breakoutIdx,
                pivot,
                config
            );
            
            if (pullback == null) {
                continue; // No valid pullback found
            }
            
            // Look for recovery from pullback
            RecoveryInfo recovery = findRecoveryFromPullback(
                candles,
                pullback,
                pivot,
                config
            );
            
            if (recovery == null || recovery.recoveryIdx <= pullback.lowIdx) {
                continue; // No recovery found
            }
            
            // Calculate quality score for this follow-through pattern
            double ftScore = calculateFollowThroughScore(
                setup,
                candidateBreakout,
                pullback,
                recovery,
                candles
            );
            
            if (ftScore < 30.0) {
                continue; // Too low quality
            }
            
            int daysSinceBreakout = candles.size() - 1 - breakoutIdx;
            int daysInPullback = pullback.lowIdx - breakoutIdx;
            double pullbackDepth = (pivot - pullback.lowPrice) / pivot;
            double recoveryProgress = calculateRecoveryProgress(pivot, pullback.lowPrice, recovery.recoveryClose);
            
            String reason = String.format(
                "Follow-through: breakout %d bars ago, pulled back %.2f%%, now recovering %.1f%% back to pivot",
                daysSinceBreakout,
                pullbackDepth * 100,
                recoveryProgress * 100
            );
            
            return new FollowThroughResult(
                symbol,
                setup,
                candidateBreakout,
                pullback.lowCandle,
                recovery.recoveryCandle,
                daysSinceBreakout,
                daysInPullback,
                pullbackDepth,
                recoveryProgress,
                ftScore,
                reason
            );
        }
        
        return null;
    }

    private static class PullbackInfo {
        int lowIdx;
        double lowPrice;
        Candle lowCandle;
        int pullbackBars;
        double pullbackDepthPct;

        PullbackInfo(int lowIdx, double lowPrice, Candle lowCandle, int pullbackBars, double pullbackDepthPct) {
            this.lowIdx = lowIdx;
            this.lowPrice = lowPrice;
            this.lowCandle = lowCandle;
            this.pullbackBars = pullbackBars;
            this.pullbackDepthPct = pullbackDepthPct;
        }
    }

    private PullbackInfo findPullbackAfterBreakout(
        List<Candle> candles,
        int breakoutIdx,
        double pivot,
        AppConfig config
    ) {
        if (breakoutIdx + 1 >= candles.size()) {
            return null;
        }

        // Look for a low that dips into the support zone (pivot ±1%)
        // within 5-20 bars after breakout
        double supportZone = pivot * 0.99; // Just below pivot
        int maxPullbackBars = Math.min(20, candles.size() - breakoutIdx - 1);

        for (int i = breakoutIdx + 1; i <= breakoutIdx + maxPullbackBars && i < candles.size(); i++) {
            Candle bar = candles.get(i);
            if (bar.getLow() < supportZone) {
                // Found a pullback dip
                double pullbackDepth = (pivot - bar.getLow()) / pivot;
                
                // Valid pullback should be 0.5% to 15% below pivot
                if (pullbackDepth >= 0.005 && pullbackDepth <= 0.15) {
                    int barsInPullback = i - breakoutIdx;
                    return new PullbackInfo(i, bar.getLow(), bar, barsInPullback, pullbackDepth);
                }
            }
        }
        
        return null;
    }

    private static class RecoveryInfo {
        int recoveryIdx;
        double recoveryClose;
        Candle recoveryCandle;

        RecoveryInfo(int recoveryIdx, double recoveryClose, Candle recoveryCandle) {
            this.recoveryIdx = recoveryIdx;
            this.recoveryClose = recoveryClose;
            this.recoveryCandle = recoveryCandle;
        }
    }

    private RecoveryInfo findRecoveryFromPullback(
        List<Candle> candles,
        PullbackInfo pullback,
        double pivot,
        AppConfig config
    ) {
        if (pullback.lowIdx + 1 >= candles.size()) {
            return null;
        }

        // Look for recovery: close back above or near pivot (within 2% above pivot)
        double recoveryTarget = pivot * 1.02; // 2% above pivot for fresh signal
        int maxRecoveryBars = Math.min(15, candles.size() - pullback.lowIdx - 1);

        for (int i = pullback.lowIdx + 1; i <= pullback.lowIdx + maxRecoveryBars && i < candles.size(); i++) {
            Candle bar = candles.get(i);
            
            // Recovery bar should close above pivot or have high touch recovery target
            if (bar.getClose() > pivot * (1.0 + config.breakoutBufferPct) || 
                (bar.getHigh() >= pivot && bar.getClose() > pivot * 0.98)) {
                // Found recovery
                return new RecoveryInfo(i, bar.getClose(), bar);
            }
        }
        
        return null;
    }

    private double calculateFollowThroughScore(
        VcpSetup setup,
        Candle breakoutCandle,
        PullbackInfo pullback,
        RecoveryInfo recovery,
        List<Candle> candles
    ) {
        double score = setup.getQualityScore() * 0.7; // Base on original setup quality
        
        // Bonus for tight pullback (less than 2% below pivot)
        if (pullback.pullbackDepthPct < 0.02) {
            score += 15;
        } else if (pullback.pullbackDepthPct < 0.05) {
            score += 8;
        }
        
        // Bonus for quick recovery (within 3-5 bars of pullback low)
        int recoverySpeed = recovery.recoveryIdx - pullback.lowIdx;
        if (recoverySpeed <= 3) {
            score += 10;
        } else if (recoverySpeed <= 5) {
            score += 5;
        }
        
        // Bonus for volume confirmation on recovery
        int volStart = Math.max(0, pullback.lowIdx - 14);
        double volAvg = Indicators.averageVolume(candles, volStart, pullback.lowIdx - 1);
        if (recovery.recoveryCandle.getVolume() > volAvg * 1.15) {
            score += 8;
        }
        
        return Math.min(100.0, score);
    }

    private double calculateRecoveryProgress(double pivot, double pullbackLow, double recoveryClose) {
        if (pivot <= pullbackLow) {
            return 0.0;
        }
        double range = pivot - pullbackLow;
        double progress = recoveryClose - pullbackLow;
        return Math.max(0.0, Math.min(1.0, progress / range));
    }

    /**
     * Convenience method: detect follow-through for a symbol using cached full history
     */
    public FollowThroughResult detectFollowThrough(
        String symbol,
        List<Candle> candles,
        AppConfig config
    ) {
        return detectFollowThrough(symbol, candles, config, "both");
    }
}

