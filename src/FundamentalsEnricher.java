import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;

/**
 * FundamentalsEnricher - Optional Java integration for fetching and caching fundamentals data.
 * 
 * This class provides methods to:
 * - Read cached fundamentals from JSON files
 * - Return formatted fundamentals for display
 * - Integrate with ScanResult for enrichment
 * 
 * In production, this would integrate with FundamentalsProvider.py for data fetching.
 * For now, it provides read-only access to pre-cached data.
 */
public final class FundamentalsEnricher {
    private FundamentalsEnricher() {
    }

    private static final String CACHE_DIR = "cache";

    /**
     * Represents fundamental data for a stock.
     */
    public static class Fundamentals {
        public final String symbol;
        public final Double marketCapB;  // Market cap in billions
        public final Double peRatio;
        public final Double forwardPE;
        public final String sector;
        public final String industry;
        public final Double dividendYield;
        public final String currency;
        public final String error;

        public Fundamentals(String symbol, Double marketCapB, Double peRatio, Double forwardPE,
                           String sector, String industry, Double dividendYield, String currency, String error) {
            this.symbol = symbol;
            this.marketCapB = marketCapB;
            this.peRatio = peRatio;
            this.forwardPE = forwardPE;
            this.sector = sector;
            this.industry = industry;
            this.dividendYield = dividendYield;
            this.currency = currency;
            this.error = error;
        }

        @Override
        public String toString() {
            if (error != null) {
                return "N/A";
            }
            StringBuilder sb = new StringBuilder();
            if (sector != null) {
                sb.append(sector);
            }
            if (marketCapB != null) {
                if (sb.length() > 0) sb.append(" | ");
                sb.append(String.format("$%.1fB", marketCapB));
            }
            if (peRatio != null) {
                if (sb.length() > 0) sb.append(" | ");
                sb.append(String.format("PE:%.1f", peRatio));
            }
            if (dividendYield != null) {
                if (sb.length() > 0) sb.append(" | ");
                sb.append(String.format("Div:%.2f%%", dividendYield));
            }
            return sb.length() > 0 ? sb.toString() : "N/A";
        }
    }

    /**
     * Parse a simple JSON string for fundamentals data.
     * Uses basic string parsing to avoid external dependencies.
     */
    private static Fundamentals parseJsonSimple(String jsonStr) {
        try {
            // Extract fields using simple string parsing
            Double marketCapB = extractDoubleField(jsonStr, "market_cap_b");
            Double peRatio = extractDoubleField(jsonStr, "pe_ratio");
            Double forwardPE = extractDoubleField(jsonStr, "forward_pe");
            String sector = extractStringField(jsonStr, "sector");
            String industry = extractStringField(jsonStr, "industry");
            Double dividendYield = extractDoubleField(jsonStr, "dividend_yield");
            String currency = extractStringField(jsonStr, "currency");
            String symbol = extractStringField(jsonStr, "symbol");
            String error = extractStringField(jsonStr, "error");

            return new Fundamentals(symbol, marketCapB, peRatio, forwardPE, sector, industry, dividendYield, currency, error);
        } catch (Exception e) {
            return null;
        }
    }

    private static String extractStringField(String json, String fieldName) {
        String pattern = "\"" + fieldName + "\":\"";
        int idx = json.indexOf(pattern);
        if (idx == -1) return null;
        int start = idx + pattern.length();
        int end = json.indexOf("\"", start);
        if (end == -1) return null;
        return json.substring(start, end);
    }

    private static Double extractDoubleField(String json, String fieldName) {
        String pattern = "\"" + fieldName + "\":";
        int idx = json.indexOf(pattern);
        if (idx == -1) return null;
        int start = idx + pattern.length();
        int end = start;
        while (end < json.length() && (Character.isDigit(json.charAt(end)) || json.charAt(end) == '.')) {
            end++;
        }
        if (end == start) return null;
        try {
            return Double.parseDouble(json.substring(start, end));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /**
     * Load fundamentals from cached JSON file.
     */
    public static Fundamentals loadFundamentals(String symbol) {
        try {
            Path cachePath = Paths.get(CACHE_DIR, "fundamentals_" + symbol + ".json");
            if (!Files.exists(cachePath)) {
                return null;
            }
            String jsonStr = new String(Files.readAllBytes(cachePath));
            return parseJsonSimple(jsonStr);
        } catch (IOException e) {
            return null;
        }
    }

    /**
     * Get a map of fundamentals for multiple symbols.
     */
    public static Map<String, Fundamentals> loadFundamentalsBatch(String... symbols) {
        Map<String, Fundamentals> result = new HashMap<>();
        for (String symbol : symbols) {
            Fundamentals fund = loadFundamentals(symbol);
            if (fund != null) {
                result.put(symbol, fund);
            }
        }
        return result;
    }
}

