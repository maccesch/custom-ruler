"""Interference / clearance checks on the assembled caliper."""
from caliper import *

def inter(a, b):
    x = a.intersect(b)
    if x is None:
        return 0.0, None
    sols = x.solids() if hasattr(x, "solids") else list(x)
    sols = [s for s in sols]
    v = sum(s.volume for s in sols)
    if v < 1e-9:
        return 0.0, None
    bb = sols[0].bounding_box()
    for s in sols[1:]:
        bb = bb.add(s.bounding_box())
    return v, (tuple(round(c,2) for c in bb.min), tuple(round(c,2) for c in bb.max))

READINGS = [round(f * MAX_UNITS, 3) for f in (0, 0.037, 0.25, 0.633, 1.0)]
for reading in READINGS:
    parts = {n: loc * s for n, s, loc in assembly(reading)}
    print(f"--- reading {reading:8.2f} {UNIT_NAME}  "
          f"(slider face x = {reading / UNITS_PER_MM:.2f} mm)")
    for a, b in [("beam", "pinion")]:
        v, bb = inter(parts[a], parts[b])
        flag = "" if v < 1e-6 else f"   <-- {bb}"
        print(f"   {a:>12} x {b:<12} {v:9.4f} mm^3{flag}")

# every generated part must be one connected solid and must mesh to a
# sane STL: a twisted extrusion of a boolean-generated outline can silently
# explode into millions of triangles, so the file size is part of the contract.
# (the static hardware is in caliper_static.3mf; the paper dial is drawn by
# the web app.  Only the beam and pinion are generated here.)
print("--- printed parts")
import os
import tempfile
from caliper import PRINT_PARTS
from build123d import export_stl

STL_BUDGET_MB = 5.0
with tempfile.TemporaryDirectory() as tmp:
    built = {}
    for name, fn in PRINT_PARTS.items():
        part = built[name] = fn()
        n = len(part.solids())
        path = os.path.join(tmp, name + ".stl")
        export_stl(part, path, tolerance=0.01, angular_tolerance=0.1)
        mb = os.path.getsize(path) / 1e6
        tris = (os.path.getsize(path) - 84) // 50
        notes = []
        if n != 1:
            # the scale's closed counters (0, 4, 6, 8, 9) are separate pieces
            # of the white layer by design: they sit on the inserted strip
            notes.append("counters ride on the insert" if name == "beam"
                         else "DETACHED GEOMETRY")
        if mb > STL_BUDGET_MB:
            notes.append(f"STL OVER {STL_BUDGET_MB:g} MB")
        print(f"   {name:<12} {n} solid  {mb:6.2f} MB  {tris:7d} triangles"
              + ("   <-- " + ", ".join(notes) if notes else ""))

# the beam only becomes one solid with the strip in place - that assembly is
# what actually gets printed
print(f"--- beam + scale insert: {len((built['beam'] + built['scale_insert']).solids())} solid")

# mesh: sweep one full tooth pitch from reading 0 and confirm the pinion never
# bites the rack
print("--- rack/pinion mesh sweep")
bm = beam()
worst = 0.0
for i in range(13):
    xp = PIN_X + i * (pi * MODULE) / 12
    p = Pos(xp, PIN_Y, 0) * Rot(0, 0, pinion_angle(xp)) * pinion()
    v, _ = inter(bm, p)
    worst = max(worst, v)
    print(f"   x_p {xp:8.3f}  overlap {v:8.5f} mm^3")
print(f"   worst {worst:.5f} mm^3")
