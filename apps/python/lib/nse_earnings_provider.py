"""NSE India earnings data adapter.

Provides the two endpoints that actually matter for the "avoid volatility /
enter after beat" workflow:

* **Event calendar** — upcoming Board Meetings flagged for "Financial
  Results". Canonical, authoritative, days-accurate.
* **Financial results** — recent quarterly results with net-profit figures.
  We use net-profit YoY delta as a proxy for "surprise" when Yahoo doesn't
  have an EPS estimate (very common for Indian mid/small-caps).

NSE's JSON API is notoriously picky about cookies/headers. We:

1. Bootstrap a requests.Session by hitting the homepage (sets ``nseappid`` +
   ``ak_bmsc`` cookies).
2. Re-bootstrap every 5 min because cookies expire fast.
3. Fetch **global** lists (all symbols at once) rather than per-symbol — one
   HTTP call covers every ticker in your positions + watchlist.

All results are cached to ``trade_data/nse_events_cache.json`` with a 6h TTL
so we hit NSE at most a few times per day.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore


NSE_HOME = "https://www.nseindia.com/"
NSE_EVENT_CAL = "https://www.nseindia.com/api/event-calendar"
NSE_RESULTS = "https://www.nseindia.com/api/corporates-financial-results"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

COOKIE_TTL_SECONDS = 300       # re-bootstrap cookies every 5 min
CACHE_TTL_SECONDS = 6 * 3600   # 6 h disk TTL
FINANCIAL_SUBJECT_KEYS = ("financial", "quarter", "results")


class NSEEarningsProvider:
    """Thin, thread-safe NSE JSON client with disk caching."""

    def __init__(self, cache_path: Path | str) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._session: Any = None
        self._cookie_ts: float = 0.0
        self._cache: dict = self._load_cache()

    # ── cookie / session bootstrap ────────────────────────────────────────
    def _get_session(self):
        if requests is None:
            return None
        with self._session_lock:
            now = time.time()
            if self._session is None or (now - self._cookie_ts) > COOKIE_TTL_SECONDS:
                s = requests.Session()
                s.headers.update(_HEADERS)
                try:
                    # NSE sets cookies on the homepage. 2 hits needed for some
                    # CDN variants (first returns 401, second 200).
                    s.get(NSE_HOME, timeout=8)
                    s.get(NSE_HOME, timeout=8)
                except Exception:
                    pass
                self._session = s
                self._cookie_ts = now
            return self._session

    # ── disk cache ────────────────────────────────────────────────────────
    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {"version": 1}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1}

    def _save_cache(self) -> None:
        with self._lock:
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._cache, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self.cache_path)

    def _cache_fresh(self, key: str) -> bool:
        entry = self._cache.get(key) or {}
        ts = entry.get("fetched_at")
        if not ts:
            return False
        try:
            age = time.time() - datetime.fromisoformat(ts).timestamp()
        except Exception:
            return False
        return age < CACHE_TTL_SECONDS

    def _cache_put(self, key: str, payload: Any) -> None:
        self._cache[key] = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self._save_cache()

    def _cache_get(self, key: str) -> Any:
        entry = self._cache.get(key) or {}
        return entry.get("payload")

    # ── HTTP helpers ──────────────────────────────────────────────────────
    def _get_json(self, url: str, params: dict, attempts: int = 3) -> Any:
        s = self._get_session()
        if s is None:
            return None
        last_err: Exception | None = None
        for i in range(attempts):
            try:
                r = s.get(url, params=params, timeout=12)
                if r.status_code == 200 and r.text:
                    return r.json()
                # Force a cookie refresh on 401/403
                if r.status_code in (401, 403):
                    self._cookie_ts = 0
                    s = self._get_session()
            except Exception as e:
                last_err = e
                self._cookie_ts = 0
            time.sleep(0.5 * (i + 1))
        if last_err:
            print(f"[nse] {url} failed: {last_err}", flush=True)
        return None

    # ── public API ────────────────────────────────────────────────────────
    def fetch_upcoming(
        self,
        days_ahead: int = 60,
        force: bool = False,
    ) -> dict[str, list[dict]]:
        """Return ``{SYMBOL: [event_dict, …]}`` for board meetings flagged as
        financial results in the next ``days_ahead`` days.

        One HTTP call covers every NSE-listed equity, so cheap even for
        hundreds of watchlist symbols.
        """
        key = f"upcoming:{days_ahead}"
        if not force and self._cache_fresh(key):
            return self._cache_get(key) or {}

        today = datetime.now()
        params = {
            "index": "equities",
            "from_date": today.strftime("%d-%m-%Y"),
            "to_date": (today + timedelta(days=days_ahead)).strftime("%d-%m-%Y"),
        }
        raw = self._get_json(NSE_EVENT_CAL, params)
        grouped: dict[str, list[dict]] = {}
        for item in (raw or []):
            subj = str(item.get("subject") or item.get("purpose") or "").lower()
            if not any(k in subj for k in FINANCIAL_SUBJECT_KEYS):
                continue
            sym = (item.get("symbol") or "").strip().upper()
            if not sym:
                continue
            # NSE returns date as "DD-MMM-YYYY" or ISO. Normalise → YYYY-MM-DD.
            date_str = (item.get("date") or item.get("bm_date") or "").strip()
            iso = _parse_nse_date(date_str)
            if not iso:
                continue
            grouped.setdefault(sym, []).append({
                "date": iso,
                "purpose": item.get("purpose") or item.get("subject") or "",
                "details": item.get("bm_desc") or item.get("details") or "",
                "source": "nse-event-calendar",
            })
        # Sort each bucket ascending by date
        for sym in grouped:
            grouped[sym].sort(key=lambda x: x["date"])
        self._cache_put(key, grouped)
        return grouped

    def fetch_recent_results(self, force: bool = False) -> dict[str, list[dict]]:
        """Return ``{SYMBOL: [result_dict, …]}`` for quarterly results filed
        with NSE. One API call returns every recent quarterly filing (~3–4k
        records); we bucket by symbol.

        The list endpoint gives **filing date + quarter period**, but not the
        P&L numbers themselves (those live inside the XBRL files linked from
        each record). Callers combine this with OHLCV-based gap reaction to
        classify beats/misses.
        """
        key = "recent_results"
        if not force and self._cache_fresh(key):
            return self._cache_get(key) or {}

        raw = self._get_json(
            NSE_RESULTS,
            {"index": "equities", "period": "Quarterly"},
        )
        grouped: dict[str, list[dict]] = {}
        for item in (raw or []):
            sym = (item.get("symbol") or "").strip().upper()
            if not sym:
                continue
            date_str = (
                item.get("filingDate")
                or item.get("broadCastDate")
                or item.get("exchdisstime")
                or ""
            )
            iso = _parse_nse_date(date_str)
            if not iso:
                continue
            grouped.setdefault(sym, []).append({
                "date": iso,
                "filing_datetime": date_str,
                "quarter": item.get("relatingTo") or "",
                "from_date": _parse_nse_date(item.get("fromDate") or ""),
                "to_date": _parse_nse_date(item.get("toDate") or ""),
                "financial_year": item.get("financialYear") or "",
                "audited": item.get("audited") or "",
                "consolidated": item.get("consolidated") or "",
                "xbrl_url": item.get("xbrl") or "",
                "source": "nse-results",
            })
        # Dedupe by date (NSE sometimes files both standalone + consolidated)
        for sym in grouped:
            seen: set[str] = set()
            out: list[dict] = []
            for ev in sorted(grouped[sym], key=lambda x: x["date"], reverse=True):
                if ev["date"] in seen:
                    continue
                seen.add(ev["date"])
                out.append(ev)
            grouped[sym] = out[:8]  # keep last 8 quarters max
        self._cache_put(key, grouped)
        return grouped


# ── helpers ──────────────────────────────────────────────────────────────
def _parse_nse_date(s: str) -> str | None:
    """Accept NSE's various date formats and return ISO (YYYY-MM-DD).

    Handles:
      * ``16-Jan-2025``            (pure date)
      * ``16-Jan-2025 19:42``      (filingDate)
      * ``16-Jan-2025 19:42:10``   (broadCastDate)
      * ``01-Oct-2024``            (quarter bounds)
      * ``2025-01-16``             (ISO)
      * Empty / ``None`` / ``"None"`` → returns ``None``.
    """
    if not s:
        return None
    s = str(s).strip()
    if s.lower() in ("none", "null", "na", "n/a", ""):
        return None
    # Strip any trailing time component — we only want the date for bucketing.
    date_part = s.split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y"):
        try:
            return datetime.strptime(date_part, fmt).date().isoformat()
        except ValueError:
            continue
    # Last-ditch ISO with timezone
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    if not s or s in ("-", "NA", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

