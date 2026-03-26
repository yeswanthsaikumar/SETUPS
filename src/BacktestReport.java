import java.util.ArrayList;
import java.util.List;

public class BacktestReport {
    private final List<BacktestTrade> trades = new ArrayList<>();
    private int signals;

    public void addSignal() { signals++; }
    public void addTrade(BacktestTrade t) { trades.add(t); }
    public int getSignals()   { return signals; }
    public List<BacktestTrade> getTrades() { return trades; }
    public int getTradeCount(){ return trades.size(); }

    public long getWinCount() {
        return trades.stream().filter(t -> t.getRMultiple() > 0.0).count();
    }
    public double getWinRate() {
        return trades.isEmpty() ? 0.0 : (getWinCount() * 100.0) / trades.size();
    }
    public double getTotalR() {
        return trades.stream().mapToDouble(BacktestTrade::getRMultiple).sum();
    }
    public double getAverageR() {
        return trades.isEmpty() ? 0.0 : getTotalR() / trades.size();
    }
    public double getTotalPnl() {
        return trades.stream().mapToDouble(BacktestTrade::getPnl).sum();
    }

    /** Peak-to-trough in cumulative R (negative number = drawdown magnitude). */
    public double getMaxDrawdown() {
        double peak = 0.0, cumR = 0.0, maxDD = 0.0;
        for (BacktestTrade t : trades) {
            cumR += t.getRMultiple();
            if (cumR > peak) peak = cumR;
            double dd = cumR - peak;
            if (dd < maxDD) maxDD = dd;
        }
        return maxDD;
    }

    /** Sum of positive R / abs(sum of negative R). */
    public double getProfitFactor() {
        double pos = trades.stream().filter(t -> t.getRMultiple() > 0)
                .mapToDouble(BacktestTrade::getRMultiple).sum();
        double neg = trades.stream().filter(t -> t.getRMultiple() < 0)
                .mapToDouble(t -> -t.getRMultiple()).sum();
        return neg == 0.0 ? (pos > 0 ? 99.0 : 0.0) : pos / neg;
    }

    public double getAvgMae() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getMae).average().orElse(0.0);
    }
    public double getAvgMfe() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getMfe).average().orElse(0.0);
    }
    public double getAvgHoldBars() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getHoldBars).average().orElse(0.0);
    }
    public long getT1HitCount() { return trades.stream().filter(BacktestTrade::isHitT1).count(); }
    public long getT2HitCount() { return trades.stream().filter(BacktestTrade::isHitT2).count(); }
    public long getT3HitCount() { return trades.stream().filter(BacktestTrade::isHitT3).count(); }
    public double getAvgBenchmarkReturnPct() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getBenchmarkReturnPct).average().orElse(0.0);
    }
    public double getAvgAlphaPct() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getAlphaPct).average().orElse(0.0);
    }
    public double getAlphaWinRate() {
        if (trades.isEmpty()) {
            return 0.0;
        }
        long winners = trades.stream().filter(t -> t.getAlphaPct() > 0.0).count();
        return winners * 100.0 / trades.size();
    }
    public double getAvgMarketStrengthScore() {
        return trades.isEmpty() ? 0.0 :
                trades.stream().mapToDouble(BacktestTrade::getMarketStrengthScore).average().orElse(0.0);
    }

    public String toSummaryLine() {
        return String.format(
                "Signals %d | Trades %d | WinRate %.1f%% | AvgR %.2f | TotalR %.2f | MaxDD %.2fR | PF %.2f | PnL %.2f | AvgAlpha %.2f%% | AlphaWin %.1f%% | MktScore %.2f",
                signals, getTradeCount(), getWinRate(), getAverageR(),
                getTotalR(), getMaxDrawdown(), getProfitFactor(), getTotalPnl(),
                getAvgAlphaPct(), getAlphaWinRate(), getAvgMarketStrengthScore()
        );
    }
}
