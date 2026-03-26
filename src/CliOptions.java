import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CliOptions {
    public final String mode;
    public final String provider;
    public final String timeframe;
    public final List<String> symbols;
    public final String exportFormat;
    public final String outPrefix;
    public final String setups;
    public final int lookbackDays;
    public final int retries;
    public final String cacheDir;
    public final long cacheTtlMinutes;
    public final int backtestHoldDays;
    public final double backtestTargetR;
    public final boolean lookbackProvided;
    public final int alreadyBreakoutMinBars;
    public final int alreadyBreakoutMaxBars;
    public final int backtestYears;
    public final String benchmarkSymbol;

    private CliOptions(
            String mode,
            String provider,
            String timeframe,
            List<String> symbols,
            String exportFormat,
            String outPrefix,
            String setups,
            int lookbackDays,
            int retries,
            String cacheDir,
            long cacheTtlMinutes,
            int backtestHoldDays,
            double backtestTargetR,
            boolean lookbackProvided,
            int alreadyBreakoutMinBars,
            int alreadyBreakoutMaxBars,
            int backtestYears,
            String benchmarkSymbol
    ) {
        this.mode = mode;
        this.provider = provider;
        this.timeframe = timeframe;
        this.symbols = symbols;
        this.exportFormat = exportFormat;
        this.outPrefix = outPrefix;
        this.setups = setups;
        this.lookbackDays = lookbackDays;
        this.retries = retries;
        this.cacheDir = cacheDir;
        this.cacheTtlMinutes = cacheTtlMinutes;
        this.backtestHoldDays = backtestHoldDays;
        this.backtestTargetR = backtestTargetR;
        this.lookbackProvided = lookbackProvided;
        this.alreadyBreakoutMinBars = alreadyBreakoutMinBars;
        this.alreadyBreakoutMaxBars = alreadyBreakoutMaxBars;
        this.backtestYears = backtestYears;
        this.benchmarkSymbol = benchmarkSymbol;
    }

    public static CliOptions parse(String[] args) {
        String mode = "scan";
        String provider = "sample";
        String timeframe = "daily";
        String symbolsArg = null;
        String export = "none";
        String outPrefix = "output/results";
        String setups = "both";
        int lookback = 252;
        boolean lookbackProvided = false;
        int retries = 3;
        String cacheDir = "cache";
        long cacheTtlMinutes = 360;
        int backtestHoldDays = 15;
        double backtestTargetR = 2.0;
        int alreadyBreakoutMinBars = 14;
        int alreadyBreakoutMaxBars = 20;
        int backtestYears = 2;
        String benchmarkSymbol = "";

        List<String> positional = new ArrayList<>();

        for (String arg : args) {
            if (!arg.startsWith("--")) {
                positional.add(arg);
                continue;
            }

            if (arg.startsWith("--mode=")) {
                mode = value(arg);
            } else if (arg.startsWith("--provider=")) {
                provider = value(arg);
            } else if (arg.startsWith("--timeframe=")) {
                timeframe = value(arg);
            } else if (arg.startsWith("--symbols=")) {
                symbolsArg = value(arg);
            } else if (arg.startsWith("--export=")) {
                export = value(arg);
            } else if (arg.startsWith("--out=")) {
                outPrefix = value(arg);
            } else if (arg.startsWith("--setups=")) {
                setups = normalizeSetups(value(arg));
            } else if (arg.startsWith("--lookback=")) {
                lookback = parseInt(value(arg), lookback);
                lookbackProvided = true;
            } else if (arg.startsWith("--retries=")) {
                retries = parseInt(value(arg), retries);
            } else if (arg.startsWith("--cache-dir=")) {
                cacheDir = value(arg);
            } else if (arg.startsWith("--cache-ttl-min=")) {
                cacheTtlMinutes = parseLong(value(arg), cacheTtlMinutes);
            } else if (arg.startsWith("--backtest-hold-days=")) {
                backtestHoldDays = parseInt(value(arg), backtestHoldDays);
            } else if (arg.startsWith("--backtest-target-r=")) {
                backtestTargetR = parseDouble(value(arg), backtestTargetR);
            } else if (arg.startsWith("--already-breakout-min-bars=")) {
                alreadyBreakoutMinBars = parseInt(value(arg), alreadyBreakoutMinBars);
            } else if (arg.startsWith("--already-breakout-max-bars=")) {
                alreadyBreakoutMaxBars = parseInt(value(arg), alreadyBreakoutMaxBars);
            } else if (arg.startsWith("--backtest-years=")) {
                backtestYears = parseInt(value(arg), backtestYears);
            } else if (arg.startsWith("--benchmark=")) {
                benchmarkSymbol = value(arg);
            }
        }

        if (!lookbackProvided && "weekly".equalsIgnoreCase(timeframe)) {
            lookback = 104;
        }

        List<String> symbols;
        if (symbolsArg != null && !symbolsArg.isBlank()) {
            symbols = splitCsv(symbolsArg);
        } else if (!positional.isEmpty()) {
            symbols = positional;
        } else {
            symbols = List.of("NVCP", "VCPX", "ALPHA", "BETA", "OMEGA", "DELTA", "GAMMA");
        }

        alreadyBreakoutMinBars = Math.max(1, alreadyBreakoutMinBars);
        alreadyBreakoutMaxBars = Math.max(alreadyBreakoutMinBars, alreadyBreakoutMaxBars);
        backtestYears = Math.max(1, backtestYears);

        return new CliOptions(
                mode.toLowerCase(),
                provider.toLowerCase(),
                normalizeTimeframe(timeframe),
                symbols,
                export.toLowerCase(),
                outPrefix,
                setups,
                lookback,
                retries,
                cacheDir,
                cacheTtlMinutes,
                backtestHoldDays,
                backtestTargetR,
                lookbackProvided,
                alreadyBreakoutMinBars,
                alreadyBreakoutMaxBars,
                backtestYears,
                benchmarkSymbol.trim()
        );
    }

    private static String value(String arg) {
        int idx = arg.indexOf('=');
        return idx < 0 ? "" : arg.substring(idx + 1).trim();
    }

    private static int parseInt(String value, int defaultValue) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException ex) {
            return defaultValue;
        }
    }

    private static long parseLong(String value, long defaultValue) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ex) {
            return defaultValue;
        }
    }

    private static double parseDouble(String value, double defaultValue) {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException ex) {
            return defaultValue;
        }
    }

    private static List<String> splitCsv(String csv) {
        List<String> parts = new ArrayList<>();
        Arrays.stream(csv.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .forEach(parts::add);
        return parts;
    }

    private static String normalizeTimeframe(String timeframe) {
        if (timeframe == null || timeframe.isBlank()) {
            return "daily";
        }
        String normalized = timeframe.trim().toLowerCase();
        return "weekly".equals(normalized) ? "weekly" : "daily";
    }

    private static String normalizeSetups(String setups) {
        if (setups == null || setups.isBlank()) {
            return "both";
        }
        String normalized = setups.trim().toLowerCase().replace('-', '_');
        if ("meanreversion".equals(normalized)) {
            normalized = "mean_reversion";
        }
        if ("vcp".equals(normalized)) {
            return "vcp";
        }
        if ("range_expansion".equals(normalized)) {
            return "range_expansion";
        }
        if ("mean_reversion".equals(normalized)) {
            return "mean_reversion";
        }
        return "both";
    }
}

