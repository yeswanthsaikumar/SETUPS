import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class SampleMarketDataProvider implements MarketDataProvider {
    @Override
    public List<Candle> getDailyCandles(String symbol, int lookbackDays) {
        long seed = symbol.hashCode() * 31L;
        Random random = new Random(seed);

        List<Candle> candles = new ArrayList<>();
        LocalDate startDate = LocalDate.now().minusDays(lookbackDays + 30L);

        double price = 80.0 + (Math.abs(symbol.hashCode()) % 60);
        long baseVolume = 800_000L + (Math.abs(symbol.hashCode()) % 500_000);

        if ("NVCP".equalsIgnoreCase(symbol) || "VCPX".equalsIgnoreCase(symbol)) {
            if (lookbackDays < 35) {
                addRandomDays(candles, startDate, 0, lookbackDays, random, baseVolume, price, 1.2, 0.9);
                return candles;
            }

            int usedDays = 0;
            if (lookbackDays >= 80) {
                int leadDays = lookbackDays - 80;
                usedDays += addRandomDays(candles, startDate, usedDays, leadDays, random, baseVolume, price, 1.1, 0.8);
                if (!candles.isEmpty()) {
                    price = candles.get(candles.size() - 1).getClose();
                }

                buildBullishVcpSequence(candles, startDate.plusDays(usedDays), price, baseVolume);
                usedDays += 35;
                price = candles.get(candles.size() - 1).getClose();

                usedDays += addRandomDays(candles, startDate, usedDays, 10, random, baseVolume, price, 1.4, 1.0);
                price = candles.get(candles.size() - 1).getClose();

                buildBullishVcpSequence(candles, startDate.plusDays(usedDays), price, baseVolume);
            } else {
                int leadDays = lookbackDays - 35;
                if (leadDays > 0) {
                    addRandomDays(candles, startDate, 0, leadDays, random, baseVolume, price, 1.1, 0.8);
                    price = candles.get(candles.size() - 1).getClose();
                }
                buildBullishVcpSequence(candles, startDate.plusDays(lookbackDays - 35L), price, baseVolume);
            }
        } else {
            addRandomDays(candles, startDate, 0, lookbackDays, random, baseVolume, price, 1.8, 1.2);
        }

        return candles;
    }

    private int addRandomDays(
            List<Candle> candles,
            LocalDate startDate,
            int startOffset,
            int days,
            Random random,
            long baseVolume,
            double startPrice,
            double driftScale,
            double wickScale
    ) {
        int added = 0;
        double price = startPrice;
        for (int i = 0; i < days; i++) {
            double drift = (random.nextDouble() - 0.48) * driftScale;
            double close = Math.max(5.0, price + drift);
            double high = Math.max(price, close) + random.nextDouble() * wickScale;
            double low = Math.min(price, close) - random.nextDouble() * wickScale;
            long volume = Math.max(100_000L, (long) (baseVolume * (0.75 + random.nextDouble() * 0.5)));
            candles.add(new Candle(startDate.plusDays(startOffset + i), price, high, low, close, volume));
            price = close;
            added++;
        }
        return added;
    }

    private void buildBullishVcpSequence(List<Candle> candles, LocalDate start, double lastPrice, long baseVolume) {
        double center = Math.max(20.0, lastPrice);
        int dayOffset = 0;
        dayOffset = addWave(candles, start, dayOffset, center, 10, 0.14, baseVolume, 0.95);
        dayOffset = addWave(candles, start, dayOffset, center * 1.01, 10, 0.09, baseVolume, 0.70);
        dayOffset = addWave(candles, start, dayOffset, center * 1.015, 10, 0.05, baseVolume, 0.52);

        double pivot = Indicators.highestHigh(candles, candles.size() - 30, candles.size() - 1);
        double handleClose = center * 1.02;

        // Add a tight handle under pivot so consolidation remains intact before the breakout bar.
        while (dayOffset < 34) {
            double open = handleClose * 0.999;
            double close = handleClose * (0.998 + ((dayOffset % 2) * 0.002));
            double high = Math.max(open, close) * 1.004;
            double low = Math.min(open, close) * 0.996;
            long volume = (long) (baseVolume * 0.55);
            candles.add(new Candle(start.plusDays(dayOffset), open, high, low, close, volume));
            handleClose = close;
            dayOffset++;
        }

        double open = pivot * 1.001;
        double close = pivot * 1.026;
        double high = pivot * 1.034;
        double low = pivot * 0.997;
        long volume = (long) (baseVolume * 1.95);
        candles.add(new Candle(start.plusDays(dayOffset), open, high, low, close, volume));
    }

    private int addWave(
            List<Candle> candles,
            LocalDate start,
            int dayOffset,
            double center,
            int days,
            double rangePct,
            long baseVolume,
            double volumeScale
    ) {
        for (int i = 0; i < days; i++) {
            double angle = (2 * Math.PI * i) / (days - 1);
            double close = center + (Math.sin(angle) * center * rangePct * 0.5);
            double open = center + (Math.cos(angle) * center * rangePct * 0.35);
            double localHigh = Math.max(open, close) * (1 + rangePct * 0.25);
            double localLow = Math.min(open, close) * (1 - rangePct * 0.25);
            long volume = (long) (baseVolume * volumeScale * (1.0 - (i * 0.02)));
            candles.add(new Candle(start.plusDays(dayOffset), open, localHigh, localLow, close, Math.max(100_000L, volume)));
            dayOffset++;
        }
        return dayOffset;
    }
}

