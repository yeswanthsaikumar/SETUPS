#!/usr/bin/env python3
"""Compare performance before/after quality gate improvements across confidence tiers and timeframes."""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "python" / "lib"))
sys.path.insert(0, str(ROOT / "apps" / "python" / "cli"))

import generate_performance_tracker as g
import performance_tracker as pt

data   = json.loads((ROOT / "output" / "performance_tracker.json").read_text())
trades = [
    dict(t) for t in data.get("trades", [])
    if t.get("market") == "india" and t.get("timeframe") in ("daily", "weekly")
]
for t in trades:
    t.update(g.evaluate_trade_quality(t))

def show(label: str, items: list[dict]) -> None:
    s = pt.compute_summary_stats(items)
    n = s["total"]
    sl_rate  = s["slHits"]  / n * 100 if n else 0
    tgt_rate = s["targetHits"] / n * 100 if n else 0
    print(f"  {label:28} n={n:4}  wr={s['winRate']:5.1f}%  avg={s['avgGainPct']:+6.2f}%"
          f"  tgt={tgt_rate:4.1f}%  sl={sl_rate:4.1f}%")

print("\n=== OVERALL ===")
show("ALL trades", trades)
for tf in ("daily", "weekly"):
    show(f"{tf.upper()} all", [t for t in trades if t["timeframe"] == tf])

print("\n=== BY CONFIDENCE TIER (no weak fundamentals) ===")
for cut in (60, 65, 70, 75, 80, 85, 90):
    sub = [t for t in trades if float(t.get("confidence", 0)) >= cut and not t.get("weakFundamentals")]
    show(f"Conf {cut}+", sub)

print("\n=== BY TIMEFRAME × CONFIDENCE 70+ ===")
for tf in ("daily", "weekly"):
    sub = [t for t in trades if t["timeframe"] == tf
           and float(t.get("confidence", 0)) >= 70
           and not t.get("weakFundamentals")]
    show(f"{tf.upper()} conf70+", sub)

print("\n=== TOP 20 HIGHEST-CONFIDENCE PICKS ===")
top = sorted(
    [t for t in trades if not t.get("weakFundamentals")],
    key=lambda x: (-float(x.get("confidence", 0)), -float(x.get("score", 0)))
)[:20]
for t in top:
    sym    = t["symbol"].replace(".NS", "").replace(".BO", "")
    conf   = int(float(t.get("confidence", 0)))
    rating = t.get("rating", "?")
    rs3m   = float(t.get("rs3mAtScan", 0))
    gain   = float(t.get("gainPct", 0))
    status = t.get("status", "OPEN")
    tf     = t.get("timeframe", "?")
    td     = t.get("tradeDate", "?")
    reasons = "; ".join(t.get("pickReasons", []))
    print(f"  {sym:16} conf={conf:3}  {rating:2}  {tf:6}  {td}  rs3m={rs3m:+6.1f}%  "
          f"gain={gain:+6.2f}%  {status:8}  [{reasons}]")

print("\n=== EXCLUDED SUMMARY ===")
excl = [t for t in trades if not t.get("include")]
by_reason: dict[str, int] = {}
for t in excl:
    r = t.get("excludeReason", "unknown")
    by_reason[r] = by_reason.get(r, 0) + 1
for r, n in sorted(by_reason.items(), key=lambda x: -x[1]):
    print(f"  {n:4}×  {r}")

