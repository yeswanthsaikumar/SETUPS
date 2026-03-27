import java.util.List;

public class TradePlanner {
    public TradePlan buildPlan(double entryPrice, VcpSetup setup, AppConfig config) {
        return buildPlan(entryPrice, setup, null, -1, null, false, "BREAKOUT", config);
    }

    public TradePlan buildPlan(double entryPrice, VcpSetup setup, Candle signalCandle, boolean triggeredBreakout, AppConfig config) {
        String signalType = triggeredBreakout ? "BREAKOUT" : "WATCHLIST";
        return buildPlan(entryPrice, setup, null, -1, signalCandle, triggeredBreakout, signalType, config);
    }

    public TradePlan buildPlan(
            double entryPrice,
            VcpSetup setup,
            List<Candle> candles,
            int signalIndex,
            Candle signalCandle,
            boolean triggeredBreakout,
            String signalType,
            AppConfig config
    ) {
        StopDecision stopDecision = computeStopPrice(entryPrice, setup, candles, signalIndex, signalCandle, triggeredBreakout, signalType, config);
        double riskPerShare = entryPrice - stopDecision.stopPrice;
        if (riskPerShare <= 0.0) {
            return null;
        }

        double riskCapital = config.accountSize * config.riskPerTradePct;
        long shares = (long) Math.floor(riskCapital / riskPerShare);
        if (shares < 1) {
            return null;
        }

        double[] targetMultipliers = targetProfile(setup);
        double t1 = entryPrice + (targetMultipliers[0] * riskPerShare);
        double t2 = entryPrice + (targetMultipliers[1] * riskPerShare);
        double t3 = entryPrice + (targetMultipliers[2] * riskPerShare);
        return new TradePlan(
                entryPrice,
                stopDecision.stopPrice,
                shares,
                t1,
                t2,
                t3,
                normalizeSignalType(signalType),
                entryTimeLabel(signalType),
                entryInstruction(signalType, entryPrice, setup),
                entryTriggerCondition(signalType, entryPrice, setup),
                stopDecision.stopModel,
                stopDecision.trailingStopPolicy,
                stopDecision.stopReferencePrice,
                riskPerShare
        );
    }

    private StopDecision computeStopPrice(
            double entryPrice,
            VcpSetup setup,
            List<Candle> candles,
            int signalIndex,
            Candle signalCandle,
            boolean triggeredBreakout,
            String signalType,
            AppConfig config
    ) {
        if (triggeredBreakout && signalCandle != null && signalCandle.getLow() > 0.0) {
            double avgRangePct = resolveAverageRangePct(candles, signalIndex, signalCandle, config);
            double bufferPct = structureBufferPct(avgRangePct, config);
            double breakoutStructureStop = signalCandle.getLow() * (1.0 - bufferPct);
            String stopModel = structureModelForVolatility(avgRangePct);

            double atr = candles != null && signalIndex >= 0 && signalIndex < candles.size()
                    ? Indicators.averageTrueRange(candles, signalIndex, config.atrTrailPeriodDaily)
                    : 0.0;
            if (avgRangePct >= 3.5 && atr > 0.0) {
                breakoutStructureStop = Math.min(breakoutStructureStop, entryPrice - (2.0 * atr));
                stopModel = "BREAKOUT_CANDLE_LOW_ATR_WIDE";
            }

            if (breakoutStructureStop > 0.0 && breakoutStructureStop < entryPrice) {
                return new StopDecision(
                        breakoutStructureStop,
                        stopModel,
                        signalCandle.getLow(),
                        trailingStopPolicy(avgRangePct, true)
                );
            }
        }

        double supportStop = setup.getSupportPrice() * (1.0 - config.stopBufferPct);
        if (setup.getSetupType() != VcpSetup.SetupType.MEAN_REVERSION) {
            if ("NEAR_BREAKOUT".equalsIgnoreCase(signalType)) {
                return new StopDecision(
                        supportStop,
                        "PIVOT_HOLD_STRUCTURE",
                        setup.getSupportPrice(),
                        trailingStopPolicy(resolveAverageRangePct(candles, signalIndex, signalCandle, config), true)
                );
            }
            return new StopDecision(
                    supportStop,
                    "BASE_STRUCTURE_SUPPORT",
                    setup.getSupportPrice(),
                    trailingStopPolicy(resolveAverageRangePct(candles, signalIndex, signalCandle, config), false)
            );
        }

        // Mean-reversion setups use a tighter stop anchored near support and bounded by 1R sanity.
        double tighterSupportStop = setup.getSupportPrice() * (1.0 - (config.stopBufferPct * 0.6));
        double capByEntry = entryPrice * (1.0 - 0.08);
        return new StopDecision(
                Math.max(tighterSupportStop, capByEntry),
                "MEAN_REVERSION_SUPPORT",
                setup.getSupportPrice(),
                "TIGHT_SUPPORT_TRAIL"
        );
    }

    private double[] targetProfile(VcpSetup setup) {
        if (setup.getSetupType() == VcpSetup.SetupType.MEAN_REVERSION) {
            return new double[]{0.8, 1.6, 2.4};
        }
        return new double[]{1.0, 2.0, 3.0};
    }

    private double resolveAverageRangePct(List<Candle> candles, int signalIndex, Candle signalCandle, AppConfig config) {
        if (candles != null && signalIndex >= 0 && signalIndex < candles.size()) {
            return Indicators.averageRangePct(candles, signalIndex, config.structureVolatilityLookbackBars);
        }
        if (signalCandle == null || signalCandle.getClose() <= 0.0) {
            return 2.0;
        }
        return ((signalCandle.getHigh() - signalCandle.getLow()) / signalCandle.getClose()) * 100.0;
    }

    private double structureBufferPct(double avgRangePct, AppConfig config) {
        if (avgRangePct < 1.8) {
            return config.structureStopBufferLowVolPct;
        }
        if (avgRangePct < 3.5) {
            return config.structureStopBufferMedVolPct;
        }
        return config.structureStopBufferHighVolPct;
    }

    private String structureModelForVolatility(double avgRangePct) {
        if (avgRangePct < 1.8) {
            return "BREAKOUT_CANDLE_LOW_TIGHT";
        }
        if (avgRangePct < 3.5) {
            return "BREAKOUT_CANDLE_LOW_MEDIUM";
        }
        return "BREAKOUT_CANDLE_LOW_WIDE";
    }

    private String trailingStopPolicy(double avgRangePct, boolean breakoutStyle) {
        if (!breakoutStyle) {
            return "SUPPORT_HOLD_THEN_EMA10_IF_TRENDING";
        }
        if (avgRangePct < 1.8) {
            return "VOL_ADAPTIVE_5PCT_TRAIL_PLUS_EMA10";
        }
        if (avgRangePct < 3.5) {
            return "VOL_ADAPTIVE_6PCT_TRAIL_PLUS_EMA10";
        }
        return "VOL_ADAPTIVE_8PCT_TRAIL_PLUS_EMA10";
    }

    private String normalizeSignalType(String signalType) {
        if (signalType == null || signalType.isBlank()) {
            return "BREAKOUT";
        }
        return signalType.trim().toUpperCase();
    }

    private String entryTimeLabel(String signalType) {
        String normalized = normalizeSignalType(signalType);
        if ("WATCHLIST".equals(normalized)) {
            return "WAIT_FOR_BREAKOUT_CLOSE";
        }
        return "SIGNAL_BAR_CLOSE";
    }

    private String entryInstruction(String signalType, double entryPrice, VcpSetup setup) {
        String normalized = normalizeSignalType(signalType);
        if ("WATCHLIST".equals(normalized)) {
            return String.format(
                    "Set alert near pivot %.2f and buy only after a confirmed breakout close above %.2f.",
                    setup.getPivotPrice(), entryPrice
            );
        }
        if ("NEAR_BREAKOUT".equals(normalized)) {
            return String.format(
                    "Use continuation entry around %.2f only while price keeps holding the pivot/support structure.",
                    entryPrice
            );
        }
        return String.format(
                "Enter around %.2f on the breakout confirmation close; avoid chasing if price gets materially extended above pivot.",
                entryPrice
        );
    }

    private String entryTriggerCondition(String signalType, double entryPrice, VcpSetup setup) {
        String normalized = normalizeSignalType(signalType);
        if ("WATCHLIST".equals(normalized)) {
            return String.format(
                    "Breakout close above %.2f with healthy volume expansion through pivot %.2f.",
                    entryPrice, setup.getPivotPrice()
            );
        }
        if ("NEAR_BREAKOUT".equals(normalized)) {
            return String.format(
                    "Continuation while price stays above pivot %.2f and confirms support near %.2f.",
                    setup.getPivotPrice(), setup.getSupportPrice()
            );
        }
        return String.format(
                "Breakout close above %.2f with strong candle body, volume confirmation, and pivot clearance.",
                entryPrice
        );
    }

    private static class StopDecision {
        final double stopPrice;
        final String stopModel;
        final double stopReferencePrice;
        final String trailingStopPolicy;

        StopDecision(double stopPrice, String stopModel, double stopReferencePrice, String trailingStopPolicy) {
            this.stopPrice = stopPrice;
            this.stopModel = stopModel;
            this.stopReferencePrice = stopReferencePrice;
            this.trailingStopPolicy = trailingStopPolicy;
        }
    }
}

