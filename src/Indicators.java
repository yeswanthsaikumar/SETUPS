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
}
