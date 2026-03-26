"""
stock_analyzer.py
─────────────────
Single-stock deep-dive analysis engine.

Searches all available scan output files for a given symbol and generates
a detailed, human-readable analysis using the rule-based deterministic logic
already computed by the Java scanner + Python pipeline.

Returned structure (dict):
  symbol         – canonical symbol (uppercased)
  found          – bool
  status         – 'PORTFOLIO_SHORTLIST' | 'ACTIVE_TRADE' | 'BREAKOUT' | 'WATCHLIST' | 'REJECTED' | 'NOT_FOUND'
  listType       – raw listType from scan data
  market         – market searched
  timeframe      – timeframe searched
  analysisSource – 'output' | 'live'
  scanData       – raw scan record (if found in any positive list)
  rejection      – raw rejection record (if rejected)
  summary        – one-line verdict sentence
  tradePlan      – dict with trade plan details (entry, stop, targets, risk/reward)
  setupAnalysis  – dict with detailed setup explanation
  regimeAnalysis – dict with market regime context
  rsAnalysis     – dict with relative-strength assessment
  volumeAnalysis – dict with volume/liquidity assessment
  mtfAnalysis    – dict with multi-timeframe alignment
  reasoning      – list[str] of step-by-step reasoning bullets
  actionVerdict  – 'BUY_NOW' | 'WATCH_CLOSELY' | 'AVOID' | 'DATA_MISSING'
  confidence     – 0–100
  rejectionDetail– detailed rejection explanation (if rejected)
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import to_float as _to_float

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> list[dict] | dict | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw
    except Exception:
        return None


def _search_list(rows: list[dict] | None, symbol_upper: str) -> dict | None:
    if not rows:
        return None
    for row in rows:
        if str(row.get("symbol", "")).upper() == symbol_upper:
            return row
    return None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _candidate_files(output_dir: Path, market: str, timeframe: str, setups: str) -> dict[str, list[Path]]:
    """Return candidate paths for each list type in priority order."""
    label_full   = f"{market}_{timeframe}_full"
    label_setups = f"{market}_{timeframe}_{setups}" if setups not in ("full", "all") else label_full
    label_base   = f"{market}_{timeframe}"

    def _paths(prefix: str) -> list[Path]:
        return [
            output_dir / f"{prefix}_{label_full}_LATEST.json",
            output_dir / f"{prefix}_{label_setups}_LATEST.json",
            output_dir / f"{prefix}_{label_base}_LATEST.json",
        ]

    return {
        "hits":      _paths("vcp_hits"),
        "watchlist": _paths("watchlist"),
        "open_trades": _paths("open_trades"),
        "portfolio": _paths("portfolio_shortlist"),
        "rejections": _paths("rejections"),
    }


def _search_outputs(
    output_dir: Path,
    symbol_upper: str,
    market: str,
    timeframe: str,
    setups: str,
) -> tuple[dict | None, str, str, Path | None, dict | None, Path | None]:
    candidate_paths = _candidate_files(output_dir, market, timeframe, setups)

    search_order = [
        ("portfolio", "PORTFOLIO_SHORTLIST"),
        ("hits", "BREAKOUT"),
        ("open_trades", "ACTIVE_TRADE"),
        ("watchlist", "WATCHLIST"),
    ]

    found_row: dict | None = None
    found_status = "NOT_FOUND"
    found_list_type = ""
    found_path: Path | None = None

    for key, status_label in search_order:
        for path in candidate_paths[key]:
            rows = _load_json(path)
            if isinstance(rows, list):
                hit = _search_list(rows, symbol_upper)
                if hit:
                    found_row = hit
                    found_status = status_label
                    found_list_type = str(hit.get("listType", status_label))
                    found_path = path
                    break
        if found_row:
            break

    rejection_row: dict | None = None
    rejection_path: Path | None = None
    if not found_row:
        for path in candidate_paths["rejections"]:
            rows = _load_json(path)
            if isinstance(rows, list):
                hit = _search_list(rows, symbol_upper)
                if hit:
                    rejection_row = hit
                    rejection_path = path
                    break

    return found_row, found_status, found_list_type, found_path, rejection_row, rejection_path


# ---------------------------------------------------------------------------
# Setup explanations
# ---------------------------------------------------------------------------

_SETUP_DESCRIPTIONS = {
    "VCP": (
        "Volatility Contraction Pattern (VCP) — A classic Minervini-style base where price "
        "contracts in progressively tighter waves with declining volume, forming a launchpad "
        "for a high-probability breakout above the pivot."
    ),
    "RANGE_EXPANSION": (
        "Range Expansion Setup — The stock has completed a tight consolidation phase with "
        "drying-up volume and is now expanding its range to the upside, signalling renewed "
        "institutional demand and potential for a sustained trend move."
    ),
    "MEAN_REVERSION": (
        "Mean Reversion Setup — Price has pulled back sharply to a statistically significant "
        "support level (Bollinger Band lower bound / SMA) while RSI is oversold, offering a "
        "counter-trend entry with a defined risk level and measured upside target."
    ),
}

_SUBTYPE_DESCRIPTIONS = {
    "BB_BOUNCE": "Bollinger Band bounce — price touched or violated the lower BB and is recovering.",
    "RSI_OVERSOLD": "RSI oversold bounce — momentum is at extreme oversold levels suggesting a snap-back.",
    "SMA_BOUNCE": "SMA support bounce — price is testing a key moving average from above.",
}

_RATING_DESCRIPTIONS = {
    "A+": "Exceptional (A+) — highest conviction; all criteria strongly met.",
    "A":  "Strong (A)  — nearly all criteria met; high-quality setup.",
    "B+": "Above-average (B+) — most criteria met with minor weaknesses.",
    "B":  "Average (B)  — setup is valid but has notable flaws; size conservatively.",
    "C":  "Below-average (C) — weak setup; consider skipping or minimal size.",
}


def _describe_rating(rating: str) -> str:
    return _RATING_DESCRIPTIONS.get(rating.upper(), f"Rating {rating}")


# ---------------------------------------------------------------------------
# Trade plan builder
# ---------------------------------------------------------------------------

def _build_trade_plan(row: dict) -> dict:
    entry  = _to_float(row.get("entry"))
    sl     = _to_float(row.get("sl"))
    t1     = _to_float(row.get("T1"))
    t2     = _to_float(row.get("T2"))
    t3     = _to_float(row.get("T3"))
    close  = _to_float(row.get("close"))
    pivot  = _to_float(row.get("pivot"))
    shares = _to_float(row.get("shares"))
    dist   = _to_float(row.get("dist%"))

    risk_per_share = max(0.0, entry - sl) if entry > sl else 0.0
    rr_t1 = round((t1 - entry) / risk_per_share, 2) if risk_per_share > 0 and t1 > entry else None
    rr_t2 = round((t2 - entry) / risk_per_share, 2) if risk_per_share > 0 and t2 > entry else None
    rr_t3 = round((t3 - entry) / risk_per_share, 2) if risk_per_share > 0 and t3 > entry else None

    return {
        "currentPrice": round(close, 2) if close else None,
        "pivotPrice":   round(pivot, 2) if pivot else None,
        "entryPrice":   round(entry, 2) if entry else None,
        "stopLoss":     round(sl, 2) if sl else None,
        "target1":      round(t1, 2) if t1 else None,
        "target2":      round(t2, 2) if t2 else None,
        "target3":      round(t3, 2) if t3 else None,
        "riskPerShare": round(risk_per_share, 2) if risk_per_share else None,
        "rrT1":         rr_t1,
        "rrT2":         rr_t2,
        "rrT3":         rr_t3,
        "suggestedShares": int(shares) if shares else None,
        "distFromPivotPct": round(dist, 2) if dist else None,
    }


# ---------------------------------------------------------------------------
# Detailed reasoning generator
# ---------------------------------------------------------------------------

def _explain_rejection(reason: str, detail: str) -> tuple[str, list[str]]:
    """Returns (short_summary, [detailed_bullets])."""
    r = reason.upper()
    bullets: list[str] = []

    if r in ("NO_BREAKOUT_OR_QUALITY", "LOW_QUALITY"):
        summary = "Setup quality is insufficient — no valid pattern detected."
        bullets = [
            "❌ The scanner could not identify a qualifying VCP, Range Expansion, or Mean Reversion "
            "pattern in the recent price history.",
            "📋 The stock may be in a stage 3 or 4 decline, in a wide and loose base, or simply "
            "hasn't formed the tight contraction required.",
            "💡 Tip: Check back after the stock builds a new base with contracting volatility and "
            "drying volume for at least 3–6 weeks.",
        ]
    elif r == "BELOW_MA":
        summary = "Stock is trading below its key moving average — uptrend is broken."
        bullets = [
            "❌ Price is below the configured trend-filter moving average at the base end.",
            "📋 Rule: The scanner requires the stock to be in a structural uptrend (price above MA). "
            "Trading below MA indicates bearish momentum or distribution.",
            f"📊 Detail: {detail}" if detail else "",
            "💡 Tip: The stock must reclaim and hold above the MA before it qualifies as a buyable setup.",
        ]
    elif r == "FAR_FROM_52W_HIGH":
        summary = "Stock is too far below its 52-week high — not actionable yet."
        bullets = [
            "❌ Price is more than the maximum allowed distance below its trailing 52-week high.",
            "📋 Rule: Setups must form near the 52-week high, confirming institutional sponsorship "
            "and relative strength. Bases formed deep in a downtrend are excluded.",
            f"📊 Detail: {detail}" if detail else "",
            "💡 Tip: Wait for the stock to regain its highs and build a proper stage-2 base.",
        ]
    elif r == "LOW_PRICE":
        summary = "Stock price is below the minimum price filter — penny stock excluded."
        bullets = [
            "❌ The closing price is below the configured minimum price threshold.",
            "📋 Rule: Very low-priced stocks are excluded due to wide spreads, manipulation risk, "
            "and difficulty achieving consistent institutional execution.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    elif r == "LOW_VOLUME":
        summary = "Average trading volume is too low for reliable execution."
        bullets = [
            "❌ The stock failed the minimum average-volume filter.",
            "📋 Thinly traded names can have poor fills, higher slippage, and unstable breakout behavior.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    elif r == "LOW_ADV":
        summary = "Average dollar volume is too low for institutional-quality liquidity."
        bullets = [
            "❌ The stock failed the average dollar-volume filter.",
            "📋 Even if share volume looks acceptable, low dollar turnover can still make entries and exits difficult.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    elif r == "INSUFFICIENT_DATA":
        summary = "Insufficient price history — not enough data to evaluate."
        bullets = [
            "❌ The scanner could not load enough historical candles for this symbol.",
            "📋 This usually means the stock is newly listed, has very thin trading, or the "
            "cache file is missing/corrupt.",
            "💡 Tip: Ensure the symbol is spelled correctly (e.g., 'RELIANCE.NS' for NSE stocks).",
        ]
    elif r == "DATA_UNAVAILABLE":
        summary = "Price data is unavailable in the local cache for live analysis."
        bullets = [
            "❌ The live analyzer could not load sufficient historical bars from cache.",
            "📋 The system attempted to reuse the existing scan logic, but no usable cached dataset was available.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    elif r == "DATA_ERROR":
        summary = "Data error encountered while processing this symbol."
        bullets = [
            "❌ An error occurred while loading or processing price data.",
            f"📊 Detail: {detail}" if detail else "",
            "💡 Tip: The symbol may be delisted, suspended, or have corrupted cache data.",
        ]
    elif r == "REGIME_UNFAVORABLE":
        summary = "Market regime filter blocked the setup under current breadth conditions."
        bullets = [
            "❌ The stock may have a valid pattern, but the overall market regime was not supportive enough.",
            "📋 In hard/strict regime mode, the scanner can reject otherwise valid setups when market breadth is weak.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    elif r == "TOO_FAR_FROM_PIVOT":
        summary = "Stock is too far below its pivot — not on watchlist."
        bullets = [
            "❌ The stock has a valid base, but the current price is too far below the pivot level "
            "to qualify for the watchlist.",
            "📋 Rule: The watchlist only includes stocks within the configured maximum distance "
            "from the pivot to avoid chasing extended moves.",
            f"📊 Detail: {detail}" if detail else "",
            "💡 Tip: Monitor for the stock to work its way closer to the pivot on lower volume.",
        ]
    elif r == "ALREADY_BROKEN_OUT":
        summary = "Stock has already broken out — moved to active/breakout list."
        bullets = [
            "ℹ️ The stock already triggered the breakout condition and is now on the active trades "
            "list rather than the watchlist.",
            "📋 If you see this on the watchlist rejection, it means the stock graduated from "
            "watchlist to open-trade status.",
        ]
    elif r == "NO_BREAKOUT":
        summary = "Setup is valid but breakout not yet confirmed."
        bullets = [
            "⏳ The stock has a qualifying base structure, but the price has not yet surged above "
            "the pivot on expanding volume.",
            "📋 Rule: A breakout requires price to exceed the pivot with volume at least 1.5–2× "
            "the 20-day average, confirming institutional participation.",
            "💡 Tip: This is a watchlist candidate. Set an alert at the pivot price.",
        ]
    elif r == "INSUFFICIENT_VOLUME":
        summary = "Volume confirmation insufficient — breakout lacks institutional participation."
        bullets = [
            "❌ Price may have crossed the pivot, but volume did not confirm the move.",
            "📋 Rule: Breakouts without volume expansion are high-failure-rate. The scanner "
            "requires volume to significantly exceed the 20-day average on the breakout bar.",
            f"📊 Detail: {detail}" if detail else "",
            "💡 Tip: Wait for a breakout day with 2× or more average volume before entering.",
        ]
    elif r == "ATR_EXPANDING":
        summary = "ATR (volatility) is expanding — base is not tightening."
        bullets = [
            "❌ Instead of contracting, the Average True Range is growing — the base is getting "
            "wider and looser, the opposite of what a VCP requires.",
            "📋 Rule: A valid VCP must show progressively shrinking volatility waves. Expanding "
            "ATR indicates indecision, distribution, or trapped longs.",
            f"📊 Detail: {detail}" if detail else "",
        ]
    else:
        summary = f"Rejected: {reason}"
        bullets = [
            f"📋 Rejection code: {reason}",
            f"📊 Detail: {detail}" if detail else "No additional detail available.",
        ]

    return summary, [b for b in bullets if b]


def _build_regime_analysis(row: dict) -> dict:
    regime_score  = _to_float(row.get("regimeScore"))
    regime_state  = str(row.get("regimeState", "UNKNOWN")).upper()
    regime_support = str(row.get("regimeSupport", "")).upper()

    if regime_state == "FAVORABLE":
        regime_text = "Market regime is FAVORABLE — broad market tailwind supports breakout follow-through."
        regime_emoji = "🟢"
    elif regime_state == "NEUTRAL":
        regime_text = "Market regime is NEUTRAL — neither strongly tailwind nor headwind; size moderately."
        regime_emoji = "🟡"
    elif regime_state == "UNFAVORABLE":
        regime_text = "Market regime is UNFAVORABLE — broad market headwind; breakout failure risk is elevated."
        regime_emoji = "🔴"
    else:
        regime_text = f"Market regime: {regime_state}"
        regime_emoji = "⚪"

    support_text = ""
    if regime_support == "TAILWIND":
        support_text = "Regime provides a tailwind — ideal environment for position entries."
    elif regime_support == "HEADWIND":
        support_text = "Regime is a headwind — consider reducing position size or waiting for improvement."
    elif regime_support == "NEUTRAL":
        support_text = "Regime is neutral — standard sizing applies."

    return {
        "score":      round(regime_score, 2),
        "state":      regime_state,
        "support":    regime_support,
        "emoji":      regime_emoji,
        "summary":    regime_text,
        "supportText": support_text,
    }


def _build_rs_analysis(row: dict) -> dict:
    rs3m  = _to_float(row.get("rs3m"))
    rs6m  = _to_float(row.get("rs6m"))
    rs12m = _to_float(row.get("rs12m"))
    rs_score = _to_float(row.get("rsScore"))
    rs_rank  = _to_float(row.get("rsRankScore"))

    bullets: list[str] = []
    if rs_score >= 80:
        bullets.append(f"🚀 RS Score {rs_score:.1f} — top-tier relative strength vs. universe.")
    elif rs_score >= 60:
        bullets.append(f"✅ RS Score {rs_score:.1f} — above-average relative strength.")
    elif rs_score >= 40:
        bullets.append(f"⚠️  RS Score {rs_score:.1f} — mediocre relative strength; prefer leaders.")
    else:
        bullets.append(f"❌ RS Score {rs_score:.1f} — weak relative strength; stock is lagging.")

    if rs3m > 0:
        bullets.append(f"📅 RS 3-month: {rs3m:.1f}th percentile")
    if rs6m > 0:
        bullets.append(f"📅 RS 6-month: {rs6m:.1f}th percentile")
    if rs12m > 0:
        bullets.append(f"📅 RS 12-month: {rs12m:.1f}th percentile")

    return {
        "rs3m":    round(rs3m, 2),
        "rs6m":    round(rs6m, 2),
        "rs12m":   round(rs12m, 2),
        "rsScore": round(rs_score, 2),
        "rsRank":  round(rs_rank, 2),
        "bullets": bullets,
    }


def _build_volume_analysis(row: dict) -> dict:
    avg_vol  = _to_float(row.get("avgVol20"))
    avg_dv   = _to_float(row.get("avgDollarVol20"))
    vol_dry  = _to_float(row.get("volumeDryUpRatio"))
    vol_score = _to_float(row.get("volumeDryUpScore"))
    vol_pct  = _to_float(row.get("vol%"))

    bullets: list[str] = []
    if avg_vol > 0:
        bullets.append(f"📊 Avg 20-day volume: {avg_vol:,.0f} shares")
    if avg_dv > 0:
        bullets.append(f"💰 Avg 20-day dollar volume: ₹{avg_dv:,.0f}" if ".NS" in str(row.get("symbol", "")) else f"💰 Avg 20-day dollar volume: ${avg_dv:,.0f}")

    if vol_dry > 0:
        if vol_dry < 0.8:
            bullets.append(f"✅ Volume dry-up confirmed (ratio {vol_dry:.2f}x) — smart money quiet accumulation.")
        elif vol_dry < 1.2:
            bullets.append(f"🟡 Volume dry-up mild (ratio {vol_dry:.2f}x) — acceptable but prefer tighter dry-up.")
        else:
            bullets.append(f"⚠️  Volume dry-up not confirmed (ratio {vol_dry:.2f}x) — higher-than-desired volume during base.")

    if vol_pct != 0:
        if vol_pct > 0:
            bullets.append(f"📈 Breakout bar volume: {vol_pct:.1f}% above average — strong institutional participation.")
        else:
            bullets.append(f"📉 Breakout bar volume: {abs(vol_pct):.1f}% below average — weak volume on breakout.")

    return {
        "avgVol20":       int(avg_vol) if avg_vol else None,
        "avgDollarVol20": round(avg_dv, 0) if avg_dv else None,
        "dryUpRatio":     round(vol_dry, 3) if vol_dry else None,
        "dryUpScore":     round(vol_score, 2) if vol_score else None,
        "bullets":        bullets,
    }


def _build_mtf_analysis(row: dict) -> dict:
    weekly_agreement = str(row.get("weeklyAgreement", "UNKNOWN")).upper()
    weekly_score     = _to_float(row.get("weeklyAgreementScore"))

    if weekly_agreement == "STRONG":
        text  = "✅ Weekly chart strongly agrees — multi-timeframe alignment confirmed."
        emoji = "✅"
    elif weekly_agreement == "MIXED":
        text  = "🟡 Weekly chart is mixed — daily setup is valid but lacks weekly confirmation."
        emoji = "🟡"
    elif weekly_agreement == "DISAGREE":
        text  = "❌ Weekly chart disagrees — consider avoiding or reducing size."
        emoji = "❌"
    else:
        text  = f"Weekly alignment: {weekly_agreement}"
        emoji = "⚪"

    return {
        "weeklyAgreement": weekly_agreement,
        "weeklyScore":     round(weekly_score, 2),
        "emoji":           emoji,
        "summary":         text,
    }


def _compute_confidence(row: dict, status: str) -> int:
    """Compute a 0–100 confidence score from the scan data."""
    score = 0

    # Base score from status
    if status == "BREAKOUT":
        score += 40
    elif status == "ACTIVE_TRADE":
        score += 45
    elif status == "PORTFOLIO_SHORTLIST":
        score += 50
    elif status == "WATCHLIST":
        score += 25

    # Rating boost
    rating = str(row.get("rating", "")).upper().strip()
    if rating == "A+":
        score += 20
    elif rating == "A":
        score += 15
    elif rating == "B+":
        score += 10
    elif rating == "B":
        score += 5

    # RS
    rs_score = _to_float(row.get("rsScore"))
    if rs_score >= 80:
        score += 15
    elif rs_score >= 60:
        score += 8
    elif rs_score >= 40:
        score += 3

    # Regime
    regime_state = str(row.get("regimeState", "")).upper()
    if regime_state == "FAVORABLE":
        score += 10
    elif regime_state == "NEUTRAL":
        score += 5
    elif regime_state == "UNFAVORABLE":
        score -= 10

    # Weekly agreement
    weekly = str(row.get("weeklyAgreement", "")).upper()
    if weekly == "STRONG":
        score += 10
    elif weekly == "MIXED":
        score += 0
    elif weekly == "DISAGREE":
        score -= 10

    # Volume dry-up
    dry_ratio = _to_float(row.get("volumeDryUpRatio"))
    if 0 < dry_ratio < 0.8:
        score += 5

    return max(0, min(100, score))


def _build_setup_analysis(row: dict) -> dict:
    setup     = str(row.get("setup", "UNKNOWN")).upper()
    subtype   = str(row.get("setupSubtype", row.get("mrSubtype", ""))).upper()
    window    = str(row.get("window", ""))
    height_pct = _to_float(row.get("height%"))
    depth_pct  = _to_float(row.get("depth%"))
    contractions = str(row.get("ctr", ""))
    score_val    = _to_float(row.get("score"))
    quality_score = _to_float(row.get("watchlistQualityScore", row.get("rankingScore")))
    pivot_fresh  = str(row.get("pivotFreshness", "")).upper()
    days_near    = int(_to_float(row.get("daysNearPivot")))
    pivot_prox_score = _to_float(row.get("pivotProximityScore"))

    description = _SETUP_DESCRIPTIONS.get(setup, f"{setup} pattern detected.")
    subtype_desc = _SUBTYPE_DESCRIPTIONS.get(subtype, "")

    bullets: list[str] = [description]
    if subtype_desc:
        bullets.append(f"  ↳ Subtype: {subtype_desc}")

    if window:
        bullets.append(f"📐 Consolidation window: {window}")
    if height_pct:
        bullets.append(f"📏 Base height: {height_pct:.1f}% (the depth of the prior trend move forming the base)")
    if depth_pct and setup != "MEAN_REVERSION":
        bullets.append(f"📉 Correction depth: {depth_pct:.1f}%")
    if contractions and contractions not in ("0", "0/0"):
        bullets.append(f"🌊 Wave contractions: {contractions} — progressive tightening confirmed.")
    if score_val:
        bullets.append(f"⭐ Raw quality score: {score_val:.1f}")

    freshness_text = {
        "ACTIVE":  "✅ Pivot is ACTIVE — setup is fresh and actionable.",
        "FADING":  "⚠️  Pivot is FADING — setup is ageing; urgency is increasing.",
        "EXPIRED": "❌ Pivot is EXPIRED — setup has been running too long; risk of failure rises.",
        "FRESH":   "✅ Pivot is FRESH — ideal; stock just broke out.",
    }.get(pivot_fresh, "")
    if freshness_text:
        bullets.append(freshness_text)
    if days_near > 0:
        bullets.append(f"📅 Days spent near pivot: {days_near}")

    # MR-specific
    mr_rsi = row.get("mrRsi")
    mr_lower_bb = row.get("mrLowerBB")
    mr_sma20 = row.get("mrSma20")
    if mr_rsi:
        bullets.append(f"📊 RSI: {mr_rsi} — {'oversold' if _to_float(mr_rsi) < 35 else 'neutral'}")
    if mr_lower_bb:
        bullets.append(f"📊 Lower Bollinger Band: {mr_lower_bb}")

    return {
        "setup":        setup,
        "subtype":      subtype,
        "window":       window,
        "description":  description,
        "bullets":      bullets,
        "score":        round(score_val, 2),
        "qualityScore": round(quality_score, 2) if quality_score else None,
    }


def _status_summary(
    *,
    symbol_upper: str,
    found_status: str,
    rating: str,
    setup_type: str,
    trade_plan: dict,
) -> str:
    entry = trade_plan.get("entryPrice")
    sl = trade_plan.get("stopLoss")
    t1 = trade_plan.get("target1")
    rr_t1 = trade_plan.get("rrT1")
    dist = trade_plan.get("distFromPivotPct")

    if found_status == "PORTFOLIO_SHORTLIST":
        return (
            f"{symbol_upper} is in the PORTFOLIO SHORTLIST with a {rating}-rated {setup_type} setup. "
            f"Entry ~{entry}, Stop ~{sl}, Target1 ~{t1}"
            + (f" (R:R {rr_t1:.2f}x)" if rr_t1 else "") + "."
        )
    if found_status == "ACTIVE_TRADE":
        return (
            f"{symbol_upper} is an ACTIVE trade with a {rating}-rated {setup_type} setup. "
            f"Manage risk around Stop ~{sl}; next objective ~{t1}"
            + (f" (R:R {rr_t1:.2f}x from entry)" if rr_t1 else "") + "."
        )
    if found_status == "BREAKOUT":
        if dist and dist > 0:
            return (
                f"{symbol_upper} has a fresh {rating}-rated {setup_type} breakout candidate "
                f"({dist:.1f}% below pivot). Entry ~{entry}, Stop ~{sl}, Target1 ~{t1}"
                + (f" (R:R {rr_t1:.2f}x)" if rr_t1 else "") + "."
            )
        return (
            f"{symbol_upper} has a {rating}-rated {setup_type} breakout signal. "
            f"Entry ~{entry}, Stop ~{sl}, Target1 ~{t1}"
            + (f" (R:R {rr_t1:.2f}x)" if rr_t1 else "") + "."
        )
    # WATCHLIST
    if dist is not None:
        return (
            f"{symbol_upper} is on WATCHLIST with a {rating}-rated {setup_type} setup, "
            f"currently {abs(dist):.1f}% {'below' if dist >= 0 else 'above'} pivot."
        )
    return f"{symbol_upper} is on WATCHLIST with a {rating}-rated {setup_type} setup."


def _status_reasoning_header(symbol_upper: str, found_status: str, found_list_type: str) -> str:
    if found_status == "PORTFOLIO_SHORTLIST":
        return f"✅ {symbol_upper} is shortlisted for portfolio allocation ({found_list_type})."
    if found_status == "ACTIVE_TRADE":
        return f"✅ {symbol_upper} is in ACTIVE_TRADE state ({found_list_type}) — focus shifts from entry to risk management."
    if found_status == "BREAKOUT":
        return f"✅ {symbol_upper} has a BREAKOUT-state setup ({found_list_type})."
    return f"⏳ {symbol_upper} is on WATCHLIST ({found_list_type}) awaiting trigger confirmation."


def _status_execution_bullets(
    found_status: str,
    trade_plan: dict,
    regime_state: str,
    weekly_agree: str,
) -> list[str]:
    out: list[str] = []
    entry = trade_plan.get("entryPrice")
    sl = trade_plan.get("stopLoss")
    t1 = trade_plan.get("target1")
    dist = trade_plan.get("distFromPivotPct")

    if found_status in {"PORTFOLIO_SHORTLIST", "ACTIVE_TRADE", "BREAKOUT"}:
        out.append(
            f"🧭 Execution: Use Entry {entry} and Stop {sl} as the primary invalidation framework; first objective is {t1}."
            if entry and sl and t1
            else "🧭 Execution: Manage risk around the provided stop and follow staged exits at target levels."
        )
        if found_status == "ACTIVE_TRADE":
            out.append("📌 Active-trade discipline: Avoid adding size if the stock is extended from pivot; prioritize stop adherence.")
        if found_status == "PORTFOLIO_SHORTLIST":
            out.append("📌 Portfolio context: This symbol passed quality + heat constraints, so sizing can follow normal model limits.")
    else:
        if dist is not None and dist > 0:
            out.append(f"📌 Trigger condition: Price is still {dist:.1f}% below pivot; wait for a decisive breakout with volume confirmation.")
        elif dist is not None and dist < 0:
            out.append(f"📌 Trigger condition: Price is {abs(dist):.1f}% above pivot; avoid late chase and wait for constructive re-entry.")
        else:
            out.append("📌 Trigger condition: Keep this on alert for pivot break with volume expansion before entry.")

    if regime_state == "UNFAVORABLE":
        out.append("⚠️ Regime overlay: Market headwind is active; reduce risk or require tighter confirmations.")
    if weekly_agree in {"DISAGREE", "WEAK"}:
        out.append("⚠️ Timeframe overlay: Weekly alignment is weak/disagreeing; treat the setup as lower-conviction.")
    return out


def _analysis_from_found_row(
    *,
    found_row: dict,
    found_status: str,
    found_list_type: str,
    symbol_upper: str,
    market: str,
    timeframe: str,
    setups_norm: str,
    metadata: dict[str, Any] | None = None,
) -> dict:
    trade_plan = _build_trade_plan(found_row)
    setup_analysis = _build_setup_analysis(found_row)
    regime = _build_regime_analysis(found_row)
    rs_analysis = _build_rs_analysis(found_row)
    volume = _build_volume_analysis(found_row)
    mtf = _build_mtf_analysis(found_row)
    confidence = _compute_confidence(found_row, found_status)
    rating = str(found_row.get("rating", "")).upper().strip()
    setup_type = setup_analysis["setup"]

    summary = _status_summary(
        symbol_upper=symbol_upper,
        found_status=found_status,
        rating=rating,
        setup_type=setup_type,
        trade_plan=trade_plan,
    )

    regime_state = regime["state"]
    weekly_agree = mtf["weeklyAgreement"]

    if found_status in ("BREAKOUT", "ACTIVE_TRADE", "PORTFOLIO_SHORTLIST"):
        action_verdict = "CAUTION" if regime_state == "UNFAVORABLE" else "BUY_NOW"
    elif found_status == "WATCHLIST":
        action_verdict = "WATCH_CLOSELY"
    else:
        action_verdict = "AVOID"

    reasoning: list[str] = [
        _status_reasoning_header(symbol_upper, found_status, found_list_type),
        f"📋 Setup: {setup_analysis['description']}",
        f"⭐ Rating: {_describe_rating(rating)}",
        f"🏦 {regime['summary']}",
    ]
    if regime["supportText"]:
        reasoning.append(f"   ↳ {regime['supportText']}")
    rs_bullets = rs_analysis.get("bullets", [])
    volume_bullets = volume.get("bullets", [])
    reasoning.extend(rs_bullets)
    reasoning.append(f"🔄 {mtf['summary']}")
    reasoning.extend(volume_bullets[:3])
    reasoning.extend(_status_execution_bullets(found_status, trade_plan, regime_state, weekly_agree))

    result = {
        "symbol": symbol_upper,
        "found": True,
        "status": found_status,
        "listType": found_list_type,
        "market": market,
        "timeframe": timeframe,
        "setups": setups_norm,
        "scanData": found_row,
        "rejection": None,
        "summary": summary,
        "tradePlan": trade_plan,
        "setupAnalysis": setup_analysis,
        "regimeAnalysis": regime,
        "rsAnalysis": rs_analysis,
        "volumeAnalysis": volume,
        "mtfAnalysis": mtf,
        "reasoning": reasoning,
        "actionVerdict": action_verdict,
        "confidence": confidence,
        "rejectionDetail": None,
    }
    if metadata:
        result.update(metadata)
    return result


def _analysis_from_rejection(
    *,
    rejection_row: dict,
    symbol_upper: str,
    market: str,
    timeframe: str,
    setups_norm: str,
    metadata: dict[str, Any] | None = None,
) -> dict:
    reason = str(rejection_row.get("reason", "UNKNOWN"))
    detail = str(rejection_row.get("detail", ""))
    source = str(rejection_row.get("source", "")).upper().strip()
    rej_summary, rej_bullets = _explain_rejection(reason, detail)

    follow_up: list[str] = []
    r = reason.upper()
    if r in {"NO_BREAKOUT_OR_QUALITY", "LOW_QUALITY", "NO_BREAKOUT", "TOO_FAR_FROM_PIVOT"}:
        follow_up.append("🛠️ Next step: Keep the symbol on passive watch and re-check after a new tightening base forms.")
    elif r in {"LOW_VOLUME", "LOW_ADV", "LOW_PRICE"}:
        follow_up.append("🛠️ Next step: Skip for now; liquidity filters are structural and usually not short-term fixes.")
    elif r in {"INSUFFICIENT_DATA", "DATA_UNAVAILABLE", "DATA_ERROR"}:
        follow_up.append("🛠️ Next step: Refresh cache/data and verify symbol formatting before re-running analysis.")
    elif r in {"REGIME_UNFAVORABLE", "FAR_FROM_52W_HIGH", "BELOW_MA"}:
        follow_up.append("🛠️ Next step: Wait for market/structure improvement before considering any entry.")
    else:
        follow_up.append("🛠️ Next step: Treat as non-actionable until a fresh scan returns a positive list status.")

    reasoning = [
        f"❌ {symbol_upper} was REJECTED by the rule-based scanner.",
        f"📋 Rejection reason: {reason}",
        f"🧾 Rejection source: {source}" if source else "",
    ] + rej_bullets + follow_up
    reasoning = [b for b in reasoning if b]

    result = {
        "symbol": symbol_upper,
        "found": False,
        "status": "REJECTED",
        "listType": "REJECTED",
        "market": market,
        "timeframe": timeframe,
        "setups": setups_norm,
        "scanData": None,
        "rejection": rejection_row,
        "summary": f"{symbol_upper} was rejected: {rej_summary}",
        "tradePlan": None,
        "setupAnalysis": None,
        "regimeAnalysis": None,
        "rsAnalysis": None,
        "volumeAnalysis": None,
        "mtfAnalysis": None,
        "reasoning": reasoning,
        "actionVerdict": "AVOID",
        "confidence": 0,
        "rejectionDetail": {
            "reason": reason,
            "detail": detail,
            "source": source,
            "summary": rej_summary,
            "bullets": rej_bullets,
        },
    }
    if metadata:
        result.update(metadata)
    return result


def _analysis_not_found(
    *,
    symbol_upper: str,
    market: str,
    timeframe: str,
    setups_norm: str,
    metadata: dict[str, Any] | None = None,
) -> dict:
    result = {
        "symbol": symbol_upper,
        "found": False,
        "status": "NOT_FOUND",
        "listType": "NOT_FOUND",
        "market": market,
        "timeframe": timeframe,
        "setups": setups_norm,
        "scanData": None,
        "rejection": None,
        "summary": (
            f"{symbol_upper} was not found in the latest outputs or current live scan for "
            f"{market}/{timeframe}/{setups_norm}. Either the symbol is outside the configured universe, "
            "does not currently qualify under the scanner rules, or its data is unavailable."
        ),
        "tradePlan": None,
        "setupAnalysis": None,
        "regimeAnalysis": None,
        "rsAnalysis": None,
        "volumeAnalysis": None,
        "mtfAnalysis": None,
        "reasoning": [
            f"⚠️  {symbol_upper} was not found by either the latest saved outputs or the live rule-based scan.",
            "💡 Possible reasons:",
            "   1. The symbol is not in the configured scan universe for the selected market.",
            "   2. The stock does not currently meet the setup filters.",
            "   3. Historical bars are missing or insufficient for this timeframe.",
            "   4. Symbol spelling may be incorrect (e.g. NSE stocks need '.NS').",
        ],
        "actionVerdict": "DATA_MISSING",
        "confidence": 0,
        "rejectionDetail": None,
    }
    if metadata:
        result.update(metadata)
    return result


def _load_scan_module():
    return importlib.import_module("apps.python.cli.run_full_us_scan")


def _compile_java_if_needed() -> None:
    class_file = ROOT / "src" / "Main.class"
    if class_file.exists():
        return
    java_files = sorted(str(path) for path in (ROOT / "src").glob("*.java"))
    if not java_files:
        return
    subprocess.run(["javac", *java_files], cwd=ROOT, check=True, capture_output=True, text=True)


def _build_live_args(market: str, timeframe: str, setups: str, cache_dir: str | None) -> SimpleNamespace:
    lookback = 252 if timeframe == "daily" else 104
    cache_root = cache_dir or str(ROOT / "cache")
    exchange_suffix = ".NS" if market == "india" else None
    return SimpleNamespace(
        symbols=None,
        timeframe=timeframe,
        setups=setups,
        lookback=lookback,
        retries=3,
        cache_dir=cache_root,
        cache_ttl=360,
        batch=1,
        mr_min_score=35.0,
        workers=1,
        output_dir=str(ROOT / "output"),
        no_watchlist=False,
        min_price_floor=5.0,
        min_avg_volume=0.0,
        min_avg_dollar_volume=0.0,
        liquidity_lookback=20,
        regime_mode="soft",
        regime_sample=100,
        regime_min_breadth50=0.50,
        regime_min_breadth200=0.45,
        rs_weight=0.35,
        max_portfolio_heat_r=6.0,
        account_size=100_000.0,
        base_risk_pct=0.01,
        market_label=market,
        exchange_suffix=exchange_suffix,
    )


def _load_market_universe(scan_mod, market: str, args: SimpleNamespace) -> tuple[list[str], str]:
    if market == "india":
        path = scan_mod.INDIA_SYMBOLS_FILE
    elif Path(scan_mod.CSV_SYMBOLS_FILE).exists():
        path = scan_mod.CSV_SYMBOLS_FILE
    elif Path(scan_mod.DEFAULT_SYMBOLS_FILE).exists():
        path = scan_mod.DEFAULT_SYMBOLS_FILE
    else:
        path = scan_mod.FALLBACK_SYMBOLS_FILE

    if str(path).lower().endswith(".csv"):
        return scan_mod.load_symbols_from_csv(path, args), str(path)
    return scan_mod.load_symbols_from_text(path), str(path)


def _warm_symbol_cache_if_needed(scan_mod, symbol_upper: str, args: SimpleNamespace) -> bool:
    bars = scan_mod.load_cached_bars(symbol_upper, args.lookback, args.timeframe, args.cache_dir)
    if bars:
        return True

    _compile_java_if_needed()
    warm_args = SimpleNamespace(**vars(args))
    warm_args.setups = "vcp"
    try:
        scan_mod.scan_batch([symbol_upper], warm_args)
    except Exception:
        return False
    bars = scan_mod.load_cached_bars(symbol_upper, args.lookback, args.timeframe, args.cache_dir)
    return bool(bars)


def _row_symbol(row: dict) -> str:
    return str(row.get("symbol", "")).strip().upper()


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (
            _row_symbol(row),
            str(row.get("listType", "")).upper(),
            str(row.get("setup", row.get("setupType", ""))).upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _scan_live_symbol(
    *,
    symbol_upper: str,
    market: str,
    timeframe: str,
    setups_norm: str,
    cache_dir: str | None,
) -> tuple[dict | None, str, str, dict | None, dict[str, Any]]:
    started = time.time()
    scan_mod = _load_scan_module()
    args = _build_live_args(market, timeframe, setups_norm, cache_dir)

    if setups_norm != "mean_reversion":
        _compile_java_if_needed()

    universe_symbols, universe_path = _load_market_universe(scan_mod, market, args)
    cache_ready = _warm_symbol_cache_if_needed(scan_mod, symbol_upper, args)
    regime = scan_mod.build_market_regime(universe_symbols, args) if universe_symbols else {
        "mode": args.regime_mode,
        "favorable": True,
        "breadth50": 1.0,
        "breadth200": 1.0,
        "score": 1.0,
        "sampled": 0,
        "bench3m": 0.0,
        "bench6m": 0.0,
        "bench12m": 0.0,
    }

    raw_hits: list[dict] = []
    raw_watchlist: list[dict] = []
    raw_mr_hits: list[dict] = []

    if setups_norm != "mean_reversion":
        raw_hits = [_ for _ in (scan_mod.parse_hit(line) for line in scan_mod.scan_batch([symbol_upper], args)) if _row_symbol(_) == symbol_upper]
        raw_watchlist = [_ for _ in (scan_mod.parse_hit(line) for line in scan_mod.scan_watchlist_batch([symbol_upper], args)) if _row_symbol(_) == symbol_upper]

    if setups_norm in {"mean_reversion", "full"} and cache_ready:
        raw_mr_hits = [row for row in scan_mod._run_mr_scan([symbol_upper], args) if _row_symbol(row) == symbol_upper]

    raw_hits = _dedupe_rows(raw_hits + raw_mr_hits)
    raw_watchlist = _dedupe_rows(raw_watchlist)

    kept_hits, rejected_hits, rejected_map_hits = scan_mod.enrich_and_filter_rows(raw_hits, args, regime, "LIVE_BREAKOUT")
    kept_watchlist, rejected_watchlist, rejected_map_watchlist = scan_mod.enrich_and_filter_rows(raw_watchlist, args, regime, "LIVE_WATCHLIST")
    portfolio_rows = scan_mod.apply_portfolio_heat(kept_hits, args)
    watchlist_rows = scan_mod.rank_watchlist_rows(kept_watchlist)

    found_row: dict | None = None
    found_status = "NOT_FOUND"
    found_list_type = ""

    for rows, status_label in (
        (portfolio_rows, "PORTFOLIO_SHORTLIST"),
        (kept_hits, "BREAKOUT"),
        (watchlist_rows, "WATCHLIST"),
    ):
        hit = _search_list(rows, symbol_upper)
        if hit:
            found_row = hit
            found_status = status_label
            found_list_type = str(hit.get("listType", status_label))
            break

    rejection_row: dict | None = None
    if not found_row:
        all_rejected = rejected_hits + rejected_watchlist
        rejection_row = _search_list(all_rejected, symbol_upper)
        if not rejection_row:
            bars = scan_mod.load_cached_bars(symbol_upper, args.lookback, args.timeframe, args.cache_dir)
            if not bars:
                rejection_row = {
                    "symbol": symbol_upper,
                    "reason": "INSUFFICIENT_DATA",
                    "source": "LIVE_SCAN",
                    "detail": "No usable cached bars available for live symbol analysis.",
                }
            else:
                generated = scan_mod.build_rejection_rows(
                    [symbol_upper],
                    {_row_symbol(row) for row in portfolio_rows + kept_hits + watchlist_rows},
                    {**rejected_map_hits, **rejected_map_watchlist},
                )
                rejection_row = generated[0] if generated else None

    live_meta = {
        "analysisSource": "live",
        "analysisGeneratedAt": _now_iso(),
        "analysisSourceDetail": "Generated by rerunning the existing scanner logic for this symbol.",
        "analysisMatchedFile": None,
        "liveScanMeta": {
            "cacheDir": args.cache_dir,
            "cacheReady": cache_ready,
            "lookback": args.lookback,
            "universeFile": universe_path,
            "universeSize": len(universe_symbols),
            "regimeSampled": int(regime.get("sampled", 0) or 0),
            "regimeScore": round(_to_float(regime.get("score"), 0.0) * 100.0, 2),
            "breakoutCandidates": len(raw_hits),
            "watchlistCandidates": len(raw_watchlist),
            "portfolioCandidates": len(portfolio_rows),
            "elapsedMs": int((time.time() - started) * 1000),
        },
    }
    return found_row, found_status, found_list_type, rejection_row, live_meta


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_stock(
    output_dir: Path,
    symbol: str,
    market: str = "india",
    timeframe: str = "daily",
    setups: str = "full",
    source: str = "auto",
    cache_dir: str | None = None,
) -> dict:
    """
    Analyze a single stock symbol across all scan output files.
    Returns a rich analysis dict.
    """
    symbol_upper = symbol.strip().upper()
    market = market.strip().lower()
    timeframe = timeframe.strip().lower()
    setups_norm = setups.strip().lower()
    source_norm = (source or "auto").strip().lower()
    if setups_norm == "all":
        setups_norm = "full"
    if source_norm not in {"auto", "output", "live"}:
        source_norm = "auto"

    if source_norm in {"auto", "output"}:
        found_row, found_status, found_list_type, found_path, rejection_row, rejection_path = _search_outputs(
            output_dir=output_dir,
            symbol_upper=symbol_upper,
            market=market,
            timeframe=timeframe,
            setups=setups_norm,
        )

        output_meta = {
            "analysisSource": "output",
            "analysisGeneratedAt": _now_iso(),
            "analysisSourceDetail": "Matched from the latest saved scan output.",
            "analysisMatchedFile": str((found_path or rejection_path).resolve()) if (found_path or rejection_path) else None,
            "analysisRequestedSource": source_norm,
            "liveScanMeta": None,
        }

        if found_row:
            return _analysis_from_found_row(
                found_row=found_row,
                found_status=found_status,
                found_list_type=found_list_type,
                symbol_upper=symbol_upper,
                market=market,
                timeframe=timeframe,
                setups_norm=setups_norm,
                metadata=output_meta,
            )
        if rejection_row or source_norm == "output":
            if rejection_row:
                return _analysis_from_rejection(
                    rejection_row=rejection_row,
                    symbol_upper=symbol_upper,
                    market=market,
                    timeframe=timeframe,
                    setups_norm=setups_norm,
                    metadata=output_meta,
                )
            return _analysis_not_found(
                symbol_upper=symbol_upper,
                market=market,
                timeframe=timeframe,
                setups_norm=setups_norm,
                metadata=output_meta,
            )

    found_row, found_status, found_list_type, rejection_row, live_meta = _scan_live_symbol(
        symbol_upper=symbol_upper,
        market=market,
        timeframe=timeframe,
        setups_norm=setups_norm,
        cache_dir=cache_dir,
    )
    live_meta["analysisRequestedSource"] = source_norm

    if found_row:
        return _analysis_from_found_row(
            found_row=found_row,
            found_status=found_status,
            found_list_type=found_list_type,
            symbol_upper=symbol_upper,
            market=market,
            timeframe=timeframe,
            setups_norm=setups_norm,
            metadata=live_meta,
        )
    if rejection_row:
        return _analysis_from_rejection(
            rejection_row=rejection_row,
            symbol_upper=symbol_upper,
            market=market,
            timeframe=timeframe,
            setups_norm=setups_norm,
            metadata=live_meta,
        )
    return _analysis_not_found(
        symbol_upper=symbol_upper,
        market=market,
        timeframe=timeframe,
        setups_norm=setups_norm,
        metadata=live_meta,
    )

