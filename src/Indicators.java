import java.util.List;

public final class Indicators {
    private Indicators() {
    }

    public static double averageClose(List<Candle> candles, int start, int end) {
        if (candles == null || candles.isEmpty()) return 0.0;
        int s = Math.max(0, start);
        int e = Math.min(end, candles.size() - 1);
        double sum = 0.0;
        int count = 0;
        for (int i = s; i <= e; i++) {
            sum += candles.get(i).getClose();
            count++;
        }
        return count == 0 ? 0.0 : sum / count;
    }

    public static double averageVolume(List<Candle> candles, int start, int end) {
        if (candles == null || candles.isEmpty()) return 0.0;
        int s = Math.max(0, start);
        int e = Math.min(end, candles.size() - 1);
        double sum = 0.0;
        int count = 0;
        for (int i = s; i <= e; i++) {
            sum += candles.get(i).getVolume();
            count++;
        }
        return count == 0 ? 0.0 : sum / count;
    }

    public static double highestHigh(List<Candle> candles, int start, int end) {
        if (candles == null || candles.isEmpty()) return 0.0;
        int s = Math.max(0, start);
        int e = Math.min(end, candles.size() - 1);
        double max = Double.NEGATIVE_INFINITY;
        for (int i = s; i <= e; i++) {
            max = Math.max(max, candles.get(i).getHigh());
        }
        return max == Double.NEGATIVE_INFINITY ? 0.0 : max;
    }

    public static double lowestLow(List<Candle> candles, int start, int end) {
        if (candles == null || candles.isEmpty()) return 0.0;
        int s = Math.max(0, start);
        int e = Math.min(end, candles.size() - 1);
        double min = Double.POSITIVE_INFINITY;
        for (int i = s; i <= e; i++) {
            min = Math.min(min, candles.get(i).getLow());
        }
        return min == Double.POSITIVE_INFINITY ? 0.0 : min;
    }

    public static double averageTrueRange(List<Candle> candles, int endIndexInclusive, int period) {
        if (candles == null || candles.isEmpty() || endIndexInclusive <= 0 || endIndexInclusive >= candles.size()) {
            return 0.0;
        }
        int start = Math.max(1, endIndexInclusive - period + 1);
        double sumTr = 0.0;
        int count = 0;

        for (int i = start; i <= endIndexInclusive; i++) {
            Candle current = candles.get(i);
            Candle prev = candles.get(i - 1);
            double tr1 = current.getHigh() - current.getLow();
            double tr2 = Math.abs(current.getHigh() - prev.getClose());
            double tr3 = Math.abs(current.getLow() - prev.getClose());
            double tr = Math.max(tr1, Math.max(tr2, tr3));
            sumTr += tr;
            count++;
        }

        return count == 0 ? 0.0 : sumTr / count;
    }

    /**
     * Simple moving average of close prices ending at endIndex (inclusive).
     */
    public static double movingAverage(List<Candle> candles, int endIndex, int period) {
        if (endIndex < 0 || endIndex >= candles.size() || period <= 0) {
            return 0.0;
        }
        int start = Math.max(0, endIndex - period + 1);
        return averageClose(candles, start, endIndex);
    }

    /**
     * Exponential moving average of close prices ending at endIndex (inclusive).
     */
    public static double exponentialMovingAverage(List<Candle> candles, int endIndex, int period) {
        if (endIndex < 0 || endIndex >= candles.size() || period <= 0) {
            return 0.0;
        }
        int seedEnd = period - 1;
        if (endIndex < seedEnd) {
            return movingAverage(candles, endIndex, endIndex + 1);
        }

        double ema = averageClose(candles, 0, seedEnd);
        double alpha = 2.0 / (period + 1.0);
        for (int i = seedEnd + 1; i <= endIndex; i++) {
            ema = (candles.get(i).getClose() * alpha) + (ema * (1.0 - alpha));
        }
        return ema;
    }

    /**
     * Mean candle range % (high-low)/close * 100 over lookback bars ending at endIndex.
     */
    public static double averageRangePct(List<Candle> candles, int endIndex, int lookback) {
        if (candles == null || candles.isEmpty() || endIndex < 0 || endIndex >= candles.size()) {
            return 0.0;
        }
        int period = Math.max(1, lookback);
        int start = Math.max(0, endIndex - period + 1);
        double sum = 0.0;
        int count = 0;
        for (int i = start; i <= endIndex; i++) {
            Candle c = candles.get(i);
            if (c.getClose() <= 0.0) {
                continue;
            }
            sum += ((c.getHigh() - c.getLow()) / c.getClose()) * 100.0;
            count++;
        }
        return count == 0 ? 0.0 : (sum / count);
    }

    /**
     * Highest high over the full list (used for 52-week high).
     */
    public static double highestHigh(List<Candle> candles) {
        if (candles == null || candles.isEmpty()) return 0.0;
        return highestHigh(candles, 0, candles.size() - 1);
    }

    // ══════════════════════════════════════════════════════════════════════════
    // NEW INDICATORS — Volume Dry-Up, Accumulation/Distribution, Tight Close,
    //                  Liquidity, EMA Fan
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Volume dry-up: checks if the last N bars before breakout have quiet volume.
     * Returns the ratio of recent avg volume to baseline avg volume.
     * A value < 0.70 indicates institutional selling/accumulation is complete.
     *
     * @param candles        Full candle list
     * @param preBreakoutEnd Index of the last bar before breakout (consolidationEnd)
     * @param recentBars     Number of recent bars to measure (e.g., 5)
     * @param baselineBars   Number of baseline bars (e.g., 50)
     * @return ratio (lower = more dried up). 0.0 if insufficient data.
     */
    public static double volumeDryUpRatio(List<Candle> candles, int preBreakoutEnd, int recentBars, int baselineBars) {
        if (candles == null || preBreakoutEnd < recentBars || preBreakoutEnd >= candles.size()) {
            return 1.0; // Not enough data; assume no dry-up
        }
        int recentStart = preBreakoutEnd - recentBars + 1;
        double recentAvgVol = averageVolume(candles, recentStart, preBreakoutEnd);

        int baseStart = Math.max(0, preBreakoutEnd - baselineBars + 1);
        double baseAvgVol = averageVolume(candles, baseStart, preBreakoutEnd);

        if (baseAvgVol <= 0.0) return 1.0;
        return recentAvgVol / baseAvgVol;
    }

    /**
     * Accumulation/Distribution ratio within a consolidation range.
     * Counts up-days on above-average volume (accumulation) vs
     * down-days on above-average volume (distribution).
     *
     * @return ratio of accumDays / distDays. Higher = more healthy base.
     *         Returns 10.0 if zero distribution days (very bullish).
     */
    public static double accumDistRatio(List<Candle> candles, int start, int end) {
        if (candles == null || start < 0 || end >= candles.size() || end <= start) {
            return 1.0;
        }
        double avgVol = averageVolume(candles, start, end);
        int accumDays = 0;
        int distDays = 0;
        for (int i = start; i <= end; i++) {
            Candle c = candles.get(i);
            boolean up = c.getClose() >= c.getOpen();
            boolean highVol = c.getVolume() >= avgVol;
            if (up && highVol) accumDays++;
            if (!up && highVol) distDays++;
        }
        return distDays == 0 ? 10.0 : (double) accumDays / distDays;
    }

    /**
     * Tight-close count: number of consecutive bars (in the last N) where
     * ALL closes fall within maxSpreadPct of the median close.
     *
     * @param candles          Full candle list
     * @param endIndex         Last bar to check
     * @param lookbackBars     How many bars to look back
     * @param maxSpreadPct     Maximum spread between min and max close (e.g., 1.5%)
     * @return count of bars in the tight cluster. Higher = more compressed.
     */
    public static int tightCloseCount(List<Candle> candles, int endIndex, int lookbackBars, double maxSpreadPct) {
        if (candles == null || endIndex < 0 || endIndex >= candles.size()) return 0;
        int start = Math.max(0, endIndex - lookbackBars + 1);
        if (start > endIndex) return 0;

        // Find min and max close in the window
        double minClose = Double.MAX_VALUE;
        double maxClose = Double.MIN_VALUE;
        for (int i = start; i <= endIndex; i++) {
            double cl = candles.get(i).getClose();
            minClose = Math.min(minClose, cl);
            maxClose = Math.max(maxClose, cl);
        }
        if (minClose <= 0.0) return 0;
        double spreadPct = ((maxClose - minClose) / minClose) * 100.0;

        // Count bars whose close is within the tight range
        if (spreadPct <= maxSpreadPct) {
            return endIndex - start + 1; // All bars are tight
        }

        // Otherwise count the longest run of tight bars ending at endIndex
        int count = 0;
        for (int i = endIndex; i >= start; i--) {
            double localMin = Double.MAX_VALUE;
            double localMax = Double.MIN_VALUE;
            for (int j = i; j <= endIndex; j++) {
                localMin = Math.min(localMin, candles.get(j).getClose());
                localMax = Math.max(localMax, candles.get(j).getClose());
            }
            double localSpread = localMin > 0 ? ((localMax - localMin) / localMin) * 100.0 : 999.0;
            if (localSpread <= maxSpreadPct) {
                count = endIndex - i + 1;
            } else {
                break;
            }
        }
        return count;
    }

    /**
     * EMA fan alignment check: 10 EMA > 21 EMA > 50 EMA.
     * Returns true if all three EMAs are stacked bullishly.
     */
    public static boolean isEmaFanAligned(List<Candle> candles, int endIndex) {
        if (candles == null || endIndex < 50 || endIndex >= candles.size()) return false;
        double ema10 = exponentialMovingAverage(candles, endIndex, 10);
        double ema21 = exponentialMovingAverage(candles, endIndex, 21);
        double ema50 = exponentialMovingAverage(candles, endIndex, 50);
        return ema10 > 0 && ema21 > 0 && ema50 > 0 && ema10 > ema21 && ema21 > ema50;
    }
}
