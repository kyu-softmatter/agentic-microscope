"""Verify microscope configuration control on the real system, in stages.

Run this on the microscope PC against DMD_dualcam_LUNF.cfg. It walks
docs/07-roadmap.md Phase 5 in order and each stage is a separate flag, so
nothing moves unless you ask for it:

    --read                  5a+5b  load, dump state, diff every preset against
                                   live state. Hardware untouched. Start here.
    --propose GROUP PRESET  5c     write the current state out as a ConfigGroup
                                   preset in a new .cfg. Nothing applied.
    --roundtrip DEV.PROP=VALUE ...
                            5d     apply, hold, then restore the previous
                                   values. Requires typed confirmation.

Everything goes through hardware/microscope.py, so the three write gates apply:
COLLISION_DEVICES (Nosepiece/ZDrive/PFSOffset) need --allow-motion, and
LASER_DEVICES (LUNF-Blanking) need --allow-laser. Both are off by default.

RUN THE TWEEZERS GUI FIRST, AND LET IT RELEASE THE CAMERA
---------------------------------------------------------
**Do this before any stage below, including --read.** The Aresis Tweez 300 GUI
takes one of the two Kinetix bodies, uses it, then releases it -- the same camera
this script initializes -- and PVCAM hands a camera to exactly one process at a
time. So:

    Tweez GUI takes the Kinetix
      -> its GUI calibration (Magnification + Beam Position) + visual trap setup
      -> release the camera
      -> this script
      -> acquire

Backwards, both directions fail and neither says why: with the camera held here
the Tweez GUI gets no live image, which blocks its calibration (Beam Position has
to *see* trapped beads) and all visual trap placement; with the Tweez GUI holding
it, loading below fails on an opaque PVCAM adapter error.
``Microscope.connect()`` catches that one and names the tweezers GUI --
see ``microscope.SHARED_DEVICES``.

The tweezers drive itself survives the release: TCP trap and pattern commands
need no image and the GUI runs cameraless (Tweez300UserManual p.34). Only the
interactive parts are lost.

BEFORE --roundtrip
------------------
- Take the sample off, or know the clearance. The gates stop an accidental
  objective/Z move, not a deliberate one.
- The LUN-F's per-line power is not reachable from here (Nikon does not
  document the FT4222 DAC word format -- hardware/lunf_power.py), so if you do
  drive blanking, the power behind each line is whatever NIS last set. Set the
  lines to 0% in NIS first, or keep the CSU-W1 shutter closed.
- Prior/Queensgate piezo: this script cannot touch it and must not. The
  Dev1/ao2 analog line into that controller is still cabled, and
  microscope.check_config_file() refuses any .cfg that declares it.

WHAT --read CANNOT SETTLE
-------------------------
Whether a preset is *physically* sensible -- that a FilterTurret1 cube passes
the excitation the plan asks for, that the CSU-W1 port matches the camera in
use. Reading back a label only proves the device moved. The committee lenses
own that judgement; this script only proves the control path.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.microscope import Microscope, MicroscopeError, Setting  # noqa: E402

DEFAULT_CFG = REPO / "config" / "micromanager" / "DMD_dualcam_LUNF.cfg"


def parse_assignment(text: str) -> Setting:
    """``Device.Property=Value`` -> Setting. Device labels here contain '-'
    and '_' but no '.', so the first dot splits device from property."""
    target, _, value = text.partition("=")
    if not value:
        raise argparse.ArgumentTypeError(f"{text!r}: expected DEVICE.PROPERTY=VALUE")
    device, dot, prop = target.partition(".")
    if not dot:
        raise argparse.ArgumentTypeError(f"{target!r}: expected DEVICE.PROPERTY")
    return Setting(device, prop, value)


def show_state(scope: Microscope) -> None:
    print("\n-- devices ------------------------------------------------")
    for label, kind in sorted(scope.devices().items()):
        print(f"   {label:28} {kind}")

    print("\n-- state (turrets, wheels, paths, core roles) -------------")
    for label, value in sorted(scope.state().items()):
        print(f"   {label:28} {value}")

    print("\n-- config groups -----------------------------------------")
    for group, presets in sorted(scope.groups().items()):
        current = scope.current_preset(group)
        marker = current if current else "<matches no preset>"
        print(f"   {group:28} current={marker}")
        for preset in presets:
            changes = scope.preset_diff(group, preset)
            moves = [c for c in changes if not c.is_noop]
            if not changes:
                print(f"      {preset:24} (empty preset)")
            elif not moves:
                print(f"      {preset:24} already satisfied")
            else:
                print(f"      {preset:24} would change {len(moves)}/{len(changes)}:")
                for c in moves:
                    print(f"         {c.device}.{c.property}: {c.before!r} -> {c.after!r}")


def propose(scope: Microscope, group: str, preset: str, out_path: Path) -> None:
    """Capture the live state of every state device as a preset (5c).

    State devices only -- the labelled turrets/wheels/paths that make up "a
    configuration". Sweeping every settable property would bake camera
    exposure and adapter internals into the preset, which is not what a
    ConfigGroup is for.
    """
    labels = {
        device: value
        for device, value in scope.state().items()
        if not device.startswith("Core.")
    }
    settings = {device: {"Label": value} for device, value in labels.items()}
    scope.define_preset(group, preset, settings)
    written = scope.save_config(out_path)
    print(f"\n-- 5c: defined {group}/{preset} from live state -----------")
    for device, value in sorted(labels.items()):
        print(f"   {device:28} {value}")
    print(f"\n   wrote {written}")
    print("   nothing was applied -- load this .cfg in Micro-Manager to use it")


def roundtrip(scope: Microscope, settings: list[Setting], dwell: float) -> None:
    print("\n-- 5d: proposed change -----------------------------------")
    for c in scope.diff(settings):
        state = "already correct" if c.is_noop else f"{c.before!r} -> {c.after!r}"
        print(f"   {c.device}.{c.property}: {state}")

    answer = input(f"\n   apply, hold {dwell:.0f}s, then revert? type 'apply': ")
    if answer.strip() != "apply":
        print("   aborted -- nothing written")
        return

    with scope.temporarily(settings):
        print("   applied. reading back:")
        for s in settings:
            print(f"      {s.device}.{s.property} = "
                  f"{scope.core.getProperty(s.device, s.property)!r}")
        time.sleep(dwell)
    print("   reverted. reading back:")
    for s in settings:
        print(f"      {s.device}.{s.property} = "
              f"{scope.core.getProperty(s.device, s.property)!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--read", action="store_true", help="5a+5b, hardware untouched")
    g.add_argument("--propose", nargs=2, metavar=("GROUP", "PRESET"), help="5c")
    g.add_argument(
        "--roundtrip",
        nargs="+",
        type=parse_assignment,
        metavar="DEVICE.PROPERTY=VALUE",
        help="5d, apply then revert",
    )
    ap.add_argument("--cfg", type=Path, default=DEFAULT_CFG)
    ap.add_argument("--mm-dir", type=Path, default=None,
                    help="device-adapter folder (the lab's MM install, which "
                         "has Ti2_Mic_Driver.dll)")
    ap.add_argument("--out", type=Path, default=Path("proposed.cfg"),
                    help="--propose output path")
    ap.add_argument("--dwell", type=float, default=3.0)
    ap.add_argument("--allow-motion", action="store_true",
                    help="permit Nosepiece/ZDrive/PFSOffset -- check clearance")
    ap.add_argument("--allow-laser", action="store_true",
                    help="permit LUNF-Blanking -- lines emit")
    a = ap.parse_args()

    writing = a.roundtrip is not None
    try:
        scope = Microscope.connect(
            a.cfg,
            mm_dir=a.mm_dir,
            allow_write=writing,
            allow_motion=a.allow_motion,
            allow_laser=a.allow_laser,
        )
    except MicroscopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"cfg: {a.cfg}")
    print(f"write: {'ENABLED' if writing else 'disabled (read-only)'}"
          f"   motion: {'allowed' if a.allow_motion else 'gated'}"
          f"   laser: {'allowed' if a.allow_laser else 'gated'}")
    try:
        if a.read:
            show_state(scope)
        elif a.propose:
            propose(scope, a.propose[0], a.propose[1], a.out)
        else:
            roundtrip(scope, a.roundtrip, a.dwell)
    except MicroscopeError as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        scope.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
