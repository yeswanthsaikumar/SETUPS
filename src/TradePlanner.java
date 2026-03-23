public class TradePlanner {
    public TradePlan buildPlan(double entryPrice, VcpSetup setup, AppConfig config) {
        double stop = computeStopPrice(entryPrice, setup, config);
        double riskPerShare = entryPrice - stop;
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
        return new TradePlan(entryPrice, stop, shares, t1, t2, t3);
    }

    private double computeStopPrice(double entryPrice, VcpSetup setup, AppConfig config) {
        double supportStop = setup.getSupportPrice() * (1.0 - config.stopBufferPct);
        if (setup.getSetupType() != VcpSetup.SetupType.MEAN_REVERSION) {
            return supportStop;
        }

        // Mean-reversion setups use a tighter stop anchored near support and bounded by 1R sanity.
        double tighterSupportStop = setup.getSupportPrice() * (1.0 - (config.stopBufferPct * 0.6));
        double capByEntry = entryPrice * (1.0 - 0.08);
        return Math.max(tighterSupportStop, capByEntry);
    }

    private double[] targetProfile(VcpSetup setup) {
        if (setup.getSetupType() == VcpSetup.SetupType.MEAN_REVERSION) {
            return new double[]{0.8, 1.6, 2.4};
        }
        return new double[]{1.0, 2.0, 3.0};
    }
}

