"""Hidden-line preview drawings of the assembled caliper."""
from build123d import *
from build123d.exporters import ExportSVG
from caliper import assembly

parts = [loc * s for n, s, loc in assembly()]
asm = Compound(children=parts)

def draw(shape, name, scale=6.0):
    ex = ExportSVG(scale=scale, margin=6, line_weight=0.18)
    ex.add_layer("hidden", line_type=LineType.ISO_DOT, line_weight=0.08)
    ex.add_layer("visible")
    ex.add_shape(shape, layer="visible", reverse_wires=False)
    ex.write(name)
    print("wrote", name)

from caliper import pinion
for shape, name in [(asm, "out/caliper_front.svg"),
                    (pinion(), "out/pinion.svg"),
                    (Rot(-90, 0, 0) * asm, "out/caliper_top.svg")]:
    try:
        draw(shape, name)
    except Exception as exc:          # svgpathtools chokes on some tiny edges
        print("skipped", name, type(exc).__name__)
