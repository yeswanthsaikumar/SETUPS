import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class RejectionDiagnostic {
    public enum Reason {
        BELOW_MA,
        FAR_FROM_52W_HIGH,
        LOW_PRICE,
        LOW_QUALITY,
        NO_BREAKOUT,
        TOO_FAR_FROM_PIVOT,
        ATR_EXPANDING,
        INSUFFICIENT_VOLUME,
        INSUFFICIENT_DATA,
        DATA_ERROR,
        ALREADY_BROKEN_OUT,
        LOW_RS_RANK,
        WEAK_SECTOR,
        MARKET_HEADWIND,
        LOW_LIQUIDITY
    }

    private static final DateTimeFormatter TS_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    private final String timestamp;
    private final String symbol;
    private final String mode;
    private final String timeframe;
    private final Reason reason;
    private final String details;

    public RejectionDiagnostic(String symbol, String mode, String timeframe, Reason reason, String details) {
        this.timestamp = LocalDateTime.now().format(TS_FMT);
        this.symbol = symbol;
        this.mode = mode;
        this.timeframe = timeframe;
        this.reason = reason;
        this.details = details == null ? "" : details;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public String getSymbol() {
        return symbol;
    }

    public String getMode() {
        return mode;
    }

    public String getTimeframe() {
        return timeframe;
    }

    public Reason getReason() {
        return reason;
    }

    public String getDetails() {
        return details;
    }
}
