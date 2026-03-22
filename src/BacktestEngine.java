import java.util.ArrayList;
import java.util.List;

public class BacktestEngine {
    private final MarketDataProvider marketDataProvider;
    private final ScannerEngine scannerEngine;
    private final String timeframe;
    private final int holdDays;
    private final AppConfig config;

    public BacktestEngine(MarketDataProvider marketDataProvider, ScannerEngine scannerEngine,
                          String timeframe, int holdDays, double targetR) {
        this.marketDataProvider = marketDataProvider;
        this.scannerEngine = scannerEngine;
        this.timeframe = timeframe;
        this.holdDays = Math.max(2, holdDays);
        this.config = new AppConfig(timeframe);
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
                SimulatedTrade sim = simulateTrade(candles, i, plan, setup);

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

    private SimulatedTrade simulateTrade(List<Candle> candles, int signalIndex, TradePlan plan, VcpSetup setup) {
        double entry  = plan.getEntry();
        double initialStop = plan.getStopLoss();
        double stop   = initialStop;
        double risk   = entry - initialStop;
        double t1     = plan.getTarget1();
        double t2     = plan.getTarget2();
        double t3     = plan.getTarget3();

        int effectiveHold = resolveHoldDays(setup);
        int last = Math.min(candles.size() - 1, signalIndex + effectiveHold);
        int exitIndex  = last;
        double exitPrice = candles.get(last).getClose();
        String reason  = "TIME_EXIT";

        boolean hitT1 = false, hitT2 = false, hitT3 = false;
        double mae = 0.0, mfe = 0.0;

        // Partial exit model:
        // - config.partialExitPctAtT1 at T1
        // - config.partialExitPctAtT2 at T2
        // - remaining trails using ATR and/or swing-low after breakout confirmation
        double remaining = 1.0;
        double realizedPerShare = 0.0;
        boolean trailingEnabled = false;
        int atrPeriod = "weekly".equalsIgnoreCase(timeframe)
                ? config.atrTrailPeriodWeekly : config.atrTrailPeriodDaily;
        int swingLookback = "weekly".equalsIgnoreCase(timeframe)
                ? config.swingLookbackWeekly : config.swingLookbackDaily;
        double atrMult = trailingAtrMultiplier(setup);
        double partialT1 = Math.max(0.0, Math.min(1.0, config.partialExitPctAtT1));
        double partialT2 = Math.max(0.0, Math.min(1.0 - partialT1, config.partialExitPctAtT2));
        double breakoutConfirmLevel = entry * (1.0 + config.breakoutBufferPct);
        List<String> tags = new ArrayList<>();

        for (int i = signalIndex + 1; i <= last; i++) {
            Candle c = candles.get(i);

            // Max adverse / favorable excursion (% from entry)
            if (entry > 0) {
                mae = Math.max(mae, Math.max(0.0, (entry - c.getLow())  / entry) * 100.0);
                mfe = Math.max(mfe, Math.max(0.0, (c.getHigh() - entry) / entry) * 100.0);
            }

            // Conservative: stop executes before any target fills on same bar.
            if (remaining > 0.0 && c.getLow() <= stop) {
                realizedPerShare += remaining * (stop - entry);
                remaining = 0.0;
                exitIndex = i;
                exitPrice = stop;
                reason = trailingEnabled ? "TRAIL_STOP" : "STOP";
                tags.add(reason);
                break;
            }

            if (!hitT1 && c.getHigh() >= t1) {
                double qty = Math.min(remaining, partialT1);
                realizedPerShare += qty * (t1 - entry);
                remaining -= qty;
                hitT1 = true;
                tags.add("PARTIAL_T1");
            }

            if (!hitT2 && c.getHigh() >= t2) {
                double qty = Math.min(remaining, partialT2);
                realizedPerShare += qty * (t2 - entry);
                remaining -= qty;
                hitT2 = true;
                tags.add("PARTIAL_T2");
            }

            if (c.getHigh() >= t3) {
                hitT3 = true;
            }

            if (remaining <= 0.0) {
                exitIndex = i;
                exitPrice = c.getClose();
                reason = "TARGET_T2_FULLY_EXITED";
                break;
            }

            // Enable trailing once breakout is confirmed by close above entry buffer.
            if (!trailingEnabled && c.getClose() >= breakoutConfirmLevel) {
                trailingEnabled = true;
                tags.add("TRAIL_ACTIVE");
            }

            if (trailingEnabled) {
                double atr = Indicators.averageTrueRange(candles, i, atrPeriod);
                double atrStop = stop;
                if (config.enableAtrTrailingStop && atr > 0.0) {
                    atrStop = c.getClose() - (atrMult * atr);
                }
                int swingStart = Math.max(signalIndex + 1, i - swingLookback + 1);
                double swingLow = Indicators.lowestLow(candles, swingStart, i);
                double swingStop = stop;
                if (config.enableSwingLowTrailingStop) {
                    swingStop = swingLow * (1.0 - config.swingStopBufferPct);
                }
                stop = Math.max(stop, Math.max(atrStop, swingStop));
            }
        }

        int holdBars    = exitIndex - signalIndex;
        if (remaining > 0.0) {
            realizedPerShare += remaining * (exitPrice - entry);
        }
        double weightedExit = entry + realizedPerShare;
        double rMultiple = risk <= 0.0 ? 0.0 : (realizedPerShare / risk);
        double pnl       = realizedPerShare * plan.getShares();
        exitPrice = weightedExit;
        if (!tags.isEmpty() && "TIME_EXIT".equals(reason)) {
            reason = String.join("+", tags) + "+TIME_EXIT";
        } else if (!tags.isEmpty() && ("STOP".equals(reason) || "TRAIL_STOP".equals(reason))) {
            reason = String.join("+", tags) + "+" + reason;
        }
        return new SimulatedTrade(exitIndex, exitPrice, rMultiple, pnl, reason,
                hitT1, hitT2, hitT3, mae, mfe, holdBars);
    }

    private int resolveHoldDays(VcpSetup setup) {
        boolean weeklyTf = "weekly".equalsIgnoreCase(timeframe);
        boolean rangeExpansion = setup.getSetupType() == VcpSetup.SetupType.RANGE_EXPANSION;
        int profileHold;
        if (weeklyTf && rangeExpansion) {
            profileHold = config.holdBarsWeeklyRangeExpansion;
        } else if (weeklyTf) {
            profileHold = config.holdBarsWeeklyVcp;
        } else if (rangeExpansion) {
            profileHold = config.holdBarsDailyRangeExpansion;
        } else {
            profileHold = config.holdBarsDailyVcp;
        }
        // Keep CLI holdDays as a global cap for backward-compatible control.
        return Math.max(2, Math.min(profileHold, holdDays));
    }

    private double trailingAtrMultiplier(VcpSetup setup) {
        boolean weeklyTf = "weekly".equalsIgnoreCase(timeframe);
        boolean rangeExpansion = setup.getSetupType() == VcpSetup.SetupType.RANGE_EXPANSION;
        if (weeklyTf && rangeExpansion) {
            return config.atrTrailMultWeeklyRangeExpansion;
        }
        if (weeklyTf) {
            return config.atrTrailMultWeeklyVcp;
        }
        if (rangeExpansion) {
            return config.atrTrailMultDailyRangeExpansion;
        }
        return config.atrTrailMultDailyVcp;
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
