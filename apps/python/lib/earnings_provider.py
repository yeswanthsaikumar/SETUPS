"""Quarterly earnings provider.

Pulls per-symbol earnings calendars (historical + upcoming) via yfinance,
classifies each event into one of:

* ``UPCOMING``  — scheduled in the next ``days_ahead`` days → AVOID (volatility).
* ``BEAT``      — reported within last ``days_back`` days, surprise > +5%
                  OR post-announcement gap > +4% → ENTRY CANDIDATE (PEG).
* ``INLINE``    — reported recently, surprise within ±5% → neutral.
* ``MISS``      — reported recently, surprise < −5% OR post-announcement
                  gap < −4% → AVOID / EXIT.

Thin, tolerant, and cache-backed. Each symbol gets its own TTL so a single
flaky Yahoo response never poisons the whole board.
"""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

try:  # soft-dep — callers handle the ImportError path upstream
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

try:
    from nse_earnings_provider import NSEEarningsProvider  # type: ignore
except Exception:  # pragma: no cover
    NSEEarningsProvider = None  # type: ignore

BEAT_SURPRISE_PCT = 5.0
MISS_SURPRISE_PCT = -5.0
BEAT_GAP_PCT = 4.0
MISS_GAP_PCT = -4.0
# Historical events never change; upcoming events can shift, so we revalidate
# often — but we always serve the cached copy first (stale-while-revalidate).
DEFAULT_TTL_HOURS = 24.0
DEFAULT_DAYS_AHEAD = 14
DEFAULT_DAYS_BACK = 45
# How old a cache entry can get before we schedule a background refresh while
# still serving it immediately. Must be < TTL to actually pre-empt expiry.
DEFAULT_REVALIDATE_AFTER_HOURS = 6.0


@dataclass
class EarningsEvent:
    symbol: str
    name: str
    date: str                 # ISO YYYY-MM-DD
    status: str               # UPCOMING | BEAT | INLINE | MISS | UNKNOWN
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None
    gap_pct: float | None     # (open / prior_close − 1) × 100 on report day
    close_after_pct: float | None  # (close / prior_close − 1) × 100
    volume_ratio: float | None     # report-day vol / 20d-avg vol
    days_until: int           # negative → already reported
    source: str               # "yfinance" | "cache"


class EarningsProvider:
    """Small, thread-safe provider with a per-symbol JSON cache.

    Uses a **stale-while-revalidate** strategy:
      • Any cached entry is returned immediately (even after TTL).
      • If the entry is older than ``revalidate_after_hours``, a background
        thread refreshes it so the *next* call sees fresh data.
      • Only ``force=True`` blocks on a live fetch.
    The cache file survives server restarts, so once a symbol is fetched the
    data is never "lost" — Yahoo only gets re-hit on revalidation windows.
    """

    def __init__(
        self,
        cache_path: Path | str,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        max_workers: int = 3,
        revalidate_after_hours: float = DEFAULT_REVALIDATE_AFTER_HOURS,
        nse_cache_path: Path | str | None = None,
        ohlcv_reader=None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600.0
        self.revalidate_seconds = revalidate_after_hours * 3600.0
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._cache: dict = self._load()
        # Symbols currently being refreshed in the background (avoid duplicate
        # concurrent Yahoo calls for the same ticker).
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()

        # Optional NSE India adapter — primary source for Indian tickers.
        # Yahoo lags filings by 1–2 quarters on many mid/small-caps, so we
        # merge NSE's authoritative event calendar + recent filings on top.
        self._nse = None
        if nse_cache_path and NSEEarningsProvider is not None:
            try:
                self._nse = NSEEarningsProvider(nse_cache_path)
            except Exception as e:
                print(f"[earnings] NSE adapter disabled: {e}", flush=True)
        # OHLCV reader callable: (symbol) → pandas.DataFrame with
        # OHLCV columns + DatetimeIndex. Used to classify NSE-sourced events
        # via post-filing gap when no EPS surprise is available.
        self._read_ohlcv = ohlcv_reader

    # ── cache ────────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if not self.cache_path.exists():
            return {"version": 1, "symbols": {}}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "symbols": {}}

    def _save(self) -> None:
        with self._lock:
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._cache, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self.cache_path)

    def _is_fresh(self, entry: dict) -> bool:
        """True if the entry is within the full TTL (no refetch needed at all)."""
        age = self._entry_age_seconds(entry)
        return age is not None and age < self.ttl_seconds

    def _needs_revalidation(self, entry: dict) -> bool:
        """True if the entry is older than ``revalidate_after_hours`` — serve
        it, but schedule a background refresh."""
        age = self._entry_age_seconds(entry)
        return age is None or age >= self.revalidate_seconds

    def _entry_age_seconds(self, entry: dict) -> float | None:
        ts = entry.get("fetched_at")
        if not ts:
            return None
        try:
            fetched = datetime.fromisoformat(ts)
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - fetched).total_seconds()

    # ── public API ───────────────────────────────────────────────────────
    def fetch_many(
        self,
        symbols: Iterable[str],
        names: dict[str, str] | None = None,
        force: bool = False,
    ) -> list[EarningsEvent]:
        """Return cached events immediately; refresh stale ones in background.

        ``force=True`` blocks and refetches every symbol from Yahoo (used by
        the manual Refresh button).
        """
        names = names or {}
        symbols = [s for s in {s.strip() for s in symbols} if s]
        events: list[EarningsEvent] = []
        must_fetch_now: list[str] = []      # blocking fetches (no cache / force)
        to_revalidate: list[str] = []       # background fetches (stale but usable)

        # Cache-first pass: always return whatever we have on disk.
        for sym in symbols:
            entry = self._cache.get("symbols", {}).get(sym)
            if force:
                must_fetch_now.append(sym)
                continue
            if not entry:
                must_fetch_now.append(sym)
                continue
            # We have *something* cached — serve it regardless of age.
            for e in entry.get("events", []):
                events.append(EarningsEvent(**{**e, "source": "cache"}))
            # …and schedule a background refresh if the data is getting old.
            if self._needs_revalidation(entry):
                to_revalidate.append(sym)

        # Blocking fetch path (empty cache / force=True).
        if must_fetch_now and yf is not None:
            events.extend(
                self._fetch_batch(must_fetch_now, names, blocking=True)
            )

        # Background refresh path (cache served, freshen asynchronously).
        if to_revalidate and yf is not None:
            self._spawn_background_refresh(to_revalidate, names)

        # ── NSE INDIA MERGE ──────────────────────────────────────────────
        # For every .NS-suffixed symbol, pull NSE's authoritative dates and
        # either (a) add missing upcoming/recent events, or (b) replace
        # stale Yahoo dates with NSE's current filings. Classifications for
        # NSE-only events come from OHLCV gap reaction (if reader available).
        if self._nse is not None:
            try:
                events = self._merge_nse_events(symbols, events)
            except Exception as e:
                print(f"[earnings] NSE merge failed: {e}", flush=True)

        return events

    # ── NSE merge ────────────────────────────────────────────────────────
    def _merge_nse_events(
        self,
        symbols: list[str],
        events: list[EarningsEvent],
    ) -> list[EarningsEvent]:
        """Overlay NSE India dates onto the Yahoo-based event list.

        NSE's event-calendar gives us accurate **upcoming** dates, and its
        financial-results feed gives us accurate **filing dates** for every
        recent quarter. We:

        * Add any NSE event that isn't already present (by symbol + date).
        * **Drop Yahoo's stale upcoming projections** when NSE has a
          confirmed upcoming event for the same symbol (Yahoo often
          extrapolates a wrong future date 3–6 weeks off).
        * Classify NSE-only events via OHLCV gap reaction when possible.
        """
        assert self._nse is not None
        india_syms = {s for s in symbols if s.endswith(".NS")}
        if not india_syms:
            return events

        today = datetime.now(timezone.utc).date()

        # Both global fetches are cheap (one HTTP each) and cached 6h.
        try:
            upcoming_map = self._nse.fetch_upcoming(days_ahead=60)
        except Exception:
            upcoming_map = {}
        try:
            recent_map = self._nse.fetch_recent_results()
        except Exception:
            recent_map = {}

        # Preserve existing display names so NSE events inherit the nice name
        # the user saw (e.g. "Anand Rathi Wealth" not "Financial Results").
        name_by_sym: dict[str, str] = {}
        for e in events:
            if e.name and e.symbol not in name_by_sym:
                name_by_sym[e.symbol] = e.name

        # STEP 1: For each Indian symbol with an NSE-confirmed upcoming, drop
        # any Yahoo-sourced UPCOMING we already have for it — Yahoo's
        # projection is almost certainly a wrong guess at the same event.
        india_with_nse_upcoming = {
            s for s in india_syms if upcoming_map.get(s[:-3])
        }
        if india_with_nse_upcoming:
            filtered: list[EarningsEvent] = []
            for e in events:
                if (
                    e.symbol in india_with_nse_upcoming
                    and e.status == "UPCOMING"
                    and (e.source or "").startswith(("yfinance", "cache"))
                ):
                    continue  # drop stale Yahoo projection
                filtered.append(e)
            events = filtered

        existing: set[tuple[str, str]] = {(e.symbol, e.date) for e in events}
        new_events: list[EarningsEvent] = []

        for yf_sym in india_syms:
            bare = yf_sym[:-3]  # strip .NS
            display_name = name_by_sym.get(yf_sym) or bare

            # STEP 2: Add NSE upcoming events.
            for ev in upcoming_map.get(bare, []) or []:
                key = (yf_sym, ev["date"])
                if key in existing:
                    continue
                try:
                    d = datetime.fromisoformat(ev["date"]).date()
                except Exception:
                    continue
                days_until = (d - today).days
                # The purpose string is the board-meeting subject — keep it
                # as tooltip text in the name.
                purpose = (ev.get("purpose") or "").strip()
                name = display_name
                if purpose and "dividend" in purpose.lower():
                    name = f"{display_name} · Results + Dividend"
                elif purpose and "fund raising" in purpose.lower():
                    name = f"{display_name} · Results + Fund Raising"
                new_events.append(EarningsEvent(
                    symbol=yf_sym,
                    name=name,
                    date=ev["date"],
                    status="UPCOMING" if days_until >= 0 else "UNKNOWN",
                    eps_estimate=None,
                    eps_reported=None,
                    surprise_pct=None,
                    gap_pct=None,
                    close_after_pct=None,
                    volume_ratio=None,
                    days_until=days_until,
                    source="nse-event-calendar",
                ))
                existing.add(key)

            # STEP 3: Add NSE recent-filing dates, classified via OHLCV gap.
            for ev in recent_map.get(bare, []) or []:
                key = (yf_sym, ev["date"])
                if key in existing:
                    continue
                try:
                    d = datetime.fromisoformat(ev["date"]).date()
                except Exception:
                    continue
                days_until = (d - today).days
                gap, close_after, vol_ratio = self._gap_from_ohlcv(yf_sym, d)
                # Without EPS numbers we rely purely on gap reaction.
                status = _classify(
                    days_until=days_until,
                    surprise_pct=None,
                    gap_pct=gap,
                    reported=1.0,  # we know a filing happened
                )
                quarter = (ev.get("quarter") or "").strip()
                new_events.append(EarningsEvent(
                    symbol=yf_sym,
                    name=display_name + (f" ({quarter})" if quarter else ""),
                    date=ev["date"],
                    status=status,
                    eps_estimate=None,
                    eps_reported=None,
                    surprise_pct=None,
                    gap_pct=_round(gap, 2),
                    close_after_pct=_round(close_after, 2),
                    volume_ratio=_round(vol_ratio, 2),
                    days_until=days_until,
                    source="nse-results",
                ))
                existing.add(key)

        return events + new_events

    def _gap_from_ohlcv(
        self, yf_sym: str, event_date
    ) -> tuple[float | None, float | None, float | None]:
        """Compute gap%, close%, volume-× from local OHLCV cache on event_date.

        Accepts either a ``list[dict]`` reader (fields: date, open, high, low,
        close, volume — the format used by ``_read_ohlcv`` in ``main.py``) or
        a pandas DataFrame with a DatetimeIndex. Returns ``(None, None, None)``
        if the reader isn't wired or data is missing. Purely local — no Yahoo
        round-trip.
        """
        if self._read_ohlcv is None:
            return (None, None, None)
        try:
            data = self._read_ohlcv(yf_sym)
        except Exception:
            return (None, None, None)
        if not data:
            return (None, None, None)

        target_iso = event_date.isoformat()

        # Path 1: list[dict] — the format used by main.py
        if isinstance(data, list):
            rows = sorted(
                (r for r in data if isinstance(r, dict) and r.get("date")),
                key=lambda r: r["date"],
            )
            if not rows:
                return (None, None, None)
            # first session on or after target
            idx = next(
                (i for i, r in enumerate(rows) if r["date"] >= target_iso),
                None,
            )
            if idx is None or idx == 0:
                return (None, None, None)
            prior = rows[idx - 1]
            report = rows[idx]
            try:
                prior_close = float(prior.get("close") or 0)
                r_open = float(report.get("open") or 0)
                r_close = float(report.get("close") or 0)
                r_vol = float(report.get("volume") or 0)
            except (TypeError, ValueError):
                return (None, None, None)
            gap = (r_open / prior_close - 1.0) * 100.0 if prior_close else None
            close_after = (r_close / prior_close - 1.0) * 100.0 if prior_close else None
            window = rows[max(0, idx - 20):idx]
            vols = [float(r.get("volume") or 0) for r in window]
            avg_vol = sum(vols) / len(vols) if vols else 0.0
            vol_ratio = (r_vol / avg_vol) if avg_vol else None
            return (gap, close_after, vol_ratio)

        # Path 2: pandas DataFrame (kept for compat)
        try:
            import pandas as pd  # type: ignore
            df = data
            if not isinstance(df.index, pd.DatetimeIndex):
                return (None, None, None)
            target = pd.Timestamp(event_date)
            on_or_after = df.index[df.index >= target]
            if len(on_or_after) == 0:
                return (None, None, None)
            report_ts = on_or_after[0]
            pos = df.index.get_loc(report_ts)
            if pos == 0:
                return (None, None, None)
            prior_ts = df.index[pos - 1]
            prior_close = float(df.loc[prior_ts, "Close"])
            r_open = float(df.loc[report_ts, "Open"])
            r_close = float(df.loc[report_ts, "Close"])
            r_vol = float(df.loc[report_ts, "Volume"])
            gap = (r_open / prior_close - 1.0) * 100.0 if prior_close else None
            close_after = (r_close / prior_close - 1.0) * 100.0 if prior_close else None
            vols = [float(v) for v in df["Volume"].iloc[max(0, pos - 20):pos].values]
            avg_vol = sum(vols) / len(vols) if vols else 0.0
            vol_ratio = (r_vol / avg_vol) if avg_vol else None
            return (gap, close_after, vol_ratio)
        except Exception:
            return (None, None, None)

    def prewarm(self, symbols: Iterable[str], names: dict[str, str] | None = None) -> None:
        """Fire-and-forget: fetch any missing / expired symbols in the
        background. Safe to call from FastAPI startup.
        """
        if yf is None:
            return
        names = names or {}
        symbols = [s for s in {s.strip() for s in symbols} if s]
        stale: list[str] = []
        for sym in symbols:
            entry = self._cache.get("symbols", {}).get(sym)
            if not entry or self._needs_revalidation(entry):
                stale.append(sym)
        if stale:
            self._spawn_background_refresh(stale, names)

    # ── background refresh plumbing ──────────────────────────────────────
    def _spawn_background_refresh(
        self, symbols: list[str], names: dict[str, str]
    ) -> None:
        """Launch a daemon thread that refreshes ``symbols`` without blocking
        the caller. Deduplicates against any refresh already in flight.
        """
        with self._inflight_lock:
            pending = [s for s in symbols if s not in self._inflight]
            if not pending:
                return
            self._inflight.update(pending)

        def _run() -> None:
            try:
                self._fetch_batch(pending, names, blocking=True)
            finally:
                with self._inflight_lock:
                    self._inflight.difference_update(pending)

        threading.Thread(
            target=_run,
            name=f"earnings-refresh-{len(pending)}",
            daemon=True,
        ).start()

    def _fetch_batch(
        self,
        symbols: list[str],
        names: dict[str, str],
        blocking: bool,
    ) -> list[EarningsEvent]:
        """Internal worker used by both blocking and background paths."""
        out: list[EarningsEvent] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {
                ex.submit(self._fetch_one, s, names.get(s, s)): s
                for s in symbols
            }
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    ev_list = fut.result()
                except Exception:
                    ev_list = []
                # Preserve previously cached events on failure — we never want
                # a bad Yahoo response to erase data we already have.
                existing = self._cache.get("symbols", {}).get(sym) or {}
                existing_events = existing.get("events") or []

                if ev_list:
                    self._cache.setdefault("symbols", {})[sym] = {
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "events": [asdict(e) for e in ev_list],
                    }
                elif existing_events:
                    # Keep old events, just update the timestamp so we retry
                    # again in one revalidate window, not immediately.
                    short_ts = datetime.now(timezone.utc) - timedelta(
                        seconds=max(0, self.ttl_seconds - self.revalidate_seconds)
                    )
                    self._cache.setdefault("symbols", {})[sym] = {
                        "fetched_at": short_ts.isoformat(),
                        "events": existing_events,
                    }
                else:
                    # No old data and fetch failed → short-TTL "tried" marker.
                    short_ts = datetime.now(timezone.utc) - timedelta(
                        seconds=max(0, self.ttl_seconds - 1800)
                    )
                    self._cache.setdefault("symbols", {})[sym] = {
                        "fetched_at": short_ts.isoformat(),
                        "events": [],
                    }
                if blocking:
                    out.extend(ev_list)
        self._save()
        return out

    # ── single symbol fetch ──────────────────────────────────────────────
    def _fetch_one(self, symbol: str, name: str) -> list[EarningsEvent]:
        if yf is None:
            return []
        # Tiny jitter to stagger the pool and soften Yahoo rate-limits.
        time.sleep(0.15 + (hash(symbol) % 100) / 400.0)
        ticker = yf.Ticker(symbol)
        today = datetime.now(timezone.utc).date()
        events: list[EarningsEvent] = []

        # 1. Earnings calendar (upcoming + trailing 4 quarters)
        try:
            df = ticker.get_earnings_dates(limit=8)
        except Exception as exc:
            # Log only unexpected errors; rate-limit / missing-symbol noise is
            # silenced to keep the server log readable.
            msg = str(exc)
            if "lxml" in msg or "Rate limited" in msg:
                print(f"[earnings] {symbol}: {msg[:120]}", flush=True)
            df = None

        if df is None or df.empty:
            return []

        # yfinance returns a tz-aware DatetimeIndex; normalise to date.
        for idx, row in df.iterrows():
            try:
                dt = idx.to_pydatetime()
            except Exception:
                continue
            event_date = dt.date()
            days_until = (event_date - today).days

            est = _safe_float(row.get("EPS Estimate"))
            rep = _safe_float(row.get("Reported EPS"))
            surprise = _safe_float(row.get("Surprise(%)"))
            if surprise is None and est and rep is not None and est != 0:
                surprise = (rep - est) / abs(est) * 100.0

            gap_pct, close_after_pct, vol_ratio = (None, None, None)
            if days_until < 0 and rep is not None:
                gap_pct, close_after_pct, vol_ratio = _price_reaction(
                    ticker, event_date
                )

            status = _classify(
                days_until=days_until,
                surprise_pct=surprise,
                gap_pct=gap_pct,
                reported=rep,
            )

            events.append(EarningsEvent(
                symbol=symbol,
                name=name,
                date=event_date.isoformat(),
                status=status,
                eps_estimate=est,
                eps_reported=rep,
                surprise_pct=_round(surprise, 2),
                gap_pct=_round(gap_pct, 2),
                close_after_pct=_round(close_after_pct, 2),
                volume_ratio=_round(vol_ratio, 2),
                days_until=days_until,
                source="yfinance",
            ))

        # Sort newest first, dedupe by date
        events.sort(key=lambda e: e.date, reverse=True)
        seen: set[str] = set()
        unique: list[EarningsEvent] = []
        for e in events:
            if e.date in seen:
                continue
            seen.add(e.date)
            unique.append(e)
        return unique[:8]


# ── classification + price helpers ───────────────────────────────────────
def _classify(
    *,
    days_until: int,
    surprise_pct: float | None,
    gap_pct: float | None,
    reported: float | None,
) -> str:
    if days_until > 0:
        return "UPCOMING"
    # already reported
    if reported is None and surprise_pct is None and gap_pct is None:
        return "UNKNOWN"
    # Prefer surprise-based classification; fall back to gap reaction.
    s = surprise_pct if surprise_pct is not None else 0.0
    g = gap_pct if gap_pct is not None else 0.0
    if s >= BEAT_SURPRISE_PCT or g >= BEAT_GAP_PCT:
        return "BEAT"
    if s <= MISS_SURPRISE_PCT or g <= MISS_GAP_PCT:
        return "MISS"
    return "INLINE"


def _price_reaction(ticker, event_date) -> tuple[float | None, float | None, float | None]:
    """Return (gap%, close-after%, vol-ratio) around ``event_date``.

    Uses a 30-day window ending 3 days after event. Tolerant of missing data.
    """
    try:
        start = event_date - timedelta(days=45)
        end = event_date + timedelta(days=5)
        hist = ticker.history(start=start, end=end, auto_adjust=False)
    except Exception:
        return (None, None, None)
    if hist is None or hist.empty:
        return (None, None, None)

    # Localise to date index for lookup
    try:
        hist.index = hist.index.date  # type: ignore[assignment]
    except Exception:
        pass

    dates = sorted(d for d in hist.index if d <= event_date + timedelta(days=3))
    if not dates:
        return (None, None, None)

    # Find the first session on or after event_date (announcement often after-hours)
    report_day = next((d for d in dates if d >= event_date), dates[-1])
    idx = dates.index(report_day)
    if idx == 0:
        return (None, None, None)

    prior = dates[idx - 1]
    try:
        prior_close = float(hist.loc[prior, "Close"])
        report_open = float(hist.loc[report_day, "Open"])
        report_close = float(hist.loc[report_day, "Close"])
        report_vol = float(hist.loc[report_day, "Volume"])
    except Exception:
        return (None, None, None)

    gap = (report_open / prior_close - 1.0) * 100.0 if prior_close else None
    close_after = (report_close / prior_close - 1.0) * 100.0 if prior_close else None

    # 20-day avg vol leading up to prior session
    try:
        prior_idx = dates.index(prior)
        window = dates[max(0, prior_idx - 19):prior_idx + 1]
        vols = [float(hist.loc[d, "Volume"]) for d in window if d in hist.index]
        avg_vol = sum(vols) / len(vols) if vols else 0.0
        vol_ratio = (report_vol / avg_vol) if avg_vol else None
    except Exception:
        vol_ratio = None

    return (gap, close_after, vol_ratio)


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _round(v: float | None, nd: int) -> float | None:
    return None if v is None else round(v, nd)


# ── aggregation used by the FastAPI endpoint ─────────────────────────────
def summarize(events: list[EarningsEvent]) -> dict:
    """Group events into actionable buckets for the dashboard."""
    buckets = {"upcoming": [], "beats": [], "misses": [], "inline": []}
    for e in events:
        d = asdict(e)
        if e.status == "UPCOMING":
            buckets["upcoming"].append(d)
        elif e.status == "BEAT":
            buckets["beats"].append(d)
        elif e.status == "MISS":
            buckets["misses"].append(d)
        elif e.status == "INLINE":
            buckets["inline"].append(d)

    buckets["upcoming"].sort(key=lambda x: x["days_until"])
    buckets["beats"].sort(
        key=lambda x: (x["surprise_pct"] or 0, x["gap_pct"] or 0),
        reverse=True,
    )
    buckets["misses"].sort(
        key=lambda x: (x["surprise_pct"] or 0, x["gap_pct"] or 0),
    )
    buckets["inline"].sort(key=lambda x: x["date"], reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "total": len(events),
            "upcoming": len(buckets["upcoming"]),
            "beats": len(buckets["beats"]),
            "misses": len(buckets["misses"]),
            "inline": len(buckets["inline"]),
        },
        "buckets": buckets,
    }

