"""Oscillate, hold at the peak, release -- host-timed, on one piezo axis.

    python config/piezo/run_sine_hold.py --link COM4          # plan only, nothing moves
    python config/piezo/run_sine_hold.py --link COM4 --move --unlock 0xDEC0DED

One program is four phases, back to back, with no gap in the command stream:

    1. ``--cycles`` cycles of a sine, ``--amplitude-um`` about the axis's
       current position, at 1/``--period-s`` Hz
    2. a quarter cycle on from the last sine sample up to the **peak**, so the
       hold starts at the top of the same sine rather than after a jump
    3. hold at the peak for ``--hold-s``
    4. **step** back to the centre and hold for ``--release-s``

Phases 3 and 4 are the informative ones and they are why this is not just
try_hardware.py with a bigger ``--cycles``: a creep-and-recovery shape needs the
release to be a step, and it needs the readback split per phase. The report gives
the hold's drift and noise separately from the oscillation's tracking error.

WHY THIS IS HOST-TIMED AND NOT ON THE CONTROLLER'S GENERATOR
-----------------------------------------------------------
The NPC-D has a hardware waveform generator, which would clock all of this off
its own 20 us tick instead of off Windows. It is not used, and not because
nobody wired it up: as of 2026-08-27 the generator does **not** read its samples
in picometres, and a +/-5 um sine uploaded as picometres swung the axis 314 um.
See ``piezo_stage.WAVEFORM_DATA_UNITS`` for the measurement and the experiment
that would settle it. ``piezo_stage.function_start()`` refuses until then.

Host timing is good enough for this shape at these rates and the report proves
it per run rather than assuming it: the round trip is ~0.7 ms, so a 10 ms sample
period has 14x of headroom, and a 60 s run at 1 Hz measured 0/6000 overruns with
a median schedule slip of 1 us.

SAFETY
------
Nothing moves without ``--move``, and ``--move`` needs ``--unlock`` because the
whole ``.set`` half of the command set is invisible at the base security level.
The trajectory is range-checked against the travel the controller reports and
**refuses** rather than clipping. It is centred on the axis's current measured
position, never on the travel centre.

**Prefer a lateral axis.** On channel 3 (Z) every micrometre here is a change in
focus, and a hold at the peak is a sustained one; ``--channel 3`` prints a
warning and still requires the typed confirmation.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.piezo_stage import PiezoStage, PiezoStageError  # noqa: E402
from hardware.piezo_waveform import (  # noqa: E402
    PM_PER_UM,
    StageTravel,
    Waveform,
    WaveformError,
)

#: Command quantisation measured on COM4, 2026-08-27 -- see piezo_waveform.CALIBRATED.
STEP_PM = 32.0

AXIS_NAMES = {1: "x", 2: "y", 3: "z"}


def build_program(centre_pm, amplitude_pm, n_per_cycle, cycles, hold_s,
                  release_s, dt_s, channel):
    """The four phases as one sample array, plus the index each phase starts at."""
    samples = []
    marks = {}

    marks["sine"] = 0
    for _ in range(cycles):
        for i in range(n_per_cycle):
            samples.append(centre_pm + amplitude_pm * math.sin(2 * math.pi * i / n_per_cycle))

    marks["rise"] = len(samples)
    quarter = n_per_cycle // 4
    for i in range(quarter + 1):
        samples.append(centre_pm + amplitude_pm * math.sin(2 * math.pi * i / n_per_cycle))

    marks["hold"] = len(samples)
    samples += [centre_pm + amplitude_pm] * max(1, round(hold_s / dt_s))

    marks["release"] = len(samples)
    samples += [centre_pm] * max(1, round(release_s / dt_s))

    name = (f"sine{cycles}x_hold{hold_s:g}s_release{release_s:g}s"
            f"_a{amplitude_pm / PM_PER_UM:g}um")
    return Waveform(samples=tuple(samples), channel=channel, name=name), marks


def play(stage, waveform, dt_s, programs):
    """Command every sample on a fixed schedule, reading each one back.

    Absolute deadlines from one t0, so a slow round trip does not push the whole
    schedule out -- the next sample still goes at its own time.
    """
    log = []
    t0 = time.perf_counter()
    index = 0
    for program in range(programs):
        for i, value in enumerate(waveform.samples):
            deadline = t0 + index * dt_s
            while True:
                now = time.perf_counter()
                if now >= deadline:
                    break
            stage.set_position_pm(waveform.channel, value)
            measured = stage.get_position_pm(waveform.channel)
            log.append((program, i, now - t0, deadline - t0, value, measured))
            index += 1
    return log


def phase_of(index, marks, length):
    order = sorted(marks.items(), key=lambda kv: kv[1])
    current = order[0][0]
    for name, start in order:
        if index >= start:
            current = name
    return current


def report(log, waveform, marks, dt_s, centre_pm, amplitude_pm, programs):
    lines = []
    slips = [t - d for _, _, t, d, _, _ in log]
    overruns = sum(1 for s in slips if s > dt_s)
    lines.append("-- timing ---------------------------------------------------")
    lines.append(f"  samples          {len(log)} over {programs} program(s), "
                 f"{dt_s * 1e3:g} ms apart")
    lines.append(f"  wall clock       {log[-1][2]:.3f} s "
                 f"(planned {len(log) * dt_s:.3f} s)")
    lines.append(f"  schedule slip    med {statistics.median(slips) * 1e3:.3f} ms, "
                 f"max {max(slips) * 1e3:.3f} ms")
    lines.append(f"  overruns         {overruns}/{len(log)} samples arrived more "
                 "than one period late")

    by_phase = {}
    for program, i, t, _, commanded, measured in log:
        by_phase.setdefault(phase_of(i, marks, len(waveform)), []).append(
            (t, commanded, measured))

    lines.append("")
    lines.append("-- what the axis actually did, per phase --------------------")
    for phase in ("sine", "rise", "hold", "release"):
        rows = by_phase.get(phase)
        if not rows:
            continue
        measured = [m for _, _, m in rows]
        errors = [abs(m - c) for _, c, m in rows]
        span_um = (max(measured) - min(measured)) / PM_PER_UM
        lines.append(f"  {phase:8} n={len(rows):5}  "
                     f"span {span_um:8.4f} um   "
                     f"|measured-cmd| med {statistics.median(errors) / 1e3:7.1f} nm "
                     f"max {max(errors) / 1e3:7.1f} nm")

    hold = by_phase.get("hold")
    if hold:
        # Per program, so the drift is not read across a release and back.
        lines.append("")
        lines.append(f"-- the {len(hold) // programs * dt_s if programs else 0:g} s hold at the peak "
                     f"({(centre_pm + amplitude_pm) / PM_PER_UM:.4f} um) ------------")
        per = len(hold) // programs
        for program in range(programs):
            chunk = [m for _, _, m in hold[program * per:(program + 1) * per]]
            if len(chunk) < 2:
                continue
            drift_nm = (chunk[-1] - chunk[0]) / 1e3
            lines.append(
                f"  program {program + 1}   mean {statistics.mean(chunk) / PM_PER_UM:.4f} um   "
                f"drift {drift_nm:+7.1f} nm over the hold   "
                f"stdev {statistics.stdev(chunk) / 1e3:5.1f} nm"
            )

    release = by_phase.get("release")
    if release:
        lines.append("")
        lines.append("-- release: how long to settle back to the centre ----------")
        per = len(release) // programs
        for program in range(programs):
            chunk = release[program * per:(program + 1) * per]
            if not chunk:
                continue
            t_start = chunk[0][0]
            settled = next(
                (t - t_start for t, _, m in chunk if abs(m - centre_pm) < 100_000),
                None,
            )
            end = chunk[-1][2]
            lines.append(
                f"  program {program + 1}   within 100 nm of centre after "
                + (f"{settled * 1e3:6.1f} ms" if settled is not None else "  never")
                + f"   ended at {end / PM_PER_UM:.4f} um"
            )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", default="COM4", help='COM port, IP, or "sim:/NPC6330"')
    ap.add_argument("--channel", type=int, default=1, help="1-based (default 1 = x)")
    ap.add_argument("--amplitude-um", type=float, default=10.0)
    ap.add_argument("--period-s", type=float, default=1.0, help="one sine cycle")
    ap.add_argument("--cycles", type=int, default=3, help="sine cycles per program")
    ap.add_argument("--points", type=int, default=100, help="samples per sine cycle")
    ap.add_argument("--hold-s", type=float, default=2.0, help="hold at the peak")
    ap.add_argument("--release-s", type=float, default=5.0, help="hold at the centre")
    ap.add_argument("--programs", type=int, default=1, help="repeats of the whole program")
    ap.add_argument("--unlock", default=None, metavar="CODE",
                    help="security access code, 0x-prefixed (see piezo_stage.ACCESS_CODES)")
    ap.add_argument("--move", action="store_true", help="actually drive the stage")
    a = ap.parse_args()

    dt_s = a.period_s / a.points

    try:
        stage = PiezoStage(allow_motion=a.move)
    except PiezoStageError as exc:
        print(f"FAILED to load the controller DLL: {exc}", file=sys.stderr)
        return 2
    try:
        stage.connect(a.link)
    except PiezoStageError as exc:
        print(f"could not open {a.link!r}: {exc}", file=sys.stderr)
        print("  the vendor NanoBench GUI holds the port exclusively -- close its "
              "session first", file=sys.stderr)
        stage.close()
        return 2

    try:
        if a.unlock:
            print(f"  security level   {stage.unlock(a.unlock)}")
        else:
            print(f"  security level   {stage.security_level()}")

        lo, hi = stage.travel_pm(a.channel)
        travel = StageTravel(min_pm=lo, max_pm=hi, resolution_pm=STEP_PM)
        centre_pm = stage.get_position_pm(a.channel)
        amplitude_pm = a.amplitude_um * PM_PER_UM
        waveform, marks = build_program(
            centre_pm, amplitude_pm, a.points, a.cycles, a.hold_s, a.release_s,
            dt_s, a.channel,
        )

        axis = AXIS_NAMES.get(a.channel, "?")
        span_lo, span_hi = waveform.span_pm
        print(f"  channel {a.channel} ({axis})       centre {centre_pm / PM_PER_UM:.4f} um "
              "(current measured position, read just now)")
        print(f"  travel           {lo / PM_PER_UM:.1f} .. {hi / PM_PER_UM:.1f} um, "
              f"step {STEP_PM:g} pm")
        print(f"  program          {a.cycles} x {1 / a.period_s:g} Hz sine "
              f"+/-{a.amplitude_um:g} um, then {a.hold_s:g} s at the peak, "
              f"then {a.release_s:g} s at the centre")
        print(f"  span             {span_lo / PM_PER_UM:.4f} .. {span_hi / PM_PER_UM:.4f} um")
        print(f"  samples          {len(waveform)} per program x {a.programs} "
              f"= {len(waveform) * a.programs}, {dt_s * 1e3:g} ms apart "
              f"({len(waveform) * a.programs * dt_s:.2f} s)")
        print(f"  peak speed       {waveform.peak_speed_um_s(dt_s):.2f} um/s")

        try:
            waveform.check(travel)
        except WaveformError as exc:
            print(f"\n  range check      REFUSED: {exc}", file=sys.stderr)
            return 2
        print("  range check      OK: every sample is inside the travel above")

        if not a.move:
            print("\n  nothing moved -- pass --move (and --unlock) to drive it")
            return 0
        if a.channel == 3:
            print("\n  *** channel 3 is Z: every um here is focus, and the hold "
                  "sustains it.")

        answer = input(f"\n  this MOVES {axis} between "
                       f"{span_lo / PM_PER_UM:.4f} and {span_hi / PM_PER_UM:.4f} um. "
                       "type 'move': ")
        if answer.strip() != "move":
            print("  aborted -- nothing commanded")
            return 0

        start_pm = stage.get_position_pm(a.channel)
        try:
            log = play(stage, waveform, dt_s, a.programs)
        except KeyboardInterrupt:
            stage.set_position_pm(a.channel, start_pm)
            print(f"\n  interrupted -- commanded back to "
                  f"{start_pm / PM_PER_UM:.4f} um")
            return 130
        print()
        print(report(log, waveform, marks, dt_s, centre_pm, amplitude_pm, a.programs))

        stage.set_position_pm(a.channel, start_pm)
        time.sleep(0.2)
        print(f"\n  restored         {stage.get_position_um(a.channel):.4f} um "
              f"(started at {start_pm / PM_PER_UM:.4f} um)")
        return 0
    except PiezoStageError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        stage.disconnect()
        stage.close()


if __name__ == "__main__":
    sys.exit(main())
