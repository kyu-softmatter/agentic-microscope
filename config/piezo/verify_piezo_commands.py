"""Read the NPC-D piezo controller's real command set and signatures.

This is the script that replaces a manual we do not have. The vendor's
"NPC-D-6xx0 NanoMechanism Controller Interface Command Set And Control System"
is not in this repo, but the DLL will report, per command, its description, its
parameters and its results with units -- so the signatures can be read off the
controller instead of looked up.

    --link LINK        comms link: a COM port, an IP address, or "sim:/NPC6330"
                       for the DLL's own simulator. Start with the simulator.
    --unlock LEVEL     raise the security level, which is what decides how many
                       commands *exist*: "user", "super-user", or a raw code
                       like 0xDEC0DED. Prints what became visible.
    --describe FAMILY  full signature of every command in a family
                       (function, snapshot, stage, controller, ...), or "all"
    --out PATH         tee the whole run to a file as well -- "all" at a raised
                       level is far more than a terminal scrollback holds
    --leave-unlocked   do NOT put the security level back on the way out
    --hazard           read the analogue-vs-digital command path settings, i.e.
                       the open question in kb/systems/current.md about whether
                       this controller acts on the Dev1/ao2 cable NIS drives

EVERYTHING HERE IS READ-ONLY
----------------------------
No position is commanded and no playback is started. ``PiezoStage`` is
constructed without ``allow_motion``, so anything that could move the stage
raises instead. Safe with a sample in place.

``--unlock`` is the one write, and it writes a *visibility* setting rather than
anything mechanical. It matters anyway, because **the security level is
controller-side state that outlives the session**: a run that leaves the
controller at super-user hands that level to whatever connects next, the vendor
GUI included. So the level found on the way in is restored on the way out unless
``--leave-unlocked`` says otherwise.

SUPER-USER HAS NEVER BEEN TRIED ON THIS CONTROLLER
--------------------------------------------------
``0xB01DFACE`` comes from the vendor GUI's own config file and nothing more
(``piezo_stage.ACCESS_CODES``); User is the level this repo has confirmed. What
super-user exposes is unknown. The interesting question is whether the families
that answer "Invalid command name" at User level -- ``fpga.*``, ``peek.*``,
``system.*``, which reference/npcd-command-set.md attributes to other models or
to a service interface -- are gated rather than absent. Listing and describing
them is read-only. *Calling* one is not, and nothing here calls anything.

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
    ACCESS_CODES,
    WAVEFORM_PROTOCOL,
    PiezoStage,
    PiezoStageError,
    reference_commands,
)

#: Families worth dumping by default: the waveform generator, triggered capture,
#: and the position/mode part of stage.
INTERESTING = ("function", "snapshot")

#: ``--describe`` argument that means every family the controller reports.
ALL_FAMILIES = "all"


def _level_key(level: str | None) -> str | None:
    """``ACCESS_CODES`` key for a level however it is spelled, or None.

    The controller reports ``User``; the config file writes ``Super User``; this
    script's own flag takes ``super-user``. All three name one level, so they
    are folded to one key rather than compared as strings.
    """
    if not level:
        return None
    key = level.strip().lower().replace(" ", "-").replace("_", "-")
    return key if key in ACCESS_CODES else None


def resolve_code(value: str) -> str:
    """``--unlock`` argument to the code that goes on the wire.

    A level name is a convenience; a raw code passes through untouched, so the
    constant actually sent is always visible in one place or the other. The
    ``0x`` prefix is *not* added for a raw code: the controller parses the code
    as a number and "DEC0DED" fails with "Not enough parameters for command", so
    a caller who drops the prefix should see that failure rather than have it
    silently repaired.
    """
    key = _level_key(value)
    return ACCESS_CODES[key] if key else value.strip()


def raise_level(stage: PiezoStage, code: str) -> None:
    """Unlock, then report what became *visible* -- which is the whole point.

    A level that rose without revealing anything new is a level that did not
    rise, and the failure looks identical either way from the outside: the
    controller answers with a level name, not with a diff. So the diff is taken
    here.
    """
    print("\n-- security level -----------------------------------------")
    before_names = set(c for c in stage.find_commands() if c)
    before = stage.security_level()
    print(f"  before           {before!r}, {len(before_names)} commands visible")
    print(f"  sending          controller.security.user.set {code}")
    after = stage.unlock(code)
    after_names = set(c for c in stage.find_commands() if c)
    print(f"  after            {after!r}, {len(after_names)} commands visible")

    appeared = sorted(after_names - before_names)
    vanished = sorted(before_names - after_names)
    if not appeared:
        print("  *** nothing new became visible. Either the code was rejected, or")
        print("      the level was already this high -- the vendor GUI leaves it")
        print("      raised, so an unlock that changes nothing is the common case.")
    else:
        by_family: dict[str, list[str]] = {}
        for name in appeared:
            by_family.setdefault(name.split(".")[0], []).append(name)
        print(f"\n  {len(appeared)} command(s) appeared, in "
              f"{len(by_family)} family/families:")
        for family, names in sorted(by_family.items()):
            settable = sum(1 for n in names if n.endswith(".set"))
            print(f"\n    {family}.*  x{len(names)}  ({settable} .set)")
            for name in names:
                print(f"      + {name}")
    if vanished:
        print(f"\n  {len(vanished)} command(s) DISAPPEARED, which no reading of the")
        print("  security model predicts -- record this before going further:")
        for name in vanished:
            print(f"      - {name}")


def restore_level(stage: PiezoStage, wanted: str | None) -> None:
    """Put the level back to ``wanted``, because it outlives this session.

    There is no "set level to X" command -- only ``controller.security.user.set``
    with a code, and ``controller.security.lock``. So the way down is to lock and
    climb back, and a level this script has no code for cannot be restored at
    all. That case is reported rather than papered over.
    """
    current = stage.security_level()
    if current == wanted:
        print(f"  security level   {current!r}, unchanged by this run")
        return
    print(f"  security level   {current!r} now, restoring the {wanted!r} it "
          "was found at")
    stage.lock()
    key = _level_key(wanted)
    if key:
        stage.unlock(ACCESS_CODES[key])
    now = stage.security_level()
    print(f"  security level   {now!r}")
    if now != wanted:
        print(f"  *** could not get back to {wanted!r} -- it is {now!r}. This is")
        print("      controller-side state that outlives the session, so raise it")
        print("      by hand if the vendor GUI or another script expects it.")


def all_families(stage: PiezoStage) -> list[str]:
    """Every family the controller currently reports, at the current level."""
    return sorted({c.split(".")[0] for c in stage.find_commands() if c})


class Tee:
    """stdout, duplicated into a file.

    ``--describe all`` at a raised level is thousands of lines, and the machine
    that can produce it is not the machine this repo is edited on -- so the run
    has to leave a file behind rather than a scrollback.
    """

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle

    def write(self, text: str) -> int:
        self._handle.write(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()
        self._handle.flush()


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
    ap.add_argument("--unlock", default=None, metavar="LEVEL",
                    help='raise the security level: "user", "super-user", or a '
                         "raw code like 0xDEC0DED. This is what decides how "
                         "many commands exist")
    ap.add_argument("--describe", action="append", default=None,
                    metavar="FAMILY", help='dump a family\'s signatures '
                                           '(repeatable), or "all"')
    ap.add_argument("--out", default=None, metavar="PATH",
                    help="tee the whole run to this file as well")
    ap.add_argument("--leave-unlocked", action="store_true",
                    help="do not restore the security level on the way out")
    ap.add_argument("--hazard", action="store_true",
                    help="read the analogue/digital command-path settings")
    a = ap.parse_args()

    out_handle = open(a.out, "w", encoding="utf-8") if a.out else None
    real_stdout = sys.stdout
    if out_handle is not None:
        sys.stdout = Tee(real_stdout, out_handle)

    try:
        return _run(a)
    finally:
        sys.stdout = real_stdout
        if out_handle is not None:
            out_handle.close()
            print(f"\n  transcript written to {a.out}")


def _run(a: argparse.Namespace) -> int:
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
    found_level = None
    try:
        show_identity(stage, a.link)
        # Unlock BEFORE the survey, or the survey reports the 188-command view
        # and every later question is asked of a controller that is hiding half
        # its answers.
        found_level = stage.security_level()
        if a.unlock is not None:
            raise_level(stage, resolve_code(a.unlock))
        show_command_set(stage)
        show_units(stage)

        families = list(a.describe or INTERESTING)
        if ALL_FAMILIES in families:
            families = all_families(stage)
        if families:
            print("\n  NOTE the units columns below read '-' throughout. The DLL's"
                  " four unit")
            print("  getters access-violate, so they are not called at all -- see"
                  " piezo_stage")
            print("  .command_parameters(). Units are not knowable from this API.")
        for family in families:
            describe(stage, family)
        if a.hazard:
            show_hazard(stage)
    finally:
        print("\n-- on the way out -----------------------------------------")
        if a.leave_unlocked:
            print(f"  security level   {stage.security_level()!r}, LEFT AS IS "
                  "(--leave-unlocked).")
            print("  It outlives this session: whatever connects next gets it.")
        else:
            try:
                restore_level(stage, found_level)
            except PiezoStageError as exc:
                print(f"  *** could not restore the security level: {exc}")
        stage.disconnect()
        stage.close()

    print(f"\n-- next --------------------------------------------------")
    # This used to say "copy the parameter list into piezo_stage.py". That is
    # done -- WAVEFORM_PROTOCOL was read off the controller on 2026-08-27 -- so
    # the open item moved, and saying so is the point of printing it here.
    print(f"  WAVEFORM_PROTOCOL holds {len(WAVEFORM_PROTOCOL)} signatures, read "
          "off this")
    print("  controller, so upload_waveform() works. What refuses is")
    print("  function_start(): piezo_stage.WAVEFORM_DATA_UNITS is None because the")
    print("  generator does not read its samples in picometres -- a +/-5 um sine")
    print("  uploaded as picometres swung the axis 314 um. The experiment that")
    print("  settles it is config/piezo/settle_waveform_units.py, not this script.")
    print("  For every command at every security level, with descriptions:")
    print("  config/piezo/dump_command_set.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
