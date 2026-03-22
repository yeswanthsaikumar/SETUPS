import java.time.LocalDate;

public class MarketRegimeSnapshot {
    private final LocalDate asOfDate;
    private final String mode;
    private final String benchmarkSymbol;
    private final String vixSymbol;
    private final MarketRegimeState state;
    private final double score;
    private final double trendScore;
    private final double breadthScore;
    private final double volatilityScore;
    private final double rankingMultiplier;
    private final boolean indexAbove50;
    private final boolean indexAbove200;
    private final boolean ma50Above200;
    private final double breadthAbove50Pct;
    private final double breadthAbove200Pct;
    private final double vixPercentile;
    private final double indexAtrPercentile;

    public MarketRegimeSnapshot(
            LocalDate asOfDate,
            String mode,
            String benchmarkSymbol,
            String vixSymbol,
            MarketRegimeState state,
            double score,
            double trendScore,
            double breadthScore,
            double volatilityScore,
            double rankingMultiplier,
            boolean indexAbove50,
            boolean indexAbove200,
            boolean ma50Above200,
            double breadthAbove50Pct,
            double breadthAbove200Pct,
            double vixPercentile,
            double indexAtrPercentile
    ) {
        this.asOfDate = asOfDate;
        this.mode = mode;
        this.benchmarkSymbol = benchmarkSymbol;
        this.vixSymbol = vixSymbol;
        this.state = state;
        this.score = score;
        this.trendScore = trendScore;
        this.breadthScore = breadthScore;
        this.volatilityScore = volatilityScore;
        this.rankingMultiplier = rankingMultiplier;
        this.indexAbove50 = indexAbove50;
        this.indexAbove200 = indexAbove200;
        this.ma50Above200 = ma50Above200;
        this.breadthAbove50Pct = breadthAbove50Pct;
        this.breadthAbove200Pct = breadthAbove200Pct;
        this.vixPercentile = vixPercentile;
        this.indexAtrPercentile = indexAtrPercentile;
    }

    public static MarketRegimeSnapshot neutral(String mode) {
        return new MarketRegimeSnapshot(
                null,
                mode == null || mode.isBlank() ? "off" : mode.toLowerCase(),
                "",
                "",
                MarketRegimeState.UNKNOWN,
                50.0,
                0.5,
                0.5,
                0.5,
                1.0,
                false,
                false,
                false,
                50.0,
                50.0,
                50.0,
                50.0
        );
    }

    public LocalDate getAsOfDate() { return asOfDate; }
    public String getMode() { return mode; }
    public String getBenchmarkSymbol() { return benchmarkSymbol; }
    public String getVixSymbol() { return vixSymbol; }
    public MarketRegimeState getState() { return state; }
    public double getScore() { return score; }
    public double getTrendScore() { return trendScore; }
    public double getBreadthScore() { return breadthScore; }
    public double getVolatilityScore() { return volatilityScore; }
    public double getRankingMultiplier() { return rankingMultiplier; }
    public boolean isIndexAbove50() { return indexAbove50; }
    public boolean isIndexAbove200() { return indexAbove200; }
    public boolean isMa50Above200() { return ma50Above200; }
    public double getBreadthAbove50Pct() { return breadthAbove50Pct; }
    public double getBreadthAbove200Pct() { return breadthAbove200Pct; }
    public double getVixPercentile() { return vixPercentile; }
    public double getIndexAtrPercentile() { return indexAtrPercentile; }

    public boolean isPoorRegime() {
        return state == MarketRegimeState.BROAD_WEAK_TAPE || state == MarketRegimeState.PANIC_VOLATILITY;
    }

    public String toConsoleLine() {
        return String.format(
                "%s | Score %.1f | Trend %.2f | Breadth %.2f | Vol %.2f | B50 %.1f%% | B200 %.1f%% | VIX%% %.1f | ATR%% %.1f",
                state,
                score,
                trendScore,
                breadthScore,
                volatilityScore,
                breadthAbove50Pct,
                breadthAbove200Pct,
                vixPercentile,
                indexAtrPercentile
        );
    }
}

