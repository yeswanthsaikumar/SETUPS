import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Structured data export system for JSON/CSV output.
 * 
 * Exports:
 * 1. Scan Results (hits) - Complete signal data
 * 2. Watchlist Items - Pre-breakout opportunities
 * 3. Rejection Log - Why signals were skipped
 * 4. Scan Metadata - Execution details, data quality summary
 * 
 * Format: JSON (primary) or CSV (secondary)
 */
public class StructuredExporter {
    
    private static final DateTimeFormatter TIMESTAMP_FMT = 
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");
    
    /**
     * Complete export of a scan execution.
     */
    public static class ScanExportData {
        public ScanMetadata metadata;
        public List<SignalExport> hits;           // Breakout signals
        public List<WatchlistExport> watchlist;   // Pre-breakout entries
        public List<RejectionExport> rejections;  // Why signals rejected
        public DataQualitySummary dataQuality;    // Data quality report
        
        public ScanExportData() {
            this.metadata = new ScanMetadata();
            this.hits = new ArrayList<>();
            this.watchlist = new ArrayList<>();
            this.rejections = new ArrayList<>();
            this.dataQuality = new DataQualitySummary();
        }
    }
    
    /**
     * Scan execution metadata.
     */
    public static class ScanMetadata {
        public String timestamp;
        public String mode;                  // scan / watchlist / backtest
        public String timeframe;             // daily / weekly
        public int lookbackDays;
        public String setupFilter;           // both / vcp / range_expansion
        public List<String> symbols;
        public int totalSymbolsProcessed;
        public long executionTimeMs;
        public String version;
        
        public ScanMetadata() {
            this.timestamp = LocalDateTime.now().format(TIMESTAMP_FMT);
            this.symbols = new ArrayList<>();
            this.version = "1.0";
        }
    }
    
    /**
     * Single breakout hit/signal.
     */
    public static class SignalExport {
        public String symbol;
        public String signalType;            // BREAKOUT / NEAR_BREAKOUT
        public double baseQualityScore;      // VCP setup score
        public double alignmentBonus;        // Multi-timeframe bonus
        public double finalScore;            // Base + alignment + quality
        public String breakoutQualityRating; // EXCELLENT/STRONG/GOOD/FAIR/WEAK
        public double breakoutQualityScore;  // 0-40 pts
        
        public SetupDetails setup;
        public BreakoutDetails breakout;
        public TradePlanDetails tradePlan;
        public DataQualityIssues dataQuality;
    }
    
    public static class SetupDetails {
        public String type;              // VCP / RANGE_EXPANSION
        public String windowLabel;
        public int windowBars;
        public double rangeHeightPct;
        public double contractionDepthPct;
        public double rangeContraction;
        public double volumeContraction;
        public double rangeExpansion;
        public String setupRating;
    }
    
    public static class BreakoutDetails {
        public double pivotPrice;
        public double closePrice;
        public double entryPrice;
        public double closeToPivotDistancePct;
        public int pivotTestCount;
        public String multiTimeframeAlignment;
        public double weeklyAlignmentBonus;
        public String weeklyStructure;      // breakout/near-breakout/base/none
    }
    
    public static class TradePlanDetails {
        public double entryPrice;
        public double stopLoss;
        public long shares;
        public double target1;
        public double target2;
        public double target3;
        public double riskReward1;          // R-multiple to T1
        public double riskReward2;          // R-multiple to T2
        public double riskReward3;          // R-multiple to T3
    }
    
    public static class DataQualityIssues {
        public List<String> errors;         // Critical issues
        public List<String> warnings;       // Non-critical issues
        public boolean isClean;
    }
    
    /**
     * Watchlist item (pre-breakout).
     */
    public static class WatchlistExport {
        public String symbol;
        public double baseQualityScore;
        public double alignmentBonus;
        public double finalScore;
        public String breakoutQualityRating;
        public double breakoutQualityScore;
        
        public SetupDetails setup;
        public WatchlistDetails watchlist;
        public TradePlanDetails tradePlan;
        public DataQualityIssues dataQuality;
    }
    
    public static class WatchlistDetails {
        public double pivotPrice;
        public double currentPrice;
        public double distanceToPivotPct;
        public double distanceEfficiencyScore;
        public String multiTimeframeAlignment;
        public double alignmentBonus;
    }
    
    /**
     * Rejection reason log.
     */
    public static class RejectionExport {
        public String symbol;
        public String rejectionReason;      // Why signal was skipped
        public String rejectionType;        // FAILED_QUALITY / NO_BREAKOUT / DATA_ERROR / etc.
        public double detailedScore;        // What score was (if applicable)
        public String details;
    }
    
    /**
     * Data quality summary across all symbols.
     */
    public static class DataQualitySummary {
        public int totalSymbolsScanned;
        public int cleanData;
        public int dataWithWarnings;
        public int failedDueToDataError;
        public List<DataQualityIssueCount> issueCounts;
        
        public DataQualitySummary() {
            this.issueCounts = new ArrayList<>();
        }
    }
    
    public static class DataQualityIssueCount {
        public String issueType;
        public int count;
        
        public DataQualityIssueCount(String type, int count) {
            this.issueType = type;
            this.count = count;
        }
    }
    
    /**
     * Export scan data as JSON.
     */
    public static String exportAsJson(ScanExportData data) {
        // Simple JSON builder (in production, use JSON library)
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"metadata\": ").append(metadataToJson(data.metadata)).append(",\n");
        sb.append("  \"hits\": ").append(signalsToJson(data.hits)).append(",\n");
        sb.append("  \"watchlist\": ").append(watchlistToJson(data.watchlist)).append(",\n");
        sb.append("  \"rejections\": ").append(rejectionsToJson(data.rejections)).append(",\n");
        sb.append("  \"dataQuality\": ").append(dataQualityToJson(data.dataQuality)).append("\n");
        sb.append("}");
        return sb.toString();
    }
    
    private static String metadataToJson(ScanMetadata m) {
        return String.format(
            "{\"timestamp\":\"%s\",\"mode\":\"%s\",\"timeframe\":\"%s\"," +
            "\"lookbackDays\":%d,\"setupFilter\":\"%s\",\"totalSymbols\":%d," +
            "\"executionTimeMs\":%d,\"version\":\"%s\"}",
            m.timestamp, m.mode, m.timeframe, m.lookbackDays, m.setupFilter,
            m.totalSymbolsProcessed, m.executionTimeMs, m.version
        );
    }
    
    private static String signalsToJson(List<SignalExport> signals) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < signals.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append(signalToJson(signals.get(i)));
        }
        sb.append("]");
        return sb.toString();
    }
    
    private static String signalToJson(SignalExport s) {
        String qualityRating = s.breakoutQualityRating != null ? s.breakoutQualityRating : "";
        return String.format(
            "{\"symbol\":\"%s\",\"signalType\":\"%s\",\"baseScore\":%.1f," +
            "\"alignmentBonus\":%.1f,\"finalScore\":%.1f," +
            "\"qualityRating\":\"%s\",\"qualityScore\":%.1f}",
            s.symbol != null ? s.symbol : "",
            s.signalType != null ? s.signalType : "",
            s.baseQualityScore, s.alignmentBonus,
            s.finalScore, qualityRating, s.breakoutQualityScore
        );
    }
    
    private static String watchlistToJson(List<WatchlistExport> items) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) sb.append(",");
            WatchlistExport w = items.get(i);
            sb.append(String.format(
                "{\"symbol\":\"%s\",\"baseScore\":%.1f,\"alignmentBonus\":%.1f," +
                "\"finalScore\":%.1f,\"qualityRating\":\"%s\"}",
                w.symbol != null ? w.symbol : "",
                w.baseQualityScore, w.alignmentBonus,
                w.finalScore, w.breakoutQualityRating != null ? w.breakoutQualityRating : ""
            ));
        }
        sb.append("]");
        return sb.toString();
    }
    
    private static String rejectionsToJson(List<RejectionExport> rejections) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < rejections.size(); i++) {
            if (i > 0) sb.append(",");
            RejectionExport r = rejections.get(i);
            sb.append(String.format(
                "{\"symbol\":\"%s\",\"reason\":\"%s\",\"type\":\"%s\"}",
                r.symbol != null ? r.symbol : "",
                escapeJson(r.rejectionReason),
                r.rejectionType != null ? r.rejectionType : ""
            ));
        }
        sb.append("]");
        return sb.toString();
    }
    
    private static String dataQualityToJson(DataQualitySummary dq) {
        return String.format(
            "{\"totalScanned\":%d,\"clean\":%d,\"warnings\":%d,\"errors\":%d}",
            dq.totalSymbolsScanned, dq.cleanData, dq.dataWithWarnings, dq.failedDueToDataError
        );
    }
    
    /**
     * Export scan data as CSV (3 separate files).
     */
    public static Map<String, String> exportAsCsv(ScanExportData data) {
        Map<String, String> csvFiles = new HashMap<>();
        
        csvFiles.put("hits.csv", exportHitsAsCsv(data.hits));
        csvFiles.put("watchlist.csv", exportWatchlistAsCsv(data.watchlist));
        csvFiles.put("rejections.csv", exportRejectionsAsCsv(data.rejections));
        csvFiles.put("metadata.csv", exportMetadataAsCsv(data.metadata));
        
        return csvFiles;
    }
    
    private static String exportHitsAsCsv(List<SignalExport> signals) {
        StringBuilder sb = new StringBuilder();
        sb.append("symbol,signalType,baseScore,alignmentBonus,finalScore,qualityRating,qualityScore\n");
        
        for (SignalExport s : signals) {
            sb.append(String.format("%s,%s,%.2f,%.2f,%.2f,%s,%.1f\n",
                s.symbol, s.signalType, s.baseQualityScore, s.alignmentBonus,
                s.finalScore, s.breakoutQualityRating, s.breakoutQualityScore
            ));
        }
        
        return sb.toString();
    }
    
    private static String exportWatchlistAsCsv(List<WatchlistExport> items) {
        StringBuilder sb = new StringBuilder();
        sb.append("symbol,baseScore,alignmentBonus,finalScore,qualityRating,qualityScore\n");
        
        for (WatchlistExport w : items) {
            sb.append(String.format("%s,%.2f,%.2f,%.2f,%s,%.1f\n",
                w.symbol, w.baseQualityScore, w.alignmentBonus,
                w.finalScore, w.breakoutQualityRating, w.breakoutQualityScore
            ));
        }
        
        return sb.toString();
    }
    
    private static String exportRejectionsAsCsv(List<RejectionExport> rejections) {
        StringBuilder sb = new StringBuilder();
        sb.append("symbol,rejectionType,reason\n");
        
        for (RejectionExport r : rejections) {
            sb.append(String.format("%s,%s,\"%s\"\n",
                r.symbol, r.rejectionType, escapeQuotes(r.rejectionReason)
            ));
        }
        
        return sb.toString();
    }
    
    private static String exportMetadataAsCsv(ScanMetadata m) {
        StringBuilder sb = new StringBuilder();
        sb.append("key,value\n");
        sb.append(String.format("timestamp,%s\n", m.timestamp));
        sb.append(String.format("mode,%s\n", m.mode));
        sb.append(String.format("timeframe,%s\n", m.timeframe));
        sb.append(String.format("lookbackDays,%d\n", m.lookbackDays));
        sb.append(String.format("setupFilter,%s\n", m.setupFilter));
        sb.append(String.format("totalSymbols,%d\n", m.totalSymbolsProcessed));
        sb.append(String.format("executionTimeMs,%d\n", m.executionTimeMs));
        return sb.toString();
    }
    
    /**
     * Write exported data to files.
     */
    public static void writeExports(String outputDir, String prefix, ScanExportData data, String format) 
            throws IOException {
        Path outPath = Paths.get(outputDir);
        Files.createDirectories(outPath);
        
        boolean writeJson = "json".equalsIgnoreCase(format) || "both".equalsIgnoreCase(format);
        boolean writeCsv  = "csv".equalsIgnoreCase(format) || "both".equalsIgnoreCase(format);

        if (writeJson) {
            String jsonContent = exportAsJson(data);
            Files.write(outPath.resolve(prefix + "_scan.json"), jsonContent.getBytes());
        }
        if (writeCsv) {
            Map<String, String> csvFiles = exportAsCsv(data);
            for (Map.Entry<String, String> entry : csvFiles.entrySet()) {
                Files.write(outPath.resolve(prefix + "_" + entry.getKey()), 
                    entry.getValue().getBytes());
            }
        }
    }
    
    // Helper methods
    private static String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
    
    private static String escapeQuotes(String s) {
        if (s == null) return "";
        return s.replace("\"", "\"\"");
    }
}

