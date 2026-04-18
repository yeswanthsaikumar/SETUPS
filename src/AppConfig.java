public class AppConfig {
    // ── Data ──────────────────────────────────────────────────────────────────
    public final int lookbackDays;
    public final String timeframe;

    // ── IPO detection ─────────────────────────────────────────────────────────
    // Stocks with fewer trading bars than this are flagged as IPO (recently listed).
    // Daily: ~126 bars ≈ 6 months of trading; Weekly: ~26 bars ≈ 6 months.
    public final int ipoMaxBarsSinceListing;

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

    // ── Relative Strength & Sector ──────────────────────────────────────────
    // Minimum RS percentile rank to pass live scan (0-100). 0 = disabled.
    public final double minRsPercentile;
    // Minimum average daily volume (shares) to filter illiquid names
    public final double minAvgVolume;
    // Taxonomy file path for sector/industry lookup
    public final String taxonomyPath;

    // ── Volume dry-up: pre-breakout quietness ───────────────────────────────
    // Last N bars before breakout should have volume ≤ this ratio of 50-day avg
    public final int volumeDryUpLookbackBars;
    public final double volumeDryUpMaxRatio;
    public final double volumeDryUpScoreBonus;

    // ── Accumulation/Distribution in base ───────────────────────────────────
    // Minimum ratio of accumulation days to distribution days in the base
    public final double minAccumDistRatio;
    public final double accumDistScoreBonus;

    // ── Gap-up breakout ─────────────────────────────────────────────────────
    // If open > pivot and volume >= this multiple, classify as GAP_BREAKOUT
    public final double gapBreakoutVolumeMultiplier;
    public final double gapBreakoutScoreBonus;

    // ── Tight-close count ───────────────────────────────────────────────────
    // Count bars in last N where closes cluster within this % of each other
    public final int tightCloseLookbackBars;
    public final double tightCloseMaxSpreadPct;
    public final double tightCloseScoreBonus;

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
        this.ipoMaxBarsSinceListing    = weekly ? 26 : 126;  // ~6 months of trading

        // IPO-friendly windows are included so recently listed stocks can still qualify.
        // Daily: short windows + quarter-style variants, Weekly: few-weeks + quarter-style variants.
        this.consolidationWindows      = weekly
                ? new int[]{6, 8, 10, 13, 16, 20, 26, 39, 52}
                : new int[]{12, 15, 20, 30, 45, 60, 90, 120, 180, 240};
        this.waveCount                 = 3;
        this.waveContractionMissTolerance = 1;

        // ── Quality gates (tightened for higher win-rate) ─────────────────────
        this.minRangeContraction       = weekly ? 0.15 : 0.18;   // was 0.12/0.15
        this.minVolumeContraction      = weekly ? 0.10 : 0.12;   // was 0.08/0.10
        this.minQualityScore           = weekly ? 38.0 : 40.0;   // lowered from 40/45 to catch GMDC-type wider bases
        this.minRangeExpansionMultiplier = weekly ? 1.20 : 1.35; // was 1.15/1.25 — stronger expansion required
        this.minExpansionVolumeMultiplier = weekly ? 1.15 : 1.25;// was 1.05/1.10 — more vol conviction
        this.minExpansionClosePosition = 0.65;                    // was 0.60 — close must be in upper 35%
        this.meanReversionMinPullbackPct = weekly ? 0.04 : 0.05; // was 0.03/0.04
        this.meanReversionMaxPullbackPct = weekly ? 0.15 : 0.12; // was 0.18/0.14 — tighter pullback band
        this.meanReversionMinRecoveryPct = weekly ? 0.02 : 0.015;// was 0.015/0.01 — more recovery needed
        this.meanReversionVolumeMultiplier = weekly ? 1.00 : 1.05;// was 0.95/1.00 — require volume
        this.meanReversionNearVolumeMultiplier = weekly ? 0.95 : 1.00;// was 0.90/0.95
        this.meanReversionMaxDistanceToTriggerPct = weekly ? 0.025 : 0.018;// was 0.035/0.025
        this.wickBiasLookbackBars      = weekly ? 3 : 4;          // was 2/3
        this.bodyDirectionalWeight     = 1.2;                     // was 1.0 — reward clean bodies
        this.lowerWickPositiveWeight   = 1.35;                    // was 1.25
        this.upperWickNegativeWeight   = 1.60;                    // was 1.45 — penalise rejection more
        this.maxWickBodyScoreAdjustment = weekly ? 10.0 : 14.0;  // was 8/12
        this.minBaseHeightPct          = weekly ? 6.0 : 4.0;     // lowered from 7/5 to catch tighter/shallower bases
        this.maxBaseHeightPct          = weekly ? 65.0 : 50.0;   // raised from 60/45 to allow wider bases (GMDC-type)
        this.shortWindowHeightCapPct   = weekly ? 35.0 : 25.0;   // was 40/30
        this.longWindowHeightCapPct    = weekly ? 58.0 : 44.0;   // was 72/58
        this.shortWindowContractionPairRatio = weekly ? 1.0 : 1.0;// was 0.95/1.0
        this.longWindowContractionPairRatio  = 0.60;              // was 0.50

        // Trend filter: tighter proximity to highs, above stronger MA
        this.maxDistanceFrom52WkHighPct = 0.30;  // was 0.25 — allow 30% below 52-wk high for wider bases (e.g. GMDC)
        this.requireAboveMA            = true;
        this.maPeriod                  = weekly ? 30 : 50;        // was 10/50 — weekly uses 30-bar MA
        this.annualHighLookbackBars    = weekly ? 52 : 252;
        this.minPrice                  = 5.0;

        // ── NEW: RS, Liquidity, Sector ────────────────────────────────────────
        this.minRsPercentile           = 0.0;   // 0 = disabled; set to 50-70 for strict filtering
        this.minAvgVolume              = weekly ? 50_000.0 : 100_000.0;  // Minimum avg daily volume
        this.taxonomyPath              = "data/nse_stock_taxonomy.csv";

        // ── NEW: Volume dry-up before breakout ────────────────────────────────
        this.volumeDryUpLookbackBars   = weekly ? 3 : 5;
        this.volumeDryUpMaxRatio       = 0.70;   // Last 5 bars vol should be ≤ 70% of 50-day avg
        this.volumeDryUpScoreBonus     = 6.0;    // Score bonus for dry-up detected

        // ── NEW: Accumulation/Distribution ────────────────────────────────────
        this.minAccumDistRatio         = 1.0;    // At least equal accum vs dist days
        this.accumDistScoreBonus       = 5.0;    // Bonus when ratio ≥ 1.5

        // ── NEW: Gap-up breakout ──────────────────────────────────────────────
        this.gapBreakoutVolumeMultiplier = 2.0;  // Open > pivot + vol ≥ 2x avg = gap breakout
        this.gapBreakoutScoreBonus     = 8.0;

        // ── NEW: Tight-close clustering ───────────────────────────────────────
        this.tightCloseLookbackBars    = weekly ? 4 : 7;
        this.tightCloseMaxSpreadPct    = 1.5;    // Closes within 1.5% of each other
        this.tightCloseScoreBonus      = 5.0;

        // Breakout confirmation: more volume + closer-to-pivot entries only
        this.breakoutBufferPct         = weekly ? 0.006 : 0.004; // was 0.005/0.003
        this.breakoutVolumeMultiplier  = weekly ? 1.25 : 1.50;   // was 1.10/1.25 — meaningful vol surge
        // Continuation zone after breakout: allow entries that are still close enough to pivot.
        this.nearBreakoutMinAbovePivotPct = 0.03;
        this.nearBreakoutMaxAbovePivotPct = 0.08;
        this.nearBreakoutVolumeMultiplier = weekly ? 1.00 : 1.05;
        // Pre-breakout watchlist band: only keep names within 5% below pivot.
        this.watchlistMaxDistanceToPivotPct = 0.05;
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
