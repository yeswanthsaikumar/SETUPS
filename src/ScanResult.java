public class ScanResult {
    private final String symbol;
    private final VcpSetup setup;
    private final Candle signalCandle;
    private final TradePlan tradePlan;
    private final String signalType;
    private double alignmentBonus;              // Multi-timeframe alignment score boost
    private String alignmentReason;             // Why alignment bonus was applied
    private boolean weeklyAligned;              // Whether weekly structure supports daily signal
    private BreakoutQualityAnalyzer.BreakoutQualityContext breakoutQuality;  // Enhanced quality metrics
    private boolean ipoFlag;                    // True if stock is recently listed (limited history)
    private int daysSinceListing;               // Number of available trading bars (proxy for listing age)

    public ScanResult(String symbol, VcpSetup setup, Candle signalCandle, TradePlan tradePlan) {
        this(symbol, setup, signalCandle, tradePlan, "BREAKOUT");
    }

    public ScanResult(String symbol, VcpSetup setup, Candle signalCandle, TradePlan tradePlan, String signalType) {
        this.symbol = symbol;
        this.setup = setup;
        this.signalCandle = signalCandle;
        this.tradePlan = tradePlan;
        this.signalType = signalType == null || signalType.isBlank() ? "BREAKOUT" : signalType;
        this.alignmentBonus = 0.0;
        this.alignmentReason = "NO_ALIGNMENT";
        this.weeklyAligned = false;
        this.breakoutQuality = null;
        this.ipoFlag = false;
        this.daysSinceListing = 0;
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
        return setup.getQualityScore() + alignmentBonus;
    }

    public String getSignalType() {
        return signalType;
    }

    // ── Multi-timeframe alignment ────────────────────────────────────────────────
    public double getAlignmentBonus() {
        return alignmentBonus;
    }

    public void setAlignmentBonus(double bonus, String reason, boolean aligned) {
        this.alignmentBonus = Math.max(0.0, bonus);
        this.alignmentReason = reason == null ? "NO_ALIGNMENT" : reason;
        this.weeklyAligned = aligned;
    }

    public String getAlignmentReason() {
        return alignmentReason;
    }

    public boolean isWeeklyAligned() {
        return weeklyAligned;
    }

    public BreakoutQualityAnalyzer.BreakoutQualityContext getBreakoutQuality() {
        return breakoutQuality;
    }

    public void setBreakoutQuality(BreakoutQualityAnalyzer.BreakoutQualityContext quality) {
        this.breakoutQuality = quality;
    }

    // ── IPO flag ────────────────────────────────────────────────────────────────
    public boolean isIpoFlag() {
        return ipoFlag;
    }

    public int getDaysSinceListing() {
        return daysSinceListing;
    }

    public void setIpoFlag(boolean flag, int days) {
        this.ipoFlag = flag;
        this.daysSinceListing = days;
    }

    public String toConsoleLine() {
        String alignmentTag = alignmentBonus > 0.0 ? String.format(" [MTF: %s (+%.1f)]", alignmentReason, alignmentBonus) : "";
        String ipoTag = ipoFlag ? String.format(" [IPO %dd]", daysSinceListing) : "";
        return String.format(
                "%s | Type %s | Setup %s | Window %s(%d) | Height %.1f%% | Depth %.1f%% | Len %d | Ctr %d/%d | Rating %s | Close %.2f | Pivot %.2f | Entry %.2f | Score %.1f | Range %.1f%% | Vol %.1f%% | RExp %.2fx | Shares %d | SL %.2f | T1 %.2f T2 %.2f T3 %.2f%s",
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
                getQualityScore(),
                setup.getRangeContraction() * 100.0,
                setup.getVolumeContraction() * 100.0,
                setup.getRangeExpansion(),
                tradePlan.getShares(),
                tradePlan.getStopLoss(),
                tradePlan.getTarget1(),
                tradePlan.getTarget2(),
                tradePlan.getTarget3(),
                alignmentTag
        ) + ipoTag;
    }
}
