public class VcpSetup {
    public enum SetupType {
        VCP,
        RANGE_EXPANSION
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
    }

    public SetupType getSetupType() {
        return setupType;
    }

    public double getPivotPrice() {
        return pivotPrice;
    }

    public double getSupportPrice() {
        return supportPrice;
    }

    public double getQualityScore() {
        return qualityScore;
    }

    public double getRangeContraction() {
        return rangeContraction;
    }

    public double getVolumeContraction() {
        return volumeContraction;
    }

    public double getRangeExpansion() {
        return rangeExpansion;
    }

    public int getBaseWindowBars() {
        return baseWindowBars;
    }

    public String getBaseWindowLabel() {
        return baseWindowLabel;
    }

    public double getBaseRangeHeightPct() {
        return baseRangeHeightPct;
    }

    public double getContractionDepthPct() {
        return contractionDepthPct;
    }

    public String getSetupRating() {
        return setupRating;
    }

    public int getRangeContractionCount() {
        return rangeContractionCount;
    }

    public int getVolumeContractionCount() {
        return volumeContractionCount;
    }

    public int getContractionPairs() {
        return contractionPairs;
    }
}

