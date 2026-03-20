import java.time.LocalDate;

public class BacktestTrade {
    private final String symbol;
    private final LocalDate entryDate;
    private final LocalDate exitDate;
    private final double entryPrice;
    private final double exitPrice;
    private final double stopPrice;
    private final long shares;
    private final double rMultiple;
    private final double pnl;
    private final String exitReason;
    // ── Setup metadata ────────────────────────────────────────────────────────
    private final String setupType;
    private final String setupRating;
    private final String windowLabel;
    private final double qualityScore;
    // ── Trade analytics ───────────────────────────────────────────────────────
    private final double mae;      // max adverse excursion % from entry
    private final double mfe;      // max favorable excursion % from entry
    private final int holdBars;
    private final boolean hitT1;
    private final boolean hitT2;
    private final boolean hitT3;

    public BacktestTrade(
            String symbol, LocalDate entryDate, LocalDate exitDate,
            double entryPrice, double exitPrice, double stopPrice, long shares,
            double rMultiple, double pnl, String exitReason,
            String setupType, String setupRating, String windowLabel, double qualityScore,
            double mae, double mfe, int holdBars,
            boolean hitT1, boolean hitT2, boolean hitT3
    ) {
        this.symbol = symbol;
        this.entryDate = entryDate;
        this.exitDate = exitDate;
        this.entryPrice = entryPrice;
        this.exitPrice = exitPrice;
        this.stopPrice = stopPrice;
        this.shares = shares;
        this.rMultiple = rMultiple;
        this.pnl = pnl;
        this.exitReason = exitReason;
        this.setupType = setupType;
        this.setupRating = setupRating;
        this.windowLabel = windowLabel;
        this.qualityScore = qualityScore;
        this.mae = mae;
        this.mfe = mfe;
        this.holdBars = holdBars;
        this.hitT1 = hitT1;
        this.hitT2 = hitT2;
        this.hitT3 = hitT3;
    }

    public String getSymbol()      { return symbol; }
    public LocalDate getEntryDate(){ return entryDate; }
    public LocalDate getExitDate() { return exitDate; }
    public double getEntryPrice()  { return entryPrice; }
    public double getExitPrice()   { return exitPrice; }
    public double getStopPrice()   { return stopPrice; }
    public long getShares()        { return shares; }
    public double getRMultiple()   { return rMultiple; }
    public double getPnl()         { return pnl; }
    public String getExitReason()  { return exitReason; }
    public String getSetupType()   { return setupType; }
    public String getSetupRating() { return setupRating; }
    public String getWindowLabel() { return windowLabel; }
    public double getQualityScore(){ return qualityScore; }
    public double getMae()         { return mae; }
    public double getMfe()         { return mfe; }
    public int getHoldBars()       { return holdBars; }
    public boolean isHitT1()       { return hitT1; }
    public boolean isHitT2()       { return hitT2; }
    public boolean isHitT3()       { return hitT3; }

    public String toConsoleLine() {
        return String.format(
                "%s | %s | %s | Entry %s %.2f | Exit %s %.2f | R %.2f | PnL %.2f | Hold %d | %s",
                symbol, setupType, setupRating,
                entryDate, entryPrice,
                exitDate, exitPrice,
                rMultiple, pnl, holdBars, exitReason
        );
    }
}
