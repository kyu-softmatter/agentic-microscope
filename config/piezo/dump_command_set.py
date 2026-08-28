"""Ask the NPC-D controller for its ENTIRE command set, at every level it will grant.

    python config/piezo/dump_command_set.py --link COM4
    python config/piezo/dump_command_set.py --link COM4 --climb user,super-user

GOAL: one run at the microscope PC produces the complete inventory -- every
command name, its description, and its parameter and result names -- at the base
level, at User, and at **super-user, which this repo has never reached**. Written
so that a second trip to the PC is not needed to answer "what else is there".

Counterpart of kb/systems/PyTool_ApiDump.py.reference, which does the same job for
the tweezers' embedded Python. Same design rule: exhaustive by default, every
probe best-effort, and the thing that would cost a return trip -- the level climb
-- automated rather than left as a manual follow-up. The run sheet is
kb/systems/piezo-superuser-RUN-FIRST.md.

WHY A SEPARATE SCRIPT FROM verify_piezo_commands.py
---------------------------------------------------
That one is the interactive tool: pick a family, read its signatures, decide
something. This one is the archival sweep -- it visits levels rather than
families, keeps the *diffs* between them, and writes a file meant to be committed.
The two share hardware/piezo_stage.py and disagree about nothing.

WHAT IT ESTABLISHES, IN ORDER OF WHAT IT WOULD CHANGE
----------------------------------------------------
1. **Does super-user exist, and does 0xB01DFACE reach it?** The code is straight
   out of the vendor GUI's config file and has never been sent
   (piezo_stage.ACCESS_CODES). If it is rejected, that is the finding and §2
   records the controller's exact words.
2. **What does it expose?** The diff, per level, per family. reference/
   npcd-command-set.md attributes `fpga.*`, `peek.*`, `system.*`,
   `stage.command.digital.scaling.*` and `identity.software.fpga.version.get` to
   *other models*, on the evidence that they answer "Invalid command name" here.
   But that is exactly what a gated command answers too -- §2 of
   kb/decisions/2026-08-27-piezo-first-light-measured-limits.md is the whole
   lesson. §4 asks each of those names at every level and separates the two.
3. **Every description this controller will give**, which exists nowhere else:
   the vendor's command-set manual is not in this repo and the DLL is the only
   copy. §3.

SAFETY
------
**Nothing here can move the stage.** ``PiezoStage`` is constructed without
``allow_motion``, so the position setters and ``function_start`` raise. Beyond
that gate, no command is *executed* at all: the sweep only calls the DLL's
introspection entry points (``FindCommands``, ``GetCommandDescription``,
``GetCommandParameterName``, ``GetCommandResultName``), which report what a
command *is*. The four exceptions, all deliberate, all state-free except the
third:

    controller.security.user.get     read the level
    controller.security.user.set     raise it -- changes visibility, not position
    controller.security.lock         drop it, on the way out
    identity.software.version.get    firmware string

Units are never requested. ``GetCommandParameterUnitsType`` and its three
siblings access-violate on this DLL (the buffer length is dereferenced as a
pointer), so ``with_units`` stays False throughout -- see
``piezo_stage.command_parameters``. That is not a gap this script can close.

**The security level outlives the session.** It is controller-side state, and the
vendor GUI leaves it raised. So the level found on the way in is restored on the
way out, and ``--leave-unlocked`` is the only way to skip that.

Every probe is wrapped: a command whose description crashes the DLL must not cost
the other 413. Failures are recorded in place, with the exception text, because a
command that cannot be described is itself a finding.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.piezo_stage import (  # noqa: E402
    ACCESS_CODES,
    PiezoStage,
    PiezoStageError,
    reference_commands,
)

#: Where the dump lands, first writable wins. Mirrors PyTool_ApiDump's habit of
#: not assuming a path exists on a machine this file was not written on.
OUT_CANDIDATES = (
    REPO / "data" / "piezo",
    Path.home(),
)
OUT_STEM = "npcd_command_set"

#: Levels to climb, in order. Named rather than swept: each one is a code being
#: sent to an instrument, and "try everything in ACCESS_CODES" is not a thing to
#: do implicitly.
DEFAULT_CLIMB = ("user", "super-user")

#: Names reference/npcd-command-set.md records as answering "Invalid command
#: name" at User level, and attributes to other NPC-D models or to a service
#: interface. **That inference is unsafe** -- a gated command answers identically
#: -- so every one is re-asked at every level reached. A name that appears only
#: at super-user was gated, not absent, and the reference file needs correcting.
ABSENT_AT_USER = (
    "fpga.version.get",
    "peek.address.get",
    "system.version.get",
    "identity.software.fpga.version.get",
    "stage.command.digital.scaling.gain.get",
    "stage.command.digital.scaling.offset.get",
    "stage.command.analogue.scaling.gain.get",
    "stage.command.analogue.scaling.offset.get",
)

#: Family prefixes to probe wholesale at each level, for the same reason: an
#: empty answer at User and a non-empty one at super-user is the finding.
ABSENT_FAMILIES = ("fpga", "peek", "system", "service", "factory", "debug")


def _safe(fn, *args, **kwargs):
    """Every probe is best-effort. Returns ``(ok, value_or_exception_text)``.

    A DLL that access-violates on one command must not end a sweep that has 400
    more to do -- and the exception text is data, not noise: "Invalid command
    name" and an OSError mean very different things about the same name.
    """
    try:
        return True, fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001  -- an OSError from ctypes counts
        return False, f"{type(exc).__name__}: {exc}"


def rule(title: str) -> str:
    return f"\n{'=' * 78}\n== {title}\n{'=' * 78}"


def inventory(stage) -> tuple[set[str], str | None]:
    """``(visible command names, security level)`` right now."""
    ok, names = _safe(stage.find_commands)
    if not ok:
        print(f"  find_commands FAILED: {names}")
        return set(), None
    ok, level = _safe(stage.security_level)
    return {n for n in names if n}, (level if ok else f"unreadable ({level})")


def by_family(names) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in sorted(names):
        out.setdefault(name.split(".")[0], []).append(name)
    return out


def print_family_table(names) -> None:
    fams = by_family(names)
    print(f"  {len(names)} commands in {len(fams)} families")
    for family, members in sorted(fams.items()):
        settable = sum(1 for n in members if n.endswith(".set"))
        actions = sum(1 for n in members if not n.endswith((".set", ".get")))
        print(f"    {family + '.*':26} {len(members):4}   "
              f"{settable:3} .set   {actions:3} action")


def probe_absent(stage, label: str) -> None:
    """Ask the names and families the reference file calls absent. §4.

    The distinction being drawn: "Invalid command name" from ``describe_command``
    means *not visible at this level*, which is what a gated command and a
    nonexistent one both look like. Only the level climb separates them, which is
    why this runs at every level rather than once.
    """
    print(f"\n-- claimed-absent names, asked at {label} " + "-" * 20)
    for name in ABSENT_AT_USER:
        ok, value = _safe(stage.describe_command, name)
        verdict = "PRESENT" if ok else "absent/gated"
        detail = value if ok else value.split(":", 1)[-1].strip()
        print(f"  {verdict:13} {name:52} {detail}")
    print(f"\n-- claimed-absent families, asked at {label} " + "-" * 17)
    for family in ABSENT_FAMILIES:
        ok, names = _safe(stage.find_commands, family + ".")
        if not ok:
            print(f"  {'FAILED':13} {family + '.*':52} {names}")
            continue
        found = [n for n in names if n]
        print(f"  {'PRESENT' if found else 'empty':13} {family + '.*':52} "
              f"{len(found)} command(s)")
        for name in found:
            print(f"                  + {name}")


def climb(stage, levels, found_level) -> tuple[dict, str | None]:
    """Raise the level once per entry in ``levels``, keeping every diff. §2.

    Returns ``({level_label: name_set}, highest_label_reached)``. A code that is
    rejected, or that reveals nothing, does not stop the climb -- the next level
    may still answer, and the record of what was refused is the point.
    """
    seen = {}
    label = f"as-found ({found_level!r})"
    names, _ = inventory(stage)
    seen[label] = names
    print(rule(f"§2  LEVEL CLIMB -- starting from {found_level!r}"))
    print(f"\n{label}:")
    print_family_table(names)
    probe_absent(stage, label)
    highest = label

    for wanted in levels:
        code = ACCESS_CODES.get(wanted, wanted)
        print(f"\n-- sending controller.security.user.set {code}   "
              f"(for {wanted!r}) " + "-" * 12)
        ok, result = _safe(stage.unlock, code)
        if not ok:
            print(f"  REFUSED: {result}")
            print("  Not fatal, and not necessarily the code: at this point the")
            print("  level may already be higher than the one being asked for.")
            continue
        print(f"  controller reports security = {result!r}")
        names, level = inventory(stage)
        label = f"{wanted} ({result!r})"
        appeared = names - seen[highest]
        vanished = seen[highest] - names
        print(f"\n  {len(names)} visible, {len(appeared)} appeared, "
              f"{len(vanished)} disappeared")
        if not appeared and not vanished:
            print("  *** IDENTICAL to the previous level. Either the code was")
            print("      accepted without raising anything, or this level was")
            print("      already in force. The vendor GUI leaves the level up,")
            print("      so 'already in force' is the common case -- check the")
            print("      as-found level above before concluding the code failed.")
        for title, delta in (("APPEARED", appeared), ("DISAPPEARED", vanished)):
            if not delta:
                continue
            print(f"\n  {title} at {label}:")
            for family, members in sorted(by_family(delta).items()):
                print(f"    {family}.*  x{len(members)}")
                for name in members:
                    print(f"      {'+' if title == 'APPEARED' else '-'} {name}")
        seen[label] = names
        highest = label
        print_family_table(names)
        probe_absent(stage, label)

    return seen, highest


def describe_all(stage, names) -> None:
    """Description + parameter and result names for every command. §3.

    This is the section that exists nowhere else: the vendor's command-set manual
    is not in this repo, and the DLL is the only copy of these strings.

    Units are not requested -- ``with_units=False`` -- because those four getters
    access-violate. So every signature here is names only, and that is the
    ceiling of what this API will give.
    """
    print(rule(f"§3  FULL SIGNATURES -- {len(names)} commands"))
    failures = 0
    for family, members in sorted(by_family(names).items()):
        print(f"\n-- {family}.*  ({len(members)}) " + "-" * 40)
        for name in members:
            print(f"\n  {name}")
            ok, description = _safe(stage.describe_command, name)
            if not ok:
                failures += 1
                print(f"    !! description failed: {description}")
            else:
                print(f"    {description}")
            for kind, getter in (("param", stage.command_parameters),
                                 ("result", stage.command_results)):
                ok, items = _safe(getter, name)
                if not ok:
                    failures += 1
                    print(f"    !! {kind}s failed: {items}")
                    continue
                for item_name, _, _ in items:
                    print(f"    {kind:6} {item_name!r}")
    if failures:
        print(f"\n  {failures} introspection call(s) failed. Each is printed in")
        print("  place above. An OSError is the DLL's string-getter bug; an")
        print("  'Invalid command name' on a name find_commands just returned")
        print("  would be new and worth reporting.")


def cross_check(names) -> None:
    """Diff the sweep against reference/npcd-command-set.md. §5."""
    print(rule("§5  AGAINST reference/npcd-command-set.md"))
    reference = reference_commands()
    print(f"  reference file holds {len(reference)} names")
    print(f"  this run reached     {len(names)}")
    new = sorted(names - reference)
    gone = sorted(reference - names)
    if new:
        print(f"\n  {len(new)} name(s) NOT in the reference file -- add them:")
        for name in new:
            print(f"    + {name}")
    if gone:
        print(f"\n  {len(gone)} name(s) in the reference but not reached here.")
        print("  Expected if this run stopped at a lower level than the one that")
        print("  produced the file; a finding otherwise:")
        for name in gone:
            print(f"    - {name}")
    if not new and not gone:
        print("\n  identical -- the reference file is current for this level.")


def out_path(stem: str) -> Path:
    """First writable candidate directory, so the run survives a missing path."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for directory in OUT_CANDIDATES:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{stem}_{stamp}.txt"
            path.touch()
            return path
        except OSError:
            continue
    raise PiezoStageError(
        f"no writable directory among {[str(d) for d in OUT_CANDIDATES]}"
    )


def sweep(stage, a) -> int:
    print(rule("§0  CONTROLLER"))
    for label, call in (
        ("DLL version", stage.dll_version),
        ("devices", stage.list_devices),
        ("channels", stage.channels),
        ("firmware", stage.identity),
        ("security level", stage.security_level),
    ):
        ok, value = _safe(call)
        print(f"  {label:16} {value!r}" + ("" if ok else "   (FAILED)"))

    ok, found_level = _safe(stage.security_level)
    found_level = found_level if ok else None

    print(rule("§1  WHAT THE REFERENCE FILE EXPECTS"))
    print(f"  reference/npcd-command-set.md: {len(reference_commands())} names,")
    print("  read at User level on 2026-08-27. §5 diffs this run against it.")

    levels = [] if a.no_climb else [s.strip() for s in a.climb.split(",") if s.strip()]
    seen, highest = climb(stage, levels, found_level)
    reached = seen[highest]

    if not a.no_describe:
        describe_all(stage, sorted(reached))
    cross_check(reached)

    print(rule("§6  WHAT TO DO WITH THIS FILE"))
    print("  1. If §2 shows names appearing at super-user, reference/")
    print("     npcd-command-set.md is a User-level snapshot and now says so.")
    print("     Its 'names that do not exist here' paragraph is the part to fix.")
    print("  2. If §4 flips any name from absent/gated to PRESENT, that is a")
    print("     correction to a claim this repo currently states as fact.")
    print("  3. §3 is the only copy of these descriptions outside the DLL.")
    print("     Commit the file; do not summarise it away.")
    print("  4. Still unread even after this run, because they need a *drive*")
    print("     rather than a description: function.trigger-inputs.*,")
    print("     function.trigger-output.*, controller.synchronisation.master/")
    print("     slave -- the plumbing that would start piezo and camera off one")
    print("     edge. And piezo_stage.WAVEFORM_DATA_UNITS, which needs")
    print("     config/piezo/settle_waveform_units.py, not this.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--link", default="sim:/NPC6330",
                    help='COM port, IP, or "sim:/NPC6330" (default)')
    ap.add_argument("--climb", default=",".join(DEFAULT_CLIMB),
                    help="levels to raise to, in order, comma separated. Names "
                         f"from piezo_stage.ACCESS_CODES {sorted(ACCESS_CODES)} "
                         "or raw codes (default: %(default)s)")
    ap.add_argument("--no-climb", action="store_true",
                    help="stay at the level found; sweep that and stop")
    ap.add_argument("--no-describe", action="store_true",
                    help="skip §3, the per-command descriptions (much faster)")
    ap.add_argument("--leave-unlocked", action="store_true",
                    help="do not restore the security level on the way out")
    ap.add_argument("--out", default=None,
                    help="write here instead of an auto-named file")
    a = ap.parse_args()

    try:
        stage = PiezoStage()  # allow_motion stays False: nothing here moves
    except PiezoStageError as exc:
        print(f"FAILED to load the controller DLL: {exc}", file=sys.stderr)
        print("  hardware/piezo/vendor/*.dll are Windows PE binaries -- this "
              "runs on the microscope PC only.", file=sys.stderr)
        return 2

    try:
        stage.connect(a.link)
    except PiezoStageError as exc:
        print(f"could not open {a.link!r}: {exc}", file=sys.stderr)
        print('  the vendor NanoBench GUI holds the port exclusively -- close its',
              file=sys.stderr)
        print('  session first. Or start with --link "sim:/NPC6330".',
              file=sys.stderr)
        stage.close()
        return 2

    # Everything is captured, then written, then echoed. Buffering rather than
    # teeing on purpose: this run is worth nothing if the transcript is lost to a
    # crash three quarters of the way through, and a StringIO survives what a
    # half-flushed file does not.
    buffer = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = buffer
    ok, level_on_entry = _safe(stage.security_level)
    rc = 2
    try:
        rc = sweep(stage, a)
    except Exception:  # noqa: BLE001  -- the transcript matters more than the traceback
        print(rule("SWEEP RAISED -- everything above still stands"))
        print(traceback.format_exc())
        rc = 1
    finally:
        print(rule("ON THE WAY OUT"))
        if a.leave_unlocked:
            print("  security level LEFT AS IS (--leave-unlocked). It outlives")
            print("  this session: whatever connects next inherits it.")
        else:
            print(f"  restoring the level found on entry: {level_on_entry!r}")
            restore_ok, result = _safe(stage.lock)
            if not restore_ok:
                print(f"  lock FAILED: {result}")
            key = (level_on_entry or "").strip().lower().replace(" ", "-")
            if key in ACCESS_CODES:
                _safe(stage.unlock, ACCESS_CODES[key])
            _, now = _safe(stage.security_level)
            print(f"  security level now {now!r}")
            if now != level_on_entry:
                print(f"  *** not back to {level_on_entry!r}. Raise it by hand if")
                print("      the vendor GUI or another script expects it.")
        _safe(stage.disconnect)
        _safe(stage.close)

        sys.stdout = real_stdout
        text = buffer.getvalue()
        try:
            path = Path(a.out) if a.out else out_path(OUT_STEM)
            path.write_text(text, encoding="utf-8")
            written = str(path)
        except (OSError, PiezoStageError) as exc:
            written = f"NOWHERE -- {exc}"
        print(text)
        print(f"\n{'=' * 78}\ntranscript: {written}\n{'=' * 78}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
