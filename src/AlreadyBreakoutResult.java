import java.time.LocalDate;

public class AlreadyBreakoutResult {
    private final String symbol;
    private final VcpSetup setup;
    private final LocalDate breakoutDate;
    private final double breakoutPrice;
    private final Candle latestCandle;
    private final int barsSinceBreakout;
    private final double returnSinceBreakoutPct;
    private final double maxGainPct;
    private final double maxDrawdownPct;
    private final double pivotHoldRatePct;
    private boolean ipoFlag;
    private int daysSinceListing;

    public AlreadyBreakoutResult(
            String symbol,
            VcpSetup setup,
            LocalDate breakoutDate,
            double breakoutPrice,
            Candle latestCandle,
            int barsSinceBreakout,
            double returnSinceBreakoutPct,
            double maxGainPct,
            double maxDrawdownPct,
            double pivotHoldRatePct
    ) {
        this.symbol = symbol;
        this.setup = setup;
        this.breakoutDate = breakoutDate;
        this.breakoutPrice = breakoutPrice;
        this.latestCandle = latestCandle;
        this.barsSinceBreakout = barsSinceBreakout;
        this.returnSinceBreakoutPct = returnSinceBreakoutPct;
        this.maxGainPct = maxGainPct;
        this.maxDrawdownPct = maxDrawdownPct;
        this.pivotHoldRatePct = pivotHoldRatePct;
        this.ipoFlag = false;
        this.daysSinceListing = 0;
    }

    public String getSymbol() {
        return symbol;
    }

    public VcpSetup getSetup() {
        return setup;
    }

    public LocalDate getBreakoutDate() {
        return breakoutDate;
    }

    public double getBreakoutPrice() {
        return breakoutPrice;
    }

    public Candle getLatestCandle() {
        return latestCandle;
    }

    public int getBarsSinceBreakout() {
        return barsSinceBreakout;
    }

    public double getReturnSinceBreakoutPct() {
        return returnSinceBreakoutPct;
    }

    public double getMaxGainPct() {
        return maxGainPct;
    }

    public double getMaxDrawdownPct() {
        return maxDrawdownPct;
    }

    public double getPivotHoldRatePct() {
        return pivotHoldRatePct;
    }

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
        String ipoTag = ipoFlag ? String.format(" [IPO %dd]", daysSinceListing) : "";
        return String.format(
                "%s | Setup %s | Breakout %s | Bars %d | Return %.2f%% | MaxGain %.2f%% | MaxDD %.2f%% | PivotHold %.1f%%",
                symbol,
                setup.getSetupType(),
                breakoutDate,
                barsSinceBreakout,
                returnSinceBreakoutPct,
                maxGainPct,
                maxDrawdownPct,
                pivotHoldRatePct
        ) + ipoTag;
    }
}
