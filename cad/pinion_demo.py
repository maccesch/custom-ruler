"""Demo export: the pinion with its gear dropped to the axis bottom.

The working caliper keeps the gear at z 0..2 (in the rack strip) with the
4 mm below it as the journal that rides in the slider's bore.  This demo
generates exactly the same gear and axis, then moves the gear down to the
bottom of the axis, and moves the beam/rack down by the same amount so the
mesh is unchanged.

It is a viewing/print demo, not the assembled caliper: there is no journal
left below the gear, and the slider, front plate and dial have not moved.

    python cad/pinion_demo.py
"""

from pathlib import Path

from build123d import Box, Compound, Pos, Rot, export_step, export_stl
from build123d.exporters import ExportSVG, LineType

import caliper as c

OUT = Path(__file__).resolve().parent / "out"
# measure the post-cut-out axis bottom: the socket leaves a rim at -3.9586,
# not the raw axis end at -4.0, and the gear should still land exactly on it
GEAR_DZ = c.pinion().bounding_box().min.Z


def draw(shape, name, origin, scale, up=(0, 0, 1)):
    visible, hidden = shape.project_to_viewport(origin, viewport_up=up)
    ex = ExportSVG(scale=scale, margin=8, line_weight=0.25)
    ex.add_layer("visible")
    ex.add_layer("hidden", line_type=LineType.ISO_DOT, line_weight=0.12)
    ex.add_shape(visible, layer="visible")
    ex.add_shape(hidden, layer="hidden")
    ex.write(str(name))
    print("wrote", name)


def main():
    OUT.mkdir(exist_ok=True)
    pin = c.pinion(gear_dz=GEAR_DZ)
    print(f"pinion   {len(pin.solids())} solid, {pin.volume:.3f} mm^3")
    print(f"bbox     {pin.bounding_box().min} -> {pin.bounding_box().max}")
    export_stl(pin, str(OUT / "pinion_demo.stl"),
               tolerance=0.01, angular_tolerance=0.1)
    export_step(pin, str(OUT / "pinion_demo.step"))
    draw(pin, OUT / "pinion_demo_iso.svg", (14, -22, 16), 14)
    draw(pin, OUT / "pinion_demo_side.svg", (0, -30, 0), 14)
    draw(pin, OUT / "pinion_demo_bottom.svg", (0, 0, -30), 14, up=(0, 1, 0))

    # the rack is part of the beam, so move the whole beam by the same amount.
    # Keep only the 2 mm rack strip and a short length around the pinion, so
    # the mesh is visible rather than buried in the beam.
    xs = c.RANGE / 4                 # same placement as caliper.assembly()
    placed = (Pos(xs + c.PIN_X, c.PIN_Y, 0)
              * Rot(0, 0, c.pinion_angle(xs + c.PIN_X)) * pin)
    strip = Pos(0, 0, GEAR_DZ) * c.beam() & (
        Pos(xs + c.PIN_X, c.PIN_Y, GEAR_DZ + c.RACK_T / 2)
        * Box(44, 26, c.RACK_T + 0.4))
    overlap = placed.intersect(strip)
    vol = sum(s.volume for s in overlap.solids()) if overlap else 0.0
    print(f"mesh     {vol:.6f} mm^3 overlap with the shifted rack")
    draw(Compound(children=[strip, placed]),
         OUT / "pinion_demo_mesh.svg", (26, -38, 30), 4)


if __name__ == "__main__":
    main()
