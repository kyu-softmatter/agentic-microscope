r"""The two-colour dual-camera hardware configuration, as a declarative state.

    python config/session/dualcam_hardware_config.py --read     # 5a+5b, nothing moves
    python config/session/dualcam_hardware_config.py --apply    # 5d, every write read back
    python config/session/dualcam_hardware_config.py --apply --save-cfg OUT.cfg

WHY THIS EXISTS ALONGSIDE setup_dualcam_run.py
----------------------------------------------
`setup_dualcam_run.py` is imperative: it checks things, writes things, and can
measure the splitter. Useful, but its writes are hand-rolled `setProperty`
calls that trust the device moved.

This file is the same state expressed DECLARATIVELY and pushed through
`hardware/microscope.Microscope`, which is the repository's sanctioned
configuration surface (docs/07 Phase 5). Three things come with that and none
are available to a hand-rolled write:

  · every write is READ BACK and raises on mismatch, rather than trusting a
    device that accepted a command (the same principle SAFETY.md §0 states for
    the tweezers, where a return code of 0 means only "the GUI accepted it")
  · `diff()` shows what WOULD change before anything does, no-ops included, so
    "already correct" is distinguishable from "could not tell"
  · the three write gates are enforced by the module, not by my remembering:
    COLLISION_DEVICES (Nosepiece/ZDrive/PFSOffset) need allow_motion,
    LASER_DEVICES (LUNF-Blanking) need allow_laser. THIS SCRIPT PASSES NEITHER,
    so the objective cannot be moved from here and no laser line can be opened
    from here, whatever is asked of it.

WHAT IS IN THE STATE, AND WHY EACH ENTRY
----------------------------------------
Only property-settable devices. ROI, binning, exposure and the circular buffer
are NOT device properties and cannot live in a ConfigGroup -- they stay in
`setup_dualcam_run.match_cameras`.

    LappMainBranch1        mirror_out   ⚠ THE ENTRY MOST WORTH READING. This is
                           the position in which the Aura REACHES THE SAMPLE.
                           kb/systems/current.md carried the opposite for a
                           month, in three places, from a dictation rather than
                           a measurement; setting the branch from the wrong
                           record turned the light off and cost the 2026-09-04
                           session, which then blamed the unreadable splitter.
                           Measured 2026-09-04 and again 2026-09-06: mirror_out
                           +8.83 ADU median rise, mirror_in -0.42, i.e. nothing.
    CSUW1-Port             blue_red     both cameras fed; red_only starves blue
    CSUW1-Bright           Bright Field disk bypassed, widefield epi
    CSUW1-Dichroic         on           the Di01-T quad dichroic, in path
    CSUW1-Filter_Blue      488          FF01-515/30, 500-530 nm -> Dragon Green
    CSUW1-Filter_Red       555          FF01-595/31, 579.5-610.5 nm -> the red
                                        bead, MEASURED 2026-09-06 as 5.8x
                                        better than FF01-680/42
    LightPath              4-L100       the port the CSU-W1 and cameras are on
    Turret1Shutter         1            in series with Turret2Shutter
    Turret2Shutter         1            in series; also the 1064 nm trap path
    Kinetix_blue/red Port  Dynamic Range   16-bit, 15,000 e- full well. Found in
                                        DIFFERENT modes on 2026-09-06 (blue in
                                        Sensitivity/12-bit), which would have
                                        put the two channels on different
                                        conversion gains and full wells.
    PP * ENABLED           No           despeckle off on BOTH bodies. Ordered
                                        LAST on purpose -- see below.

ORDER IS LOAD-BEARING AND `apply()` PRESERVES IT
------------------------------------------------
`Microscope.apply` writes in the order given and does not sort, because turret
and shutter sequencing matters and the module has no model of which order is
safe. Two orderings here are not stylistic:

  1. Each camera's `Port` comes BEFORE its post-processing entries. A Port
     change RESETS post-processing to enabled -- measured 2026-09-06, when
     disabling PP first left Kinetix_blue's six entries back at Yes after its
     mode moved. Post-processing is the last thing written to a camera.
  2. The light path and wheels come before the shutters. Nothing here closes
     Turret2Shutter, per SAFETY.md §8 ("Never close Turret2Shutter to tidy
     up") -- it is also the 1064 path and a trap may depend on it.

NOT IN HERE, DELIBERATELY
-------------------------
    Nosepiece      the objective is changed AT THE STAND (SAFETY.md §2). This
                   script VERIFIES it and refuses to proceed on a mismatch, and
                   it does not pass allow_motion, so it could not write it even
                   if the state listed it.
    Splitter       not an MM device at all. Manual, unreadable, and the one
                   element that has to be confirmed by eye or by
                   `setup_dualcam_run.py --verify-splitter`.
    FilterTurret2  not settable here either; position 0 holds the OT dichroic +
                   750/SP whose label does not name it.
    LUNF-Blanking  the confocal lasers stay at the LaserLine `AllOff` preset.
                   This is the widefield Aura path; opening a LUN-F line would
                   need allow_laser, which this script does not pass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.microscope import Microscope, MicroscopeError  # noqa: E402

DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_noDMD.cfg"

EXPECTED_OBJECTIVE = "6-Plan Apo LmbdD0.13 100x Oil"

CAMERAS = ("Kinetix_blue", "Kinetix_red")
READOUT_PORT = "Dynamic Range"

#: The configuration, in application order. See the module docstring on why the
#: order is not cosmetic.
def wanted_state(cameras=CAMERAS, port: str = READOUT_PORT) -> list[tuple[str, str, str]]:
    state: list[tuple[str, str, str]] = [
        # Light path first: get photons to the sample and to the right port.
        ("LappMainBranch1", "Label", "mirror_out"),
        ("LightPath", "Label", "4-L100"),
        ("CSUW1-Bright", "BrightFieldPort", "Bright Field"),
        ("CSUW1-Dichroic", "Label", "on"),
        ("CSUW1-Port", "Label", "blue_red"),
        # Then each arm's emission filter.
        ("CSUW1-Filter_Blue", "Label", "488"),
        ("CSUW1-Filter_Red", "Label", "555"),
    ]
    # Then the cameras: Port before post-processing, because Port resets it.
    for cam in cameras:
        state.append((cam, "Port", port))
    # Shutters open after the path is set.
    state += [
        ("Turret1Shutter", "State", "1"),
        ("Turret2Shutter", "State", "1"),
    ]
    return state


def pp_settings(scope: Microscope, cameras=CAMERAS) -> list[tuple[str, str, str]]:
    """Every post-processing ENABLED entry on both bodies, set to off.

    Discovered rather than hard-coded: the entries are named `PP  1   ENABLED`
    with adapter-dependent spacing, and which indices exist depends on the
    camera. `startswith("PP")` and not `"ENABLED" in name`, because the loose
    test also matches `CircularBufferEnabled` -- which is the acquisition
    buffer, has nothing to do with post-processing, and got switched off by
    exactly that mistake on 2026-09-06.
    """
    out: list[tuple[str, str, str]] = []
    for cam in cameras:
        for name in scope.core.getDevicePropertyNames(cam):
            if not name.startswith("PP") or "ENABLED" not in name.upper():
                continue
            allowed = list(scope.core.getAllowedPropertyValues(cam, name)) or ["No"]
            off = next((v for v in allowed
                        if str(v).strip().lower() in {"no", "0", "false", "off"}), "No")
            out.append((cam, name, str(off)))
    return out


def check_objective(scope: Microscope, expected: str) -> str | None:
    try:
        actual = str(scope.core.getStateLabel("Nosepiece"))
    except Exception as exc:
        return f"Nosepiece unreadable ({exc})"
    if actual == expected:
        return None
    return (
        f"Nosepiece = {actual!r}, expected {expected!r}. Change it AT THE STAND "
        f"or in NIS (SAFETY.md §2): the Ti2 runs no objective escape on an MM "
        f"nosepiece write, so whatever Z the outgoing lens sat at is where the "
        f"incoming one arrives, and the 100x Oil has 130 um of working distance "
        f"to absorb it. This script does not pass allow_motion and will not "
        f"write the Nosepiece. Note also that an objective change silently "
        f"invalidates BOTH tweezers calibrations, neither readable over TCP."
    )


def write_preset_cfg(parent: str | Path, out_path: str | Path, group: str,
                     preset: str, state) -> Path:
    """Copy `parent` and append `state` as a ConfigGroup preset, as text.

    ⚠ NOT `Microscope.save_config` / `CMMCorePlus.saveSystemConfiguration`.
    That call HANGS on this system -- measured 2026-09-06, never returned in
    75 s with a one-setting group defined, while `defineConfigGroup` and
    `defineConfig` both return instantly. It is what made the first two
    --apply runs look like an apply failure when the apply had in fact already
    finished; the process was stuck in the saver afterwards, and because stdout
    was a pipe (block-buffered, not line-buffered) the completed output was
    still in the buffer and was lost when the run was killed. Two lessons, both
    cheap: run these with `python -u`, and do not conclude anything about WHERE
    a process hung from output that a kill may have swallowed.

    Appending text is also better than the saver would have been even if it
    worked: `saveSystemConfiguration` regenerates the whole file from the
    core's state, which would silently drop the parent's comment header --
    and on this repo's .cfg files that header is where the derivation, the
    removed DMD line and the reasoning live.
    """
    parent, out = Path(parent), Path(out_path)
    # Preserve the parent's line endings. MM writes these files CRLF on
    # Windows, and emitting LF makes every one of the 237 inherited lines show
    # up as changed in a diff against the parent -- which destroys the one
    # cheap check that this file is its parent plus a preset.
    raw = parent.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    body = raw.decode("utf-8").replace("\r\n", "\n").rstrip("\n")
    lines = [
        body,
        "",
        "# " + "=" * 70,
        f"# ConfigGroup {group}/{preset} -- appended by",
        f"# config/session/dualcam_hardware_config.py, verified against the",
        "# instrument at the time of writing (every value below was applied and",
        "# read back, not just declared).",
        "#",
        "# Apply with setConfig(group, preset). What it restores and what it",
        "# cannot: these are all DEVICE PROPERTIES, so binning, ROI, exposure and",
        "# the circular-buffer footprint are NOT here -- they are not properties",
        "# and do not survive a config load either. Set those per session.",
        "#",
        "# The entry most worth understanding is LappMainBranch1 = mirror_out:",
        "# that is the position in which the Aura reaches the sample. The kb",
        "# carried the reverse for a month in three places, and setting the branch",
        "# from that record turned the light off and cost the 2026-09-04 session.",
        "# " + "=" * 70,
    ]
    for device, prop, value in state:
        lines.append(f"ConfigGroup,{group},{preset},{device},{prop},{value}")
    out.write_bytes((eol.join(lines) + eol).encode("utf-8"))
    return out


def show(changes, title: str) -> int:
    print(f"\n{title}")
    n = 0
    for c in changes:
        if c.is_noop:   # a property on Change, not a method
            print(f"   ok      {c.device}.{c.property} = {c.after!r}")
        else:
            n += 1
            print(f"   CHANGE  {c.device}.{c.property}: {c.before!r} -> {c.after!r}")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--mm-dir", default=None,
                   help="device-adapter folder (the lab's MM install, which has "
                        "Ti2_Mic_Driver.dll)")
    p.add_argument("--objective", default=EXPECTED_OBJECTIVE)
    p.add_argument("--port", default=READOUT_PORT, help="readout mode for BOTH cameras")
    p.add_argument("--read", action="store_true", help="5a+5b: diff only, nothing moves")
    p.add_argument("--apply", action="store_true", help="5d: apply, each write read back")
    p.add_argument("--save-cfg", default=None,
                   help="also define a TwoColour/GreenRed-Widefield preset and "
                        "write the whole configuration to this .cfg")
    p.add_argument("--group", default="TwoColour")
    p.add_argument("--preset", default="GreenRed-Widefield")
    p.add_argument("--write-all", action="store_true",
                   help="write every setting including ones already correct. "
                        "Slow and it rewrites camera Port -- see the note in main()")
    p.add_argument("--skip-objective-check", action="store_true",
                   help="proceed with a different objective in place; the state "
                        "below is objective-independent, but the run is not")
    args = p.parse_args(argv)

    if not (args.read or args.apply):
        p.error("pass --read (safe) or --apply")

    # allow_motion and allow_laser are deliberately NOT passed. See the docstring.
    try:
        scope = Microscope.connect(args.cfg, allow_write=bool(args.apply), mm_dir=args.mm_dir)
    except MicroscopeError as exc:
        print(f"could not load {args.cfg}:\n{exc}", file=sys.stderr)
        return 1

    with scope:
        print(f"loaded {args.cfg}")
        print(f"write gates: allow_write={scope.allow_write} "
              f"allow_motion={scope.allow_motion} allow_laser={scope.allow_laser}")

        state = wanted_state(port=args.port) + pp_settings(scope)

        problem = check_objective(scope, args.objective)
        if problem:
            print(f"\n[objective] {problem}")

        n = show(scope.diff(state), "-- diff: what this state would change --")
        print(f"\n   {n} of {len(state)} settings differ from the instrument")

        if not args.apply:
            print("\n--read: nothing was written.")
            return 0 if (n == 0 and not problem) else 1

        if problem and not args.skip_objective_check:
            print("\nREFUSED. The objective is not the one this run expects. "
                  "Change it at the stand, or pass --skip-objective-check if you "
                  "are deliberately configuring the path before the objective.")
            return 1

        # Apply ONLY what differs, unless asked otherwise.
        #
        # `Microscope.apply` writes every setting it is handed, no-ops included,
        # and that is correct for a preset -- setConfig semantics are "make it
        # so", and a device you believe is right may not be. But writing a
        # camera's `Port` to the value it already holds triggers a real readout-
        # mode change, and on 2026-09-06 that spun for 500 s of CPU inside
        # waitForDevice with both bodies held, on a list whose 11 path settings
        # were ALL already correct. Rewriting correct hardware is also how a
        # Port write resets post-processing for no reason.
        #
        # So the default is: touch what is wrong, leave what is right, and say
        # which. `--write-all` restores the make-it-so behaviour for when the
        # readback itself is what you want to prove.
        if args.write_all:
            to_write = state
        else:
            differing = {(c.device, c.property) for c in scope.diff(state) if not c.is_noop}
            to_write = [s for s in state if (s[0], s[1]) in differing]
            skipped = len(state) - len(to_write)
            print(f"\napplying {len(to_write)} differing settings, "
                  f"leaving {skipped} already-correct ones untouched "
                  f"(--write-all to write all {len(state)})")
        if not to_write:
            print("   nothing to write.")
        try:
            applied = scope.apply(to_write)
        except Exception as exc:
            done = getattr(exc, "applied", ())
            print(f"\nAPPLY FAILED after {len(done)} settings: {exc}", file=sys.stderr)
            print("Already-applied changes, for rollback:", file=sys.stderr)
            for c in done:
                print(f"   {c.device}.{c.property}: {c.before!r} -> {c.after!r}", file=sys.stderr)
            return 1

        moved = show(applied, "-- applied (each value read back and confirmed) --")
        print(f"\n   {moved} settings moved, {len(applied) - moved} were already correct")

        left = show(scope.diff(state), "-- re-diff after applying --")
        if left:
            print(f"\n⚠ {left} settings STILL differ after a successful apply. Every "
                  f"write above was read back, so this means something changed them "
                  f"afterwards -- the usual cause is a Port write resetting a "
                  f"camera's post-processing.")
            return 1
        print("\n   clean: the instrument matches the declared state")

        if args.save_cfg:
            out = write_preset_cfg(args.cfg, args.save_cfg, args.group, args.preset, state)
            print(f"\ndefined {args.group}/{args.preset} ({len(state)} settings)")
            print(f"wrote {out}")
            print(f"  Load it and call setConfig('{args.group}', '{args.preset}') to "
                  f"restore this state in one call -- the only part of the setup that\n"
                  f"  survives a config load. Binning, ROI, exposure and the circular "
                  f"buffer are not device properties and must still be set per\n"
                  f"  session (setup_dualcam_run.match_cameras).")

    print("\nstill outside software, and unchanged by this script:")
    print("  · the objective, at the stand (SAFETY.md §2)")
    print("  · the splitter to position 1 — unreadable; confirm by eye or with")
    print("    setup_dualcam_run.py --verify-splitter")
    print("  · the tweezers px->um calibration, invalid after an objective change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
