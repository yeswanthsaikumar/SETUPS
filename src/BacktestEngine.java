import java.util.List;

public class BacktestEngine {
    private final MarketDataProvider marketDataProvider;
    private final ScannerEngine scannerEngine;
    private final String timeframe;
    private final int holdDays;
    private final double targetR;

    public BacktestEngine(MarketDataProvider marketDataProvider, ScannerEngine scannerEngine, String timeframe, int holdDays, double targetR) {
        this.marketDataProvider = marketDataProvider;
        this.scannerEngine = scannerEngine;
        this.timeframe = timeframe;
        this.holdDays = Math.max(2, holdDays);
        this.targetR = Math.max(0.5, targetR);
    }

    public BacktestReport run(List<String> symbols, int lookbackDays) {
        BacktestReport report = new BacktestReport();

        for (String symbol : symbols) {
            List<Candle> candles = "weekly".equalsIgnoreCase(timeframe)
                    ? marketDataProvider.getWeeklyCandles(symbol, lookbackDays)
                    : marketDataProvider.getDailyCandles(symbol, lookbackDays);
            if (candles.size() < 60) {
                continue;
            }

            int i = 40;
            while (i < candles.size() - 2) {
                ScanResult signal = scannerEngine.evaluateAtIndex(symbol, candles, i);
                if (signal == null) {
                    i++;
                    continue;
                }

                report.addSignal();
                SimulatedTrade simulated = simulateTrade(candles, i, signal.getTradePlan());
                report.addTrade(new BacktestTrade(
                        symbol,
                        candles.get(i).getDate(),
                        candles.get(simulated.exitIndex).getDate(),
                        signal.getTradePlan().getEntry(),
                        simulated.exitPrice,
                        signal.getTradePlan().getStopLoss(),
                        signal.getTradePlan().getShares(),
                        simulated.rMultiple,
                        simulated.pnl,
                        simulated.exitReason
                ));

                i = simulated.exitIndex + 1;
            }
        }

        return report;
    }

    private SimulatedTrade simulateTrade(List<Candle> candles, int signalIndex, TradePlan plan) {
        double entry = plan.getEntry();
        double stop = plan.getStopLoss();
        double risk = entry - stop;
        double target = entry + (risk * targetR);

        int last = Math.min(candles.size() - 1, signalIndex + holdDays);
        int exitIndex = last;
        double exitPrice = candles.get(last).getClose();
        String reason = "TIME_EXIT";

        for (int i = signalIndex + 1; i <= last; i++) {
            Candle c = candles.get(i);
            boolean hitStop = c.getLow() <= stop;
            boolean hitTarget = c.getHigh() >= target;

            // Conservative assumption for bars hitting both levels: stop first.
            if (hitStop && hitTarget) {
                exitIndex = i;
                exitPrice = stop;
                reason = "STOP_AND_TARGET_SAME_BAR";
                break;
            }

            if (hitStop) {
                exitIndex = i;
                exitPrice = stop;
                reason = "STOP";
                break;
            }

            if (hitTarget) {
                exitIndex = i;
                exitPrice = target;
                reason = "TARGET";
                break;
            }
        }

        double rMultiple = risk <= 0.0 ? 0.0 : (exitPrice - entry) / risk;
        double pnl = (exitPrice - entry) * plan.getShares();
        return new SimulatedTrade(exitIndex, exitPrice, rMultiple, pnl, reason);
    }

    private static class SimulatedTrade {
        private final int exitIndex;
        private final double exitPrice;
        private final double rMultiple;
        private final double pnl;
        private final String exitReason;

        private SimulatedTrade(int exitIndex, double exitPrice, double rMultiple, double pnl, String exitReason) {
            this.exitIndex = exitIndex;
            this.exitPrice = exitPrice;
            this.rMultiple = rMultiple;
            this.pnl = pnl;
            this.exitReason = exitReason;
        }
    }
}

