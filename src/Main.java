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
        long startTime = System.currentTimeMillis();
        List<ScanResult> results = scannerEngine.scan(options.symbols, options.lookbackDays, options.timeframe);
        List<RejectionDiagnostic> rejections = scannerEngine.getLastRejections();
        long duration = System.currentTimeMillis() - startTime;

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

        // Export structured data if requested
        if (!"none".equals(options.exportFormat)) {
            try {
                StructuredExporter.ScanExportData exportData = buildScanExportData(
                    options, results, duration
                );
                StructuredExporter.writeExports(
                    "output", 
                    options.outPrefix, 
                    exportData, 
                    options.exportFormat
                );
                System.out.println("\nStructured exports written to: output/");
            } catch (Exception ex) {
                System.err.println("Failed to write structured exports: " + ex.getMessage());
            }
        }

        // Also write legacy text export if exists
        ResultExporter.exportScanResults(results, options.exportFormat, options.outPrefix);
        ResultExporter.exportRejectionsLatest(rejections, inferMarket(options.symbols), options.timeframe);
    }

    private static StructuredExporter.ScanExportData buildScanExportData(
            CliOptions options, 
            List<ScanResult> results, 
            long durationMs) {
        StructuredExporter.ScanExportData data = new StructuredExporter.ScanExportData();
        
        data.metadata.mode = "scan";
        data.metadata.timeframe = options.timeframe;
        data.metadata.lookbackDays = options.lookbackDays;
        data.metadata.setupFilter = options.setups;
        data.metadata.symbols = options.symbols;
        data.metadata.totalSymbolsProcessed = options.symbols.size();
        data.metadata.executionTimeMs = durationMs;
        
        for (ScanResult result : results) {
            StructuredExporter.SignalExport signal = new StructuredExporter.SignalExport();
            signal.symbol = result.getSymbol();
            signal.signalType = result.getSignalType();
            signal.baseQualityScore = result.getSetup().getQualityScore();
            signal.alignmentBonus = result.getAlignmentBonus();
            signal.finalScore = result.getQualityScore();
            
            if (result.getBreakoutQuality() != null) {
                signal.breakoutQualityRating = result.getBreakoutQuality().qualityRating;
                signal.breakoutQualityScore = result.getBreakoutQuality().totalQualityScore;
            }
            
            data.hits.add(signal);
        }
        
        return data;
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
        List<RejectionDiagnostic> rejections = scannerEngine.getLastRejections();

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
        ResultExporter.exportRejectionsLatest(rejections, inferMarket(options.symbols), options.timeframe);
    }

    private static String inferMarket(List<String> symbols) {
        if (symbols == null || symbols.isEmpty()) {
            return "us";
        }
        int indiaVotes = 0;
        int usVotes = 0;
        for (String symbol : symbols) {
            String s = symbol == null ? "" : symbol.trim().toUpperCase();
            if (s.endsWith(".NS") || s.endsWith(".BO")) {
                indiaVotes++;
            } else {
                usVotes++;
            }
        }
        return indiaVotes > usVotes ? "india" : "us";
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