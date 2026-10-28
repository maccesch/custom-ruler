#!/usr/bin/env python3
"""Turn the hand-traced DIN numerals into `cad/stroke_din.json`.

The glyphs come from `cad/fonts/alte_din_trace.svg`, a single-stroke tracing
of the Alte DIN 1451 numerals (one `<path>` per digit, stroked centreline).
This script only parses that file, normalises the glyphs to a 1000-unit cap
and writes the data `cad/vecfont.py` reads.

    python cad/tools/derive_stroke.py            # write data + review sheet
    python cad/tools/derive_stroke.py --check    # fail if the data is stale
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent          # cad/tools
CAD = HERE.parent                               # cad
TRACE = CAD / "fonts" / "alte_din_trace.svg"
OUT = CAD / "stroke_din.json"
REVIEW = CAD / "out" / "din_review.html"

SIZE = 1000             # output cap height, in data units
CURVE_STEPS = 12        # samples per cubic segment
RDP_EPS = 1.2           # data units (~0.0012 cap)

# The renderer lays glyphs out ink-edge to ink-edge and puts a fixed GAP
# between them (see vecfont.extent/GAP), so `adv` is only used for characters
# with no ink (the space) and as a readable record of the design width.
BEARING = 55.0          # nominal side bearing, for the `adv` field
# Per-glyph space adjustment, in data units, applied on top of GAP when a
# glyph sits next to another.  "before" tightens the gap on its left, "after"
# the one on its right; a pair gets prev.after + next.before.
#   1  flag tapers away to the left, so the gap before it reads wider;
#      its stem is a hard edge, so it wants a little more air after
#   7  diagonal leaves the lower right empty, so the gap after it reads wider
KERN = {
    "1": {"before": -40.0, "after": 25.0},
    "7": {"after": -20.0},
}
DOT_Y = 75.0            # centre of the period, above the baseline
SPACE_ADV = 350.0       # no ink, so no channel is added

SVG_NS = "{http://www.w3.org/2000/svg}"
SERIF_NS = "{http://www.serif.com/}"

TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


# ------------------------------------------------------------------ parsing

def parse_path(d: str) -> list[list[tuple[float, float]]]:
    """SVG path data -> polylines (only the commands the trace uses)."""
    toks = TOKEN.findall(d)
    subs: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    pos = (0.0, 0.0)
    start = None
    cmd = None
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd.upper() == "Z":
                if start is not None:
                    cur.append(start)
                    pos = start
                if cur:
                    subs.append(cur)
                cur, start, cmd = [], None, None
                continue

        def take(n):
            nonlocal i
            vals = [float(toks[i + j]) for j in range(n)]
            i += n
            return vals

        rel = cmd.islower()
        kind = cmd.upper()
        if kind == "M":
            x, y = take(2)
            if rel:
                x, y = pos[0] + x, pos[1] + y
            if cur:
                subs.append(cur)
            cur = [(x, y)]
            pos = start = (x, y)
            cmd = "l" if rel else "L"
        elif kind == "L":
            x, y = take(2)
            if rel:
                x, y = pos[0] + x, pos[1] + y
            cur.append((x, y))
            pos = (x, y)
        elif kind == "H":
            (x,) = take(1)
            x = pos[0] + x if rel else x
            cur.append((x, pos[1]))
            pos = (x, pos[1])
        elif kind == "V":
            (y,) = take(1)
            y = pos[1] + y if rel else y
            cur.append((pos[0], y))
            pos = (pos[0], y)
        elif kind == "C":
            x1, y1, x2, y2, x, y = take(6)
            if rel:
                x1, y1, x2, y2, x, y = (pos[0] + x1, pos[1] + y1, pos[0] + x2,
                                        pos[1] + y2, pos[0] + x, pos[1] + y)
            p0 = pos
            for k in range(1, CURVE_STEPS + 1):
                u = k / CURVE_STEPS
                m = 1.0 - u
                cur.append((
                    m**3 * p0[0] + 3 * m * m * u * x1 + 3 * m * u * u * x2 + u**3 * x,
                    m**3 * p0[1] + 3 * m * m * u * y1 + 3 * m * u * u * y2 + u**3 * y,
                ))
            pos = (x, y)
        else:  # pragma: no cover - the trace has no other commands
            raise SystemExit(f"unsupported path command {cmd!r}")
    if cur:
        subs.append(cur)
    return subs


# SVG transforms: (a, b, c, d, e, f) as in matrix(a,b,c,d,e,f)

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mat_mul(m, n):
    """m after n."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _mat_apply(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def _parse_transform(text):
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        else:                                   # rotate/skew: not used here
            raise SystemExit(f"unsupported SVG transform {name!r}")
        m = _mat_mul(m, t)
    return m


def read_trace() -> dict[str, list[list[tuple[float, float]]]]:
    """Glyph name -> contours, with group ids inherited and transforms applied.

    Affinity exports a moved glyph as `<g id="2" transform="matrix(...)">` around
    a bare `<path>`, so the id and the matrix live on the group, not the path.
    """
    root = ElementTree.parse(TRACE).getroot()
    glyphs: dict[str, list[list[tuple[float, float]]]] = {}

    def name_of(el):
        name = el.get(f"{SERIF_NS}id") or el.get("id")
        return name.lstrip("_") if name else None

    def walk(el, matrix, inherited):
        name = name_of(el) or inherited
        transform = el.get("transform")
        if transform:
            matrix = _mat_mul(matrix, _parse_transform(transform))
        if el.tag.split("}")[-1] == "path":
            d = el.get("d")
            if name and d:
                for sub in parse_path(d):
                    glyphs.setdefault(name, []).append([_mat_apply(matrix, p) for p in sub])
            return
        for child in el:
            walk(child, matrix, name)

    walk(root, IDENTITY, None)
    return glyphs


# ---------------------------------------------------------------- geometry

def ramer_douglas(points, eps):
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x0, y0), (x1, y1) = points[a], points[b]
        dx, dy = x1 - x0, y1 - y0
        norm = math.hypot(dx, dy)
        best, best_i = -1.0, -1
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * (x - x0) - dx * (y - y0)) / norm if norm else math.hypot(x - x0, y - y0)
            if d > best:
                best, best_i = d, i
        if best > eps:
            keep[best_i] = True
            stack.append((a, best_i))
            stack.append((best_i, b))
    return [p for p, k in zip(points, keep) if k]


def build() -> dict:
    trace = read_trace()
    if not trace:
        raise SystemExit(f"no glyphs found in {TRACE}")

    ys = [p[1] for subs in trace.values() for sub in subs for p in sub]
    top, bottom = min(ys), max(ys)
    scale = SIZE / (bottom - top)

    glyphs = {}
    for name, subs in sorted(trace.items()):
        flat = [p for sub in subs for p in sub]
        x0 = min(p[0] for p in flat)
        ink = (max(p[0] for p in flat) - x0) * scale
        adv = round(ink + 2.0 * BEARING, 1)
        pad = BEARING

        strokes = []
        for sub in subs:
            pts = [((p[0] - x0) * scale + pad, (bottom - p[1]) * scale) for p in sub]
            pts = ramer_douglas(pts, RDP_EPS)
            strokes.append([(round(x, 1), round(y, 1)) for x, y in pts])
        glyphs[name] = {"adv": adv, "strokes": strokes}

    # a period is a dot: zero-width ink, so the same rule gives its cell
    glyphs["."] = {"adv": round(2.0 * BEARING, 1),
                   "strokes": [[[BEARING, DOT_Y]]]}
    glyphs[" "] = {"adv": SPACE_ADV, "strokes": []}

    return {
        "source": {
            "design": "Alte DIN 1451 Mittelschrift (Ludwig Goller, 1936)",
            "trace": TRACE.name,
            "tool": "cad/tools/derive_stroke.py",
            "licence": "see cad/fonts/NOTICE.md",
        },
        "cap": SIZE,
        "kern": KERN,
        "glyphs": glyphs,
    }


# ------------------------------------------------------------------ review

def review(data):
    """A sheet with every glyph at the sizes the models use, laid out with the
    same ink-edge rule as vecfont (imported from cad/ after the JSON is
    written)."""
    import sys

    sys.path.insert(0, str(CAD))
    import vecfont

    parts = [
        "<!doctype html><meta charset=utf-8><title>DIN stroke review</title>",
        "<style>body{font:13px -apple-system,Helvetica,sans-serif;margin:24px;background:#faf9f7}"
        "h1{font-size:17px}section{background:#fff;border:1px solid #e2ded8;border-radius:8px;"
        "padding:10px 14px;margin-bottom:12px}svg{display:block;margin:2px 0 8px}"
        ".n{color:#666;font-size:12px}</style>",
        "<h1>stroke_din.json</h1>",
        "<p class=n>2.8 mm cap, 0.40 mm channel (top), then 3&times;.</p>",
    ]

    def svg(text, size, stroke):
        unit = size / vecfont.CAP
        placed, ink = vecfont.layout(text, size, stroke)
        d = []
        for glyph, dx in placed:
            for pts in glyph:
                if len(pts) == 1:
                    # a zero-length line with round caps draws the dot; a bare
                    # moveto draws nothing
                    x = dx + pts[0][0] * unit
                    y = -pts[0][1] * unit
                    d.append(f"M{x:.3f},{y:.3f} L{x:.3f},{y:.3f}")
                else:
                    d.append("M" + " L".join(
                        f"{dx + px * unit:.3f},{-py * unit:.3f}" for px, py in pts))
        w = ink + 2 * size
        h = size + 3 * size
        return (f'<svg width="{w * 14:.0f}" height="{h * 14:.0f}" '
                f'viewBox="{-size} {-2 * size} {w} {h}">'
                f'<path d="{" ".join(d)}" fill="none" stroke="#111" stroke-width="{stroke}" '
                'stroke-linecap="round" stroke-linejoin="round"/></svg>')

    for name, text in [("digits", "0123456789"), ("one", "11 10 12.5 100 150"), ("labels", "10 12.5 100 7.5")]:
        parts.append(f"<section><h2>{name}</h2>{svg(text, 2.8, 0.40)}{svg(text, 8.4, 1.35)}</section>")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if the JSON is stale")
    args = ap.parse_args()

    data = build()
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{OUT} is stale - run: python cad/tools/derive_stroke.py")
        print(f"{OUT.name} up to date ({OUT.stat().st_size / 1000:.1f} kB)")
        return
    OUT.write_text(text, encoding="utf-8")
    review(data)
    print(f"{OUT.name}: {len(data['glyphs'])} glyphs, {OUT.stat().st_size / 1000:.1f} kB")
    print(f"review: {REVIEW}")


if __name__ == "__main__":
    main()
