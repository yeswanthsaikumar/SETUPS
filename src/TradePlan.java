public class TradePlan {
    private final double entry;
    private final double stopLoss;
    private final long shares;
    private final double target1;
    private final double target2;
    private final double target3;

    public TradePlan(double entry, double stopLoss, long shares, double target1, double target2, double target3) {
        this.entry = entry;
        this.stopLoss = stopLoss;
        this.shares = shares;
        this.target1 = target1;
        this.target2 = target2;
        this.target3 = target3;
    }

    public double getEntry() {
        return entry;
    }

    public double getStopLoss() {
        return stopLoss;
    }

    public long getShares() {
        return shares;
    }

    public double getTarget1() {
        return target1;
    }

    public double getTarget2() {
        return target2;
    }

    public double getTarget3() {
        return target3;
    }
}

