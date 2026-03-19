import java.util.List;

public final class Indicators {
    private Indicators() {
    }

    public static double averageClose(List<Candle> candles, int start, int end) {
        double sum = 0.0;
        int count = 0;
        for (int i = start; i <= end; i++) {
            sum += candles.get(i).getClose();
            count++;
        }
        return count == 0 ? 0.0 : sum / count;
    }

    public static double averageVolume(List<Candle> candles, int start, int end) {
        double sum = 0.0;
        int count = 0;
        for (int i = start; i <= end; i++) {
            sum += candles.get(i).getVolume();
            count++;
        }
        return count == 0 ? 0.0 : sum / count;
    }

    public static double highestHigh(List<Candle> candles, int start, int end) {
        double max = Double.NEGATIVE_INFINITY;
        for (int i = start; i <= end; i++) {
            max = Math.max(max, candles.get(i).getHigh());
        }
        return max;
    }

    public static double lowestLow(List<Candle> candles, int start, int end) {
        double min = Double.POSITIVE_INFINITY;
        for (int i = start; i <= end; i++) {
            min = Math.min(min, candles.get(i).getLow());
        }
        return min;
    }

    public static double averageTrueRange(List<Candle> candles, int endIndexInclusive, int period) {
        if (endIndexInclusive <= 0 || endIndexInclusive >= candles.size()) {
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
     * Highest high over the full list (used for 52-week high).
     */
    public static double highestHigh(List<Candle> candles) {
        return highestHigh(candles, 0, candles.size() - 1);
    }
}
