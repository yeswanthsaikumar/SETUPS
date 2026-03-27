public class TradePlan {
    private final double entry;
    private final double stopLoss;
    private final long shares;
    private final double target1;
    private final double target2;
    private final double target3;
    private final String signalType;
    private final String entryTimeLabel;
    private final String entryInstruction;
    private final String entryTriggerCondition;
    private final String stopModel;
    private final String trailingStopPolicy;
    private final double stopReferencePrice;
    private final double riskPerShare;

    public TradePlan(double entry, double stopLoss, long shares, double target1, double target2, double target3) {
        this(entry, stopLoss, shares, target1, target2, target3,
                "BREAKOUT", "SIGNAL_BAR_CLOSE", "", "",
                "STRUCTURE_SUPPORT", "VOL_ADAPTIVE_TRAIL", 0.0,
                Math.max(0.0, entry - stopLoss));
    }

    public TradePlan(
            double entry,
            double stopLoss,
            long shares,
            double target1,
            double target2,
            double target3,
            String signalType,
            String entryTimeLabel,
            String entryInstruction,
            String entryTriggerCondition,
            String stopModel,
            String trailingStopPolicy,
            double stopReferencePrice,
            double riskPerShare
    ) {
        this.entry = entry;
        this.stopLoss = stopLoss;
        this.shares = shares;
        this.target1 = target1;
        this.target2 = target2;
        this.target3 = target3;
        this.signalType = signalType == null || signalType.isBlank() ? "BREAKOUT" : signalType;
        this.entryTimeLabel = entryTimeLabel == null || entryTimeLabel.isBlank() ? "SIGNAL_BAR_CLOSE" : entryTimeLabel;
        this.entryInstruction = entryInstruction == null ? "" : entryInstruction;
        this.entryTriggerCondition = entryTriggerCondition == null ? "" : entryTriggerCondition;
        this.stopModel = stopModel == null || stopModel.isBlank() ? "STRUCTURE_SUPPORT" : stopModel;
        this.trailingStopPolicy = trailingStopPolicy == null || trailingStopPolicy.isBlank()
                ? "VOL_ADAPTIVE_TRAIL"
                : trailingStopPolicy;
        this.stopReferencePrice = stopReferencePrice;
        this.riskPerShare = riskPerShare;
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

    public String getSignalType() {
        return signalType;
    }

    public String getEntryTimeLabel() {
        return entryTimeLabel;
    }

    public String getEntryInstruction() {
        return entryInstruction;
    }

    public String getEntryTriggerCondition() {
        return entryTriggerCondition;
    }

    public String getStopModel() {
        return stopModel;
    }

    public String getTrailingStopPolicy() {
        return trailingStopPolicy;
    }

    public double getStopReferencePrice() {
        return stopReferencePrice;
    }

    public double getRiskPerShare() {
        return riskPerShare;
    }
}

