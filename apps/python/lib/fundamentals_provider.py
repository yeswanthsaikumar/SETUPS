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

    def fetch(self, symbol: str) -> dict:
        """Return a rich fundamentals dict for one symbol."""
        cached = self._load_cache(symbol)
        if cached:
            return cached

        if not HAS_YFINANCE:
            return {"symbol": symbol, "error": "yfinance_unavailable"}

        try:
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

        # ── EPS / Earnings growth ─────────────────────────────────────────────
        # Quarterly EPS: last 4 quarters from info or quarterly_earnings
        eps_q_growth_qoq = None
        eps_q_growth_yoy = None
        try:
            qe = t.quarterly_earnings
            if qe is not None and not qe.empty and "Earnings" in qe.columns:
                vals = qe["Earnings"].dropna().tolist()
                if len(vals) >= 2:
                    eps_q_growth_qoq = _pct(vals[-1], vals[-2])
                if len(vals) >= 5:
                    eps_q_growth_yoy = _pct(vals[-1], vals[-5])
                elif len(vals) >= 4:
                    eps_q_growth_yoy = _pct(vals[-1], vals[-4])
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
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                rev_row = None
                for label in ["Total Revenue", "Revenue"]:
                    if label in qf.index:
                        rev_row = qf.loc[label].dropna()
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

    def fetch_batch(self, symbols: list[str], delay_s: float = 0.3) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for sym in symbols:
            out[sym] = self.fetch(sym)
            time.sleep(delay_s)
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

