"""A single-stroke font for engraved text, after Alte DIN 1451.

Engraved lettering wants a uniform, printable channel rather than a filled
outline, so the glyphs are polylines that get stroked to a constant width.
The data in `stroke_din.json` is derived from Alte DIN 1451 Mittelschrift
(see `cad/tools/derive_stroke.py` and `cad/fonts/NOTICE.md`); it carries the
characters the models engrave - digits and their punctuation - on a
1000-unit cap height with a per-character advance.

Regenerate with `python cad/tools/derive_stroke.py`.
"""

from __future__ import annotations

import json
from math import atan2, degrees, hypot
from pathlib import Path

from build123d import Pos, Rectangle, Rot, Sketch

_DATA = json.loads(
    Path(__file__).with_name("stroke_din.json").read_text(encoding="utf-8")
)

CAP = float(_DATA["cap"])                       # data units per cap height
GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    ch: g["strokes"] for ch, g in _DATA["glyphs"].items()
}
ADVANCES: dict[str, float] = {ch: g["adv"] for ch, g in _DATA["glyphs"].items()}
KERN: dict[str, dict[str, float]] = _DATA.get("kern", {})
FALLBACK = "?"


def _glyph(ch: str):
    """The strokes for `ch`, or None if the data has no such glyph."""
    g = GLYPHS.get(ch)
    if g is None:
        g = GLYPHS.get(ch.upper())
    return g


def _kern(ch: str, side: str) -> float:
    """Space adjustment for one side of `ch`, in data units."""
    return KERN.get(ch, {}).get(side, 0.0)


def _advance(ch: str) -> float:
    if ch in ADVANCES:
        return ADVANCES[ch]
    if ch.upper() in ADVANCES:
        return ADVANCES[ch.upper()]
    return ADVANCES.get(FALLBACK, 0.6 * CAP)


def _stroke(p, q, w):
    """One segment as a rectangle, over-long by `w` so joints close up."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = hypot(dx, dy)
    return (Pos((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            * Rot(0, 0, degrees(atan2(dy, dx)) if length else 0.0)
            * Rectangle(length + w, w))


GAP = 150.0       # data units of clear space between the ink of two glyphs
MIN_GAP_MM = 0.43  # ...but never closer than this, whatever the cap height


def extent(glyph, unit, w):
    """Drawn x-extent of one glyph, in mm, at `unit` mm per data unit.

    Each segment is a rectangle `w` wide and `w` longer than the segment, so a
    slanted stroke reaches further than `w/2` past its ends.  Measuring that
    here (instead of using a nominal bearing) is what keeps the gaps equal for
    letters with diagonals such as 4 and 7.
    """
    x0 = x1 = None
    for poly in glyph:
        if len(poly) == 1:
            x = poly[0][0] * unit
            lo, hi = x - w / 2.0, x + w / 2.0
            x0 = lo if x0 is None else min(x0, lo)
            x1 = hi if x1 is None else max(x1, hi)
            continue
        for (ax, ay), (bx, by) in zip(poly, poly[1:]):
            dx, dy = bx - ax, by - ay
            length = hypot(dx, dy)
            slant = (abs(dx) + abs(dy)) / length if length else 1.0
            lo = min(ax, bx) * unit - w / 2.0 * slant
            hi = max(ax, bx) * unit + w / 2.0 * slant
            x0 = lo if x0 is None else min(x0, lo)
            x1 = hi if x1 is None else max(x1, hi)
    return x0, x1


def width(txt: str, size: float, stroke=None) -> float:
    """Width of the drawn `txt` at cap height `size`, in mm.

    Ink edge to ink edge: the glyphs plus one `GAP` between each pair, which is
    what the models need for label clearance.
    """
    w = stroke if stroke is not None else max(0.40, 0.14 * size)
    unit = size / CAP
    total = 0.0
    inked = 0
    for ch in txt:
        glyph = _glyph(ch)
        if not glyph:
            total += _advance(ch) * unit
            continue
        x0, x1 = extent(glyph, unit, w)
        total += x1 - x0
        inked += 1
    return total + max(inked - 1, 0) * GAP * unit


def layout(txt, size, stroke=None):
    """Place `txt` and return ([(glyph, dx_mm), ...], ink_width_mm).

    Glyphs are spaced ink-edge to ink-edge: a fixed GAP plus any kerning for
    the character about to be placed.  `dx` is the offset that puts that
    glyph's ink where the pen is.
    """
    unit = size / CAP
    w = stroke if stroke is not None else max(0.40, 0.14 * size)
    pen = 0.0
    placed = []
    left = right = None
    prev = None
    for ch in txt:
        glyph = _glyph(ch) or GLYPHS.get(FALLBACK)
        if not glyph:
            pen += _advance(ch) * unit
            prev = None                     # a space breaks the pair
            continue
        if prev is not None:
            gap = (GAP + _kern(prev, "after") + _kern(ch, "before")) * unit
            pen += max(MIN_GAP_MM, gap)
        x0, x1 = extent(glyph, unit, w)
        placed.append((glyph, pen - x0))
        if left is None:
            left = pen
        right = pen + (x1 - x0)
        pen += x1 - x0                   # the gap is added before the next glyph
        prev = ch
    return placed, (0.0 if left is None else right - left)


def width(txt: str, size: float, stroke=None) -> float:
    """Width of the drawn `txt` at cap height `size`, in mm (ink edge to ink
    edge, with the gaps and kerning already applied)."""
    return layout(txt, size, stroke)[1]


def text(txt, size, stroke=None, center=True):
    """Stroked text as a sketch. `size` is the cap height in mm; the result is
    centred on the origin unless `center` is False (then its ink starts at
    x=0, baseline y=0)."""
    unit = size / CAP
    w = stroke if stroke is not None else max(0.40, 0.14 * size)
    placed, total = layout(txt, size, w)

    faces = None
    for glyph, dx in placed:
        for poly in glyph:
            pts = [(dx + x * unit, y * unit) for x, y in poly]
            if len(pts) == 1:
                pts = pts + pts
            for a, b in zip(pts, pts[1:]):
                f = _stroke(a, b, w)
                faces = f if faces is None else faces + f

    if faces is None:
        return Sketch()
    if not center:
        return faces
    return Pos(-total / 2, -size / 2) * faces
