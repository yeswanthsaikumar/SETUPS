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
    private static final int MAX_DATA_GAP_DAYS = 5; // >5 calendar days = always stale

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

            // Step 2: Fetch crumb (short timeout)
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
            // Failed to get crumb — trip circuit breaker so future calls don't waste time
            tripCircuitBreaker();
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

        if (daysSince <= 1) return true;
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
     * Merge newly-fetched bars into a stale baseline, let fresh bars overwrite stale
     * on the same date, sort chronologically, and trim to the most recent lookbackDays bars.
     */
    private List<Candle> mergeAndTrim(List<Candle> stale, List<Candle> fresh, int lookbackDays) {
        Map<LocalDate, Candle> byDate = new LinkedHashMap<>();
        for (Candle c : stale) byDate.put(c.getDate(), c);
        for (Candle c : fresh)  byDate.put(c.getDate(), c); // fresh overwrites same date
        List<Candle> merged = new ArrayList<>(byDate.values());
        merged.sort(Comparator.comparing(Candle::getDate));
        if (merged.size() > lookbackDays) {
            merged = new ArrayList<>(merged.subList(merged.size() - lookbackDays, merged.size()));
        }
        return merged;
    }

    @Override
    public List<Candle> getDailyCandles(String symbol, int lookbackDays) {
        try {
            Files.createDirectories(cacheDir);
        } catch (IOException ignored) {}

        Path cacheFile = cacheDir.resolve(symbol.toUpperCase() + "_" + lookbackDays + ".csv");

        // 1. Exact-size cache — primary freshness check is DATA DATE (not file mtime).
        //    A file written hours ago with March-31 data is stale; a week-old file with
        //    last Friday's data may still be current (long holiday weekend).
        List<Candle> exact = readCache(cacheFile, false);
        if (isDataCurrentEnough(exact)) return exact;

        // 2. Any alternative cache file (larger) that already has current data.
        //    Avoids a network round-trip when a bigger file is already up-to-date.
        List<Candle> altFresh = findFreshAlternativeCache(symbol, lookbackDays);
        if (!altFresh.isEmpty()) {
            return trimToLookback(altFresh, lookbackDays);
        }

        // 3. Incremental network fetch — only download bars after the last known date.
        //    We do NOT cache-guard stale checks with file mtime here, because:
        //    - Yahoo may publish EOD data with a short delay after market close.
        //    - A "recently checked" cache guard would prevent getting the new data.
        //    - isDataCurrentEnough() above already handles "cache is up-to-date → skip Yahoo".
        List<Candle> stale = !exact.isEmpty() ? exact : readBestExistingCache(symbol, lookbackDays, false);
        LocalDate fetchFrom = stale.isEmpty() ? null : stale.get(stale.size() - 1).getDate();

        Exception lastError = null;
        for (int attempt = 1; attempt <= retries; attempt++) {
            try {
                List<Candle> newBars = fetchFromYahoo(symbol, lookbackDays, fetchFrom);
                if (!newBars.isEmpty()) {
                    // Got new bars — merge with stale baseline, persist, and return.
                    List<Candle> merged = mergeAndTrim(stale, newBars, lookbackDays);
                    writeCache(cacheFile, merged);
                    return merged;
                }
                // Yahoo returned HTTP 200 but no new bars — market is closed (holiday /
                // weekend) OR data is not yet published.  Do NOT touch the cache file so
                // that the next scan run will re-check Yahoo and pick up data as soon as
                // it becomes available (typically within minutes of market close).
                break; // no point retrying if HTTP 200 with empty result
            } catch (Exception ex) {
                lastError = ex;
                sleepQuietly((long) attempt * 400L);
            }
        }

        // 4. Stale fallback — graceful degradation when network fails or data unavailable.
        if (!stale.isEmpty()) {
            return trimToLookback(stale, lookbackDays);
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
     * Scan cache directory for any SYMBOL_N.csv file that passes the data-date freshness
     * check AND has at least lookbackDays bars.  Returns the best candidate (smallest
     * adequate file) or an empty list if none qualify.
     */
    private List<Candle> findFreshAlternativeCache(String symbol, int lookbackDays) {
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
        if (candidates.isEmpty()) return List.of();

        // Sort ascending by numeric suffix (smallest first → least I/O)
        candidates.sort(Comparator.comparingInt(p -> {
            String name = p.getFileName().toString();
            String num  = name.substring(prefix.length(), name.length() - 4);
            try { return Integer.parseInt(num); } catch (NumberFormatException e) { return Integer.MAX_VALUE; }
        }));

        for (Path candidate : candidates) {
            List<Candle> candles = readCache(candidate, false);
            if (candles.size() >= lookbackDays && isDataCurrentEnough(candles)) {
                return candles;
            }
        }
        return List.of();
    }

    /**
     * Scan the cache directory for any file matching {@code SYMBOL_N.csv}.
     * When {@code requireFresh=true}, uses mtime TTL as a secondary gate (stale-fallback path).
     * When {@code requireFresh=false}, any file is accepted (last-resort fallback).
     */
    private List<Candle> readBestExistingCache(String symbol, int lookbackDays, boolean requireFresh) {
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
        if (candidates.isEmpty()) return List.of();

        if (requireFresh) {
            Instant cutoff = Instant.now().minus(cacheTtl);
            candidates.removeIf(p -> {
                try {
                    return Files.getLastModifiedTime(p).toInstant().isBefore(cutoff);
                } catch (IOException e) {
                    return true;
                }
            });
            if (candidates.isEmpty()) return List.of();
        }

        candidates.sort(Comparator.comparingInt(p -> {
            String name = p.getFileName().toString();
            String num  = name.substring(prefix.length(), name.length() - 4);
            try { return Integer.parseInt(num); } catch (NumberFormatException e) { return Integer.MAX_VALUE; }
        }));

        Path bestLarge = candidates.get(candidates.size() - 1);
        for (Path candidate : candidates) {
            List<Candle> candles = readCache(candidate, false);
            if (candles.size() >= lookbackDays) {
                if (candles.size() > lookbackDays) {
                    candles = new ArrayList<>(candles.subList(candles.size() - lookbackDays, candles.size()));
                }
                return candles;
            }
        }

        return readCache(bestLarge, false);
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

                // Return raw parsed bars — caller's mergeAndTrim handles dedup + trimming
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
