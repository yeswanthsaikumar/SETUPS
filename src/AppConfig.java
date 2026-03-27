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
    public final double meanReversionMinPullbackPct;
    public final double meanReversionMaxPullbackPct;
    public final double meanReversionMinRecoveryPct;
    public final double meanReversionVolumeMultiplier;
    public final double meanReversionNearVolumeMultiplier;
    public final double meanReversionMaxDistanceToTriggerPct;
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
    public final double maxBreakoutEntryDistancePct;

    // ── Trade plan ───────────────────────────────────────────────────────────
    public final double accountSize;
    public final double riskPerTradePct;
    public final double stopBufferPct;

    // ── Exit policy (backtest/runtime) ───────────────────────────────────────
    // Partial exits: default 25% at T1, 25% at T2, trail remaining 50%
    public final double partialExitPctAtT1;
    public final double partialExitPctAtT2;

    // ATR trailing stop policy
    public final boolean enableAtrTrailingStop;
    public final int atrTrailPeriodDaily;
    public final int atrTrailPeriodWeekly;
    public final double atrTrailMultDailyVcp;
    public final double atrTrailMultDailyRangeExpansion;
    public final double atrTrailMultDailyMeanReversion;
    public final double atrTrailMultWeeklyVcp;
    public final double atrTrailMultWeeklyRangeExpansion;
    public final double atrTrailMultWeeklyMeanReversion;

    // Swing-low trailing stop policy
    public final boolean enableSwingLowTrailingStop;
    public final int swingLookbackDaily;
    public final int swingLookbackWeekly;
    public final double swingStopBufferPct;

    // Optional break-even upgrade once trade proves itself (typically after T1)
    public final boolean moveStopToBreakEvenAfterT1;
    public final double breakEvenBufferPct;

    // Structure-first trailing policy
    public final double structureStopBufferLowVolPct;
    public final double structureStopBufferMedVolPct;
    public final double structureStopBufferHighVolPct;
    public final double structureTrailPctLowVol;
    public final double structureTrailPctMedVol;
    public final double structureTrailPctHighVol;
    public final int structureVolatilityLookbackBars;
    public final double strongTrendMarketScoreThreshold;
    public final double emaTrailBufferPct;

    // Delay trailing activation slightly so we avoid reacting to the first noisy bar
    public final int minBarsAfterSignalForTrailingDaily;
    public final int minBarsAfterSignalForTrailingWeekly;

    // Time-stop by setup type and timeframe
    public final int holdBarsDailyVcp;
    public final int holdBarsDailyRangeExpansion;
    public final int holdBarsDailyMeanReversion;
    public final int holdBarsWeeklyVcp;
    public final int holdBarsWeeklyRangeExpansion;
    public final int holdBarsWeeklyMeanReversion;

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
        this.meanReversionMinPullbackPct = weekly ? 0.03 : 0.04;
        this.meanReversionMaxPullbackPct = weekly ? 0.18 : 0.14;
        this.meanReversionMinRecoveryPct = weekly ? 0.015 : 0.01;
        this.meanReversionVolumeMultiplier = weekly ? 0.95 : 1.00;
        this.meanReversionNearVolumeMultiplier = weekly ? 0.90 : 0.95;
        this.meanReversionMaxDistanceToTriggerPct = weekly ? 0.035 : 0.025;
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
        this.maxBreakoutEntryDistancePct = weekly ? 0.06 : 0.05;

        this.accountSize               = 100_000.0;
        this.riskPerTradePct           = 0.01;
        this.stopBufferPct             = 0.005;

        // Exit policy defaults (safe + configurable)
        this.partialExitPctAtT1        = 0.25;
        this.partialExitPctAtT2        = 0.25;

        this.enableAtrTrailingStop     = true;
        this.atrTrailPeriodDaily       = 14;
        this.atrTrailPeriodWeekly      = 8;
        this.atrTrailMultDailyVcp      = 2.0;
        this.atrTrailMultDailyRangeExpansion = 2.4;
        this.atrTrailMultDailyMeanReversion = 1.8;
        this.atrTrailMultWeeklyVcp     = 2.4;
        this.atrTrailMultWeeklyRangeExpansion = 2.8;
        this.atrTrailMultWeeklyMeanReversion = 2.1;

        this.enableSwingLowTrailingStop = true;
        this.swingLookbackDaily        = 5;
        this.swingLookbackWeekly       = 3;
        this.swingStopBufferPct        = 0.005;

        this.moveStopToBreakEvenAfterT1 = true;
        this.breakEvenBufferPct         = weekly ? 0.0015 : 0.001;

        this.structureStopBufferLowVolPct = 0.001;
        this.structureStopBufferMedVolPct = 0.003;
        this.structureStopBufferHighVolPct = weekly ? 0.010 : 0.007;
        this.structureTrailPctLowVol = 0.05;
        this.structureTrailPctMedVol = 0.06;
        this.structureTrailPctHighVol = 0.08;
        this.structureVolatilityLookbackBars = weekly ? 8 : 14;
        this.strongTrendMarketScoreThreshold = weekly ? 3.0 : 4.0;
        this.emaTrailBufferPct = weekly ? 0.005 : 0.003;

        this.minBarsAfterSignalForTrailingDaily = 2;
        this.minBarsAfterSignalForTrailingWeekly = 1;

        // Setup + timeframe aware hold periods
        this.holdBarsDailyVcp          = 15;
        this.holdBarsDailyRangeExpansion = 11;
        this.holdBarsDailyMeanReversion = 8;
        this.holdBarsWeeklyVcp         = 10;
        this.holdBarsWeeklyRangeExpansion = 8;
        this.holdBarsWeeklyMeanReversion = 6;
    }
}
