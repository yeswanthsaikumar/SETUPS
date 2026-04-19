"""
fundamentals_provider.py
────────────────────────
Fetches and caches fundamental stock data from yfinance.
Returns a compact single-line summary per stock for the HTML report column:

  "EPS +23%QoQ +45%YoY | Rev +18%YoY | Debt ↓12% | PE 28 | MCap ₹4.2K Cr"

For US stocks the currency label is $ and MCap is shown in billions.
"""
from __future__ import annotations

import json
import logging
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("FundamentalsProvider")

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    logger.warning("yfinance not installed – fundamentals unavailable (pip install yfinance)")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "N/A" and v != "" and not (isinstance(v, float) and v != v):
            return v
    return default


def _pct(new, old) -> float | None:
    try:
        if old and old != 0:
            return round((new - old) / abs(old) * 100, 1)
    except Exception:
        pass
    return None


def _arrow(pct: float | None) -> str:
    if pct is None:
        return ""
    if pct >= 15:
        return "↑↑"
    if pct >= 5:
        return "↑"
    if pct <= -15:
        return "↓↓"
    if pct <= -5:
        return "↓"
    return "→"


# ── Core provider ─────────────────────────────────────────────────────────────

class FundamentalsProvider:
    def __init__(self, cache_dir: str = "cache", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=cache_ttl_hours)

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"fundamentals_{symbol.replace('/', '_')}.json"

    def _load_cache(self, symbol: str) -> dict | None:
        p = self._cache_path(symbol)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            cached_at = data.get("_cached_at")
            if cached_at and datetime.now() - datetime.fromisoformat(cached_at) < self.ttl:
                return data
        except Exception:
            pass
        return None

    def _save_cache(self, symbol: str, data: dict):
        data["_cached_at"] = datetime.now().isoformat()
        try:
            self._cache_path(symbol).write_text(json.dumps(data))
        except Exception:
            pass

    def _fetch_groww(self, symbol: str) -> dict | None:
        """Fetch fundamentals from Groww API. Returns dict or None on failure."""
        try:
            from groww_client import get_groww_client
        except ImportError:
            return None
        client = get_groww_client()
        if not client:
            return None
        try:
            from growwapi import GrowwAPI
            base_sym = symbol.replace(".NS", "").replace(".BO", "")
            exchange_sym = f"NSE_{base_sym}"

            # Get quote which includes fundamental data
            quote = client.get_quote(
                trading_symbol=base_sym,
                exchange=GrowwAPI.EXCHANGE_NSE,
                segment=GrowwAPI.SEGMENT_CASH,
                timeout=10,
            )
            if not quote or not isinstance(quote, dict):
                return None

            result: dict = {"symbol": symbol, "_source": "groww"}

            # Extract fields from Groww quote response
            # Groww returns various structures; extract what's available
            info = quote if isinstance(quote, dict) else {}

            result["sector"] = info.get("sector")
            result["industry"] = info.get("industry")
            result["currency"] = "INR"

            pe = info.get("pe") or info.get("trailingPE") or info.get("pe_ratio")
            result["pe"] = float(pe) if pe else None

            fwd_pe = info.get("forwardPE") or info.get("forward_pe")
            result["fwd_pe"] = float(fwd_pe) if fwd_pe else None

            mc = info.get("marketCap") or info.get("market_cap")
            result["market_cap"] = float(mc) if mc else None

            # EPS growth - may not be available from Groww quote
            result["eps_qoq"] = None
            result["eps_yoy"] = None

            eg = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
            if eg is not None:
                try:
                    result["eps_yoy"] = round(float(eg) * 100, 1) if abs(float(eg)) < 10 else round(float(eg), 1)
                except Exception:
                    pass

            rg = info.get("revenueGrowth")
            result["rev_yoy"] = round(float(rg) * 100, 1) if rg else None

            result["debt_trend_pct"] = None

            dy = info.get("dividendYield") or info.get("dividend_yield")
            result["div_yield"] = round(float(dy) * 100, 2) if dy else None

            # Only return if we got at least some useful data
            if result.get("pe") or result.get("market_cap") or result.get("sector"):
                return result
            return None
        except Exception:
            return None

    def fetch(self, symbol: str) -> dict:
        """Return a rich fundamentals dict for one symbol. Tries Groww first, yfinance as fallback."""
        cached = self._load_cache(symbol)
        if cached:
            return cached

        # Try Groww API first (primary source for NSE stocks)
        if symbol.endswith(".NS") or symbol.endswith(".BO") or not "." in symbol:
            result = self._fetch_groww(symbol)
            if result and not result.get("error"):
                self._save_cache(symbol, result)
                return result

        # Groww-only gate: for Indian symbols, no silent fallback to yfinance
        # (which routes through geo-blocked Yahoo and requires a VPN that
        # may itself be broken). Return an explicit "source_unavailable"
        # marker so the UI can prompt the user to fix Groww creds.
        try:
            from groww_client import should_use_non_groww_source
        except Exception:
            should_use_non_groww_source = lambda s: True
        if not should_use_non_groww_source(symbol):
            return {
                "symbol": symbol,
                "error": "groww_unavailable",
                "_source": "groww",
                "_hint": ("Groww-only mode is ON and Groww did not return "
                          "fundamentals. Verify credentials via "
                          "/api/groww/verify or set GROWW_ONLY=0 to restore "
                          "yfinance fallback."),
            }

        # Fallback to yfinance
        if not HAS_YFINANCE:
            return {"symbol": symbol, "error": "yfinance_unavailable"}

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                t = yf.Ticker(symbol)
                info = t.info or {}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

        result: dict[str, Any] = {"symbol": symbol}

        # ── Basic info ────────────────────────────────────────────────────────
        result["sector"]      = _safe(info, "sector")
        result["industry"]    = _safe(info, "industry")
        result["currency"]    = _safe(info, "currency", default="INR")
        result["pe"]          = _safe(info, "trailingPE", "forwardPE")
        result["fwd_pe"]      = _safe(info, "forwardPE")
        mc = _safe(info, "marketCap")
        result["market_cap"]  = mc

        # ── EPS / Earnings growth (use income_stmt instead of deprecated quarterly_earnings) ──
        eps_q_growth_qoq = None
        eps_q_growth_yoy = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                qf = t.quarterly_income_stmt
            if qf is not None and not qf.empty:
                eps_row = None
                for label in ["Net Income", "Net Income Common Stockholders", "Basic EPS", "Diluted EPS"]:
                    if label in qf.index:
                        eps_row = qf.loc[label].dropna()
                        break
                if eps_row is not None and len(eps_row) >= 2:
                    vals = eps_row.tolist()
                    eps_q_growth_qoq = _pct(vals[0], vals[1])
                if eps_row is not None and len(eps_row) >= 5:
                    eps_q_growth_yoy = _pct(vals[0], vals[4])
                elif eps_row is not None and len(eps_row) >= 4:
                    eps_q_growth_yoy = _pct(vals[0], vals[3])
        except Exception:
            pass

        # Fallback: use info fields
        if eps_q_growth_yoy is None:
            eg = _safe(info, "earningsQuarterlyGrowth")
            if eg is not None:
                try:
                    eps_q_growth_yoy = round(float(eg) * 100, 1)
                except Exception:
                    pass

        result["eps_qoq"] = eps_q_growth_qoq
        result["eps_yoy"] = eps_q_growth_yoy

        # ── Revenue growth ────────────────────────────────────────────────────
        rev_yoy = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                qfin = t.quarterly_financials
            if qfin is not None and not qfin.empty:
                rev_row = None
                for label in ["Total Revenue", "Revenue"]:
                    if label in qfin.index:
                        rev_row = qfin.loc[label].dropna()
                        break
                if rev_row is not None and len(rev_row) >= 5:
                    rev_yoy = _pct(rev_row.iloc[0], rev_row.iloc[4])
                elif rev_row is not None and len(rev_row) >= 4:
                    rev_yoy = _pct(rev_row.iloc[0], rev_row.iloc[3])
        except Exception:
            pass

        if rev_yoy is None:
            rg = _safe(info, "revenueGrowth")
            if rg is not None:
                try:
                    rev_yoy = round(float(rg) * 100, 1)
                except Exception:
                    pass

        result["rev_yoy"] = rev_yoy

        # ── Debt trend ────────────────────────────────────────────────────────
        debt_trend_pct = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                bs = t.quarterly_balance_sheet
            if bs is not None and not bs.empty:
                debt_row = None
                for label in ["Total Debt", "Long Term Debt", "LongTermDebt"]:
                    if label in bs.index:
                        debt_row = bs.loc[label].dropna()
                        break
                if debt_row is not None and len(debt_row) >= 2:
                    debt_trend_pct = _pct(debt_row.iloc[0], debt_row.iloc[1])
        except Exception:
            pass

        result["debt_trend_pct"] = debt_trend_pct

        # ── Dividend yield ────────────────────────────────────────────────────
        dy = _safe(info, "dividendYield")
        result["div_yield"] = round(dy * 100, 2) if dy else None

        self._save_cache(symbol, result)
        return result

    def fetch_batch(self, symbols: list[str], workers: int = 20, show_progress: bool = True) -> dict[str, dict]:
        """Fetch fundamentals for all symbols in parallel using a thread pool."""
        total = len(symbols)
        if total == 0:
            return {}

        # Split into cached vs. needs-fetch to avoid unnecessary threads
        needs_fetch = [s for s in symbols if self._load_cache(s) is None]
        cached_results = {s: self._load_cache(s) for s in symbols if s not in needs_fetch}

        if show_progress and needs_fetch:
            print(f"  Fetching fundamentals for {len(needs_fetch)} symbols "
                  f"({total - len(needs_fetch)} cached) …", flush=True)

        out: dict[str, dict] = dict(cached_results)

        if not needs_fetch:
            return out

        done = 0
        with ThreadPoolExecutor(max_workers=min(workers, len(needs_fetch))) as pool:
            futures = {pool.submit(self.fetch, sym): sym for sym in needs_fetch}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    out[sym] = future.result()
                except Exception as e:
                    out[sym] = {"symbol": sym, "error": str(e)}
                done += 1
                if show_progress and done % 50 == 0:
                    print(f"    fundamentals {done}/{len(needs_fetch)} …", flush=True)

        if show_progress and needs_fetch:
            print(f"  Fundamentals complete ({total} symbols)", flush=True)

        return out


# ── Compact single-line summary ───────────────────────────────────────────────

def compact_summary(f: dict, is_india: bool = True) -> str:
    """Return one-line fundamentals string for the HTML report column."""
    if not f or f.get("error"):
        return "—"

    parts: list[str] = []

    # EPS growth
    qoq = f.get("eps_qoq")
    yoy = f.get("eps_yoy")
    if qoq is not None or yoy is not None:
        eps_str = "EPS"
        if qoq is not None:
            sign = "+" if qoq >= 0 else ""
            eps_str += f" {_arrow(qoq)}{sign}{qoq:.0f}%QoQ"
        if yoy is not None:
            sign = "+" if yoy >= 0 else ""
            eps_str += f" {sign}{yoy:.0f}%YoY"
        parts.append(eps_str)

    # Revenue growth
    rv = f.get("rev_yoy")
    if rv is not None:
        sign = "+" if rv >= 0 else ""
        parts.append(f"Rev {_arrow(rv)}{sign}{rv:.0f}%YoY")

    # Debt trend
    dt = f.get("debt_trend_pct")
    if dt is not None:
        arrow = "↓" if dt <= -5 else ("↑" if dt >= 5 else "→")
        sign = "+" if dt >= 0 else ""
        parts.append(f"Debt {arrow}{sign}{dt:.0f}%")

    # PE
    pe = f.get("pe")
    if pe is not None:
        try:
            parts.append(f"PE {float(pe):.0f}")
        except Exception:
            pass

    # Market cap
    mc = f.get("market_cap")
    if mc:
        try:
            mc_f = float(mc)
            if is_india:
                # Convert to Crore (1 Cr = 10M)
                mc_cr = mc_f / 1e7
                if mc_cr >= 1000:
                    parts.append(f"MCap ₹{mc_cr/1000:.1f}K Cr")
                else:
                    parts.append(f"MCap ₹{mc_cr:.0f} Cr")
            else:
                mc_b = mc_f / 1e9
                parts.append(f"MCap ${mc_b:.1f}B")
        except Exception:
            pass

    return " | ".join(parts) if parts else "—"

