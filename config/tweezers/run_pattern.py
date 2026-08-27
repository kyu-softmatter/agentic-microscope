"""Generate a .tpf drive pattern from a spec, and optionally run it.

Same staging as config/micromanager/verify_config_control.py: the safe stages
work anywhere, and the one that touches the instrument is a separate flag.

    --plan SPEC     print the timing plan and the TCP commands it implies.
                    Pure computation, runs on the offline PC. Start here.
    --write SPEC    also write the .tpf. Still touches no hardware.
    --run SPEC      microscope PC only: send the command sequence over TCP.
                    Requires the plan to advance, plus typed confirmation.

THE LASER
---------
No stage sends ``LASER_ON``. Arm the laser at the GUI, deliberately, with the
interlocks in front of you -- it is a class 4 source and its power is not even
readable from this repo (dial% -> mW is uncalibrated, deferred 2026-08-19).
``TRAP_ON`` is sent, which only routes an already-on beam to a trap.

**But that is not the same as "this cannot turn the laser on."** A project file
stores "information on the state of the laser operation and beam setting"
(manual p. 65), so ``LOAD_PROJECT`` -- the first command in the sequence
whenever a `project:` is set -- can restore a saved laser-on state. Save the
template with the laser OFF, and treat --run as laser-affecting regardless.

CAMERA ORDERING
---------------
The Tweez GUI takes a Kinetix and releases it, and PVCAM is exclusive -- so do
the camera-bound work (its GUI calibration, visual trap setup) while the GUI
still holds it, release, and only then let Micro-Manager load a configuration
(config/micromanager/verify_config_control.py, microscope.SHARED_DEVICES).
``--run`` itself needs no camera: TCP trap and pattern commands work with the
GUI cameraless (manual p.34).

WHAT --run ASSUMES AND CANNOT CHECK
-----------------------------------
The Tweez 300 TCP interface is write-only: no position, force, or trap-list
query exists (manual pp. 66-69). So unlike the Micro-Manager path, there is no
read-back verification available here at all -- a 0 return means the GUI
accepted the command, not that the trap is where you asked. Watch the GUI.

In particular ``--run`` cannot confirm:
  - that the project template actually carries the wait states the plan needs
    (the plan states the number; check it in the property inspector),
  - that the pattern fits the calibrated trapezoid rather than the rectangle
    ``trapping_range`` records -- points outside are silently clipped,
  - the number of traps in the loop, which scales every time in the plan.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.optical_tweezers import OpticalTweezers, TweezersError  # noqa: E402
from hardware.tweezers_drive import (  # noqa: E402
    blanking_time_note,
    command_sequence,
    load_spec,
    plan,
)
from hardware.tweezers_patterns import PatternError  # noqa: E402


def default_tpf(spec_path: Path) -> Path:
    return spec_path.with_suffix(".tpf")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", metavar="SPEC", help="print the plan, write nothing")
    g.add_argument("--write", metavar="SPEC", help="print the plan and write the .tpf")
    g.add_argument("--run", metavar="SPEC", help="microscope PC: send the commands")
    ap.add_argument("--out", type=Path, default=None, help=".tpf path (default: next to the spec)")
    ap.add_argument("--tpf-on-scope", default=None,
                    help="absolute path the GUI should read the .tpf from; "
                         "required for --run, since TCP paths are absolute")
    ap.add_argument("--decimal", default=".", choices=[".", ","],
                    help="decimal separator, per the lab PC's Windows locale")
    ap.add_argument("--file-first", action="store_true",
                    help="send LOAD_PATTERN with the file argument first -- see "
                         "optical_tweezers.load_pattern on the manual's "
                         "self-contradiction")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2070)
    a = ap.parse_args()

    spec_path = Path(a.plan or a.write or a.run)
    try:
        drive = plan(load_spec(spec_path))
    except PatternError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(drive.report())

    out = a.out or default_tpf(spec_path)
    on_scope = a.tpf_on_scope or str(out)
    print("\n-- TCP commands this plan implies ------------------------")
    for line in command_sequence(drive, on_scope, file_first=a.file_first):
        print(f"   {line}")
    print(f"\n   {blanking_time_note(drive.switching_rate_hz())}")

    if a.plan:
        print("\n   --plan only: nothing written, nothing sent")
        return 0

    written = drive.emitted_pattern().write(out, decimal=a.decimal)
    print(f"\n-- wrote {written}  ({len(drive.emitted_pattern()):,} points) --")
    if a.write:
        print("   --write only: nothing sent. Copy it to the microscope PC and")
        print("   pass --tpf-on-scope with its absolute path there.")
        return 0

    if not drive.advances:
        print("\nREFUSED: the plan does not advance --", file=sys.stderr)
        for blocker in drive.blockers:
            print(f"  - {blocker}", file=sys.stderr)
        return 2

    print(f"\n-- run: {a.host}:{a.port} --")
    if drive.project:
        print("   WARNING: LOAD_PROJECT restores the saved laser and beam state")
        print("   (manual p.65). Confirm the template was saved with the laser OFF.")
    else:
        print("   no LOAD_PROJECT in this sequence; no LASER_ON is sent either.")
    answer = input("   send the commands above? type 'send': ")
    if answer.strip() != "send":
        print("   aborted -- nothing sent")
        return 0

    try:
        with OpticalTweezers(host=a.host, port=a.port) as tweez:
            for line in command_sequence(drive, on_scope, file_first=a.file_first):
                tweez.do(line)
                print(f"   ok  {line}")
    except TweezersError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        print("   check the GUI's Status Pane > TCP/IP Svr log for the status code",
              file=sys.stderr)
        return 1
    print("\n   sent. The interface has no readback -- confirm on the GUI that the")
    print("   pattern is assigned, in range, and traversing at the expected rate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
