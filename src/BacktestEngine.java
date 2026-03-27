import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class BacktestEngine {
    private final MarketDataProvider marketDataProvider;
    private final ScannerEngine scannerEngine;
    private final String timeframe;
    private final AppConfig config;
    private final String benchmarkSymbol;

    public BacktestEngine(MarketDataProvider marketDataProvider, ScannerEngine scannerEngine,
                          String timeframe, int holdDays, String benchmarkSymbol) {
        if (holdDays < 1) {
            throw new IllegalArgumentException("Invalid holdDays");
        }
        this.marketDataProvider = marketDataProvider;
        this.scannerEngine = scannerEngine;
        this.timeframe = timeframe;
        this.config = new AppConfig(timeframe);
        this.benchmarkSymbol = benchmarkSymbol == null ? "" : benchmarkSymbol.trim();
    }

    public BacktestReport run(List<String> symbols, int lookbackDays) {
        BacktestReport report = new BacktestReport();
        String resolvedBenchmark = resolveBenchmarkSymbol(symbols);
        List<Candle> benchmarkCandles = "weekly".equalsIgnoreCase(timeframe)
                ? marketDataProvider.getWeeklyCandles(resolvedBenchmark, lookbackDays)
                : marketDataProvider.getDailyCandles(resolvedBenchmark, lookbackDays);
        Map<java.time.LocalDate, Integer> benchmarkByDate = buildDateIndex(benchmarkCandles);

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
                java.time.LocalDate entryDate = candles.get(i).getDate();
                double entryMarketStrength = marketStrengthScore(benchmarkCandles, benchmarkByDate, entryDate);
                double relativeStrengthScore = relativeStrengthScore(candles, i, benchmarkCandles, benchmarkByDate, entryDate);
                SimulatedTrade sim = simulateTrade(candles, i, plan, entryMarketStrength);
                java.time.LocalDate exitDate = candles.get(sim.exitIndex).getDate();
                double benchmarkReturn = benchmarkReturnPct(benchmarkCandles, benchmarkByDate, entryDate, exitDate);
                double tradeReturnPct = plan.getEntry() <= 0.0 ? 0.0 : ((sim.exitPrice / plan.getEntry()) - 1.0) * 100.0;
                double alphaPct = tradeReturnPct - benchmarkReturn;
                double riskPerShare = Math.max(0.0, plan.getEntry() - plan.getStopLoss());
                double rewardToRiskT1 = riskPerShare > 0.0
                        ? Math.max(0.0, (plan.getTarget1() - plan.getEntry()) / riskPerShare)
                        : 0.0;
                double positionRiskAmount = riskPerShare * plan.getShares();
                double positionNotional = plan.getEntry() * plan.getShares();
                double pivot = setup.getPivotPrice();
                double pivotDistancePct = pivot > 0.0
                        ? ((plan.getEntry() / pivot) - 1.0) * 100.0
                        : 0.0;
                String entryMarketRegime = classifyEntryMarketRegime(entryMarketStrength);
                String macroTrigger = classifyMacroTrigger(entryMarketRegime, relativeStrengthScore);

                report.addTrade(new BacktestTrade(
                        symbol,
                        entryDate,
                        exitDate,
                        plan.getEntry(), sim.exitPrice, plan.getStopLoss(), plan.getShares(),
                        sim.rMultiple, sim.pnl, sim.exitReason,
                        // setup metadata
                        setup.getSetupType().toString(),
                        setup.getSetupRating(),
                        setup.getBaseWindowLabel(),
                        setup.getQualityScore(),
                        // analytics
                        sim.mae, sim.mfe, sim.holdBars,
                        sim.hitT1, sim.hitT2, sim.hitT3,
                        benchmarkReturn,
                        alphaPct,
                        entryMarketStrength,
                        rewardToRiskT1,
                        positionRiskAmount,
                        positionNotional,
                        pivot,
                        pivotDistancePct,
                        sim.exitReason,
                        entryMarketRegime,
                        relativeStrengthScore,
                        macroTrigger
                ));

                // Walk every bar so backtest includes all system-signaled entries.
                i++;
            }
        }

        return report;
    }

    private Map<java.time.LocalDate, Integer> buildDateIndex(List<Candle> candles) {
        Map<java.time.LocalDate, Integer> map = new HashMap<>();
        for (int i = 0; i < candles.size(); i++) {
            map.put(candles.get(i).getDate(), i);
        }
        return map;
    }

    private double benchmarkReturnPct(
            List<Candle> benchmark,
            Map<java.time.LocalDate, Integer> benchmarkByDate,
            java.time.LocalDate entryDate,
            java.time.LocalDate exitDate
    ) {
        Integer entryIdx = benchmarkByDate.get(entryDate);
        Integer exitIdx = benchmarkByDate.get(exitDate);
        if (entryIdx == null || exitIdx == null || entryIdx < 0 || exitIdx < entryIdx || exitIdx >= benchmark.size()) {
            return 0.0;
        }
        double entry = benchmark.get(entryIdx).getClose();
        double exit = benchmark.get(exitIdx).getClose();
        if (entry <= 0.0) {
            return 0.0;
        }
        return ((exit / entry) - 1.0) * 100.0;
    }

    private double marketStrengthScore(
            List<Candle> benchmark,
            Map<java.time.LocalDate, Integer> benchmarkByDate,
            java.time.LocalDate entryDate
    ) {
        Integer idx = benchmarkByDate.get(entryDate);
        if (idx == null || idx < 0 || idx >= benchmark.size()) {
            return 0.0;
        }
        double close = benchmark.get(idx).getClose();
        if (close <= 0.0) {
            return 0.0;
        }

        int lookback20 = Math.max(0, idx - 20);
        double momentum20 = 0.0;
        double close20 = benchmark.get(lookback20).getClose();
        if (close20 > 0.0) {
            momentum20 = ((close / close20) - 1.0) * 100.0;
        }

        double ma50 = Indicators.movingAverage(benchmark, idx, 50);
        double trendScore = ma50 > 0.0 && close >= ma50 ? 2.0 : -2.0;
        return momentum20 + trendScore;
    }

    private String resolveBenchmarkSymbol(List<String> symbols) {
        if (!benchmarkSymbol.isBlank()) {
            return benchmarkSymbol;
        }
        int indiaVotes = 0;
        int usVotes = 0;
        for (String symbol : symbols) {
            String s = symbol == null ? "" : symbol.trim().toUpperCase();
            if (s.endsWith(".NS") || s.endsWith(".BO")) {
                indiaVotes++;
            } else {
                usVotes++;
            }
        }
        return indiaVotes > usVotes ? "^NSEI" : "SPY";
    }

    private double relativeStrengthScore(
            List<Candle> symbolCandles,
            int symbolIdx,
            List<Candle> benchmark,
            Map<java.time.LocalDate, Integer> benchmarkByDate,
            java.time.LocalDate entryDate
    ) {
        int stockLookback = Math.max(0, symbolIdx - 20);
        double stockClose = symbolCandles.get(symbolIdx).getClose();
        double stockOldClose = symbolCandles.get(stockLookback).getClose();
        if (stockClose <= 0.0 || stockOldClose <= 0.0) {
            return 0.0;
        }
        double stockMomentum = ((stockClose / stockOldClose) - 1.0) * 100.0;

        Integer benchIdx = benchmarkByDate.get(entryDate);
        if (benchIdx == null || benchIdx < 0 || benchIdx >= benchmark.size()) {
            return stockMomentum;
        }
        int benchLookback = Math.max(0, benchIdx - 20);
        double benchClose = benchmark.get(benchIdx).getClose();
        double benchOldClose = benchmark.get(benchLookback).getClose();
        if (benchClose <= 0.0 || benchOldClose <= 0.0) {
            return stockMomentum;
        }
        double benchMomentum = ((benchClose / benchOldClose) - 1.0) * 100.0;
        return stockMomentum - benchMomentum;
    }

    private String classifyEntryMarketRegime(double marketStrength) {
        if (marketStrength >= config.strongTrendMarketScoreThreshold) {
            return "TAILWIND";
        }
        if (marketStrength <= -2.0) {
            return "HEADWIND";
        }
        return "NEUTRAL";
    }

    private String classifyMacroTrigger(String marketRegime, double rsScore) {
        if ("TAILWIND".equals(marketRegime) && rsScore >= 2.0) {
            return "MACRO+MARKET_TAILWIND";
        }
        if ("TAILWIND".equals(marketRegime)) {
            return "MACRO_TAILWIND";
        }
        if (rsScore >= 2.0) {
            return "MARKET_RELATIVE_STRENGTH";
        }
        return "NO_CLEAR_TAILWIND";
    }

    private SimulatedTrade simulateTrade(
            List<Candle> candles,
            int signalIndex,
            TradePlan plan,
            double entryMarketStrength
    ) {
        double entry = plan.getEntry();
        double initialStop = resolveInitialStructureStop(candles, signalIndex, entry, plan.getStopLoss());
        double risk = entry - initialStop;
        if (risk <= 0.0) {
            initialStop = Math.min(plan.getStopLoss(), entry * 0.995);
            risk = Math.max(0.000001, entry - initialStop);
        }

        double t1 = plan.getTarget1();
        double t2 = plan.getTarget2();
        double t3 = plan.getTarget3();

        int last = candles.size() - 1;
        int exitIndex = last;
        double exitPrice = candles.get(last).getClose();
        String reason = "DATA_END_EXIT";

        boolean hitT1 = false;
        boolean hitT2 = false;
        boolean hitT3 = false;
        double mae = 0.0;
        double mfe = 0.0;

        double highestHigh = candles.get(signalIndex).getHigh();
        double trailingPct = trailingPercentForSignal(candles, signalIndex);
        boolean supportiveTrend = entryMarketStrength >= config.strongTrendMarketScoreThreshold;

        for (int i = signalIndex + 1; i <= last; i++) {
            Candle c = candles.get(i);

            if (entry > 0.0) {
                mae = Math.max(mae, Math.max(0.0, (entry - c.getLow()) / entry) * 100.0);
                mfe = Math.max(mfe, Math.max(0.0, (c.getHigh() - entry) / entry) * 100.0);
            }

            highestHigh = Math.max(highestHigh, c.getHigh());
            if (!hitT1 && c.getHigh() >= t1) {
                hitT1 = true;
            }
            if (!hitT2 && c.getHigh() >= t2) {
                hitT2 = true;
            }
            if (!hitT3 && c.getHigh() >= t3) {
                hitT3 = true;
            }

            double activeStop = initialStop;
            String activeReason = "STRUCTURE_BREAK_INITIAL";

            // Winners move to a dynamic trail from the highest-high structure.
            if (highestHigh >= entry + risk) {
                double trailStop = highestHigh * (1.0 - trailingPct);
                if (trailStop > activeStop) {
                    activeStop = trailStop;
                    activeReason = "STRUCTURE_BREAK_TRAIL";
                }
            }

            // In strong market trend context, a rising EMA10 acts as dynamic structure support.
            if (supportiveTrend) {
                double ema10 = Indicators.exponentialMovingAverage(candles, i, 10);
                double ema10Prev = Indicators.exponentialMovingAverage(candles, Math.max(0, i - 1), 10);
                boolean emaRising = ema10 > 0.0 && ema10 >= ema10Prev;
                if (emaRising) {
                    double emaStop = ema10 * (1.0 - config.emaTrailBufferPct);
                    if (emaStop > activeStop) {
                        activeStop = emaStop;
                        activeReason = "STRUCTURE_BREAK_EMA10";
                    }
                }
            }

            if (c.getLow() <= activeStop) {
                exitIndex = i;
                exitPrice = activeStop;
                reason = activeReason;
                break;
            }
        }

        int holdBars = exitIndex - signalIndex;
        double realizedPerShare = exitPrice - entry;
        double rMultiple = risk <= 0.0 ? 0.0 : (realizedPerShare / risk);
        double pnl = realizedPerShare * plan.getShares();

        return new SimulatedTrade(exitIndex, exitPrice, rMultiple, pnl, reason,
                hitT1, hitT2, hitT3, mae, mfe, holdBars);
    }

    private double resolveInitialStructureStop(List<Candle> candles, int signalIndex, double entry, double fallbackStop) {
        Candle signal = candles.get(signalIndex);
        double avgRangePct = Indicators.averageRangePct(candles, signalIndex, config.structureVolatilityLookbackBars);
        double bufferPct;
        if (avgRangePct < 1.8) {
            bufferPct = config.structureStopBufferLowVolPct;
        } else if (avgRangePct < 3.5) {
            bufferPct = config.structureStopBufferMedVolPct;
        } else {
            bufferPct = config.structureStopBufferHighVolPct;
        }

        double stop = signal.getLow() * (1.0 - bufferPct);
        double atr = Indicators.averageTrueRange(candles, signalIndex, config.atrTrailPeriodDaily);
        if (avgRangePct >= 3.5 && atr > 0.0) {
            // Volatile candles get a wider structure line to avoid noise exits.
            stop = Math.min(stop, entry - (2.0 * atr));
        }
        if (stop <= 0.0 || stop >= entry) {
            stop = fallbackStop;
        }
        if (stop <= 0.0 || stop >= entry) {
            stop = entry * 0.995;
        }
        return stop;
    }

    private double trailingPercentForSignal(List<Candle> candles, int signalIndex) {
        double avgRangePct = Indicators.averageRangePct(candles, signalIndex, config.structureVolatilityLookbackBars);
        if (avgRangePct < 1.8) {
            return config.structureTrailPctLowVol;
        }
        if (avgRangePct < 3.5) {
            return config.structureTrailPctMedVol;
        }
        return config.structureTrailPctHighVol;
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
