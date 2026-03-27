import java.time.LocalDate;

public class BacktestTrade {
    private final String symbol;
    private final LocalDate entryDate;
    private final LocalDate exitDate;
    private final double entryPrice;
    private final double exitPrice;
    private final double stopPrice;
    private final long shares;
    private final double rMultiple;
    private final double pnl;
    private final String exitReason;
    // ── Setup metadata ────────────────────────────────────────────────────────
    private final String setupType;
    private final String setupRating;
    private final String windowLabel;
    private final double qualityScore;
    // ── Trade analytics ───────────────────────────────────────────────────────
    private final double mae;      // max adverse excursion % from entry
    private final double mfe;      // max favorable excursion % from entry
    private final int holdBars;
    private final boolean hitT1;
    private final boolean hitT2;
    private final boolean hitT3;
    private final double benchmarkReturnPct;
    private final double alphaPct;
    private final double marketStrengthScore;
    private final double rewardToRiskT1;
    private final double positionRiskAmount;
    private final double positionNotional;
    private final double pivotPrice;
    private final double pivotDistancePct;
    private final String structureStopModel;
    private final String entryMarketRegime;
    private final double relativeStrengthScore;
    private final String macroTrigger;
    private final double accountBalanceBefore;
    private final double accountBalanceAfter;
    private final double riskPctUsed;
    private final String signalType;
    private final String entryTimeLabel;
    private final String entryInstruction;
    private final String entryTriggerCondition;
    private final String trailingStopPolicy;
    private final double stopReferencePrice;
    private final double riskPerShare;

    public BacktestTrade(
            String symbol, LocalDate entryDate, LocalDate exitDate,
            double entryPrice, double exitPrice, double stopPrice, long shares,
            double rMultiple, double pnl, String exitReason,
            String setupType, String setupRating, String windowLabel, double qualityScore,
            double mae, double mfe, int holdBars,
            boolean hitT1, boolean hitT2, boolean hitT3,
            double benchmarkReturnPct, double alphaPct, double marketStrengthScore,
            double rewardToRiskT1, double positionRiskAmount, double positionNotional,
            double pivotPrice, double pivotDistancePct,
            String structureStopModel, String entryMarketRegime,
            double relativeStrengthScore, String macroTrigger,
            double accountBalanceBefore, double accountBalanceAfter, double riskPctUsed,
            String signalType, String entryTimeLabel,
            String entryInstruction, String entryTriggerCondition,
            String trailingStopPolicy, double stopReferencePrice, double riskPerShare
    ) {
        this.symbol = symbol;
        this.entryDate = entryDate;
        this.exitDate = exitDate;
        this.entryPrice = entryPrice;
        this.exitPrice = exitPrice;
        this.stopPrice = stopPrice;
        this.shares = shares;
        this.rMultiple = rMultiple;
        this.pnl = pnl;
        this.exitReason = exitReason;
        this.setupType = setupType;
        this.setupRating = setupRating;
        this.windowLabel = windowLabel;
        this.qualityScore = qualityScore;
        this.mae = mae;
        this.mfe = mfe;
        this.holdBars = holdBars;
        this.hitT1 = hitT1;
        this.hitT2 = hitT2;
        this.hitT3 = hitT3;
        this.benchmarkReturnPct = benchmarkReturnPct;
        this.alphaPct = alphaPct;
        this.marketStrengthScore = marketStrengthScore;
        this.rewardToRiskT1 = rewardToRiskT1;
        this.positionRiskAmount = positionRiskAmount;
        this.positionNotional = positionNotional;
        this.pivotPrice = pivotPrice;
        this.pivotDistancePct = pivotDistancePct;
        this.structureStopModel = structureStopModel;
        this.entryMarketRegime = entryMarketRegime;
        this.relativeStrengthScore = relativeStrengthScore;
        this.macroTrigger = macroTrigger;
        this.accountBalanceBefore = accountBalanceBefore;
        this.accountBalanceAfter = accountBalanceAfter;
        this.riskPctUsed = riskPctUsed;
        this.signalType = signalType;
        this.entryTimeLabel = entryTimeLabel;
        this.entryInstruction = entryInstruction;
        this.entryTriggerCondition = entryTriggerCondition;
        this.trailingStopPolicy = trailingStopPolicy;
        this.stopReferencePrice = stopReferencePrice;
        this.riskPerShare = riskPerShare;
    }

    public String getSymbol()      { return symbol; }
    public LocalDate getEntryDate(){ return entryDate; }
    public LocalDate getExitDate() { return exitDate; }
    public double getEntryPrice()  { return entryPrice; }
    public double getExitPrice()   { return exitPrice; }
    public double getStopPrice()   { return stopPrice; }
    public long getShares()        { return shares; }
    public double getRMultiple()   { return rMultiple; }
    public double getPnl()         { return pnl; }
    public String getExitReason()  { return exitReason; }
    public String getSetupType()   { return setupType; }
    public String getSetupRating() { return setupRating; }
    public String getWindowLabel() { return windowLabel; }
    public double getQualityScore(){ return qualityScore; }
    public double getMae()         { return mae; }
    public double getMfe()         { return mfe; }
    public int getHoldBars()       { return holdBars; }
    public boolean isHitT1()       { return hitT1; }
    public boolean isHitT2()       { return hitT2; }
    public boolean isHitT3()       { return hitT3; }
    public double getBenchmarkReturnPct() { return benchmarkReturnPct; }
    public double getAlphaPct()    { return alphaPct; }
    public double getMarketStrengthScore() { return marketStrengthScore; }
    public double getRewardToRiskT1() { return rewardToRiskT1; }
    public double getPositionRiskAmount() { return positionRiskAmount; }
    public double getPositionNotional() { return positionNotional; }
    public double getPivotPrice() { return pivotPrice; }
    public double getPivotDistancePct() { return pivotDistancePct; }
    public String getStructureStopModel() { return structureStopModel; }
    public String getEntryMarketRegime() { return entryMarketRegime; }
    public double getRelativeStrengthScore() { return relativeStrengthScore; }
    public String getMacroTrigger() { return macroTrigger; }
    public double getAccountBalanceBefore() { return accountBalanceBefore; }
    public double getAccountBalanceAfter() { return accountBalanceAfter; }
    public double getRiskPctUsed() { return riskPctUsed; }
    public String getSignalType() { return signalType; }
    public String getEntryTimeLabel() { return entryTimeLabel; }
    public String getEntryInstruction() { return entryInstruction; }
    public String getEntryTriggerCondition() { return entryTriggerCondition; }
    public String getTrailingStopPolicy() { return trailingStopPolicy; }
    public double getStopReferencePrice() { return stopReferencePrice; }
    public double getRiskPerShare() { return riskPerShare; }

    public double getTradeReturnPct() {
        if (entryPrice <= 0.0) {
            return 0.0;
        }
        return ((exitPrice / entryPrice) - 1.0) * 100.0;
    }

    public String toConsoleLine() {
        return String.format(
                "%s | %s | %s | %s | Entry %s %.2f (%s) | Exit %s %.2f | R %.2f | Alpha %.2f%% | PnL %.2f | Hold %d | %s",
                symbol, setupType, setupRating, signalType,
                entryDate, entryPrice,
                entryTimeLabel,
                exitDate, exitPrice,
                rMultiple, alphaPct, pnl, holdBars, exitReason
        );
    }
}
