"""Generate dark-theme SVG chart pattern visuals for the trading playbook.

Outputs to docs/assets/chart-patterns/. Run from project root:

    python3 scripts/generate_chart_pattern_svgs.py
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "chart-patterns"
OUT.mkdir(parents=True, exist_ok=True)

# ----- design tokens -----
W, H = 1400, 760
BG = "#070d18"
GRID = "#172338"
TEXT = "#e5edf8"
MUTED = "#9eb1c7"
GREEN = "#2ecc71"
RED = "#ff5a6e"
ENTRY = "#22c55e"
STOP = "#ef4444"
T1 = "#7dd3fc"
T2 = "#60a5fa"
TRAIL = "#f59e0b"
MAXGAIN = "#fbbf24"
PIVOT = "#facc15"
ACCENT = "#4da3ff"
VOL_UP = "#2f6f49"
VOL_DN = "#6e3745"

# chart panel
PX0, PX1 = 80, 1320
PY0, PY1 = 60, 560        # price area (top-bottom, top is small y)
VY0, VY1 = 600, 720       # volume area


def header(title: str, subtitle: str = "") -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">',
        f'<title id="t">{title}</title>',
        f'<desc id="d">{subtitle or title}</desc>',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        # grid
        '<g stroke="{g}" stroke-width="1">'.format(g=GRID),
        '<path d="M80 70H1320M80 140H1320M80 210H1320M80 280H1320M80 350H1320M80 420H1320M80 490H1320M80 560H1320"/>',
        '<path d="M120 60V580M220 60V580M320 60V580M420 60V580M520 60V580M620 60V580M720 60V580M820 60V580M920 60V580M1020 60V580M1120 60V580M1220 60V580"/>',
        '</g>',
        f'<text x="90" y="42" fill="{TEXT}" font-size="26" font-family="Arial, sans-serif" font-weight="600">{title}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="90" y="64" fill="{MUTED}" font-size="14" font-family="Arial, sans-serif">{subtitle}</text>')
    return "\n".join(parts)


def footer() -> str:
    return "</svg>\n"


# ----- helpers -----

def y_from_price(p: float, lo: float, hi: float) -> float:
    """Map price to y in price panel. hi maps near top (PY0), lo near bottom (PY1)."""
    if hi == lo:
        return (PY0 + PY1) / 2
    frac = (p - lo) / (hi - lo)
    return PY1 - frac * (PY1 - PY0)


def candle(x: float, o: float, h: float, l: float, c: float, lo: float, hi: float) -> str:
    color = GREEN if c >= o else RED
    yh = y_from_price(h, lo, hi)
    yl = y_from_price(l, lo, hi)
    yo = y_from_price(o, lo, hi)
    yc = y_from_price(c, lo, hi)
    body_top = min(yo, yc)
    body_h = max(2.0, abs(yo - yc))
    return (
        f'<line x1="{x}" y1="{yh:.1f}" x2="{x}" y2="{yl:.1f}" stroke="{color}"/>'
        f'<rect x="{x-7}" y="{body_top:.1f}" width="14" height="{body_h:.1f}" fill="{color}"/>'
    )


def candles(seq: Sequence[Tuple[float, float, float, float, float]], lo: float, hi: float) -> str:
    """seq of (x, o, h, l, c)."""
    return "\n".join(candle(x, o, h, l, c, lo, hi) for (x, o, h, l, c) in seq)


def vol_bars(bars: Sequence[Tuple[float, float, str]], max_h: float = 100) -> str:
    """bars: (x, height_units 0..1, 'up'|'dn')."""
    out = []
    base = VY1
    for (x, hf, kind) in bars:
        col = VOL_UP if kind == "up" else VOL_DN
        h = max(3.0, hf * max_h)
        out.append(f'<rect x="{x-12}" y="{base-h:.1f}" width="24" height="{h:.1f}" fill="{col}"/>')
    return "\n".join(out)


def hline(y: float, color: str, dash: str = "6 6", x0: int = PX0, x1: int = PX1, w: int = 2) -> str:
    return f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{color}" stroke-dasharray="{dash}" stroke-width="{w}"/>'


def vline(x: float, color: str, dash: str = "5 5", y0: int = PY0, y1: int = PY1, w: int = 1) -> str:
    return f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{color}" stroke-dasharray="{dash}" stroke-width="{w}"/>'


def label(x: float, y: float, txt: str, color: str = TEXT, size: int = 14, weight: int = 400) -> str:
    return f'<text x="{x}" y="{y:.1f}" fill="{color}" font-size="{size}" font-family="Arial, sans-serif" font-weight="{weight}">{txt}</text>'


def arrow(x1: float, y1: float, x2: float, y2: float, color: str = TEXT) -> str:
    return (
        f'<defs><marker id="a-{abs(int(x1+y1+x2+y2))}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{color}"/></marker></defs>'
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2" marker-end="url(#a-{abs(int(x1+y1+x2+y2))})"/>'
    )


def legend_trade_plan(x: int = 1020, y: int = 80) -> str:
    items = [
        ("Entry", ENTRY),
        ("Stop", STOP),
        ("Target 1", T1),
        ("Target 2 / Max", T2),
        ("Trail line", TRAIL),
    ]
    lines = [f'<rect x="{x-10}" y="{y-18}" width="280" height="120" rx="8" fill="#0d1626" stroke="{GRID}"/>']
    for i, (name, col) in enumerate(items):
        yy = y + i * 22
        lines.append(f'<line x1="{x}" y1="{yy}" x2="{x+30}" y2="{yy}" stroke="{col}" stroke-dasharray="6 6" stroke-width="2"/>')
        lines.append(label(x + 40, yy + 4, name, TEXT, 13))
    return "\n".join(lines)


# ============================================================
# Pattern generators
# ============================================================

def gen_path_chart(
    filename: str,
    title: str,
    subtitle: str,
    points: Sequence[Tuple[float, float]],   # (x, price)
    lo: float,
    hi: float,
    annotations: List[Tuple[float, str, str]],  # (price, color, label)
    vol_seq: Sequence[Tuple[float, float, str]],
    notes: List[Tuple[float, float, str, str]] = None,  # (x, y, text, color)
    candles_seq: Sequence[Tuple[float, float, float, float, float]] = (),
    show_legend: bool = True,
    extra_svg: str = "",
) -> None:
    parts = [header(title, subtitle)]

    # price polyline
    if points:
        d = " ".join(
            ("M" if i == 0 else "L") + f"{x:.1f} {y_from_price(p, lo, hi):.1f}"
            for i, (x, p) in enumerate(points)
        )
        parts.append(f'<path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="2.5"/>')

    if candles_seq:
        parts.append(candles(candles_seq, lo, hi))

    # horizontal annotations
    for price, color, txt in annotations:
        y = y_from_price(price, lo, hi)
        parts.append(hline(y, color))
        parts.append(label(PX1 - 220, y - 6, txt, color, 13, 600))

    # volume
    parts.append(vol_bars(vol_seq))
    parts.append(label(PX0 + 10, VY0 - 8, "Volume", MUTED, 13))

    # notes
    if notes:
        for (x, y, t, c) in notes:
            parts.append(label(x, y, t, c, 13, 600))

    if show_legend:
        parts.append(legend_trade_plan())

    if extra_svg:
        parts.append(extra_svg)

    parts.append(footer())
    (OUT / filename).write_text("\n".join(parts))


# ----- specific patterns -----

def make_bull_flag_tp() -> None:
    # pole rises 100->150, flag drifts 150->142, breakout to 175 (T1), trail toward 195 (T2/max)
    pole = [(120, 100), (180, 108), (240, 118), (300, 130), (360, 142), (420, 150)]
    flag = [(460, 148), (500, 146), (540, 144), (580, 143), (620, 144), (660, 146)]
    bo   = [(700, 152), (760, 162), (820, 172), (880, 180), (940, 188), (1000, 192), (1060, 196)]
    pts = pole + flag + bo
    lo, hi = 90, 210

    annots = [
        (150, ENTRY, "Entry: break > 150 flag high"),
        (142, STOP, "Stop: < 142 flag low"),
        (170, T1, "T1: +1R (≈158) → trim 1/3"),
        (185, T2, "T2: pole projection ≈ 195 (max)"),
    ]
    # trail line slope under price action
    trail_pts = [(420, 138), (700, 145), (1060, 175)]
    trail_d = " ".join(("M" if i == 0 else "L") + f"{x:.1f} {y_from_price(p,lo,hi):.1f}" for i,(x,p) in enumerate(trail_pts))
    extra = f'<path d="{trail_d}" fill="none" stroke="{TRAIL}" stroke-width="2" stroke-dasharray="6 6"/>'
    extra += label(1070, y_from_price(175,lo,hi)-6, "Trail under higher lows", TRAIL, 12)

    # volume: rising on pole, drying in flag, expanding on breakout
    vol = []
    for x in range(120, 421, 60): vol.append((x, 0.45 + (x-120)/600, "up"))
    for x in range(460, 661, 40): vol.append((x, 0.25 - (x-460)/2000, "dn"))
    for x in range(700, 1061, 60): vol.append((x, 0.6 + (x-700)/700, "up"))

    notes = [
        (140, 88, "1) POLE: high vol drive", GREEN),
        (470, 88, "2) FLAG: orderly drift, vol dry-up", MUTED),
        (790, 88, "3) BREAKOUT: vol expansion + strong close", GREEN),
        (90, 590, "Max gain logic: pole height (≈50) projected from breakout = ≈+30% potential", MAXGAIN),
    ]

    gen_path_chart(
        "tp-bull-flag.svg",
        "Bull Flag — Entry / Stop / Targets / Trail / Max Gain",
        "Pole drive, flag dry-up, breakout, manage with R-multiples and trail",
        pts, lo, hi, annots, vol, notes, extra_svg=extra,
    )


def make_pennant_main() -> None:
    impulse = [(120, 100), (180, 110), (240, 122), (300, 134), (360, 144), (420, 152)]
    coil_top = [(460, 152), (520, 150), (580, 149), (640, 148), (700, 148)]
    coil_bot = [(460, 138), (520, 142), (580, 145), (640, 147), (700, 148)]
    pts = impulse + [(420,152)] + coil_top
    lo, hi = 90, 200

    # draw triangle lines
    extra_lines = []
    extra_lines.append(f'<line x1="420" y1="{y_from_price(152,lo,hi):.1f}" x2="700" y2="{y_from_price(148,lo,hi):.1f}" stroke="{ACCENT}" stroke-dasharray="4 4" stroke-width="1.5"/>')
    extra_lines.append(f'<line x1="420" y1="{y_from_price(138,lo,hi):.1f}" x2="700" y2="{y_from_price(148,lo,hi):.1f}" stroke="{ACCENT}" stroke-dasharray="4 4" stroke-width="1.5"/>')
    bo = [(700, 148), (760, 158), (820, 170), (880, 180), (940, 188), (1000, 194)]
    pts = impulse + bo

    annots = [
        (152, ENTRY, "Entry: close > triangle apex (~152)"),
        (140, STOP, "Stop: < last higher low (140)"),
        (180, T1, "T1: prior impulse extension"),
        (195, T2, "T2: measured move from widest range (max ≈ +28%)"),
    ]

    vol = []
    for x in range(120, 421, 60): vol.append((x, 0.55 + (x-120)/700, "up"))
    for x in range(460, 681, 40): vol.append((x, 0.30 - (x-460)/1400, "dn"))
    for x in range(720, 1001, 60): vol.append((x, 0.7 + (x-720)/600, "up"))

    notes = [
        (140, 88, "Impulse leg", GREEN),
        (470, 88, "Coil — vol dries, lower highs + higher lows", MUTED),
        (740, 88, "Breakout with expansion", GREEN),
        (90, 590, "Pattern says energy. Trade plan says risk. Combine both before entry.", MAXGAIN),
    ]

    gen_path_chart(
        "5-2-pennant.svg",
        "Pennant / Symmetrical Triangle — Continuation",
        "Impulse, coil, breakout — annotated trade plan",
        pts, lo, hi, annots, vol, notes, extra_svg="\n".join(extra_lines),
    )


def make_ascending_triangle_tp() -> None:
    base = [(120, 100), (180, 110), (240, 120), (300, 130), (360, 140)]
    # 3 tests of 150 with rising lows
    swings = [(420, 150),(480, 138),(540, 150),(600, 142),(660, 150),(720, 146),(780, 150)]
    bo = [(820, 156),(880, 166),(940, 176),(1000, 184),(1060, 190),(1120, 195)]
    pts = base + swings + bo
    lo, hi = 90, 210

    extra = []
    # flat top resistance
    extra.append(f'<line x1="420" y1="{y_from_price(150,lo,hi):.1f}" x2="780" y2="{y_from_price(150,lo,hi):.1f}" stroke="{PIVOT}" stroke-width="2"/>')
    # rising trendline through lows
    extra.append(f'<line x1="480" y1="{y_from_price(138,lo,hi):.1f}" x2="720" y2="{y_from_price(146,lo,hi):.1f}" stroke="{ACCENT}" stroke-dasharray="4 4"/>')

    annots = [
        (150, ENTRY, "Entry: break > 150 with vol expansion"),
        (144, STOP, "Stop: < last higher low (144)"),
        (172, T1, "T1: +2R partial"),
        (190, T2, "T2: triangle height projection (max ≈ +27%)"),
    ]

    vol = []
    for x in range(120, 361, 60): vol.append((x, 0.5, "up"))
    for x in range(420, 781, 60): vol.append((x, max(0.18, 0.45 - (x-420)/1500), "up" if x not in (480,600,720) else "dn"))
    for x in range(820, 1121, 60): vol.append((x, 0.7 + (x-820)/700, "up"))

    notes = [
        (430, 88, "Resistance defended (3-5 tests)", PIVOT),
        (820, 88, "Breakout — fresh participation", GREEN),
        (90, 590, "Trail under each new higher low; do not lower stop after breakout.", TRAIL),
    ]

    gen_path_chart(
        "tp-ascending-triangle.svg",
        "Ascending Triangle — Trade Plan",
        "Flat top + rising lows; sized risk under last higher low",
        pts, lo, hi, annots, vol, notes, extra_svg="\n".join(extra),
    )


def make_high_tight_flag() -> None:
    # vertical run 100 -> 200, then tight shelf 188-198, then break to 250
    run = [(120, 100),(180, 118),(240, 138),(300, 158),(360, 178),(420, 196),(460, 200)]
    shelf = [(500, 196),(540, 192),(580, 190),(620, 192),(660, 196),(700, 198)]
    bo = [(740, 206),(800, 220),(860, 234),(920, 242),(980, 248)]
    pts = run + shelf + bo
    lo, hi = 80, 270

    annots = [
        (200, ENTRY, "Entry: clean break > 200 (no gap chase)"),
        (188, STOP, "Stop: < shelf low 188 (~6%)"),
        (228, T1, "T1: +2R partial (≈ +14%)"),
        (260, T2, "T2: trail — HTF can run +50-100%"),
    ]
    vol = []
    for x in range(120, 461, 60): vol.append((x, 0.6 + (x-120)/500, "up"))
    for x in range(500, 701, 40): vol.append((x, 0.25 - (x-500)/2200, "dn"))
    for x in range(740, 981, 60): vol.append((x, 0.85 + (x-740)/600, "up"))

    notes = [
        (140, 88, "Vertical run (90-100%+)", GREEN),
        (520, 88, "Tight shelf, no distribution", MUTED),
        (760, 88, "Explosion through pivot", GREEN),
        (90, 590, "HTF max-gain logic: don't anchor to a measured move. Trail under 21EMA / shelf.", MAXGAIN),
    ]

    gen_path_chart(
        "5-4-high-tight-flag.svg",
        "High Tight Flag — Continuation",
        "Vertical run, tight shelf, breakout — trail aggressively",
        pts, lo, hi, annots, vol, notes,
    )


def make_cup_handle_tp() -> None:
    # cup: 150 -> 100 -> 148, handle 138-148, breakout 160 -> 200
    left = [(120, 150),(180, 140),(240, 128),(300, 116),(360, 108),(420, 102),(480, 100)]
    right = [(540, 104),(600, 114),(660, 126),(720, 136),(780, 144),(820, 148)]
    handle = [(840, 146),(880, 142),(920, 140),(960, 142),(1000, 146),(1020, 148)]
    bo = [(1060, 156),(1100, 168),(1160, 180),(1220, 192)]
    pts = left + right + handle + bo
    lo, hi = 80, 220

    annots = [
        (148, ENTRY, "Entry: break > handle high 148"),
        (138, STOP, "Stop: < handle low 138 (≈ 7%)"),
        (175, T1, "T1: +2R partial"),
        (200, T2, "T2: cup depth projection (max ≈ +35%)"),
    ]
    vol = []
    # cup decline heavy, mid quiet, right side improving, handle dry, breakout big
    seq = [(120,0.85,"dn"),(180,0.7,"dn"),(240,0.55,"dn"),(300,0.4,"dn"),(360,0.3,"dn"),(420,0.22,"dn"),(480,0.2,"dn"),
           (540,0.3,"up"),(600,0.4,"up"),(660,0.5,"up"),(720,0.6,"up"),(780,0.65,"up"),(820,0.55,"up"),
           (860,0.25,"dn"),(900,0.2,"dn"),(940,0.18,"dn"),(980,0.2,"dn"),(1020,0.22,"up"),
           (1080,0.95,"up"),(1140,1.05,"up"),(1200,1.1,"up")]
    vol = seq

    notes = [
        (140, 88, "Cup decline (panic, heavy vol)", RED),
        (540, 88, "Right-side rebuild (vol improving)", GREEN),
        (840, 88, "Handle (calm drift, quiet)", MUTED),
        (1080, 88, "Breakout > pivot", GREEN),
        (90, 590, "Max gain target = cup depth projected from pivot. Trail under 10/21 EMA.", MAXGAIN),
    ]

    gen_path_chart(
        "tp-cup-handle.svg",
        "Cup with Handle — Trade Plan",
        "Pivot above handle high, stop below handle low, target = cup depth projection",
        pts, lo, hi, annots, vol, notes,
    )


def make_flat_base() -> None:
    rise = [(120, 100),(180, 112),(240, 124),(300, 136),(360, 145)]
    base = [(420, 150),(480, 148),(540, 145),(600, 144),(660, 146),(720, 148),(780, 145),(840, 147),(900, 150)]
    bo = [(940, 156),(1000, 166),(1060, 176),(1120, 184),(1180, 190)]
    pts = rise + base + bo
    lo, hi = 90, 210

    extra = f'<line x1="420" y1="{y_from_price(150,lo,hi):.1f}" x2="900" y2="{y_from_price(150,lo,hi):.1f}" stroke="{PIVOT}" stroke-width="2"/>'
    extra += f'<line x1="420" y1="{y_from_price(144,lo,hi):.1f}" x2="900" y2="{y_from_price(144,lo,hi):.1f}" stroke="{ACCENT}" stroke-dasharray="4 4"/>'

    annots = [
        (150, ENTRY, "Entry: close > 150 base top"),
        (143, STOP, "Stop: < 143 base low"),
        (165, T1, "T1: +2R"),
        (188, T2, "T2: prior impulse extension (max ≈ +25%)"),
    ]
    vol = []
    for x in range(120, 361, 60): vol.append((x, 0.55 + (x-120)/600, "up"))
    for x in range(420, 901, 60): vol.append((x, max(0.12, 0.45 - (x-420)/1500), "up" if (x//60)%2==0 else "dn"))
    for x in range(940, 1181, 60): vol.append((x, 0.85 + (x-940)/600, "up"))

    notes = [
        (430, 88, "Flat base — tight range, vol declining", MUTED),
        (940, 88, "Break of base top with expansion", GREEN),
        (90, 590, "Best when: 4-6 weeks of base, drying vol, no 10%+ correction during base.", MAXGAIN),
    ]

    gen_path_chart(
        "6-2-flat-base.svg",
        "Flat Base — Structured Breakout",
        "Sideways consolidation after advance; pivot = base top",
        pts, lo, hi, annots, vol, notes, extra_svg=extra,
    )


def make_double_bottom_tp() -> None:
    decline = [(120, 200),(180, 180),(240, 160),(300, 140),(360, 124),(420, 112)]
    rebound = [(480, 130),(540, 144),(600, 152),(660, 148)]
    second  = [(720, 134),(780, 118),(800, 110)]  # undercut
    reclaim = [(840, 130),(900, 145),(960, 152)]
    bo = [(1000, 162),(1060, 174),(1120, 184),(1180, 192)]
    pts = decline + rebound + second + reclaim + bo
    lo, hi = 90, 220

    annots = [
        (152, ENTRY, "Entry: break > midpoint pivot 152"),
        (108, STOP, "Stop: < second-low 108"),
        (180, T1, "T1: +2R partial"),
        (196, T2, "T2: base height projection (max ≈ +30%)"),
    ]
    vol = []
    seq = [(120,0.95,"dn"),(180,1.0,"dn"),(240,0.85,"dn"),(300,0.7,"dn"),(360,0.55,"dn"),(420,0.45,"dn"),
           (480,0.4,"up"),(540,0.45,"up"),(600,0.35,"up"),(660,0.3,"dn"),
           (720,0.3,"dn"),(780,0.25,"dn"),
           (840,0.55,"up"),(900,0.7,"up"),(960,0.6,"up"),
           (1020,1.0,"up"),(1080,1.05,"up"),(1140,1.1,"up")]
    vol = seq

    notes = [
        (140, 88, "1st low (heavy panic vol)", RED),
        (560, 88, "Rebound to midpoint (lighter vol)", MUTED),
        (740, 88, "2nd low — undercut on lighter vol = strength", GREEN),
        (1000, 88, "Pivot break with expansion", GREEN),
        (90, 590, "If 2nd low prints heavier vol than 1st = false W; skip.", RED),
    ]

    gen_path_chart(
        "tp-double-bottom.svg",
        "Double Bottom — Trade Plan",
        "Two lows + midpoint pivot. Undercut + reclaim is the strongest variant.",
        pts, lo, hi, annots, vol, notes,
    )


def make_vcp_tp() -> None:
    # 3 contractions: 12% / 8% / 4%
    pts = [(120, 100),(180, 116),(240, 130),(300, 142),(360, 152),(420, 156)]
    # contraction 1: 156->137 (12%)
    pts += [(460, 154),(500, 146),(540, 140),(580, 137)]
    # rebuild 1
    pts += [(620, 142),(660, 150),(700, 156)]
    # contraction 2: 156->143 (8%)
    pts += [(740, 154),(780, 148),(820, 144),(860, 143)]
    # rebuild 2
    pts += [(900, 148),(940, 154),(980, 156)]
    # contraction 3: 156->150 (4%) tight
    pts += [(1000, 154),(1020, 152),(1040, 150),(1060, 152),(1080, 154),(1100, 156)]
    # breakout
    pts += [(1140, 164),(1180, 174),(1220, 184),(1260, 192)]
    lo, hi = 90, 210

    annots = [
        (156, ENTRY, "Entry: break of final pivot 156"),
        (149, STOP, "Stop: < final contraction low 149 (~ 4-5%)"),
        (175, T1, "T1: +2R / +3R partial"),
        (192, T2, "T2: trail under 10EMA (max often +30-50%)"),
    ]
    # mark contractions
    extra = []
    for (cx, low) in [(580, 137),(860, 143),(1040, 150)]:
        extra.append(f'<circle cx="{cx}" cy="{y_from_price(low,lo,hi):.1f}" r="6" fill="none" stroke="{TRAIL}" stroke-width="2"/>')

    vol = []
    # decreasing volume each contraction
    for x in range(120, 421, 60): vol.append((x, 0.55, "up"))
    for x in range(460, 581, 40): vol.append((x, 0.45 - (x-460)/600, "dn"))
    for x in range(620, 701, 40): vol.append((x, 0.35, "up"))
    for x in range(740, 861, 40): vol.append((x, 0.30 - (x-740)/800, "dn"))
    for x in range(900, 981, 40): vol.append((x, 0.25, "up"))
    for x in range(1000, 1101, 20): vol.append((x, 0.13, "dn"))
    for x in range(1140, 1261, 40): vol.append((x, 0.95 + (x-1140)/500, "up"))

    notes = [
        (470, 88, "C1 — 12% pullback", MUTED),
        (740, 88, "C2 — 8% (smaller)", MUTED),
        (1000, 88, "C3 — 4% (tightest)", GREEN),
        (1140, 88, "Breakout — vol urgency", GREEN),
        (90, 590, "If contractions WIDEN (10→14→18%), pattern is broken. Stand aside.", RED),
    ]

    gen_path_chart(
        "tp-vcp.svg",
        "VCP — Trade Plan with Contraction Markers",
        "Each pullback tighter; final pivot = trigger; trail below 10EMA",
        pts, lo, hi, annots, vol, notes, extra_svg="\n".join(extra),
    )


def make_inverse_hs_tp() -> None:
    pts = [(120, 200),(180, 180),(240, 160),(300, 145),(360, 138),  # left shoulder low
           (420, 152),(480, 158),(540, 150),(600, 130),(660, 118),(700, 115),  # head low
           (740, 130),(780, 148),(820, 158),(860, 152),(900, 144),(940, 142),  # right shoulder low (less deep)
           (980, 152),(1020, 162),(1060, 170),  # to neckline
           (1100, 178),(1160, 188),(1220, 196)]  # breakout
    lo, hi = 90, 220

    extra = []
    # neckline ~160
    extra.append(f'<line x1="360" y1="{y_from_price(160,lo,hi):.1f}" x2="1060" y2="{y_from_price(160,lo,hi):.1f}" stroke="{PIVOT}" stroke-width="2"/>')
    # head/shoulder labels
    extra.append(label(360, y_from_price(138,lo,hi)+24, "L. Shoulder", MUTED, 12))
    extra.append(label(680, y_from_price(115,lo,hi)+24, "Head (capitulation)", RED, 12))
    extra.append(label(900, y_from_price(142,lo,hi)+24, "R. Shoulder (lighter)", GREEN, 12))

    annots = [
        (160, ENTRY, "Entry: break > neckline 160"),
        (140, STOP, "Stop: < right shoulder 140"),
        (180, T1, "T1: +2R"),
        (205, T2, "T2: head→neckline projected up (max ≈ +28%)"),
    ]
    vol = []
    seq = [(120,0.85,"dn"),(180,0.95,"dn"),(240,0.7,"dn"),(300,0.55,"dn"),(360,0.5,"dn"),
           (420,0.4,"up"),(480,0.45,"up"),(540,0.4,"dn"),(600,0.65,"dn"),(660,0.85,"dn"),(720,0.5,"up"),
           (780,0.4,"up"),(820,0.35,"up"),(860,0.3,"dn"),(900,0.25,"dn"),(940,0.22,"dn"),
           (980,0.4,"up"),(1020,0.55,"up"),(1080,1.0,"up"),(1140,1.1,"up"),(1200,1.15,"up")]
    vol = seq

    notes = [
        (90, 590, "Right shoulder must be SHALLOWER than head, with lighter vol — proves sellers are exhausted.", MAXGAIN),
    ]
    gen_path_chart(
        "tp-inverse-hs.svg",
        "Inverse Head & Shoulders — Trade Plan",
        "Neckline trigger, stop under right shoulder, target = head-to-neckline projection",
        pts, lo, hi, annots, vol, notes, extra_svg="\n".join(extra),
    )


def make_rounding_bottom() -> None:
    # smooth U
    pts = []
    for i in range(40):
        x = 120 + i*30
        # parabola: low at i=20 (~price 100), top edges 180
        p = 100 + 0.18*(i-20)**2
        pts.append((x, p))
    bo = [(1320, pts[-1][1]+8), (1360, pts[-1][1]+18)]
    pts = [(p[0], p[1]) for p in pts if p[0] <= 1240]
    pts += [(1280, 188), (1320, 200)]
    lo, hi = 90, 230

    annots = [
        (180, ENTRY, "Entry: break of saucer pivot 180"),
        (165, STOP, "Stop: < last higher low / breakout candle low"),
        (200, T1, "T1: +2R partial"),
        (225, T2, "T2: depth projection (max often runs months)"),
    ]
    vol = []
    # quiet at bottom, improves into right side
    for i, (x, _) in enumerate(pts):
        kind = "dn" if i < 15 else "up"
        h = max(0.12, 0.7 - (abs(i-20)/20)*0.55)
        vol.append((x, h, kind))

    notes = [
        (90, 590, "Slow accumulation. Hold longer; target by trailing under 50/200 SMA.", MAXGAIN),
    ]
    gen_path_chart(
        "7-2-rounding-bottom.svg",
        "Rounding Bottom / Saucer — Reversal",
        "Smooth U-turn, 6-12 weeks, accumulation signature, breakout starts trend",
        pts, lo, hi, annots, vol, notes,
    )


def make_undercut_reclaim() -> None:
    pts = [(120, 160),(180, 156),(240, 152),(300, 148),(360, 145),(420, 142),
           (480, 140),(540, 138),(600, 132),(660, 122),  # undercut intraday low
           (700, 134),(740, 144),(780, 152),(820, 156),  # reclaim
           (860, 162),(920, 170),(980, 178),(1040, 184),(1100, 190)]
    lo, hi = 90, 210

    extra = []
    extra.append(hline(y_from_price(140, lo, hi), PIVOT, "8 8"))
    extra.append(label(PX1 - 230, y_from_price(140, lo, hi) - 6, "Support 140", PIVOT, 13, 600))

    annots = [
        (152, ENTRY, "Entry: reclaim close > 140 + follow-through > 152"),
        (122, STOP, "Stop: < undercut low 122"),
        (170, T1, "T1: midpoint of prior range"),
        (195, T2, "T2: prior resistance (max ≈ +28%)"),
    ]
    vol = []
    seq = [(120,0.4,"dn"),(180,0.45,"dn"),(240,0.45,"dn"),(300,0.5,"dn"),(360,0.55,"dn"),(420,0.6,"dn"),
           (480,0.7,"dn"),(540,0.75,"dn"),(600,0.95,"dn"),(660,1.1,"dn"),
           (700,1.0,"up"),(740,0.85,"up"),(780,0.7,"up"),(820,0.55,"up"),(860,0.7,"up"),(920,0.85,"up"),(980,1.0,"up"),(1040,1.1,"up")]
    vol = seq

    notes = [
        (110, 88, "Decline into key support", MUTED),
        (560, 88, "Undercut: panic flush (climactic vol)", RED),
        (760, 88, "Reclaim above support = trap reversal", GREEN),
        (90, 590, "Failure = close back below 140 → exit immediately. Never debate a failed reclaim.", RED),
    ]
    gen_path_chart(
        "7-3-undercut-reclaim.svg",
        "Undercut & Reclaim — Reversal",
        "Support flush + reclaim close + follow-through = trade",
        pts, lo, hi, annots, vol, notes, extra_svg="\n".join(extra),
    )


# ----- variation grids (multi-mini) -----

def variations_grid(filename: str, title: str, panels: List[Tuple[str, str, Callable[[float, float], str]]]):
    """panels: [(panel_title, verdict, draw_fn)] where draw_fn(x_origin, y_origin) returns svg snippet drawing in 600x300 area."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">',
        f'<title id="t">{title}</title>',
        f'<desc id="d">{title}</desc>',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<text x="40" y="40" fill="{TEXT}" font-size="24" font-family="Arial, sans-serif" font-weight="700">{title}</text>',
    ]
    cols = 2
    panel_w = (W - 80) // cols
    panel_h = (H - 80) // ((len(panels) + cols - 1) // cols)
    for i, (ptitle, verdict, fn) in enumerate(panels):
        ox = 40 + (i % cols) * panel_w
        oy = 70 + (i // cols) * panel_h
        # frame
        verdict_color = GREEN if verdict.startswith("Take") else (RED if verdict.startswith("Avoid") else PIVOT)
        parts.append(f'<rect x="{ox}" y="{oy}" width="{panel_w-20}" height="{panel_h-20}" rx="10" fill="#0d1626" stroke="{GRID}"/>')
        parts.append(f'<text x="{ox+16}" y="{oy+26}" fill="{TEXT}" font-size="16" font-family="Arial, sans-serif" font-weight="600">{ptitle}</text>')
        parts.append(f'<text x="{ox+16}" y="{oy+46}" fill="{verdict_color}" font-size="13" font-family="Arial, sans-serif">{verdict}</text>')
        parts.append(fn(ox + 16, oy + 60))
    parts.append("</svg>\n")
    (OUT / filename).write_text("\n".join(parts))


def mini_path(ox: float, oy: float, w: float, h: float, points: Sequence[Tuple[float, float]], lo: float, hi: float, color: str = ACCENT, marks: List[Tuple[float, float, str, str]] = None) -> str:
    if not points:
        return ""
    xs = [p[0] for p in points]
    minx, maxx = min(xs), max(xs)
    def mx(x): return ox + (x - minx) / max(1e-9, (maxx - minx)) * w
    def my(p): return oy + h - (p - lo) / max(1e-9, (hi - lo)) * h
    d = " ".join(("M" if i == 0 else "L") + f"{mx(x):.1f} {my(p):.1f}" for i,(x,p) in enumerate(points))
    out = [f'<rect x="{ox}" y="{oy}" width="{w}" height="{h}" fill="#0a1322" stroke="{GRID}"/>']
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
    if marks:
        for (px, pp, lbl, c) in marks:
            out.append(f'<circle cx="{mx(px):.1f}" cy="{my(pp):.1f}" r="4" fill="{c}"/>')
            out.append(f'<text x="{mx(px)+8:.1f}" y="{my(pp)+4:.1f}" fill="{c}" font-size="11" font-family="Arial, sans-serif">{lbl}</text>')
    return "\n".join(out)


def make_var_bull_flag():
    panels = []
    base = [(0,100),(20,108),(40,118),(60,130),(80,142),(100,150)]
    panels.append(("Tight / shallow flag (A-grade)", "Take it: minimal pullback, vol dries, fast continuation",
        lambda ox, oy: mini_path(ox, oy, 600, 240, base + [(120,148),(140,146),(160,145),(180,146),(200,148),(220,156),(240,168),(260,178)], 90, 200, GREEN)))
    panels.append(("Sideways flag (also strong)", "Take it: orderly drift sideways, dry vol",
        lambda ox, oy: mini_path(ox, oy, 600, 240, base + [(120,150),(140,148),(160,150),(180,149),(200,150),(220,156),(240,166),(260,178)], 90, 200, GREEN)))
    panels.append(("Deep flag (lower quality)", "Caution: > 50% pullback of pole, vol can rise",
        lambda ox, oy: mini_path(ox, oy, 600, 240, base + [(120,140),(140,130),(160,122),(180,118),(200,120),(220,128),(240,138),(260,148)], 90, 200, PIVOT)))
    panels.append(("Wide & loose flag (avoid)", "Avoid: wide red candles, vol expanding on red = distribution",
        lambda ox, oy: mini_path(ox, oy, 600, 240, base + [(120,142),(140,128),(160,118),(180,128),(200,116),(220,124),(240,114),(260,118)], 90, 200, RED)))
    variations_grid("var-bull-flag.svg", "Bull Flag — Variations & Verdict", panels)


def make_var_cup_handle():
    def cup_pts(depth_factor=1.0, vshape=False):
        pts = []
        for i in range(0, 21):
            x = i*12
            # parabola
            if vshape:
                p = 150 - 50*depth_factor + 5*depth_factor*abs(i-10)
            else:
                p = 100 + (50/100)*depth_factor*(i-10)**2 if False else 150 - 50*depth_factor + (50*depth_factor*(i-10)**2)/100
            pts.append((x, p))
        # handle
        for i in range(21, 31):
            x = i*12
            p = pts[-1][1] - (i-21)*1.5
            pts.append((x, p))
        return pts
    panels = [
        ("Classic U-shape (highest quality)", "Take it: rounded base, calm handle in upper half",
         lambda ox, oy: mini_path(ox, oy, 600, 240, cup_pts(1.0), 80, 160, GREEN)),
        ("V-shaped cup (lower quality)", "Caution: sharp drop & rip, weak hands not flushed",
         lambda ox, oy: mini_path(ox, oy, 600, 240, cup_pts(1.0, vshape=True), 80, 160, PIVOT)),
        ("Deep cup > 35% (wait for confirmation)", "Caution: needs strong context",
         lambda ox, oy: mini_path(ox, oy, 600, 240, cup_pts(1.5), 50, 160, PIVOT)),
        ("Loose / wide handle (avoid)", "Avoid: handle in lower half = supply not absorbed",
         lambda ox, oy: mini_path(ox, oy, 600, 240,
            [(i*12, 150 - (50*(i-10)**2)/100) for i in range(21)] +
            [(i*12, 150 - (i-20)*7) for i in range(21, 31)], 70, 160, RED)),
    ]
    variations_grid("var-cup-handle.svg", "Cup with Handle — Variations & Verdict", panels)


def make_var_vcp():
    def make_vcp_pts(contractions):
        x = 0
        pts = [(0, 100)]
        # initial run
        for i in range(1, 6):
            x += 20; pts.append((x, 100 + i*10))
        peak = pts[-1][1]
        for c, depth in enumerate(contractions):
            for i in range(1, 5):
                x += 15; pts.append((x, peak - depth*(i/4)))
            for i in range(1, 4):
                x += 15; pts.append((x, peak - depth + (depth)*(i/3)))
        # breakout
        for i in range(1, 6):
            x += 20; pts.append((x, peak + i*5))
        return pts
    panels = [
        ("2-contraction VCP (acceptable)", "Take it carefully: needs strong context",
         lambda ox, oy: mini_path(ox, oy, 600, 240, make_vcp_pts([20, 12]), 70, 200, PIVOT)),
        ("3-contraction VCP (classic)", "Take it: 12 → 8 → 4 percent contractions, dry vol",
         lambda ox, oy: mini_path(ox, oy, 600, 240, make_vcp_pts([20, 12, 6]), 70, 200, GREEN)),
        ("4-contraction VCP (excellent if tight)", "Take it: prolonged supply absorption",
         lambda ox, oy: mini_path(ox, oy, 600, 240, make_vcp_pts([18, 12, 7, 4]), 70, 200, GREEN)),
        ("Widening contractions (broken)", "Avoid: 8 → 12 → 18 percent = supply growing",
         lambda ox, oy: mini_path(ox, oy, 600, 240, make_vcp_pts([8, 14, 22]), 50, 200, RED)),
    ]
    variations_grid("var-vcp.svg", "VCP — Variations & Verdict", panels)


def make_var_double_bottom():
    base_decline = [(0,200),(20,180),(40,160),(60,140),(80,120),(100,108)]
    rebound = [(120,128),(140,140),(160,148)]
    panels = [
        ("Clean W (equal lows)", "Take it: 2nd low ≈ 1st, vol lighter on 2nd",
         lambda ox, oy: mini_path(ox, oy, 600, 240, base_decline + rebound + [(180,140),(200,124),(220,110),(240,128),(260,148),(280,160),(300,170)], 90, 210, GREEN)),
        ("Undercut & reclaim (strongest)", "Take it: 2nd low UNDERCUTS then snaps back",
         lambda ox, oy: mini_path(ox, oy, 600, 240, base_decline + rebound + [(180,140),(200,120),(220,100),(240,130),(260,150),(280,162),(300,172)], 90, 210, GREEN)),
        ("Higher 2nd low", "Take it (acceptable): 2nd low above 1st",
         lambda ox, oy: mini_path(ox, oy, 600, 240, base_decline + rebound + [(180,140),(200,128),(220,118),(240,134),(260,150),(280,160),(300,170)], 90, 210, PIVOT)),
        ("2nd low much lower (failure)", "Avoid: 2nd low breaks, no reclaim = downtrend continues",
         lambda ox, oy: mini_path(ox, oy, 600, 240, base_decline + rebound + [(180,140),(200,114),(220,96),(240,84),(260,80),(280,82),(300,78)], 70, 210, RED)),
    ]
    variations_grid("var-double-bottom.svg", "Double Bottom — Variations & Verdict", panels)


def make_var_inverse_hs():
    base = [(0,200),(20,180),(40,160),(60,148)]  # to ls low
    panels = [
        ("Classic IHS — head deepest, R.shoulder lighter", "Take it",
         lambda ox, oy: mini_path(ox, oy, 600, 240,
            base + [(80,162),(100,170),(120,164),(140,148),(160,128),(180,118),(200,135),(220,150),(240,160),(260,154),(280,150),(300,160),(320,170),(340,184)],
            100, 210, GREEN)),
        ("Symmetric shoulders (acceptable)", "Take it: clean structure",
         lambda ox, oy: mini_path(ox, oy, 600, 240,
            base + [(80,162),(100,170),(120,160),(140,140),(160,120),(180,116),(200,135),(220,150),(240,148),(260,140),(280,148),(300,160),(320,172),(340,184)],
            100, 210, GREEN)),
        ("R. shoulder LOWER than L. shoulder", "Caution: weakening pattern",
         lambda ox, oy: mini_path(ox, oy, 600, 240,
            base + [(80,162),(100,170),(120,160),(140,140),(160,124),(180,118),(200,134),(220,148),(240,142),(260,128),(280,134),(300,150),(320,160),(340,170)],
            100, 210, PIVOT)),
        ("Failed neckline break", "Avoid: breakout fails immediately",
         lambda ox, oy: mini_path(ox, oy, 600, 240,
            base + [(80,162),(100,170),(120,160),(140,140),(160,124),(180,120),(200,134),(220,148),(240,154),(260,148),(280,158),(300,164),(320,154),(340,140)],
            100, 210, RED)),
    ]
    variations_grid("var-inverse-hs.svg", "Inverse Head & Shoulders — Variations & Verdict", panels)


# ----- master runner -----

def main():
    make_bull_flag_tp()
    make_pennant_main()
    make_ascending_triangle_tp()
    make_high_tight_flag()
    make_cup_handle_tp()
    make_flat_base()
    make_double_bottom_tp()
    make_vcp_tp()
    make_inverse_hs_tp()
    make_rounding_bottom()
    make_undercut_reclaim()
    make_var_bull_flag()
    make_var_cup_handle()
    make_var_vcp()
    make_var_double_bottom()
    make_var_inverse_hs()
    files = sorted(p.name for p in OUT.glob("*.svg"))
    print(f"Generated {len(files)} SVGs in {OUT}")
    for f in files:
        print(" -", f)


if __name__ == "__main__":
    main()

