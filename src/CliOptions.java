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
            double backtestTargetR
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
                backtestTargetR
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

