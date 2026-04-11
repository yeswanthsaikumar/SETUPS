#!/usr/bin/env python3
import sys
sys.path.insert(0,'apps/python/cli')
sys.path.insert(0,'apps/python/lib')
from generate_breadth_dashboard import CUSTOM_THEMES, compute_theme_metrics, _load_nifty
from html import escape
nifty = _load_nifty()
print("KEY vs BUTTON ONCLICK comparison:")
for name, cfg in CUSTOM_THEMES.items():
    tm = compute_theme_metrics(name, cfg, nifty)
    if tm:
        sb = tm.get('stock_breadth', [])
        safe_key = name.replace("'","")
        safe_btn = escape(name.replace("'",""))
        match = safe_key == safe_btn
        flag = "" if match else " <-- MISMATCH!"
        print(f"  key={safe_key!r}")
        print(f"  btn={safe_btn!r}  stocks={len(sb)}{flag}")
        print()

