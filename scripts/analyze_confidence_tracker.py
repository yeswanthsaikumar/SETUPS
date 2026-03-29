import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'python' / 'lib'))
sys.path.insert(0, str(ROOT / 'apps' / 'python' / 'cli'))

import generate_performance_tracker as g
import performance_tracker as pt


def main() -> None:
    data = json.loads((ROOT / 'output' / 'performance_tracker.json').read_text())
    trades = [
        dict(t) for t in data.get('trades', [])
        if t.get('market') == 'india' and t.get('timeframe') in ('daily', 'weekly')
    ]
    for t in trades:
        t.update(g.evaluate_trade_quality(t))

    def subset_stats(items):
        stats = pt.compute_summary_stats(items)
        total = len(items)
        sl_rate = (sum(1 for t in items if t.get('status') == 'SL_HIT') * 100.0 / total) if total else 0.0
        target_rate = (sum(1 for t in items if t.get('status') in ('T1_HIT', 'T2_HIT', 'T3_HIT')) * 100.0 / total) if total else 0.0
        return {
            'count': total,
            'winRate': stats['winRate'],
            'avgGainPct': stats['avgGainPct'],
            'targetRate': round(target_rate, 1),
            'slRate': round(sl_rate, 1),
        }

    print('ALL', subset_stats(trades))
    for cut in (60, 70, 80, 90):
        subset = [t for t in trades if float(t.get('confidence', 0)) >= cut and not t.get('weakFundamentals')]
        print(f'CONF_{cut}', subset_stats(subset))


if __name__ == '__main__':
    main()

