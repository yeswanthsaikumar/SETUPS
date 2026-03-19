import java.util.List;
import java.nio.file.Paths;
import java.time.Duration;

public class Main {
    public static void main(String[] args) {
        CliOptions options = CliOptions.parse(args);
        AppConfig config = new AppConfig(options.timeframe);
        MarketDataProvider provider = buildProvider(options);

        ScannerEngine scannerEngine = new ScannerEngine(
                provider,
                new VcpDetector(),
                new BreakoutEvaluator(),
                new TradePlanner(),
                config,
                options.setups
        );

        if ("backtest".equals(options.mode)) {
            runBacktest(options, provider, scannerEngine);
        } else if ("watchlist".equals(options.mode)) {
            runWatchlist(options, scannerEngine);
        } else {
            runScan(options, scannerEngine);
        }
    }

    private static void runScan(CliOptions options, ScannerEngine scannerEngine) {
        List<ScanResult> results = scannerEngine.scan(options.symbols, options.lookbackDays, options.timeframe);

        System.out.println(("weekly".equals(options.timeframe) ? "Weekly" : "Daily") + " VCP + Range Expansion Breakout Scan Results");
        System.out.println("Setup filter: " + options.setups.toUpperCase());
        System.out.println("================================");

        if (results.isEmpty()) {
            System.out.println("No qualifying breakouts found for the current universe.");
        } else {
            for (ScanResult result : results) {
                System.out.println(result.toConsoleLine());
            }
        }

        ResultExporter.exportScanResults(results, options.exportFormat, options.outPrefix);
    }

    private static void runBacktest(CliOptions options, MarketDataProvider provider, ScannerEngine scannerEngine) {
        BacktestEngine backtestEngine = new BacktestEngine(
                provider,
                scannerEngine,
                options.timeframe,
                options.backtestHoldDays,
                options.backtestTargetR
        );

        BacktestReport report = backtestEngine.run(options.symbols, options.lookbackDays);

        System.out.println("Backtest Results");
        System.out.println("================");
        System.out.println(report.toSummaryLine());
        int show = Math.min(15, report.getTrades().size());
        for (int i = 0; i < show; i++) {
            System.out.println(report.getTrades().get(i).toConsoleLine());
        }

        ResultExporter.exportBacktestReport(report, options.exportFormat, options.outPrefix);
    }

    private static void runWatchlist(CliOptions options, ScannerEngine scannerEngine) {
        List<WatchlistResult> results = scannerEngine.scanWatchlist(options.symbols, options.lookbackDays, options.timeframe);

        System.out.println(("weekly".equals(options.timeframe) ? "Weekly" : "Daily") + " Potential Breakout Watchlist");
        System.out.println("Setup filter: " + options.setups.toUpperCase());
        System.out.println("================================");

        if (results.isEmpty()) {
            System.out.println("No watchlist candidates found near pivot for the current universe.");
        } else {
            for (WatchlistResult result : results) {
                System.out.println(result.toConsoleLine());
            }
        }

        ResultExporter.exportWatchlistResults(results, options.exportFormat, options.outPrefix);
    }

    private static MarketDataProvider buildProvider(CliOptions options) {
        if ("yahoo".equals(options.provider)) {
            return new YahooFinanceProvider(
                    options.retries,
                    Paths.get(options.cacheDir),
                    Duration.ofMinutes(options.cacheTtlMinutes)
            );
        }
        return new SampleMarketDataProvider();
    }
}