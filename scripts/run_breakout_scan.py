#!/usr/bin/env python3
"""Quick scan + backtest runner for breakout alerts."""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "python" / "lib"))
from breakout_alert_engine import BreakoutScanner, AlertConfig

ROOT = Path(__file__).resolve().parent

scanner = BreakoutScanner(
    data_dir=ROOT / "trade_data",
    cache_dir=ROOT / "cache",
)

# Load watchlist
wl_path = ROOT / "trade_data" / "watchlist.json"
symbols = []
if wl_path.exists():
    items = json.loads(wl_path.read_text())
    symbols = [i["symbol"] for i in items if i.get("symbol")]

print(f"Scanning {len(symbols)} watchlist stocks: {', '.join(symbols)}")
print("=" * 70)

results = scanner.scan_now(symbols=symbols)
print(f"\n=== Found {len(results)} signal(s) ===\n")

for s in results:
    print(f"  {s['signal_type']:12} {s['symbol']:12} Price:₹{s['close']:.1f}  "
          f"Vol:{s['volume_ratio']:.1f}x  Body:{s['body_ratio']:.0%}  "
          f"ATR:{s['atr_multiple']:.1f}x  Base:{s['consolidation_days']}d  "
          f"Score:{s['strength_score']:.0f}")
    print(f"  {'':12} {'':12} Entry:₹{s['entry_price']:.1f}  SL:₹{s['stop_loss']:.1f}  "
          f"T1:₹{s['target_1']:.1f}  T2:₹{s['target_2']:.1f}")
    print(f"  {'':12} {'':12} Level:₹{s['breakout_level']:.1f} ({s['breakout_level_type']})")
    if s.get("notes"):
        print(f"  {'':12} {'':12} {s['notes']}")
    print()

# Always run backtest to validate
print("\n" + "=" * 70)
print("Running backtest to validate detection on historical data...")
print("=" * 70)
bt = scanner.backtest_watchlist(symbols=symbols, hold_days=20)
agg = bt.get("aggregate", {})
print(f"\n  Total signals found historically: {agg.get('total_signals', 0)}")
print(f"  Win rate:      {agg.get('win_rate', 0):.1f}%")
print(f"  Avg win:       +{agg.get('avg_gain_pct', 0):.1f}%")
print(f"  Avg loss:      {agg.get('avg_loss_pct', 0):.1f}%")
print(f"  Profit factor: {agg.get('profit_factor', 0):.2f}")
print(f"  Expectancy:    {agg.get('expectancy', 0):.2f}")
print(f"  Best trade:    +{agg.get('max_gain_pct', 0):.1f}%")
print(f"  Worst trade:   {agg.get('max_loss_pct', 0):.1f}%")
print(f"  Avg hold:      {agg.get('avg_hold_days', 0):.1f} days")

print("\n  Per-symbol breakdown:")
for sym, data in bt.get("bySymbol", {}).items():
    if isinstance(data, dict) and not data.get("error"):
        n = data.get("total_signals", 0)
        if n > 0:
            print(f"    {sym:14} {n:3} signals  {data['win_rate']:.0f}% win  "
                  f"PF:{data['profit_factor']:.2f}  Exp:{data['expectancy']:.2f}")
        else:
            print(f"    {sym:14}   0 signals (no breakout candles in history)")

# Show recent trades
trades = agg.get("trades", [])
if trades:
    print(f"\n  Last {min(10, len(trades))} simulated trades:")
    for t in trades[:10]:
        gc = "+" if t["gain_pct"] > 0 else ""
        print(f"    {t['symbol']:12} {t['entry_date']} → {t['exit_date']}  "
              f"₹{t['entry']:.0f}→₹{t['exit']:.0f}  {gc}{t['gain_pct']:.1f}%  "
              f"({t['exit_reason']})  Vol:{t['volume_ratio']:.1f}x  Score:{t['strength_score']:.0f}")

print("\nDone!")

