"""Hands-on hardware exercise: drive one 1 Hz sine on the tweezers, or on the piezo.

The two subsystems that have never been driven from this repo. Micro-Manager is
left out on purpose -- pymmcore is already known to work, and
``config/micromanager/verify_config_control.py`` covers it.

    python try_hardware.py tweezers            # plan + write the .tpf, send nothing
    python try_hardware.py tweezers --send     # microscope PC: send the TCP sequence
    python try_hardware.py piezo               # read-only survey + the planned waveform
    python try_hardware.py piezo --move        # microscope PC: actually oscillate

Default drive for both: a sine of **10 um peak-to-peak** (so +/-5 um about the
centre) at **1 Hz**. ``--peak-to-peak-um`` and ``--amplitude-um`` are separate
flags, and every report prints both numbers, because "왕복 10 um" can be read
either way and the amplitude enters the result.

HOW THE TWO PATHS DIFFER, AND WHY THAT SHOWS UP IN THE OUTPUT
-------------------------------------------------------------
tweezers  hardware-timed and blind. The pattern is a point list the AOD trap
          loop advances one point per pass, so 1 Hz is set by choosing the
          switching rate; the trajectory is then clocked by the instrument. But
          the TCP interface is write-only (manual pp. 66-69): a 0 return means
          the GUI accepted the command, not that the trap moved. Nothing here
          can verify the drive -- watch the GUI.

piezo     host-timed and readable. The controller *has* a hardware waveform
          generator (`function.*`), but this repo cannot use it yet: the
          argument layout of `function.waveform.data.set` is undocumented here,
          so `piezo_stage.upload_waveform()` refuses, and the generator's
          timebase is unknown anyway, so "1 Hz" could not be requested of it.
          → kb/decisions/2026-08-26-piezo-waveform-generator.md
          So this drives `stage.position.command.set` from Python, one sample at
          a time. That timing is as soft as the host, which is exactly why this
          script measures it and reports the achieved frequency and jitter
          rather than claiming 1 Hz. Unlike the tweezers, every sample is read
          back, so the drive is verified rather than assumed.

--unlock IS NOT OPTIONAL FOR --move (PIEZO)
-------------------------------------------
Established here against the DLL simulator, and it was not obvious: the
controller gates its command set by security level, and ``find_commands()``
reports only what the *current* level permits. At the base level that is **one**
``.set`` command in the entire 202-command set --
``controller.security.user.set``. ``stage.position.command.set`` is not merely
unavailable, it is invisible, and asking for its signature comes back "unknown
command", which reads like "this controller cannot do it" and is not what it
means.

So ``--move`` without ``--unlock`` refuses up front and says why, rather than
failing later with that misleading message. The access code is a fixed per-level
vendor constant -- not a secret anyone chooses (see ``piezo_stage.unlock``) --
and it is not in this repo; read it off the vendor software's config. After
unlocking, the survey re-counts the visible ``.set`` commands, because that
delta is the only direct evidence the unlock took effect.

Two other commands this turned up, both readable at the base level and both now
used: ``stage.position.calibrated-range.minimum/maximum.get``, which is the real
travel and retires ``piezo_waveform.OBSERVED``'s borrowed-from-NIS caveat; and
``stage.position.measured.is-readable.get``, which says whether the position
readout means anything at all (the bare simulator answers 0).

WHY THIS IS NOT config/tweezers/run_pattern.py
----------------------------------------------
``run_pattern.py`` is the production path for a measurement, and it *refuses*
to run a plan with blockers -- an unrecorded trapping range or GUI calibration
means the um coordinates are not trustworthy and the data would be wrong.

This script is the first-light path, and those blockers are exactly what it
exists to resolve: you cannot record the trapezoid off the GUI until something
draws a pattern in it. So it reports the blockers and proceeds on typed
confirmation. The blockers it will proceed past are all *measurement-validity*
ones (silent clipping, an unknown um scale). The safety ones stay hard:

  - no ``LASER_ON`` is ever sent (class 4; arm it at the GUI, interlocks in
    front of you). ``LOAD_PROJECT`` is not sent either, and that is deliberate:
    a project file carries "the state of the laser operation and beam setting"
    (manual p. 65), so loading one can restore a saved laser-on state.
  - the piezo waveform is range-checked against the stage travel and *refuses*
    rather than clipping, and it is centred on the stage's **currently measured
    position**, never on the travel centre. This is a Z piezo: commanding it to
    the middle of its 400 um travel from wherever it is now is how an objective
    meets a coverslip.

A KNOWN CRASH YOU WILL PROBABLY MEET (PIEZO)
--------------------------------------------
The vendor DLL's string getters -- ``GetCommandResultUnitsType`` and siblings,
reached through ``piezo_stage.command_parameters``/``command_results`` -- raise
``OSError: access violation`` intermittently, against the DLL's own simulator,
on the same command that answered a moment earlier. It is not this script:
``config/piezo/verify_piezo_commands.py`` (no ``--describe`` needed, its units
section is enough) reproduces it, and the argtypes in
``hardware/piezo/vendor/dll_adapter.py`` match the library manual, so the
suspect is the two-call sizing probe in ``piezo_stage._read_string`` -- a
2-byte buffer declared as length 1.

Fixing that belongs in the driver, not here. What this script does is survive
it: every introspection read is reported and stepped over, and the pre-move
signature check turns a crash into a refusal to move, because commanding a
stage through a signature you could not read is the guess this repo keeps
declining to make. It is intermittent, so a rerun often gets through.

WHAT NEITHER PATH CAN CHECK
---------------------------
The trap count in the loop (it scales every tweezers time and speed linearly),
whether the pattern fits the calibrated trapezoid rather than the rectangle,
and -- for the piezo -- whether `stage.mode.get` says the controller is even
acting on the digital command path this script writes to. The piezo survey
prints the mode; `config/piezo/verify_piezo_commands.py --hazard` is the fuller
read.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.optical_tweezers import (  # noqa: E402
    OpticalTweezers,
    TweezersError,
    find_gui_port,
)
from hardware.piezo_waveform import (  # noqa: E402
    OBSERVED,
    PM_PER_UM,
    StageTravel,
    Waveform,
    WaveformError,
    sine,
)
from hardware.tweezers_drive import (  # noqa: E402
    MIN_TRAP_REFRESH_HZ,
    DrivePlan,
    SlowdownRoute,
    blanking_time_note,
    command_sequence,
)
from hardware.tweezers_patterns import (  # noqa: E402
    BREAKPOINT_BITS,
    MAX_SWITCHING_RATE_HZ,
    Pattern,
    PatternError,
    PatternPoint,
    TrapLoop,
)

# hardware.piezo_stage is imported inside the piezo subcommand only: it pulls in
# the vendor ctypes adapter and the Windows PE DLLs, which exist on the
# microscope PC and nowhere else. The tweezers path should not depend on that.

#: Default drive. Peak-to-peak, not amplitude -- see the module docstring on
#: which reading of "왕복 10 um" this is.
DEFAULT_PEAK_TO_PEAK_UM = 10.0
DEFAULT_PERIOD_S = 1.0

#: Where a breakpoint may sit on the sine, as a fraction of one cycle.
#:
#: The sine is x = A sin(2 pi i / N), so these are the four phases a "stop here"
#: can mean. ``start`` and ``centre`` are the same *position* (x = 0) travelled
#: in opposite directions, which the trap cannot tell apart but the experiment
#: can. ``max``/``min`` are the turning points, where the trap is already
#: momentarily still -- halting there adds no velocity discontinuity, while
#: halting at a centre crossing stops the trap at its peak speed.
BREAKPOINT_PHASES = {"start": 0.0, "max": 0.25, "centre": 0.5, "min": 0.75}

#: Busy-wait window at the end of each host-timed sleep. time.sleep() on Windows
#: resolves to about a millisecond even on 3.12, which is a tenth of a 100-sample
#: 1 Hz interval -- enough jitter to be worth spinning through.
_SPIN_S = 0.002


def rule(title: str) -> str:
    return f"\n-- {title} " + "-" * max(0, 56 - len(title))


def amplitude_from_args(a: argparse.Namespace) -> float:
    """The half-excursion in um, from whichever flag was given."""
    if a.amplitude_um is not None:
        return float(a.amplitude_um)
    return float(a.peak_to_peak_um) / 2.0


def describe_drive(amplitude_um: float, period_s: float) -> str:
    return (
        f"sine  {2 * amplitude_um:.3f} um peak-to-peak "
        f"(amplitude +/-{amplitude_um:.3f} um)  at {1.0 / period_s:.4g} Hz "
        f"(period {period_s:.4g} s)"
    )


def latency_row(label: str, samples_s: list[float]) -> str:
    """min / median / p95 / max in ms -- the same summary orchestrator.py prints."""
    if not samples_s:
        return f"  {label:22} (none)"
    ms = sorted(s * 1e3 for s in samples_s)
    p95 = ms[min(len(ms) - 1, int(0.95 * (len(ms) - 1) + 0.5))]
    return (
        f"  {label:22} n={len(ms):<6} min {ms[0]:7.3f}  med "
        f"{statistics.median(ms):7.3f}  p95 {p95:7.3f}  max {ms[-1]:7.3f}  ms"
    )


# =====================================================================
# tweezers
# =====================================================================


def sine_pattern(
    amplitude_um: float,
    n_points: int,
    angle_deg: float = 0.0,
    strength: float = 1.0,
) -> Pattern:
    """A closed sinusoidal there-and-back sweep along one axis.

    Deliberately not in hardware/tweezers_patterns.py: it is the one shape here
    whose points are **not** evenly spaced by arc length, which breaks the
    assumption that module's ``mean_speed_um_s`` docstring calls out ("for them
    the two coincide"). Compare its ``oscillation``, which spaces positions
    uniformly -- that is a *triangle* wave in time, constant speed with a
    reversal at each end. This spaces *phase* uniformly, which is what makes
    position sinusoidal in time, because the trap loop gives every point the
    same dwell. The cost is that speed varies over the cycle: peak = pi/2 times
    mean, at the centre crossing, and zero at the turning points.

    If a sine drive turns out to be a standing need rather than a bring-up test,
    this belongs next to ``oscillation`` with that caveat attached.
    """
    if amplitude_um <= 0:
        raise PatternError("amplitude must be positive")
    if n_points < 4:
        raise PatternError("a sine needs at least 4 points")
    theta = math.radians(angle_deg)
    ux, uy = math.cos(theta), math.sin(theta)
    coords = [
        amplitude_um * math.sin(2 * math.pi * i / n_points) for i in range(n_points)
    ]
    return Pattern(
        tuple(PatternPoint(s * ux, s * uy, strength) for s in coords),
        name=f"sine_a{amplitude_um:g}um_n{n_points}",
    )


def breakpoint_index(where: str, n_points: int) -> int:
    """Index of the ``BREAKPOINT_PHASES`` phase in an n-point sine."""
    return int(round(BREAKPOINT_PHASES[where] * n_points)) % n_points


def tweezers_plan(a: argparse.Namespace) -> DrivePlan:
    """Build the drive plan. Pure computation -- runs on the offline PC."""
    amplitude_um = amplitude_from_args(a)
    pattern = sine_pattern(amplitude_um, a.points, angle_deg=a.angle_deg,
                           strength=a.strength)
    if a.breakpoint_at:
        pattern = pattern.with_breakpoint_at(
            breakpoint_index(a.breakpoint_at, a.points), bits=a.breakpoint_bits
        )

    # One pattern point per trap-loop pass, so a full cycle is n_points passes
    # and each pass costs one switching interval per trap in the loop. Hence the
    # rate that makes the cycle last exactly `period_s`:
    rate_hz = a.points * a.n_traps / a.period_s
    loop = TrapLoop(switching_rate_hz=rate_hz, n_traps=a.n_traps)

    # No slowdown is needed: unlike the microrheology drive, which starts at
    # 100 kHz and has to come down by ~1e3, the rate above IS the rate this
    # drive wants. Recording that as a factor-1 `switching_rate` route keeps
    # DrivePlan.report() and command_sequence() honest about what gets sent.
    native = pattern.mean_speed_um_s(loop)
    chosen = SlowdownRoute(
        "switching_rate",
        1.0,
        python_settable=True,
        cost="none -- the rate below was solved for this period, not reduced "
        "from 100 kHz. It is still global: every other pattern-driven trap in "
        "the loop slows with it",
    )

    half = a.half_range_um
    if half is None:
        status, note = "BLOCKED", (
            "trapping_range not recorded. Pass --half-range-um once you have "
            "read the green trapezoid off the GUI; until then a pattern that "
            "overruns it is clipped to the edge silently and undrawn"
        )
    else:
        dx, dy = pattern.half_extent_um
        fits = pattern.fits_within(float(half), float(half))
        status = "OK" if fits else "FAIL"
        note = (
            f"+/-{dx:.2f} x +/-{dy:.2f} um vs the recorded +/-{float(half):.2f} um "
            + ("(rectangular check only; the real edge is a trapezoid)" if fits
               else "-- points outside are silently clipped to the edge")
        )

    return DrivePlan(
        name=a.name,
        trap=a.trap,
        pattern_name=a.pattern_name,
        project=None,  # never LOAD_PROJECT from here: it can restore laser-on
        pattern=pattern,
        loop=loop,
        target_speed_um_s=native,
        routes=(chosen,),
        chosen=chosen,
        range_status=status,
        range_note=note,
        calibration={"objective": a.objective} if a.objective else {},
        field_calibration=(
            {"objective": a.field_objective} if a.field_objective else {}
        ),
    )


def tweezers_extra_report(drive: DrivePlan, a: argparse.Namespace) -> str:
    """The sine-specific numbers DrivePlan.report() does not know to print."""
    amplitude_um = amplitude_from_args(a)
    rate = drive.switching_rate_hz()
    refresh_hz = a.points / a.period_s  # = rate / n_traps, independent of n_traps
    mean = drive.effective_speed_um_s()
    lines = [
        rule("this sine, and what set the rate"),
        f"  drive            {describe_drive(amplitude_um, a.period_s)}",
        f"  solved rate      {a.points} points x {a.n_traps} traps / "
        f"{a.period_s:g} s = {rate:,.1f} Hz",
        f"  cycle time       {drive.effective_cycle_time_s():.4f} s  "
        f"-> {1.0 / drive.effective_cycle_time_s():.4f} Hz",
        "",
        "  speed is NOT constant over the cycle -- that is what makes it a sine",
        f"    mean           {mean:,.2f} um/s   (path {drive.pattern.path_length_um:.2f} "
        "um per closed cycle = 4x amplitude)",
        f"    peak           {2 * math.pi * amplitude_um / a.period_s:,.2f} um/s"
        f"   at each centre crossing (pi/2 x mean)",
        "    turning points zero, and each is illuminated once per cycle",
        "",
        f"  trap refresh     {refresh_hz:,.1f} Hz  (= points / period; the trap "
        "count cancels)",
    ]
    if refresh_hz < MIN_TRAP_REFRESH_HZ:
        lines.append(
            f"    *** BELOW the {MIN_TRAP_REFRESH_HZ:g} Hz advisory hold threshold. "
            "A trap revisited"
        )
        lines.append(
            "        this rarely may not hold a particle at all -- raise --points"
        )
    else:
        lines.append(
            f"    comfortably over the {MIN_TRAP_REFRESH_HZ:g} Hz advisory "
            "threshold. Raise --points to raise both"
        )
        lines.append(
            "    the refresh and the spatial fidelity of the sine; the ceiling is"
        )
        lines.append(
            f"    {MAX_SWITCHING_RATE_HZ:,.0f} Hz / {a.n_traps} traps x "
            f"{a.period_s:g} s = {MAX_SWITCHING_RATE_HZ * a.period_s / a.n_traps:,.0f} points"
        )
    if a.breakpoint_at:
        idx = breakpoint_index(a.breakpoint_at, a.points)
        pt = drive.pattern.points[idx]
        width = (
            f"{BREAKPOINT_BITS}-bit field"
            if BREAKPOINT_BITS is not None
            else "field width UNREAD (BREAKPOINT_BITS is None) -- 1 fits either"
        )
        lines += [
            "",
            f"  breakpoint       '{a.breakpoint_at}' = point {idx:,} of "
            f"{a.points:,}  ->  ({pt.x_um:+.4f}, {pt.y_um:+.4f}) um",
            f"    colBP          {pt.breakpoint}   ({width})",
            "    the trap halts there until TRAP_PATT_RELEASE_BP or a hardware",
            "    trigger. On a 4-bit system (SN >= 130) it halts only if the",
            "    trap's Enable Bits mask covers this value, and releases only",
            "    under a matching Release Bits mask -- both are GUI-only, so a",
            "    pattern that never stops means checking those there, not here",
        ]
    return "\n".join(lines)


def run_tweezers(a: argparse.Namespace) -> int:
    try:
        drive = tweezers_plan(a)
    except PatternError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(drive.report())
    print(tweezers_extra_report(drive, a))

    out = a.out or (REPO / f"{a.name}.tpf")
    on_scope = a.tpf_on_scope or str(out)
    sequence = list(command_sequence(drive, on_scope, file_first=a.file_first,
                                     blanking_time_us=a.blanking_us))
    if a.trap_x_um is not None or a.trap_y_um is not None:
        # command_sequence() hardcodes TRAP_POSITION <trap> 0 0. Appending
        # supersedes it, since the GUI acts on commands in order -- and leaving
        # both lines visible is the point: you can see what is being overridden.
        tx, ty = a.trap_x_um or 0.0, a.trap_y_um or 0.0
        q = f'"{a.trap}"' if " " in a.trap else a.trap
        sequence.append(f"TRAP_POSITION {q} {tx:g} {ty:g}")

    print(rule("TCP commands this plan implies"))
    for line in sequence:
        print(f"   {line}")
    print(f"\n   {blanking_time_note(drive.switching_rate_hz(), a.blanking_us)}")
    print("   no LASER_ON and no LOAD_PROJECT: see the module docstring")

    written = drive.emitted_pattern().write(out, decimal=a.decimal)
    print(f"\n-- wrote {written}  ({len(drive.emitted_pattern()):,} points) --")

    if not a.send:
        print("   nothing sent. Copy the .tpf to the microscope PC, then rerun")
        print("   there with --send and --tpf-on-scope <absolute path>.")
        return 0

    print(rule(f"send: {a.host}:{a.port}"))
    if a.tpf_on_scope is None:
        print("   NOTE: --tpf-on-scope not given, so the path above is this PC's.")
        print("   The manual states TCP file paths are absolute; if the GUI is")
        print("   elsewhere, LOAD_PATTERN will fail with -27.")
    for blocker in drive.blockers:
        print(f"   WARNING  {blocker}")
    if drive.blockers:
        print("\n   These are measurement-validity blockers, not safety ones, and")
        print("   resolving them is what a first-light run is for. The drive will")
        print("   still be geometrically wrong in um until they are recorded --")
        print("   do not take numbers off this run.")

    try:
        with OpticalTweezers(host=a.host, port=a.port) as tweez:
            status = tweez.probe()
            print(f"\n   readiness probe -> {status}")
            if a.wait_ready:
                tweez.wait_until_ready(timeout=a.wait_ready)
                print(f"   GUI ready within {a.wait_ready:g}s")
            answer = input("   send the commands above? type 'send': ")
            if answer.strip() != "send":
                print("   aborted -- nothing sent")
                return 0
            for line in sequence:
                tweez.do(line)
                print(f"   ok  {line}")
    except OSError as exc:
        sys.stdout.flush()  # or a piped stderr overtakes the plan above it
        print(f"\nFAILED to reach the GUI on {a.host}:{a.port}: {exc}", file=sys.stderr)
        found = find_gui_port(host=a.host)
        if found:
            print(f"   a GUI did answer on port {found} -- rerun with --port {found}",
                  file=sys.stderr)
        else:
            print("   no GUI answered on 2070-2075. Start Tweez 300, connect its",
                  file=sys.stderr)
            print("   System Manager, and check External Control is enabled.",
                  file=sys.stderr)
        return 1
    except TweezersError as exc:
        sys.stdout.flush()
        print(f"\nFAILED: {exc}", file=sys.stderr)
        print("   read the status code off the GUI's Status Pane > TCP/IP Svr log",
              file=sys.stderr)
        return 1

    print("\n   sent. There is no readback on this interface, so confirm at the GUI:")
    print("     - the pattern is assigned to the trap and drawn inside the trapezoid")
    print(f"     - one cycle takes {drive.effective_cycle_time_s():.3f} s by eye/camera")
    print("     - the trap count in the loop really is "
          f"{a.n_traps} (it scales every time above)")
    return 0


# =====================================================================
# piezo
# =====================================================================


def _wait_until(t0: float, target_s: float) -> None:
    """Sleep to just short of ``target_s``, then spin. See _SPIN_S."""
    remaining = target_s - (time.perf_counter() - t0)
    if remaining > _SPIN_S:
        time.sleep(remaining - _SPIN_S)
    while (time.perf_counter() - t0) < target_s:
        pass


#: The command that moves the stage. Invisible until the security level is
#: raised -- see ``piezo_survey``. Named once so the survey and the pre-move
#: signature check cannot drift apart from what actually gets sent: the
#: playback loop commands through ``PiezoStage.set_position_pm()``, which is
#: this same command with its reply parsed.
MOVE_COMMAND = "stage.position.command.set"


def settable(stage) -> list[str]:
    """Visible ``.set`` commands. At the base security level this is a list of
    one, which is the whole reason ``--unlock`` exists."""
    return sorted(
        c for c in stage.find_commands() if c and (c.endswith(".set") or ".set." in c)
    )


def gettable(stage) -> list[str]:
    return sorted(c for c in stage.find_commands() if c and c not in settable(stage))


def read_float(stage, command: str):
    """One numeric result, or None if the controller will not give it."""
    try:
        raw = stage.get_result("value", stage.do_command(command))
        return None if raw is None else float(raw)
    except Exception:  # noqa: BLE001  an unavailable reading is a None, not a crash
        return None


def read_travel(stage, channel: int, resolution_um: float):
    """Calibrated travel read off the controller, or None.

    ``stage.position.calibrated-range.minimum/maximum.get`` are present on this
    controller and readable at the base security level, which retires the
    caveat on ``piezo_waveform.OBSERVED``: the travel no longer has to be
    inherited from NIS's analogue abstraction of the same box.

    Returns None on a degenerate answer. The DLL's bare simulator reports
    0/0 -- and a zero-width travel would fail every range check for a reason
    that has nothing to do with the waveform.
    """
    lo = read_float(stage, f"stage.position.calibrated-range.minimum.get {channel}")
    hi = read_float(stage, f"stage.position.calibrated-range.maximum.get {channel}")
    if lo is None or hi is None or hi <= lo:
        return None
    return StageTravel(
        min_pm=lo, max_pm=hi, resolution_pm=float(resolution_um) * PM_PER_UM
    )


def resolve_travel(stage, a: argparse.Namespace) -> tuple[StageTravel, str]:
    """Travel bounds and where they came from, best source first.

    Explicit flags win: if someone has measured the travel, that beats anything
    inferred. Then the controller. ``OBSERVED`` is the last resort and is the
    only one of the three that describes a different control path than the one
    this script writes to.
    """
    if a.travel_min_um is not None or a.travel_max_um is not None:
        if a.travel_min_um is None or a.travel_max_um is None:
            raise WaveformError(
                "give both --travel-min-um and --travel-max-um, or neither"
            )
        return (
            StageTravel(
                min_pm=float(a.travel_min_um) * PM_PER_UM,
                max_pm=float(a.travel_max_um) * PM_PER_UM,
                resolution_pm=float(a.resolution_um) * PM_PER_UM,
            ),
            "--travel-min-um/--travel-max-um",
        )
    from_controller = read_travel(stage, a.channel, a.resolution_um)
    if from_controller is not None:
        return from_controller, "stage.position.calibrated-range.*, read just now"
    return OBSERVED, "piezo_waveform.OBSERVED fallback"


class PiezoStageErrorLike(RuntimeError):
    """Raised for a signature this script will not command through.

    Separate from ``PiezoStageError`` on purpose: that one means the controller
    or the DLL failed, this one means *we* declined.
    """


def check_position_command(stage) -> tuple[str, str]:
    """Read the DLL's own signature for the command/measure pair.

    Returns ``(set_units, get_units)``. This is the whole reason a position can
    be commanded from here at all: the argument layout of
    ``stage.position.command.set`` is no better documented in this repo than
    ``function.waveform.data.set`` is, but unlike the waveform command the DLL
    will report it -- so it gets read off the controller rather than guessed.
    Raises unless it is the (channel, value) pair this script assumes.

    Library manual 5.2: a distance may be reported in picometres for a linear
    stage or picoradians for an angular one, and applications "should always
    check the units". So the *set* units are compared against the *measured*
    units rather than assumed to be picometres -- if the two agree, commanding
    in picometres introduces no assumption that get_position_pm() does not
    already make.
    """
    try:
        params = stage.command_parameters(MOVE_COMMAND)
        results = stage.command_results("stage.position.measured.get")
    except OSError as exc:
        raise PiezoStageErrorLike(
            f"could not read the signature: the DLL raised {exc!r}. "
            f"{INTROSPECTION_IS_FRAGILE}. Refusing to move -- the argument layout "
            "of stage.position.command.set would be a guess, and this command "
            "moves a stage. Rerun (it is intermittent), or fix "
            "piezo_stage._read_string first."
        ) from exc
    print(f"  stage.position.command.set   params  {params}")
    print(f"  stage.position.measured.get  results {results}")
    if len(params) != 2:
        raise PiezoStageErrorLike(
            f"expected stage.position.command.set to take (channel, value); the "
            f"DLL reports {len(params)} parameter(s): {params}. Refusing to "
            "guess -- this command moves a stage."
        )
    set_units = (params[1][2] or "").strip()
    measured = next((r for r in results if r[0] == "value"), results[0] if results else None)
    get_units = ((measured[2] if measured else "") or "").strip()
    if not set_units and not get_units:
        print("  the DLL reports NO units for either -- consistent, but nothing here")
        print("  CONFIRMS picometres. get_position_pm() already assumes them, so")
        print("  commanding in picometres adds no new assumption; it does not verify")
        print("  the standing one. The DLL simulator answers like this.")
        return set_units, get_units
    if set_units.lower() != get_units.lower():
        raise PiezoStageErrorLike(
            f"units mismatch: command.set value is in {set_units!r} but "
            f"measured.get returns {get_units!r}. get_position_pm() assumes "
            "picometres; commanding in a different unit would be a 1e3-or-worse "
            "scale error. Resolve it with config/piezo/verify_piezo_commands.py."
        )
    return set_units, get_units


#: The string-returning DLL getters (``GetCommandResultUnitsType`` and its
#: siblings) intermittently raise ``OSError: access violation`` -- reproducible
#: with this repo's own ``config/piezo/verify_piezo_commands.py``, and observed
#: both to succeed and to crash on the same command against the DLL simulator.
#: The argtypes in hardware/piezo/vendor/dll_adapter.py match the manual's
#: signature, so the fault is inside the DLL or in the two-call sizing probe
#: ``piezo_stage._read_string`` uses (a 2-byte buffer with a declared length of
#: 1). Nothing here tries to fix that -- it is the driver's to fix -- but this
#: script must not lose a whole survey to it, and must not command motion
#: through a signature it could not read.
INTROSPECTION_IS_FRAGILE = (
    "the vendor DLL's string getters intermittently raise an access violation; "
    "reproduce with config/piezo/verify_piezo_commands.py, whose --describe path "
    "hits the same call"
)


def try_read(label: str, fn, *args) -> None:
    """Run a DLL read, print what came back, and survive a crash in the DLL.

    Reporting only -- callers here want the line printed, not the value, so
    nothing is returned and a failure needs no sentinel to distinguish.

    ``OSError`` is caught alongside the driver's own errors because an access
    violation inside the DLL surfaces as one. Catching it is not safe in
    general -- the heap may already be damaged -- so a crash here is reported
    loudly and, in ``check_position_command``, escalated into a refusal to move.
    """
    try:
        value = fn(*args)
    except OSError as exc:
        print(f"  {label} -> DLL CRASHED: {exc}")
        print(f"    {INTROSPECTION_IS_FRAGILE}")
        return
    except Exception as exc:  # noqa: BLE001  a read that failed is information
        print(f"  {label} -> failed: {exc}")
        return
    print(f"  {label} -> {value}")


def piezo_survey(stage, a: argparse.Namespace) -> None:
    """Everything readable, and nothing that moves. Safe with a sample in place."""
    print(rule("controller"))
    print(f"  DLL version      {stage.dll_version()}")
    print(f"  connected to     {a.link}  (open={stage.is_connected()})")
    n_channels = stage.channels()
    print(f"  channels         {n_channels}")
    print(f"  firmware         {stage.identity()}")
    print(f"  security level   {stage.security_level()}"
          "   (.set commands may need this raised -- see --unlock)")

    print(rule("what the security level lets us see"))
    print(f"  visible commands {len(settable(stage)) + len(gettable(stage))}"
          f"   ({len(settable(stage))} of them .set)")
    for name in settable(stage):
        print(f"    .set  {name}")
    print("  find_commands() reports what THIS security level permits, not what the")
    print("  controller can do. At the base level that is one .set command --")
    print("  controller.security.user.set -- and stage.position.command.set is not")
    print("  merely unavailable, it is INVISIBLE. So --unlock is not an optional")
    print("  extra for --move; without it there is no way to command a position.")
    print("  The access code is a fixed per-level vendor constant, not a secret you")
    print("  choose (piezo_stage.unlock); it is not in this repo -- read it off the")
    print("  vendor software's config.")

    print(rule("command path -- is the controller even listening to us?"))
    try_read(f"stage.mode.get {a.channel}", stage.stage_mode, a.channel)
    # Sharper than stage.mode.get's packed word: this controller carries a
    # separate flag per command input, which is the analogue-vs-digital question
    # kb/systems/current.md has had open since 2026-08-19 asked directly.
    for command in ("stage.mode.digital-command.get",
                    "stage.mode.analogue-command.get",
                    "stage.mode.freeze-servo-output.get"):
        try_read(f"{command} {a.channel}", stage.do_command,
                 f"{command} {a.channel}")
    print("  This script writes the DIGITAL path. NIS drives the same controller's")
    print("  analogue input on Dev1/ao2, which is still cabled. If the mode says the")
    print("  controller is acting on analogue, the commands below will be accepted")
    print("  and ignored -- which the readback will show.")

    print(rule("hardware waveform generator -- why it is not used"))
    try_read("function.state.get", stage.function_state)
    try_read(
        "function.* commands present",
        lambda: len([c for c in stage.find_commands("function.") if c]),
    )
    from hardware.piezo_stage import WAVEFORM_PROTOCOL

    print(f"  WAVEFORM_PROTOCOL is {WAVEFORM_PROTOCOL!r} -> upload_waveform() refuses.")
    print("  And the generator's sample period is not established either, so '1 Hz'")
    print("  could not be asked of it even with the upload path open. Hence the")
    print("  host-timed loop below. → config/piezo/verify_piezo_commands.py")

    print(rule("position"))
    try_read("position units  ", stage.position_units)
    # If this is 0 the position readout is not valid, and every "measured"
    # number below -- including the whole tracking report -- means nothing. The
    # DLL's bare simulator answers 0.
    try_read(f"is-readable ch{a.channel}", stage.do_command,
             f"stage.position.measured.is-readable.get {a.channel}")
    readable = read_float(
        stage, f"stage.position.measured.is-readable.get {a.channel}"
    )
    if readable is not None and readable == 0:
        print("    *** 0 -- the position readout on this channel is NOT valid, so")
        print("        every measured number below, and the whole tracking report,")
        print("        carries no information. Expected against the bare simulator;")
        print("        on the real controller it means no stage is calibrated here.")
    for ch in range(1, n_channels + 1):
        mark = " <- driving this one" if ch == a.channel else ""
        try:
            print(f"  channel {ch}        {stage.get_position_um(ch):.4f} um{mark}")
        except Exception as exc:  # noqa: BLE001
            print(f"  channel {ch}        read failed: {exc}{mark}")


def measure_read_latency(stage, a: argparse.Namespace, n: int = 40) -> list[float]:
    """Time the read-only round trip, which caps the host-timed sample rate.

    Read-only, so this runs in the no-``--move`` survey too: it tells you what
    sample period the link can actually sustain before anything moves.
    """
    samples: list[float] = []
    for _ in range(n):
        t = time.perf_counter()
        stage.get_position_pm(a.channel)
        samples.append(time.perf_counter() - t)
    return samples


def piezo_waveform_report(wf: Waveform, travel: StageTravel, a: argparse.Namespace,
                          centre_pm: float, centre_source: str,
                          travel_source: str) -> str:
    amplitude_um = amplitude_from_args(a)
    dt = a.period_s / len(wf)
    lo, hi = wf.span_pm
    q_err_pm = wf.quantisation_error_pm(travel)
    lines = [
        rule("the waveform"),
        f"  drive            {describe_drive(amplitude_um, a.period_s)}",
        f"  centre           {centre_pm / PM_PER_UM:.4f} um   ({centre_source})",
        f"  span             {lo / PM_PER_UM:.4f} .. {hi / PM_PER_UM:.4f} um",
        f"  travel           {travel.min_pm / PM_PER_UM:.4f} .. "
        f"{travel.max_pm / PM_PER_UM:.4f} um, step "
        f"{travel.resolution_pm / PM_PER_UM * 1e3:.4g} nm",
        f"                   ({travel_source})",
        f"  samples          {len(wf)} per cycle x {a.cycles} cycle(s), "
        f"{dt * 1e3:.3f} ms apart",
        f"  peak speed       {wf.peak_speed_um_s(dt):,.2f} um/s"
        f"   (2*pi*A/T = {2 * math.pi * amplitude_um / a.period_s:,.2f} um/s)",
        f"  quantisation     {q_err_pm / PM_PER_UM * 1e3:.4g} nm worst case, "
        f"{100 * q_err_pm / (amplitude_um * PM_PER_UM):.2f}% of amplitude",
    ]
    levels = 2 * amplitude_um * PM_PER_UM / travel.resolution_pm
    if levels < 20:
        lines.append(
            f"    *** only ~{levels:.0f} controller steps across the full swing. "
            "That is a"
        )
        lines.append("        staircase, not a sine. Raise the amplitude.")
    if travel is OBSERVED:
        lines.append("")
        lines.append("  *** The controller would not give its calibrated range, so the")
        lines.append("  travel above is the one figure here NOT read off it: 0-400 um /")
        lines.append("  0.0122 um came from NIS's analogue abstraction of the same box")
        lines.append("  (kb/systems/current.md), and the DLL has its own digital")
        lines.append("  scaling. Pass --travel-min-um/--travel-max-um, or find out why")
        lines.append("  stage.position.calibrated-range.* answered 0.")
    return "\n".join(lines)


def play_host_timed(stage, wf: Waveform, a: argparse.Namespace, channel: int,
                    readback: bool) -> dict:
    """Command each sample on a fixed schedule; return what actually happened.

    The schedule is absolute (sample k is due at k*dt from the start), not
    cumulative, so a slow round trip does not push every later sample late.
    """
    dt = a.period_s / len(wf)
    samples = list(wf.samples) * a.cycles
    set_ms: list[float] = []
    get_ms: list[float] = []
    log: list[tuple[float, float, float, float | None]] = []
    first_echo_pm: float | None = None
    t0 = time.perf_counter()
    for k, value_pm in enumerate(samples):
        _wait_until(t0, k * dt)
        t_due = k * dt
        t_send = time.perf_counter() - t0
        t = time.perf_counter()
        echoed_pm = stage.set_position_pm(channel, value_pm)
        set_ms.append(time.perf_counter() - t)
        if first_echo_pm is None:
            first_echo_pm = echoed_pm
        measured = None
        if readback:
            t = time.perf_counter()
            measured = stage.get_position_pm(channel)
            get_ms.append(time.perf_counter() - t)
        log.append((t_due, t_send, value_pm, measured))
    return {
        "dt_s": dt,
        "n": len(samples),
        "log": log,
        "set_s": set_ms,
        "get_s": get_ms,
        "first_echo_pm": first_echo_pm,
        "total_s": time.perf_counter() - t0,
    }


def report_playback(run: dict, wf: Waveform, a: argparse.Namespace) -> str:
    """Achieved timing and tracking. This is the output that matters."""
    log = run["log"]
    dt = run["dt_s"]
    late_s = [t_send - t_due for t_due, t_send, _, _ in log]
    overruns = sum(1 for x in late_s if x > dt)
    n_cycles = a.cycles
    # From the send timestamps, not from the loop's wall time: `total_s` stops
    # after the LAST sample is sent, and the last sample is due at (n-1)*dt, so
    # dividing it by the cycle count is short by one sample period and reports a
    # 1 Hz drive as 1.0126 Hz. n-1 intervals span the samples that were sent;
    # scaling that mean interval by the samples per cycle gives the cycle.
    spans = len(log) - 1
    achieved_dt_s = (log[-1][1] - log[0][1]) / spans if spans else dt
    achieved_period_s = achieved_dt_s * len(wf)
    lines = [
        rule("achieved timing (the host clock is the weak link here)"),
        f"  requested        {1.0 / a.period_s:.4f} Hz  "
        f"({a.period_s:g} s x {n_cycles} cycles = {a.period_s * n_cycles:g} s)",
        f"  achieved         {1.0 / achieved_period_s:.4f} Hz  "
        f"({achieved_period_s:.4f} s per cycle, mean sample period "
        f"{achieved_dt_s * 1e3:.3f} ms)",
        f"  schedule slip    med {statistics.median(late_s) * 1e3:.3f} ms, "
        f"max {max(late_s) * 1e3:.3f} ms  (target sample period {dt * 1e3:.3f} ms)",
        f"  overruns         {overruns}/{run['n']} samples arrived more than one "
        "period late",
        "",
        latency_row("set round trip", run["set_s"]),
    ]
    if run["get_s"]:
        lines.append(latency_row("get round trip", run["get_s"]))
    else:
        lines.append("  get round trip         skipped (--no-readback)")

    per_sample_s = statistics.median(run["set_s"]) + (
        statistics.median(run["get_s"]) if run["get_s"] else 0.0
    )
    if per_sample_s > 0:
        sustained_hz = 1.0 / per_sample_s
        lines += [
            "",
            f"  the link sustains about {sustained_hz:,.0f} samples/s, so a "
            f"{a.period_s:g} s cycle",
            f"  supports up to ~{sustained_hz * a.period_s:,.0f} samples before the "
            "host, not the stage, becomes the limit.",
        ]
    if overruns > run["n"] * 0.05:
        lines += [
            "",
            "  *** MORE THAN 5% OF SAMPLES WERE LATE. The frequency above is what",
            "      the stage actually did; the requested one was not met. Lower",
            "      --points, or pass --no-readback to halve the round trips.",
        ]

    measured = [m for _, _, _, m in log if m is not None]
    if not measured:
        lines += ["", "  no readback taken, so nothing here verifies the stage moved."]
        return "\n".join(lines)

    lines.append(rule("tracking (readback -- this is what the tweezers cannot do)"))
    moved_pm = max(measured) - min(measured)
    lines.append(
        f"  measured span    {moved_pm / PM_PER_UM:.4f} um  "
        f"(commanded {2 * amplitude_from_args(a):.4f} um peak-to-peak)"
    )
    errors_pm = [abs(m - c) for _, _, c, m in log if m is not None]
    lines.append(
        f"  |measured-cmd|   med {statistics.median(errors_pm) / PM_PER_UM * 1e3:.1f} nm, "
        f"max {max(errors_pm) / PM_PER_UM * 1e3:.1f} nm"
    )
    lines.append(
        "    an UPPER bound on the real tracking error: the readback happens after"
    )
    lines.append(
        "    the command, so it also carries the stage's settling and one round trip."
    )
    commanded_swing_pm = 2 * amplitude_from_args(a) * PM_PER_UM
    if moved_pm < 0.2 * commanded_swing_pm:
        lines += [
            "",
            f"  *** THE STAGE BARELY MOVED: {moved_pm / PM_PER_UM:.4f} um of a "
            f"commanded {commanded_swing_pm / PM_PER_UM:.4f} um.",
            "      The controller accepted the commands",
            f"      (the first was echoed back as "
            f"{run['first_echo_pm'] / PM_PER_UM:.4f} um) but the measured position",
            "      did not follow. The two things to check, in order:",
            "        1. security level -- .set commands need it raised (--unlock CODE)",
            "        2. stage.mode.get -- the controller may be acting on the",
            "           analogue input from Dev1/ao2, not on this digital path",
        ]
    return "\n".join(lines)


def run_piezo(a: argparse.Namespace) -> int:
    try:
        from hardware.piezo_stage import PiezoStage, PiezoStageError
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to import the piezo driver: {exc}", file=sys.stderr)
        print("  hardware/piezo/vendor/*.dll are Windows PE binaries -- the piezo",
              file=sys.stderr)
        print("  path runs on the microscope PC only.", file=sys.stderr)
        return 2

    try:
        # allow_motion tracks --move, and it gates everything below that can
        # move the stage: the loop commands through set_position_pm() and the
        # restores go the same way, so a survey run -- allow_motion=False --
        # cannot command a position even by accident, and function_start()
        # stays blocked as well. The typed confirmation before the drive is
        # the second gate.
        stage = PiezoStage(allow_motion=a.move)
    except PiezoStageError as exc:
        print(f"FAILED to load the controller DLL: {exc}", file=sys.stderr)
        return 2

    try:
        stage.connect(a.link)
    except PiezoStageError as exc:
        print(f"could not open {a.link!r}: {exc}", file=sys.stderr)
        print('  start with the DLL\'s own simulator: --link "sim:/NPC6330"',
              file=sys.stderr)
        stage.close()
        return 2

    rc = 0
    try:
        piezo_survey(stage, a)

        if a.unlock is not None:
            print(rule("security -- unlocking"))
            before = len(settable(stage))
            print(f"  controller.security.user.set -> {stage.unlock(a.unlock)}")
            after = settable(stage)
            print(f"  .set commands visible: {before} -> {len(after)}")
            # The count is the evidence the unlock worked. The command set is
            # gated per level, so a level that rose without revealing anything
            # new is a level that did not rise far enough.
            if len(after) <= before:
                print("  *** nothing new became visible. Either the code was wrong or")
                print("      it raised the level to one that still cannot command a")
                print("      position -- there is more than one level.")
            elif MOVE_COMMAND in after:
                print(f"  {MOVE_COMMAND} is now available.")

        if a.move and MOVE_COMMAND not in settable(stage):
            sys.stdout.flush()  # or a piped stderr overtakes the survey above it
            print(rule("REFUSED"), file=sys.stderr)
            print(f"  {MOVE_COMMAND} is not visible at this security level, so", file=sys.stderr)
            print("  there is no way to command a position. This is the expected state",
                  file=sys.stderr)
            print("  without --unlock: the .set half of the command set is gated, and",
                  file=sys.stderr)
            print("  the survey above lists what IS visible. Pass --unlock CODE.",
                  file=sys.stderr)
            print("  The code is a fixed per-level vendor constant; it lives in the",
                  file=sys.stderr)
            print("  vendor software's config, not in this repo.", file=sys.stderr)
            return 2

        print(rule("read-only round trip (caps the host-timed sample rate)"))
        print(latency_row("get position", measure_read_latency(stage, a)))

        travel, travel_source = resolve_travel(stage, a)

        # Centre on where the stage is NOW, not on the travel centre. This is a
        # Z piezo: a 200 um step to the middle of its travel is how an objective
        # meets a coverslip.
        if a.centre_um is not None:
            centre_pm = float(a.centre_um) * PM_PER_UM
            centre_source = "--centre-um, EXPLICIT -- check clearance yourself"
        else:
            centre_pm = stage.get_position_pm(a.channel)
            centre_source = "current measured position, read just now"

        amplitude_um = amplitude_from_args(a)
        wf = sine(
            amplitude_pm=amplitude_um * PM_PER_UM,
            n_samples=a.points,
            channel=a.channel,
            centre_pm=centre_pm,
        )
        print(piezo_waveform_report(wf, travel, a, centre_pm, centre_source,
                                    travel_source))

        # Hard gate, and it refuses rather than clipping -- a clipped trajectory
        # produces data that looks fine and is wrong.
        try:
            wf.check(travel)
        except WaveformError as exc:
            print(f"\n  range check      REFUSED: {exc}")
            headroom_um = min(
                centre_pm - travel.min_pm, travel.max_pm - centre_pm
            ) / PM_PER_UM
            print(f"  the centre sits {headroom_um:.4f} um from the nearer travel "
                  f"bound, so +/-{amplitude_um:.3f} um does not fit.")
            if a.centre_um is None:
                print("  That centre came from the controller. If this is the DLL")
                print('  simulator ("sim:/NPC6330") it reports 0 um -- the travel')
                print("  minimum -- so a symmetric sine can never fit, and the check")
                print("  is doing its job rather than finding a real problem. Pass")
                print("  --centre-um 200 to exercise the path against the simulator.")
                print("  On the real stage, parked mid-travel, this passes as it is.")
            else:
                print("  Lower the amplitude, move --centre-um inward, or correct the")
                print("  bounds with --travel-min-um/--travel-max-um.")
            return 2
        print("\n  range check      OK: every sample is inside the travel above")

        if not a.move:
            print(rule("nothing moved"))
            print("  --move to actually oscillate. It will swing "
                  f"+/-{amplitude_um:.3f} um about")
            print(f"  {centre_pm / PM_PER_UM:.4f} um on channel {a.channel}. On a Z "
                  "piezo that is a change in")
            print("  focus: confirm the clearance to the coverslip first.")
            return 0

        print(rule("move"))
        print(f"  channel {a.channel}, "
              f"{centre_pm / PM_PER_UM:.4f} +/- {amplitude_um:.3f} um, "
              f"{a.cycles} cycle(s) of {a.period_s:g} s")
        print("  Reading the signature off the DLL before commanding anything:")
        set_units, _ = check_position_command(stage)
        if set_units:
            print(f"  units agree ({set_units!r}), so commanding in picometres adds")
            print("  no assumption that get_position_pm() does not already make.")

        axis = {1: "x", 2: "y", 3: "z"}.get(a.channel, "?")
        if a.channel == 3:
            print("\n  *** channel 3 is Z: every um here is a change in focus.")
        answer = input(
            f"\n  this MOVES {axis} (channel {a.channel}) "
            f"+/-{amplitude_um:.3f} um. type 'move': "
        )
        if answer.strip() != "move":
            print("  aborted -- nothing commanded")
            return 0

        start_pm = stage.get_position_pm(a.channel)
        try:
            run = play_host_timed(stage, wf, a, a.channel, readback=not a.no_readback)
            print(report_playback(run, wf, a))
        except KeyboardInterrupt:
            print("\n  interrupted -- commanding the start position back")
            stage.set_position_pm(a.channel, start_pm)
            print(f"  now at {stage.get_position_um(a.channel):.4f} um")
            return 130
        # A closed sine ends one sample short of the centre, so this is a
        # sub-nanometre correction, not a step. Sent anyway so the exit state is
        # stated rather than inferred.
        stage.set_position_pm(a.channel, start_pm)
        print(f"\n  returned to {stage.get_position_um(a.channel):.4f} um "
              f"(started at {start_pm / PM_PER_UM:.4f} um)")

    except (PiezoStageError, PiezoStageErrorLike, WaveformError) as exc:
        sys.stdout.flush()  # or a piped stderr overtakes the report above it
        print(f"\nREFUSED/FAILED: {exc}", file=sys.stderr)
        rc = 1
    finally:
        try:
            stage.disconnect()
        finally:
            stage.close()
    return rc


# =====================================================================
# cli
# =====================================================================


def add_sine_args(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--peak-to-peak-um", type=float, default=DEFAULT_PEAK_TO_PEAK_UM,
                   help="full swing, one extreme to the other (default: "
                        f"{DEFAULT_PEAK_TO_PEAK_UM:g})")
    g.add_argument("--amplitude-um", type=float, default=None,
                   help="half swing, i.e. +/-this. Use instead of "
                        "--peak-to-peak-um if that is the reading you meant")
    p.add_argument("--period-s", type=float, default=DEFAULT_PERIOD_S,
                   help=f"one full cycle (default: {DEFAULT_PERIOD_S:g} s = 1 Hz)")
    p.add_argument("--points", type=int, required=False,
                   help="samples per cycle (see each subcommand's default)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="subsystem", required=True)

    # ---- tweezers ----
    t = sub.add_parser("tweezers", help="Aresis Tweez 300, via a generated .tpf")
    add_sine_args(t)
    t.set_defaults(points=200)
    t.add_argument("--angle-deg", type=float, default=0.0,
                   help="direction of the sweep in the trap's frame (default: +x)")
    t.add_argument("--strength", type=float, default=1.0,
                   help="relative point strength, 0-1, multiplied by the trap's own")
    t.add_argument("--n-traps", type=int, default=1,
                   help="traps sharing the loop. MUST match the real project -- it "
                        "scales every time and speed linearly (default: 1)")
    t.add_argument("--trap", default="Trap 1", help="trap name in the Tweez project")
    t.add_argument("--pattern-name", default="Sine 1Hz")
    t.add_argument("--name", default="try-sine-1hz",
                   help="plan name, and the default .tpf stem")
    t.add_argument("--half-range-um", type=float, default=None,
                   help="calibrated trapping half-extent read off the GUI. Without "
                        "it the range check reports BLOCKED")
    t.add_argument("--objective", default=None,
                   help="objective the Tweez GUI calibration was taken with")
    t.add_argument("--field-objective", default=None,
                   help="objective the AOD trapping-field calibration was taken with")
    t.add_argument("--trap-x-um", type=float, default=None,
                   help="place the trap here instead of the origin")
    t.add_argument("--trap-y-um", type=float, default=None)
    t.add_argument("--out", type=Path, default=None,
                   help=".tpf output path (default: <name>.tpf beside this script)")
    t.add_argument("--tpf-on-scope", default=None,
                   help="absolute path the GUI should read the .tpf from")
    t.add_argument("--decimal", default=".", choices=[".", ","],
                   help="decimal separator, per the lab PC's Windows locale")
    t.add_argument("--file-first", action="store_true",
                   help="send LOAD_PATTERN file-first -- the manual contradicts "
                        "itself on the order")
    t.add_argument("--breakpoint-at", choices=sorted(BREAKPOINT_PHASES),
                   default=None,
                   help="halt the trap at this phase of the sine until "
                        "TRAP_PATT_RELEASE_BP or a hardware trigger releases "
                        "it. 'start' and 'centre' are both x=0 travelled in "
                        "opposite directions; 'max'/'min' are the turning "
                        "points, where the trap is already momentarily still")
    t.add_argument("--breakpoint-bits", type=int, default=1,
                   help="value written to colBP. 1 fits both the 1-bit "
                        "(SN < 130) and the 4-bit (SN >= 130) field, so it is "
                        "the safe choice while tweezers_patterns."
                        "BREAKPOINT_BITS is unread (default: 1)")
    t.add_argument("--blanking-us", type=float, default=0.0,
                   help="blanking time sent with BEAM_SET_PARAMS. That one "
                        "command carries the rate AND the blanking time, so a "
                        "0 here overwrites the GUI's standing value -- read it "
                        "off the GUI and pass it back (default: 0)")
    t.add_argument("--host", default="127.0.0.1")
    t.add_argument("--port", type=int, default=2070,
                   help="one port per running GUI instance, and each is bound to "
                        "its own camera and calibration (default: 2070)")
    t.add_argument("--wait-ready", type=float, default=None, metavar="SECONDS",
                   help="block until the GUI reports ready before sending")
    t.add_argument("--send", action="store_true",
                   help="microscope PC: send the TCP sequence (typed confirmation)")

    # ---- piezo ----
    p = sub.add_parser("piezo", help="Prior/Queensgate NPC-D, via the vendor DLL")
    add_sine_args(p)
    # 100 samples over 1 s is 10 ms per sample, which the measured round trip
    # above will tell you whether the link can hold.
    p.set_defaults(points=100)
    p.add_argument("--link", default="sim:/NPC6330",
                   help='COM port, IP, or "sim:/NPC6330" for the DLL\'s own '
                        "simulator (default). Start with the simulator")
    p.add_argument("--channel", type=int, default=1, help="1-based (default: 1)")
    p.add_argument("--cycles", type=int, default=3,
                   help="how many full cycles to play (default: 3)")
    p.add_argument("--centre-um", type=float, default=None,
                   help="centre the sine here. DEFAULT IS THE CURRENT MEASURED "
                        "POSITION, which is the safe choice on a Z piezo -- pass "
                        "this only if you have checked the clearance")
    p.add_argument("--travel-min-um", type=float, default=None,
                   help="real travel read off the controller; give both bounds")
    p.add_argument("--travel-max-um", type=float, default=None)
    p.add_argument("--resolution-um", type=float, default=32e-6,
                   help="smallest commandable step, um (default: 32e-6, i.e. 32 pm, "
                        "measured on COM4 2026-08-27 by stepping 2 pm at a time and "
                        "watching stage.position.command.get. The old 0.0122 default "
                        "was NIS's analogue step, 380x coarser)")
    p.add_argument("--unlock", default=None, metavar="CODE",
                   help="controller.security.user.set code; .set commands need the "
                        "security level raised")
    p.add_argument("--no-readback", action="store_true",
                   help="skip the position read after each sample -- halves the "
                        "round trips, and gives up the only verification there is")
    p.add_argument("--move", action="store_true",
                   help="microscope PC: actually oscillate (typed confirmation)")

    a = ap.parse_args()
    if a.points is not None and a.points < 4:
        ap.error("--points must be at least 4")
    if a.period_s <= 0:
        ap.error("--period-s must be positive")
    if amplitude_from_args(a) <= 0:
        ap.error("the amplitude must be positive")

    if a.subsystem == "tweezers":
        return run_tweezers(a)
    return run_piezo(a)


if __name__ == "__main__":
    sys.exit(main())
