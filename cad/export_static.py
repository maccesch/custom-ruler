"""Sync the static assets the browser needs with the files in `cad/`.

The caliper's static hardware (FacePlate, DialRing, SliderBottom, SliderTop,
ArrestLever, SliderTopConnectRing, ThumbPinion, SliderBar) is packaged in
`caliper_static.3mf`, a Bambu/Orca project.  The browser fetches that project
and merges the generated beam + black inlay and pinion into a copy, so the
whole model still arrives as one 3MF.

The STEPs are used by the generated parts: the pinion axis/socket, the beam
profile and the 0-end bar.  The browser fetches those too, only when a part
that uses them is actually built.

    python cad/export_static.py            # write ../public/cad
    python cad/export_static.py --check    # verify what is there is current
"""

import sys
from pathlib import Path

CAD = Path(__file__).resolve().parent
PUBLIC_CAD = CAD.parent / "public" / "cad"

ASSETS = (
    "caliper_static.3mf",
    "pinion_axis.step",
    "pinion_cut_out.step",
    "beam.step",
    "top_bar.step",
)


def sync_assets(check_only=False):
    """Keep the served copies byte-identical to the files in `cad/`."""
    stale = False
    for name in ASSETS:
        want = CAD / name
        if not want.is_file():
            print(f"  {name:<24} MISSING from cad/")
            stale = True
            continue
        path = PUBLIC_CAD / name
        current = path.read_bytes() if path.is_file() else None
        if current == want.read_bytes():
            print(f"  {name:<24} up to date ({want.stat().st_size / 1000:.0f} kB)")
            continue
        stale = True
        if check_only:
            print(f"  {name:<24} "
                  + ("STALE" if current is not None else "MISSING"))
        else:
            PUBLIC_CAD.mkdir(parents=True, exist_ok=True)
            path.write_bytes(want.read_bytes())
            print(f"  {name:<24} written ({want.stat().st_size / 1000:.0f} kB)")
    return stale


def main(check_only=False):
    print("static assets (served to the browser):")
    stale = sync_assets(check_only)
    if check_only and stale:
        print("\nout of date - run: python cad/export_static.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(check_only="--check" in sys.argv))
