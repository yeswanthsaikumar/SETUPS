import java.util.List;

public class BreakoutEvaluator {
    public RejectionDiagnostic.Reason classifyBreakoutRejection(List<Candle> candles, VcpSetup setup, AppConfig config) {
        if (candles == null || candles.size() < 8 || setup == null) {
            return RejectionDiagnostic.Reason.INSUFFICIENT_DATA;
        }

        Candle latest = candles.get(candles.size() - 1);
        int baseEnd = candles.size() - 2;
        int volumeLookback = Math.min(20, baseEnd);
        int volumeStart = Math.max(0, baseEnd - volumeLookback + 1);
        double avgVolume = Indicators.averageVolume(candles, volumeStart, baseEnd);

        if (setup.getSetupType() == VcpSetup.SetupType.MEAN_REVERSION) {
            return classifyMeanReversionRejection(candles, setup, config, avgVolume);
        }

        boolean priceBreakout = latest.getClose() > setup.getPivotPrice() * (1.0 + config.breakoutBufferPct);
        boolean intradayBreak = latest.getHigh() > setup.getPivotPrice();
        boolean volumeBreakout = latest.getVolume() >= avgVolume * config.breakoutVolumeMultiplier;

        if (!volumeBreakout) {
            return RejectionDiagnostic.Reason.INSUFFICIENT_VOLUME;
        }
        if (!priceBreakout || !intradayBreak) {
            return RejectionDiagnostic.Reason.NO_BREAKOUT;
        }

        if (setup.getSetupType() == VcpSetup.SetupType.RANGE_EXPANSION) {
            double breakoutRange = Math.max(0.0, latest.getHigh() - latest.getLow());
            double atr20 = Indicators.averageTrueRange(candles, candles.size() - 2, 20);
            boolean expandedRange = atr20 > 0.0 && breakoutRange >= atr20 * config.minRangeExpansionMultiplier;
            if (!expandedRange) {
                return RejectionDiagnostic.Reason.ATR_EXPANDING;
            }
            double closeInRange = breakoutRange <= 0.0 ? 0.0 : (latest.getClose() - latest.getLow()) / breakoutRange;
            if (closeInRange < config.minExpansionClosePosition) {
                return RejectionDiagnostic.Reason.NO_BREAKOUT;
            }
        }

        // If breakout is valid but scan still rejected, it likely failed continuation branch checks.
        return RejectionDiagnostic.Reason.NO_BREAKOUT;
    }

    public boolean isBullishBreakout(List<Candle> candles, VcpSetup setup, AppConfig config) {
        if (candles.size() < 8) {
            return false;
        }

        Candle latest = candles.get(candles.size() - 1);
        int baseEnd = candles.size() - 2;
        int volumeLookback = Math.min(20, baseEnd);
        int volumeStart = Math.max(0, baseEnd - volumeLookback + 1);
        double volume20 = Indicators.averageVolume(candles, volumeStart, baseEnd);

        if (setup.getSetupType() == VcpSetup.SetupType.MEAN_REVERSION) {
            return isMeanReversionBreakout(candles, setup, config, volume20);
        }

        // Price: latest CLOSE must be above pivot + buffer (0.3%)
        boolean priceBreakout = latest.getClose() > setup.getPivotPrice() * (1.0 + config.breakoutBufferPct);

        // Volume: breakout bar volume must be >= 1.25x 20-day average (was 1.5x)
        boolean volumeBreakout = latest.getVolume() >= volume20 * config.breakoutVolumeMultiplier;

        // Intraday confirmation: the HIGH of the breakout bar must have pierced the pivot
        // (avoids false breakouts where stock gapped up at open but closed near pivot)
        boolean intradayBreak = latest.getHigh() > setup.getPivotPrice();

        if (!priceBreakout || !volumeBreakout || !intradayBreak) {
            return false;
        }

        if (setup.getSetupType() == VcpSetup.SetupType.RANGE_EXPANSION) {
            double breakoutRange = Math.max(0.0, latest.getHigh() - latest.getLow());
            double atr20 = Indicators.averageTrueRange(candles, candles.size() - 2, 20);
            boolean expandedRange = atr20 > 0.0 && breakoutRange >= atr20 * config.minRangeExpansionMultiplier;

            double closeInRange = breakoutRange <= 0.0 ? 0.0 : (latest.getClose() - latest.getLow()) / breakoutRange;
            boolean strongClose = closeInRange >= config.minExpansionClosePosition;

            return expandedRange && strongClose;
        }

        return true;
    }

    public boolean isNearBreakoutContinuation(List<Candle> candles, VcpSetup setup, AppConfig config) {
        if (candles.size() < 8) {
            return false;
        }

        Candle latest = candles.get(candles.size() - 1);
        int baseEnd = candles.size() - 2;
        int volumeLookback = Math.min(20, baseEnd);
        int volumeStart = Math.max(0, baseEnd - volumeLookback + 1);
        double avgVolume = Indicators.averageVolume(candles, volumeStart, baseEnd);

        if (setup.getSetupType() == VcpSetup.SetupType.MEAN_REVERSION) {
            return isNearMeanReversionContinuation(candles, setup, config, avgVolume);
        }

        double pivot = setup.getPivotPrice();
        if (pivot <= 0.0) {
            return false;
        }

        // Must already be above pivot buffer, but not too extended.
        double abovePivotPct = (latest.getClose() - pivot) / pivot;
        boolean inContinuationZone =
                abovePivotPct >= config.nearBreakoutMinAbovePivotPct
                        && abovePivotPct <= config.nearBreakoutMaxAbovePivotPct;
        if (!inContinuationZone) {
            return false;
        }

        boolean volumeHealthy = latest.getVolume() >= avgVolume * config.nearBreakoutVolumeMultiplier;
        boolean holdingPivot = latest.getLow() >= pivot * (1.0 - config.breakoutBufferPct);
        boolean closeAboveEntry = latest.getClose() >= pivot * (1.0 + config.breakoutBufferPct);
        if (!volumeHealthy || !holdingPivot || !closeAboveEntry) {
            return false;
        }

        if (setup.getSetupType() == VcpSetup.SetupType.RANGE_EXPANSION) {
            double breakoutRange = Math.max(0.0, latest.getHigh() - latest.getLow());
            double closeInRange = breakoutRange <= 0.0 ? 0.0 : (latest.getClose() - latest.getLow()) / breakoutRange;
            return closeInRange >= config.minExpansionClosePosition;
        }

        return true;
    }

    private boolean isMeanReversionBreakout(List<Candle> candles, VcpSetup setup, AppConfig config, double avgVolume) {
        Candle latest = candles.get(candles.size() - 1);
        Candle prev = candles.get(candles.size() - 2);
        double pivot = setup.getPivotPrice();
        if (pivot <= 0.0 || setup.getSupportPrice() <= 0.0) {
            return false;
        }

        boolean reclaimTrigger = latest.getClose() >= pivot * (1.0 + config.breakoutBufferPct);
        boolean bullishReversal = latest.getClose() > latest.getOpen() && latest.getClose() > prev.getClose();
        boolean heldSupport = latest.getLow() > setup.getSupportPrice() * (1.0 - config.stopBufferPct);
        boolean volumeConfirmed = latest.getVolume() >= avgVolume * config.meanReversionVolumeMultiplier;
        return reclaimTrigger && bullishReversal && heldSupport && volumeConfirmed;
    }

    private boolean isNearMeanReversionContinuation(List<Candle> candles, VcpSetup setup, AppConfig config, double avgVolume) {
        Candle latest = candles.get(candles.size() - 1);
        double pivot = setup.getPivotPrice();
        if (pivot <= 0.0 || setup.getSupportPrice() <= 0.0) {
            return false;
        }

        double distanceToTrigger = (pivot - latest.getClose()) / pivot;
        boolean nearTrigger = distanceToTrigger >= 0.0
                && distanceToTrigger <= config.meanReversionMaxDistanceToTriggerPct;
        boolean aboveSupport = latest.getClose() > setup.getSupportPrice() * (1.0 + config.stopBufferPct);
        boolean volumeHealthy = latest.getVolume() >= avgVolume * config.meanReversionNearVolumeMultiplier;
        return nearTrigger && aboveSupport && volumeHealthy;
    }

    private RejectionDiagnostic.Reason classifyMeanReversionRejection(
            List<Candle> candles,
            VcpSetup setup,
            AppConfig config,
            double avgVolume
    ) {
        Candle latest = candles.get(candles.size() - 1);
        Candle prev = candles.get(candles.size() - 2);
        double pivot = setup.getPivotPrice();

        boolean reclaimTrigger = pivot > 0.0 && latest.getClose() >= pivot * (1.0 + config.breakoutBufferPct);
        boolean bullishReversal = latest.getClose() > latest.getOpen() && latest.getClose() > prev.getClose();
        boolean heldSupport = setup.getSupportPrice() > 0.0
                && latest.getLow() > setup.getSupportPrice() * (1.0 - config.stopBufferPct);
        boolean volumeConfirmed = latest.getVolume() >= avgVolume * config.meanReversionVolumeMultiplier;

        if (!volumeConfirmed) {
            return RejectionDiagnostic.Reason.INSUFFICIENT_VOLUME;
        }
        if (!reclaimTrigger || !bullishReversal || !heldSupport) {
            return RejectionDiagnostic.Reason.NO_BREAKOUT;
        }
        return RejectionDiagnostic.Reason.NO_BREAKOUT;
    }
}
