import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * Detects a bullish Volatility Contraction Pattern (VCP) setup.
 *
 * Improvements over v1:
 *  1. Tries multiple consolidation window lengths (20/30/45/60 bars) — keeps best score.
 *  2. Wave contraction allows up to N misses (configurable) so organic bases aren't rejected.
 *  3. Trend filter: close must be above configurable-period MA at base end.
 *  4. 52-week high proximity: base must form near highs, not in a downtrend.
 *  5. Minimum price filter: skips penny stocks.
 */
public class VcpDetector {
    private final Map<VcpSetup.SetupType, SetupDetector> detectorRegistry;

    public VcpDetector() {
        this.detectorRegistry = new EnumMap<>(VcpSetup.SetupType.class);
        detectorRegistry.put(VcpSetup.SetupType.VCP, this::detectClassicVcp);
        detectorRegistry.put(VcpSetup.SetupType.RANGE_EXPANSION, this::detectRangeExpansionSetup);
        detectorRegistry.put(VcpSetup.SetupType.MEAN_REVERSION, this::detectMeanReversionSetup);
    }

    public VcpSetup detect(List<Candle> candles, AppConfig config) {
        return detect(candles, config, "both");
    }

    public VcpSetup detect(List<Candle> candles, AppConfig config, String setupFilter) {
        if (candles == null || candles.size() < minBarsForAnyWindow(config)) {
            return null;
        }

        // ── Gate 1: minimum price ──────────────────────────────────────────────
        double latestClose = candles.get(candles.size() - 1).getClose();
        if (latestClose < config.minPrice) {
            return null;
        }

        // ── Gate 2: 52-week high proximity ────────────────────────────────────
        // Stock must be within maxDistanceFrom52WkHighPct of its trailing 1-year high.
        int highLookback = Math.min(candles.size(), config.annualHighLookbackBars);
        double high52w = Indicators.highestHigh(candles,
                candles.size() - highLookback, candles.size() - 1);
        if (high52w > 0) {
            double distanceFromHigh = (high52w - latestClose) / high52w;
            if (distanceFromHigh > config.maxDistanceFrom52WkHighPct) {
                return null;   // base is too far below 52-week high — likely a downtrend
            }
        }

        // ── Gate 3: trend filter (price above MA at base end) ─────────────────
        if (config.requireAboveMA) {
            int baseEndIdx = candles.size() - 2;   // second-to-last bar (last bar is breakout)
            double ma = Indicators.movingAverage(candles, baseEndIdx, config.maPeriod);
            if (ma > 0 && candles.get(baseEndIdx).getClose() < ma) {
                return null;   // stock is below MA — not in an uptrend
            }
        }

        // ── Try every configured consolidation window; keep highest-scoring setup ──
        VcpSetup best = null;
        for (int windowDays : config.consolidationWindows) {
            VcpSetup candidate = detectForWindow(candles, config, windowDays, setupFilter);
            if (candidate != null) {
                if (best == null || candidate.getQualityScore() > best.getQualityScore()) {
                    best = candidate;
                }
            }
        }
        return best;
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Core detection for a specific window length
    // ──────────────────────────────────────────────────────────────────────────
    private VcpSetup detectForWindow(List<Candle> candles, AppConfig config, int windowDays, String setupFilter) {
        if (candles.size() < windowDays + 2) {
            return null;
        }

        int consolidationEnd   = candles.size() - 2;
        int consolidationStart = consolidationEnd - windowDays + 1;
        if (consolidationStart < 0) {
            return null;
        }

        int waveSize = windowDays / config.waveCount;
        int minWaveSize = "weekly".equalsIgnoreCase(config.timeframe) ? 2 : 3;
        if (waveSize < minWaveSize) {
            return null;
        }

        // ── Compute range and volume for each wave ────────────────────────────
        double[] waveRanges  = new double[config.waveCount];
        double[] waveVolumes = new double[config.waveCount];

        for (int i = 0; i < config.waveCount; i++) {
            int start = consolidationStart + (i * waveSize);
            int end   = (i == config.waveCount - 1) ? consolidationEnd : (start + waveSize - 1);
            end = Math.min(end, consolidationEnd);

            double high     = Indicators.highestHigh(candles, start, end);
            double low      = Indicators.lowestLow(candles, start, end);
            double avgClose = Indicators.averageClose(candles, start, end);
            waveRanges[i]   = avgClose == 0.0 ? 0.0 : (high - low) / avgClose;
            waveVolumes[i]  = Indicators.averageVolume(candles, start, end);
        }

        // ── Overall first-to-last ratios used by both setup flavors ───────────
        double rangeContraction = safeRatioReduction(waveRanges[0], waveRanges[config.waveCount - 1]);
        double volumeContraction = safeRatioReduction(waveVolumes[0], waveVolumes[config.waveCount - 1]);

        // ── ATR contraction: late volatility must not be expanding ────────────
        double atrEarly = Indicators.averageTrueRange(candles, consolidationStart + waveSize, 10);
        double atrLate  = Indicators.averageTrueRange(candles, consolidationEnd, 10);
        boolean atrOk   = atrLate <= 0 || atrEarly >= (atrLate * 0.90);  // 10% slack
        if (!atrOk) return null;

        // ── Build setup ───────────────────────────────────────────────────────
        double pivot   = Indicators.highestHigh(candles, consolidationStart, consolidationEnd);
        double support = Indicators.lowestLow(candles, consolidationStart, consolidationEnd);
        double avgBaseClose = Indicators.averageClose(candles, consolidationStart, consolidationEnd);
        double baseRangeHeightPct = avgBaseClose <= 0.0 ? 0.0 : ((pivot - support) / avgBaseClose) * 100.0;
        double contractionDepthPct = rangeContraction * 100.0;
        String windowLabel = classifyWindow(config.timeframe, windowDays);
        double requiredRangeContraction = dynamicRangeContractionThreshold(config, windowDays);
        double requiredVolumeContraction = dynamicVolumeContractionThreshold(config, windowDays);
        double requiredRangeExpansion = dynamicRangeExpansionThreshold(config, windowDays);
        double requiredExpansionVolume = dynamicExpansionVolumeThreshold(config, windowDays);
        ContractionStats contractionStats = calculateContractionStats(waveRanges, waveVolumes);
        int requiredContractionPairs = requiredContractionPairs(config, windowDays, contractionStats.totalPairs);

        int breakoutIndex = consolidationEnd + 1;
        SetupDetectionContext ctx = new SetupDetectionContext(
                candles,
                config,
                windowDays,
                consolidationStart,
                consolidationEnd,
                breakoutIndex,
                pivot,
                support,
                rangeContraction,
                volumeContraction,
                baseRangeHeightPct,
                contractionDepthPct,
                windowLabel,
                requiredRangeContraction,
                requiredVolumeContraction,
                requiredRangeExpansion,
                requiredExpansionVolume,
                requiredContractionPairs,
                contractionStats,
                computeRangeExpansion(candles, consolidationEnd),
                computeBreakoutVolumeExpansion(candles, consolidationEnd),
                computeWickBodyAdjustment(candles, breakoutIndex, config)
        );

        VcpSetup bestSetup = null;
        for (Map.Entry<VcpSetup.SetupType, SetupDetector> entry : detectorRegistry.entrySet()) {
            if (!allowsSetupType(setupFilter, entry.getKey())) {
                continue;
            }
            VcpSetup candidate = entry.getValue().detect(ctx);
            if (candidate != null && (bestSetup == null || candidate.getQualityScore() > bestSetup.getQualityScore())) {
                bestSetup = candidate;
            }
        }
        return bestSetup;
    }

    private VcpSetup detectClassicVcp(SetupDetectionContext ctx) {
        if (!isBaseHeightAccepted(ctx.config, VcpSetup.SetupType.VCP, ctx.windowDays, ctx.baseRangeHeightPct)
                || !isWaveContractionAccepted(ctx.contractionStats, ctx.config)
                || ctx.contractionStats.rangeContractions < ctx.requiredContractionPairs
                || ctx.rangeContraction < ctx.requiredRangeContraction
                || ctx.volumeContraction < ctx.requiredVolumeContraction) {
            return null;
        }

        double baseBonus = ctx.windowDays <= 20 ? 5.0 : ctx.windowDays <= 30 ? 2.0 : 0.0;
        double score = ((ctx.rangeContraction * 0.6) + (ctx.volumeContraction * 0.4)) * 100.0 + baseBonus + ctx.wickBodyAdjustment;
        if (score < ctx.config.minQualityScore) {
            return null;
        }

        return buildSetup(ctx, VcpSetup.SetupType.VCP, score, 0.0);
    }

    private VcpSetup detectRangeExpansionSetup(SetupDetectionContext ctx) {
        if (!isBaseHeightAccepted(ctx.config, VcpSetup.SetupType.RANGE_EXPANSION, ctx.windowDays, ctx.baseRangeHeightPct)
                || ctx.rangeContraction < (ctx.requiredRangeContraction * 0.75)
                || ctx.rangeExpansion < ctx.requiredRangeExpansion
                || ctx.expansionVolume < ctx.requiredExpansionVolume) {
            return null;
        }

        double score = (
                (ctx.rangeContraction * 0.35)
                        + (ctx.volumeContraction * 0.15)
                        + (Math.min(ctx.rangeExpansion / ctx.requiredRangeExpansion, 2.0) * 0.35)
                        + (Math.min(ctx.expansionVolume / ctx.requiredExpansionVolume, 2.0) * 0.15)
        ) * 100.0 + ctx.wickBodyAdjustment;

        if (score < ctx.config.minQualityScore) {
            return null;
        }
        return buildSetup(ctx, VcpSetup.SetupType.RANGE_EXPANSION, score, ctx.rangeExpansion);
    }

    private VcpSetup detectMeanReversionSetup(SetupDetectionContext ctx) {
        if (!isBaseHeightAccepted(ctx.config, VcpSetup.SetupType.MEAN_REVERSION, ctx.windowDays, ctx.baseRangeHeightPct)
                || ctx.breakoutIndex <= 0
                || ctx.breakoutIndex >= ctx.candles.size()) {
            return null;
        }

        Candle breakout = ctx.candles.get(ctx.breakoutIndex);
        Candle prior = ctx.candles.get(ctx.breakoutIndex - 1);

        int meanPeriod = Math.max(6, Math.min(20, ctx.windowDays / 3));
        double reversionMean = Indicators.movingAverage(ctx.candles, ctx.consolidationEnd, meanPeriod);
        if (reversionMean <= 0.0) {
            return null;
        }

        double pullbackPct = (reversionMean - ctx.supportPrice) / reversionMean;
        if (pullbackPct < ctx.config.meanReversionMinPullbackPct || pullbackPct > ctx.config.meanReversionMaxPullbackPct) {
            return null;
        }

        double recoveryPct = prior.getClose() <= 0.0 ? 0.0 : (breakout.getClose() - prior.getClose()) / prior.getClose();
        if (recoveryPct < ctx.config.meanReversionMinRecoveryPct) {
            return null;
        }

        int triggerStart = Math.max(ctx.consolidationStart, ctx.breakoutIndex - 3);
        double triggerPrice = Indicators.highestHigh(ctx.candles, triggerStart, ctx.breakoutIndex - 1);
        if (triggerPrice <= ctx.supportPrice) {
            return null;
        }

        int volStart = Math.max(ctx.consolidationStart, ctx.breakoutIndex - 10);
        double avgVolume = Indicators.averageVolume(ctx.candles, volStart, ctx.breakoutIndex - 1);
        double volumeRecovery = avgVolume <= 0.0 ? 0.0 : breakout.getVolume() / avgVolume;
        if (volumeRecovery < ctx.config.meanReversionNearVolumeMultiplier) {
            return null;
        }

        double span = Math.max(1e-6, (ctx.config.meanReversionMaxPullbackPct - ctx.config.meanReversionMinPullbackPct) / 2.0);
        double targetPullback = (ctx.config.meanReversionMaxPullbackPct + ctx.config.meanReversionMinPullbackPct) / 2.0;
        double pullbackFit = clamp01(1.0 - Math.abs(pullbackPct - targetPullback) / span);
        double structureScore = clamp01(ctx.rangeContraction / Math.max(0.001, ctx.requiredRangeContraction)) * 10.0;
        double pullbackScore = pullbackFit * 22.0;
        double recoveryScore = Math.min(2.0, recoveryPct / Math.max(0.001, ctx.config.meanReversionMinRecoveryPct)) * 12.0;
        double volumeScore = Math.min(2.0, volumeRecovery / Math.max(0.001, ctx.config.meanReversionVolumeMultiplier)) * 8.0;

        double score = pullbackScore + recoveryScore + volumeScore + structureScore + ctx.wickBodyAdjustment;
        if (score < ctx.config.minQualityScore) {
            return null;
        }

        return new VcpSetup(
                VcpSetup.SetupType.MEAN_REVERSION,
                triggerPrice,
                ctx.supportPrice,
                score,
                ctx.rangeContraction,
                ctx.volumeContraction,
                Math.max(0.0, recoveryPct),
                ctx.windowDays,
                ctx.windowLabel,
                ctx.baseRangeHeightPct,
                ctx.contractionDepthPct,
                rateSetup(score, ctx.baseRangeHeightPct, ctx.contractionDepthPct, ctx.windowDays),
                ctx.contractionStats.rangeContractions,
                ctx.contractionStats.volumeContractions,
                ctx.contractionStats.totalPairs
        );
    }

    private VcpSetup buildSetup(SetupDetectionContext ctx, VcpSetup.SetupType setupType, double score, double rangeExpansion) {
        return new VcpSetup(
                setupType,
                ctx.pivotPrice,
                ctx.supportPrice,
                score,
                ctx.rangeContraction,
                ctx.volumeContraction,
                rangeExpansion,
                ctx.windowDays,
                ctx.windowLabel,
                ctx.baseRangeHeightPct,
                ctx.contractionDepthPct,
                rateSetup(score, ctx.baseRangeHeightPct, ctx.contractionDepthPct, ctx.windowDays),
                ctx.contractionStats.rangeContractions,
                ctx.contractionStats.volumeContractions,
                ctx.contractionStats.totalPairs
        );
    }

    private boolean isWaveContractionAccepted(ContractionStats stats, AppConfig config) {
        return stats.rangeMisses <= config.waveContractionMissTolerance
                && stats.volumeMisses <= config.waveContractionMissTolerance;
    }

    private ContractionStats calculateContractionStats(double[] waveRanges, double[] waveVolumes) {
        ContractionStats stats = new ContractionStats();
        stats.totalPairs = Math.max(0, waveRanges.length - 1);
        for (int i = 1; i < waveRanges.length; i++) {
            if (waveRanges[i] < waveRanges[i - 1]) {
                stats.rangeContractions++;
            } else {
                stats.rangeMisses++;
            }
            if (waveVolumes[i] <= waveVolumes[i - 1] * 1.05) {
                stats.volumeContractions++;
            } else {
                stats.volumeMisses++;
            }
        }
        return stats;
    }

    private double computeRangeExpansion(List<Candle> candles, int consolidationEnd) {
        int breakoutIndex = consolidationEnd + 1;
        if (breakoutIndex <= 0 || breakoutIndex >= candles.size()) {
            return 0.0;
        }
        Candle breakout = candles.get(breakoutIndex);
        double breakoutRange = Math.max(0.0, breakout.getHigh() - breakout.getLow());
        double preBreakAtr = Indicators.averageTrueRange(candles, consolidationEnd, 10);
        if (preBreakAtr <= 0.0) {
            return 0.0;
        }
        return breakoutRange / preBreakAtr;
    }

    private double computeBreakoutVolumeExpansion(List<Candle> candles, int consolidationEnd) {
        int breakoutIndex = consolidationEnd + 1;
        int start = Math.max(0, consolidationEnd - 9);
        if (breakoutIndex >= candles.size() || start > consolidationEnd) {
            return 0.0;
        }
        double baseVolume = Indicators.averageVolume(candles, start, consolidationEnd);
        if (baseVolume <= 0.0) {
            return 0.0;
        }
        return candles.get(breakoutIndex).getVolume() / baseVolume;
    }

    private double dynamicRangeContractionThreshold(AppConfig config, int windowDays) {
        double base = config.minRangeContraction;
        if (windowDays >= 180) return Math.max(0.10, base - 0.04);
        if (windowDays >= 120) return Math.max(0.11, base - 0.03);
        if (windowDays >= 60) return Math.max(0.12, base - 0.02);
        if (windowDays <= 15) return Math.min(0.30, base + 0.04);
        if (windowDays <= 30) return Math.min(0.28, base + 0.02);
        return base;
    }

    private double dynamicVolumeContractionThreshold(AppConfig config, int windowDays) {
        double base = config.minVolumeContraction;
        if (windowDays >= 180) return Math.max(0.05, base - 0.03);
        if (windowDays >= 120) return Math.max(0.06, base - 0.02);
        if (windowDays <= 15) return Math.min(0.22, base + 0.03);
        if (windowDays <= 30) return Math.min(0.20, base + 0.02);
        return base;
    }

    private double dynamicRangeExpansionThreshold(AppConfig config, int windowDays) {
        double base = config.minRangeExpansionMultiplier;
        if (windowDays >= 180) return Math.max(1.10, base - 0.10);
        if (windowDays >= 120) return Math.max(1.12, base - 0.07);
        if (windowDays <= 15) return base + 0.10;
        if (windowDays <= 30) return base + 0.05;
        return base;
    }

    private double dynamicExpansionVolumeThreshold(AppConfig config, int windowDays) {
        double base = config.minExpansionVolumeMultiplier;
        if (windowDays >= 180) return Math.max(1.00, base - 0.05);
        if (windowDays >= 120) return Math.max(1.02, base - 0.03);
        if (windowDays <= 15) return base + 0.08;
        return base;
    }

    private String classifyWindow(String timeframe, int windowDays) {
        if ("weekly".equalsIgnoreCase(timeframe)) {
            if (windowDays >= 52) return "Q4";
            if (windowDays >= 39) return "Q3";
            if (windowDays >= 26) return "Q2";
            if (windowDays >= 13) return "Q1";
            return "WEEK";
        }
        if (windowDays >= 240) return "Q4";
        if (windowDays >= 180) return "Q3";
        if (windowDays >= 120) return "Q2";
        if (windowDays >= 60) return "Q1";
        return "WEEK";
    }

    private boolean isBaseHeightAccepted(AppConfig config, VcpSetup.SetupType type, int windowDays, double baseHeightPct) {
        if (baseHeightPct <= 0.0) {
            return false;
        }

        boolean weekly = "weekly".equalsIgnoreCase(config.timeframe);
        double minHeight = config.minBaseHeightPct;
        double maxHeight = config.maxBaseHeightPct;

        // Short windows need tighter bases; long windows can be wider.
        if ((weekly && windowDays <= 13) || (!weekly && windowDays <= 30)) {
            maxHeight = Math.min(maxHeight, config.shortWindowHeightCapPct);
        } else if ((weekly && windowDays >= 39) || (!weekly && windowDays >= 120)) {
            maxHeight = Math.min(maxHeight, config.longWindowHeightCapPct);
            minHeight = Math.max(weekly ? 8.0 : 6.0, minHeight);
        }

        // Range-expansion breakouts tolerate slightly wider bases than strict VCP.
        if (type == VcpSetup.SetupType.RANGE_EXPANSION) {
            maxHeight += weekly ? 6.0 : 5.0;
        }

        // Mean-reversion entries can accept a bit wider pullback structures.
        if (type == VcpSetup.SetupType.MEAN_REVERSION) {
            minHeight = Math.max(weekly ? 4.0 : 3.0, minHeight - 2.0);
            maxHeight += weekly ? 8.0 : 6.0;
        }

        return baseHeightPct >= minHeight && baseHeightPct <= maxHeight;
    }

    private String rateSetup(double qualityScore, double baseRangeHeightPct, double contractionDepthPct, int windowDays) {
        double lengthBonus = windowDays >= 60 ? 4.0 : windowDays >= 30 ? 2.0 : 0.0;
        double compactness = baseRangeHeightPct <= 0.0 ? 0.0 : Math.max(0.0, 35.0 - baseRangeHeightPct);
        double ratingScore = qualityScore + (contractionDepthPct * 0.15) + (compactness * 0.10) + lengthBonus;

        // Thresholds raised vs original (85/75/65/55) for higher-conviction signals only
        if (ratingScore >= 95.0) return "A+";
        if (ratingScore >= 83.0) return "A";
        if (ratingScore >= 72.0) return "B";
        if (ratingScore >= 62.0) return "C";
        return "D";
    }

    private int requiredContractionPairs(AppConfig config, int windowDays, int totalPairs) {
        if (totalPairs <= 0) {
            return 0;
        }
        boolean weekly = "weekly".equalsIgnoreCase(config.timeframe);
        boolean shortWindow = (weekly && windowDays <= 13) || (!weekly && windowDays <= 30);
        boolean longWindow = (weekly && windowDays >= 39) || (!weekly && windowDays >= 120);

        double ratio = shortWindow
                ? config.shortWindowContractionPairRatio
                : longWindow ? config.longWindowContractionPairRatio : 0.75;

        int required = (int) Math.ceil(totalPairs * ratio);
        return Math.max(1, Math.min(totalPairs, required));
    }

    private boolean allowsSetupType(String setupFilter, VcpSetup.SetupType setupType) {
        String normalized = setupFilter == null ? "both" : setupFilter.trim().toLowerCase();
        if ("vcp".equals(normalized)) {
            return setupType == VcpSetup.SetupType.VCP;
        }
        if ("range_expansion".equals(normalized)) {
            return setupType == VcpSetup.SetupType.RANGE_EXPANSION;
        }
        if ("mean_reversion".equals(normalized)) {
            return setupType == VcpSetup.SetupType.MEAN_REVERSION;
        }
        return true;
    }

    private double clamp01(double value) {
        if (value < 0.0) return 0.0;
        return Math.min(1.0, value);
    }

    private double safeRatioReduction(double first, double last) {
        if (first <= 0.0) return 0.0;
        return Math.max(0.0, (first - last) / first);
    }

    private double computeWickBodyAdjustment(List<Candle> candles, int breakoutIndex, AppConfig config) {
        if (candles == null || candles.isEmpty() || breakoutIndex <= 0 || breakoutIndex >= candles.size()) {
            return 0.0;
        }

        int lookbackBars = Math.max(1, config.wickBiasLookbackBars);
        int start = Math.max(0, breakoutIndex - lookbackBars + 1);

        double weightedSum = 0.0;
        double weightTotal = 0.0;
        for (int i = start; i <= breakoutIndex; i++) {
            Candle c = candles.get(i);
            double range = c.getHigh() - c.getLow();
            if (range <= 0.0) {
                continue;
            }

            double bodyDirectional = (c.getClose() - c.getOpen()) / range;
            double lowerWick = Math.max(0.0, Math.min(c.getOpen(), c.getClose()) - c.getLow()) / range;
            double upperWick = Math.max(0.0, c.getHigh() - Math.max(c.getOpen(), c.getClose())) / range;

            double candleBias =
                    (bodyDirectional * config.bodyDirectionalWeight)
                    + (lowerWick * config.lowerWickPositiveWeight)
                    - (upperWick * config.upperWickNegativeWeight);

            // Recency-weight candles so breakout candle anatomy contributes the most.
            double recencyWeight = (i - start + 1);
            weightedSum += candleBias * recencyWeight;
            weightTotal += recencyWeight;
        }

        if (weightTotal <= 0.0) {
            return 0.0;
        }

        double normalizedBias = weightedSum / weightTotal;
        double adjustment = normalizedBias * config.maxWickBodyScoreAdjustment;
        double maxAbs = Math.max(0.0, config.maxWickBodyScoreAdjustment);
        return Math.max(-maxAbs, Math.min(maxAbs, adjustment));
    }

    private int minBarsForAnyWindow(AppConfig config) {
        int minWindow = Integer.MAX_VALUE;
        for (int w : config.consolidationWindows) {
            minWindow = Math.min(minWindow, w);
        }
        // Need base window bars plus one prior candle and one breakout candle.
        return minWindow == Integer.MAX_VALUE ? 20 : (minWindow + 2);
    }

    private static final class ContractionStats {
        private int rangeContractions;
        private int volumeContractions;
        private int rangeMisses;
        private int volumeMisses;
        private int totalPairs;
    }

    private interface SetupDetector {
        VcpSetup detect(SetupDetectionContext ctx);
    }

    private static final class SetupDetectionContext {
        private final List<Candle> candles;
        private final AppConfig config;
        private final int windowDays;
        private final int consolidationStart;
        private final int consolidationEnd;
        private final int breakoutIndex;
        private final double pivotPrice;
        private final double supportPrice;
        private final double rangeContraction;
        private final double volumeContraction;
        private final double baseRangeHeightPct;
        private final double contractionDepthPct;
        private final String windowLabel;
        private final double requiredRangeContraction;
        private final double requiredVolumeContraction;
        private final double requiredRangeExpansion;
        private final double requiredExpansionVolume;
        private final int requiredContractionPairs;
        private final ContractionStats contractionStats;
        private final double rangeExpansion;
        private final double expansionVolume;
        private final double wickBodyAdjustment;

        private SetupDetectionContext(
                List<Candle> candles,
                AppConfig config,
                int windowDays,
                int consolidationStart,
                int consolidationEnd,
                int breakoutIndex,
                double pivotPrice,
                double supportPrice,
                double rangeContraction,
                double volumeContraction,
                double baseRangeHeightPct,
                double contractionDepthPct,
                String windowLabel,
                double requiredRangeContraction,
                double requiredVolumeContraction,
                double requiredRangeExpansion,
                double requiredExpansionVolume,
                int requiredContractionPairs,
                ContractionStats contractionStats,
                double rangeExpansion,
                double expansionVolume,
                double wickBodyAdjustment
        ) {
            this.candles = candles;
            this.config = config;
            this.windowDays = windowDays;
            this.consolidationStart = consolidationStart;
            this.consolidationEnd = consolidationEnd;
            this.breakoutIndex = breakoutIndex;
            this.pivotPrice = pivotPrice;
            this.supportPrice = supportPrice;
            this.rangeContraction = rangeContraction;
            this.volumeContraction = volumeContraction;
            this.baseRangeHeightPct = baseRangeHeightPct;
            this.contractionDepthPct = contractionDepthPct;
            this.windowLabel = windowLabel;
            this.requiredRangeContraction = requiredRangeContraction;
            this.requiredVolumeContraction = requiredVolumeContraction;
            this.requiredRangeExpansion = requiredRangeExpansion;
            this.requiredExpansionVolume = requiredExpansionVolume;
            this.requiredContractionPairs = requiredContractionPairs;
            this.contractionStats = contractionStats;
            this.rangeExpansion = rangeExpansion;
            this.expansionVolume = expansionVolume;
            this.wickBodyAdjustment = wickBodyAdjustment;
        }
    }
}
