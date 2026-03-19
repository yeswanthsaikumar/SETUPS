import java.util.ArrayList;
import java.util.List;

public class BacktestReport {
    private final List<BacktestTrade> trades = new ArrayList<>();
    private int signals;

    public void addSignal() {
        signals++;
    }

    public void addTrade(BacktestTrade trade) {
        trades.add(trade);
    }

    public int getSignals() {
        return signals;
    }

    public List<BacktestTrade> getTrades() {
        return trades;
    }

    public int getTradeCount() {
        return trades.size();
    }

    public long getWinCount() {
        return trades.stream().filter(t -> t.getRMultiple() > 0.0).count();
    }

    public double getWinRate() {
        if (trades.isEmpty()) {
            return 0.0;
        }
        return (getWinCount() * 100.0) / trades.size();
    }

    public double getTotalR() {
        return trades.stream().mapToDouble(BacktestTrade::getRMultiple).sum();
    }

    public double getAverageR() {
        if (trades.isEmpty()) {
            return 0.0;
        }
        return getTotalR() / trades.size();
    }

    public double getTotalPnl() {
        return trades.stream().mapToDouble(BacktestTrade::getPnl).sum();
    }

    public String toSummaryLine() {
        return String.format(
                "Signals %d | Trades %d | WinRate %.1f%% | AvgR %.2f | TotalR %.2f | TotalPnL %.2f",
                signals,
                getTradeCount(),
                getWinRate(),
                getAverageR(),
                getTotalR(),
                getTotalPnl()
        );
    }
}

