"""What unit does ``function.waveform.data.set`` read? One bounded experiment.

    python config/piezo/settle_waveform_units.py --link COM4              # plan only
    python config/piezo/settle_waveform_units.py --link COM4 --move --unlock 0xDEC0DED

This is the single experiment that unblocks hardware timing on this rig. The
NPC-D has a waveform generator -- 500 001 samples, its own sample period, played
off the controller's 20 us servo -- and it is unusable for one reason: **the
generator does not read its samples in picometres**, so nothing can be uploaded
with confidence. `piezo_stage.function_start()` refuses while
``WAVEFORM_DATA_UNITS`` is None, and this is what fills that constant in.

WHY A CONSTANT WAVEFORM
-----------------------
Every sample the same value. A constant cannot oscillate whatever the unit, so
wherever the axis parks *is* the answer -- there is no trajectory to
misinterpret. Two further things fall out of using a constant, and both matter:

  - **The iterations question stops mattering.** ``function.waveform.iterations``
    and ``.repeat-count`` both exist, both were set on 2026-08-27, neither was
    isolated, and how they interact is still unknown. With every sample equal,
    any iteration behaviour parks the axis in the same place. The unknown cannot
    contaminate the result.
  - **The playback window hazard is defanged.** The window defaults to the whole
    500 001-sample buffer (start 0, end 500000, count 1), so a normal start
    plays 499 901 samples of uninitialised memory as a trajectory. Here the
    buffer is filled with one value, so even a stale window plays the constant.
    ``upload_waveform()`` sets the window properly anyway.

WHAT IS BEING DISTINGUISHED
---------------------------
Three readings of the sample value V, and they predict different parking spots:

    H1  absolute picometres     position = V / 1e6 um
    H2  an offset in picometres position = start + V / 1e6 um
    H3  a DAC code, full scale F   position = 600 um * (V mod F) / F

H3 is the reading that best explains 2026-08-27: a +/-5 um sine about 300 um,
uploaded as picometres, swung the axis **313.9 um** with centre crossings
0.7-25 ms apart. 300 um of picometres is 3.0e8, which overflows a 24-bit code,
and wrapping scatters consecutive samples across the whole travel -- exactly the
observed shape. F is carried as a candidate list rather than assumed.

THE LADDER, AND WHY IT IS ADAPTIVE
----------------------------------
Probes run one at a time, and **a probe is refused if any hypothesis still in
play predicts a position outside the travel.** That is the safety property: the
script never issues a command whose destination it cannot bound under every
reading it is still entertaining. Each probe eliminates readings, which is what
makes the next one safe to widen.

    V = 5e6          **first**, because it does both jobs: it puts all six
                     readings in six distinguishable places (5 / 305 / 176 /
                     461 / 358 / 179 um) *and* its worst destination is 5 um
                     rather than an end stop. One probe should settle it.
    V = 0            confirmation, and a very different number. H2 predicts no
                     motion at all while every other reading predicts the
                     bottom of travel, so it is the sharpest test of "offset"
                     specifically -- at the cost of being the harshest move in
                     the ladder, which is why it is not first.
    V = 2^23         confirmation. Separates the code widths on their own terms:
                     300 um at F = 2^24, 0 um at every smaller F.
    V = 3.0e8        the value that produced the 314 um excursion on
                     2026-08-27. Run last, as the tie back to the one
                     observation on record.

If no reading survives, that is a result too and the table is what gets
recorded -- the value could be something not on this list (a velocity, a segment
index) and inventing a fourth hypothesis at the bench is how a wrong constant
gets written down.

SAFETY -- READ THIS
-------------------
**Expect a large, fast lateral excursion.** The destination is the unknown being
measured, and several hypotheses predict a move of hundreds of micrometres
carried by a 20 us servo. Do not run this with a sample you care about, or with
anything in the travel that must not be swept through.

  - **Lateral axes only. Channel 3 is refused outright**, not warned about. On Z
    every micrometre is focus and the destination is unknown by construction, so
    there is no version of this experiment that belongs on Z.
  - Nothing moves without ``--move``, and ``--move`` needs ``--unlock``: the
    whole ``.set`` half of the command set is invisible at the base security
    level, and ``function.waveform.data.set`` is part of it.
  - Every probe needs a typed confirmation that states the predicted
    destinations, and the axis is re-parked between probes.
  - ``function.command.stop`` is sent after every probe, and in the finally.
"""

from __future__ import annotations

import argparse
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
    CALIBRATED,
    Waveform,
)

#: Candidate full-scale codes for H3. 2^24 is the one that explains the 314 um
#: excursion; the others are carried because nothing has ruled them out and a
#: single probe distinguishes them.
CODE_SCALES = (2**16, 2**20, 2**23, 2**24)

#: The probe ladder. 5e6 goes **first** on two counts at once: it separates all
#: six readings on its own, and its worst realistic destination is 5 um rather
#: than 0, so it is also the gentlest. The rest are confirmations at very
#: different values, which is what catches a reading that fits one probe by
#: coincidence -- and by then only one reading is live, so each confirmation
#: prompt shows a single unambiguous destination.
LADDER = (5.0e6, 0.0, float(2**23), 3.0e8)

#: A reading survives if its prediction lands within this of the measurement.
#: Predictions differ by tens to hundreds of micrometres, and the axis holds to
#: ~10 nm standing still, so this is loose on purpose -- it is a discriminator,
#: not a calibration.
TOLERANCE_UM = 2.0

#: A prediction this close to either end of travel is flagged in the
#: confirmation prompt. Not refused: 0 and 600 um are *legal* positions -- the
#: controller's own calibrated range -- and "absolute picometres" necessarily
#: maps every small value near the bottom, so refusing the limits would refuse
#: the cheapest probe in the ladder. Out-of-travel is what gets refused; at the
#: limit is what gets shown to the operator with the number attached, because
#: whether the controller clamps or faults there has never been tested here.
MARGIN_UM = 5.0

#: Samples per probe. Small: the protocol is one command per sample at ~0.4 ms,
#: and a constant needs no resolution.
N_SAMPLES = 8

#: Slow enough that playback lasts while the position is read, and irrelevant
#: to the answer -- a constant has no time dependence.
SAMPLE_PERIOD_S = 0.100

#: Reads taken during playback, and the settle before them. Release settles to
#: within 100 nm of centre in 20 ms, so 300 ms is generous.
SETTLE_S = 0.300
N_READS = 12


class Hypothesis:
    """One reading of the sample unit, and what it predicts."""

    def __init__(self, key: str, describe: str, predict) -> None:
        self.key = key
        self.describe = describe
        self._predict = predict
        self.alive = True
        self.residuals_um: list[float] = []

    def predict_um(self, value: float, start_um: float) -> float:
        return self._predict(value, start_um)

    def __str__(self) -> str:
        return f"{self.key:12} {self.describe}"


def hypotheses() -> list[Hypothesis]:
    out = [
        Hypothesis("absolute-pm", "value is an absolute position in picometres",
                   lambda v, s: v / PM_PER_UM),
        Hypothesis("offset-pm", "value is an offset from the current position, pm",
                   lambda v, s: s + v / PM_PER_UM),
    ]
    span_um = CALIBRATED.span_pm / PM_PER_UM
    for scale in CODE_SCALES:
        bits = scale.bit_length() - 1
        out.append(
            Hypothesis(
                f"code-2^{bits}",
                f"value is a DAC code, full scale 2^{bits} = {scale}",
                lambda v, s, f=float(scale): span_um * ((v % f) / f),
            )
        )
    return out


def live(hs: list[Hypothesis]) -> list[Hypothesis]:
    return [h for h in hs if h.alive]


def limit_note(predicted_um: float) -> str:
    """Flag a prediction sitting on an end of travel."""
    lo_um = CALIBRATED.min_pm / PM_PER_UM
    hi_um = CALIBRATED.max_pm / PM_PER_UM
    if predicted_um - lo_um <= MARGIN_UM:
        return "  <- AT THE BOTTOM OF TRAVEL"
    if hi_um - predicted_um <= MARGIN_UM:
        return "  <- AT THE TOP OF TRAVEL"
    return ""


def park(stage: PiezoStage, channel: int, centre_um: float) -> float:
    """Put the axis at a known place, and return where it actually is."""
    stage.set_position_um(channel, centre_um)
    time.sleep(SETTLE_S)
    return stage.get_position_um(channel)


def probe(
    stage: PiezoStage,
    channel: int,
    value: float,
    start_um: float,
    dry: bool,
) -> dict:
    """Load a constant waveform of ``value``, play it, and report where it went."""
    waveform = Waveform(
        samples=tuple([value] * N_SAMPLES),
        channel=channel,
        name=f"constant {value:.0f}",
    )
    # check() reads samples as picometres, which is exactly the assumption under
    # test -- so this bounds the *number*, not the physical destination. The
    # destination is bounded by the caller's hypothesis screen instead.
    waveform.check(CALIBRATED)

    if dry:
        return {"measured_um": None, "span_um": None, "reads": 0}

    stage.upload_waveform(
        waveform,
        CALIBRATED,
        sample_period_s=SAMPLE_PERIOD_S,
        # Both are set because their interaction is untested; with a constant
        # waveform it cannot change the answer. repeat_count 0 = forever, so the
        # axis holds the constant while it is being read.
        iterations=1,
        repeat_count=0,
        verify=2,
    )
    window = stage.playback_window(channel)
    # force=True is the documented override, and this is the experiment its
    # docstring points at. The window was just written by upload_waveform.
    stage.function_start(channels=(channel,), force=True)
    try:
        time.sleep(SETTLE_S)
        reads = [stage.get_position_um(channel) for _ in range(N_READS)]
    finally:
        stage.function_stop(channels=(channel,))
    return {
        "measured_um": statistics.median(reads),
        "span_um": max(reads) - min(reads),
        "reads": len(reads),
        "window": window,
    }


def screen(hs: list[Hypothesis], value: float, start_um: float) -> tuple[bool, str]:
    """May this probe be issued? Only if every live reading lands in travel."""
    lo_um = CALIBRATED.min_pm / PM_PER_UM
    hi_um = CALIBRATED.max_pm / PM_PER_UM
    for h in live(hs):
        predicted = h.predict_um(value, start_um)
        if not (lo_um <= predicted <= hi_um):
            return False, (
                f"{h.key} predicts {predicted:.3f} um, outside travel "
                f"{lo_um:.0f}..{hi_um:.0f} um -- refusing to issue a command "
                "whose destination is unbounded under a reading still in play"
            )
    return True, ""


def confirm(value: float, start_um: float, hs: list[Hypothesis]) -> bool:
    print(f"\n   probe: every sample = {value:.0f}")
    print(f"   axis is at {start_um:.4f} um. Predicted destinations:")
    for h in live(hs):
        predicted = h.predict_um(value, start_um)
        print(f"      {h.key:12} -> {predicted:9.3f} um{limit_note(predicted)}")
    reply = input("   type MOVE to issue this probe, anything else to skip: ")
    return reply.strip() == "MOVE"


def plan(hs: list[Hypothesis], centre_um: float) -> int:
    """Walk the ladder on paper: predictions, and which probes are issuable.

    Needs no device, so the arithmetic and the safety screen can be checked
    anywhere -- including on a machine the vendor DLL cannot load at all.
    Assumes each probe re-parks at ``centre_um``, which is what the run does,
    and assumes every probe is *consistent with nothing yet*, so no reading is
    eliminated and the screen is at its most conservative.
    """
    lo_um = CALIBRATED.min_pm / PM_PER_UM
    hi_um = CALIBRATED.max_pm / PM_PER_UM
    keys = [h.key for h in hs]
    print(f"{'value':>12}  " + "  ".join(f"{k:>12}" for k in keys) + "   issuable?")
    issuable = 0
    for value in LADDER:
        cells = []
        worst = None
        at_limit = []
        for h in hs:
            predicted = h.predict_um(value, centre_um)
            flag = "*" if limit_note(predicted) else " "
            cells.append(f"{predicted:11.3f}{flag}")
            if not (lo_um <= predicted <= hi_um):
                worst = h.key
            elif flag == "*":
                at_limit.append(h.key)
        ok = worst is None
        issuable += ok
        if worst is not None:
            note = f"NO -- {worst} leaves travel"
        elif at_limit:
            note = f"yes, but {', '.join(at_limit)} is at a limit"
        else:
            note = "yes"
        print(f"{value:12.0f}  " + "  ".join(cells) + f"   {note}")

    print("\n   * = prediction sits on an end of travel: legal, untested "
          "clamping,")
    print("       flagged in the confirmation prompt rather than refused.")
    print(f"\n   {issuable}/{len(LADDER)} probes issuable with every reading "
          "still in play.")
    print("   A probe marked NO becomes issuable once the reading that")
    print("   overshoots has been eliminated by an earlier probe -- which is")
    print("   what makes the ladder adaptive rather than a fixed list.")
    print("\n   Separation check -- a probe is only useful if two readings")
    print("   disagree by more than the tolerance:")
    for value in LADDER:
        preds = sorted(h.predict_um(value, centre_um) for h in hs)
        gaps = [b - a for a, b in zip(preds, preds[1:])]
        distinct = 1 + sum(1 for g in gaps if g > TOLERANCE_UM)
        print(f"      {value:12.0f}  ->  {distinct} distinguishable group(s) "
              f"of {len(hs)} readings")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Settle the waveform generator's sample unit, on a lateral axis."
    )
    ap.add_argument("--link", default="sim:/NPC6330",
                    help="bare port name, e.g. COM4 (no scheme). sim:/NPC6330 "
                         "reaches the DLL's own simulator")
    ap.add_argument("--channel", type=int, default=1,
                    help="1 = x, 2 = y. Channel 3 (z) is refused")
    ap.add_argument("--centre-um", type=float, default=300.0,
                    help="where the axis is parked before each probe")
    ap.add_argument("--move", action="store_true",
                    help="actually issue the probes. Without this, plan only")
    ap.add_argument("--unlock", default=None, metavar="CODE",
                    help="security code, e.g. 0xDEC0DED. The 0x prefix is "
                         "required -- a bare hex string answers 'Not enough "
                         "parameters'")
    args = ap.parse_args()

    if args.channel == 3:
        print("REFUSED: channel 3 is Z. The destination of these probes is the "
              "unknown being measured, and on Z every micrometre is focus. Use "
              "channel 1 or 2.", file=sys.stderr)
        return 2
    if args.channel not in (1, 2):
        print(f"REFUSED: channel must be 1 or 2, got {args.channel}",
              file=sys.stderr)
        return 2
    if args.move and not args.unlock:
        print("REFUSED: --move needs --unlock. function.waveform.data.set is "
              "invisible at the base security level and answers 'Invalid "
              "command name'.", file=sys.stderr)
        return 2

    hs = hypotheses()
    print("readings under test")
    for h in hs:
        print(f"   {h}")
    print(f"\nladder      {', '.join(f'{v:.0f}' for v in LADDER)}")
    print(f"tolerance   {TOLERANCE_UM} um     travel  0..600 um     "
          f"channel {args.channel}")
    # -- plan only: no DLL, no link, so this runs on any machine ----------
    if not args.move:
        print("\nPLAN ONLY -- nothing will move, and no device is opened.")
        print("Add --move --unlock CODE on the microscope PC to run it.\n")
        return plan(hs, args.centre_um)

    stage = PiezoStage(allow_motion=args.move)
    rows = []
    try:
        stage.connect(args.link)
        if args.unlock:
            stage.unlock(args.unlock)
        print(f"\nconnected   {args.link}   {stage.identity()}")

        start_um = park(stage, args.channel, args.centre_um)
        print(f"parked at   {start_um:.4f} um")

        for value in LADDER:
            ok, why = screen(hs, value, start_um)
            if not ok:
                print(f"\n   probe {value:.0f} SKIPPED: {why}")
                rows.append((value, None, "skipped -- unbounded"))
                continue
            if not confirm(value, start_um, hs):
                print("   skipped by operator")
                rows.append((value, None, "skipped by operator"))
                continue

            result = probe(stage, args.channel, value, start_um, dry=False)
            measured = result["measured_um"]
            print(f"   measured {measured:.4f} um   "
                  f"(spread {1e3 * result['span_um']:.1f} nm over "
                  f"{result['reads']} reads, window {result['window']})")

            survivors = []
            for h in live(hs):
                residual = abs(h.predict_um(value, start_um) - measured)
                h.residuals_um.append(residual)
                if residual <= TOLERANCE_UM:
                    survivors.append(h)
                else:
                    h.alive = False
                    print(f"      ruled out {h.key:12} "
                          f"(off by {residual:.3f} um)")
            for h in survivors:
                print(f"      consistent {h.key:12} "
                      f"(off by {h.residuals_um[-1]:.3f} um)")
            rows.append((value, measured, ", ".join(h.key for h in survivors)))

            start_um = park(stage, args.channel, args.centre_um)
            print(f"   re-parked at {start_um:.4f} um")

            if len(survivors) == 1:
                print(f"\n   one reading left after {len(rows)} probe(s). "
                      "Running the rest as confirmation.")
            if not survivors:
                print("\n   NO reading survives. Stopping -- the remaining "
                      "probes test hypotheses that are all dead.")
                break
    except PiezoStageError as exc:
        print(f"\npiezo: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    finally:
        try:
            if args.move:
                stage.function_stop()
        except Exception as exc:  # noqa: BLE001
            print(f"   on function_stop: {exc}", file=sys.stderr)
        try:
            stage.disconnect()
        except Exception:  # noqa: BLE001
            pass
        stage.close()

    # -- verdict ----------------------------------------------------------
    print("\n-- probes -------------------------------------------------")
    print(f"{'value':>12}  {'measured (um)':>14}  consistent with")
    for value, measured, note in rows:
        got = f"{measured:14.4f}" if measured is not None else " " * 14
        print(f"{value:12.0f}  {got}  {note}")

    survivors = live(hs)
    print("\n-- verdict ------------------------------------------------")
    if len(survivors) == 1:
        h = survivors[0]
        worst = max(h.residuals_um) if h.residuals_um else float("nan")
        print(f"   {h.key}: {h.describe}")
        print(f"   worst residual {worst:.3f} um over "
              f"{len(h.residuals_um)} probe(s)")
        print("\n   Write this into hardware/piezo_stage.WAVEFORM_DATA_UNITS,")
        print("   with the probe table above as the evidence, and")
        print("   function_start() stops needing force=True.")
        return 0
    if not survivors:
        print("   none of the readings fits. The table above is the result --")
        print("   record it and do NOT write a constant. The value may be")
        print("   something not on this list (a velocity, a segment index).")
        return 1
    print(f"   {len(survivors)} readings still consistent: "
          f"{', '.join(h.key for h in survivors)}")
    print("   The ladder did not separate them. Add a probe value whose")
    print("   predictions differ between them, and re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
