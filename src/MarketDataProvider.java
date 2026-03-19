import java.util.List;

public interface MarketDataProvider {
    List<Candle> getDailyCandles(String symbol, int lookbackDays);

    default List<Candle> getWeeklyCandles(String symbol, int lookbackWeeks) {
        int requiredDailyBars = Math.max(lookbackWeeks * 7, lookbackWeeks + 60);
        List<Candle> dailyCandles = getDailyCandles(symbol, requiredDailyBars);
        return CandleAggregationUtils.tail(CandleAggregationUtils.toWeekly(dailyCandles), lookbackWeeks);
    }
}

