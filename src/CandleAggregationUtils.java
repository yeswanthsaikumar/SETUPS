import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.ArrayList;
import java.util.List;

public final class CandleAggregationUtils {
    private static final WeekFields WEEK_FIELDS = WeekFields.ISO;

    private CandleAggregationUtils() {
    }

    public static List<Candle> toWeekly(List<Candle> dailyCandles) {
        List<Candle> weekly = new ArrayList<>();
        if (dailyCandles == null || dailyCandles.isEmpty()) {
            return weekly;
        }

        Candle first = dailyCandles.get(0);
        int currentWeek = weekOfYear(first.getDate());
        int currentYear = weekBasedYear(first.getDate());
        LocalDate currentDate = first.getDate();
        double currentOpen = first.getOpen();
        double currentHigh = first.getHigh();
        double currentLow = first.getLow();
        double currentClose = first.getClose();
        long currentVolume = first.getVolume();

        for (int i = 1; i < dailyCandles.size(); i++) {
            Candle candle = dailyCandles.get(i);
            int week = weekOfYear(candle.getDate());
            int year = weekBasedYear(candle.getDate());

            if (week != currentWeek || year != currentYear) {
                weekly.add(new Candle(currentDate, currentOpen, currentHigh, currentLow, currentClose, currentVolume));
                currentWeek = week;
                currentYear = year;
                currentDate = candle.getDate();
                currentOpen = candle.getOpen();
                currentHigh = candle.getHigh();
                currentLow = candle.getLow();
                currentClose = candle.getClose();
                currentVolume = candle.getVolume();
                continue;
            }

            currentDate = candle.getDate();
            currentHigh = Math.max(currentHigh, candle.getHigh());
            currentLow = Math.min(currentLow, candle.getLow());
            currentClose = candle.getClose();
            currentVolume += candle.getVolume();
        }

        weekly.add(new Candle(currentDate, currentOpen, currentHigh, currentLow, currentClose, currentVolume));
        return weekly;
    }

    public static List<Candle> tail(List<Candle> candles, int maxBars) {
        if (candles == null || candles.isEmpty() || maxBars <= 0) {
            return List.of();
        }
        if (candles.size() <= maxBars) {
            return new ArrayList<>(candles);
        }
        return new ArrayList<>(candles.subList(candles.size() - maxBars, candles.size()));
    }

    private static int weekOfYear(LocalDate date) {
        return date.get(WEEK_FIELDS.weekOfWeekBasedYear());
    }

    private static int weekBasedYear(LocalDate date) {
        return date.get(WEEK_FIELDS.weekBasedYear());
    }
}

