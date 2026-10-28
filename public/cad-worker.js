/*
 * CAD generator worker.
 *
 * Runs the build123d models in cad/*.py entirely in the browser, on Pyodide
 * with the OpenCascade bindings from OCP.wasm (https://github.com/yeicor/OCP.wasm).
 * Nothing is uploaded: the wheels come from PyPI/jsDelivr and every boolean
 * runs on the user's machine.
 *
 * Loaded as a module worker: new Worker(url, {type: "module"}).
 *
 * Protocol
 *   -> {type:"init", sources:{name: text}}      boots Pyodide + build123d
 *   <- {type:"log", text} ... {type:"ready"}
 *   -> {type:"generate", model, env:{...}, parts:[...], prebuilt:[{name,url}]}
 *      model: "caliper" (the dial caliper parts) or "ruler" (a single bar)
 *      parts: the parts to build here; prebuilt: the ones fetched as-is,
 *      since they come out the same for every calibration
 *   <- {type:"log"|"summary"|"file"|"done"|"error"}
 *      file: the whole model as one 3MF, for the page to download as-is
 */

// Pyodide 314.x is CPython 3.14 on the pyemscripten_2026_0 ABI, which is what
// the OCP.wasm wheels are built for.  Bump both together.
const PYODIDE_VERSION = "314.0.2";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const BUILD123D = "build123d==0.11.1";
const BD_WAREHOUSE = "bd_warehouse==0.3.0";

// The caliper 3MF starts from the static Bambu/Orca project
// (`caliper_static.3mf`); the generated beam + black inlay and pinion are
// merged into a copy.  Fetch it once and write it beside the Python modules.
const STATIC_3MF = "/cad/caliper_static.3mf";

// FreeCAD STEPs used by the generated parts: the pinion axis, the socket cut
// out of it, and the beam-profile slice.  Fetch each only when a part that
// uses it is actually being built, and write it into the Pyodide filesystem
// at the path `caliper.py` looks beside itself - the command line reads the
// same files from `cad/`.
const STEP_ASSETS = {
  pinion: ["pinion_axis.step", "pinion_cut_out.step"],
  beam: ["beam.step", "top_bar.step"],
};

// The OCP.wasm wheels are published under their own names; build123d asks for
// the native packages, so they get mocked out at the versions the wasm wheels
// actually provide.  This is the PyPI path of yeicor/OCP.wasm's bootstrap.py.
const BOOTSTRAP_PY = `
import importlib.metadata, micropip

await micropip.install(
    ["cadquery-ocp-novtk-OCP.wasm", "lib3mf-OCP.wasm"],
    keep_going=True,
)

_MOCKS = [
    ("cadquery-ocp-novtk", ["cadquery-ocp", "cadquery-ocp-novtk"]),
    ("lib3mf", ["lib3mf", "py-lib3mf"]),
]
_added = []
for _wheel, _names in _MOCKS:
    _v = importlib.metadata.version(_wheel + "-OCP.wasm")
    for _n in _names:
        if _n == "py-lib3mf":
            micropip.add_mock_package(
                _n, _v, modules={"py_lib3mf": "from lib3mf import *"})
        else:
            micropip.add_mock_package(_n, _v)
        _added.append(_n)

try:
    await micropip.install(["${BUILD123D}", "${BD_WAREHOUSE}"], keep_going=True)
finally:
    for _n in _added:
        try:
            micropip.remove_mock_package(_n)
        except Exception:
            pass

import build123d
print("build123d", build123d.__version__)
`;

const DRIVER_PY = `
import importlib, json, os, sys, time

NL = chr(10)   # the driver is embedded in a JS template literal, where a
               # backslash escape would be eaten before Python sees it

_CAD = "/cad"
_OUT = "/out"


def pi_pitch(c):
    import math
    return math.pi * c.MODULE


def _load(env_json, model):
    """(Re)import a model with a fresh set of parameters."""
    if model not in ("caliper", "ruler"):
        raise ValueError(f"unknown model {model!r}")
    os.environ.update({k: str(v) for k, v in json.loads(env_json).items()})
    for _name, _mod in list(sys.modules.items()):
        # parameters are read at import time, so drop every model module
        if (getattr(_mod, "__file__", None) or "").startswith(_CAD):
            sys.modules.pop(_name, None)
    if _CAD not in sys.path:
        sys.path.insert(0, _CAD)
    os.makedirs(_OUT, exist_ok=True)
    c = importlib.import_module(model)
    globals()["_c"] = c

    text = (
        f"{c.UNITS} {c.UNIT_NAME} per {c.PER_MM:g} mm"
        f" = {c.UNITS_PER_MM:g} {c.UNIT_NAME}/mm{NL}"
        f"range 0-{c.MAX_UNITS} {c.UNIT_NAME} = {c.RANGE:.1f} mm"
    )
    ticks = (
        f"ticks every {c.SCALE_STEPS['minor_units']:g} {c.UNIT_NAME}"
        f" ({c.SCALE_STEPS['minor_mm']:.2f} mm),"
        f" numbered every {c.SCALE_STEPS['major_units']:g}"
    )
    warn = []
    info = {
        "unit": c.UNIT_NAME,
        "units_per_mm": c.UNITS_PER_MM,
        "max_units": c.MAX_UNITS,
        "parts": list(c.PRINT_PARTS),
    }
    if model == "caliper":
        text += (
            f"  (beam {c.BEAM_L:.0f} mm long){NL}"
            + ticks + NL
            + f"dial {c.UNITS_PER_REV:g} {c.UNIT_NAME}/turn"
            f" ({c.MM_PER_REV:.3f} mm/turn, paper face){NL}"
            f"gears module {c.MODULE:.3f}, {c.PINION_TEETH} teeth,"
            f" {pi_pitch(c):.2f} mm rack pitch"
        )
        if c.MODULE < 0.45:
            warn.append(f"teeth are fine for FDM (module {c.MODULE:.2f})")
        if c.BEAM_L > 300:
            warn.append(f"beam is {c.BEAM_L:.0f} mm long")
        info.update({
            "range_mm": round(c.RANGE, 2),
            "beam_mm": round(c.BEAM_L, 1),
            "minor_units": c.SCALE_STEPS["minor_units"],
            "major_units": c.SCALE_STEPS["major_units"],
            "units_per_rev": c.UNITS_PER_REV,
            "module": round(c.MODULE, 4),
            "teeth": c.PINION_TEETH,
        })
    else:
        text += (
            f"{NL}" + ticks + NL
            + f"bar {c.LENGTH:.0f} x {c.WIDTH:.1f} x {c.THICK:g} mm,"
            f" {c.HOLE_D:g} mm hang hole"
        )
        if c.LENGTH > 300:
            warn.append(f"bar is {c.LENGTH:.0f} mm long")
        info.update({
            "range_mm": round(c.RANGE, 2),
            "length_mm": round(c.LENGTH, 1),
            "width_mm": round(c.WIDTH, 1),
            "thickness_mm": c.THICK,
            "hole_mm": c.HOLE_D,
        })
    info.update({"text": text, "warnings": warn})
    return json.dumps(info)


def _build(name):
    from build123d import export_stl
    build = _c.PRINT_PARTS.get(name)
    if build is None:
        raise ValueError(
            f"{_c.__name__} has no part {name!r} (has: {', '.join(_c.PRINT_PARTS)})"
        )
    t0 = time.time()
    part = build()
    path = f"{_OUT}/{name}.stl"
    export_stl(part, path, tolerance=0.01, angular_tolerance=0.1)
    return round(time.time() - t0, 1)


def _to_3mf(names, model):
    import threemf
    path = f"{_OUT}/{model}.3mf"
    if model == "caliper":
        def stl(name):
            p = f"{_OUT}/{name}.stl"
            return p if os.path.exists(p) else None
        # the static 3MF is the base project; the beam and its black inlay
        # become one compound, the pinion stays a separate object
        threemf.write_caliper_3mf(
            path,
            f"{_CAD}/caliper_static.3mf",
            stl("beam"),
            stl("scale_insert"),
            stl("pinion"),
            _readme(model),
        )
    else:
        groups = [[(n, f"{_OUT}/{n}.stl")] for n in names]
        threemf.write_3mf(path, groups, _readme(model))
    return path


def _readme(model):
    c = _c
    head = [
        f"scale    {c.UNITS} {c.UNIT_NAME} per {c.PER_MM:g} mm"
        f" = {c.UNITS_PER_MM:g} {c.UNIT_NAME}/mm",
        f"range    0-{c.MAX_UNITS} {c.UNIT_NAME} = {c.RANGE:.2f} mm",
        f"ticks    every {c.SCALE_STEPS['minor_units']:g} {c.UNIT_NAME},"
        f" numbered every {c.SCALE_STEPS['major_units']:g}",
    ]
    if model == "ruler":
        return NL.join(["3D printable ruler"] + head + [
            f"bar      {c.LENGTH:.1f} x {c.WIDTH:.1f} x {c.THICK:g} mm,"
            f" {c.HOLE_D:g} mm hang hole",
            "",
            "Print flat, engraved face up. See cad/README.md in the project.",
        ])
    return NL.join(["3D printable dial caliper"] + head + [
        f"dial     {c.UNITS_PER_REV:g} {c.UNIT_NAME}/turn"
        f" ({c.MM_PER_REV:.3f} mm/turn, paper face: print the Caliper dial card at 100%)",
        f"gears    module {c.MODULE:.4f}, {c.PINION_TEETH} teeth,"
        f" {c.MM_PER_REV:.3f} mm/turn",
        "",
        "Print orientations and assembly: see cad/README.md in the project.",
    ])
`;

let pyodide = null;
let booting = null;

const log = (text) => postMessage({ type: "log", text });

async function boot(sources) {
  log(`Loading Pyodide ${PYODIDE_VERSION}…`);
  const { loadPyodide } = await import(PYODIDE_CDN + "pyodide.mjs");
  pyodide = await loadPyodide({
    indexURL: PYODIDE_CDN,
    stdout: log,
    stderr: log,
  });

  log("Installing OpenCascade (OCP.wasm) and build123d — ~40 MB, cached by the browser…");
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync(BOOTSTRAP_PY);

  pyodide.FS.mkdirTree("/cad");
  for (const [name, text] of Object.entries(sources)) {
    pyodide.FS.writeFile(`/cad/${name}`, text);
  }
  await pyodide.runPythonAsync(DRIVER_PY);
  log("Ready.");
}

async function generate({ model = "caliper", env, parts, prebuilt = [] }) {
  const summary = JSON.parse(
    await pyodide.runPythonAsync(
      `_load(${JSON.stringify(JSON.stringify(env))}, ${JSON.stringify(model)})`
    )
  );
  postMessage({ type: "summary", summary });

  // the static Bambu/Orca project is the base for every caliper 3MF; the
  // FS survives across runs, so it is downloaded at most once
  if (model === "caliper") {
    if (!pyodide.FS.analyzePath(STATIC_3MF).exists) {
      log("Fetching caliper_static.3mf…");
      const res = await fetch(STATIC_3MF);
      if (!res.ok) throw new Error(`${STATIC_3MF}: HTTP ${res.status}`);
      pyodide.FS.writeFile(
        STATIC_3MF,
        new Uint8Array(await res.arrayBuffer())
      );
    }
  }

  // the STEPs are only needed by the parts that use them; the FS survives
  // across runs, so each is downloaded at most once (and cached by the
  // browser after that)
  if (model === "caliper") {
    for (const part of parts) {
      for (const name of STEP_ASSETS[part] ?? []) {
        const path = `/cad/${name}`;
        if (pyodide.FS.analyzePath(path).exists) continue;
        log(`Fetching ${name}…`);
        const res = await fetch(path);
        if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
        pyodide.FS.writeFile(path, new Uint8Array(await res.arrayBuffer()));
      }
    }
  }

  const built = [];
  for (const name of parts) {
    log(`Building ${name}…`);
    const secs = await pyodide.runPythonAsync(`_build(${JSON.stringify(name)})`);
    const bytes = pyodide.FS.readFile(`/out/${name}.stl`);
    log(`  ${name}.stl — ${(bytes.length / 1024).toFixed(0)} kB in ${secs}s`);
    built.push(name);
  }

  // the scale-independent parts are already built and served as files; drop
  // them in so the 3MF is still the whole model
  for (const { name, url } of prebuilt) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      pyodide.FS.writeFile(
        `/out/${name}.stl`,
        new Uint8Array(await res.arrayBuffer())
      );
      built.push(name);
    } catch (err) {
      log(`  could not add ${name}.stl to the 3MF: ${err.message}`);
    }
  }

  // one 3MF per run, so the download lands as a single file
  const path = await pyodide.runPythonAsync(
    `_to_3mf(${JSON.stringify(built)}, ${JSON.stringify(model)})`
  );
  const bytes = pyodide.FS.readFile(path);
  postMessage(
    { type: "file", filename: `${model}.3mf`, bytes },
    [bytes.buffer]
  );
  postMessage({ type: "done" });
}

self.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      booting = booting || boot(msg.sources);
      await booting;
      postMessage({ type: "ready" });
    } else if (msg.type === "generate") {
      if (!booting) throw new Error("worker not initialised");
      await booting;
      await generate(msg);
    }
  } catch (err) {
    postMessage({ type: "error", text: String((err && err.message) || err) });
  }
};
