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

    // ── NEW: Market context metadata ──────────────────────────────────────────
    private double rsPercentile;          // RS rank within universe (0-100)
    private String sector;                // Stock's sector
    private String industry;              // Stock's industry group
    private String basicIndustry;         // Finest NSE classification (~200 groups)
    private double sectorBonus;           // Score adjustment from sector strength
    private String marketRegime;          // TAILWIND / NEUTRAL / HEADWIND

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
        this.rsPercentile = 0.0;
        this.sector = null;
        this.industry = null;
        this.basicIndustry = null;
        this.sectorBonus = 0.0;
        this.marketRegime = "NEUTRAL";
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
        return setup.getQualityScore() + alignmentBonus + sectorBonus;
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

    // ── NEW: Context getters/setters ─────────────────────────────────────────
    public double getRsPercentile() {
        return rsPercentile;
    }

    public void setRsPercentile(double rs) {
        this.rsPercentile = rs;
    }

    public String getSector() {
        return sector;
    }

    public String getIndustry() {
        return industry;
    }

    public String getBasicIndustry() {
        return basicIndustry;
    }

    public void setSectorInfo(String sector, String industry) {
        this.sector = sector;
        this.industry = industry;
    }

    public void setSectorInfo(String sector, String industry, String basicIndustry) {
        this.sector = sector;
        this.industry = industry;
        this.basicIndustry = basicIndustry;
    }

    public double getSectorBonus() {
        return sectorBonus;
    }

    public void setSectorBonus(double bonus) {
        this.sectorBonus = bonus;
    }

    public String getMarketRegime() {
        return marketRegime;
    }

    public void setMarketRegime(String regime) {
        this.marketRegime = regime;
    }

    public String toConsoleLine() {
        String alignmentTag = alignmentBonus > 0.0 ? String.format(" [MTF: %s (+%.1f)]", alignmentReason, alignmentBonus) : "";
        String ipoTag = ipoFlag ? String.format(" [IPO %dd]", daysSinceListing) : "";
        String rsTag = rsPercentile > 0 ? String.format(" [RS:%.0f]", rsPercentile) : "";
        String sectorTag = sector != null ? String.format(" [%s]", sector) : "";
        String regimeTag = !"NEUTRAL".equals(marketRegime) ? String.format(" [%s]", marketRegime) : "";
        String dryUpTag = setup.getVolumeDryUpRatio() <= 0.70 ? " [VOL_DRY]" : "";
        String gapTag = setup.isGapBreakout() ? " [GAP]" : "";
        String emaFanTag = setup.isEmaFanAligned() ? " [EMA_FAN]" : "";
        return String.format(
                "%s | Type %s | Setup %s | Window %s(%d) | Height %.1f%% | Depth %.1f%% | Len %d | Ctr %d/%d | Rating %s | Close %.2f | Pivot %.2f | Entry %.2f | Score %.1f | Range %.1f%% | Vol %.1f%% | RExp %.2fx | Shares %d | SL %.2f | T1 %.2f T2 %.2f T3 %.2f%s",
                symbol, signalType, setup.getSetupType(),
                setup.getBaseWindowLabel(), setup.getBaseWindowBars(),
                setup.getBaseRangeHeightPct(), setup.getContractionDepthPct(),
                setup.getBaseWindowBars(), setup.getRangeContractionCount(), setup.getContractionPairs(),
                setup.getSetupRating(), signalCandle.getClose(), setup.getPivotPrice(),
                tradePlan.getEntry(), getQualityScore(),
                setup.getRangeContraction() * 100.0, setup.getVolumeContraction() * 100.0,
                setup.getRangeExpansion(), tradePlan.getShares(), tradePlan.getStopLoss(),
                tradePlan.getTarget1(), tradePlan.getTarget2(), tradePlan.getTarget3(),
                alignmentTag
        ) + rsTag + sectorTag + regimeTag + dryUpTag + gapTag + emaFanTag + ipoTag;
    }
}
