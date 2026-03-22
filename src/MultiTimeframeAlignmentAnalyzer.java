import java.util.List;
/**
 * Analyzes multi-timeframe alignment between daily and weekly setups.
 * 
 * Provides score bonuses when:
 * - Daily breakout + Weekly breakout → Strong alignment, boost score
 * - Daily breakout + Weekly watchlist/base → Moderate alignment, small boost
 * - Weekly valid for both signals
 * 
 * Philosophy: Start with score bonus (safe), not hard filter (conservative approach).
 * Later if backtests confirm, can be made into a hard requirement for lower-rated setups.
 */
public class MultiTimeframeAlignmentAnalyzer {
    private final MarketDataProvider marketDataProvider;
    private final VcpDetector vcpDetector;
    private final BreakoutEvaluator breakoutEvaluator;
    private final AppConfig config;
    public MultiTimeframeAlignmentAnalyzer(
            MarketDataProvider marketDataProvider,
            VcpDetector vcpDetector,
            BreakoutEvaluator breakoutEvaluator,
            AppConfig config
    ) {
        this.marketDataProvider = marketDataProvider;
        this.vcpDetector = vcpDetector;
        this.breakoutEvaluator = breakoutEvaluator;
        this.config = config;
    }
    /**
     * Analyzes alignment for a daily signal and returns alignment metadata.
     * 
     * @param symbol Stock symbol
     * @param dailySetup The daily VCP setup
     * @param dailyCandles Daily candles list
     * @return MultiTimeframeContext with alignment info and bonus
     */
    public MultiTimeframeContext analyzeAlignmentForDaily(
            String symbol,
            VcpSetup dailySetup,
            List<Candle> dailyCandles
    ) {
        MultiTimeframeContext ctx = new MultiTimeframeContext();
        try {
            // Load weekly data
            List<Candle> weeklyCandles = marketDataProvider.getWeeklyCandles(symbol, config.lookbackDays * 2);
            if (weeklyCandles == null || weeklyCandles.size() < 20) {
                ctx.weeklyAvailable = false;
                return ctx;
            }
            ctx.weeklyAvailable = true;
            // Detect weekly setup at the latest candle
            VcpSetup weeklySetup = vcpDetector.detect(weeklyCandles, config, "both");
            // Check if weekly has a valid setup
            if (weeklySetup != null && weeklySetup.getQualityScore() >= config.minQualityScore) {
                ctx.weeklySetupExists = true;
                ctx.weeklySetupScore = weeklySetup.getQualityScore();
                // Check if weekly has breakout
                boolean weeklyBreakout = breakoutEvaluator.isBullishBreakout(weeklyCandles, weeklySetup, config);
                boolean weeklyNearBreakout = !weeklyBreakout && breakoutEvaluator.isNearBreakoutContinuation(
                        weeklyCandles, weeklySetup, config
                );
                if (weeklyBreakout) {
                    ctx.weeklyBreakout = true;
                    ctx.alignmentBonus = 15.0; // Strong alignment bonus
                    ctx.alignmentReason = "DAILY_BREAKOUT_WEEKLY_BREAKOUT";
                } else if (weeklyNearBreakout) {
                    ctx.weeklyNearBreakout = true;
                    ctx.alignmentBonus = 10.0; // Moderate alignment bonus
                    ctx.alignmentReason = "DAILY_BREAKOUT_WEEKLY_NEAR_BREAKOUT";
                } else {
                    // Weekly has valid setup but no breakout
                    ctx.alignmentBonus = 5.0; // Small alignment bonus
                    ctx.alignmentReason = "DAILY_BREAKOUT_WEEKLY_VALID_BASE";
                }
            } else {
                ctx.weeklySetupExists = false;
                ctx.alignmentBonus = 0.0; // No bonus if weekly doesn't qualify
            }
        } catch (Exception ex) {
            // Weekly data unavailable or error loading; don't apply bonus
            ctx.weeklyAvailable = false;
            ctx.alignmentBonus = 0.0;
        }
        return ctx;
    }
    /**
     * Analyzes alignment for a watchlist signal and returns alignment metadata.
     * Watchlist signals are entries near the pivot, before breakout.
     * 
     * @param symbol Stock symbol
     * @param dailySetup The daily VCP setup
     * @param dailyCandles Daily candles list
     * @return MultiTimeframeContext with alignment info and bonus
     */
    public MultiTimeframeContext analyzeAlignmentForWatchlist(
            String symbol,
            VcpSetup dailySetup,
            List<Candle> dailyCandles
    ) {
        MultiTimeframeContext ctx = new MultiTimeframeContext();
        try {
            // Load weekly data
            List<Candle> weeklyCandles = marketDataProvider.getWeeklyCandles(symbol, config.lookbackDays * 2);
            if (weeklyCandles == null || weeklyCandles.size() < 20) {
                ctx.weeklyAvailable = false;
                return ctx;
            }
            ctx.weeklyAvailable = true;
            // Detect weekly setup at the latest candle
            VcpSetup weeklySetup = vcpDetector.detect(weeklyCandles, config, "both");
            // For watchlist, we care most about weekly having a strong base
            if (weeklySetup != null && weeklySetup.getQualityScore() >= config.minQualityScore) {
                ctx.weeklySetupExists = true;
                ctx.weeklySetupScore = weeklySetup.getQualityScore();
                // Check if weekly has breakout or near-breakout
                boolean weeklyBreakout = breakoutEvaluator.isBullishBreakout(weeklyCandles, weeklySetup, config);
                boolean weeklyNearBreakout = !weeklyBreakout && breakoutEvaluator.isNearBreakoutContinuation(
                        weeklyCandles, weeklySetup, config
                );
                if (weeklyBreakout) {
                    ctx.weeklyBreakout = true;
                    ctx.alignmentBonus = 12.0; // Good boost for weekly breakout + daily watchlist
                    ctx.alignmentReason = "WATCHLIST_WEEKLY_BREAKOUT";
                } else if (weeklyNearBreakout) {
                    ctx.weeklyNearBreakout = true;
                    ctx.alignmentBonus = 8.0; // Moderate boost for weekly near-breakout
                    ctx.alignmentReason = "WATCHLIST_WEEKLY_NEAR_BREAKOUT";
                } else {
                    // Weekly has valid setup, forms strong base
                    ctx.alignmentBonus = 5.0; // Small boost for weekly base
                    ctx.alignmentReason = "WATCHLIST_WEEKLY_STRONG_BASE";
                }
            } else {
                ctx.weeklySetupExists = false;
                ctx.alignmentBonus = 0.0; // No bonus if weekly doesn't qualify
            }
        } catch (Exception ex) {
            // Weekly data unavailable; don't apply bonus
            ctx.weeklyAvailable = false;
            ctx.alignmentBonus = 0.0;
        }
        return ctx;
    }
    /**
     * Container for multi-timeframe alignment analysis results.
     */
    public static class MultiTimeframeContext {
        public boolean weeklyAvailable;           // Whether weekly data could be loaded
        public boolean weeklySetupExists;         // Whether a valid weekly VCP setup exists
        public boolean weeklyBreakout;            // Whether weekly has an active breakout
        public boolean weeklyNearBreakout;        // Whether weekly is in near-breakout zone
        public double weeklySetupScore;           // Weekly setup quality score (if exists)
        public double alignmentBonus;             // Score bonus to apply (0-15)
        public String alignmentReason;            // Description of alignment type
        public MultiTimeframeContext() {
            this.weeklyAvailable = false;
            this.weeklySetupExists = false;
            this.weeklyBreakout = false;
            this.weeklyNearBreakout = false;
            this.weeklySetupScore = 0.0;
            this.alignmentBonus = 0.0;
            this.alignmentReason = "NO_ALIGNMENT";
        }
        @Override
        public String toString() {
            return String.format(
                    "MTF[Available=%b, SetupExists=%b, Breakout=%b, NearBK=%b, Score=%.1f, Bonus=%.1f, Reason=%s]",
                    weeklyAvailable, weeklySetupExists, weeklyBreakout, weeklyNearBreakout,
                    weeklySetupScore, alignmentBonus, alignmentReason
            );
        }
    }
}
