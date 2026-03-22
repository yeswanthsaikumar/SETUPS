import java.util.List;

/**
 * Enhanced breakout quality analysis beyond basic BreakoutEvaluator.
 * Implements four advanced quality filters across 0-40 points.
 */
public class BreakoutQualityAnalyzer {
    
    public static class BreakoutQualityContext {
        public double volumePercentile;
        public double volumePercentileScore;
        public int pivotTestCount;
        public double pivotFreshnessScore;
        public double distanceFromPivotPct;
        public double distanceEfficiencyScore;
        public double tightnessScore;
        public double totalQualityScore;
        public String qualityRating;
        
        public BreakoutQualityContext() {
            this.volumePercentile = 0.0;
            this.volumePercentileScore = 0.0;
            this.pivotTestCount = 0;
            this.pivotFreshnessScore = 0.0;
            this.distanceFromPivotPct = 0.0;
            this.distanceEfficiencyScore = 0.0;
            this.tightnessScore = 0.0;
            this.totalQualityScore = 0.0;
            this.qualityRating = "WEAK";
        }
        
        @Override
        public String toString() {
            return String.format(
                "BQC[VolPerc=%.0f%%/%.1fpt, PivotTest=%d/%.1fpt, Dist=%.2f%%/%.1fpt, Tight=%.1fpt, Total=%.1fpt, Rating=%s]",
                volumePercentile * 100.0, volumePercentileScore,
                pivotTestCount, pivotFreshnessScore,
                distanceFromPivotPct * 100.0, distanceEfficiencyScore,
                tightnessScore, totalQualityScore, qualityRating
            );
        }
    }
    
    public BreakoutQualityContext analyzeBreakoutQuality(
            List<Candle> candles,
            VcpSetup setup,
            AppConfig config
    ) {
        BreakoutQualityContext ctx = new BreakoutQualityContext();
        if (candles == null || candles.isEmpty()) {
            return ctx;
        }
        
        Candle breakoutCandle = candles.get(candles.size() - 1);
        double pivotPrice = setup.getPivotPrice();
        
        analyzeVolumePercentile(candles, breakoutCandle, ctx);
        analyzePivotFreshness(candles, pivotPrice, breakoutCandle, ctx);
        analyzeDistanceEfficiency(breakoutCandle, pivotPrice, ctx);
        analyzeTightnessQuality(candles, ctx);
        
        ctx.totalQualityScore = ctx.volumePercentileScore + ctx.pivotFreshnessScore 
            + ctx.distanceEfficiencyScore + ctx.tightnessScore;
        
        if (ctx.totalQualityScore >= 32.0) {
            ctx.qualityRating = "EXCELLENT";
        } else if (ctx.totalQualityScore >= 26.0) {
            ctx.qualityRating = "STRONG";
        } else if (ctx.totalQualityScore >= 20.0) {
            ctx.qualityRating = "GOOD";
        } else if (ctx.totalQualityScore >= 14.0) {
            ctx.qualityRating = "FAIR";
        } else {
            ctx.qualityRating = "WEAK";
        }
        return ctx;
    }
    
    private void analyzeVolumePercentile(List<Candle> candles, Candle breakoutCandle, BreakoutQualityContext ctx) {
        int volumeLookback = Math.min(50, candles.size() - 2);
        if (volumeLookback < 10) {
            ctx.volumePercentileScore = 5.0;
            return;
        }
        
        int lookbackStart = candles.size() - 1 - volumeLookback;
        double breakoutVolume = breakoutCandle.getVolume();
        int countBelowBreakout = 0;
        
        for (int i = lookbackStart; i < candles.size() - 1; i++) {
            if (candles.get(i).getVolume() < breakoutVolume) {
                countBelowBreakout++;
            }
        }
        
        ctx.volumePercentile = (double) countBelowBreakout / volumeLookback;
        
        if (ctx.volumePercentile >= 0.80) {
            ctx.volumePercentileScore = 10.0;
        } else if (ctx.volumePercentile >= 0.60) {
            ctx.volumePercentileScore = 8.0;
        } else if (ctx.volumePercentile >= 0.50) {
            ctx.volumePercentileScore = 6.0;
        } else if (ctx.volumePercentile >= 0.40) {
            ctx.volumePercentileScore = 5.0;
        } else if (ctx.volumePercentile >= 0.30) {
            ctx.volumePercentileScore = 3.0;
        } else {
            ctx.volumePercentileScore = 1.0;
        }
    }
    
    private void analyzePivotFreshness(List<Candle> candles, double pivotPrice, Candle breakoutCandle, BreakoutQualityContext ctx) {
        if (pivotPrice <= 0.0) {
            ctx.pivotFreshnessScore = 5.0;
            return;
        }
        
        int testCount = 0;
        double pivotTouchRange = pivotPrice * 0.01;
        
        for (int i = Math.max(0, candles.size() - 30); i < candles.size() - 1; i++) {
            Candle c = candles.get(i);
            boolean touchedPivot = (c.getHigh() >= pivotPrice && c.getClose() < pivotPrice * 1.005)
                    || (Math.abs(c.getClose() - pivotPrice) <= pivotTouchRange);
            if (touchedPivot) testCount++;
        }
        
        ctx.pivotTestCount = testCount;
        
        if (testCount <= 1) ctx.pivotFreshnessScore = 10.0;
        else if (testCount == 2) ctx.pivotFreshnessScore = 9.0;
        else if (testCount <= 4) ctx.pivotFreshnessScore = 7.5;
        else if (testCount <= 6) ctx.pivotFreshnessScore = 5.0;
        else if (testCount <= 9) ctx.pivotFreshnessScore = 3.0;
        else ctx.pivotFreshnessScore = 1.0;
    }
    
    private void analyzeDistanceEfficiency(Candle breakoutCandle, double pivotPrice, BreakoutQualityContext ctx) {
        if (pivotPrice <= 0.0) {
            ctx.distanceEfficiencyScore = 5.0;
            return;
        }
        
        ctx.distanceFromPivotPct = (breakoutCandle.getClose() - pivotPrice) / pivotPrice;
        
        if (ctx.distanceFromPivotPct <= 0.005) ctx.distanceEfficiencyScore = 10.0;
        else if (ctx.distanceFromPivotPct <= 0.008) ctx.distanceEfficiencyScore = 9.0;
        else if (ctx.distanceFromPivotPct <= 0.012) ctx.distanceEfficiencyScore = 7.5;
        else if (ctx.distanceFromPivotPct <= 0.020) ctx.distanceEfficiencyScore = 6.0;
        else if (ctx.distanceFromPivotPct <= 0.035) ctx.distanceEfficiencyScore = 3.0;
        else ctx.distanceEfficiencyScore = 1.0;
    }
    
    private void analyzeTightnessQuality(List<Candle> candles, BreakoutQualityContext ctx) {
        if (candles.size() < 30) {
            ctx.tightnessScore = 5.0;
            return;
        }
        double s1 = analyzeCloseClustering(candles);
        double s2 = analyzeAtrShrinkage(candles);
        double s3 = analyzePullbackDepth(candles);
        ctx.tightnessScore = (s1 + s2 + s3) / 3.0;
    }
    
    private double analyzeCloseClustering(List<Candle> candles) {
        double baseHi = Indicators.highestHigh(candles, candles.size() - 30, candles.size() - 2);
        double baseLo = Indicators.lowestLow(candles, candles.size() - 30, candles.size() - 2);
        double baseRng = baseHi - baseLo;
        double recHi = Indicators.highestHigh(candles, candles.size() - 10, candles.size() - 2);
        double recLo = Indicators.lowestLow(candles, candles.size() - 10, candles.size() - 2);
        double recRng = recHi - recLo;
        if (baseRng <= 0.0) return 5.0;
        double r = recRng / baseRng;
        if (r < 0.4) return 10.0;
        else if (r < 0.6) return 8.5;
        else if (r < 0.8) return 7.0;
        else if (r < 1.0) return 6.0;
        else if (r < 1.2) return 4.0;
        else return 2.0;
    }
    
    private double analyzeAtrShrinkage(List<Candle> candles) {
        double baseAtr = Indicators.averageTrueRange(candles, candles.size() - 2, 20);
        double recAtr = Indicators.averageTrueRange(candles, candles.size() - 2, 10);
        if (baseAtr <= 0.0) return 5.0;
        double r = recAtr / baseAtr;
        if (r < 0.6) return 10.0;
        else if (r < 0.75) return 8.5;
        else if (r < 0.9) return 7.0;
        else if (r < 1.05) return 5.0;
        else if (r < 1.2) return 3.0;
        else return 1.0;
    }
    
    private double analyzePullbackDepth(List<Candle> candles) {
        double sumBase = 0.0;
        int cntBase = 0;
        for (int i = candles.size() - 32; i < candles.size() - 12; i++) {
            if (i >= 0) {
                double hi = candles.get(i).getHigh();
                double nxtCl = candles.get(i + 1).getClose();
                if (hi > nxtCl) { sumBase += (hi - nxtCl) / hi; cntBase++; }
            }
        }
        double baseDepth = cntBase > 0 ? sumBase / cntBase : 0.01;
        
        double sumRec = 0.0;
        int cntRec = 0;
        for (int i = candles.size() - 12; i < candles.size() - 2; i++) {
            if (i >= 0) {
                double hi = candles.get(i).getHigh();
                double nxtCl = candles.get(i + 1).getClose();
                if (hi > nxtCl) { sumRec += (hi - nxtCl) / hi; cntRec++; }
            }
        }
        double recDepth = cntRec > 0 ? sumRec / cntRec : 0.01;
        double r = recDepth / Math.max(baseDepth, 0.001);
        
        if (r < 0.5) return 10.0;
        else if (r < 0.7) return 8.0;
        else if (r < 0.9) return 6.0;
        else if (r < 1.1) return 5.0;
        else if (r < 1.3) return 3.0;
        else return 1.0;
    }
}
