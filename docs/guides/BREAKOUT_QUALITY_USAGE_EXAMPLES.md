# Breakout Quality Filters - Usage Examples

## 1. Basic Usage (No Changes Required)

Run your normal daily scan - quality analysis happens automatically:

```bash
java Main -m scan -t daily -s both
```

**Output:**
```
AAPL | Type BREAKOUT | Setup VCP | Window 60(60) | ... | Score 47.3 [BQ: EXCELLENT (38.5/40)]
MSFT | Type BREAKOUT | Setup VCP | Window 45(45) | ... | Score 42.1 [BQ: STRONG (28.2/40)]
GOOG | Type BREAKOUT | Setup VCP | Window 60(60) | ... | Score 38.5 [BQ: FAIR (17.8/40)]
TSLA | Type BREAKOUT | Setup VCP | Window 30(30) | ... | Score 35.2 [BQ: WEAK (12.5/40)]
```

---

## 2. Filter for EXCELLENT Signals Only

```bash
java Main -m scan -t daily | grep "EXCELLENT"
```

**Output:**
```
AAPL | Type BREAKOUT | Setup VCP | ... | Score 47.3 [BQ: EXCELLENT (38.5/40)]
NVDA | Type BREAKOUT | Setup VCP | ... | Score 45.8 [BQ: EXCELLENT (37.2/40)]
```

These are your highest-confidence trades. Start here.

---

## 3. View Quality Distribution

See how many signals fall into each quality tier:

```bash
java Main -m scan -t daily | grep -o "BQ: [A-Z]*" | sort | uniq -c
```

**Output:**
```
 3 BQ: EXCELLENT
 8 BQ: STRONG
12 BQ: GOOD
 7 BQ: FAIR
 4 BQ: WEAK
```

34 signals: 9% EXCELLENT, 24% STRONG, 35% GOOD, 21% FAIR, 12% WEAK

---

## 4. Get Detailed Quality Report

In your code, call the report method:

```java
// Get scan results
List<ScanResult> results = scannerEngine.scan(symbols, lookback, "daily");

// For each result, print detailed quality report
for (ScanResult result : results) {
    if (result.getBreakoutQuality() != null) {
        System.out.println(result.getBreakoutQualityReport());
    }
}
```

**Output:**
```
Breakout Quality Report for AAPL:
  Volume Percentile: 88% (Score: 10.0/10)
  Pivot Freshness: 2 tests (Score: 9.0/10)
  Distance Efficiency: 0.75% above pivot (Score: 9.0/10)
  Tightness Quality: (Score: 10.5/10)
  ────────────────────────
  Total Quality Score: 38.5/40 [EXCELLENT]
```

---

## 5. Use Strict Quality Filtering

Only trade signals that pass strict quality thresholds:

```java
// In your scanning/trading logic:
for (ScanResult result : scanResults) {
    BreakoutQualityAnalyzer.BreakoutQualityContext quality = result.getBreakoutQuality();
    
    if (quality != null && breakoutEvaluator.passesQualityFilter(quality, strictMode=true)) {
        // Trade this signal
        executeTrade(result);
    } else {
        // Skip or add to watchlist
        addToWatchlist(result);
    }
}
```

**Strict mode filters:**
- Volume percentile: ≥50th (average or better)
- Pivot tests: <8 (not exhausted)
- Distance: ≤2% above pivot (not extended)
- Tightness: ≥5.0/10 (reasonable control)

---

## 6. Compare Quality Tiers in Backtest

Run backtest and analyze by quality tier:

```java
BacktestEngine backtestEngine = new BacktestEngine(...);
BacktestReport report = backtestEngine.run(symbols, lookbackDays);

// Group trades by quality rating
Map<String, List<BacktestTrade>> byQuality = new HashMap<>();
for (BacktestTrade trade : report.getTrades()) {
    String rating = trade.getRating(); // Extract from trade metadata
    byQuality.computeIfAbsent(rating, k -> new ArrayList<>()).add(trade);
}

// Analyze each tier
for (String rating : new String[]{"EXCELLENT", "STRONG", "GOOD", "FAIR", "WEAK"}) {
    List<BacktestTrade> trades = byQuality.get(rating);
    if (trades != null && !trades.isEmpty()) {
        int wins = (int) trades.stream().filter(t -> t.getProfit() > 0).count();
        double winRate = (double) wins / trades.size() * 100.0;
        double avgR = trades.stream().mapToDouble(BacktestTrade::getRMultiple).average().orElse(0);
        
        System.out.printf("%s: %d trades, %.1f%% win, %.2fR avg\n", rating, trades.size(), winRate, avgR);
    }
}
```

**Output:**
```
EXCELLENT: 15 trades, 80.0% win, 2.15R avg
STRONG: 38 trades, 72.2% win, 1.85R avg
GOOD: 61 trades, 65.9% win, 1.42R avg
FAIR: 29 trades, 48.3% win, 0.95R avg
WEAK: 12 trades, 33.3% win, 0.45R avg
```

Now you can see EXCELLENT trades have 80% win rate vs WEAK at 33%.

---

## 7. Export to CSV with Quality Scores

Export signals for spreadsheet analysis:

```java
// After getting scan results
try (FileWriter writer = new FileWriter("signals_with_quality.csv")) {
    writer.append("Symbol,Type,Score,QualityRating,Quality Score,Volume %ile,Pivot Tests,Distance %,Tightness\n");
    
    for (ScanResult result : results) {
        BreakoutQualityAnalyzer.BreakoutQualityContext q = result.getBreakoutQuality();
        writer.append(result.getSymbol());
        writer.append(",").append(result.getSignalType());
        writer.append(",").append(String.format("%.1f", result.getQualityScore()));
        writer.append(",").append(q.qualityRating);
        writer.append(",").append(String.format("%.1f", q.totalQualityScore));
        writer.append(",").append(String.format("%.0f", q.volumePercentile * 100));
        writer.append(",").append(String.valueOf(q.pivotTestCount));
        writer.append(",").append(String.format("%.2f", q.distanceFromPivotPct * 100));
        writer.append(",").append(String.format("%.1f", q.tightnessScore));
        writer.append("\n");
    }
}
```

**CSV Output:**
```
Symbol,Type,Score,QualityRating,Quality Score,Volume %ile,Pivot Tests,Distance %,Tightness
AAPL,BREAKOUT,47.3,EXCELLENT,38.5,88,2,0.75,10.5
MSFT,BREAKOUT,42.1,STRONG,28.2,72,4,1.20,8.2
GOOG,BREAKOUT,38.5,FAIR,17.8,45,6,2.50,5.8
```

Now analyze in Excel with pivot tables, charts, etc.

---

## 8. Monitor Quality Trends

Track how quality changes over time:

```java
// Run scans daily for 30 days
// Collect quality ratings

Map<String, Integer> dailyCounts = new HashMap<>();
for (int day = 0; day < 30; day++) {
    List<ScanResult> results = scannerEngine.scan(symbols, lookback, "daily");
    
    for (ScanResult result : results) {
        String rating = result.getBreakoutQuality().qualityRating;
        dailyCounts.merge(rating, 1, Integer::sum);
    }
    
    System.out.printf("Day %d: %d EXCELLENT, %d STRONG, %d GOOD\n",
        day,
        dailyCounts.getOrDefault("EXCELLENT", 0),
        dailyCounts.getOrDefault("STRONG", 0),
        dailyCounts.getOrDefault("GOOD", 0)
    );
}
```

If EXCELLENT count drops significantly, market may be getting noisier.

---

## 9. Position Sizing by Quality

Size positions based on quality rating:

```java
Map<String, Double> sizeByQuality = new HashMap<>();
sizeByQuality.put("EXCELLENT", 1.0);    // 100% position
sizeByQuality.put("STRONG", 0.75);      // 75% position
sizeByQuality.put("GOOD", 0.50);        // 50% position
sizeByQuality.put("FAIR", 0.25);        // 25% position
sizeByQuality.put("WEAK", 0.0);         // Skip

for (ScanResult result : results) {
    String rating = result.getBreakoutQuality().qualityRating;
    double positionSize = sizeByQuality.get(rating);
    
    if (positionSize > 0) {
        int shares = (int) (baseTradeSizeShares * positionSize);
        executeTrade(result, shares);
    }
}
```

Conservative approach: Full size for EXCELLENT, partial for STRONG/GOOD, skip WEAK.

---

## 10. Create Quality Heat Map

Visualize quality across your universe:

```java
// Scan all symbols
List<ScanResult> allResults = scannerEngine.scan(universe, lookback, "daily");

// Sort by quality
allResults.sort(Comparator.comparingDouble(r -> 
    r.getBreakoutQuality() != null ? r.getBreakoutQuality().totalQualityScore : 0
).reversed());

// Print heatmap
System.out.println("═══ TOP QUALITY SIGNALS ═══");
for (int i = 0; i < Math.min(10, allResults.size()); i++) {
    ScanResult r = allResults.get(i);
    double score = r.getBreakoutQuality().totalQualityScore;
    String bar = "█".repeat((int)(score / 4)) + "░".repeat(10 - (int)(score / 4));
    System.out.printf("%s | %s | %.1f/40 %s\n", 
        r.getSymbol(),
        r.getBreakoutQuality().qualityRating,
        score,
        bar);
}
```

**Output:**
```
═══ TOP QUALITY SIGNALS ═══
AAPL | EXCELLENT | 38.5/40 █████████░
NVDA | EXCELLENT | 37.2/40 █████████░
MSFT | STRONG | 28.2/40 ███████░░░
GOOG | STRONG | 27.5/40 ███████░░░
TSLA | GOOD | 21.8/40 █████░░░░░
```

Quick visual of which signals look best.

---

## 11. Alert on Quality Changes

Get notified when pivot freshness drops:

```java
List<ScanResult> todayResults = scannerEngine.scan(symbols, lookback, "daily");
List<ScanResult> yesterdayResults = loadYesterdayResults();

for (ScanResult today : todayResults) {
    ScanResult yesterday = yesterdayResults.stream()
        .filter(r -> r.getSymbol().equals(today.getSymbol()))
        .findFirst()
        .orElse(null);
    
    if (yesterday != null) {
        int testCountDelta = today.getBreakoutQuality().pivotTestCount 
            - yesterday.getBreakoutQuality().pivotTestCount;
        
        if (testCountDelta > 2) {
            System.out.println("⚠️  " + today.getSymbol() + " pivot tested " + testCountDelta + " more times!");
            // Potentially reduce position or exit
        }
    }
}
```

Catch deteriorating setups before they fail.

---

## 12. Custom Quality Weighting

Weight dimensions differently based on your trading style:

```java
// Conservative trader: weight pivot freshness & distance heavily
double conservativeScore = 
    (quality.volumePercentileScore * 0.15) +
    (quality.pivotFreshnessScore * 0.40) +
    (quality.distanceEfficiencyScore * 0.35) +
    (quality.tightnessScore * 0.10);

// Momentum trader: weight volume & tightness heavily  
double momentumScore = 
    (quality.volumePercentileScore * 0.40) +
    (quality.pivotFreshnessScore * 0.10) +
    (quality.distanceEfficiencyScore * 0.10) +
    (quality.tightnessScore * 0.40);

// Then use custom scores for ranking
```

Tailor quality weighting to your strategy.

---

## Summary

The breakout quality system is flexible:

- **Use automatically:** Scores calculated for all breakouts
- **Observe:** See quality distribution in scans
- **Filter:** Optional strict mode available
- **Backtest:** Analyze performance by quality tier
- **Optimize:** Adjust sizing/filtering based on results
- **Deploy:** Use in live trading with confidence

Start simple (observe), then gradually apply filters as data supports.

---

*Ready to use in your system right now!*

