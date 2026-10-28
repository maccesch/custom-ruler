"""Write 3MFs: a small standalone writer and a caliper template merger.

`write_3mf` writes one mesh object per part for the ruler (and for any simple
group layout).  `write_caliper_3mf` copies the Bambu/Orca project
`caliper_static.3mf`, keeps its plates and static object transforms, adds the
pinion to the plate holding `SliderTopConnectRing` (centred in that ring), and
adds the beam + black inlay as one compound on the plate holding `SliderBar`,
rotated -45 degrees into the free area around it.  The Bambu sidecars
(printer/filament settings and object names) are preserved.

The template uses the 3MF production extension for its external meshes; the
generated meshes are added inline.  The beam/inlay compound keeps their
relative positions, and the two parts can be assigned different filaments in
the slicer.

Stdlib only, so it runs in Pyodide.
"""

from __future__ import annotations

import io
import json
import math
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

GAP_MM = 5.0          # clear space between parts on the bed
PLATE_MARGIN_MM = 5.0 # clear space from the edge of the print bed
# Bed-local lower-left corner of the beam's 45-degree AABB on plate 3.
# This is the approved layout: the beam stays put while SliderBar moves.
BEAM_TARGET_MM = (48.0, 48.0)
MODEL_PART = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"
CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n')


def read_stl(path):
    """Binary STL -> (vertices, triangles), vertices de-duplicated."""
    with open(path, "rb") as f:
        data = f.read()
    count = struct.unpack_from("<I", data, 80)[0]
    index = {}
    vertices = []
    triangles = []
    for i in range(count):
        off = 84 + i * 50
        v = struct.unpack_from("<12f", data, off)
        tri = []
        for k in (3, 6, 9):
            p = (round(v[k], 4), round(v[k + 1], 4), round(v[k + 2], 4))
            j = index.get(p)
            if j is None:
                j = index[p] = len(vertices)
                vertices.append(p)
            tri.append(j)
        triangles.append(tri)
    return vertices, triangles


def _bounds(vertices):
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _chunks(f, items):
    buf = []
    for s in items:
        buf.append(s)
        if len(buf) >= 4096:
            f.write("".join(buf).encode("utf-8"))
            buf.clear()
    if buf:
        f.write("".join(buf).encode("utf-8"))


def write_3mf(path, groups, description=""):
    """groups: [[(name, stl_path), ...], ...].

    Each group is laid out side by side on the bed; parts within a group keep
    their relative positions, which is what the two-colour beam needs.
    """
    loaded = []
    for group in groups:
        meshes = [(name, *read_stl(stl)) for name, stl in group]
        x0 = min(_bounds(v)[0] for _, v, _ in meshes)
        y0 = min(_bounds(v)[1] for _, v, _ in meshes)
        z0 = min(_bounds(v)[2] for _, v, _ in meshes)
        width = max(_bounds(v)[3] for _, v, _ in meshes) - x0
        loaded.append((meshes, (x0, y0, z0, width)))

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        with z.open("3D/3dmodel.model", "w") as f:
            f.write(HEAD.encode("utf-8"))
            if description:
                f.write(f'<metadata name="Description">'
                        f'{escape(description)}</metadata>'.encode("utf-8"))
            f.write(b"<resources>")
            cursor = 0.0
            objects = []
            for meshes, (x0, y0, z0, width) in loaded:
                dx, dy, dz = cursor - x0, -y0, -z0
                for name, vertices, triangles in meshes:
                    oid = len(objects) + 1
                    objects.append(oid)
                    f.write(f'<object id="{oid}" type="model" '
                            f'name={quoteattr(name)}><mesh><vertices>'.encode("utf-8"))
                    _chunks(f, (f'<vertex x="{x + dx:g}" y="{y + dy:g}" z="{z + dz:g}"/>'
                                for x, y, z in vertices))
                    f.write(b"</vertices><triangles>")
                    _chunks(f, (f'<triangle v1="{a}" v2="{b}" v3="{c}"/>'
                                for a, b, c in triangles))
                    f.write(b"</triangles></mesh></object>")
                cursor += width + GAP_MM
            f.write(b"</resources><build>")
            for oid in objects:
                f.write(f'<item objectid="{oid}"/>'.encode("utf-8"))
            f.write(b"</build></model>")
    return path


# --------------------------------------------------------------------------
# Merging generated parts into the static Bambu/Orca project
# --------------------------------------------------------------------------

def _chunks_text(f, items):
    """Stream XML fragments to a text file without holding every triangle."""
    buf = []
    for s in items:
        buf.append(s)
        if len(buf) >= 4096:
            f.write("".join(buf))
            buf.clear()
    if buf:
        f.write("".join(buf))


def _shift(vertices, dx, dy, dz):
    return [(x + dx, y + dy, z + dz) for x, y, z in vertices]


def _write_mesh_object(f, oid, name, vertices, triangles):
    f.write(f'<object id="{oid}" type="model" name={quoteattr(name)}>'
            f'<mesh><vertices>')
    _chunks_text(f, (f'<vertex x="{x:g}" y="{y:g}" z="{z:g}"/>'
                     for x, y, z in vertices))
    f.write("</vertices><triangles>")
    _chunks_text(f, (f'<triangle v1="{a}" v2="{b}" v3="{c}"/>'
                     for a, b, c in triangles))
    f.write("</triangles></mesh></object>")


def _write_components_object(f, oid, name, children):
    f.write(f'<object id="{oid}" type="model" name={quoteattr(name)}>'
            f'<components>')
    for child in children:
        f.write(f'<component objectid="{child}"/>')
    f.write("</components></object>")


def _normalise_group(meshes):
    """Move a group of meshes so its combined minimum is (0, 0, 0)."""
    x0 = min(_bounds(v)[0] for _, v, _ in meshes)
    y0 = min(_bounds(v)[1] for _, v, _ in meshes)
    z0 = min(_bounds(v)[2] for _, v, _ in meshes)
    normalised = [(name, _shift(v, -x0, -y0, -z0), t)
                  for name, v, t in meshes]
    width = max(_bounds(v)[3] for _, v, _ in normalised)
    return normalised, width


def _bed_size(z):
    """Read the printer's usable width and depth from the template."""
    try:
        cfg = json.loads(z.read(PROJECT_SETTINGS).decode("utf-8"))
        xs, ys = [], []
        for corner in cfg.get("printable_area", []):
            x, y = corner.lower().split("x")
            xs.append(float(x))
            ys.append(float(y))
        if xs and ys:
            return max(xs), max(ys)
    except (KeyError, ValueError, TypeError):
        pass
    return 256.0, 256.0


_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def _matrix(text):
    """A 3MF 12-value row-major transform, or a model_settings 4x4 matrix."""
    if not text:
        return _IDENTITY
    values = [float(v) for v in text.split()]
    if len(values) == 12:
        return tuple(values)
    if len(values) == 16:
        # model_settings stores a row-major 4x4; the build uses 4x3
        return (values[0], values[1], values[2],
                values[4], values[5], values[6],
                values[8], values[9], values[10],
                values[12], values[13], values[14])
    raise ValueError(f"bad 3MF transform: {text!r}")


def _apply_matrix(m, point):
    """Apply a 3MF transform.

    3MF stores matrices in row-major order and transforms points as row
    vectors (v' = v * M), so the translation lives in the last row
    (elements 9-11) and the linear part is the transpose of the usual
    column-vector matrix.
    """
    x, y, z = point
    return (x * m[0] + y * m[3] + z * m[6] + m[9],
            x * m[1] + y * m[4] + z * m[7] + m[10],
            x * m[2] + y * m[5] + z * m[8] + m[11])


def _matrix_bounds(bounds, m):
    x0, y0, z0, x1, y1, z1 = bounds
    points = [_apply_matrix(m, (x, y, z))
              for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _combine_bounds(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]),
            max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5]))


def _mesh_vertices_bounds(mesh):
    vertices = list(mesh.iter(CORE + "vertex"))
    if not vertices:
        raise ValueError("mesh has no vertices")
    xs = [float(v.get("x")) for v in vertices]
    ys = [float(v.get("y")) for v in vertices]
    zs = [float(v.get("z")) for v in vertices]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _resource_objects(root):
    return {obj.get("id"): obj for obj in root.iter(CORE + "object")}


def _production_object_bounds(oid, objects, zin, cache, prefix=""):
    """Object AABB, following both inline meshes and p:path components."""
    key = (prefix, oid)
    if key in cache:
        return cache[key]
    obj = objects[oid]
    mesh = obj.find(CORE + "mesh")
    if mesh is not None:
        bounds = _mesh_vertices_bounds(mesh)
    else:
        bounds = None
        components = obj.find(CORE + "components")
        if components is None:
            raise ValueError(f"object {oid} has no mesh or components")
        for component in components.findall(CORE + "component"):
            child = component.get("objectid")
            path = component.get(PROD + "path")
            if path:
                root = cache.get(("root", path))
                if root is None:
                    root = ET.fromstring(zin.read(path.lstrip("/")))
                    cache[("root", path)] = root
                child_objects = _resource_objects(root)
                child_bounds = _production_object_bounds(
                    child, child_objects, zin, cache, path)
            else:
                child_bounds = _production_object_bounds(
                    child, objects, zin, cache, prefix)
            moved = _matrix_bounds(
                child_bounds, _matrix(component.get("transform")))
            bounds = moved if bounds is None else _combine_bounds(bounds, moved)
        if bounds is None:
            raise ValueError(f"object {oid} has no mesh or components")
    cache[key] = bounds
    return bounds


def _mesh_vertices(mesh):
    return [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
            for v in mesh.iter(CORE + "vertex")]


def _production_object_vertices(oid, objects, zin, cache, prefix=""):
    """All transformed vertices of an object, for obstacle footprints."""
    key = ("vertices", prefix, oid)
    if key in cache:
        return cache[key]
    obj = objects[oid]
    mesh = obj.find(CORE + "mesh")
    if mesh is not None:
        points = _mesh_vertices(mesh)
    else:
        points = []
        components = obj.find(CORE + "components")
        if components is None:
            raise ValueError(f"object {oid} has no mesh or components")
        for component in components.findall(CORE + "component"):
            child = component.get("objectid")
            path = component.get(PROD + "path")
            if path:
                root = cache.get(("root", path))
                if root is None:
                    root = ET.fromstring(zin.read(path.lstrip("/")))
                    cache[("root", path)] = root
                child_objects = _resource_objects(root)
                child_points = _production_object_vertices(
                    child, child_objects, zin, cache, path)
            else:
                child_points = _production_object_vertices(
                    child, objects, zin, cache, prefix)
            matrix = _matrix(component.get("transform"))
            points.extend(_apply_matrix(matrix, point)
                          for point in child_points)
    cache[key] = points
    return points


def _convex_hull(points):
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def cross(origin, a, b):
        return ((a[0] - origin[0]) * (b[1] - origin[1])
                - (a[1] - origin[1]) * (b[0] - origin[0]))

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _point_segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (a[0] + t * dx),
                      point[1] - (a[1] + t * dy))


def _segment_distance(a, b, c, d):
    def orientation(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(_point_segment_distance(a, c, d),
               _point_segment_distance(b, c, d),
               _point_segment_distance(c, a, b),
               _point_segment_distance(d, a, b))


def _point_in_convex_polygon(point, polygon):
    """True when a point is inside (or on) a convex polygon."""
    sign = None
    px, py = point
    for i in range(len(polygon)):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % len(polygon)]
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        if abs(cross) <= 1e-12:
            continue
        side = cross > 0
        if sign is None:
            sign = side
        elif side != sign:
            return False
    return True


def _polygon_distance(a, b):
    """Minimum boundary distance between two convex polygons (0 if overlapping)."""
    if (any(_point_in_convex_polygon(p, b) for p in a)
            or any(_point_in_convex_polygon(p, a) for p in b)):
        return 0.0
    best = float("inf")
    for i in range(len(a)):
        for j in range(len(b)):
            best = min(best, _segment_distance(
                a[i], a[(i + 1) % len(a)],
                b[j], b[(j + 1) % len(b)]))
    return best


def _place_diagonal_beam(length, width, obstacles, bed_w, bed_h, margin):
    """Place the beam on the free diagonal of its plate.

    The beam runs from the upper-left towards the lower-right, with its
    hooked end at the lower-right corner of the plate.
    """
    theta = math.radians(-45)
    c, s = math.cos(theta), math.sin(theta)
    rectangle = [(0.0, 0.0), (length, 0.0),
                 (length, width), (0.0, width)]
    # Column-vector footprint of the beam.  This is also the motion Orca
    # performs, because the matrix written below is its transpose.
    rotated = [(c * x - s * y, s * x + c * y) for x, y in rectangle]
    rx0 = min(x for x, _ in rotated)
    rx1 = max(x for x, _ in rotated)
    ry0 = min(y for _, y in rotated)
    ry1 = max(y for _, y in rotated)
    width_aabb, height_aabb = rx1 - rx0, ry1 - ry0
    if width_aabb > bed_w - 2 * margin or height_aabb > bed_h - 2 * margin:
        raise ValueError("the beam does not fit diagonally on its plate")

    # Keep the beam at the approved spot on the plate; the static objects can
    # move around it.  Only fall back to a clearance search if the fixed spot
    # would leave the bed.
    target_x, target_y = BEAM_TARGET_MM
    if (target_x < margin or target_y < margin
            or target_x + width_aabb > bed_w - margin
            or target_y + height_aabb > bed_h - margin):
        best = None
        x_max = bed_w - margin - width_aabb
        y_max = bed_h - margin - height_aabb
        step = 1.0
        x = margin
        while x <= x_max + 1e-9:
            y = margin
            while y <= y_max + 1e-9:
                beam = [(px - rx0 + x, py - ry0 + y) for px, py in rotated]
                clearance = min(x, y, bed_w - (x + width_aabb),
                                bed_h - (y + height_aabb))
                for obstacle in obstacles:
                    if clearance <= best[0] if best else False:
                        break
                    clearance = min(
                        clearance, _polygon_distance(beam, obstacle))
                if best is None or clearance > best[0]:
                    best = (clearance, x, y, beam)
                y += step
            x += step
        if best is None or best[0] <= 0:
            raise ValueError("no clear diagonal space for the beam on its plate")
        _, target_x, target_y, _ = best
    # 3MF applies row vectors, so store the transpose of the column
    # rotation above; otherwise Orca rotates the beam the other way.
    rotation = (c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
    local = rotation[:9] + (target_x - rx0, target_y - ry0, 0.0)
    clearance = min(target_x, target_y,
                    bed_w - (target_x + width_aabb),
                    bed_h - (target_y + height_aabb))
    return theta, local, clearance


def _settings_object_names(settings):
    result = {}
    for obj in settings.findall("object"):
        name = obj.find("metadata[@key='name']")
        if name is not None:
            result[name.get("value")] = obj.get("id")
    return result


def _plate_map(settings):
    result = {}
    for plate in settings.findall("plate"):
        value = plate.find("metadata[@key='plater_id']")
        if value is None or not value.get("value", "").isdigit():
            continue
        plate_id = int(value.get("value"))
        for instance in plate.findall("model_instance"):
            oid = instance.find("metadata[@key='object_id']")
            if oid is not None:
                result[oid.get("value")] = plate_id
    return result


def _plate_origins(plate_ids, bed_w, bed_h):
    count = max(plate_ids, default=1)
    cols = round(math.sqrt(count))
    if math.sqrt(count) > cols:
        cols += 1
    cols = max(cols, 1)
    return {
        plate_id: ((plate_id - 1) % cols * bed_w * 1.2,
                   -((plate_id - 1) // cols) * bed_h * 1.2)
        for plate_id in plate_ids
    }


def _production_layout(zin, model, settings, bed_w, bed_h):
    """Static build items in world and plate-local coordinates."""
    root = ET.fromstring(model)
    objects = _resource_objects(root)
    plate_map = _plate_map(settings)
    plate_ids = sorted({
        int(plate.find("metadata[@key='plater_id']").get("value"))
        for plate in settings.findall("plate")
        if plate.find("metadata[@key='plater_id']") is not None
    })
    origins = _plate_origins(plate_ids, bed_w, bed_h)
    cache = {}
    items = []
    for item in root.find(CORE + "build").findall(CORE + "item"):
        oid = item.get("objectid")
        transform = _matrix(item.get("transform"))
        world = _matrix_bounds(
            _production_object_bounds(oid, objects, zin, cache), transform)
        plate_id = plate_map.get(oid)
        local = None
        if plate_id in origins:
            ox, oy = origins[plate_id]
            local = (world[0] - ox, world[1] - oy, world[2],
                     world[3] - ox, world[4] - oy, world[5])
        items.append({
            "objectid": oid,
            "plate_id": plate_id,
            "transform": transform,
            "world": world,
            "local": local,
        })
    return items, origins


def _add_plate_instance(settings, plate_id, object_id, identify_id):
    plate = None
    for candidate in settings.findall("plate"):
        value = candidate.find("metadata[@key='plater_id']")
        if value is not None and value.get("value") == str(plate_id):
            plate = candidate
            break
    if plate is None:
        raise ValueError(f"plate {plate_id} is missing from the template")
    instance = ET.SubElement(plate, "model_instance")
    ET.SubElement(instance, "metadata", {
        "key": "object_id", "value": str(object_id)})
    ET.SubElement(instance, "metadata", {
        "key": "instance_id", "value": "0"})
    ET.SubElement(instance, "metadata", {
        "key": "identify_id", "value": str(identify_id)})


def _format_transform(matrix):
    return " ".join(f"{value:g}" for value in matrix)


def _set_description(model, description):
    """Replace the template's Description metadata with the current model."""
    if not description:
        return model
    pattern = re.compile(r'(<metadata name="Description">).*?(</metadata>)',
                         re.DOTALL)

    def replace(match):
        return match.group(1) + escape(description) + match.group(2)

    return pattern.sub(replace, model, count=1)


def _settings_object(oid, name, parts, extruder=1):
    """One Bambu model_settings object containing one or more parts.

    parts: [(child_object_id, part_name, extruder), ...]
    """
    obj = ET.Element("object", {"id": str(oid)})
    ET.SubElement(obj, "metadata", {"key": "name", "value": name})
    ET.SubElement(obj, "metadata",
                  {"key": "extruder", "value": str(extruder)})
    for child, part_name, extruder in parts:
        part = ET.SubElement(obj, "part", {
            "id": str(child), "subtype": "normal_part"})
        ET.SubElement(part, "metadata", {"key": "name", "value": part_name})
        ET.SubElement(part, "metadata",
                      {"key": "extruder", "value": str(extruder)})
        ET.SubElement(part, "metadata", {
            "key": "matrix",
            "value": "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1",
        })
        ET.SubElement(part, "mesh_stat", {
            "edges_fixed": "0",
            "degenerate_facets": "0",
            "facets_removed": "0",
            "facets_reversed": "0",
            "backwards_edges": "0",
        })
    return obj


def _next_identify_id(root):
    used = []
    for element in root.iter("metadata"):
        if element.get("key") != "identify_id":
            continue
        value = element.get("value", "")
        if value.lstrip("-").isdigit():
            used.append(int(value))
    return max(used, default=0) + 22


def write_caliper_3mf(path, template, beam_stl=None, insert_stl=None,
                     pinion_stl=None, description=""):
    """Add the generated parts to the static Bambu/Orca project.

    The static objects keep their existing plates, positions and rotations.
    The pinion goes on the plate that carries SliderTopConnectRing, centred in
    that ring.  The beam + black inlay compound goes on the plate that carries
    SliderBar, rotated to the angle that allows the longest beam in the empty
    area around it.
    """
    path = Path(path)
    template = Path(template)

    if not template.is_file():
        raise FileNotFoundError(
            f"{template} is missing; it is the static caliper template")

    with zipfile.ZipFile(template) as zin:
        model = zin.read(MODEL_PART).decode("utf-8")
        settings_text = zin.read(MODEL_SETTINGS).decode("utf-8")
        bed_w, bed_h = _bed_size(zin)
        settings = ET.fromstring(settings_text)
        names = _settings_object_names(settings)
        items, origins = _production_layout(
            zin, model, settings, bed_w, bed_h)
        root = ET.fromstring(model)
        objects = _resource_objects(root)

        # --- generated meshes -------------------------------------------------
        beam_meshes = []
        if beam_stl:
            beam_meshes.append(("Beam", *read_stl(beam_stl)))
        if insert_stl:
            beam_meshes.append(("Black bar", *read_stl(insert_stl)))
        beam_normalised = []
        beam_bounds = None
        if beam_meshes:
            beam_normalised, _ = _normalise_group(beam_meshes)
            beam_bounds = (
                0.0, 0.0, 0.0,
                max(_bounds(v)[3] for _, v, _ in beam_normalised),
                max(_bounds(v)[4] for _, v, _ in beam_normalised),
                max(_bounds(v)[5] for _, v, _ in beam_normalised),
            )

        pinion_mesh = None
        pinion_bounds = None
        if pinion_stl:
            pinion_mesh = ("Pinion", *read_stl(pinion_stl))
            pinion_normalised, _ = _normalise_group([pinion_mesh])
            pinion_mesh = pinion_normalised[0]
            name, vertices, _triangles = pinion_mesh
            pinion_bounds = (0.0, 0.0, 0.0,
                             max(v[0] for v in vertices),
                             max(v[1] for v in vertices),
                             max(v[2] for v in vertices))

        # --- pinion: centre of SliderTopConnectRing --------------------------
        pinion_transform = None
        pinion_plate = None
        if pinion_bounds:
            ring_oid = names.get("SliderTopConnectRing", "10")
            ring_item = next(
                (item for item in items if item["objectid"] == ring_oid), None)
            if ring_item is None:
                raise ValueError("SliderTopConnectRing is missing from the template")
            ring = ring_item["world"]
            pinion_plate = ring_item["plate_id"]
            cx = (ring[0] + ring[3]) / 2
            cy = (ring[1] + ring[4]) / 2
            pinion_transform = _IDENTITY[:9] + (
                cx - (pinion_bounds[3] - pinion_bounds[0]) / 2,
                cy - (pinion_bounds[4] - pinion_bounds[1]) / 2,
                0.0,
            )

        # --- beam: diagonal in the free area of the SliderBar plate ----------
        beam_plate = None
        beam_transform = None
        if beam_bounds:
            slider_oid = names.get("SliderBar", "16")
            slider_item = next(
                (item for item in items if item["objectid"] == slider_oid), None)
            if slider_item is None:
                raise ValueError("SliderBar is missing from the template")
            beam_plate = slider_item["plate_id"]
            ox, oy = origins[beam_plate]
            obstacles = []
            vertex_cache = {}
            for item in items:
                if item["plate_id"] != beam_plate:
                    continue
                points = _production_object_vertices(
                    item["objectid"], objects, zin, vertex_cache)
                local_points = []
                for point in points:
                    moved = _apply_matrix(item["transform"], point)
                    local_points.append((moved[0] - ox, moved[1] - oy))
                hull = _convex_hull(local_points)
                if len(hull) >= 3:
                    obstacles.append(hull)
            beam_length = beam_bounds[3] - beam_bounds[0]
            beam_width = beam_bounds[4] - beam_bounds[1]
            _theta, local, _clearance = _place_diagonal_beam(
                beam_length, beam_width, obstacles,
                bed_w, bed_h, PLATE_MARGIN_MM)
            beam_transform = local[:9] + (
                local[9] + ox, local[10] + oy, 0.0)

        # --- resource ids -----------------------------------------------------
        used_ids = [int(m.group(1)) for m in
                    re.finditer(r'<object\b[^>]*\bid="(\d+)"', model)]
        next_id = max(used_ids, default=0) + 1

        resources = io.StringIO()
        settings_objects = []   # (wrapper_id, name, parts, extruder)
        beam_wrapper = None
        pinion_wrapper = None

        if beam_normalised:
            child_ids = []
            for name, vertices, triangles in beam_normalised:
                _write_mesh_object(resources, next_id, name, vertices, triangles)
                child_ids.append(next_id)
                next_id += 1
            beam_wrapper = next_id
            next_id += 1
            wrapper_name = ("Beam + black bar" if len(child_ids) == 2
                            else beam_normalised[0][0])
            _write_components_object(
                resources, beam_wrapper, wrapper_name, child_ids)
            parts = []
            for child, (name, _, _) in zip(child_ids, beam_normalised):
                parts.append((child, name, 2 if name == "Black bar" else 1))
            settings_objects.append((beam_wrapper, wrapper_name, parts, 1))

        if pinion_mesh:
            name, vertices, triangles = pinion_mesh
            child = next_id
            next_id += 1
            _write_mesh_object(resources, child, name, vertices, triangles)
            pinion_wrapper = next_id
            next_id += 1
            _write_components_object(resources, pinion_wrapper, name, [child])
            # filament 2, like the slider hardware
            settings_objects.append(
                (pinion_wrapper, name, [(child, name, 2)], 2))

        new_resources = resources.getvalue()

        # --- model XML --------------------------------------------------------
        if description:
            model = _set_description(model, description)

        resource_close = model.rfind("</resources>")
        if resource_close < 0:
            raise ValueError(f"{template} has no resources section")
        model = (model[:resource_close] + new_resources
                 + model[resource_close:])

        dynamic_items = []
        if beam_wrapper is not None and beam_transform is not None:
            dynamic_items.append(
                f'<item objectid="{beam_wrapper}" '
                f'transform="{_format_transform(beam_transform)}" '
                f'printable="1" auto_drop="1"/>')
        if pinion_wrapper is not None and pinion_transform is not None:
            dynamic_items.append(
                f'<item objectid="{pinion_wrapper}" '
                f'transform="{_format_transform(pinion_transform)}" '
                f'printable="1" auto_drop="1"/>')
        build_close = model.rfind("</build>")
        if build_close < 0:
            raise ValueError(f"{template} has no build section")
        model = (model[:build_close] + "".join(dynamic_items)
                 + model[build_close:])

        # --- Bambu model_settings --------------------------------------------
        first_plate = next(
            (i for i, element in enumerate(settings) if element.tag == "plate"),
            len(settings))
        for offset, obj in enumerate(
                _settings_object(oid, name, parts, extruder)
                for oid, name, parts, extruder in settings_objects):
            settings.insert(first_plate + offset, obj)

        identify = _next_identify_id(settings)
        if pinion_wrapper is not None and pinion_plate is not None:
            _add_plate_instance(settings, pinion_plate, pinion_wrapper, identify)
            identify += 22
        if beam_wrapper is not None and beam_plate is not None:
            _add_plate_instance(settings, beam_plate, beam_wrapper, identify)

        settings_bytes = ET.tostring(
            settings, encoding="utf-8", xml_declaration=True)

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename == MODEL_PART:
                    data = model.encode("utf-8")
                elif info.filename == MODEL_SETTINGS:
                    data = settings_bytes
                else:
                    data = zin.read(info.filename)
                zout.writestr(info, data)

    return path
