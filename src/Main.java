import java.util.List;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
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
        } else if ("alreadybreakout".equals(options.mode) || "already_breakout".equals(options.mode)) {
            runAlreadyBreakout(options, scannerEngine);
        } else if ("watchlist".equals(options.mode)) {
            runWatchlist(options, scannerEngine);
        } else if ("followthrough".equals(options.mode)) {
            runFollowThrough();
        } else if ("combined".equals(options.mode)) {
            runCombined(options, scannerEngine);
        } else {
            runScan(options, scannerEngine);
        }
    }

    private static void runScan(CliOptions options, ScannerEngine scannerEngine) {
        long startTime = System.currentTimeMillis();
        List<ScanResult> results = scannerEngine.scan(options.symbols, options.lookbackDays, options.timeframe);
        List<RejectionDiagnostic> rejections = scannerEngine.getLastRejections();
        long duration = System.currentTimeMillis() - startTime;

        System.out.println(("weekly".equals(options.timeframe) ? "Weekly" : "Daily") + " VCP + Range Expansion + Mean Reversion Scan Results");
        System.out.println("Setup filter: " + options.setups.toUpperCase());

        // NEW: Display market regime context
        MarketRegimeDetector.RegimeContext regime = scannerEngine.getLastRegimeContext();
        if (regime != null) {
            System.out.println("Market Regime: " + regime.regime + " (score=" + String.format("%.1f", regime.marketScore) + " bench=" + regime.benchmarkSymbol + ")");
        }
        System.out.println("RS Rankings: " + scannerEngine.getLastRsRankings().size() + " symbols ranked");

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

            // V2 enrichment fields
            signal.rsPercentile = result.getRsPercentile();
            signal.sectorName = result.getSector();
            signal.industryName = result.getIndustry();
            signal.marketRegime = result.getMarketRegime();
            signal.sectorScoreBonus = result.getSectorBonus();
            signal.ipoFlag = result.isIpoFlag();
            signal.daysSinceListing = result.getDaysSinceListing();

            VcpSetup setup = result.getSetup();
            if (setup != null) {
                signal.volumeDryUpRatio = setup.getVolumeDryUpRatio();
                signal.accumDistRatio = setup.getAccumDistRatio();
                signal.tightCloseCount = setup.getTightCloseCount();
                signal.emaFanAligned = setup.isEmaFanAligned();
                signal.gapBreakout = setup.isGapBreakout();
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
                options.benchmarkSymbol
        );

        int barsPerYear = "weekly".equalsIgnoreCase(options.timeframe) ? 52 : 252;
        int backtestLookback = options.lookbackProvided
                ? options.lookbackDays
                : barsPerYear * options.backtestYears;
        BacktestReport report = backtestEngine.run(options.symbols, backtestLookback);

        System.out.println("Backtest Results");
        System.out.println("================");
        System.out.println(report.toSummaryLine());
        int show = Math.min(15, report.getTrades().size());
        for (int i = 0; i < show; i++) {
            System.out.println(report.getTrades().get(i).toConsoleLine());
        }

        ResultExporter.exportBacktestReport(report, options.exportFormat, options.outPrefix);
        writeBacktestHtmlReport(report, options.outPrefix, options.timeframe, options.symbols.size());
    }

    private static void writeBacktestHtmlReport(BacktestReport report, String outPrefix, String timeframe, int universeSize) {
        Path outputPath = Paths.get(outPrefix + "_backtest_report.html");
        StringBuilder html = new StringBuilder();
        html.append("<!DOCTYPE html>\n");
        html.append("<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n");
        html.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n");
        html.append("<title>Breakout Backtest Performance</title>\n");
        html.append("<style>");
        html.append("body{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:24px;} ");
        html.append("h1,h2{color:#93c5fd;} .card{background:#111827;border:1px solid #334155;border-radius:8px;padding:12px;margin-bottom:12px;} ");
        html.append("table{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px;} th,td{border:1px solid #334155;padding:6px 8px;text-align:left;} th{background:#1e293b;} ");
        html.append(".win{color:#22c55e;} .loss{color:#f87171;} .muted{color:#94a3b8;}");
        html.append("</style>\n</head>\n<body>\n");
        html.append("<h1>Breakout Backtest Performance Report</h1>\n");
        html.append("<div class=\"card\"><strong>Timeframe:</strong> ").append(timeframe)
                .append(" | <strong>Universe Size:</strong> ").append(universeSize)
                .append(" | <strong>Signals:</strong> ").append(report.getSignals())
                .append(" | <strong>Trades:</strong> ").append(report.getTradeCount()).append("</div>\n");
        html.append("<div class=\"card\">")
                .append("WinRate: ").append(String.format("%.1f%%", report.getWinRate())).append(" | ")
                .append("AvgR: ").append(String.format("%.2f", report.getAverageR())).append(" | ")
                .append("TotalR: ").append(String.format("%.2f", report.getTotalR())).append(" | ")
                .append("PnL: ").append(String.format("%.2f", report.getTotalPnl())).append(" | ")
                .append("AvgAlpha: ").append(String.format("%.2f%%", report.getAvgAlphaPct())).append(" | ")
                .append("AlphaWinRate: ").append(String.format("%.1f%%", report.getAlphaWinRate())).append(" | ")
                .append("AvgMarketStrength: ").append(String.format("%.2f", report.getAvgMarketStrengthScore()))
                .append("</div>\n");

        html.append("<h2>Trades</h2>\n<table><thead><tr>")
                .append("<th>Symbol</th><th>Entry Date</th><th>Exit Date</th><th>Setup</th><th>Signal</th><th>Entry Time</th>")
                .append("<th>Entry</th><th>Stop</th><th>Risk/Share</th><th>Shares</th><th>R</th><th>PnL</th>")
                .append("<th>Trade Return %</th><th>Benchmark %</th><th>Alpha %</th><th>Market Strength</th><th>Regime</th><th>RS</th><th>Macro Trigger</th><th>Stop Model</th><th>Trail Policy</th><th>Exit</th>")
                .append("</tr></thead><tbody>");

        for (BacktestTrade trade : report.getTrades()) {
            String pnlClass = trade.getPnl() >= 0.0 ? "win" : "loss";
            String alphaClass = trade.getAlphaPct() >= 0.0 ? "win" : "loss";
            html.append("<tr>")
                    .append("<td>").append(trade.getSymbol()).append("</td>")
                    .append("<td>").append(trade.getEntryDate()).append("</td>")
                    .append("<td>").append(trade.getExitDate()).append("</td>")
                    .append("<td>").append(trade.getSetupType()).append("/ ").append(trade.getSetupRating()).append("</td>")
                    .append("<td>").append(trade.getSignalType()).append("</td>")
                    .append("<td>").append(trade.getEntryTimeLabel()).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getEntryPrice())).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getStopPrice())).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getRiskPerShare())).append("</td>")
                    .append("<td>").append(trade.getShares()).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getRMultiple())).append("</td>")
                    .append("<td class=\"").append(pnlClass).append("\">").append(String.format("%.2f", trade.getPnl())).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getTradeReturnPct())).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getBenchmarkReturnPct())).append("</td>")
                    .append("<td class=\"").append(alphaClass).append("\">").append(String.format("%.2f", trade.getAlphaPct())).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getMarketStrengthScore())).append("</td>")
                    .append("<td>").append(trade.getEntryMarketRegime()).append("</td>")
                    .append("<td>").append(String.format("%.2f", trade.getRelativeStrengthScore())).append("</td>")
                    .append("<td>").append(trade.getMacroTrigger()).append("</td>")
                    .append("<td>").append(trade.getStructureStopModel()).append("</td>")
                    .append("<td>").append(trade.getTrailingStopPolicy()).append("</td>")
                    .append("<td class=\"muted\">").append(trade.getExitReason()).append("</td>")
                    .append("</tr>");
        }

        html.append("</tbody></table>\n</body>\n</html>\n");

        try {
            if (outputPath.getParent() != null) {
                Files.createDirectories(outputPath.getParent());
            }
            Files.writeString(outputPath, html.toString(), StandardCharsets.UTF_8);
            System.out.println("Backtest HTML report generated: " + outputPath.toAbsolutePath());
        } catch (Exception ex) {
            System.err.println("Failed to generate backtest HTML report: " + ex.getMessage());
        }
    }

    private static void runAlreadyBreakout(CliOptions options, ScannerEngine scannerEngine) {
        List<AlreadyBreakoutResult> results = scannerEngine.scanAlreadyBreakout(
                options.symbols,
                options.lookbackDays,
                options.timeframe,
                options.alreadyBreakoutMinBars,
                options.alreadyBreakoutMaxBars
        );

        System.out.println(("weekly".equals(options.timeframe) ? "Weekly" : "Daily") + " Already-Breakout Performance Tracker");
        System.out.println("Window: " + options.alreadyBreakoutMinBars + "-" + options.alreadyBreakoutMaxBars + " bars since breakout");
        System.out.println("================================");

        if (results.isEmpty()) {
            System.out.println("No symbols found with breakout age in the requested window.");
        } else {
            for (AlreadyBreakoutResult result : results) {
                System.out.println(result.toConsoleLine());
            }
        }

        ResultExporter.exportAlreadyBreakoutResults(results, options.exportFormat, options.outPrefix);
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

    private static void runFollowThrough() {
        // TODO: Wire up FollowThroughDetector with CLI options.
        // FollowThroughDetector requires a BreakoutEvaluator and VcpDetector to scan for
        // past breakouts + pullback recovery patterns. This mode is ready for integration—
        // it just needs CLI plumbing for symbol list and data provider.
        System.out.println("Follow-through mode: Use 'combined' mode which includes follow-through scanning.");
        System.out.println("Or integrate FollowThroughDetector directly into your scan workflow.");
    }

    /**
     * Combined mode: runs scan + watchlist in a SINGLE JVM instance.
     * Outputs scan results first (BREAKOUT/NEAR_BREAKOUT lines), then watchlist lines.
     * This is called by Python's scan_combined_batch() to halve JVM launch overhead.
     */
    private static void runCombined(CliOptions options, ScannerEngine scannerEngine) {
        // --- SCAN pass ---
        List<ScanResult> scanResults = scannerEngine.scan(options.symbols, options.lookbackDays, options.timeframe);
        for (ScanResult result : scanResults) {
            System.out.println(result.toConsoleLine());
        }

        // --- WATCHLIST pass ---
        List<WatchlistResult> watchResults = scannerEngine.scanWatchlist(options.symbols, options.lookbackDays, options.timeframe);
        for (WatchlistResult result : watchResults) {
            System.out.println(result.toConsoleLine());
        }
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