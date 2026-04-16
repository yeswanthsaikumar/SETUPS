public class VcpSetup {
    public enum SetupType {
        VCP,
        RANGE_EXPANSION,
        MEAN_REVERSION
    }

    private final SetupType setupType;
    private final double pivotPrice;
    private final double supportPrice;
    private final double qualityScore;
    private final double rangeContraction;
    private final double volumeContraction;
    private final double rangeExpansion;
    private final int baseWindowBars;
    private final String baseWindowLabel;
    private final double baseRangeHeightPct;
    private final double contractionDepthPct;
    private final String setupRating;
    private final int rangeContractionCount;
    private final int volumeContractionCount;
    private final int contractionPairs;

    // ── NEW enrichment fields ─────────────────────────────────────────────────
    private double volumeDryUpRatio;      // Pre-breakout volume quietness (lower = better)
    private double accumDistRatio;        // Accumulation/distribution ratio in base
    private int tightCloseCount;          // Number of tight-close bars before breakout
    private boolean emaFanAligned;        // 10 EMA > 21 EMA > 50 EMA
    private double volumeDryUpBonus;      // Score bonus from volume dry-up
    private double accumDistBonus;        // Score bonus from accum/dist
    private double tightCloseBonus;       // Score bonus from tight closes
    private boolean gapBreakout;          // Whether breakout was a gap-up

    public VcpSetup(
            SetupType setupType,
            double pivotPrice,
            double supportPrice,
            double qualityScore,
            double rangeContraction,
            double volumeContraction,
            double rangeExpansion,
            int baseWindowBars,
            String baseWindowLabel,
            double baseRangeHeightPct,
            double contractionDepthPct,
            String setupRating,
            int rangeContractionCount,
            int volumeContractionCount,
            int contractionPairs
    ) {
        this.setupType = setupType;
        this.pivotPrice = pivotPrice;
        this.supportPrice = supportPrice;
        this.qualityScore = qualityScore;
        this.rangeContraction = rangeContraction;
        this.volumeContraction = volumeContraction;
        this.rangeExpansion = rangeExpansion;
        this.baseWindowBars = baseWindowBars;
        this.baseWindowLabel = baseWindowLabel;
        this.baseRangeHeightPct = baseRangeHeightPct;
        this.contractionDepthPct = contractionDepthPct;
        this.setupRating = setupRating;
        this.rangeContractionCount = rangeContractionCount;
        this.volumeContractionCount = volumeContractionCount;
        this.contractionPairs = contractionPairs;
        // Defaults for new fields
        this.volumeDryUpRatio = 1.0;
        this.accumDistRatio = 1.0;
        this.tightCloseCount = 0;
        this.emaFanAligned = false;
        this.volumeDryUpBonus = 0.0;
        this.accumDistBonus = 0.0;
        this.tightCloseBonus = 0.0;
        this.gapBreakout = false;
    }

    // ...existing getters...
    public SetupType getSetupType() { return setupType; }
    public double getPivotPrice() { return pivotPrice; }
    public double getSupportPrice() { return supportPrice; }
    public double getQualityScore() { return qualityScore + volumeDryUpBonus + accumDistBonus + tightCloseBonus; }
    public double getBaseQualityScore() { return qualityScore; }
    public double getRangeContraction() { return rangeContraction; }
    public double getVolumeContraction() { return volumeContraction; }
    public double getRangeExpansion() { return rangeExpansion; }
    public int getBaseWindowBars() { return baseWindowBars; }
    public String getBaseWindowLabel() { return baseWindowLabel; }
    public double getBaseRangeHeightPct() { return baseRangeHeightPct; }
    public double getContractionDepthPct() { return contractionDepthPct; }
    public String getSetupRating() { return setupRating; }
    public int getRangeContractionCount() { return rangeContractionCount; }
    public int getVolumeContractionCount() { return volumeContractionCount; }
    public int getContractionPairs() { return contractionPairs; }

    // ── NEW getters/setters ──────────────────────────────────────────────────
    public double getVolumeDryUpRatio() { return volumeDryUpRatio; }
    public double getAccumDistRatio() { return accumDistRatio; }
    public int getTightCloseCount() { return tightCloseCount; }
    public boolean isEmaFanAligned() { return emaFanAligned; }
    public boolean isGapBreakout() { return gapBreakout; }
    public double getVolumeDryUpBonus() { return volumeDryUpBonus; }
    public double getAccumDistBonus() { return accumDistBonus; }
    public double getTightCloseBonus() { return tightCloseBonus; }

    public void enrichWithBaseQuality(double volumeDryUpRatio, double accumDistRatio,
                                       int tightCloseCount, boolean emaFanAligned,
                                       double volumeDryUpBonus, double accumDistBonus,
                                       double tightCloseBonus) {
        this.volumeDryUpRatio = volumeDryUpRatio;
        this.accumDistRatio = accumDistRatio;
        this.tightCloseCount = tightCloseCount;
        this.emaFanAligned = emaFanAligned;
        this.volumeDryUpBonus = volumeDryUpBonus;
        this.accumDistBonus = accumDistBonus;
        this.tightCloseBonus = tightCloseBonus;
    }

    public void setGapBreakout(boolean gap) {
        this.gapBreakout = gap;
    }
}
