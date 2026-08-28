"""Run whichever control surfaces are switched on, in parallel, on one clock.

    python config/session/run_parallel.py --dry-run --seconds 3
    python config/session/run_parallel.py --microscope DMD_dualcam_LUNF.cfg
    python config/session/run_parallel.py --microscope CFG --piezo COM4 --tweezers

The program shape does not change with what is plugged in. Name the subsystems
that are on; the microscope is always on and need not be named. An absent
subsystem's track is dropped, the camera handoff it would have needed is
skipped, and the report says what the record is consequently missing.

    (nothing)                microscope alone
    --piezo COM4             microscope + piezo, no camera handoff at all
    --tweezers               microscope + tweezers, full handoff
    --tweezers --piezo COM4  all three

READ-ONLY BY DEFAULT
--------------------
Nothing moves and nothing is armed unless a drive flag says so. The three
default tracks measure position (piezo), probe readiness (tweezers) and read a
property (microscope) -- all read-only, so this is safe to run with the laser
armed and a sample in place, and safe to run repeatedly while getting the
structure right. ``--releases N`` is the one drive path here; the piezo's lives
in ``config/piezo/run_sine_hold.py``, which is properly safety-gated, and is not
duplicated.

THE SETUP ORDER, AND WHY IT IS CONDITIONAL
------------------------------------------
    tweezers on   Tweez GUI takes the camera -> calibration and trap setup ->
                  release -> Micro-Manager loads its configuration
    tweezers off  Micro-Manager loads its configuration

PVCAM hands a Kinetix to one process at a time, so the first order is forced.
The second is the same statement with nothing in front of it: if the Tweez GUI
is not running then nothing ever holds the camera and there is no handoff to
wait for. ``hardware.orchestrator.Session`` enforces whichever of the two the
roster implies.

ONE TIMESTAMP ACROSS THREE CLOCKS
---------------------------------
The host clock makes host events comparable. It is not what times the
experiment -- each subsystem has its own clock, and they meet only at the moment
one of them starts. So every timed run here is bracketed by
``Timeline.anchor()``, which records the host time of that start together with
half the start command's round trip as its uncertainty, and every later time
comes from the run's own rate rather than from a fresh host stamp.

``alignment_error_s`` then states what may be claimed across two subsystems.
Expect a few milliseconds, which is a fraction of a sample at 1 Hz and several
frames at 500 fps. Tightening it is a hardware-trigger job
(``function.trigger-inputs.*``, ``/Dev1/PFI0``), not a Python job.

WHAT IS NOT HERE
----------------
**Camera frames.** The microscope track reads properties; it does not acquire.
The camera's authoritative clock is MM's per-frame ``ElapsedTime-ms`` series,
which is the right thing to anchor a sequence against -- but every device
adapter in the lab's Micro-Manager install currently fails to load against
pymmcore 12.5 (device API 75), so no acquisition path can be tested from this
repo yet. ``mmcore install`` is the fix and is already on the open list; see
`kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md` section 8.
An untested acquisition path is worse than a missing one, so this is a marked
gap rather than a guess. ``scheduled_loop`` is where it would go.

**Trap position.** Reading it back needs the Tweez GUI to hold the camera and to
be tracking, which is exactly what the handoff gives away. Unresolved, same
reference.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.orchestrator import (  # noqa: E402
    HARDWARE,
    HOST_SCHED,
    MICROSCOPE,
    PIEZO,
    TWEEZERS,
    OrchestratorError,
    Session,
    track_report,
)

#: How much of each wait is spun rather than slept. ``time.sleep`` overshoots,
#: and the overshoot lands in the data -- so the tail has to be spun, and the
#: window has to be **wider than the platform's overshoot** or the spin never
#: gets a turn.
#:
#: Measured 2026-08-27, 20 samples of ``sleep(48 ms)`` and a 50 ms schedule:
#:
#:   Windows, microscope PC   ~1 ms resolution. A 2 ms tail is enough, and the
#:                            piezo's 60 s 1 Hz run confirms it: slip median
#:                            1 us, max 1.07 ms, 0/6000 overruns.
#:   macOS, this dev box      overshoot median 2.9 ms, max 5.0 ms. A 2 ms tail
#:                            is *inside* the overshoot, so it never runs and
#:                            slip sits at 2.2 ms. At 6 ms: 2 us.
#:
#: Spinning holds the GIL, so concurrent tracks were checked rather than
#: assumed: at a 6 ms window and a 50 ms period, 1/2/3/4 concurrent tracks
#: slipped a median of 3.9/4.8/4.6/3.1 us with a worst case of 16/75/90/87 us
#: and no overruns. Threads do not degrade the schedule, which is the
#: assumption the whole parallel structure rests on.
_SPIN_S = 0.006 if sys.platform == "darwin" else 0.002


def wait_until(target_s: float, spin_s: float = _SPIN_S) -> None:
    """Sleep to just short of ``target_s`` (a ``perf_counter`` value), then spin."""
    while True:
        remaining = target_s - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > spin_s:
            time.sleep(remaining - spin_s)


def scheduled_loop(
    session: Session,
    subsystem: str,
    stop,
    *,
    label: str,
    op_name: str,
    period_s: float,
    n: int,
    step: Callable[[int], object],
    spin_s: float = _SPIN_S,
) -> dict:
    """Run ``step`` ``n`` times at ``period_s``, on absolute deadlines from one t0.

    Absolute deadlines, not ``sleep(period)``: a slow round trip then costs one
    late sample instead of pushing every later sample out. That is what made
    the piezo's 60 s run land 0/6000 overruns with a median slip of 1 us, and it
    is the only reason a host-scheduled drive is usable at all.

    The loop is anchored ``HOST_SCHED`` -- it is a schedule, not a clock. Swap
    a ``.set`` in for ``step`` and this becomes a drive with the same timing
    properties; that is the one-line change, and ``config/piezo/run_sine_hold.py``
    is the worked version with the safety gates a drive needs.
    """
    # Anchor first: the schedule's zero is what everything else aligns to, and
    # bracketing it is what puts a number on the alignment.
    with session.timeline.anchor(
        subsystem, label, clock=HOST_SCHED, rate_hz=1.0 / period_s
    ):
        t0 = time.perf_counter()

    overruns, slips, done = 0, [], 0
    for i in range(n):
        if stop.is_set():
            session.timeline.mark(subsystem, "loop stopped early", f"at step {i}")
            break
        deadline = t0 + i * period_s
        wait_until(deadline, spin_s)
        slip = time.perf_counter() - deadline
        slips.append(slip)
        if slip > period_s:
            overruns += 1
        with session.instrument(subsystem, op_name):
            step(i)
        done += 1

    return {
        "steps": done,
        "overruns": overruns,
        "slip_median_ms": (
            round(1e3 * sorted(slips)[len(slips) // 2], 4) if slips else 0.0
        ),
        "slip_max_ms": round(1e3 * max(slips), 4) if slips else 0.0,
    }


# ---- setup: open what is on the roster, in the order the camera forces ----


def setup_tweezers(session: Session, args) -> object:
    """Phase 1. The GUI holds the camera; do the things that need a live image.

    The TCP link is separate from the camera, so opening it here costs nothing
    and proves the GUI is answering before the microscope takes the Kinetix --
    which is when it is cheap to find out.
    """
    from hardware.optical_tweezers import OpticalTweezers

    with session.instrument(TWEEZERS, "connect"):
        tweez = OpticalTweezers(host=args.host, port=args.port)
    with session.instrument(TWEEZERS, "wait_until_ready"):
        tweez.wait_until_ready(timeout=args.ready_timeout_s)
    session.timeline.mark(TWEEZERS, "GUI answering", f"port {args.port}")

    if args.project:
        # Restores every GUI-only property at once -- breakpoint enable bits,
        # repeat, wait states, trap group, calibration. Save the template with
        # the laser OFF; a project carries laser state (manual p.65).
        with session.instrument(TWEEZERS, "LOAD_PROJECT"):
            status = tweez.load_project(args.project)
        session.timeline.mark(TWEEZERS, "project loaded", f"{args.project} -> {status}")
        if status != 0:
            raise OrchestratorError(
                f"LOAD_PROJECT returned {status} for {args.project!r}. It returns "
                "0 even on a partial load, so a non-zero is unambiguous: stop"
            )
    return tweez


def setup_microscope(session: Session, args) -> object:
    """Phase 3. The camera is free, so a configuration may be loaded."""
    from hardware.microscope import Microscope

    with session.instrument(MICROSCOPE, "connect (load config)"):
        scope = Microscope.connect(args.microscope, mm_dir=args.mm_dir)
    with session.instrument(MICROSCOPE, "state() full read"):
        state = scope.state()

    objective = state.get("Nosepiece") or state.get("Objective")
    session.state.set("objective", objective)
    session.timeline.mark(MICROSCOPE, "objective", str(objective))
    return scope


def check_objective(session: Session, args) -> None:
    """Refuse a run whose objective is not the one the tweezers were calibrated at.

    Only the coordinator can make this check: the objective is readable from
    Micro-Manager and the calibration it invalidates lives in the Tweez GUI,
    where it is neither readable nor announced. Both GUI calibrations --
    magnification and beam position -- die silently on an objective change, and
    the traps then land somewhere other than where they are commanded.
    """
    if not (session.has(TWEEZERS) and args.calibrated_objective):
        return
    objective = session.state.get("objective")
    if objective is None:
        session.timeline.mark(
            MICROSCOPE, "objective unknown", "cannot check the tweezers calibration"
        )
        print("   WARNING: no objective reported, so the tweezers calibration "
              "could not be checked", file=sys.stderr)
        return
    if str(objective) != args.calibrated_objective:
        raise OrchestratorError(
            f"objective is {objective!r} but the tweezers calibration was taken "
            f"at {args.calibrated_objective!r}. Both GUI calibrations are void "
            "and neither is readable -- recalibrate, or pass the objective "
            "actually in use"
        )
    session.timeline.mark(TWEEZERS, "calibration objective confirmed", str(objective))


def setup_piezo(session: Session, args) -> object:
    """Read-only: no unlock, no motion. ``allow_motion`` stays False."""
    from hardware.piezo_stage import PiezoStage

    with session.instrument(PIEZO, "load DLL"):
        stage = PiezoStage(allow_motion=False)
    with session.instrument(PIEZO, f"connect {args.piezo}"):
        stage.connect(args.piezo)
    with session.instrument(PIEZO, "identity"):
        identity = stage.identity()
    session.timeline.mark(PIEZO, "connected", f"{args.piezo}: {identity}")
    return stage


# ---- tracks: one per subsystem, all released from one barrier -------------


def microscope_track(scope, args):
    def body(session: Session, stop) -> dict:
        device, prop = _pick_readable(scope)
        return scheduled_loop(
            session, MICROSCOPE, stop,
            label=f"property poll {device}.{prop}",
            op_name=f"getProperty {device}.{prop}",
            period_s=args.period_s, n=args.steps, spin_s=args.spin_s,
            step=lambda i: scope.core.getProperty(device, prop),
        )

    return body


def _pick_readable(scope) -> tuple[str, str]:
    for device, kind in scope.devices().items():
        if kind == "StateDevice":
            return device, "Label"
    return "Core", "TimeoutMs"


def tweezers_track(tweez, args):
    """Readiness probes, or the breakpoint-release protocol with ``--releases``.

    The probe is ``TRAP_DELETE`` against a sentinel name: -22 proves a live GUI
    and changes nothing, which is the only query a write-only protocol allows.
    """
    def body(session: Session, stop) -> dict:
        if not args.releases:
            return scheduled_loop(
                session, TWEEZERS, stop,
                label="readiness probe",
                op_name="probe (TRAP_DELETE, no-op)",
                period_s=args.period_s, n=args.steps, spin_s=args.spin_s,
                step=lambda i: session.state.set(
                    "tweezers_last_status", tweez.probe()
                ),
            )
        return _release_protocol(session, tweez, stop, args)

    return body


def _release_protocol(session: Session, tweez, stop, args) -> dict:
    """Hold ``--hold-s`` at the breakpoint, release, repeat -- host-timed.

    Travel is hardware-clocked by the AOD trap loop and exact; only the release
    is host-timed, and a 3.000 s gap has been measured landing at +3 us. Being
    late is harmless (the trap waits at the breakpoint indefinitely, so the hold
    just runs long). Being early is the untested failure mode, so every wait is
    computed from the hardware clock rather than guessed.

    ``TRAP_PATT_RELEASE_BP`` answers 0 whether or not the trap was waiting, so
    nothing here can confirm a step happened. Confirm at the GUI.
    """
    from hardware.optical_tweezers import _RETURN_CODES

    cycle_s = args.points / args.switching_hz
    to_breakpoint_s = args.breakpoint_index / args.switching_hz

    # Re-assigning restarts the traversal, which is what defines t0. Anchored
    # HARDWARE: from here the AOD loop carries the timing, not the host.
    with session.timeline.anchor(
        TWEEZERS,
        f"pattern {args.pattern!r} on {args.trap!r}",
        clock=HARDWARE,
        rate_hz=args.switching_hz,
    ):
        status = tweez.send_command(
            f'TRAP_ASSIGN_PATTERN "{args.trap}" "{args.pattern}"'
        )
        t0 = time.perf_counter()
    if status != 0:
        raise OrchestratorError(
            f"TRAP_ASSIGN_PATTERN -> {status} "
            f"({_RETURN_CODES.get(status, 'unknown')}); nothing below would mean "
            "anything"
        )

    errors_ms = []
    for i in range(args.releases):
        if stop.is_set():
            session.timeline.mark(TWEEZERS, "releases stopped early", f"at {i}")
            break
        arrive_at = t0 + to_breakpoint_s + i * (args.hold_s + cycle_s)
        wait_until(arrive_at + args.hold_s, args.spin_s)
        sent = time.perf_counter()
        with session.instrument(TWEEZERS, "TRAP_PATT_RELEASE_BP"):
            status = tweez.release_pattern_breakpoint(args.trap)
        held = sent - arrive_at
        errors_ms.append(1e3 * (held - args.hold_s))
        session.timeline.mark(
            TWEEZERS, f"release {i + 1}",
            f"held {held:.3f} s, err {errors_ms[-1]:+.1f} ms, status {status}",
        )
        if status != 0:
            raise OrchestratorError(
                f"release {i + 1} refused ({status}); the run is no longer the "
                "protocol described"
            )
    return {
        "releases": len(errors_ms),
        "hold_err_max_ms": max((abs(e) for e in errors_ms), default=0.0),
        "note": "no readback exists -- confirm the holds at the GUI",
    }


def piezo_track(stage, args):
    def body(session: Session, stop) -> dict:
        return scheduled_loop(
            session, PIEZO, stop,
            label=f"position poll, channel {args.piezo_channel}",
            op_name="position.measured.get",
            period_s=args.period_s, n=args.steps, spin_s=args.spin_s,
            step=lambda i: session.state.set(
                "piezo_um", stage.get_position_um(args.piezo_channel)
            ),
        )

    return body


def stub_track(subsystem: str, args, cost_s: float):
    """Stand-in with a known cost, so ``--dry-run`` exercises the machinery."""
    def body(session: Session, stop) -> dict:
        return scheduled_loop(
            session, subsystem, stop,
            label=f"stub {subsystem}",
            op_name="stub op",
            period_s=args.period_s, n=args.steps, spin_s=args.spin_s,
            step=lambda i: time.sleep(cost_s),
        )

    return body


# ---- driving --------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the switched-on control surfaces in parallel on one clock."
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="stub every subsystem, no hardware. Runs anywhere")
    ap.add_argument("--tweezers", action="store_true", help="the Tweez 300 GUI is up")
    ap.add_argument("--microscope", type=Path, metavar="CFG", default=None,
                    help="MM system configuration (omit for the bundled demo)")
    ap.add_argument("--piezo", metavar="LINK", default=None,
                    help='NPC-D link: a bare port name like COM4, or sim:/NPC6330')
    ap.add_argument("--seconds", type=float, default=5.0, help="run length")
    ap.add_argument("--period-s", type=float, default=0.010,
                    help="poll period per track (default 10 ms, ~14x the piezo "
                         "round trip)")
    ap.add_argument("--out", type=Path, default=None, metavar="CSV",
                    help="write the merged timeline here")
    ap.add_argument("--spin-ms", type=float, default=1e3 * _SPIN_S,
                    help=f"busy-wait tail; must exceed the platform's sleep "
                         f"overshoot (default {1e3 * _SPIN_S:g} ms here)")

    g = ap.add_argument_group("tweezers")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=2070,
                   help="also selects which camera and calibration you drive")
    g.add_argument("--ready-timeout-s", type=float, default=30.0)
    g.add_argument("--project", default=None,
                   help="absolute path to a .tpf project, saved LASER OFF")
    g.add_argument("--calibrated-objective", default=None,
                   help="the objective the GUI calibration was taken at; the run "
                        "is refused if the microscope reports a different one")
    g.add_argument("--releases", type=int, default=0,
                   help="run the breakpoint-release protocol this many times")
    g.add_argument("--trap", default="Trap 1")
    g.add_argument("--pattern", default="Sine 1Hz BP max")
    g.add_argument("--points", type=int, default=50_000)
    g.add_argument("--switching-hz", type=float, default=50_000.0)
    g.add_argument("--breakpoint-index", type=int, default=12_500)
    g.add_argument("--hold-s", type=float, default=2.0)

    g = ap.add_argument_group("microscope / piezo")
    g.add_argument("--mm-dir", type=Path, default=None)
    g.add_argument("--piezo-channel", type=int, default=1)

    args = ap.parse_args()
    args.steps = max(1, int(round(args.seconds / args.period_s)))
    args.spin_s = args.spin_ms / 1e3

    # A --dry-run with no subsystem named stubs all three; name some and it
    # honours them, so the tweezers-off path is exercisable with no hardware.
    stub_all = args.dry_run and not (args.tweezers or args.piezo)
    present = []
    if args.tweezers or stub_all:
        present.append(TWEEZERS)
    if args.piezo or stub_all:
        present.append(PIEZO)
    session = Session(*present)

    print(f"roster           {session.roster}")
    print(f"clock anchored   wall {session.clock.anchor[0]:.3f}")
    print(f"plan             {args.steps} steps x {1e3 * args.period_s:.1f} ms "
          f"= {args.seconds:.1f} s per track "
          f"(spin tail {args.spin_ms:g} ms)")

    tweez = scope = stage = None
    try:
        # -- setup, in whichever order the roster implies -------------------
        if session.has(TWEEZERS):
            print("\n-- phase 1: the tweezers GUI holds the camera -------------")
            with session.tweezers_setup():
                tweez = None if args.dry_run else setup_tweezers(session, args)
            print(f"   camera released; phase now {session.phase.name}")
        else:
            print("\n-- no tweezers: nothing holds the Kinetix -----------------")
            print("   so there is no handoff, and the microscope comes up now")

        print("\n-- phase 3: the microscope loads its configuration --------")
        session.microscope_setup()
        if not args.dry_run:
            scope = setup_microscope(session, args)
            check_objective(session, args)
        if session.has(PIEZO) and not args.dry_run:
            stage = setup_piezo(session, args)

        session.start_running()
        print(f"   phase {session.phase.name}")

        # -- the parallel part. An absent subsystem drops out here ----------
        if args.dry_run:
            session.add_track(MICROSCOPE, stub_track(MICROSCOPE, args, 0.0001))
            session.add_track(TWEEZERS, stub_track(TWEEZERS, args, 0.0002))
            session.add_track(PIEZO, stub_track(PIEZO, args, 0.0004))
        else:
            session.add_track(MICROSCOPE, microscope_track(scope, args))
            if session.has(TWEEZERS):
                session.add_track(TWEEZERS, tweezers_track(tweez, args))
            if session.has(PIEZO):
                session.add_track(PIEZO, piezo_track(stage, args))

        print(f"\n-- running {len(session.tracks)} tracks in parallel "
              f"-------------------")
        results = session.run_tracks(join_timeout_s=args.seconds + 120.0)
    finally:
        if stage is not None:
            try:
                stage.disconnect()
            except Exception as exc:  # noqa: BLE001
                print(f"   on piezo disconnect: {exc}", file=sys.stderr)
        for handle in (tweez, scope, stage):
            if handle is not None:
                try:
                    handle.close()
                except Exception as exc:  # noqa: BLE001
                    print(f"   on close: {exc}", file=sys.stderr)

    # -- report ------------------------------------------------------------
    print("\n-- tracks -------------------------------------------------")
    print(track_report(results))

    print("\n-- alignment ----------------------------------------------")
    anchors = session.timeline.anchors
    if len(anchors) < 2:
        print("   fewer than two anchors: nothing to align")
    else:
        for i, a in enumerate(anchors):
            for b in anchors[i + 1:]:
                if a.subsystem == b.subsystem:
                    continue
                err_ms = 1e3 * session.timeline.alignment_error_s(
                    a.subsystem, b.subsystem
                )
                print(f"   {a.subsystem:11} <-> {b.subsystem:11} "
                      f"{err_ms:8.3f} ms  worst case")
        # The anchor budget is only half the story for a host-scheduled run:
        # its zero is known well, but every later step carries the schedule's
        # slip. Report both so the number is not read as the whole budget.
        scheduled = [a for a in anchors if a.clock == HOST_SCHED]
        if scheduled:
            worst_slip_ms = max(
                (r.value or {}).get("slip_max_ms", 0.0)
                for r in results.values()
                if r.ok and isinstance(r.value, dict)
            )
            print(f"\n   + up to {worst_slip_ms:.3f} ms of schedule slip on the "
                  f"{len(scheduled)} host-scheduled track(s):")
            print("     their zeros are known, but each later step is only as")
            print("     punctual as Windows. A HARDWARE anchor has no such term.")
        print("\n   That is the bound on any claim tying two subsystems to the")
        print("   same instant. A hardware trigger is what shrinks it.")

    print("\n-- timeline -----------------------------------------------")
    print(session.timeline.report())

    print("\n-- latency ------------------------------------------------")
    print(session.latency.report())

    print("\n-- shared state -------------------------------------------")
    for key, (stamp, value) in sorted(session.state.snapshot().items()):
        print(f"   {key:22} = {value!r}   (t={stamp:.4f}s)")

    for line in session.roster.missing_from_record():
        print(f"\n   NOT MEASURED -- {line}")

    if args.out:
        out = session.timeline.to_csv(args.out, session.latency)
        print(f"\n   timeline -> {out}")

    return 0 if all(r.ok for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
