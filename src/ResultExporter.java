import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public final class ResultExporter {
    private ResultExporter() {
    }

    public static void exportScanResults(List<ScanResult> results, String format, String outPrefix) {
        if ("none".equals(format)) {
            return;
        }
        if ("csv".equals(format) || "both".equals(format)) {
            writeScanCsv(results, Paths.get(outPrefix + "_scan.csv"));
        }
        if ("json".equals(format) || "both".equals(format)) {
            writeScanJson(results, Paths.get(outPrefix + "_scan.json"));
        }
    }

    public static void exportBacktestReport(BacktestReport report, String format, String outPrefix) {
        if ("none".equals(format)) {
            return;
        }
        if ("csv".equals(format) || "both".equals(format)) {
            writeBacktestCsv(report, Paths.get(outPrefix + "_backtest.csv"));
        }
        if ("json".equals(format) || "both".equals(format)) {
            writeBacktestJson(report, Paths.get(outPrefix + "_backtest.json"));
        }
    }

    public static void exportWatchlistResults(List<WatchlistResult> results, String format, String outPrefix) {
        if ("none".equals(format)) {
            return;
        }
        if ("csv".equals(format) || "both".equals(format)) {
            writeWatchlistCsv(results, Paths.get(outPrefix + "_watchlist.csv"));
        }
        if ("json".equals(format) || "both".equals(format)) {
            writeWatchlistJson(results, Paths.get(outPrefix + "_watchlist.json"));
        }
    }

    private static void writeScanCsv(List<ScanResult> results, Path path) {
        List<String> lines = new ArrayList<>();
        lines.add("symbol,setupType,windowLabel,windowBars,baseRangeHeightPct,contractionDepthPct,rangeContractionCount,volumeContractionCount,contractionPairs,setupRating,date,close,pivot,support,qualityScore,rangeContractionPct,volumeContractionPct,rangeExpansion,entry,stop,shares,target1,target2,target3");
        for (ScanResult r : results) {
            lines.add(String.format(
                    "%s,%s,%s,%d,%.2f,%.2f,%d,%d,%d,%s,%s,%.5f,%.5f,%.5f,%.2f,%.2f,%.2f,%.2f,%.5f,%.5f,%d,%.5f,%.5f,%.5f",
                    r.getSymbol(),
                    r.getSetup().getSetupType(),
                    r.getSetup().getBaseWindowLabel(),
                    r.getSetup().getBaseWindowBars(),
                    r.getSetup().getBaseRangeHeightPct(),
                    r.getSetup().getContractionDepthPct(),
                    r.getSetup().getRangeContractionCount(),
                    r.getSetup().getVolumeContractionCount(),
                    r.getSetup().getContractionPairs(),
                    r.getSetup().getSetupRating(),
                    r.getSignalCandle().getDate(),
                    r.getSignalCandle().getClose(),
                    r.getSetup().getPivotPrice(),
                    r.getSetup().getSupportPrice(),
                    r.getSetup().getQualityScore(),
                    r.getSetup().getRangeContraction() * 100.0,
                    r.getSetup().getVolumeContraction() * 100.0,
                    r.getSetup().getRangeExpansion(),
                    r.getTradePlan().getEntry(),
                    r.getTradePlan().getStopLoss(),
                    r.getTradePlan().getShares(),
                    r.getTradePlan().getTarget1(),
                    r.getTradePlan().getTarget2(),
                    r.getTradePlan().getTarget3()
            ));
        }
        writeLines(path, lines);
    }

    private static void writeScanJson(List<ScanResult> results, Path path) {
        StringBuilder sb = new StringBuilder();
        sb.append("[\n");
        for (int i = 0; i < results.size(); i++) {
            ScanResult r = results.get(i);
            sb.append("  {\n");
            sb.append("    \"symbol\": \"").append(escape(r.getSymbol())).append("\",\n");
            sb.append("    \"setupType\": \"").append(r.getSetup().getSetupType()).append("\",\n");
            sb.append("    \"windowLabel\": \"").append(r.getSetup().getBaseWindowLabel()).append("\",\n");
            sb.append("    \"windowBars\": ").append(r.getSetup().getBaseWindowBars()).append(",\n");
            sb.append("    \"baseRangeHeightPct\": ").append(format(r.getSetup().getBaseRangeHeightPct())).append(",\n");
            sb.append("    \"contractionDepthPct\": ").append(format(r.getSetup().getContractionDepthPct())).append(",\n");
            sb.append("    \"rangeContractionCount\": ").append(r.getSetup().getRangeContractionCount()).append(",\n");
            sb.append("    \"volumeContractionCount\": ").append(r.getSetup().getVolumeContractionCount()).append(",\n");
            sb.append("    \"contractionPairs\": ").append(r.getSetup().getContractionPairs()).append(",\n");
            sb.append("    \"setupRating\": \"").append(r.getSetup().getSetupRating()).append("\",\n");
            sb.append("    \"date\": \"").append(r.getSignalCandle().getDate()).append("\",\n");
            sb.append("    \"close\": ").append(format(r.getSignalCandle().getClose())).append(",\n");
            sb.append("    \"pivot\": ").append(format(r.getSetup().getPivotPrice())).append(",\n");
            sb.append("    \"support\": ").append(format(r.getSetup().getSupportPrice())).append(",\n");
            sb.append("    \"qualityScore\": ").append(format(r.getSetup().getQualityScore())).append(",\n");
            sb.append("    \"rangeContractionPct\": ").append(format(r.getSetup().getRangeContraction() * 100.0)).append(",\n");
            sb.append("    \"volumeContractionPct\": ").append(format(r.getSetup().getVolumeContraction() * 100.0)).append(",\n");
            sb.append("    \"rangeExpansion\": ").append(format(r.getSetup().getRangeExpansion())).append(",\n");
            sb.append("    \"entry\": ").append(format(r.getTradePlan().getEntry())).append(",\n");
            sb.append("    \"stop\": ").append(format(r.getTradePlan().getStopLoss())).append(",\n");
            sb.append("    \"shares\": ").append(r.getTradePlan().getShares()).append(",\n");
            sb.append("    \"target1\": ").append(format(r.getTradePlan().getTarget1())).append(",\n");
            sb.append("    \"target2\": ").append(format(r.getTradePlan().getTarget2())).append(",\n");
            sb.append("    \"target3\": ").append(format(r.getTradePlan().getTarget3())).append("\n");
            sb.append("  }");
            if (i < results.size() - 1) {
                sb.append(",");
            }
            sb.append("\n");
        }
        sb.append("]\n");
        writeLines(path, List.of(sb.toString()));
    }

    private static void writeBacktestCsv(BacktestReport report, Path path) {
        List<String> lines = new ArrayList<>();
        lines.add("symbol,entryDate,exitDate,entryPrice,exitPrice,stopPrice,shares,rMultiple,pnl,exitReason");
        for (BacktestTrade t : report.getTrades()) {
            lines.add(String.format(
                    "%s,%s,%s,%.5f,%.5f,%.5f,%d,%.4f,%.2f,%s",
                    t.getSymbol(),
                    t.getEntryDate(),
                    t.getExitDate(),
                    t.getEntryPrice(),
                    t.getExitPrice(),
                    t.getStopPrice(),
                    t.getShares(),
                    t.getRMultiple(),
                    t.getPnl(),
                    t.getExitReason()
            ));
        }
        writeLines(path, lines);
    }

    private static void writeBacktestJson(BacktestReport report, Path path) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"signals\": ").append(report.getSignals()).append(",\n");
        sb.append("  \"trades\": ").append(report.getTradeCount()).append(",\n");
        sb.append("  \"winRate\": ").append(format(report.getWinRate())).append(",\n");
        sb.append("  \"averageR\": ").append(format(report.getAverageR())).append(",\n");
        sb.append("  \"totalR\": ").append(format(report.getTotalR())).append(",\n");
        sb.append("  \"totalPnl\": ").append(format(report.getTotalPnl())).append(",\n");
        sb.append("  \"items\": [\n");

        List<BacktestTrade> trades = report.getTrades();
        for (int i = 0; i < trades.size(); i++) {
            BacktestTrade t = trades.get(i);
            sb.append("    {\n");
            sb.append("      \"symbol\": \"").append(escape(t.getSymbol())).append("\",\n");
            sb.append("      \"entryDate\": \"").append(t.getEntryDate()).append("\",\n");
            sb.append("      \"exitDate\": \"").append(t.getExitDate()).append("\",\n");
            sb.append("      \"entryPrice\": ").append(format(t.getEntryPrice())).append(",\n");
            sb.append("      \"exitPrice\": ").append(format(t.getExitPrice())).append(",\n");
            sb.append("      \"stopPrice\": ").append(format(t.getStopPrice())).append(",\n");
            sb.append("      \"shares\": ").append(t.getShares()).append(",\n");
            sb.append("      \"rMultiple\": ").append(format(t.getRMultiple())).append(",\n");
            sb.append("      \"pnl\": ").append(format(t.getPnl())).append(",\n");
            sb.append("      \"exitReason\": \"").append(escape(t.getExitReason())).append("\"\n");
            sb.append("    }");
            if (i < trades.size() - 1) {
                sb.append(",");
            }
            sb.append("\n");
        }

        sb.append("  ]\n");
        sb.append("}\n");
        writeLines(path, List.of(sb.toString()));
    }

    private static void writeWatchlistCsv(List<WatchlistResult> results, Path path) {
        List<String> lines = new ArrayList<>();
        lines.add("symbol,setupType,windowLabel,windowBars,distanceToPivotPct,baseRangeHeightPct,contractionDepthPct,rangeContractionCount,volumeContractionCount,contractionPairs,setupRating,date,close,pivot,support,qualityScore,rangeContractionPct,volumeContractionPct,rangeExpansion,entry,stop,shares,target1,target2,target3");
        for (WatchlistResult r : results) {
            lines.add(String.format(
                    "%s,%s,%s,%d,%.2f,%.2f,%.2f,%d,%d,%d,%s,%s,%.5f,%.5f,%.5f,%.2f,%.2f,%.2f,%.2f,%.5f,%.5f,%d,%.5f,%.5f,%.5f",
                    r.getSymbol(),
                    r.getSetup().getSetupType(),
                    r.getSetup().getBaseWindowLabel(),
                    r.getSetup().getBaseWindowBars(),
                    r.getDistanceToPivotPct() * 100.0,
                    r.getSetup().getBaseRangeHeightPct(),
                    r.getSetup().getContractionDepthPct(),
                    r.getSetup().getRangeContractionCount(),
                    r.getSetup().getVolumeContractionCount(),
                    r.getSetup().getContractionPairs(),
                    r.getSetup().getSetupRating(),
                    r.getSignalCandle().getDate(),
                    r.getSignalCandle().getClose(),
                    r.getSetup().getPivotPrice(),
                    r.getSetup().getSupportPrice(),
                    r.getSetup().getQualityScore(),
                    r.getSetup().getRangeContraction() * 100.0,
                    r.getSetup().getVolumeContraction() * 100.0,
                    r.getSetup().getRangeExpansion(),
                    r.getTradePlan().getEntry(),
                    r.getTradePlan().getStopLoss(),
                    r.getTradePlan().getShares(),
                    r.getTradePlan().getTarget1(),
                    r.getTradePlan().getTarget2(),
                    r.getTradePlan().getTarget3()
            ));
        }
        writeLines(path, lines);
    }

    private static void writeWatchlistJson(List<WatchlistResult> results, Path path) {
        StringBuilder sb = new StringBuilder();
        sb.append("[\n");
        for (int i = 0; i < results.size(); i++) {
            WatchlistResult r = results.get(i);
            sb.append("  {\n");
            sb.append("    \"symbol\": \"").append(escape(r.getSymbol())).append("\",\n");
            sb.append("    \"setupType\": \"").append(r.getSetup().getSetupType()).append("\",\n");
            sb.append("    \"windowLabel\": \"").append(r.getSetup().getBaseWindowLabel()).append("\",\n");
            sb.append("    \"windowBars\": ").append(r.getSetup().getBaseWindowBars()).append(",\n");
            sb.append("    \"distanceToPivotPct\": ").append(format(r.getDistanceToPivotPct() * 100.0)).append(",\n");
            sb.append("    \"baseRangeHeightPct\": ").append(format(r.getSetup().getBaseRangeHeightPct())).append(",\n");
            sb.append("    \"contractionDepthPct\": ").append(format(r.getSetup().getContractionDepthPct())).append(",\n");
            sb.append("    \"rangeContractionCount\": ").append(r.getSetup().getRangeContractionCount()).append(",\n");
            sb.append("    \"volumeContractionCount\": ").append(r.getSetup().getVolumeContractionCount()).append(",\n");
            sb.append("    \"contractionPairs\": ").append(r.getSetup().getContractionPairs()).append(",\n");
            sb.append("    \"setupRating\": \"").append(r.getSetup().getSetupRating()).append("\",\n");
            sb.append("    \"date\": \"").append(r.getSignalCandle().getDate()).append("\",\n");
            sb.append("    \"close\": ").append(format(r.getSignalCandle().getClose())).append(",\n");
            sb.append("    \"pivot\": ").append(format(r.getSetup().getPivotPrice())).append(",\n");
            sb.append("    \"support\": ").append(format(r.getSetup().getSupportPrice())).append(",\n");
            sb.append("    \"qualityScore\": ").append(format(r.getSetup().getQualityScore())).append(",\n");
            sb.append("    \"entry\": ").append(format(r.getTradePlan().getEntry())).append(",\n");
            sb.append("    \"stop\": ").append(format(r.getTradePlan().getStopLoss())).append(",\n");
            sb.append("    \"shares\": ").append(r.getTradePlan().getShares()).append(",\n");
            sb.append("    \"target1\": ").append(format(r.getTradePlan().getTarget1())).append(",\n");
            sb.append("    \"target2\": ").append(format(r.getTradePlan().getTarget2())).append(",\n");
            sb.append("    \"target3\": ").append(format(r.getTradePlan().getTarget3())).append("\n");
            sb.append("  }");
            if (i < results.size() - 1) {
                sb.append(",");
            }
            sb.append("\n");
        }
        sb.append("]\n");
        writeLines(path, List.of(sb.toString()));
    }

    private static void writeLines(Path path, List<String> lines) {
        try {
            if (path.getParent() != null) {
                Files.createDirectories(path.getParent());
            }
            Files.write(path, lines);
            System.out.println("Exported: " + path.toAbsolutePath());
        } catch (IOException ex) {
            System.err.println("Export failed for " + path + ": " + ex.getMessage());
        }
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String format(double value) {
        return String.format("%.5f", value);
    }
}

