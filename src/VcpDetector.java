import java.util.List;

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

        VcpSetup bestSetup = null;

        // ── Setup A: classic VCP contraction breakout base ───────────────────
        if (allowsSetupType(setupFilter, VcpSetup.SetupType.VCP)
                && isBaseHeightAccepted(config, VcpSetup.SetupType.VCP, windowDays, baseRangeHeightPct)
                && isWaveContractionAccepted(contractionStats, config)
                && contractionStats.rangeContractions >= requiredContractionPairs
                && rangeContraction >= requiredRangeContraction
                && volumeContraction >= requiredVolumeContraction) {
            double baseBonus = windowDays <= 20 ? 5.0 : windowDays <= 30 ? 2.0 : 0.0;
            double vcpScore = ((rangeContraction * 0.6) + (volumeContraction * 0.4)) * 100.0 + baseBonus;
            if (vcpScore >= config.minQualityScore) {
                String setupRating = rateSetup(vcpScore, baseRangeHeightPct, contractionDepthPct, windowDays);
                bestSetup = new VcpSetup(
                        VcpSetup.SetupType.VCP,
                        pivot,
                        support,
                        vcpScore,
                        rangeContraction,
                        volumeContraction,
                        0.0,
                        windowDays,
                        windowLabel,
                        baseRangeHeightPct,
                        contractionDepthPct,
                        setupRating,
                        contractionStats.rangeContractions,
                        contractionStats.volumeContractions,
                        contractionStats.totalPairs
                );
            }
        }

        // ── Setup B: contraction then range-expansion breakout entry ─────────
        double rangeExpansion = computeRangeExpansion(candles, consolidationEnd);
        double expansionVolume = computeBreakoutVolumeExpansion(candles, consolidationEnd);

        if (allowsSetupType(setupFilter, VcpSetup.SetupType.RANGE_EXPANSION)
                && isBaseHeightAccepted(config, VcpSetup.SetupType.RANGE_EXPANSION, windowDays, baseRangeHeightPct)
                && rangeContraction >= (requiredRangeContraction * 0.75)
                && rangeExpansion >= requiredRangeExpansion
                && expansionVolume >= requiredExpansionVolume) {
            double expansionScore = (
                    (rangeContraction * 0.35)
                    + (volumeContraction * 0.15)
                    + (Math.min(rangeExpansion / requiredRangeExpansion, 2.0) * 0.35)
                    + (Math.min(expansionVolume / requiredExpansionVolume, 2.0) * 0.15)
            ) * 100.0;

            if (expansionScore >= config.minQualityScore) {
                String setupRating = rateSetup(expansionScore, baseRangeHeightPct, contractionDepthPct, windowDays);
                VcpSetup expansionSetup = new VcpSetup(
                        VcpSetup.SetupType.RANGE_EXPANSION,
                        pivot,
                        support,
                        expansionScore,
                        rangeContraction,
                        volumeContraction,
                        rangeExpansion,
                        windowDays,
                        windowLabel,
                        baseRangeHeightPct,
                        contractionDepthPct,
                        setupRating,
                        contractionStats.rangeContractions,
                        contractionStats.volumeContractions,
                        contractionStats.totalPairs
                );
                if (bestSetup == null || expansionSetup.getQualityScore() > bestSetup.getQualityScore()) {
                    bestSetup = expansionSetup;
                }
            }
        }

        return bestSetup;
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

        return baseHeightPct >= minHeight && baseHeightPct <= maxHeight;
    }

    private String rateSetup(double qualityScore, double baseRangeHeightPct, double contractionDepthPct, int windowDays) {
        double lengthBonus = windowDays >= 60 ? 4.0 : windowDays >= 30 ? 2.0 : 0.0;
        double compactness = baseRangeHeightPct <= 0.0 ? 0.0 : Math.max(0.0, 35.0 - baseRangeHeightPct);
        double ratingScore = qualityScore + (contractionDepthPct * 0.15) + (compactness * 0.10) + lengthBonus;

        if (ratingScore >= 85.0) return "A+";
        if (ratingScore >= 75.0) return "A";
        if (ratingScore >= 65.0) return "B";
        if (ratingScore >= 55.0) return "C";
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
        return true;
    }

    private double safeRatioReduction(double first, double last) {
        if (first <= 0.0) return 0.0;
        return Math.max(0.0, (first - last) / first);
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
}
