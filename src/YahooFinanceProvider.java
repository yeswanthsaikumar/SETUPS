import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class YahooFinanceProvider implements MarketDataProvider {
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ISO_LOCAL_DATE;
    private static final Pattern ARRAY_PATTERN_TEMPLATE = Pattern.compile("\"%s\"\\s*:\\s*\\[(.*?)]", Pattern.DOTALL);

    // NSE market context — used for data-date freshness decisions
    private static final ZoneId IST           = ZoneId.of("Asia/Kolkata");
    private static final LocalTime NSE_CLOSE  = LocalTime.of(15, 35); // 3:35 PM IST (5 min buffer after 3:30 close)
    private static final int MAX_DATA_GAP_DAYS = 10; // >10 calendar days = always stale (handles long holiday stretches)

    // Yahoo Finance cookie+crumb authentication (required since ~2024)
    private static volatile String _crumb = null;
    private static volatile long   _crumbExpiry = 0L;
    private static final ReentrantLock _crumbLock = new ReentrantLock();

    // Circuit breaker: after first Yahoo failure, skip retries for 30 minutes to
    // avoid wasting time on blocked/unavailable endpoints during batch scans.
    private static volatile long _yahooBlockedUntil = 0L;
    private static final long CIRCUIT_BREAKER_MS = 30 * 60 * 1000L; // 30 minutes

    private final HttpClient httpClient;
    private final int retries;
    private final Path cacheDir;
    private final Duration cacheTtl; // kept for API compatibility; fallback TTL only

    public YahooFinanceProvider(int retries, Path cacheDir, Duration cacheTtl) {
        CookieManager cm = new CookieManager();
        cm.setCookiePolicy(CookiePolicy.ACCEPT_ALL);
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))   // short connect timeout to fail fast
                .cookieHandler(cm)
                .build();
        this.retries = Math.max(1, retries);
        this.cacheDir = cacheDir;
        this.cacheTtl = cacheTtl;
    }

    /** Returns true if Yahoo Finance is currently in circuit-breaker (blocked) state. */
    private static boolean isYahooBlocked() {
        return System.currentTimeMillis() < _yahooBlockedUntil;
    }

    /** Trip the circuit breaker — Yahoo will be skipped for CIRCUIT_BREAKER_MS. */
    private static void tripCircuitBreaker() {
        _yahooBlockedUntil = System.currentTimeMillis() + CIRCUIT_BREAKER_MS;
    }

    /**
     * Obtain (or reuse cached) Yahoo Finance crumb token.
     * The crumb is cached for 20 minutes. On failure returns null — the caller
     * will attempt the request without a crumb (some regions still work).
     * Uses short timeouts to fail fast when Yahoo is unreachable.
     *
     * NOTE: This method intentionally does NOT trip the circuit breaker on failure.
     * The crumb endpoint failing does not guarantee the v8 chart API is also blocked.
     * Circuit-breaker tripping is handled exclusively in fetchFromYahoo() where the
     * actual data endpoint fails.
     */
    private String getCrumb() {
        long now = System.currentTimeMillis();
        if (_crumb != null && now < _crumbExpiry) return _crumb;
        if (isYahooBlocked()) return null;   // don't waste time when circuit is open

        _crumbLock.lock();
        try {
            if (_crumb != null && System.currentTimeMillis() < _crumbExpiry) return _crumb;
            if (isYahooBlocked()) return null;

            // Step 1: Visit Yahoo Finance homepage to get session cookies (fast timeout)
            try {
                HttpRequest homeReq = HttpRequest.newBuilder(URI.create("https://finance.yahoo.com"))
                        .timeout(Duration.ofSeconds(5))
                        .header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                        .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                        .GET().build();
                httpClient.send(homeReq, HttpResponse.BodyHandlers.discarding());
            } catch (Exception ignored) {}

            // Step 2: Fetch crumb (short timeout) — try both query1 and query2
            for (String crumbUrl : new String[]{
                    "https://query1.finance.yahoo.com/v1/test/getcrumb",
                    "https://query2.finance.yahoo.com/v1/test/getcrumb"
            }) {
                try {
                    HttpRequest crumbReq = HttpRequest.newBuilder(URI.create(crumbUrl))
                            .timeout(Duration.ofSeconds(5))
                            .header("User-Agent", "Mozilla/5.0")
                            .GET().build();
                    HttpResponse<String> resp = httpClient.send(crumbReq, HttpResponse.BodyHandlers.ofString());
                    if (resp.statusCode() == 200 && resp.body() != null && !resp.body().isBlank()) {
                        _crumb = resp.body().trim();
                        _crumbExpiry = System.currentTimeMillis() + 20 * 60 * 1000L; // 20 min
                        return _crumb;
                    }
                } catch (Exception ignored) {}
            }
            // Failed to get crumb — return null, caller will try data fetch without crumb.
            // Do NOT trip the circuit breaker here; only fetchFromYahoo() does that when
            // a network-level failure occurs on the actual data endpoint.
        } finally {
            _crumbLock.unlock();
        }
        return null; // failed to get crumb — caller will try without it
    }

    /**
     * Determines if cached candle data is "current enough" — i.e., no closed trading
     * sessions are missing from the data.
     *
     * Only bars with a valid (non-NaN) close price are considered "complete" data.
     * Bars with NaN close (Yahoo publishes volume before the final close price) are
     * treated as incomplete and skipped — the last VALID bar's date is used instead.
     *
     * Rules (all times in IST):
     *  - 0–1 calendar days gap → always fresh (today or yesterday)
     *  - > MAX_DATA_GAP_DAYS   → always stale
     *  - 2–MAX_DATA_GAP_DAYS:
     *      • Count Mon–Fri days in the gap (ignoring NSE holidays — simpler than full calendar)
     *      • 0 biz-days in gap (pure weekend) → fresh
     *      • ≥2 biz-days in gap             → stale (missed sessions)
     *      • Exactly 1 biz-day (likely today) → stale only if NSE has already closed (≥15:35 IST)
     */
    private boolean isDataCurrentEnough(List<Candle> candles) {
        if (candles == null || candles.isEmpty()) return false;

        // Find the last candle with a VALID (non-NaN) close — bars published by Yahoo
        // immediately after market close may have null/NaN close while volume is already
        // available.  We treat such bars as "incomplete" and don't count them as fresh.
        LocalDate lastValidDate = null;
        for (int i = candles.size() - 1; i >= 0; i--) {
            if (!Double.isNaN(candles.get(i).getClose())) {
                lastValidDate = candles.get(i).getDate();
                break;
            }
        }
        if (lastValidDate == null) return false;

        LocalDate today    = LocalDate.now(IST);
        long daysSince     = ChronoUnit.DAYS.between(lastValidDate, today);

        // Same day — data already current
        if (daysSince <= 0) return true;
        if (daysSince > MAX_DATA_GAP_DAYS) return false;

        long bizDays = 0;
        for (long d = 1; d <= daysSince; d++) {
            DayOfWeek dow = lastValidDate.plusDays(d).getDayOfWeek();
            if (dow != DayOfWeek.SATURDAY && dow != DayOfWeek.SUNDAY) bizDays++;
        }

        if (bizDays == 0) return true;   // only weekends in the gap
        if (bizDays >= 2) return false;  // 2+ missed business days → definitely stale

        // Exactly 1 missed business day (could be today's session):
        // treat as stale only after NSE has closed for the day
        return ZonedDateTime.now(IST).toLocalTime().isBefore(NSE_CLOSE);
    }

    /**
     * Merge newly-fetched bars into existing data: fresh bars overwrite same dates,
     * new dates are appended. Result is sorted chronologically (oldest first, newest last).
     * No trimming — we keep ALL historical data in the unified cache file.
     */
    private List<Candle> mergeAll(List<Candle> existing, List<Candle> fresh) {
        Map<LocalDate, Candle> byDate = new LinkedHashMap<>();
        for (Candle c : existing) byDate.put(c.getDate(), c);
        for (Candle c : fresh)    byDate.put(c.getDate(), c); // fresh overwrites same date
        List<Candle> merged = new ArrayList<>(byDate.values());
        merged.sort(Comparator.comparing(Candle::getDate));
        return merged;
    }

    @Override
    public List<Candle> getDailyCandles(String symbol, int lookbackDays) {
        try {
            Files.createDirectories(cacheDir);
        } catch (IOException ignored) {}

        // Single cache file per symbol — all historical data in one file.
        // New dates are always appended at the end (last row).
        Path cacheFile = cacheDir.resolve(symbol.toUpperCase() + ".csv");

        // 1. Read the single unified cache file.
        List<Candle> cached = readCache(cacheFile, false);
        if (isDataCurrentEnough(cached)) {
            return trimToLookback(cached, lookbackDays);
        }

        // 2. One-time migration: if unified file missing/empty, try to absorb legacy
        //    SYMBOL_N.csv files (largest first) so we don't lose existing data.
        if (cached.isEmpty()) {
            cached = migrateLegacyCacheFiles(symbol);
        }

        // 3. Incremental network fetch — only download bars after the last known date.
        //    New bars are appended at the end of the file (chronological order).
        LocalDate fetchFrom = cached.isEmpty() ? null : cached.get(cached.size() - 1).getDate();

        Exception lastError = null;
        for (int attempt = 1; attempt <= retries; attempt++) {
            try {
                List<Candle> newBars = fetchFromYahoo(symbol, lookbackDays, fetchFrom);
                if (!newBars.isEmpty()) {
                    // Merge: existing data + new bars, dedup by date, sort chronologically.
                    // New dates naturally end up as the last rows.
                    List<Candle> merged = mergeAll(cached, newBars);
                    writeCache(cacheFile, merged);
                    // Clean up legacy files now that unified file is written
                    deleteLegacyCacheFiles(symbol);
                    return trimToLookback(merged, lookbackDays);
                }
                break; // no point retrying if HTTP 200 with empty result
            } catch (Exception ex) {
                lastError = ex;
                sleepQuietly((long) attempt * 400L);
            }
        }

        // 4. Stale fallback — graceful degradation when network fails or data unavailable.
        if (!cached.isEmpty()) {
            // Persist the migrated data even without new bars
            if (!Files.exists(cacheFile)) {
                writeCache(cacheFile, cached);
                deleteLegacyCacheFiles(symbol);
            }
            return trimToLookback(cached, lookbackDays);
        }

        throw new RuntimeException("Failed to fetch Yahoo data for symbol: " + symbol, lastError);
    }


    /** Trim candles list to the most recent lookbackDays entries (in-place safe). */
    private List<Candle> trimToLookback(List<Candle> candles, int lookbackDays) {
        if (candles.size() > lookbackDays) {
            return new ArrayList<>(candles.subList(candles.size() - lookbackDays, candles.size()));
        }
        return candles;
    }

    /**
     * One-time migration: read ALL legacy SYMBOL_N.csv files, merge their data into a
     * single unified list sorted chronologically. This preserves the maximum amount of
     * historical data by combining all lookback variants.
     */
    private List<Candle> migrateLegacyCacheFiles(String symbol) {
        List<Path> legacyFiles = findLegacyCacheFiles(symbol);
        if (legacyFiles.isEmpty()) return List.of();

        Map<LocalDate, Candle> byDate = new LinkedHashMap<>();
        // Largest files first — they have the most data
        for (Path legacyFile : legacyFiles) {
            List<Candle> candles = readCache(legacyFile, false);
            for (Candle c : candles) {
                byDate.putIfAbsent(c.getDate(), c);
            }
        }

        List<Candle> merged = new ArrayList<>(byDate.values());
        merged.sort(Comparator.comparing(Candle::getDate));
        return merged;
    }

    /**
     * Find all legacy cache files matching SYMBOL_N.csv pattern (N is a number).
     * Sorted by N descending (largest lookback first = most data).
     */
    private List<Path> findLegacyCacheFiles(String symbol) {
        String prefix = symbol.toUpperCase() + "_";
        List<Path> candidates = new ArrayList<>();
        try (var stream = Files.list(cacheDir)) {
            stream.filter(p -> {
                String name = p.getFileName().toString();
                if (!name.startsWith(prefix) || !name.endsWith(".csv")) return false;
                String numPart = name.substring(prefix.length(), name.length() - 4);
                try { Integer.parseInt(numPart); return true; }
                catch (NumberFormatException e) { return false; }
            }).forEach(candidates::add);
        } catch (IOException ignored) {
            return List.of();
        }
        candidates.sort(Comparator.<Path, Integer>comparing(p -> {
            String name = p.getFileName().toString();
            String num  = name.substring(prefix.length(), name.length() - 4);
            try { return Integer.parseInt(num); } catch (NumberFormatException e) { return 0; }
        }).reversed());
        return candidates;
    }

    /**
     * Delete all legacy SYMBOL_N.csv files after successful migration to unified SYMBOL.csv.
     */
    private void deleteLegacyCacheFiles(String symbol) {
        List<Path> legacyFiles = findLegacyCacheFiles(symbol);
        for (Path f : legacyFiles) {
            try { Files.deleteIfExists(f); } catch (IOException ignored) {}
        }
    }

    /**
     * Fetch candles from Yahoo Finance.
     *
     * @param fromDate  If non-null, fetch only bars strictly after this date (incremental).
     *                  If null, fetch the full lookback window from scratch.
     */
    private List<Candle> fetchFromYahoo(String symbol, int lookbackDays, LocalDate fromDate) throws IOException, InterruptedException {
        // Circuit breaker: if Yahoo has been failing, return empty (= "no new data")
        // instead of throwing. An empty return causes the caller's retry loop to
        // break immediately (no sleep delays), falling through to the stale-cache
        // fallback.  This avoids 400+800+1200ms sleep × every symbol in the batch.
        if (isYahooBlocked()) {
            return List.of();
        }

        long period2 = Instant.now().getEpochSecond();
        long period1;
        if (fromDate != null) {
            // Incremental: start the day AFTER last cached bar so we get only new sessions.
            period1 = fromDate.plusDays(1).atStartOfDay(IST).toEpochSecond();
        } else {
            // Full fetch: cover lookback + 180-day buffer to account for calendar alignment.
            period1 = Instant.now().minus(Math.max(lookbackDays + 180L, 365L), ChronoUnit.DAYS).getEpochSecond();
        }

        String encoded = URLEncoder.encode(symbol, StandardCharsets.UTF_8);

        // Get crumb (Yahoo Finance cookie+crumb auth required since ~2024)
        String crumb = getCrumb();

        IOException lastError = null;
        for (String baseHost : new String[]{"query1.finance.yahoo.com", "query2.finance.yahoo.com"}) {
            String url = "https://" + baseHost + "/v8/finance/chart/" + encoded
                    + "?interval=1d&period1=" + period1
                    + "&period2=" + period2
                    + "&events=history&includeAdjustedClose=true";
            if (crumb != null && !crumb.isBlank()) {
                url += "&crumb=" + URLEncoder.encode(crumb, StandardCharsets.UTF_8);
            }

            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(8))   // 8s per request — fail fast on slow/blocked Yahoo
                    .header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                    .header("Accept", "application/json")
                    .header("Referer", "https://finance.yahoo.com")
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                int status = response.statusCode();

                if (status == 401) {
                    // Crumb expired — force refresh and retry once
                    _crumbExpiry = 0L;
                    crumb = getCrumb();
                    continue;
                }

                if (status == 429) {
                    // Rate limited — back off and try other host
                    sleepQuietly(2000L);
                    continue;
                }

                if (status < 200 || status > 299) {
                    lastError = new IOException("Yahoo API returned status " + status + " for " + symbol);
                    continue;
                }

                // Return raw parsed bars — caller's mergeAll handles dedup + ordering
                return parseChartResponse(response.body());
            } catch (IOException e) {
                lastError = e;
                // Network-level failure (connection reset, timeout, etc.)
                // Trip the circuit breaker so subsequent symbols in batch scan
                // don't each wait 8s × 2 hosts before falling back to cache.
                tripCircuitBreaker();
                break;
            }
        }

        if (lastError != null) throw lastError;
        throw new IOException("All Yahoo Finance endpoints failed for symbol: " + symbol);
    }

    private List<Candle> parseChartResponse(String json) {
        List<Long>   timestamps = parseLongArray(extractArray(json, "timestamp"));
        List<Double> opens      = parseDoubleArray(extractArray(json, "open"));
        List<Double> highs      = parseDoubleArray(extractArray(json, "high"));
        List<Double> lows       = parseDoubleArray(extractArray(json, "low"));
        List<Double> closes     = parseDoubleArray(extractArray(json, "close"));
        List<Double> adjCloses  = parseDoubleArray(extractArray(json, "adjclose")); // fallback
        List<Long>   volumes    = parseLongArray(extractArray(json, "volume"));

        int n = minSize(timestamps.size(), opens.size(), highs.size(), lows.size(), closes.size(), volumes.size());
        List<Candle> candles = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            long   ts     = timestamps.get(i);
            double open   = opens.get(i);
            double high   = highs.get(i);
            double low    = lows.get(i);
            double close  = closes.get(i);
            long   volume = volumes.get(i);

            // Yahoo sometimes publishes volume before the close price is finalised
            // (typically within 1–2 hours after market close).  Use adjclose first,
            // then fall back to typical-price (H+L+O)/3 so the bar is not silently
            // dropped when only the raw close is temporarily null.
            if (Double.isNaN(close)) {
                if (i < adjCloses.size() && !Double.isNaN(adjCloses.get(i))) {
                    close = adjCloses.get(i);            // preferred: adjusted close
                } else if (!Double.isNaN(open) && !Double.isNaN(high) && !Double.isNaN(low)) {
                    close = (open + high + low) / 3.0;  // last-resort: typical price
                }
            }

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
        if (!Files.exists(cacheFile)) return List.of();

        if (requireFresh) {
            try {
                Instant modified = Files.getLastModifiedTime(cacheFile).toInstant();
                if (modified.isBefore(Instant.now().minus(cacheTtl))) return List.of();
            } catch (IOException ignored) {
                return List.of();
            }
        }

        try {
            List<String> lines   = Files.readAllLines(cacheFile);
            List<Candle> candles = new ArrayList<>();
            for (int i = 1; i < lines.size(); i++) {
                String[] p = lines.get(i).split(",");
                if (p.length < 6) continue;
                try {
                    LocalDate date   = LocalDate.parse(p[0], DATE_FMT);
                    double    open   = Double.parseDouble(p[1]);
                    double    high   = Double.parseDouble(p[2]);
                    double    low    = Double.parseDouble(p[3]);
                    double    close  = Double.parseDouble(p[4]); // may be NaN if Yahoo hadn't finalised
                    long      volume = Long.parseLong(p[5].trim());
                    // Store candle even with NaN close — isDataCurrentEnough() skips NaN bars;
                    // parseChartResponse applies adjclose/typical-price fallback on fresh fetches.
                    candles.add(new Candle(date, open, high, low, close, volume));
                } catch (NumberFormatException ignored) {
                    // skip malformed row
                }
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
                    candle.getOpen(), candle.getHigh(), candle.getLow(), candle.getClose(),
                    candle.getVolume()
            ));
        }
        try {
            Files.write(cacheFile, lines);
        } catch (IOException ignored) {}
    }

    private String extractArray(String json, String key) {
        Pattern pattern = Pattern.compile(String.format(ARRAY_PATTERN_TEMPLATE.pattern(), Pattern.quote(key)), Pattern.DOTALL);
        Matcher matcher = pattern.matcher(json);
        return matcher.find() ? matcher.group(1) : "";
    }

    private List<Double> parseDoubleArray(String source) {
        if (source == null || source.isBlank()) return List.of();
        String[]     parts = source.split(",");
        List<Double> out   = new ArrayList<>(parts.length);
        for (String part : parts) {
            String token = part.trim();
            if ("null".equals(token) || token.isEmpty()) out.add(Double.NaN);
            else out.add(Double.parseDouble(token));
        }
        return out;
    }

    private List<Long> parseLongArray(String source) {
        if (source == null || source.isBlank()) return List.of();
        String[]   parts = source.split(",");
        List<Long> out   = new ArrayList<>(parts.length);
        for (String part : parts) {
            String token = part.trim();
            if ("null".equals(token) || token.isEmpty()) out.add(-1L);
            else out.add(Long.parseLong(token));
        }
        return out;
    }

    private int minSize(int... values) {
        int min = Integer.MAX_VALUE;
        for (int v : values) min = Math.min(min, v);
        return min == Integer.MAX_VALUE ? 0 : min;
    }

    private void sleepQuietly(long millis) {
        try { Thread.sleep(millis); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
    }
}
