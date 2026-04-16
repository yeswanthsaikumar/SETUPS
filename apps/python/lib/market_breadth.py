#!/usr/bin/env python3
"""
market_breadth.py
─────────────────
Advanced Market Breadth Analytics Engine for NSE India.

Provides:
  - Market Regime Detection  (Bull / Recovery / Mixed / Correction / Bear)
  - Breadth Pulse            (Advance/Decline, RS momentum count)
  - Momentum Trajectories    (Accelerating / Improving / Decelerating / Collapsing)
  - Divergence Detection     (Bullish: early entry | Bearish: risk warning)
  - Smart Money Footprint    (Volume + RS + New-High institutional signatures)
  - Sector Rotation Signals  (Which sectors rotating IN vs OUT)
  - Breadth Oscillator       (Industry-level McClellan equivalent)

Usage:
    from market_breadth import (
        compute_market_regime, compute_breadth_pulse,
        detect_divergences, compute_trajectories,
        compute_smart_money_footprint, compute_rotation_signals,
        compute_breadth_oscillator,
    )

Input format (industry_data dict keys expected from generate_breadth_dashboard.py):
    industry, sector, stage, total, pct_20ma, pct_50ma, pct_200ma, pct_52wh,
    avg_rs3m, avg_rs1m, avg_rs_delta, avg_vol_rank, vol_spike_pct, new_52wh,
    ind_ret_1m, ind_ret_3m, ind_ret_6m, breadth_score, trend_score
"""
from __future__ import annotations

import math
from typing import Optional

# ── Regime constants ────────────────────────────────────────────────────────────
REGIME_BULL       = "BULL MARKET"
REGIME_RECOVERY   = "RECOVERY"
REGIME_MIXED      = "MIXED"
REGIME_CORRECTION = "CORRECTION"
REGIME_BEAR       = "BEAR MARKET"


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2.0 if n % 2 == 0 else s[n // 2]


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _safe(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key)
    return float(v) if v is not None else default


# ── 1. Market Regime Detection ──────────────────────────────────────────────────

def compute_market_regime(industry_data: list[dict]) -> dict:
    """
    Detect the overall NSE market regime from aggregated industry breadth data.

    Regime Score (0-100):
        Breadth depth  (55%) = weighted average of median >20/50/200 MA breadth
        RS vs Nifty    (30%) = average industry RS vs Nifty 3M
        Volume signal  (15%) = % industries with vol > 1.2x historical

    Returns a dict with:
        regime, regime_score, color, emoji, description, action,
        pct_bull_industries, pct_weak_industries, pct_emerging_industries,
        median_p20, median_p50, median_p200, avg_rs, rs_improving_pct,
        vol_expanding_pct, new_highs_total, industry_count
    """
    if not industry_data:
        return {
            "regime": REGIME_MIXED, "regime_score": 50,
            "color": "#e3b341", "emoji": "🟡",
            "description": "No data.", "action": "Gather more price data.",
            "industry_count": 0,
        }

    n = len(industry_data)
    bull_stages = {"BUILDING", "SURGING", "EXTENDED"}
    weak_stages = {"WEAK"}

    bull_cnt  = sum(1 for d in industry_data if d.get("stage", "") in bull_stages)
    weak_cnt  = sum(1 for d in industry_data if d.get("stage", "") in weak_stages)
    emerg_cnt = sum(1 for d in industry_data if d.get("stage", "") in ("EMERGING", "EMERGING★"))

    pct_bull    = bull_cnt  / n * 100
    pct_weak    = weak_cnt  / n * 100
    pct_emerg   = emerg_cnt / n * 100

    p20_vals  = [_safe(d, "pct_20ma")  for d in industry_data]
    p50_vals  = [_safe(d, "pct_50ma")  for d in industry_data]
    p200_vals = [_safe(d, "pct_200ma") for d in industry_data]

    med_p20   = _median(p20_vals)
    med_p50   = _median(p50_vals)
    med_p200  = _median(p200_vals)

    rs_vals   = [_safe(d, "avg_rs3m")     for d in industry_data if d.get("avg_rs3m") is not None]
    rsd_vals  = [_safe(d, "avg_rs_delta") for d in industry_data if d.get("avg_rs_delta") is not None]
    vol_vals  = [_safe(d, "avg_vol_rank", 1.0) for d in industry_data if d.get("avg_vol_rank") is not None]

    avg_rs     = _avg(rs_vals)
    rs_imp_cnt = sum(1 for v in rsd_vals if v > 0.5)
    rs_imp_pct = rs_imp_cnt / len(rsd_vals) * 100 if rsd_vals else 0
    vol_exp_pct= sum(1 for v in vol_vals if v > 1.2) / len(vol_vals) * 100 if vol_vals else 0
    new_highs  = sum(d.get("new_52wh", 0) for d in industry_data)

    # ── Regime Score ────────────────────────────────────────────────────────────
    breadth_score = med_p20 * 0.40 + med_p50 * 0.35 + med_p200 * 0.25
    rs_score      = _clamp((avg_rs + 15) / 30 * 100)
    vol_score     = vol_exp_pct
    regime_score  = round(_clamp(breadth_score * 0.55 + rs_score * 0.30 + vol_score * 0.15))

    # ── Regime Label ────────────────────────────────────────────────────────────
    if regime_score >= 70 and pct_bull >= 50:
        regime = REGIME_BULL;       color = "#3fb950"; emoji = "🟢"
        desc   = "Strong bull market — most industries above key MAs, RS positive. Risk-on."
        action = "Be aggressive. Rotate into high-RS leaders. Hold winners."
    elif regime_score >= 55 or (pct_emerg >= 20 and pct_bull >= 20):
        regime = REGIME_RECOVERY;   color = "#22d3ee"; emoji = "⭐"
        desc   = "Recovery / early bull — breadth expanding. Best entry window for swing trades."
        action = "Build positions in EMERGING★ industries. Focus RS improving + vol expanding."
    elif regime_score >= 40:
        regime = REGIME_MIXED;      color = "#e3b341"; emoji = "🟡"
        desc   = "Mixed market — sector rotation underway. Only select groups are leading."
        action = "Stock picking mode. Buy only top RS leaders. Keep tight stops."
    elif regime_score >= 22:
        regime = REGIME_CORRECTION; color = "#f87171"; emoji = "🔴"
        desc   = "Correction — breadth deteriorating rapidly. Reduce exposure."
        action = "Raise cash. Protect profits. Wait for breadth thrust before re-entering."
    else:
        regime = REGIME_BEAR;       color = "#f85149"; emoji = "⚫"
        desc   = "Bear market — most industries well below key MAs. Capital at risk."
        action = "Maximum defensive. Sit in cash or short. No new longs."

    return {
        "regime": regime, "regime_score": regime_score,
        "color": color, "emoji": emoji,
        "description": desc, "action": action,
        "pct_bull_industries":     round(pct_bull, 1),
        "pct_weak_industries":     round(pct_weak, 1),
        "pct_emerging_industries": round(pct_emerg, 1),
        "median_p20":  round(med_p20, 1),
        "median_p50":  round(med_p50, 1),
        "median_p200": round(med_p200, 1),
        "avg_rs":            round(avg_rs, 1),
        "rs_improving_pct":  round(rs_imp_pct, 1),
        "vol_expanding_pct": round(vol_exp_pct, 1),
        "new_highs_total":   new_highs,
        "industry_count":    n,
    }


# ── 2. Breadth Pulse ─────────────────────────────────────────────────────────────

def compute_breadth_pulse(industry_data: list[dict]) -> dict:
    """
    Quick-read market pulse:
      advancing / declining count (by RS delta)
      new-high vs new-low industry count
      volume expansion count
      breadth thrust classification
    """
    n = len(industry_data) or 1

    adv  = sum(1 for d in industry_data if _safe(d, "avg_rs_delta") > 0)
    dec  = sum(1 for d in industry_data if _safe(d, "avg_rs_delta") < 0)
    flat = n - adv - dec

    nh   = sum(1 for d in industry_data if d.get("new_52wh", 0) > 0)
    nl   = sum(1 for d in industry_data
               if d.get("pct_52wh", 0) == 0 and _safe(d, "pct_20ma") < 20)

    vol_exp = sum(1 for d in industry_data if _safe(d, "avg_vol_rank", 1.0) > 1.2)

    adl_ratio   = adv / max(dec, 1)
    rs_imp_pct  = adv / n * 100

    if rs_imp_pct >= 65 and adl_ratio >= 2.5:
        thrust = "BREADTH THRUST"
        tc     = "#3fb950"
        tdesc  = "Exceptionally rare bull signal — >65% industries with rising RS. Very high probability of sustained advance."
    elif rs_imp_pct >= 55:
        thrust = "BROAD ADVANCE"
        tc     = "#22d3ee"
        tdesc  = "Healthy bull phase — majority of industries gaining relative strength."
    elif rs_imp_pct >= 40:
        thrust = "SELECTIVE"
        tc     = "#e3b341"
        tdesc  = "Mixed market — pick only high-conviction RS leaders."
    elif rs_imp_pct >= 25:
        thrust = "NARROW"
        tc     = "#f87171"
        tdesc  = "Few industries leading — risk of distribution. Be defensive."
    else:
        thrust = "COLLAPSING"
        tc     = "#f85149"
        tdesc  = "Very few advancing industries — likely in correction or bear. Raise cash."

    return {
        "advancing":       adv,
        "declining":       dec,
        "flat":            flat,
        "adl_ratio":       round(adl_ratio, 2),
        "new_highs_ind":   nh,
        "new_lows_ind":    nl,
        "vol_expanding":   vol_exp,
        "rs_improving_pct": round(rs_imp_pct, 1),
        "thrust_signal":   thrust,
        "thrust_color":    tc,
        "thrust_desc":     tdesc,
    }


# ── 3. Divergence Detection ─────────────────────────────────────────────────────

def detect_divergences(industry_data: list[dict]) -> dict[str, list[dict]]:
    """
    Detect price–breadth divergences.

    BULLISH DIVERGENCE (early entry):
      Stage = WEAK or EMERGING, but RS delta > +2% AND vol expanding > 1.2x.
      "Smart money quietly accumulating before the market notices."

    BEARISH DIVERGENCE (risk warning):
      Stage = BUILDING / EXTENDED, but RS delta < -2% AND vol shrinking < 0.9x.
      "Distribution underway — price looks fine but breadth crumbling."

    Opportunity / Risk scores based on signal strength.
    """
    _PICK = ("industry","sector","stage","total","pct_20ma","pct_50ma",
             "avg_rs3m","avg_rs_delta","avg_vol_rank","ind_ret_1m",
             "ind_ret_3m","trend_score","vol_spike_pct","new_52wh")

    bullish: list[dict] = []
    bearish: list[dict] = []

    for d in industry_data:
        stage = d.get("stage", "")
        rsd   = _safe(d, "avg_rs_delta")
        vr    = _safe(d, "avg_vol_rank", 1.0)
        rs3m  = _safe(d, "avg_rs3m")
        vs    = _safe(d, "vol_spike_pct")
        n52   = d.get("new_52wh", 0)
        ret3m = _safe(d, "ind_ret_3m")
        n     = d.get("total", 0)

        base = {k: d.get(k) for k in _PICK}

        # Bullish divergence
        if stage in ("WEAK", "EMERGING", "EMERGING★") and rsd > 2.0 and vr > 1.15:
            opp = _clamp(rsd * 5 + (vr - 1) * 25 + (rs3m + 15) * 0.5 + vs * 0.3, 0, 100)
            signal_parts = []
            if vr >= 1.5:  signal_parts.append("🔥 Heavy vol accumulation")
            elif vr >= 1.2: signal_parts.append("📊 Vol expanding")
            if rsd >= 5:   signal_parts.append("🚀 RS accelerating strongly")
            elif rsd >= 3: signal_parts.append("📈 RS gaining momentum")
            if n52 > 0:    signal_parts.append(f"🏔 {n52} new 52W highs")
            if vs >= 25:   signal_parts.append("⚡ Vol cluster")
            bullish.append({
                **base,
                "divergence_type": "BULLISH",
                "signal_label":    " · ".join(signal_parts) or "RS+Vol improving",
                "opportunity_score": round(opp, 1),
                "why": "Early accumulation: RS improving + vol expanding while still early-stage."
            })

        # Bearish divergence
        elif stage in ("BUILDING", "SURGING", "EXTENDED") and rsd < -2.0 and vr < 0.9:
            risk = _clamp(abs(rsd) * 5 + (1 - vr) * 25 + max(ret3m, 0) * 0.3, 0, 100)
            signal_parts = ["📉 RS deteriorating", "💧 Vol shrinking"]
            if rsd < -4:   signal_parts.append("⚠️ RS collapse")
            if vr < 0.75:  signal_parts.append("⚠️ Volume drying up")
            bearish.append({
                **base,
                "divergence_type": "BEARISH",
                "signal_label":    " · ".join(signal_parts),
                "risk_score":      round(risk, 1),
                "why": "Distribution warning: RS and vol declining while price still elevated."
            })

    return {
        "bullish": sorted(bullish, key=lambda x: -x.get("opportunity_score", 0))[:12],
        "bearish": sorted(bearish, key=lambda x: -x.get("risk_score", 0))[:8],
    }


# ── 4. Momentum Trajectories ─────────────────────────────────────────────────────

def compute_trajectories(industry_data: list[dict]) -> dict[str, list[dict]]:
    """
    Classify industries by their RS momentum trajectory.

    ACCELERATING : RS delta > +3.5% AND vol > 1.2x  → 🚀 Strongest buy signal
    IMPROVING    : RS delta > +1.0%                  → 📈 Building momentum
    STEADY       : -1% ≤ RS delta ≤ +1%              → ➡️ Consolidating
    DECELERATING : RS delta < -1.0%                  → 📉 Momentum fading
    COLLAPSING   : RS delta < -3.5% AND vol < 0.9x   → 💥 Exit / avoid

    Returns dict with each trajectory class as key → sorted list of industries.
    """
    _PICK = ("industry","sector","stage","total","pct_20ma","pct_50ma",
             "avg_rs3m","avg_rs_delta","avg_vol_rank","ind_ret_1m",
             "ind_ret_3m","trend_score","new_52wh","vol_spike_pct","stock_list")

    acc, imp, ste, dec, col = [], [], [], [], []

    for d in industry_data:
        rsd  = _safe(d, "avg_rs_delta")
        vr   = _safe(d, "avg_vol_rank", 1.0)
        base = {k: d.get(k) for k in _PICK}

        if rsd > 3.5 and vr > 1.2:
            acc.append({**base, "trajectory": "ACCELERATING", "traj_emoji": "🚀",
                        "traj_color": "#22d3ee",
                        "insight": "RS strongly improving + vol expanding. Institutional buying confirmed."})
        elif rsd > 1.0:
            imp.append({**base, "trajectory": "IMPROVING",    "traj_emoji": "📈",
                        "traj_color": "#3fb950",
                        "insight": "RS momentum building. Good setup for swing entries."})
        elif rsd < -3.5 and vr < 0.9:
            col.append({**base, "trajectory": "COLLAPSING",   "traj_emoji": "💥",
                        "traj_color": "#f85149",
                        "insight": "RS collapsing + vol drying up. Exit or avoid."})
        elif rsd < -1.0:
            dec.append({**base, "trajectory": "DECELERATING", "traj_emoji": "📉",
                        "traj_color": "#f87171",
                        "insight": "RS momentum fading. Reduce exposure, tighten stops."})
        else:
            ste.append({**base, "trajectory": "STEADY",       "traj_emoji": "➡️",
                        "traj_color": "#475569",
                        "insight": "RS stable. Wait for directional confirmation."})

    return {
        "accelerating": sorted(acc, key=lambda x: -_safe(x, "avg_rs_delta"))[:16],
        "improving":    sorted(imp, key=lambda x: -_safe(x, "avg_rs_delta"))[:16],
        "decelerating": sorted(dec, key=lambda x:  _safe(x, "avg_rs_delta"))[:10],
        "collapsing":   sorted(col, key=lambda x:  _safe(x, "avg_rs_delta"))[:8],
        "steady":       sorted(ste, key=lambda x: -_safe(x, "trend_score"))[:10],
    }


# ── 5. Smart Money Footprint ─────────────────────────────────────────────────────

def compute_smart_money_footprint(industry_data: list[dict]) -> list[dict]:
    """
    Identify industries where institutional accumulation is most visible:
      - Volume expansion (>1.3x historical)
      - New 52W highs accumulating (breadth leadership)
      - RS vs Nifty strongly positive or improving
      - Stage is pre-extended (EMERGING or BUILDING) ← best window

    "Smart money in, retail not yet" pattern = highest reward/risk setups.

    Institutional Conviction Score (0-100):
      Volume expansion  30 pts
      New high ratio    25 pts
      Vol spike %       25 pts
      RS delta          20 pts
    """
    _PICK = ("industry","sector","stage","total","pct_20ma","pct_50ma",
             "avg_rs3m","avg_rs_delta","avg_vol_rank","vol_spike_pct",
             "new_52wh","ind_ret_1m","ind_ret_3m","trend_score","pct_52wh","stock_list")

    candidates: list[dict] = []
    for d in industry_data:
        vr    = _safe(d, "avg_vol_rank", 1.0)
        n52   = d.get("new_52wh", 0)
        vs    = _safe(d, "vol_spike_pct")
        rsd   = _safe(d, "avg_rs_delta")
        rs3m  = _safe(d, "avg_rs3m")
        p20   = _safe(d, "pct_20ma")
        stage = d.get("stage", "")
        n     = d.get("total", 1)

        # Skip stages that are too late (smart money already priced in)
        if stage == "EXTENDED" and p20 >= 85:
            continue

        conv = (
            _clamp((vr - 1) / 1.0 * 30, 0, 30) +         # vol expansion
            _clamp(n52 / max(n, 1) * 50, 0, 25) +         # new high ratio
            _clamp(vs / 100 * 25, 0, 25) +                 # vol spike %
            _clamp(max(rsd, 0) / 6 * 20, 0, 20)           # RS delta
        )

        if conv >= 8 and n >= 3:
            sig = _build_sm_signal(vr, n52, vs, rsd, rs3m, stage)
            candidates.append({
                **{k: d.get(k) for k in _PICK},
                "institutional_score": round(conv, 1),
                "signal_label": sig,
            })

    return sorted(candidates, key=lambda x: -x["institutional_score"])[:15]


def _build_sm_signal(vr: float, n52: int, vs: float, rsd: float,
                     rs3m: float, stage: str) -> str:
    parts: list[str] = []
    if vr >= 1.8:    parts.append("🔥🔥 Massive vol surge")
    elif vr >= 1.4:  parts.append("🔥 Heavy accumulation vol")
    elif vr >= 1.2:  parts.append("📊 Vol expanding")
    if n52 >= 5:     parts.append(f"🏔🏔 {n52} new 52W highs")
    elif n52 >= 2:   parts.append(f"🏔 {n52} new 52W highs")
    if rsd >= 5:     parts.append("🚀 RS accelerating")
    elif rsd >= 2:   parts.append("📈 RS improving")
    if vs >= 40:     parts.append("⚡⚡ Multiple vol clusters")
    elif vs >= 20:   parts.append("⚡ Vol cluster detected")
    if stage == "EMERGING★": parts.append("⭐ RS+Vol leading (EMERGING★)")
    return " · ".join(parts) if parts else "Moderate institutional signal"


# ── 6. Sector Rotation Signals ──────────────────────────────────────────────────

# Cycle phase mapping: sector → (cycle_phase, cycle_position)
_SECTOR_CYCLE: dict[str, tuple[str, int]] = {
    "Financials": ("Early Cycle",  1),
    "Consumer":   ("Early Cycle",  2),
    "Internet":   ("Early Cycle",  3),
    "RealEstate": ("Early Cycle",  4),
    "IT":         ("Mid Cycle",    5),
    "Electronics":("Mid Cycle",    6),
    "Cap Goods":  ("Mid Cycle",    7),
    "Defense":    ("Mid Cycle",    8),
    "Cables":     ("Mid Cycle",    9),
    "Textiles":   ("Mid Cycle",   10),
    "Metals":     ("Late Cycle",  11),
    "Chemicals":  ("Late Cycle",  12),
    "Energy":     ("Late Cycle",  13),
    "Infra":      ("Late Cycle",  14),
    "Renewable":  ("Late Cycle",  15),
    "Packaging":  ("Late Cycle",  16),
    "Shipping":   ("Late Cycle",  17),
    "Sugar":      ("Late Cycle",  18),
    "Pharma":     ("Defensive",   19),
    "FMCG":       ("Defensive",   20),
    "Banking":    ("Defensive",   21),
    "Agri":       ("Defensive",   22),
}

_CYCLE_COLORS = {
    "Early Cycle": "#4ade80",
    "Mid Cycle":   "#60a5fa",
    "Late Cycle":  "#fbbf24",
    "Defensive":   "#a78bfa",
    "Other":       "#475569",
}


def compute_rotation_signals(sector_data: list[dict]) -> list[dict]:
    """
    Compute which sectors are rotating IN (gaining) vs OUT (losing) vs Nifty.

    Rotation Score (-100 to +100):
      RS delta (primary signal)    × 5
      Short-term RS acceleration    × 2  (RS 1M - RS 3M momentum)
      Volume expansion              × 20
      Stage bonus/penalty           ± 5

    Returns sector_data enriched with rotation fields, sorted by rotation score.
    """
    result: list[dict] = []
    for sd in sector_data:
        sec   = sd.get("sector", "")
        rsd   = _safe(sd, "avg_rs_delta")
        vr    = _safe(sd, "avg_vol_rank", 1.0)
        rs3m  = _safe(sd, "avg_rs3m")
        rs1m  = _safe(sd, "avg_rs1m")
        stage = sd.get("stage", "")

        cycle_phase, cycle_pos = _SECTOR_CYCLE.get(sec, ("Other", 99))
        stage_adj = 5 if stage in ("EMERGING","EMERGING★","BUILDING","SURGING") else -5

        rot_score = _clamp(
            rsd * 5 + (rs1m - rs3m) * 2 + (vr - 1.0) * 20 + stage_adj,
            -100, 100
        )
        rot_score = round(rot_score, 1)

        if rot_score >= 20:
            sig, rc, re = "ROTATING IN",  "#3fb950", "↗️"
        elif rot_score >= 8:
            sig, rc, re = "BUILDING",     "#22d3ee", "➡️"
        elif rot_score <= -20:
            sig, rc, re = "ROTATING OUT", "#f85149", "↙️"
        elif rot_score <= -8:
            sig, rc, re = "FADING",       "#e3b341", "⬇️"
        else:
            sig, rc, re = "NEUTRAL",      "#475569", "➡️"

        result.append({
            **sd,
            "cycle_phase":    cycle_phase,
            "cycle_position": cycle_pos,
            "cycle_color":    _CYCLE_COLORS.get(cycle_phase, "#475569"),
            "rotation_score": rot_score,
            "rotation_signal": sig,
            "rotation_color":  rc,
            "rotation_emoji":  re,
        })

    return sorted(result, key=lambda x: -x.get("rotation_score", 0))


# ── 7. Breadth Oscillator ────────────────────────────────────────────────────────

def compute_breadth_oscillator(industry_data: list[dict]) -> dict:
    """
    NSE industry-level breadth oscillator (McClellan equivalent).

    Advance  = industry RS delta > +0.5%
    Decline  = industry RS delta < -0.5%
    Net      = Advance - Decline

    Short EMA (10 period surrogate) = avg of top 10 RS delta values
    Long EMA  (40 period surrogate) = avg of all RS delta values
    Oscillator = Short EMA - Long EMA

    Interpretation:
        > +5 : Broad buy signal — majority accelerating
        0–5  : Mild positive — selective buying
        -5–0 : Mild negative — market struggling
        < -5 : Strong sell signal — broad deterioration

    Note: Without historical run data we approximate using cross-sectional
    distribution of the current RS delta snapshot.
    """
    if not industry_data:
        return {"oscillator": 0, "signal": "NO DATA", "adl_net": 0}

    rsd_vals = [_safe(d, "avg_rs_delta") for d in industry_data]
    adv  = sum(1 for v in rsd_vals if v > 0.5)
    dec  = sum(1 for v in rsd_vals if v < -0.5)
    net  = adv - dec

    # Approximate oscillator from the distribution
    sorted_rsd = sorted(rsd_vals, reverse=True)
    top_n  = max(len(sorted_rsd) // 4, 5)
    short_ema_approx = _avg(sorted_rsd[:top_n])
    long_ema_approx  = _avg(rsd_vals)
    oscillator = round(short_ema_approx - long_ema_approx, 2)

    if oscillator > 5:
        signal = "STRONG BUY"; sc = "#3fb950"
    elif oscillator > 1:
        signal = "BUY";        sc = "#22d3ee"
    elif oscillator > -1:
        signal = "NEUTRAL";    sc = "#e3b341"
    elif oscillator > -5:
        signal = "CAUTION";    sc = "#f87171"
    else:
        signal = "SELL";       sc = "#f85149"

    return {
        "oscillator":  oscillator,
        "signal":      signal,
        "signal_color": sc,
        "adl_net":     net,
        "advancing":   adv,
        "declining":   dec,
        "avg_rs_delta": round(long_ema_approx, 2),
        "top_quarter_avg_rsd": round(short_ema_approx, 2),
    }


# ── 8. Sector Momentum Matrix ────────────────────────────────────────────────────

def compute_sector_momentum_matrix(sector_data: list[dict]) -> list[dict]:
    """
    Create a 2D momentum matrix for each sector:
      X-axis: RS vs Nifty 3M  (where are we now)
      Y-axis: RS Delta 4W      (which direction are we heading)

    Quadrants:
      Q1 (RS+, RSD+): Leaders             → Stay long / add on dips
      Q2 (RS-, RSD+): Improvers / Turnaround → Early accumulation zone
      Q3 (RS-, RSD-): Laggards / Avoid    → Short or avoid
      Q4 (RS+, RSD-): Distributors / Fade → Reduce / take profits

    Returns sector_data with quadrant classification added.
    """
    result = []
    for sd in sector_data:
        rs3m = _safe(sd, "avg_rs3m")
        rsd  = _safe(sd, "avg_rs_delta")

        if rs3m >= 0 and rsd >= 0:
            quadrant = "LEADER"
            qcolor   = "#3fb950"
            qdesc    = "Strong RS + improving. Stay long."
        elif rs3m < 0 and rsd >= 0:
            quadrant = "IMPROVER"
            qcolor   = "#22d3ee"
            qdesc    = "Weak RS but turning. Early accumulation."
        elif rs3m >= 0 and rsd < 0:
            quadrant = "DISTRIBUTOR"
            qcolor   = "#e3b341"
            qdesc    = "Strong RS but fading. Take profits."
        else:
            quadrant = "LAGGARD"
            qcolor   = "#f85149"
            qdesc    = "Weak RS + deteriorating. Avoid."

        result.append({
            **sd,
            "momentum_quadrant":  quadrant,
            "quadrant_color":     qcolor,
            "quadrant_desc":      qdesc,
            "rs3m_norm":  round(rs3m, 1),
            "rsd_norm":   round(rsd,  1),
        })

    return sorted(result, key=lambda x: -(
        _safe(x, "avg_rs3m") * 0.5 + _safe(x, "avg_rs_delta") * 0.5
    ))


# ── 9. Industry Opportunity Screener ─────────────────────────────────────────────

def screen_best_opportunities(
    industry_data: list[dict],
    regime_score: int = 50,
) -> list[dict]:
    """
    Screen for the highest-quality industry setups for swing trading:
      1. Stage is EMERGING or EMERGING★ (not yet extended)
      2. RS vs Nifty is positive (outperforming)
      3. RS Delta is positive (momentum building)
      4. Volume is expanding (institutional buying)
      5. New 52W highs appearing (breadth leadership)

    Opportunity Score (0-100):
      Stage factor     15 pts
      RS quality       25 pts
      RS delta         25 pts
      Volume           20 pts
      New highs        15 pts

    Returns top setups ranked by opportunity score.
    Market regime adjusts what qualifies as "best."
    """
    setups: list[dict] = []
    target_stages = {"EMERGING", "EMERGING★", "BUILDING"}

    for d in industry_data:
        stage = d.get("stage", "")
        rs3m  = _safe(d, "avg_rs3m")
        rsd   = _safe(d, "avg_rs_delta")
        vr    = _safe(d, "avg_vol_rank", 1.0)
        n52   = d.get("new_52wh", 0)
        vs    = _safe(d, "vol_spike_pct")
        p20   = _safe(d, "pct_20ma")
        n     = d.get("total", 0)

        if stage not in target_stages:
            continue
        if rs3m < -5 and regime_score > 50:  # in bull market, skip weak RS
            continue
        if n < 3:
            continue

        stage_pts = 15 if stage == "EMERGING★" else 12 if stage == "EMERGING" else 8
        rs_pts    = _clamp((rs3m + 10) / 25 * 25, 0, 25)
        rsd_pts   = _clamp(rsd / 6 * 25, 0, 25)
        vol_pts   = _clamp((vr - 0.8) / 1.2 * 20, 0, 20)
        hi_pts    = _clamp(n52 / max(n, 1) * 30, 0, 15)

        opp_score = round(stage_pts + rs_pts + rsd_pts + vol_pts + hi_pts, 1)

        setups.append({
            **{k: d.get(k) for k in (
                "industry","sector","stage","total","pct_20ma","pct_50ma",
                "avg_rs3m","avg_rs_delta","avg_vol_rank","vol_spike_pct",
                "new_52wh","ind_ret_1m","ind_ret_3m","trend_score"
            )},
            "opportunity_score": opp_score,
        })

    return sorted(setups, key=lambda x: -x["opportunity_score"])[:20]

