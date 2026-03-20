public class ScanResult {
    private final String symbol;
    private final VcpSetup setup;
    private final Candle signalCandle;
    private final TradePlan tradePlan;
    private final String signalType;

    public ScanResult(String symbol, VcpSetup setup, Candle signalCandle, TradePlan tradePlan) {
        this(symbol, setup, signalCandle, tradePlan, "BREAKOUT");
    }

    public ScanResult(String symbol, VcpSetup setup, Candle signalCandle, TradePlan tradePlan, String signalType) {
        this.symbol = symbol;
        this.setup = setup;
        this.signalCandle = signalCandle;
        this.tradePlan = tradePlan;
        this.signalType = signalType == null || signalType.isBlank() ? "BREAKOUT" : signalType;
    }

    public String getSymbol() {
        return symbol;
    }

    public VcpSetup getSetup() {
        return setup;
    }

    public Candle getSignalCandle() {
        return signalCandle;
    }

    public TradePlan getTradePlan() {
        return tradePlan;
    }

    public double getQualityScore() {
        return setup.getQualityScore();
    }

    public String getSignalType() {
        return signalType;
    }

    public String toConsoleLine() {
        return String.format(
                "%s | Type %s | Setup %s | Window %s(%d) | Height %.1f%% | Depth %.1f%% | Len %d | Ctr %d/%d | Rating %s | Close %.2f | Pivot %.2f | Entry %.2f | Score %.1f | Range %.1f%% | Vol %.1f%% | RExp %.2fx | Shares %d | SL %.2f | T1 %.2f T2 %.2f T3 %.2f",
                symbol,
                signalType,
                setup.getSetupType(),
                setup.getBaseWindowLabel(),
                setup.getBaseWindowBars(),
                setup.getBaseRangeHeightPct(),
                setup.getContractionDepthPct(),
                setup.getBaseWindowBars(),
                setup.getRangeContractionCount(),
                setup.getContractionPairs(),
                setup.getSetupRating(),
                signalCandle.getClose(),
                setup.getPivotPrice(),
                tradePlan.getEntry(),
                setup.getQualityScore(),
                setup.getRangeContraction() * 100.0,
                setup.getVolumeContraction() * 100.0,
                setup.getRangeExpansion(),
                tradePlan.getShares(),
                tradePlan.getStopLoss(),
                tradePlan.getTarget1(),
                tradePlan.getTarget2(),
                tradePlan.getTarget3()
        );
    }
}
