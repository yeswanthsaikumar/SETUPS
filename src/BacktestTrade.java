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

    public BacktestTrade(
            String symbol,
            LocalDate entryDate,
            LocalDate exitDate,
            double entryPrice,
            double exitPrice,
            double stopPrice,
            long shares,
            double rMultiple,
            double pnl,
            String exitReason
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
    }

    public String getSymbol() {
        return symbol;
    }

    public LocalDate getEntryDate() {
        return entryDate;
    }

    public LocalDate getExitDate() {
        return exitDate;
    }

    public double getEntryPrice() {
        return entryPrice;
    }

    public double getExitPrice() {
        return exitPrice;
    }

    public double getStopPrice() {
        return stopPrice;
    }

    public long getShares() {
        return shares;
    }

    public double getRMultiple() {
        return rMultiple;
    }

    public double getPnl() {
        return pnl;
    }

    public String getExitReason() {
        return exitReason;
    }

    public String toConsoleLine() {
        return String.format(
                "%s | Entry %s %.2f | Exit %s %.2f | R %.2f | PnL %.2f | %s",
                symbol,
                entryDate,
                entryPrice,
                exitDate,
                exitPrice,
                rMultiple,
                pnl,
                exitReason
        );
    }
}

