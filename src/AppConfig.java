public class AppConfig {
    // ── Data ──────────────────────────────────────────────────────────────────
    public final int lookbackDays;
    public final String timeframe;

    // ── VCP base detection ───────────────────────────────────────────────────
    // Multiple window lengths tried — best score wins (genuine bases of any length)
    public final int[] consolidationWindows;
    public final int waveCount;

    // How many waves are allowed to fail the contraction test and still pass.
    // 0 = strict (old behaviour), 1 = one imperfect wave allowed (recommended)
    public final int waveContractionMissTolerance;

    // Minimum overall (first-to-last wave) contraction ratios
    public final double minRangeContraction;
    public final double minVolumeContraction;
    public final double minQualityScore;
    public final double minRangeExpansionMultiplier;
    public final double minExpansionVolumeMultiplier;
    public final double minExpansionClosePosition;
    public final int wickBiasLookbackBars;
    public final double bodyDirectionalWeight;
    public final double lowerWickPositiveWeight;
    public final double upperWickNegativeWeight;
    public final double maxWickBodyScoreAdjustment;
    public final double minBaseHeightPct;
    public final double maxBaseHeightPct;
    public final double shortWindowHeightCapPct;
    public final double longWindowHeightCapPct;
    public final double shortWindowContractionPairRatio;
    public final double longWindowContractionPairRatio;

    // ── Trend / quality filters ───────────────────────────────────────────────
    // Stock must be within this % of its 52-week high (avoids dead-cat bounces)
    public final double maxDistanceFrom52WkHighPct;

    // Stock close must be above its N-day MA when the base ends
    public final boolean requireAboveMA;
    public final int maPeriod;
    public final int annualHighLookbackBars;

    // Minimum stock price to scan (filter penny stocks)
    public final double minPrice;

    // ── Breakout confirmation ────────────────────────────────────────────────
    // Close must be above pivot by at least this fraction
    public final double breakoutBufferPct;

    // Breakout bar volume must be >= this multiple of the 20-day average
    // 1.25x works well for large-caps; 1.5x for mid/small-caps
    public final double breakoutVolumeMultiplier;
    public final double nearBreakoutMinAbovePivotPct;
    public final double nearBreakoutMaxAbovePivotPct;
    public final double nearBreakoutVolumeMultiplier;
    public final double watchlistMaxDistanceToPivotPct;

    // ── Trade plan ───────────────────────────────────────────────────────────
    public final double accountSize;
    public final double riskPerTradePct;
    public final double stopBufferPct;

    public AppConfig() {
        this("daily");
    }

    public AppConfig(String timeframe) {
        boolean weekly = "weekly".equalsIgnoreCase(timeframe);

        this.timeframe                 = weekly ? "weekly" : "daily";
        this.lookbackDays              = weekly ? 104 : 252;

        // IPO-friendly windows are included so recently listed stocks can still qualify.
        // Daily: short windows + quarter-style variants, Weekly: few-weeks + quarter-style variants.
        this.consolidationWindows      = weekly
                ? new int[]{6, 8, 10, 13, 16, 20, 26, 39, 52}
                : new int[]{12, 15, 20, 30, 45, 60, 90, 120, 180, 240};
        this.waveCount                 = 3;
        this.waveContractionMissTolerance = 1;

        this.minRangeContraction       = weekly ? 0.12 : 0.15;
        this.minVolumeContraction      = weekly ? 0.08 : 0.10;
        this.minQualityScore           = weekly ? 30.0 : 35.0;
        this.minRangeExpansionMultiplier = weekly ? 1.15 : 1.25;
        this.minExpansionVolumeMultiplier = weekly ? 1.05 : 1.10;
        this.minExpansionClosePosition = 0.60;
        this.wickBiasLookbackBars      = weekly ? 2 : 3;
        this.bodyDirectionalWeight     = 1.0;
        this.lowerWickPositiveWeight   = 1.25;
        this.upperWickNegativeWeight   = 1.45;
        this.maxWickBodyScoreAdjustment = weekly ? 8.0 : 12.0;
        this.minBaseHeightPct          = weekly ? 6.0 : 4.0;
        this.maxBaseHeightPct          = weekly ? 75.0 : 60.0;
        this.shortWindowHeightCapPct   = weekly ? 40.0 : 30.0;
        this.longWindowHeightCapPct    = weekly ? 72.0 : 58.0;
        this.shortWindowContractionPairRatio = weekly ? 0.95 : 1.0;
        this.longWindowContractionPairRatio  = 0.50;

        this.maxDistanceFrom52WkHighPct = 0.35;
        this.requireAboveMA            = true;
        this.maPeriod                  = weekly ? 10 : 50;
        this.annualHighLookbackBars    = weekly ? 52 : 252;
        this.minPrice                  = 5.0;

        this.breakoutBufferPct         = weekly ? 0.005 : 0.003;
        this.breakoutVolumeMultiplier  = weekly ? 1.10 : 1.25;
        // Continuation zone after breakout: allow entries that are still close enough to pivot.
        this.nearBreakoutMinAbovePivotPct = 0.03;
        this.nearBreakoutMaxAbovePivotPct = 0.08;
        this.nearBreakoutVolumeMultiplier = weekly ? 1.00 : 1.05;
        this.watchlistMaxDistanceToPivotPct = weekly ? 0.08 : 0.06;

        this.accountSize               = 100_000.0;
        this.riskPerTradePct           = 0.01;
        this.stopBufferPct             = 0.005;
    }
}
