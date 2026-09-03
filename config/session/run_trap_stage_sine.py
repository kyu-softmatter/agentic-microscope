"""The three subsystems driven together: trap sine on y, stage sine on x, one video.

    # plan only -- opens nothing, sends nothing
    python config/session/run_trap_stage_sine.py --objective 100x --blanking-us 5

    # the real thing
    python config/session/run_trap_stage_sine.py --objective 100x --blanking-us 5 \
        --run --unlock 0xDEC0DED

The experiment this exists for (user, 2026-09-03): a 5 um PS bead trapped at the
image centre, the **optical trap** driven sinusoidally in y at 10 um amplitude
and 1 Hz, the **piezo stage** driven identically in x at the same moment, and a
30 fps timestamped video of the result for 5 s.

WHAT IS ACTUALLY BEING MEASURED, AND WHY THAT DECIDES THE DESIGN
---------------------------------------------------------------
The bead's y-motion comes from following the trap; its x-motion comes from the
fluid being dragged past it. Both are 1 Hz. **The quantity of interest is the
phase and amplitude of the bead relative to each drive** -- which makes the
relative timing of the two drives the measurement, not a detail of it.

That is why the drives are not started symmetrically:

    trap    hardware-timed. 50,000 points at 50 kHz is 1.000 s per cycle,
            exact rather than nominal, once released from its breakpoint. But
            the *release* is one TCP command, and that link measured a 10.5 ms
            median and 60.1 ms worst-case round trip under three-subsystem
            load (2026-09-03). 60 ms is 6% of a cycle.
    piezo   host-timed, and far tighter: 0.68 ms per set, 0.38 ms worst-case
            schedule slip over 5 s.

So the trap release goes **first** and its host time is anchored, and the piezo
start is then *scheduled relative to that anchor* rather than fired blind. The
phase offset between the two drives is consequently limited by the release
anchor's uncertainty -- half a round trip, about +/-5 ms, or 0.5% of a cycle --
instead of by the full 60 ms.

WHAT THIS CANNOT CLAIM
----------------------
**Where the trap actually was.** `TRAP_PATT_RELEASE_BP` answers 0 whether the
trap was waiting at the breakpoint or the pattern had already finished, and the
TCP interface has no position readback at all. Nothing here confirms a given
pass happened. The trap trajectory in the record is *computed* from the pattern
and the release anchor, and is labelled as computed.

**That the trap and the camera share a clock.** They do not. The camera's clock
is MM's per-frame ``ElapsedTime-ms``; the trap's is the AOD loop. They meet only
through the host stamp at the release, and ``TimeReceivedByCore`` on every frame
is what ties the camera series to that same wall clock. A hardware trigger is
what would remove the host from the path -- ``function.trigger-inputs.*`` and
``/Dev1/PFI0`` -- and that is not wired.

**The trap's calibration.** ``--objective`` is required and unvalidatable: the
Tweez GUI's px->um magnification and its AOD field response are neither readable
nor settable over TCP, so if the GUI was calibrated at a different objective
every commanded micrometre is wrong by that ratio and the drive still returns 0.
The value is recorded, not checked.

SAFETY
------
Nothing moves without ``--run``. ``--run`` additionally needs ``--unlock`` for
the piezo, because the whole ``.set`` half of the NPC-D command set is invisible
at the base security level. The trajectory is range-checked against the travel
the controller reports and **refuses** rather than clipping, centred on the
axis's current measured position.

No ``LASER_ON`` is sent -- arm at the GUI. ``TRAP_OFF`` and ``LASER_OFF`` are
never sent either, including on the exit path: the trap is the expensive thing
to re-establish and dropping a bead to tidy up is not a cleanup (user,
2026-09-03). The excitation light *is* taken down, because leaving it on
bleaches the sample and nothing depends on it.

``--blanking-us`` has no default on purpose. ``BEAM_SET_PARAMS`` carries the
switching rate **and** the blanking time in one command, so any value sent here
overwrites the GUI's standing one; it has to be read off the GUI and passed back.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from calibration.timestamped_capture import capture_timestamped  # noqa: E402
from hardware.optical_tweezers import (  # noqa: E402
    OpticalTweezers,
    _RETURN_CODES,
    find_gui_port,
)
from hardware.orchestrator import (  # noqa: E402
    HARDWARE,
    HOST_SCHED,
    MICROSCOPE,
    PIEZO,
    TWEEZERS,
    Clock,
    Timeline,
)
from hardware.piezo_stage import ACCESS_CODES, PiezoStage  # noqa: E402

#: Spun rather than slept, so ``sleep`` overshoot does not land in the data.
#: 2 ms is enough on this PC -- measured 1 us median slip, 1.07 ms max over a
#: 60 s 1 Hz piezo run (config/session/run_parallel.py _SPIN_S).
_SPIN_S = 0.002

#: Ti2-E turret shutters, in series -- either closed is a black frame, and
#: Turret2Shutter is also the 1064 coupling path. Opened, never closed here.
_TURRET_SHUTTERS = ("Turret1Shutter", "Turret2Shutter")


def wait_until(target_s: float) -> None:
    """Sleep to just short of a ``perf_counter`` value, then spin."""
    while True:
        remaining = target_s - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > _SPIN_S:
            time.sleep(remaining - _SPIN_S)


def sine_samples(centre_um: float, amplitude_um: float, n_per_cycle: int,
                 cycles: int) -> list[float]:
    """One sine, starting at the centre going positive -- the same phase as the
    trap pattern's breakpoint, which sits at point 0 = the zero crossing.

    **Closed with a final sample back at the centre.** Without it the last
    sample is index ``n*cycles - 1``, one step short of completing the cycle,
    so the axis parks off-centre -- measured 2026-09-03: a 5-cycle 100-point
    run about 300.024 um ended at 298.499 um, 1.5 um low. Harmless once and a
    creeping bias over a series, since each run re-centres on wherever the last
    one stopped. One extra sample costs one ``dt`` and removes the drift.
    """
    samples = [
        centre_um + amplitude_um * math.sin(2 * math.pi * i / n_per_cycle)
        for i in range(n_per_cycle * cycles)
    ]
    samples.append(centre_um)
    return samples


def _on_camera_clock(result, clock, *, stage_t0_perf, trap_t0_perf, release_rt_s):
    """Both drive zeros expressed in ``ElapsedTime-ms``, like every frame.

    This is the form that makes phase a subtraction instead of a correlation.
    The camera's zero is not a frame -- frame 0 already carries a nonzero
    ``ElapsedTime-ms`` (139 ms in one measured run, being exposure plus
    delivery) -- so it is recovered as::

        camera_t0_wall = frame0.TimeReceivedByCore - frame0.ElapsedTime-ms

    and a host ``perf_counter`` reading converts into the same wall clock
    through ``clock.anchor``. The two subtract to give the drive's start in the
    camera's own milliseconds.

    Returned as ``None`` if frame 0 is missing either tag, because a phase
    computed against a guessed zero is worse than an absent one.
    """
    if not result.records:
        return None
    first = result.records[0]
    if first.elapsed_ms is None or first.received_by_core is None:
        return None
    from datetime import datetime  # noqa: PLC0415

    frame0_wall = datetime.fromisoformat(first.received_by_core).timestamp()
    camera_t0_wall = frame0_wall - first.elapsed_ms / 1000.0
    wall0, perf0 = clock.anchor

    def elapsed_ms_of(perf_s):
        if perf_s is None:
            return None
        wall = wall0 + (perf_s - perf0)
        return 1000.0 * (wall - camera_t0_wall)

    return {
        "camera_t0_wall": camera_t0_wall,
        "frame0_elapsed_ms": first.elapsed_ms,
        "frame0_received_by_core": first.received_by_core,
        "stage_t0_elapsed_ms": elapsed_ms_of(stage_t0_perf),
        "trap_release_elapsed_ms": elapsed_ms_of(trap_t0_perf),
        "trap_release_uncertainty_ms": 1000.0 * release_rt_s / 2,
        "stage_uncertainty_ms": 1000.0 * _SPIN_S,
        "note": "milliseconds on the camera's own ElapsedTime-ms scale -- the "
                "same axis the timestamps CSV is indexed by. Phase = "
                "360 * (t - drive_t0_ms) / (1000 * period_s).",
    }


def write_run_record(args, result, timeline, clock, piezo_report, *,
                     piezo_t0, release_rt_s, switching_hz, centre_um,
                     onset_frame=None, lead_frames=0, trap_t0_perf=None):
    """Everything needed to put both drives on the camera's clock afterwards.

    Written because the first version of this script did not, and the phase came
    out unrecoverable: the piezo's zero lived in ``perf_counter`` and died with
    the process, so a measured bead phase of +106.7 deg could not be checked
    against the 85.6 deg the model wanted -- the 21 deg gap was probably the
    50 ms piezo lead (18 deg at 1 Hz) but "probably" is not a measurement
    (2026-09-03).

    ``clock.anchor`` is the pairing that makes it work: one ``(time.time(),
    perf_counter())`` taken at startup, so any ``perf_counter`` stamp here
    converts to the wall clock that every frame's ``TimeReceivedByCore`` is
    already in. Phase then comes from subtraction rather than from assumption.

    **TWO TIME CONVENTIONS MEET HERE, AND MIXING THEM IS SILENT.** The first
    version of this function did mix them and put the marks 15 minutes after the
    frames they were supposed to bracket (measured 2026-09-03):

        Mark.t_s          RELATIVE -- ``Clock.now_s()`` is already
                          ``perf_counter() - clock._t0``. Convert with
                          ``clock.wall_of()``, which the orchestrator provides
                          for exactly this.
        piezo_t0 here     ABSOLUTE -- a raw ``perf_counter()`` value taken at
                          the release. Convert by subtracting ``anchor[1]``
                          first.

    Subtracting the anchor from a value that had already been relativised is a
    ~900 s error that looks like a timestamp, which is why both conversions are
    named rather than inlined.
    """
    wall0, perf0 = clock.anchor

    def abs_perf_to_wall(perf_s):
        """For raw ``perf_counter()`` readings."""
        return wall0 + (perf_s - perf0)

    record = {
        "drive": {
            "amplitude_um": args.amplitude_um,
            "period_s": args.period_s,
            "cycles": args.cycles,
            "piezo_points_per_cycle": args.piezo_points,
            "piezo_channel": args.channel,
            "piezo_centre_um": centre_um,
            "trap_driven": not args.no_trap,
            "trap": args.trap,
            "pattern": args.pattern,
            "pattern_points": args.pattern_points,
            "switching_hz_commanded": None if args.keep_blanking else switching_hz,
            "beam_set_params_sent": not (args.keep_blanking or args.no_trap),
            "blanking_us": args.blanking_us,
        },
        "calibration": {
            # Recorded, never checked -- neither Tweez calibration is readable
            # over TCP. See the module docstring.
            "tweezers_gui_objective": args.objective,
            "pixel_size_um": 0.065,
            "pixel_size_provenance": "nominal 6.5/100, NOT a graticule measurement",
        },
        "clock": {
            "wall_at_perf0": wall0,
            "perf0": perf0,
            "note": "add (perf - perf0) to wall_at_perf0 to get the wall clock "
                    "that frame TimeReceivedByCore is in",
        },
        "zeros": {
            # The frame after which the drives were fired. Its ElapsedTime-ms
            # in the timestamps CSV is the drive t0 on the CAMERA clock, to
            # within one frame period -- and with the lead's flat baseline the
            # onset can be fitted from the trajectory to better than that.
            "drive_fired_after_frame": onset_frame,
            "lead_frames": lead_frames,
            "stage_t0_perf_s": piezo_t0,
            "stage_t0_wall": abs_perf_to_wall(piezo_t0),
            "trap_release_t0_perf_s": trap_t0_perf,
            "trap_release_t0_wall": (
                None if trap_t0_perf is None else abs_perf_to_wall(trap_t0_perf)
            ),
            "trap_release_round_trip_s": release_rt_s,
            "trap_t0_uncertainty_s": release_rt_s / 2,
        },
        # The form to actually use: both zeros in the camera's own milliseconds.
        "zeros_on_camera_clock": _on_camera_clock(
            result, clock, stage_t0_perf=piezo_t0,
            trap_t0_perf=trap_t0_perf, release_rt_s=release_rt_s,
        ),
        "piezo": dict(piezo_report),
        "camera": {
            "n_captured": result.n_captured,
            "achieved_fps": result.achieved_fps,
            "first_frame_received_by_core": result.records[0].received_by_core,
            "first_frame_elapsed_ms": result.records[0].elapsed_ms,
        },
        # Marks are RELATIVE clock readings -> clock.wall_of(), never
        # abs_perf_to_wall(). See the docstring.
        "marks": [
            {"subsystem": m.subsystem, "event": m.event, "detail": m.detail,
             "t_clock_s": m.t_s, "t_wall": clock.wall_of(m.t_s)}
            for m in timeline._marks
        ],
    }
    path = Path(str(args.out) + "_run.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n",
                    encoding="utf-8")
    return path


def run_piezo_sine(stage, channel, samples, dt_s, t0_s, timeline, report):
    """Play the sine on a host schedule anchored at ``t0_s``."""
    overruns = 0
    slips = []
    for i, target_um in enumerate(samples):
        due = t0_s + i * dt_s
        wait_until(due)
        actual = time.perf_counter()
        slips.append(actual - due)
        if actual - due > dt_s:
            overruns += 1
        stage.set_position_um(channel, target_um)
    timeline.mark(PIEZO, "sine end", f"{len(samples)} samples")
    slips.sort()
    report.update(
        samples=len(samples),
        overruns=overruns,
        slip_median_ms=1e3 * slips[len(slips) // 2],
        slip_max_ms=1e3 * slips[-1],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cfg", type=Path,
                    default=REPO / "config/micromanager/single_cam_red_noDMD.cfg")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:\Kyu Hwan Choi\agentic_microscope\2026-09-03")
                    / "trap-stage-sine-001")

    g = ap.add_argument_group("the drive")
    g.add_argument("--amplitude-um", type=float, default=10.0)
    g.add_argument("--period-s", type=float, default=1.0)
    g.add_argument("--cycles", type=int, default=5)
    g.add_argument("--piezo-points", type=int, default=100,
                   help="piezo samples per cycle (default 100 = 10 ms, 14x the "
                        "0.68 ms round trip)")
    g.add_argument("--pattern-points", type=int, default=50_000,
                   help="points in the loaded .tpf -- MUST match it, it sets the rate")

    g = ap.add_argument_group("camera")
    g.add_argument("--roi", type=int, default=512)
    g.add_argument("--roi-centre", type=int, nargs=2, default=None,
                   metavar=("X", "Y"),
                   help="sensor pixel to centre the ROI on. Defaults to the "
                        "sensor centre, which is only right if the trap is at "
                        "the sensor centre -- and TRAP_REMOVE_PATTERN parks the "
                        "trap wherever the pattern had it, so after a detach it "
                        "is not. Measured 2026-09-03: the trap ended up 14.1 um "
                        "(217 px) low, leaving 56 px of margin against a "
                        "+/-154 px y drive, and the bead was driven out of "
                        "frame. Moving the ROI is the fix that does not touch "
                        "the bead; a 14 um TRAP_POSITION step would simply drop "
                        "it, being far outside the capture range")
    g.add_argument("--fps", type=float, default=30.0)
    g.add_argument("--lead-s", type=float, default=1.0,
                   help="quiet video BEFORE the drives start (default 1.0 s). "
                        "The point is not padding: with a flat baseline the "
                        "onset of bead motion is fittable from the trajectory, "
                        "so the drive t0 comes from the camera's own clock "
                        "instead of from a host stamp")
    g.add_argument("--trail-s", type=float, default=0.5,
                   help="quiet video AFTER the drives finish (default 0.5 s), "
                        "which also shows the bead settling back")
    g.add_argument("--light-device", default="Aura")
    g.add_argument("--line", default="GREEN")
    g.add_argument("--intensity", type=float, default=50.0,
                   help="per-mille, 0-1000 (default 50 = 5%%)")

    g = ap.add_argument_group("tweezers -- all GUI-only reads")
    g.add_argument("--trap", default="Trap 1")
    g.add_argument("--pattern", default="Sine 1Hz Y")
    g.add_argument("--objective", default=None,
                   help="objective the Tweez GUI calibration was taken with. "
                        "Recorded, NOT checkable from here. Required unless "
                        "--no-record, since only a saved file can carry a wrong "
                        "provenance claim forward")
    g.add_argument("--blanking-us", type=float, default=None,
                   help="the GUI's standing blanking time. BEAM_SET_PARAMS "
                        "overwrites it, so it must be read off the GUI")
    g.add_argument("--keep-blanking", action="store_true",
                   help="skip BEAM_SET_PARAMS entirely, clobbering nothing. "
                        "The cost: the switching rate stays whatever the GUI "
                        "has, so the pattern period is points/rate and the "
                        "drive FREQUENCY IS UNKNOWN. Dry runs only")

    g = ap.add_argument_group("piezo")
    g.add_argument("--link", default="COM4")
    g.add_argument("--channel", type=int, default=1, help="1 = x")
    g.add_argument("--unlock", default=None, metavar="CODE",
                   help=f"security code; 'user' resolves to {ACCESS_CODES['user']}")

    ap.add_argument("--run", action="store_true",
                    help="actually drive. Without it nothing is opened or sent")
    ap.add_argument("--no-record", action="store_true",
                    help="drive both axes but take no video. Micro-Manager is "
                         "not loaded at all, so a running live_view.py keeps "
                         "the camera and the motion can be watched")
    ap.add_argument("--no-trap", action="store_true",
                    help="stage sine only, trap held static -- the drag "
                         "calibration configuration. Sends no tweezers command "
                         "at all, so --objective is not needed: nothing is "
                         "commanded in trap micrometres and there is no "
                         "calibration for it to be wrong about")
    args = ap.parse_args()

    if not args.no_record and not args.no_trap and not args.objective:
        ap.error("--objective is required when recording: the saved file would "
                 "otherwise carry no record of which calibration its "
                 "micrometres mean. Use --no-record to drive without saving")
    if args.no_trap:
        args.keep_blanking = True   # nothing is sent to the tweezers at all
    if not args.keep_blanking and args.blanking_us is None:
        ap.error("BEAM_SET_PARAMS carries the switching rate AND the blanking "
                 "time in one command, so it overwrites the GUI's standing "
                 "value. Read it off the GUI and pass --blanking-us, or pass "
                 "--keep-blanking to skip the command (frequency then unknown)")

    dt_s = args.period_s / args.piezo_points
    drive_s = args.period_s * args.cycles
    lead_frames = int(round(args.fps * args.lead_s))
    n_frames = int(round(args.fps * (args.lead_s + drive_s + args.trail_s)))
    exposure_ms = 1000.0 / args.fps
    switching_hz = args.pattern_points / args.period_s
    to_breakpoint_s = 0.0   # breakpoint at point 0 -- release *is* the start

    print(f"drive      trap y +/-{args.amplitude_um} um and stage x "
          f"+/-{args.amplitude_um} um, both {1 / args.period_s:.4g} Hz, "
          f"{args.cycles} cycles")
    if args.no_trap:
        print(f"trap       '{args.trap}' HELD STATIC -- no tweezers command is "
              "sent at all.")
        print("           Static trap + moving stage is the drag-calibration "
              "configuration:")
        print("           Stokes drag at a known stage velocity -> kappa. "
              "Needs no trap calibration,")
        print("           because nothing is commanded in trap micrometres.")
    else:
        print(f"trap       '{args.trap}' <- pattern '{args.pattern}', "
              f"{args.pattern_points:,} points -> {switching_hz:,.0f} Hz "
              "switching")
        print(f"           breakpoint at point 0, so release is t0 "
              f"({to_breakpoint_s * 1e3:.0f} ms to first motion)")
    print(f"piezo      channel {args.channel}, {args.piezo_points} samples/cycle "
          f"= {dt_s * 1e3:.2f} ms period")
    if args.no_record:
        print("camera     NOT USED -- Micro-Manager is not loaded, so a running "
              "live_view.py keeps it")
        print("light      untouched (whatever the live view has)")
    else:
        print(f"camera     {n_frames} frames, {args.roi}x{args.roi}, "
              f"exposure {exposure_ms:.4f} ms -> {args.fps:g} fps")
        print(f"           {args.lead_s:g} s lead ({lead_frames} frames) + "
              f"{drive_s:g} s drive + {args.trail_s:g} s trail")
        print(f"           drives fire after frame {lead_frames - 1}, so the "
              "onset is at a known frame index")
        print(f"light      {args.light_device}.{args.line} at "
              f"{args.intensity:.0f}/1000")
    if args.no_trap:
        print("calibration no trap calibration is used, so none can be wrong")
    else:
        print(f"calibration objective '{args.objective or '<unrecorded>'}' "
              "-- RECORDED, NOT CHECKED")
    if args.no_trap:
        print("blanking   untouched -- no BEAM_SET_PARAMS, no tweezers command")
    elif args.keep_blanking:
        print("blanking   BEAM_SET_PARAMS SKIPPED -- the GUI's rate and blanking "
              "are untouched.")
        print("           >> The pattern period is points/rate, so the DRIVE "
              "FREQUENCY IS UNKNOWN.")
    else:
        print(f"blanking   {args.blanking_us:g} us -- overwrites the GUI's value")

    if not args.run:
        print("\n-- plan only. Nothing opened, nothing sent. Add --run. --")
        return 0
    if not args.unlock:
        ap.error("--run needs --unlock: the piezo's .set commands are invisible "
                 "at the base security level")

    from pymmcore_plus import CMMCorePlus  # noqa: PLC0415

    clock = Clock()
    timeline = Timeline(clock)
    piezo_report: dict = {}
    lit = False

    core = None
    if not args.no_record:
        core = CMMCorePlus()
        core.loadSystemConfiguration(str(args.cfg))
        timeline.mark(MICROSCOPE, "config loaded", args.cfg.name)
    else:
        print()
        print("[Micro-Manager not loaded -- the camera stays with whoever "
              "has it]")

    stage = PiezoStage(allow_motion=True)
    stage.connect(args.link)
    level = stage.unlock(
        ACCESS_CODES["user"] if args.unlock == "user" else args.unlock
    )
    timeline.mark(PIEZO, "connected", f"{args.link}: {stage.identity()}, {level}")

    port = find_gui_port()
    if port is None:
        raise SystemExit("no Tweez GUI answering on 2070-2075")
    tweezers = OpticalTweezers(port=port)
    timeline.mark(TWEEZERS, "GUI answering", f"port {port}")

    try:
        # -- camera channel -------------------------------------------------
        camera = None
        if core is not None:
            camera = core.getCameraDevice()
            core.clearROI()
            full_w, full_h = core.getImageWidth(), core.getImageHeight()
            size = min(args.roi, full_w, full_h)
            if args.roi_centre is None:
                cx_px, cy_px = full_w // 2, full_h // 2
            else:
                cx_px, cy_px = args.roi_centre
            # Clamp so the requested centre cannot push the ROI off the sensor.
            ox = min(max(cx_px - size // 2, 0), full_w - size)
            oy = min(max(cy_px - size // 2, 0), full_h - size)
            core.setROI(ox, oy, size, size)
            if args.roi_centre is not None:
                print(f"ROI centred on sensor ({cx_px}, {cy_px}) -> "
                      f"offset ({ox}, {oy}), margin "
                      f"{min(cx_px - ox, ox + size - cx_px, cy_px - oy, oy + size - cy_px)} px "
                      "to the nearest edge")
            core.setExposure(exposure_ms)
            core.setAutoShutter(False)
            for label in _TURRET_SHUTTERS:
                core.setShutterOpen(label, True)
            core.setProperty(args.light_device, f"{args.line}_Intensity",
                             args.intensity)
            core.setProperty(args.light_device, args.line, 1)
            core.setShutterDevice(args.light_device)
            core.setShutterOpen(True)
            lit = True
            timeline.mark(MICROSCOPE, "channel armed",
                          f"{camera} {size}x{size} @ {core.getExposure():.4f} ms")

        # -- piezo trajectory, range-checked before anything moves ----------
        centre_um = stage.get_position_um(args.channel)
        lo_pm, hi_pm = stage.travel_pm(args.channel)
        lo_um, hi_um = lo_pm / 1e6, hi_pm / 1e6
        if not (lo_um <= centre_um - args.amplitude_um
                and centre_um + args.amplitude_um <= hi_um):
            raise SystemExit(
                f"REFUSING: {centre_um:.3f} +/- {args.amplitude_um} um leaves the "
                f"{lo_um:.1f}-{hi_um:.1f} um travel. Centre the axis first."
            )
        samples = sine_samples(centre_um, args.amplitude_um,
                               args.piezo_points, args.cycles)
        print(f"\npiezo centre {centre_um:.4f} um, sweep "
              f"{min(samples):.3f}-{max(samples):.3f} um, {len(samples)} samples")

        # -- arm the trap: assign the pattern, it parks at the breakpoint ----
        if args.no_trap:
            print("tweezers: NO COMMAND SENT -- the trap is held static, "
                  "wherever the GUI has it")
            timeline.mark(TWEEZERS, "held static", "no command sent")
        else:
            if args.keep_blanking:
                print("BEAM_SET_PARAMS skipped -- GUI rate and blanking "
                      "untouched, so the drive frequency is UNKNOWN")
            else:
                code = tweezers.send_command(
                    f"BEAM_SET_PARAMS {switching_hz:.0f} {args.blanking_us:g}")
                print(f"BEAM_SET_PARAMS -> {code} "
                      f"{_RETURN_CODES.get(code, '?')}")
            code = tweezers.send_command(
                f'TRAP_ASSIGN_PATTERN "{args.trap}" "{args.pattern}"')
            print(f"TRAP_ASSIGN_PATTERN -> {code} {_RETURN_CODES.get(code, '?')}")
            timeline.mark(TWEEZERS, "pattern assigned",
                          f"{args.trap} <- {args.pattern}; parked at breakpoint")

        # -- go: camera, then trap release, then the piezo scheduled off it --
        result_box: dict = {}
        lead_done = threading.Event()
        onset = {"frame": None}

        def on_frame(index, _image):
            """Fire the drives off the FRAME COUNTER, not a host sleep.

            The lead has to be measured in frames rather than seconds because
            frames are what the record is indexed by: this way the onset sits
            at a known index whose ``ElapsedTime-ms`` is already in the data,
            rather than at a host instant that has to be mapped in afterwards.
            """
            if index >= lead_frames - 1 and not lead_done.is_set():
                onset["frame"] = index
                lead_done.set()

        def acquire():
            result_box["result"] = capture_timestamped(
                core, n_frames, interval_ms=0.0, camera=camera,
                on_frame=on_frame)

        cam_thread = None
        if core is not None:
            cam_thread = threading.Thread(target=acquire, name="camera",
                                          daemon=True)
            with timeline.anchor(MICROSCOPE, f"{n_frames} frames",
                                 clock=HARDWARE, rate_hz=args.fps):
                cam_thread.start()

        # Wait out the lead. Frames are already being recorded, so this is the
        # quiet baseline the onset is fitted against.
        if cam_thread is not None and lead_frames > 0:
            if not lead_done.wait(timeout=args.lead_s + 10):
                raise SystemExit("no frames arrived during the lead -- "
                                 "refusing to drive blind")
            print(f"lead done at frame {onset['frame']}; firing the drives")

        # The trap release is the loosest link, so it goes first and its own
        # anchor -- not a later host stamp -- is what the piezo is scheduled off.
        release_rt_s = 0.0
        trap_t0_perf = None
        if args.no_trap:
            # Nothing to release, so the piezo owns its own zero. A short lead
            # so the first sample is waited for rather than already overdue.
            piezo_t0 = time.perf_counter() + 0.050
        else:
            with timeline.anchor(TWEEZERS, f"release {args.pattern}",
                                 clock=HARDWARE, rate_hz=switching_hz):
                release_t0 = time.perf_counter()
                code = tweezers.send_command(
                    f'TRAP_PATT_RELEASE_BP "{args.trap}"')
            release_rt_s = time.perf_counter() - release_t0
            # Midpoint of the round trip: the command was accepted somewhere
            # inside it, and the midpoint is the estimate whose worst-case error
            # is half the trip rather than all of it.
            trap_t0_perf = release_t0 + release_rt_s / 2
            print(f"TRAP_PATT_RELEASE_BP -> {code} "
                  f"{_RETURN_CODES.get(code, '?')}  "
                  f"(round trip {release_rt_s * 1e3:.2f} ms; the trap's t0 is "
                  f"inside it, +/-{release_rt_s * 1e3 / 2:.2f} ms)")
            piezo_t0 = release_t0 + release_rt_s / 2 + to_breakpoint_s
        with timeline.anchor(PIEZO, "sine x", clock=HOST_SCHED,
                             rate_hz=1 / dt_s):
            pass
        run_piezo_sine(stage, args.channel, samples, dt_s, piezo_t0,
                       timeline, piezo_report)

        result = None
        if cam_thread is not None:
            cam_thread.join(timeout=30)
            result = result_box.get("result")
            if result is None:
                raise SystemExit("camera thread produced nothing")

        # -- report ---------------------------------------------------------
        if result is not None:
            drops = result.drop_report()
            print("\n-- camera -------------------------------------------------")
            print(f"  frames        {result.n_captured}/{result.n_requested}  "
                  f"complete={result.complete}")
            print(f"  achieved      {result.achieved_fps:.4f} fps  "
                  f"(span {result.span_ms:.1f} ms)")
            print(f"  dropped       {drops.dropped_frames} (drops.analyse)  "
                  f"{result.dropped_by_image_number} (ImageNumber)")
            print(f"  contaminated  {drops.contaminated}")
        print("\n-- piezo ----------------------------------------------------")
        for key, value in piezo_report.items():
            print(f"  {key:14s} {value}")
        print(f"  final position {stage.get_position_um(args.channel):.4f} um")
        print("\n-- alignment ------------------------------------------------")
        pairs = []
        if not args.no_trap:
            pairs.append((PIEZO, TWEEZERS))
        if result is not None:
            pairs.append((PIEZO, MICROSCOPE))
            if not args.no_trap:
                pairs.append((TWEEZERS, MICROSCOPE))
        for a, b in pairs:
            print(f"  {a:11s} <-> {b:11s} "
                  f"{1e3 * timeline.alignment_error_s(a, b):.3f} ms worst case")
        if args.no_trap:
            print("  the trap sent nothing, so there is no trap anchor and")
            print("  nothing to align it to -- it was static for the whole run.")
        else:
            print("  + the trap's own zero is only known to "
                  f"+/-{release_rt_s * 1e3 / 2:.2f} ms "
                  "(half the release round trip)")
            print("  + the trap trajectory is COMPUTED from the pattern, "
                  "never read back")

        if result is not None:
            paths = result.write(args.out)
            paths.update(result.write_ome_tiff(args.out, pixel_size_um=0.065))
            paths["run"] = write_run_record(
                args, result, timeline, clock, piezo_report,
                piezo_t0=piezo_t0, release_rt_s=release_rt_s,
                switching_hz=switching_hz, centre_um=centre_um,
                onset_frame=onset["frame"], lead_frames=lead_frames,
                trap_t0_perf=trap_t0_perf,
            )
            print()
            for kind, path in paths.items():
                print(f"  wrote {kind:13s} {path}")
        else:
            print()
            print("  nothing written -- --no-record")
    finally:
        if lit:
            try:
                core.setShutterOpen(False)
                core.setProperty(args.light_device, args.line, 0)
                print("\n[excitation off]")
            except Exception as exc:
                print(f"cleanup warning (light): {exc}")
        # Turret shutters stay open and no TRAP_OFF / LASER_OFF is sent --
        # closing that path drops the bead.
        closers = [stage.close, tweezers.close]
        if core is not None:
            closers.insert(0, core.unloadAllDevices)
        for closer in closers:
            try:
                closer()
            except Exception as exc:
                print(f"cleanup warning ({closer.__qualname__}): {exc}")
        print("[trap left running, turret shutters left open]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
