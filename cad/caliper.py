"""
Parametric 3D-printable dial caliper (build123d).

Layout (global coordinates, millimetres)
    X  along the beam, 0 = left end of the beam
    Y  across the beam, 0 = bottom edge of the beam
    Z  beam thickness, 0 = back face

The beam is a single slab with a slot along X through it, closed near both
ends: the rack sits on the slot floor across the full thickness (rack width =
beam thickness) with teeth pointing up (+Y), and the main scale is engraved on
its face (z = BEAM_T) hanging from the top edge - rack and scale on opposite
sides of the beam.  The slot opens just past the pinion's tip circle at
reading 0 (PIN_X down the beam), so the first stretch of beam is closed like
the tail past the last tooth.

The pinion axis sits in the beam's y-centre; its journal and shaft run in the
manual slider / front plate, and the shaft reaches forward into the dial
housing.  +X travel rolls the pinion clockwise.  The rack teeth are phased so
the pinion is at rotation 0 at reading 0 (a tooth centred under the axis
there), which lines the needle's hex drive up with the dial's 0.

    reading  M = (slider left face) * UNITS_PER_MM, in units
    outside  = M
    one turn of the needle = UNITS_PER_REV

Run:  python cad/caliper.py            -> cad/out/caliper.3mf + caliper.step
"""

import os
from math import ceil, floor, pi, degrees, radians, tan
from pathlib import Path

from build123d import *

from gears import (herringbone_pinion, herringbone_rack, pinion_profile,
                   rack_teeth)
from scale import compute_ticks, nice_round
from vecfont import text as vtext

# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
# --- what the caliper reads in -------------------------------------------
# Calibrated exactly like the web app in this repo: UNITS counted over PER_MM
# millimetres.  UNITS = PER_MM = 1 is a plain millimetre caliper; UNITS = 150,
# PER_MM = 10 reads in the 15-per-mm units of whatever you calibrated against.
# MAX_UNITS is where the scale ends, and the beam is sized from it.
UNITS = 1              # units counted...
PER_MM = 1.0           # ...over this many millimetres
UNIT_NAME = "mm"       # unit label (the paper dial uses it, the 3D parts don't)
MAX_UNITS = 100        # scale ends here

UNITS_PER_MM = UNITS / PER_MM
RANGE = MAX_UNITS / UNITS_PER_MM       # physical measuring range, mm

# --- transmission --------------------------------------------------------
# One needle revolution is a round number of units.  Tooth size follows from
# it: the pitch circumference IS one revolution of travel, so more units (and
# so more millimetres) per turn means bigger teeth and a coarser dial.
# UNITS_PER_REV is snapped to a nice 1/2/5 value near TARGET_MM_PER_REV, and
# the tooth count is picked to land the module near MODULE_TARGET; set either
# explicitly to override.
TARGET_MM_PER_REV = 20.0   # aim for this much travel per turn
MODULE_TARGET = 0.64       # ~2 mm rack pitch: five extrusion widths per flank
UNITS_PER_REV = None       # or a number, in units
PINION_TEETH = None        # or a tooth count

PRESSURE_ANGLE = 20.0
PROFILE_SHIFT = 0.45   # avoids undercut on the low tooth count
BACKLASH = 0.15        # nominal, generous for printing
HELIX = 30.0           # herringbone helix angle at the pitch line
RACK_DEDENDUM = 1.9    # deep roots and
CUTTER_ADDENDUM = 1.85 # deep pinion roots, so the mesh has somewhere to go
HELIX_SHAVE = 0.02     # clearance for the ruled-surface approximation, folded
                       # into the cutter rather than offset afterwards: an
                       # offset rounds every corner into its own arc, and those
                       # extra edges cost more than the rest of the pinion
PROFILE_SIMPLIFY = 0.01  # decimation of the generated tooth outline, mm

# --- beam -----------------------------------------------------------------
BEAM_T = 4.0           # full beam thickness (z)
RACK_T = 2.0           # rack strip thickness (z 0..RACK_T, back face side)
BEAM_H = 18.0          # beam height (y)
# The beam carries a z-layered slot along X; the 2 mm rack strip sits on the
# slot floor (back face side) with teeth pointing up (+Y).  PIN_Y, RACK_REF
# and the slot walls are derived below so the pinion axis lands in the
# beam's y-centre.

# --- manual slider interface ----------------------------------------------
# The slider, its pinion journal and the rest of the mechanism are modelled
# manually (fixed across calibrations).  Only the dimensions the generated
# geometry bears on are kept here: SLIDER_L sizes the beam, PLATE_T sets the
# front plate thickness (pinion shaft reach + dial stack), PIN_X locates the
# pinion axis from the slider datum.
SLIDER_L = 56.0
PLATE_T = 4.0
# The manual slider's top face (the reading datum) is 40 mm from the pinion
# axis, so at reading 0 the axis sits 40 mm down the beam.  40 mm is two
# needle turns at the default 20 mm/turn, which puts the pinion at rotation 0
# there: the rack teeth are phased to that (a tooth centred at PIN_X), so the
# needle can be pressed onto the hex drive pointing at the dial's 0.
PIN_X = 40.0

# --- slot -----------------------------------------------------------------
# The slot frees the pinion's sweep above the rack, leaving a top rail and a
# bottom rail.  The rack sits on the slot floor (bottom rail top face) with
# its roots buried RACK_EMBED deep: no slit behind the roots, only the tip
# side (front) is slotted for the pinion sweep.  Above the rack tips a plain
# 0.2 floor extension (same z strip, no teeth) steadies the pinion, then a
# 0.8 top plate spans the slot with only a shaft-wide slit (shaft + 0.1
# clearance per side in y, plus the slider's preload travel).
# SLOT_MARGIN keeps 1.0 of rail past the slot; SLOT_BOT (the rail top)
# is derived below, once MODULE / PINION_TEETH are known.
SLOT_MARGIN = 1.0
SHAFT_SLOT_CLR = 0.1   # y clearance per side round the shaft in the top plate
SHAFT_SLOT_PLAY = 0.35 # extra y room each side for the slider's pinion
                       # preload/travel, so the shaft never rubs the slit walls
TOP_PLATE_T = 0.8      # top plate thickness (z BEAM_T-TOP_PLATE_T..BEAM_T)
PLAIN_EXT = 0.2        # plain floor extension above the rack tips (in y)
RACK_EMBED = 0.3         # tooth roots stay buried this deep in the bottom rail

# --- dial / manual front plate interface ----------------------------------
# The dial face is paper: it is drawn by the web app at 1:1.  Only the recess
# the paper disc sits in is modelled here.  The rest of the slider/dial
# hardware is static and lives in caliper_static.3mf, not in this module.
DIAL_R = 22.0          # dial recess radius (paper disc sits in it)
DIAL_T = 2.6           # dial recess depth
SHAFT_D = 3.0          # pinion shaft diameter
ENGRAVE = 0.40         # depth of the beam graduations
NUM_SIZE = 2.8         # beam numerals, cap height
SCALE_BAR_T = 0.20     # thickness of the second-colour inlay, inside the beam
SCALE_BAR_MARGIN = 1.0 # white border kept around the engraved marks

# Any parameter above can be overridden from the environment without editing
# this file, e.g.
#   CALIPER_UNITS=150 CALIPER_PER_MM=10 CALIPER_MAX_UNITS=1500 \
#   CALIPER_UNIT_NAME=u python caliper.py
for _k, _v in os.environ.items():
    if not _k.startswith("CALIPER_") or _k[8:] not in globals():
        continue
    _cur = globals()[_k[8:]]
    if isinstance(_cur, str):
        globals()[_k[8:]] = _v
    elif isinstance(_cur, int) and not isinstance(_cur, bool):
        globals()[_k[8:]] = int(_v)
    elif isinstance(_cur, float):
        globals()[_k[8:]] = float(_v)
    else:                                   # the None-by-default overrides
        globals()[_k[8:]] = int(_v) if _v.isdigit() else float(_v)
UNITS_PER_MM = UNITS / PER_MM
RANGE = MAX_UNITS / UNITS_PER_MM

# --- derived transmission -------------------------------------------------
if UNITS_PER_REV is None:
    UNITS_PER_REV = nice_round(TARGET_MM_PER_REV * UNITS_PER_MM)
MM_PER_REV = UNITS_PER_REV / UNITS_PER_MM
if PINION_TEETH is None:
    # more teeth run smoother, so break ties upwards
    PINION_TEETH = min(range(8, 17),
                       key=lambda z: (abs(MM_PER_REV / (pi * z) - MODULE_TARGET),
                                      -z))
MODULE = MM_PER_REV / (pi * PINION_TEETH)

# --- derived --------------------------------------------------------------
RP = MODULE * PINION_TEETH / 2
PIN_Y = BEAM_H / 2                       # pinion axis in the beam's y-centre
# rack sits on the slot floor, teeth pointing up (+Y): RACK_REF is the
# reference line, roots at RACK_REF - hf, tips at RACK_REF + ha.  The mesh
# depth is set by the GENERATOR: pinion_profile cuts the blank with the rack
# cutter rolling at distance t, cutter reference line at y = -(rp + shift*m)
# in pinion frame - so the rack reference line sits exactly there in mesh.
# (BACKLASH and the deep roots leave the manual slider's preload somewhere to
# go.)
# RACK_X0/X1 are fixed up below, once BEAM_L is known: they span the pinion's
# whole travel plus half a pitch each end, so the pinion never runs off.
RACK_REF = None          # fixed below, once the rack dedendum is known
GEAR_Z0 = 0.0                          # pinion gear: z 0..RACK_T, same strip
GEAR_H = RACK_T                        # gear spans the 2 mm rack strip only
HELIX_DX = (GEAR_H / 2) * tan(radians(HELIX))        # chevron offset per half
HELIX_TWIST = degrees(HELIX_DX / RP)
SCALE_TOP = BEAM_H - 0.6               # scale hangs from the top edge,
                                       # opposite side from the rack
SCALE_STEPS, SCALE_TICKS = compute_ticks(MAX_UNITS, UNITS_PER_MM)

BEAM_L = RANGE + SLIDER_L + 8.0
RACK_X0 = None    # fixed below: the rack starts where the slot opens
RACK_X1 = None    # fixed below, once RA is known (must clear the disc + rail)
Z_PLATE = BEAM_T + 0.4                               # front plate back face
Z_FRONT = Z_PLATE + PLATE_T                          # front plate front face
Z_DIAL = Z_FRONT - 1.0                               # dial recess floor
# slot (y-width): only the pinion tip circle sweeps it.  Top rail keeps
# SLOT_MARGIN past the tip circle; the bottom rail top face is the slot floor
# the rack sits on: reference line below it by the rack roots
# (RACK_DEDENDUM*MODULE) minus the RACK_EMBED the roots stay buried.  The rack
# roots go deep (1.9 module) to leave the mesh some room.
RA = RP + MODULE * (1 + PROFILE_SHIFT)               # pinion tip radius
# generator-mesh depth (see above): exact conjugate position
RACK_REF = PIN_Y - RP - PROFILE_SHIFT * MODULE
SLOT_TOP = PIN_Y + RA + SLOT_MARGIN
SLOT_BOT = RACK_REF - RACK_DEDENDUM * MODULE + RACK_EMBED
# The pinion axis sits PIN_X down the beam at reading 0, so its tip circle is
# the leftmost thing that ever enters the slot: the beam stays closed from the
# 0 end up to there, just like it stays closed past the last tooth.  The rack
# starts with the slot, a couple of teeth before the axis.
SLOT_X0 = PIN_X - RA - 0.5
RACK_X0 = SLOT_X0
# rack span clears the pinion disc edge at MAX (plus chevron + margin), and
# leaves room for the 2 mm plain side rail past it
RACK_X1 = RANGE + PIN_X + RA + HELIX_DX + 1.0 + 2.0

def rect(x0, x1, y0, y1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2) * Rectangle(x1 - x0, y1 - y0)


def text_sk(txt, size, pos, angle=0.0):
    """Centred stroked text - see vecfont for why this is not build123d's
    Text(): there is no font to rely on in a browser."""
    return Pos(*pos) * Rot(0, 0, angle) * vtext(txt, size)


# --------------------------------------------------------------------------
# beam
# --------------------------------------------------------------------------
# FreeCAD beam-profile slice, repeated along the beam.  It is modelled in the
# FreeCAD beam frame (y centred, z -4..0); the pattern below moves it into
# this model's frame (y 0..BEAM_H, z 0..BEAM_T).
BEAM_SLICE = Path(__file__).with_name("beam.step")
TOP_BAR = Path(__file__).with_name("top_bar.step")
_BEAM_PATTERN = []
_TOP_BAR = []


def _top_bar():
    """The FreeCAD end bar, placed at the beam's 0 end.

    The right end sits 3 mm into the beam.  Its top is aligned with the
    18 mm beam core and its front with the beam's front face.
    """
    if _TOP_BAR:
        return _TOP_BAR[0]
    bar = import_step(str(TOP_BAR))
    bb = bar.bounding_box()
    placed = Pos(-bb.max.X + 3.0,
                 BEAM_H - bb.max.Y,
                 BEAM_T - bb.max.Z) * bar
    _TOP_BAR.append(placed)
    return placed


def _beam_slice_pattern():
    """Tile the beam-profile slice along X.

    The slice spans exactly 5 pi of a profile whose period is pi, with
    matching end sections, so 5 pi is also the seamless tile pitch.  It is
    shifted +pi/4 in X to put its left edge at x=0.  The pattern is extended
    left to the 0-end bar's outer end so the rail finishes flush with it, and
    clipped to the beam length on the right.  `glue` joins coincident ends.
    """
    if _BEAM_PATTERN:
        return _BEAM_PATTERN[0]
    x_min = min(0.0, _top_bar().bounding_box().min.X)
    tile = import_step(str(BEAM_SLICE))
    pitch = 5 * pi
    k0 = floor(x_min / pitch)
    k_end = max(1, ceil(BEAM_L / pitch))
    pattern = None
    for k in range(k0, k_end):
        part = Pos(k * pitch + pi / 4, BEAM_H / 2, BEAM_T) * tile
        pattern = part if pattern is None else pattern.fuse(part, glue=True)
    pattern = pattern & Pos((x_min + BEAM_L) / 2, 0, 0) * Box(
        BEAM_L - x_min, 200, 200)
    _BEAM_PATTERN.append(pattern)
    return pattern


TICK_R = 0.6                            # major graduation circle radius
TICK_Y = SCALE_TOP - 1.2                 # centre of the graduation dots
LABEL_Y = SCALE_TOP - 4.2                # centre of the numerals
_SCALE_MARKS = []


def _scale_marks():
    """The engraved dots and numerals, as one 2D sketch in the beam frame."""
    if _SCALE_MARKS:
        return _SCALE_MARKS[0]
    cuts = None
    for t in SCALE_TICKS:
        if t["kind"] != "major":
            continue
        c = Pos(t["mm"], TICK_Y) * Circle(TICK_R)
        cuts = c if cuts is None else cuts + c
    for t in SCALE_TICKS:
        # label every major graduation centred on its dot, including the 0
        if t["label"] or t["kind"] == "major":
            cuts += text_sk(str(t["value"]), NUM_SIZE, (t["mm"], LABEL_Y))
    _SCALE_MARKS.append(cuts)
    return cuts


def scale_bar_rect():
    """x0, x1, y0, y1 of the inlay: the marks plus a margin.

    The pocket is cut after the FreeCAD end bar is unioned, so the strip runs
    past the 0 end as well - the 0 glyph itself straddles x = 0, and the end
    bar is what carries its left half.
    """
    bb = _scale_marks().bounding_box()
    # the top plate's shaft slit runs the length of the scale at
    # PIN_Y +- (shaft + clearance): keep a printable wall below the strip so
    # the inlay never reaches into it
    slit_top = PIN_Y + SHAFT_SLOT_PLAY + SHAFT_D / 2 + SHAFT_SLOT_CLR
    return (bb.min.X - SCALE_BAR_MARGIN,
            bb.max.X + SCALE_BAR_MARGIN,
            max(slit_top + 0.3, bb.min.Y - SCALE_BAR_MARGIN),
            min(SCALE_TOP, bb.max.Y + SCALE_BAR_MARGIN))


def scale_bar():
    """The second-colour slab: it fills the pocket cut in `beam()`, with its
    top face at the engraving floor, so every groove bottoms out on it."""
    x0, x1, y0, y1 = scale_bar_rect()
    z0 = BEAM_T - ENGRAVE - SCALE_BAR_T
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, SCALE_BAR_T,
                                align=(Align.MIN, Align.MIN, Align.MIN))


def beam():
    b = extrude(rect(0, BEAM_L, 0, BEAM_H), BEAM_T)

    # add the repeated FreeCAD profile and the 0-end bar before the
    # scale/slot/rack cuts, so those features are cut into the new surface
    # instead of being filled
    b += _beam_slice_pattern()
    b += _top_bar()

    # the scale strip is printed in a second colour: cut the inlay's pocket,
    # then engrave the marks 0.4 deep so their floors are the inlay's top face
    # NOTE: the scale cuts go FIRST, before the slot+rack: cutting them into
    # the rack-fused beam fragments it into ~10 solids (OCC boolean-order
    # sensitivity), while slot+rack after stays one solid.
    b -= scale_bar()
    b -= Pos(0, 0, BEAM_T - ENGRAVE) * extrude(_scale_marks(), ENGRAVE + 0.1)

    # z-layered slot along X, on the tip (front) side of the rack only:
    #   z 0..RACK_T:            full-width sweep (tip circle + margin)
    #   z RACK_T..RACK_T+0.2:   plain floor extension (no teeth) steadying the
    #                           pinion, same full-width sweep
    #   z 2.2..BEAM_T:          shaft slit only: it clears the shaft over the
    #                           slider's preload travel (+0.1 per side in y).
    #                           The 0.8 top plate (z 3.2..4.0) is the top of
    #                           this layer.
    # The rack strip (z 0..RACK_T, back side) keeps its roots buried RACK_EMBED
    # in the bottom rail: no slit behind them.  The rack span stops 1 mm past
    # the end teeth; the slot opens at SLOT_X0, just left of the pinion's tip
    # circle at reading 0, so the beam stays closed from the 0 end up to there
    # (like the tail past the last tooth).
    z_rack_top = RACK_T
    z_plain_top = RACK_T + PLAIN_EXT
    b -= Pos(0, 0, 0) * extrude(rect(SLOT_X0, RACK_X1 + 1, SLOT_BOT, SLOT_TOP),
                                z_rack_top)
    b -= Pos(0, 0, z_rack_top) * extrude(rect(SLOT_X0, RACK_X1 + 1, SLOT_BOT, SLOT_TOP),
                                         PLAIN_EXT)
    b -= Pos(0, 0, z_plain_top) * extrude(
        rect(SLOT_X0, RACK_X1 + 1,
             PIN_Y - SHAFT_SLOT_PLAY - SHAFT_D / 2 - SHAFT_SLOT_CLR,
             PIN_Y + SHAFT_SLOT_PLAY + SHAFT_D / 2 + SHAFT_SLOT_CLR),
        BEAM_T - z_plain_top)

    # rack strip on the back face (z 0..RACK_T), teeth pointing up (+Y):
    # face width is RACK_T, not the full slab.  Roots sit buried RACK_EMBED
    # in the floor, tips rise into the slot; no slit behind the roots, only
    # the tip side (front) is slotted for the pinion sweep.
    # The rack span stops 1 mm past the end teeth (no HELIX_DX margin: the
    # chevron overhang past the end teeth would detach as chips).
    # Rack teeth exactly span the slot, so no chevron overhang can detach
    # as chips at either end.
    # The teeth are generated in a frame shifted by PIN_X, so a tooth is
    # centred under the pinion axis at reading 0: that is what makes the
    # pinion sit at rotation 0 there (the needle's hex drive zero).
    teeth, hf, ha = rack_teeth(MODULE, RACK_X0 - 1 - PIN_X,
                               RACK_X1 + 1 - PIN_X, PRESSURE_ANGLE,
                               backlash=0.0, dedendum=RACK_DEDENDUM)
    # NOTE: rack_teeth draws the profile about y=0 (reference line), so the
    # sketch y-span is -hf..ha; it is placed at RACK_REF when swept.  The
    # teeth come out disjoint and a single n-way union will NOT join them
    # (OCC keeps ~half the faces): accumulate them into the root bar one at
    # a time, starting from the bar, which does fuse to one face.  Bar top
    # sits RACK_EMBED above the roots, so the teeth stay buried that deep in
    # the bottom rail.  herringbone_rack needs a single Face: the union above
    # is one face but typed as a Sketch, which the sweep reads back as
    # disjoint teeth - hence .faces()[0].  The bar starts at RACK_X0-1, where
    # the slot opens, so its left end is buried in the closed beam.
    bar = rect(RACK_X0 - 1 - PIN_X, RACK_X1 + 1 - PIN_X, -hf, -hf + RACK_EMBED)
    teeth_joined = bar
    for f in teeth.faces():
        teeth_joined = teeth_joined + f
    teeth = teeth_joined.faces()[0]
    # the top chevron half runs PLAIN_EXT tall (fills the 0.2 gap up to the
    # shaft-slit layer for printability); the bottom half stays RACK_T/2, so
    # the mesh side is unchanged.  The extra height also shifts +x by
    # HELIX_DX * PLAIN_EXT / (RACK_T/2) - covered by the 1.0 end margin.
    rack = Pos(PIN_X, RACK_REF, 0) * herringbone_rack(teeth, 0, RACK_T,
                                                     HELIX_DX,
                                                     top_extra=PLAIN_EXT)
    # clip to the strip: roots buried (SLOT_BOT - RACK_EMBED), tips to
    # RACK_REF + ha (full tip height into the slot); x from RACK_X0-1, where
    # the slot opens, so the left end is buried in the closed beam
    rack = rack & Pos(PIN_X, 0, 0) * extrude(rect(RACK_X0 - 1 - PIN_X,
                                                  RACK_X1 + 1 - PIN_X,
                                                  SLOT_BOT - RACK_EMBED,
                                                  RACK_REF + ha),
                                             RACK_T + PLAIN_EXT)
    b += rack

    return b


# --------------------------------------------------------------------------
# pinion
# (the paper dial face is drawn by the web app; the static hardware is in
# caliper_static.3mf - neither is built here)
# --------------------------------------------------------------------------
_PINION = {}

# The pinion axis - shaft, hex drive and journal - and the socket cut out of
# its bottom are static models drawn in FreeCAD and exported to STEP (exact
# B-reps, not meshes).  The axis is fused into the generated gear and the
# cut-out subtracted, so the printed part, its STL and the assembly all carry
# them.  The browser worker fetches both files and writes them to these same
# paths inside the Pyodide filesystem, so the CLI and the page agree.
PINION_AXIS = Path(__file__).with_name("pinion_axis.step")
PINION_CUT_OUT = Path(__file__).with_name("pinion_cut_out.step")


def pinion(gear_dz=0.0):
    """Gear + FreeCAD axis, as one solid.

    `gear_dz` moves only the gear, after it is generated and before the axis
    is fused; the normal part uses the default (the rack strip at z 0..2).
    Demos/print variants can drop the gear to the axis bottom, but that is
    not an assembled-caliper position: the beam/rack, slider and dial are all
    built around the gear at z 0..2.
    """
    if gear_dz in _PINION:           # the helical lofts are slow; build once
        return _PINION[gear_dz]
    # the helical halves are ruled surfaces between their end sections, so the
    # flank bulges a little off the true helicoid; HELIX_SHAVE thins the tooth
    # by that much, applied through the cutter so the outline stays polygonal
    prof = pinion_profile(MODULE, PINION_TEETH, PRESSURE_ANGLE, PROFILE_SHIFT,
                          BACKLASH + 2 * HELIX_SHAVE,
                          cutter_addendum=CUTTER_ADDENDUM,
                          simplify_tol=PROFILE_SIMPLIFY)
    # NOTE: the pinion rides ON TOP of the rack (contact at the bottom of the
    # pinion), so its chevron twists the standard way for a pinion riding on
    # top: the rotation that shifts the bottom contact +dx at the gear ends
    # is +twist.
    # The gear itself carries only the 45-degree cone pivot seat cut into its
    # back face (z=0).  The shaft (with its hex drive for the needle) and the
    # bottom journal are the FreeCAD axis, unioned in below.  Base diameter =
    # SHAFT_D, so the bearing size matches the old axle; the recess stays
    # inside the gear (well clear of the tooth roots) and prints without
    # support.
    cone_r = SHAFT_D / 2
    cone_h = cone_r                     # 45 deg half-angle: height = radius
    p = herringbone_pinion(prof, GEAR_Z0, GEAR_H, +HELIX_TWIST)
    p -= Pos(0, 0, cone_h / 2) * Cone(bottom_radius=cone_r, top_radius=0.0,
                                      height=cone_h)
    if gear_dz:                      # demo/print variants only; 0 for the
        p = Pos(0, 0, gear_dz) * p   # assembled caliper
    # exact B-rep fused on the same OpenCascade kernel; the axis is modelled
    # in this part's local frame (Z along the shaft, z=0 at the gear's back
    # face), so no placement is needed here
    p = (p + import_step(str(PINION_AXIS))).clean()
    # the FreeCAD cut-out is a conical socket in the bottom of the axis
    p = (p - import_step(str(PINION_CUT_OUT))).clean()
    _PINION[gear_dz] = p
    return p


# --------------------------------------------------------------------------
# assembly / export
# --------------------------------------------------------------------------
def pinion_angle(x_global):
    """Rotation that meshes the pinion with the rack at that beam position.

    The pinion rides on top of the rack (contact at the bottom of the
    pinion): +X travel turns the pinion clockwise.  The rack teeth are phased
    so a tooth is centred PIN_X down the beam, i.e. under the axis at reading
    0, where the generated profile has a tooth space at -90 deg - so the
    pinion is at rotation 0 exactly there and the needle's hex drive lines up
    with the dial's 0.
    """
    return -degrees((x_global - PIN_X) / RP)


def assembly(reading=None):
    """`reading` is in units, like the dial.

    Only the generated parts are placed: the front plate, dial and the rest of
    the slider are modelled manually.
    """
    reading = MAX_UNITS / 4 if reading is None else reading
    xs = reading / UNITS_PER_MM
    parts = [
        ("beam", beam(), Location()),
        ("pinion", pinion(),
         Pos(xs + PIN_X, PIN_Y, 0) * Rot(0, 0, pinion_angle(xs + PIN_X))),
        # no dial_face: the dial is paper now (drawn by the web app), so there is no
        # generated part at Z_DIAL to place in the assembly
    ]
    return parts


def pinion_for_print():
    """The pinion as printed: the gear joined at the bottom of the axis, so it
    sits flat on the bed - the same variant pinion_demo.py shows.  The
    assembled caliper keeps the gear in the rack strip (pinion())."""
    return pinion(gear_dz=pinion().bounding_box().min.Z)


PRINT_PARTS = {
    "beam": lambda: Rot(0, 180, 0) * beam(),          # front face on the bed
    "scale_insert": lambda: Rot(0, 180, 0) * scale_bar(),  # same frame as beam
    "pinion": pinion_for_print,                        # gear on the bed
}

if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    print(f"scale     {UNITS} {UNIT_NAME} per {PER_MM} mm "
          f"= {UNITS_PER_MM:g} {UNIT_NAME}/mm")
    print(f"range     0-{MAX_UNITS} {UNIT_NAME} = {RANGE:.2f} mm, "
          f"ticks every {SCALE_STEPS['minor_units']:g} {UNIT_NAME} "
          f"({SCALE_STEPS['minor_mm']:.2f} mm), numbered every "
          f"{SCALE_STEPS['major_units']:g}")
    print(f"dial      {UNITS_PER_REV:g} {UNIT_NAME}/turn "
          f"({MM_PER_REV:.3f} mm/turn)")
    print(f"gears     module {MODULE:.4f}, pitch {pi*MODULE:.3f} mm, "
          f"{PINION_TEETH} teeth, {MM_PER_REV:.3f} mm/turn")
    print(f"beam      {BEAM_L:.0f} mm,  pinion axis y = {PIN_Y:.3f}")
    if MODULE < 0.45:
        print(f"WARNING: module {MODULE:.3f} is small for FDM - raise "
              f"TARGET_MM_PER_REV or lower PINION_TEETH")
    if BEAM_L > 300:
        print(f"WARNING: beam is {BEAM_L:.0f} mm - check MAX_UNITS")
    import tempfile
    from threemf import write_caliper_3mf

    template = Path(__file__).with_name("caliper_static.3mf")
    with tempfile.TemporaryDirectory() as tmp:
        stls = {}
        for name, fn in PRINT_PARTS.items():
            part = fn()
            stl = os.path.join(tmp, f"{name}.stl")
            export_stl(part, stl, tolerance=0.01, angular_tolerance=0.1)
            print(f"  {name:<12} bbox {part.bounding_box().size}")
            stls[name] = stl
        # The template carries the static hardware (FacePlate, DialRing,
        # Slider*, ArrestLever, ConnectRing, ThumbPinion, SliderBar).  Add the
        # generated beam + black inlay as one compound and the pinion as a
        # separate object.
        write_caliper_3mf(out / "caliper.3mf", template,
                          stls["beam"], stls["scale_insert"], stls["pinion"],
                          f"dial caliper, {UNITS} {UNIT_NAME} per {PER_MM:g} mm")
    asm = Compound(children=[Compound(label=n, children=[loc * s])
                             for n, s, loc in assembly()])
    export_step(asm, str(out / "caliper.step"))
    print("wrote", out)
