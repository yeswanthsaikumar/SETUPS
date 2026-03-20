import java.util.List;

public class BacktestEngine {
    private final MarketDataProvider marketDataProvider;
    private final ScannerEngine scannerEngine;
    private final String timeframe;
    private final int holdDays;

    public BacktestEngine(MarketDataProvider marketDataProvider, ScannerEngine scannerEngine,
                          String timeframe, int holdDays, double targetR) {
        this.marketDataProvider = marketDataProvider;
        this.scannerEngine = scannerEngine;
        this.timeframe = timeframe;
        this.holdDays = Math.max(2, holdDays);
    }

    public BacktestReport run(List<String> symbols, int lookbackDays) {
        BacktestReport report = new BacktestReport();

        for (String symbol : symbols) {
            List<Candle> candles = "weekly".equalsIgnoreCase(timeframe)
                    ? marketDataProvider.getWeeklyCandles(symbol, lookbackDays)
                    : marketDataProvider.getDailyCandles(symbol, lookbackDays);
            if (candles.size() < 60) continue;

            int i = 40;
            while (i < candles.size() - 2) {
                ScanResult signal = scannerEngine.evaluateAtIndex(symbol, candles, i);
                if (signal == null) { i++; continue; }

                report.addSignal();
                TradePlan plan = signal.getTradePlan();
                VcpSetup setup = signal.getSetup();
                SimulatedTrade sim = simulateTrade(candles, i, plan);

                report.addTrade(new BacktestTrade(
                        symbol,
                        candles.get(i).getDate(),
                        candles.get(sim.exitIndex).getDate(),
                        plan.getEntry(), sim.exitPrice, plan.getStopLoss(), plan.getShares(),
                        sim.rMultiple, sim.pnl, sim.exitReason,
                        // setup metadata
                        setup.getSetupType().toString(),
                        setup.getSetupRating(),
                        setup.getBaseWindowLabel(),
                        setup.getQualityScore(),
                        // analytics
                        sim.mae, sim.mfe, sim.holdBars,
                        sim.hitT1, sim.hitT2, sim.hitT3
                ));

                i = sim.exitIndex + 1;
            }
        }

        return report;
    }

    private SimulatedTrade simulateTrade(List<Candle> candles, int signalIndex, TradePlan plan) {
        double entry  = plan.getEntry();
        double stop   = plan.getStopLoss();
        double risk   = entry - stop;
        double t1     = plan.getTarget1();
        double t2     = plan.getTarget2();
        double t3     = plan.getTarget3();

        int last = Math.min(candles.size() - 1, signalIndex + holdDays);
        int exitIndex  = last;
        double exitPrice = candles.get(last).getClose();
        String reason  = "TIME_EXIT";

        boolean hitT1 = false, hitT2 = false, hitT3 = false;
        double mae = 0.0, mfe = 0.0;

        for (int i = signalIndex + 1; i <= last; i++) {
            Candle c = candles.get(i);

            // Max adverse / favorable excursion (% from entry)
            if (entry > 0) {
                mae = Math.max(mae, Math.max(0.0, (entry - c.getLow())  / entry) * 100.0);
                mfe = Math.max(mfe, Math.max(0.0, (c.getHigh() - entry) / entry) * 100.0);
            }

            boolean barHitStop   = c.getLow()  <= stop;
            boolean barHitTarget = c.getHigh() >= t1;

            // Conservative: if both hit same bar, assume stop fills first
            if (barHitStop && barHitTarget) {
                exitIndex = i; exitPrice = stop; reason = "STOP_AND_TARGET_SAME_BAR"; break;
            }
            if (barHitStop) {
                exitIndex = i; exitPrice = stop; reason = "STOP"; break;
            }
            if (c.getHigh() >= t3) {
                exitIndex = i; exitPrice = t3; reason = "TARGET_T3";
                hitT1 = true; hitT2 = true; hitT3 = true; break;
            }
            if (c.getHigh() >= t2) {
                exitIndex = i; exitPrice = t2; reason = "TARGET_T2";
                hitT1 = true; hitT2 = true; break;
            }
            if (c.getHigh() >= t1) {
                exitIndex = i; exitPrice = t1; reason = "TARGET_T1";
                hitT1 = true; break;
            }
        }

        int holdBars    = exitIndex - signalIndex;
        double rMultiple = risk <= 0.0 ? 0.0 : (exitPrice - entry) / risk;
        double pnl       = (exitPrice - entry) * plan.getShares();
        return new SimulatedTrade(exitIndex, exitPrice, rMultiple, pnl, reason,
                hitT1, hitT2, hitT3, mae, mfe, holdBars);
    }

    private static class SimulatedTrade {
        final int exitIndex;
        final double exitPrice, rMultiple, pnl, mae, mfe;
        final String exitReason;
        final boolean hitT1, hitT2, hitT3;
        final int holdBars;

        SimulatedTrade(int exitIndex, double exitPrice, double rMultiple, double pnl,
                       String exitReason, boolean hitT1, boolean hitT2, boolean hitT3,
                       double mae, double mfe, int holdBars) {
            this.exitIndex = exitIndex;
            this.exitPrice = exitPrice;
            this.rMultiple = rMultiple;
            this.pnl = pnl;
            this.exitReason = exitReason;
            this.hitT1 = hitT1;
            this.hitT2 = hitT2;
            this.hitT3 = hitT3;
            this.mae = mae;
            this.mfe = mfe;
            this.holdBars = holdBars;
        }
    }
}
