#!/usr/bin/env python3
"""Top-view preview of the caliper beam's engraved scale.

Draws the scale exactly as `caliper.beam()` cuts it - the major graduations as
0.6 mm circles and the numerals as 0.40 mm channels centred under them - at 1:1
and zoomed, into `cad/out/beam.html`.

    python cad/tools/beam_preview.py
"""

from __future__ import annotations

import sys
from pathlib import Path

CAD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CAD))

import caliper                       # noqa: E402
import vecfont                       # noqa: E402

OUT = CAD / "out" / "beam.html"

BAR = caliper.scale_bar_rect()
TICK_R = 0.6
TICK_Y = caliper.SCALE_TOP - 1.2
LABEL_Y = caliper.SCALE_TOP - 4.2
STROKE = max(0.40, 0.14 * caliper.NUM_SIZE)


def labels_svg():
    """Every engraved numeral, as stroked paths in beam coordinates (y up)."""
    unit = caliper.NUM_SIZE / vecfont.CAP
    out = []
    for tick in caliper.SCALE_TICKS:
        if not (tick["label"] or tick["kind"] == "major"):
            continue
        placed, ink = vecfont.layout(str(tick["value"]), caliper.NUM_SIZE, STROKE)
        left = tick["mm"] - ink / 2.0
        baseline = LABEL_Y - caliper.NUM_SIZE / 2.0
        for glyph, dx in placed:
            for pts in glyph:
                if len(pts) == 1:
                    x = left + dx + pts[0][0] * unit
                    y = baseline + pts[0][1] * unit
                    out.append(f'<path d="M{x:.3f},{y:.3f} L{x:.3f},{y:.3f}"/>')
                else:
                    d = "M" + " L".join(
                        f"{left + dx + px * unit:.3f},{baseline + py * unit:.3f}"
                        for px, py in pts)
                    out.append(f'<path d="{d}"/>')
    return "".join(out)


def ticks_svg():
    out = []
    for tick in caliper.SCALE_TICKS:
        if tick["kind"] != "major":
            continue
        out.append(f'<circle cx="{tick["mm"]:.3f}" cy="{TICK_Y}" r="{TICK_R}"/>')
    return "".join(out)


def section(x0, x1, px_per_mm, height_px=None):
    w = (x1 - x0) * px_per_mm
    h = caliper.BEAM_H * px_per_mm
    body = (
        f'<g transform="translate(0,{caliper.BEAM_H}) scale(1,-1)">'
        f'<rect x="{x0}" y="0" width="{x1 - x0}" height="{caliper.BEAM_H}" '
        f'fill="#f5f2ec" stroke="#d8d1c6" stroke-width="0.15"/>'
        f'<rect x="{BAR[0]}" y="{BAR[2]}" width="{BAR[1] - BAR[0]}" '
        f'height="{BAR[3] - BAR[2]}" fill="#e3dbcd"/>'
        f'<g fill="#2b2b2b">{ticks_svg()}</g>'
        f'<g fill="none" stroke="#2b2b2b" stroke-width="{STROKE}" '
        f'stroke-linecap="round" stroke-linejoin="round">{labels_svg()}</g>'
        f'</g>'
    )
    return (f'<svg width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="{x0} 0 {x1 - x0} {caliper.BEAM_H}">{body}</svg>')


def stack_svg():
    """Z section through the scale strip.  z is exaggerated so the 0.2 mm inlay
    and the 0.4 mm top layer are readable; x is schematic."""
    xs, zs = 12.0, 40.0                    # px per mm
    left, top = 12.0, 26.0
    X = lambda x: left + x * xs
    Y = lambda z: top + (4.4 - z) * zs
    w, h = 60, 4.4
    white, black, bg = "#ffffff", "#1e1e1e", "#faf9f7"
    parts = [
        f'<svg width="{X(w) + 250:.0f}" height="{Y(0) + 50:.0f}" '
        f'viewBox="0 0 {X(w) + 250:.0f} {Y(0) + 50:.0f}">',
        # beam body
        f'<rect x="{X(0):.1f}" y="{Y(3.4):.1f}" width="{w * xs:.1f}" '
        f'height="{(3.4) * zs:.1f}" fill="{white}" stroke="#cfc9c0" stroke-width="1"/>',
        # inlay
        f'<rect x="{X(4):.1f}" y="{Y(3.6):.1f}" width="{52 * xs:.1f}" '
        f'height="{0.2 * zs:.1f}" fill="{black}"/>',
        # top layer, engraved through
        f'<rect x="{X(0):.1f}" y="{Y(4.0):.1f}" width="{w * xs:.1f}" '
        f'height="{0.4 * zs:.1f}" fill="{white}" stroke="#cfc9c0" stroke-width="1"/>',
    ]
    for gx in (14.0, 30.0, 46.0):
        parts.append(f'<rect x="{X(gx):.1f}" y="{Y(4.0):.1f}" width="{STROKE * xs:.1f}" '
                     f'height="{0.4 * zs:.1f}" fill="{bg}"/>')
    parts += [
        f'<text x="{X(w) + 8:.0f}" y="{Y(4.2):.0f}" font-size="13" fill="#444">'
        f'white 0.40, engraved through</text>',
        f'<text x="{X(w) + 8:.0f}" y="{Y(3.5) + 4:.0f}" font-size="13" fill="#444">'
        f'black inlay 0.20</text>',
        f'<text x="{X(w) + 8:.0f}" y="{Y(2.0):.0f}" font-size="13" fill="#444">'
        f'white beam</text>',
        f'<text x="{X(14) - 2:.0f}" y="{Y(0) + 18:.0f}" font-size="12" fill="#666">'
        f'grooves {STROKE:.2f} wide &times; 0.40 deep</text>',
        "</svg>",
    ]
    return "".join(parts)


def main():
    sections = [
        ("whole beam", 0.0, caliper.BEAM_L, 5.0),
        ("0-45 mm, 4x", 0.0, 45.0, 18.0),
    ]
    parts = [
        "<!doctype html><meta charset=utf-8><title>beam preview</title>",
        "<style>body{font:13px -apple-system,Helvetica,sans-serif;margin:24px;"
        "background:#faf9f7;color:#111}h1{font-size:17px;margin:0 0 4px}"
        ".sub{color:#666;margin:0 0 18px}section{background:#fff;border:1px solid "
        "#e2ded8;border-radius:8px;padding:12px 14px;margin-bottom:14px}"
        "h2{font-size:13px;margin:0 0 8px}svg{display:block;background:#fff}"
        ".n{color:#666;font-size:12px;margin:8px 0 0}</style>",
        "<h1>Caliper beam - engraved scale</h1>",
        f'<p class="sub">cap {caliper.NUM_SIZE} mm &middot; channel {STROKE:.2f} mm wide '
        f'&times; {caliper.ENGRAVE:.2f} mm deep &middot; graduation dots '
        f'{2 * TICK_R:.1f} mm &oslash; &middot; inlay {caliper.SCALE_BAR_T:.2f} mm, '
        f'{BAR[1] - BAR[0]:.1f} &times; {BAR[3] - BAR[2]:.1f} mm</p>',
    ]
    for name, x0, x1, px in sections:
        parts.append(f"<section><h2>{name}</h2>{section(x0, x1, px)}</section>")
    parts.append("<section><h2>layer stack (z to scale, x schematic)</h2>"
                 f"{stack_svg()}</section>")
    parts.append(
        '<p class="n">Drawn from caliper.SCALE_TICKS and vecfont.layout(), so the '
        'positions and the chamfer widths match the STL cut.</p>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"cap {caliper.NUM_SIZE} mm, channel {STROKE:.3f} mm, depth {caliper.ENGRAVE} mm")
    print(f"beam {caliper.BEAM_L:.1f} x {caliper.BEAM_H} mm, "
          f"{sum(1 for t in caliper.SCALE_TICKS if t['kind'] == 'major')} majors")


if __name__ == "__main__":
    main()
