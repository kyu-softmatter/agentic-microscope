"""Derive a one-camera Micro-Manager config from the dual-camera one.

    python config/micromanager/make_single_cam_cfg.py --keep Kinetix_blue
    python config/micromanager/make_single_cam_cfg.py --keep Kinetix_red --check

For one experiment: can the Tweez 300 GUI keep one Kinetix for its bead tracking
while Micro-Manager images on the other? PVCAM hands a camera to one process at a
time, and today the whole conflict is treated as unavoidable -- the Tweez GUI
holds the camera, or Micro-Manager does, and whichever loses cannot see what it
needs (`kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md` §8).

But there are **two** Kinetix bodies, and in `DMD_dualcam_LUNF.cfg` they are two
independent PVCAM devices -- `Camera-1` and `Camera-2` -- with no Multi-Camera or
splitter device wrapping them, no config group switching `Core,Camera`, and no
per-camera preset. So "one owner each" is expressible in Micro-Manager, and the
edit that expresses it is two lines. That is what this generates.

WHAT IT DOES NOT SETTLE
-----------------------
Two things, and both have to be checked at the instrument:

  - **Which physical body MM actually opened.** PVCAM enumerates by index, and
    whether `Camera-1` still means the same Kinetix once the other is held by a
    different process is untested. If the indices shift, MM opens the wrong body
    and reports nothing wrong. Check by serial, not by label.
  - **Whether the trap plane appears on the kept camera at all.** That is optics,
    not configuration, and nothing in this repo can answer it.

So a successful load is necessary and nowhere near sufficient. `--check` verifies
only the derivation: that the output is the parent minus exactly the two intended
lines.

WHY GENERATE RATHER THAN HAND-EDIT
----------------------------------
A config that is hand-edited is a config nobody can regenerate after the parent
changes, and this one gets loaded against real hardware. Generating it keeps the
provenance in the file and makes the diff checkable, which is what `--check`
prints. Line endings are read from the parent and preserved -- this repo lives in
a Box sync folder edited from both Windows and macOS.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE / "DMD_dualcam_LUNF.cfg"

#: label -> the PVCAM device name it is registered under in the parent.
CAMERAS = {"Kinetix_blue": "Camera-1", "Kinetix_red": "Camera-2"}


def derive(parent: Path, keep: str) -> tuple[bytes, list[str]]:
    """Return the derived bytes and a list of the edits made."""
    if keep not in CAMERAS:
        raise SystemExit(f"--keep must be one of {sorted(CAMERAS)}; got {keep!r}")
    drop = next(label for label in CAMERAS if label != keep)

    raw = parent.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    device_line = f"Device,{drop},PVCAM,{CAMERAS[drop]}".encode()

    core_camera = f"Property,Core,Camera,{keep}".encode()
    out, edits = [], []
    for line in raw.split(eol):
        stripped = line.strip()
        if stripped == device_line:
            edits.append(f"removed  {stripped.decode()}")
            continue
        if stripped.startswith(b"Property,Core,Camera,"):
            out.append(core_camera)
            # The parent may already name the camera being kept -- it names
            # Kinetix_red -- in which case this is not an edit at all. Saying it
            # was one is how a one-line derivation gets checked as a two-line
            # one, which is exactly what --check caught.
            if stripped != core_camera:
                edits.append(
                    f"changed  {stripped.decode()}  ->  {core_camera.decode()}"
                )
            else:
                edits.append(f"unchanged  {stripped.decode()} (already the kept camera)")
            continue
        out.append(line)

    header = _header(parent, keep, drop, edits, eol)
    return eol.join(header + out), edits


def _header(parent: Path, keep: str, drop: str, edits: list[str], eol: bytes):
    lines = [
        "# DERIVED FILE -- do not edit by hand.",
        f"# Regenerate:  python {Path(__file__).name} --keep {keep}",
        f"# Parent:      {parent.name}",
        "#",
        f"# One camera only: {keep} stays, {drop} is not loaded, so another",
        f"# process -- the Tweez 300 GUI -- can hold {drop} at the same time.",
        "# PVCAM gives a camera to one process at a time; the two Kinetix are",
        "# independent PVCAM devices here, so one owner each is expressible.",
        "#",
        "# Edits against the parent:",
    ]
    lines += [f"#   {e}" for e in edits]
    lines += [
        "#",
        "# BEFORE TRUSTING A SUCCESSFUL LOAD, check two things at the instrument:",
        "#   1. Which physical body did MM open? PVCAM enumerates by index and",
        "#      whether Camera-1 still means the same Kinetix once the other is",
        "#      held elsewhere is untested. Check the serial, not the label.",
        "#   2. Does the trap plane appear on this camera at all? That is optics.",
        "#",
        "# Needs mmcore install first -- every adapter in the lab's MM install",
        "# fails against pymmcore's device API 75 (2026-08-27).",
        "#",
        "# Context: kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md",
        "# section 8, and 2026-08-27-optional-subsystems-one-timeline.md section 8.",
        "",
    ]
    return [line.encode() for line in lines]


def check(parent: Path, derived: bytes, keep: str) -> int:
    """Verify the output is the parent minus exactly the two intended lines."""
    raw = parent.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"

    def payload(data: bytes) -> list[str]:
        return [
            line.strip().decode()
            for line in data.split(eol)
            if line.strip() and not line.strip().startswith(b"#")
        ]

    before, after = payload(raw), payload(derived)
    only_before = [line for line in before if line not in after]
    only_after = [line for line in after if line not in before]

    print(f"parent   {len(before)} setting lines")
    print(f"derived  {len(after)} setting lines")
    print("\nremoved:")
    for line in only_before:
        print(f"   - {line}")
    print("added:")
    for line in only_after:
        print(f"   + {line}")

    # Invariants rather than an enumerated diff: which lines change depends on
    # which camera the parent already names as Core,Camera, and hardcoding that
    # made --keep Kinetix_red report a correct file as UNEXPECTED.
    drop = next(label for label in CAMERAS if label != keep)
    failures = []
    for line in only_before:
        if drop not in line:
            failures.append(f"removed a line that is not about {drop}: {line}")
    for line in only_after:
        if line != f"Property,Core,Camera,{keep}":
            failures.append(f"added an unexpected line: {line}")
    if any(drop in line for line in after):
        failures.append(
            f"{drop} still appears: {[l for l in after if drop in l]}"
        )
    if f"Device,{keep},PVCAM,{CAMERAS[keep]}" not in after:
        failures.append(f"{keep}'s Device line is missing from the result")
    if f"Property,Core,Camera,{keep}" not in after:
        failures.append(f"Core,Camera does not name {keep}")

    print(f"\n{'OK' if not failures else 'UNEXPECTED'}: "
          f"{len(only_before)} removed, {len(only_after)} added")
    for failure in failures:
        print(f"   ! {failure}")
    if failures:
        return 1
    print(f"   every removed line is about {drop}, and {drop} appears nowhere")
    print(f"   {keep} is loaded and is the Core camera")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", required=True, choices=sorted(CAMERAS))
    ap.add_argument("--parent", type=Path, default=PARENT)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--check", action="store_true",
                    help="print the diff against the parent and verify it")
    args = ap.parse_args()

    if not args.parent.exists():
        print(f"no parent config at {args.parent}", file=sys.stderr)
        return 2

    derived, edits = derive(args.parent, args.keep)
    if not any(e.startswith("removed") for e in edits):
        print(f"nothing was removed -- is {args.keep}'s counterpart registered "
              f"in {args.parent.name}? edits: {edits}", file=sys.stderr)
        return 1

    out = args.out or args.parent.with_name(
        f"single_cam_{args.keep.split('_')[-1]}_LUNF.cfg"
    )
    out.write_bytes(derived)
    print(f"wrote {out}")
    for edit in edits:
        print(f"   {edit}")
    if args.check:
        print()
        return check(args.parent, derived, args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
