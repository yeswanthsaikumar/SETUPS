import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class YahooFinanceProvider implements MarketDataProvider {
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ISO_LOCAL_DATE;
    private static final Pattern ARRAY_PATTERN_TEMPLATE = Pattern.compile("\"%s\"\\s*:\\s*\\[(.*?)]", Pattern.DOTALL);

    private final HttpClient httpClient;
    private final int retries;
    private final Path cacheDir;
    private final Duration cacheTtl;

    public YahooFinanceProvider(int retries, Path cacheDir, Duration cacheTtl) {
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
        this.retries = Math.max(1, retries);
        this.cacheDir = cacheDir;
        this.cacheTtl = cacheTtl;
    }

    @Override
    public List<Candle> getDailyCandles(String symbol, int lookbackDays) {
        try {
            Files.createDirectories(cacheDir);
        } catch (IOException ignored) {
            // Best-effort cache directory creation; fetch can still proceed.
        }

        // 1. Exact-size fresh cache hit (fastest path)
        Path cacheFile = cacheDir.resolve(symbol.toUpperCase() + "_" + lookbackDays + ".csv");
        List<Candle> cachedFresh = readCache(cacheFile, true);
        if (!cachedFresh.isEmpty()) {
            return cachedFresh;
        }

        // 2. Any existing cache file with enough bars (avoids unnecessary network round-trips)
        //    Prefer the smallest adequate file to keep I/O minimal.
        List<Candle> existing = readBestExistingCache(symbol, lookbackDays);
        if (!existing.isEmpty()) {
            return existing;
        }

        // 3. Network fetch (only when no usable cache exists at all)
        Exception lastError = null;
        for (int attempt = 1; attempt <= retries; attempt++) {
            try {
                List<Candle> fetched = fetchFromYahoo(symbol, lookbackDays);
                if (!fetched.isEmpty()) {
                    writeCache(cacheFile, fetched);
                    return fetched;
                }
            } catch (Exception ex) {
                lastError = ex;
                sleepQuietly((long) attempt * 400L);
            }
        }

        // 4. Stale exact-size cache as last resort
        List<Candle> stale = readCache(cacheFile, false);
        if (!stale.isEmpty()) {
            return stale;
        }

        throw new RuntimeException("Failed to fetch Yahoo data for symbol: " + symbol, lastError);
    }

    /**
     * Scan the cache directory for any file matching {@code SYMBOL_N.csv}.
     * Return the last {@code lookbackDays} candles from the smallest file that has enough bars,
     * falling back to the largest available file if none meet the minimum.
     */
    private List<Candle> readBestExistingCache(String symbol, int lookbackDays) {
        String prefix = symbol.toUpperCase() + "_";
        List<Path> candidates = new ArrayList<>();
        try (var stream = Files.list(cacheDir)) {
            stream.filter(p -> {
                String name = p.getFileName().toString();
                return name.startsWith(prefix) && name.endsWith(".csv");
            }).forEach(candidates::add);
        } catch (IOException ignored) {
            return List.of();
        }
        if (candidates.isEmpty()) {
            return List.of();
        }

        // Sort by the numeric suffix ascending (smallest file first = least I/O)
        candidates.sort(Comparator.comparingInt(p -> {
            String name = p.getFileName().toString();
            String num = name.substring(prefix.length(), name.length() - 4);
            try { return Integer.parseInt(num); } catch (NumberFormatException e) { return Integer.MAX_VALUE; }
        }));

        // Try smallest-adequate first, then fall back to largest
        Path bestLarge = candidates.get(candidates.size() - 1);
        for (Path candidate : candidates) {
            List<Candle> candles = readCache(candidate, false);
            if (candles.size() >= lookbackDays) {
                // Trim to the most recent lookbackDays bars so downstream has a predictable window
                if (candles.size() > lookbackDays) {
                    candles = new ArrayList<>(candles.subList(candles.size() - lookbackDays, candles.size()));
                }
                return candles;
            }
        }

        // No file has enough bars — return all bars from the largest file
        return readCache(bestLarge, false);
    }

    private List<Candle> fetchFromYahoo(String symbol, int lookbackDays) throws IOException, InterruptedException {
        long period2 = Instant.now().getEpochSecond();
        long period1 = Instant.now().minus(Math.max(lookbackDays + 180L, 365L), ChronoUnit.DAYS).getEpochSecond();
        String encoded = URLEncoder.encode(symbol, StandardCharsets.UTF_8);
        String url = "https://query1.finance.yahoo.com/v8/finance/chart/" + encoded
                + "?interval=1d&period1=" + period1
                + "&period2=" + period2
                + "&events=history&includeAdjustedClose=true";

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(15))
                .header("User-Agent", "Mozilla/5.0")
                .GET()
                .build();

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() > 299) {
            throw new IOException("Yahoo API returned status " + response.statusCode());
        }

        List<Candle> candles = parseChartResponse(response.body());
        if (candles.size() > lookbackDays) {
            candles = new ArrayList<>(candles.subList(candles.size() - lookbackDays, candles.size()));
        }
        return candles;
    }

    private List<Candle> parseChartResponse(String json) {
        List<Long> timestamps = parseLongArray(extractArray(json, "timestamp"));
        List<Double> opens = parseDoubleArray(extractArray(json, "open"));
        List<Double> highs = parseDoubleArray(extractArray(json, "high"));
        List<Double> lows = parseDoubleArray(extractArray(json, "low"));
        List<Double> closes = parseDoubleArray(extractArray(json, "close"));
        List<Long> volumes = parseLongArray(extractArray(json, "volume"));

        int n = minSize(timestamps.size(), opens.size(), highs.size(), lows.size(), closes.size(), volumes.size());
        List<Candle> candles = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            long ts = timestamps.get(i);
            double open = opens.get(i);
            double high = highs.get(i);
            double low = lows.get(i);
            double close = closes.get(i);
            long volume = volumes.get(i);

            if (ts <= 0 || Double.isNaN(open) || Double.isNaN(high) || Double.isNaN(low) || Double.isNaN(close) || volume <= 0) {
                continue;
            }

            LocalDate date = Instant.ofEpochSecond(ts).atZone(ZoneId.systemDefault()).toLocalDate();
            candles.add(new Candle(date, open, high, low, close, volume));
        }

        candles.sort(Comparator.comparing(Candle::getDate));
        return candles;
    }

    private List<Candle> readCache(Path cacheFile, boolean requireFresh) {
        if (!Files.exists(cacheFile)) {
            return List.of();
        }

        if (requireFresh) {
            try {
                Instant modified = Files.getLastModifiedTime(cacheFile).toInstant();
                if (modified.isBefore(Instant.now().minus(cacheTtl))) {
                    return List.of();
                }
            } catch (IOException ignored) {
                return List.of();
            }
        }

        try {
            List<String> lines = Files.readAllLines(cacheFile);
            List<Candle> candles = new ArrayList<>();
            for (int i = 1; i < lines.size(); i++) {
                String[] p = lines.get(i).split(",");
                if (p.length < 6) {
                    continue;
                }
                LocalDate date = LocalDate.parse(p[0], DATE_FMT);
                candles.add(new Candle(
                        date,
                        Double.parseDouble(p[1]),
                        Double.parseDouble(p[2]),
                        Double.parseDouble(p[3]),
                        Double.parseDouble(p[4]),
                        Long.parseLong(p[5])
                ));
            }
            return candles;
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private void writeCache(Path cacheFile, List<Candle> candles) {
        List<String> lines = new ArrayList<>();
        lines.add("date,open,high,low,close,volume");
        for (Candle candle : candles) {
            lines.add(String.format(
                    "%s,%.5f,%.5f,%.5f,%.5f,%d",
                    candle.getDate().format(DATE_FMT),
                    candle.getOpen(),
                    candle.getHigh(),
                    candle.getLow(),
                    candle.getClose(),
                    candle.getVolume()
            ));
        }

        try {
            Files.write(cacheFile, lines);
        } catch (IOException ignored) {
            // Cache write failure should not fail the scan flow.
        }
    }

    private String extractArray(String json, String key) {
        Pattern pattern = Pattern.compile(String.format(ARRAY_PATTERN_TEMPLATE.pattern(), Pattern.quote(key)), Pattern.DOTALL);
        Matcher matcher = pattern.matcher(json);
        return matcher.find() ? matcher.group(1) : "";
    }

    private List<Double> parseDoubleArray(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }

        String[] parts = source.split(",");
        List<Double> out = new ArrayList<>(parts.length);
        for (String part : parts) {
            String token = part.trim();
            if ("null".equals(token) || token.isEmpty()) {
                out.add(Double.NaN);
            } else {
                out.add(Double.parseDouble(token));
            }
        }
        return out;
    }

    private List<Long> parseLongArray(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }

        String[] parts = source.split(",");
        List<Long> out = new ArrayList<>(parts.length);
        for (String part : parts) {
            String token = part.trim();
            if ("null".equals(token) || token.isEmpty()) {
                out.add(-1L);
            } else {
                out.add(Long.parseLong(token));
            }
        }
        return out;
    }

    private int minSize(int... values) {
        int min = Integer.MAX_VALUE;
        for (int v : values) {
            min = Math.min(min, v);
        }
        return min == Integer.MAX_VALUE ? 0 : min;
    }

    private void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}

