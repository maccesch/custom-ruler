"""
3D-printable ruler (build123d).

Mirrors the web app's SVG scale at 1:1: the same `scale.compute_ticks` layout
as the SVG print and the caliper's beam, ticks hanging from one edge with
their minor/medium/major lengths and the major values engraved rotated along
the bar, in the same places the SVG puts them.  The ticks run right up to the
bar's edge and the blank margin sits past the numerals instead; by default the
bar also starts on the 0 tick's centre, so its left edge is the zero line
(`ZERO_MARGIN` keeps the SVG's padding there instead).  Past the last
graduation the bar carries a rounded hanging hole.

Layout (global coordinates, millimetres)
    X  along the bar, 0 = left edge, ZERO_X = first (zero) tick
    Y  across the bar, WIDTH = tick edge
    Z  bar thickness, 0 = back face, engraved face at THICK

Run:  python cad/ruler.py           -> cad/out/ruler.stl

Any parameter can be overridden from the environment, e.g.
    CALIPER_UNITS=150 CALIPER_PER_MM=10 CALIPER_MAX_UNITS=1500 \
    CALIPER_FONT_MM=2.5 python cad/ruler.py
"""

import os
from pathlib import Path

from build123d import *

from scale import compute_ticks
from vecfont import CAP, GLYPHS, extent as vextent, text as vtext, width as vwidth

# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
UNITS = 1              # units counted...
PER_MM = 1.0           # ...over this many millimetres
UNIT_NAME = "mm"       # kept for parity with caliper.py and the web app
MAX_UNITS = 150        # scale ends here
FONT_MM = 3.0          # label cap height, the web app's label size

THICK = 2.0            # bar thickness, the app's default
ZERO_MARGIN = False    # keep the SVG's padding before the 0 tick; off means
                       # the bar starts on the 0 tick's centre
ENGRAVE = 0.45         # depth of every engraved graduation
TICK_W = 0.5           # engraved tick groove width (SVG strokes are hairlines)
CORNER_R = 2.5         # plan-view corner radius
HOLE_D = 4.5           # hanging hole
END_WALL = 2.5         # material between the hole and the bar end
LABEL_GAP = 1.5        # material between the last label and the hole

# Layout, following the SVG's spacing along the bar (from ../src/app.rs).  The
# bar mirrors it across Y, so the tick edge is the bar's +Y edge.  Unlike the
# SVG the ticks run right up to that edge, and the blank margin sits past the
# numerals instead.
TICK_EDGE = 0.0        # tick roots, from the tick edge
LABEL_BASE_Y = 13.0    # label baseline, labels advance away from the ticks
NUMBER_MARGIN = 2.0    # between the longest label and the far edge
MIN_WIDTH = 18.0       # keep the bar comfortable to handle and print

for _k, _v in os.environ.items():
    if not _k.startswith("CALIPER_") or _k[8:] not in globals():
        continue
    _cur = globals()[_k[8:]]
    if isinstance(_cur, bool):
        globals()[_k[8:]] = _v.strip().lower() not in ("0", "false", "")
    elif isinstance(_cur, str):
        globals()[_k[8:]] = _v
    elif isinstance(_cur, int) and not isinstance(_cur, bool):
        globals()[_k[8:]] = int(_v)
    elif isinstance(_cur, float):
        globals()[_k[8:]] = float(_v)

# --------------------------------------------------------------------------
# derived
# --------------------------------------------------------------------------
UNITS_PER_MM = UNITS / PER_MM
RANGE = MAX_UNITS / UNITS_PER_MM

SCALE_STEPS, SCALE_TICKS = compute_ticks(MAX_UNITS, UNITS_PER_MM)

LENGTHS = {"minor": 5.0, "medium": 7.5, "major": 9.0}      # as in the SVG

PAD = max(0.75 * FONT_MM, 2.0)                             # the SVG's pad_mm
ZERO_X = PAD if ZERO_MARGIN else 0.0                       # bar x of the 0 tick
LABEL_LEN = max(vwidth(str(t["value"]), FONT_MM) for t in SCALE_TICKS)
WIDTH = max(MIN_WIDTH, LABEL_BASE_Y + LABEL_LEN + NUMBER_MARGIN)

TICK_TOP = WIDTH - TICK_EDGE
LABEL_BASE = WIDTH - LABEL_BASE_Y

HOLE_R = HOLE_D / 2
SCALE_END = ZERO_X + RANGE
HOLE_X = SCALE_END + max(PAD, FONT_MM + LABEL_GAP) + HOLE_R
LENGTH = HOLE_X + HOLE_R + END_WALL


def rect(x0, x1, y0, y1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2) * Rectangle(x1 - x0, y1 - y0)


# --------------------------------------------------------------------------
# the bar
# --------------------------------------------------------------------------
def ruler():
    prof = Rectangle(LENGTH, WIDTH, align=(Align.MIN, Align.MIN))
    prof = fillet(prof.vertices(), CORNER_R)
    prof -= Pos(HOLE_X, WIDTH / 2) * Circle(HOLE_R)
    bar = extrude(prof, THICK)

    # graduations: same positions, lengths and labels as the SVG
    cuts = None
    for t in SCALE_TICKS:
        x = ZERO_X + t["mm"]
        ln = LENGTHS[t["kind"]]
        r = rect(x - TICK_W / 2, x + TICK_W / 2, TICK_TOP - ln, TICK_TOP)
        cuts = r if cuts is None else cuts + r
    for t in SCALE_TICKS:
        if t["label"]:
            lbl = (Pos(ZERO_X + t["mm"], LABEL_BASE) * Rot(0, 0, -90)
                   * vtext(str(t["value"]), FONT_MM, center=False))
            cuts += lbl
    return bar - Pos(0, 0, THICK - ENGRAVE) * extrude(cuts, ENGRAVE + 0.1)


PRINT_PARTS = {
    "ruler": ruler,                                    # engraved face up
}

if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    print(f"scale     {UNITS} {UNIT_NAME} per {PER_MM:g} mm "
          f"= {UNITS_PER_MM:g} {UNIT_NAME}/mm")
    print(f"range     0-{MAX_UNITS} {UNIT_NAME} = {RANGE:.2f} mm")
    print(f"ticks     every {SCALE_STEPS['minor_units']:g} {UNIT_NAME} "
          f"({SCALE_STEPS['minor_mm']:.2f} mm), numbered every "
          f"{SCALE_STEPS['major_units']:g}")
    print(f"bar       {LENGTH:.1f} x {WIDTH:.1f} x {THICK:g} mm, "
          f"{CORNER_R:g} mm corners, {HOLE_D:g} mm hole, "
          f"zero {'padded' if ZERO_MARGIN else 'on the left edge'}")
    if LENGTH > 300:
        print(f"WARNING: bar is {LENGTH:.0f} mm - check the print bed")

    p = ruler()

    # one solid bar with the expected envelope
    assert len(p.solids()) == 1, f"{len(p.solids())} solids"
    bb = p.bounding_box().size
    assert abs(bb.X - LENGTH) < 1e-6, f"length {bb.X} != {LENGTH}"
    assert abs(bb.Y - WIDTH) < 1e-6, f"width {bb.Y} != {WIDTH}"
    assert abs(bb.Z - THICK) < 1e-6, f"thickness {bb.Z} != {THICK}"

    # the scale must sit inside the bar, and the hang hole past its end
    assert SCALE_TICKS[0]["mm"] == 0.0
    assert SCALE_TICKS[-1]["mm"] <= RANGE
    assert HOLE_X - HOLE_R > ZERO_X + SCALE_TICKS[-1]["mm"] + FONT_MM

    # the 0 tick sits on the bar's left edge unless a margin was asked for
    if ZERO_MARGIN:
        assert ZERO_X == PAD
    else:
        assert ZERO_X == 0.0, "0 tick must sit on the bar's edge"
    at_zero = p.intersect(Pos(ZERO_X + 0.1, TICK_TOP - LENGTHS["major"] / 2,
                              THICK - ENGRAVE / 2) * Box(
        0.1, 0.2, ENGRAVE / 2 + 1e-6,
        align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    zv = 0.0 if at_zero is None else sum(s.volume for s in at_zero.solids())
    assert zv < 1e-9, f"0 tick not engraved where the bar starts ({zv} mm^3)"

    # the ticks start at the bar's tick edge; the blank margin is on the
    # number side, past the numerals
    assert TICK_TOP == WIDTH, "ticks must start at the tick edge"
    assert WIDTH - (LABEL_BASE_Y + LABEL_LEN) >= 2.0, "no margin past the numerals"

    # material budget: engraved marks remove some, but nowhere near 10%
    solid = (LENGTH * WIDTH - (4 - 3.141592653589793) * CORNER_R**2
             - 3.141592653589793 * (HOLE_D / 2) ** 2) * THICK
    assert 0.0 < solid - p.volume < 0.10 * solid, f"engraving {solid - p.volume}"

    # the hang hole goes through the full thickness
    probe = Pos(HOLE_X, WIDTH / 2, -1.0) * Box(
        0.4, 0.4, THICK + 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    through = p.intersect(probe)
    v = 0.0 if through is None else sum(s.volume for s in through.solids())
    assert v < 1e-9, f"hang hole blocked ({v} mm^3)"

    # the corners are rounded: a probe at the bounding-box corner is void
    corner = p.intersect(Pos(LENGTH - 0.15, WIDTH - 0.15, -1.0) * Box(
        0.3, 0.3, THICK + 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    cv = 0.0 if corner is None else sum(s.volume for s in corner.solids())
    assert cv < 1e-9, f"corner not rounded ({cv} mm^3)"

    # a label stroke is engraved where the SVG puts it: the first labelled
    # tick's "1" is a bar at the right-hand stem, running away from the ticks
    # after Rot -90 about the anchor.  The probe is derived from the glyph data
    # so it moves with the font instead of being pinned to a magic offset.
    first = next(t for t in SCALE_TICKS if t["label"])
    stroke_w = max(0.40, 0.14 * FONT_MM)
    unit = FONT_MM / CAP
    ink_x0, _ = vextent(GLYPHS["1"], unit, stroke_w)
    stem_x = max(p[0] for s in GLYPHS["1"] for p in s) * unit - ink_x0
    lx = ZERO_X + first["mm"] + 1.5
    ly = LABEL_BASE - stem_x
    lbl = p.intersect(Pos(lx, ly, THICK - ENGRAVE / 2) * Box(
        0.2, 0.2, ENGRAVE / 2 + 1e-6,
        align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    lv = 0.0 if lbl is None else sum(s.volume for s in lbl.solids())
    assert lv < 1e-9, f"label not engraved at the SVG position ({lv} mm^3)"

    # a major tick is engraving - void at the top face, solid underneath
    tick = next(t for t in SCALE_TICKS if t["kind"] == "major")
    ty = TICK_TOP - LENGTHS["major"] / 2
    at = lambda z: Pos(ZERO_X + tick["mm"], ty, z) * Box(
        0.2, 0.2, ENGRAVE / 2 + 1e-6,
        align=(Align.CENTER, Align.CENTER, Align.CENTER))
    top = p.intersect(at(THICK - ENGRAVE / 2))
    tip = 0.0 if top is None else sum(s.volume for s in top.solids())
    assert tip < 1e-9, f"tick not engraved ({tip} mm^3)"
    under = p.intersect(at(ENGRAVE / 2))
    un = 0.0 if under is None else sum(s.volume for s in under.solids())
    assert un > 0.0, "tick cut through the bar"

    # and the groove reaches the tick edge itself
    edge = p.intersect(Pos(ZERO_X + tick["mm"], WIDTH - 0.1, THICK - ENGRAVE / 2) * Box(
        0.2, 0.2, ENGRAVE / 2 + 1e-6,
        align=(Align.CENTER, Align.CENTER, Align.CENTER)))
    ev = 0.0 if edge is None else sum(s.volume for s in edge.solids())
    assert ev < 1e-9, f"tick does not reach the tick edge ({ev} mm^3)"

    import tempfile
    from threemf import write_3mf

    with tempfile.TemporaryDirectory() as tmp:
        stl = os.path.join(tmp, "ruler.stl")
        export_stl(p, stl, tolerance=0.01, angular_tolerance=0.1)
        write_3mf(out / "ruler.3mf", [[("ruler", stl)]],
                  f"ruler, {UNITS} {UNIT_NAME} per {PER_MM:g} mm")
    print("ruler checks passed")
    print("wrote", out)
