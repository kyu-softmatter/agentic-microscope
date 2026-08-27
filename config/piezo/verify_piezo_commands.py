"""Read the NPC-D piezo controller's real command set and signatures.

This is the script that replaces a manual we do not have. The vendor's
"NPC-D-6xx0 NanoMechanism Controller Interface Command Set And Control System"
is not in this repo, but the DLL will report, per command, its description, its
parameters and its results with units -- so the signatures can be read off the
controller instead of looked up.

    --link LINK        comms link: a COM port, an IP address, or "sim:/NPC6330"
                       for the DLL's own simulator. Start with the simulator.
    --describe FAMILY  full signature of every command in a family
                       (function, snapshot, stage, controller, ...)
    --hazard           read the analogue-vs-digital command path settings, i.e.
                       the open question in kb/systems/current.md about whether
                       this controller acts on the Dev1/ao2 cable NIS drives

EVERYTHING HERE IS READ-ONLY
----------------------------
No position is commanded and no playback is started. ``PiezoStage`` is
constructed without ``allow_motion``, so anything that could move the stage
raises instead. Safe with a sample in place.

WHAT IT IS FOR
--------------
Three questions, in order of how much they change:

1. **Does this controller have the waveform generator?** The `function.*` family
   is documented as "For NPC-D-6000 controllers" only, and the command list in
   reference/npcd-command-set.md was extracted from a DLL that serves the whole
   family -- so it is a superset and a hypothesis. `--describe function` settles
   it, and its parameter list is what `WAVEFORM_PROTOCOL` needs.
2. **What are the position units?** Library manual 5.2 says a distance may be
   picometres for a linear stage or picoradians for an angular one, and that
   applications should always check. `piezo_stage.get_position_pm()` assumes
   picometres.
3. **Which command input is the controller acting on?** `--hazard`. The analogue
   cable from `Dev1/ao2` is still physically connected; this repo drives the
   digital path instead and deliberately keeps `NIDAQAO-Dev1/ao2` out of every
   Micro-Manager configuration (microscope.check_config_file refuses one that
   declares it). `stage.mode.get` is the query that has been outstanding since
   2026-08-19. Note there is no `stage.mode.set`: readable, not changeable here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.piezo_stage import (  # noqa: E402
    WAVEFORM_PROTOCOL,
    PiezoStage,
    PiezoStageError,
    reference_commands,
)

#: Families worth dumping by default: the waveform generator, triggered capture,
#: and the position/mode part of stage.
INTERESTING = ("function", "snapshot")


def show_identity(stage: PiezoStage, link: str) -> None:
    print(f"  DLL version    {stage.dll_version()}")
    print(f"  devices        {stage.list_devices()}")
    print(f"  connected to   {link}   (open={stage.is_connected()})")
    print(f"  channels       {stage.channels()}")
    print(f"  firmware       {stage.identity()}")
    print(f"  security level {stage.security_level()}")


def show_command_set(stage: PiezoStage) -> None:
    supported, reference_only, controller_only = stage.verify_command_set()
    reference = reference_commands()
    print(f"\n-- command set --------------------------------------------")
    print(f"  controller reports   {len(supported)} commands")
    print(f"  extracted reference  {len(reference)} (family-wide superset)")

    fams: dict[str, int] = {}
    for name in supported:
        fams[name.split(".")[0]] = fams.get(name.split(".")[0], 0) + 1
    print("  by family:           " + ", ".join(
        f"{f}={n}" for f, n in sorted(fams.items())
    ))

    have_function = [c for c in supported if c.startswith("function.")]
    print(f"\n  waveform generator:  "
          f"{'PRESENT' if have_function else 'ABSENT'}"
          f"  ({len(have_function)} function.* commands)")
    if not have_function:
        print("    -> this controller is NOT an NPC-D-6000-class waveform host.")
        print("       Piezo trajectories would have to be host-driven, which "
              "makes their timing")
        print("       as soft as the tweezers' TCP path. Say so in the KB before "
              "planning on it.")

    if controller_only:
        print(f"\n  in the controller but NOT in the extracted reference "
              f"({len(controller_only)}) -- the extraction missed these:")
        for name in controller_only:
            print(f"    + {name}")
    if reference_only:
        print(f"\n  in the reference but not on this controller "
              f"({len(reference_only)}) -- expected: other models' commands")
        by_family: dict[str, list[str]] = {}
        for name in reference_only:
            by_family.setdefault(name.split(".")[0], []).append(name)
        for family, names in sorted(by_family.items()):
            print(f"    - {family}.* x{len(names)}")


def describe(stage: PiezoStage, family: str) -> None:
    print(f"\n-- {family}.* signatures ----------------------------------")
    described = stage.describe_family(family + ".")
    if not described:
        print(f"  no commands start with {family!r} on this controller")
        return
    for name, info in sorted(described.items()):
        print(f"\n  {name}")
        print(f"    {info['description']}")
        for label, items in (("param", info["parameters"]), ("result", info["results"])):
            for pname, units_type, units in items:
                print(f"    {label:6} {pname!r:24} {units_type or '-':12} {units or '-'}")


def show_hazard(stage: PiezoStage) -> None:
    print("\n-- command path (the outstanding KB question) --------------")
    print("  kb/systems/current.md > devices_not_in_mm_config > piezo stage:")
    print("  the Dev1/ao2 analogue cable is still connected, and whether this")
    print("  controller acts on it depends on the mode below.\n")
    for channel in range(1, stage.channels() + 1):
        try:
            print(f"  channel {channel} stage.mode.get      -> {stage.stage_mode(channel)}")
        except PiezoStageError as exc:
            print(f"  channel {channel} stage.mode.get      -> failed: {exc}")
    for command in (
        "stage.command.analogue.scaling.gain.get",
        "stage.command.analogue.scaling.offset.get",
        "stage.command.digital.scaling.gain.get",
        "stage.command.digital.scaling.offset.get",
    ):
        try:
            print(f"  {command:46} -> {stage.do_command(command + ' 1')}")
        except PiezoStageError as exc:
            print(f"  {command:46} -> failed: {exc}")
    print("\n  Two independent scalings confirm two command paths. Whatever the")
    print("  mode says, keep NIDAQAO-Dev1/ao2 out of every MM configuration:")
    print("  MM writes 0 V on initialize, which on the analogue path is 0 um.")


def show_units(stage: PiezoStage) -> None:
    print("\n-- position units (do not assume picometres) --------------")
    for command in ("stage.position.measured.get", "stage.position.command.get"):
        try:
            print(f"  {command:34} results {stage.position_units(command)}")
        except PiezoStageError as exc:
            print(f"  {command:34} failed: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", default="sim:/NPC6330",
                    help='COM port, IP, or "sim:/NPC6330" (default)')
    ap.add_argument("--describe", action="append", default=None,
                    metavar="FAMILY", help="dump a family's signatures (repeatable)")
    ap.add_argument("--hazard", action="store_true",
                    help="read the analogue/digital command-path settings")
    a = ap.parse_args()

    try:
        stage = PiezoStage()  # allow_motion stays False: nothing here moves
    except PiezoStageError as exc:
        print(f"FAILED to load the controller DLL: {exc}", file=sys.stderr)
        print("  The DLLs in hardware/piezo/vendor/ are Windows PE binaries -- "
              "this runs on the microscope PC only.", file=sys.stderr)
        return 2

    print(f"-- controller ---------------------------------------------")
    try:
        stage.connect(a.link)
    except PiezoStageError as exc:
        print(f"  could not open {a.link!r}: {exc}", file=sys.stderr)
        stage.close()
        return 2
    try:
        show_identity(stage, a.link)
        show_command_set(stage)
        show_units(stage)
        for family in a.describe or INTERESTING:
            describe(stage, family)
        if a.hazard:
            show_hazard(stage)
    finally:
        stage.disconnect()
        stage.close()

    print(f"\n-- next --------------------------------------------------")
    print(f"  WAVEFORM_PROTOCOL is currently {WAVEFORM_PROTOCOL!r}; "
          "upload_waveform() refuses while it is None.")
    print("  Copy the function.waveform.data.set parameter list above into")
    print("  hardware/piezo_stage.py, then the upload path is a few lines.")
    print("  Build the samples with hardware/piezo_waveform.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
