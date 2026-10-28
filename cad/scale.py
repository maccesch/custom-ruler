"""Scale generation in arbitrary units - a port of ../src/scale.rs.

`units_per_mm` is how many logical units fit into one physical millimetre,
calibrated the same way as the web app: UNITS counted over PER_MM millimetres.
Minor ticks land every ~1.5 mm by snapping to a nice 1/2/5 x 10^n step, with
medium at 5x and major at 10x that.
"""

from math import floor, log10

MAX_TICKS = 5000

MINOR, MEDIUM, MAJOR = "minor", "medium", "major"


def nice_ceil(x):
    """Smallest nice 1/2/5 x 10^n value that is >= x."""
    if x <= 1.0:
        return 1
    pow10 = 10.0 ** floor(log10(x))
    m = x / pow10
    base = 1.0 if m <= 1.0 else 2.0 if m <= 2.0 else 5.0 if m <= 5.0 else 10.0
    return round(base * pow10)


def nice_ceil_frac(x):
    """Like nice_ceil but not clamped at 1 - the dial needs steps finer than
    one unit (0.5, 0.2, 0.1 ...)."""
    if x <= 0:
        return 1.0
    pow10 = 10.0 ** floor(log10(x))
    m = x / pow10
    base = 1.0 if m <= 1.0 else 2.0 if m <= 2.0 else 5.0 if m <= 5.0 else 10.0
    return float(f"{base * pow10:.10g}")


def nice_round(x):
    """Nearest nice 1/2/5 x 10^n value (on a log scale)."""
    if x <= 0:
        return 1
    pow10 = 10.0 ** floor(log10(x))
    m = x / pow10
    base = min((1.0, 2.0, 5.0, 10.0), key=lambda b: abs(log10(m / b)))
    return round(base * pow10)


def nice_minor_step(units_per_mm, units_eff):
    """Minor step in units giving ~1.5 mm spacing, capped so that a labelled
    major tick (10x the minor step) always fits inside the scale."""
    if units_per_mm <= 0:
        return 1
    raw = 1.5 * units_per_mm
    if raw <= 1.0:
        base_step = 1
    else:
        pow10 = 10.0 ** floor(log10(raw))
        m = raw / pow10
        base = 1.0 if m < 1.75 else 2.0 if m < 3.5 else 5.0 if m < 7.5 else 10.0
        base_step = round(base * pow10)
    return max(1, min(base_step, max(1, units_eff // 10)))


def compute_ticks(units_eff, units_per_mm):
    """-> (steps, ticks).  Ticks land only on exact multiples of the minor
    step, so the last one may sit short of units_eff; total_mm still describes
    the full length."""
    if units_eff <= 0 or units_per_mm <= 0:
        raise ValueError("units_eff and units_per_mm must be positive")

    minor = nice_minor_step(units_per_mm, units_eff)
    min_step_for_count = -(-units_eff // MAX_TICKS)      # ceil div
    if min_step_for_count > minor:
        minor = nice_ceil(float(min_step_for_count))
    medium, major = minor * 5, minor * 10

    steps = {
        "minor_units": minor,
        "medium_units": medium,
        "major_units": major,
        "total_mm": units_eff / units_per_mm,
        "minor_mm": minor / units_per_mm,
        "medium_mm": medium / units_per_mm,
        "major_mm": major / units_per_mm,
    }

    ticks = []
    u = 0
    while u <= units_eff:
        kind = MAJOR if u % major == 0 else MEDIUM if u % medium == 0 else MINOR
        ticks.append({
            "value": u,
            "mm": u / units_per_mm,
            "kind": kind,
            # 0 keeps its major tick but goes unlabelled
            "label": kind == MAJOR and u > 0,
        })
        u += minor
    return steps, ticks


if __name__ == "__main__":
    # the worked examples from src/scale.rs, so the two stay in step
    s, _ = compute_ticks(150, 1.0)
    assert (s["minor_units"], s["medium_units"], s["major_units"]) == (1, 5, 10)
    assert abs(s["total_mm"] - 150.0) < 1e-9
    s, _ = compute_ticks(150, 10.0)
    assert (s["minor_units"], s["major_units"]) == (10, 100)
    assert abs(s["total_mm"] - 15.0) < 1e-9
    s, _ = compute_ticks(100, 2.0)
    assert (s["minor_units"], s["medium_units"]) == (2, 10)
    s, t = compute_ticks(155, 2.0)
    assert t[-1]["value"] == 154 and abs(s["total_mm"] - 77.5) < 1e-9
    s, t = compute_ticks(100_000, 1.0)
    assert s["minor_units"] == 20 and len(t) <= MAX_TICKS + 1
    assert [nice_ceil(v) for v in (0.4, 1.0, 1.1, 3.0, 20.0, 21.0)] == \
           [1, 1, 2, 5, 20, 50]
    assert [nice_ceil_frac(v) for v in (0.2, 0.11, 2.0, 3.0)] == [0.2, 0.2, 2.0, 5.0]
    for d in (0.5, 1.0, 2.0, 10.0, 33.0, 250.0):
        assert nice_minor_step(d, 50_000) / d <= 2.0
    print("scale.py matches src/scale.rs on every ported case")
