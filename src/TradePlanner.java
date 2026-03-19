public class TradePlanner {
    public TradePlan buildPlan(double entryPrice, VcpSetup setup, AppConfig config) {
        double stop = setup.getSupportPrice() * (1.0 - config.stopBufferPct);
        double riskPerShare = entryPrice - stop;
        if (riskPerShare <= 0.0) {
            return null;
        }

        double riskCapital = config.accountSize * config.riskPerTradePct;
        long shares = (long) Math.floor(riskCapital / riskPerShare);
        if (shares < 1) {
            return null;
        }

        double t1 = entryPrice + riskPerShare;
        double t2 = entryPrice + (2.0 * riskPerShare);
        double t3 = entryPrice + (3.0 * riskPerShare);
        return new TradePlan(entryPrice, stop, shares, t1, t2, t3);
    }
}

