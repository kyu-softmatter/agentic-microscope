"""Put the pixel size for a recommended objective into a Micro-Manager `.cfg`.

    python config/micromanager/set_pixel_size.py single_cam_red_noDMD.cfg --objective 40
    python config/micromanager/set_pixel_size.py single_cam_red_noDMD.cfg --objective 40 --write
    python config/micromanager/set_pixel_size.py single_cam_red_noDMD.cfg --audit

**File only. This never opens a device.** It is the half of "make the config
match the recommendation" that is a text edit, deliberately separated from the
half that turns a turret -- the Nosepiece is in
`hardware.microscope.COLLISION_DEVICES` and an objective change swings glass past
a coverslip 0.13 mm away (SAFETY.md). Nothing here moves anything, and it runs on
the offline PC.

WHY IT EXISTS
-------------
The committee recommends an objective. The `.cfg` has to carry a matching
`PixelSize` preset or Micro-Manager answers `getPixelSizeUm()` with 0.0 -- which
is the whole reason `data/pixel_size.yaml` was written, after an agent was asked
for a pixel size at the instrument and had none. The recommendation and the scale
under every distance it implies have to agree, and this is what makes them agree.

WHAT IT REFUSES TO DO
---------------------
Three things, and each is a case where writing something plausible is worse than
writing nothing:

  - **An objective with no row in `data/pixel_size.yaml`.** It will not fall back
    to `p_sensor / M`. That quotient is available to anyone, and putting it in a
    `.cfg` dressed as a calibration is how a computed number acquires a
    provenance it did not earn.
  - **A magnification the `.cfg`'s own Nosepiece does not have.** A preset keyed
    on a label no position carries can never match, so it is dead text that reads
    like coverage.
  - **A preset that already exists and disagrees.** It reports the conflict and
    stops. Silently overwriting is how you lose the one number somebody measured.

THE 1.5x CAVEAT, WHICH THIS TOOL INHERITS
-----------------------------------------
Presets are keyed on the Nosepiece alone, because `IntermediateMagnification`'s
positions are named nowhere in the `.cfg`. So they are right at intermediate 1x
and high by exactly 1.5x at 1.5x. `--intermediate` writes the other column's
numbers, but it cannot key on the device, so **writing both is not possible and
would not help** -- two presets on the same Nosepiece label would be the same
preset. `python -m calibration.cli intermediate-mag <cfg>` reads the turret at
the instrument and emits the two-property form that fixes this properly.

WHY GENERATE RATHER THAN HAND-EDIT
----------------------------------
Same reason as `make_single_cam_cfg.py`: this file gets loaded against real
hardware, and a hand-edited config is one nobody can re-derive after the table
changes. Dry run by default; `--write` is the switch. Line endings are read from
the file and preserved -- this repo lives in a Box sync folder edited from both
Windows and macOS.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hardware.microscope import _objective_mag_from_label  # noqa: E402
from optics.components import recorded_pixel_um  # noqa: E402

HERE = Path(__file__).resolve().parent


def read_cfg(path: Path) -> tuple[list[str], str]:
    """Split into lines and report the ending to write back with.

    **Splits on either ending, not on whichever one it guessed.** A working copy
    in this repo can genuinely be mixed -- it lives in a Box sync folder edited
    from Windows and macOS, `core.autocrlf` is on, and appending to it from a
    POSIX shell leaves LF lines in a CRLF checkout. Splitting on the majority
    ending then swallows the whole minority block into one giant "line", which
    is not theoretical: it made `--audit` report 0 presets against 6 that were
    there.

    The ending returned for writing is the majority one, so a clean file stays
    clean and a mixed one is normalised on the next write rather than made worse.
    """
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    eol = "\r\n" if crlf >= (raw.count(b"\n") - crlf) and crlf else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text.split("\n"), eol


def nosepiece_labels(lines: list[str]) -> dict[float, str]:
    """Objective magnification -> the exact Nosepiece label string."""
    out: dict[float, str] = {}
    for line in lines:
        if not line.startswith("Label,Nosepiece,"):
            continue
        label = line.split(",", 3)[3]
        mag = _objective_mag_from_label(label)
        if mag is not None:
            out[mag] = label
    return out


def existing_presets(lines: list[str]) -> dict[str, tuple[str | None, float | None]]:
    """Preset name -> (the Nosepiece label it keys on, its pixel size)."""
    out: dict[str, tuple[str | None, float | None]] = {}
    for line in lines:
        if line.startswith("ConfigPixelSize,") and ",Nosepiece,Label," in line:
            name = line.split(",")[1]
            label = line.split(",Label,", 1)[1]
            out[name] = (label, out.get(name, (None, None))[1])
        elif line.startswith("PixelSize_um,"):
            parts = line.split(",")
            name = parts[1]
            um = float(parts[2].split("#")[0])
            out[name] = (out.get(name, (None, None))[0], um)
    return out


def plan(path: Path, mag: float, intermediate: float) -> tuple[list[str], list[str]]:
    """Return ``(lines_to_add, problems)``. Non-empty problems means: do not write."""
    lines, _ = read_cfg(path)
    problems: list[str] = []

    hit = recorded_pixel_um(mag, intermediate)
    if hit is None:
        problems.append(
            f"data/pixel_size.yaml has no row for {mag:g}x x {intermediate:g}x. "
            "Refusing to substitute p_sensor/M -- a computed number written into "
            "a .cfg reads as a calibration to everything downstream."
        )
        return [], problems
    um, evidence = hit

    labels = nosepiece_labels(lines)
    if mag not in labels:
        have = ", ".join(f"{m:g}x" for m in sorted(labels)) or "none"
        problems.append(
            f"{path.name}'s Nosepiece has no {mag:g}x position (it has: {have}). "
            "A preset keyed on a label no position carries can never match."
        )
        return [], problems
    label = labels[mag]

    name = f"{mag:g}x-{intermediate:g}x"
    for existing_name, (existing_label, existing_um) in existing_presets(lines).items():
        if existing_label != label:
            continue
        if existing_um is not None and abs(existing_um - um) > 1e-9:
            problems.append(
                f"preset {existing_name!r} already covers {label!r} at "
                f"{existing_um} um/px, and the table says {um}. Not overwriting -- "
                "one of the two is wrong and this tool cannot tell which."
            )
        else:
            problems.append(
                f"preset {existing_name!r} already covers {label!r} at {um} um/px. "
                "Nothing to do."
            )
        return [], problems

    return (
        [
            f"ConfigPixelSize,{name},Nosepiece,Label,{label}",
            f"PixelSize_um,{name},{um}",
        ],
        [],
    )


def apply(path: Path, additions: list[str]) -> None:
    """Append below the file's own ``# PixelSize settings`` header."""
    lines, eol = read_cfg(path)
    marker = "# PixelSize settings"
    if marker in lines:
        # After the header and any block already sitting under it.
        at = len(lines)
        for i in range(lines.index(marker) + 1, len(lines)):
            if lines[i].strip() and not lines[i].startswith(("#", "ConfigPixelSize,", "PixelSize_um,")):
                at = i
                break
        else:
            at = len(lines)
        lines[at:at] = additions
    else:
        lines += ["", marker, *additions]
    path.write_bytes(eol.join(lines).encode("utf-8"))


def audit(path: Path, intermediate: float) -> int:
    """Every Nosepiece position, and whether the .cfg can name its pixel size."""
    lines, _ = read_cfg(path)
    labels = nosepiece_labels(lines)
    presets = existing_presets(lines)
    covered = {label: um for label, um in presets.values() if label}

    print(f"{path.name}: {len(labels)} objectives, {len(presets)} pixel-size presets")
    missing = 0
    for mag in sorted(labels):
        label = labels[mag]
        hit = recorded_pixel_um(mag, intermediate)
        table = f"{hit[0]} ({hit[1]})" if hit else "not in data/pixel_size.yaml"
        if label in covered:
            mark = "ok " if hit and abs(covered[label] - hit[0]) < 1e-9 else "DIFF"
            print(f"  {mark} {mag:>4g}x  cfg {covered[label]:<9} table {table}")
            if mark == "DIFF":
                missing += 1
        else:
            missing += 1
            print(f"  --  {mag:>4g}x  cfg (none)   table {table}")
    if missing:
        print(f"\n{missing} position(s) MM cannot name a pixel size for, or disagrees on.")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("config", help=".cfg filename (in this folder) or a full path")
    p.add_argument("--objective", type=float, help="recommended objective magnification, e.g. 40")
    p.add_argument(
        "--intermediate", type=float, default=1.0,
        help="intermediate magnification the preset is for (default 1.0; see the module docstring "
             "-- presets cannot key on this device yet, so 1.0 is the only honest value today)",
    )
    p.add_argument("--audit", action="store_true", help="report coverage for every objective, write nothing")
    p.add_argument("--write", action="store_true", help="actually modify the file (default: dry run)")
    args = p.parse_args(argv)

    path = Path(args.config)
    if not path.exists():
        path = HERE / args.config
    if not path.exists():
        print(f"no such config: {args.config}", file=sys.stderr)
        return 2

    if args.audit:
        return audit(path, args.intermediate)

    if args.objective is None:
        print("--objective is required (or use --audit)", file=sys.stderr)
        return 2

    additions, problems = plan(path, args.objective, args.intermediate)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if args.intermediate != 1.0:
        print(
            f"NOTE: writing the {args.intermediate:g}x column, but the preset still keys on the "
            "Nosepiece alone -- MM will apply it at every intermediate setting. See the module "
            "docstring, and calibration.cli intermediate-mag."
        )

    print(f"would add to {path.name}:" if not args.write else f"added to {path.name}:")
    for line in additions:
        print(f"  {line}")
    if args.write:
        apply(path, additions)
    else:
        print("\n(dry run -- pass --write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
