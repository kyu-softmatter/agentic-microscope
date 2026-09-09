r"""Measure the tweezers' px->um calibration against the camera, after an
objective change.

⚠⚠ READ THIS FIRST: PREFER config/tweezers/trap_sequence.py.
That module already measures this properly and owns the constants, and
`config/tweezers/trap_from_tracking.py` beside it has the real machinery --
`sine_schedule`, `stream_sine`, `fit_against_drive`, `column_from_fit`, and a
saveable `TrapTransform`. Its stage 3 drives a 5 um 1 Hz sine on a bead ALREADY
SITTING IN THE TRAP and fits the matrix against the drive, which is the only
measurement that gets the scale: a ramp-to-origin cannot, because the bead's
starting pixel is where the BEAD was and not where the trap was commanded, and
solving from that mixes in the origin offset (it comes out 12% anisotropic, and
that is the contamination rather than the optics).

This script was written on 2026-09-06 before that was found, and it duplicates
stage 3 badly. It is kept for two reasons only: it works from the dual-camera
config and watches BOTH cameras, and its null-result path is a worked example
of how a plausible discriminator can be worthless. What it got wrong is
recorded below rather than quietly fixed, because the mistake is the useful
part.

    python config/session/verify_trap_calibration.py --plan        # no hardware
    python config/session/verify_trap_calibration.py --run --amplitude-um 3

WHY THIS IS REQUIRED, NOT OPTIONAL
----------------------------------
An objective change silently invalidates BOTH tweezers calibrations -- the
Tweez GUI's px->um Magnification and its AOD trapping-field response
(Tweez300UserManual pp. 28-32, 35-38). Neither is readable or settable over
the TCP interface, so afterwards every `TRAP_POSITION` in um lands somewhere
else and NOTHING on either side reports it. SAFETY.md §2 and §8 step 11 both
say the same thing: verify by driving a known amplitude and MEASURING it.

The nosepiece moved from 4x to 100x Oil on 2026-09-06, so the calibration in
the GUI is unverified as of now. It may well be intact -- the last check was
also at 100x (2026-09-03: +-10.000 um commanded, 9.9672 and 10.0852 um
measured) and nothing touched the tweezers during the 4x work -- but "probably
unchanged" is not a measurement, and this is the one number every later force
and distance depends on.

WHAT IT MEASURES, AND THE ONE HONEST DISCRIMINATOR
--------------------------------------------------
`micrometres measured / micrometres commanded`, plus the ANGLE between the
trap's coordinate frame and the camera's -- which is not recorded anywhere and
cannot be assumed to be zero, since the AOD axes have no stated relationship to
the camera's rows and columns.

The hard part is not the measurement, it is knowing WHICH bead is trapped.
SAFETY.md §7 records the failure: in a crowded field, brightness cannot
identify it -- six blobs within 27,200-29,140 counts produced six
plausible-but-wrong fits. Two discriminators actually work, and this script
uses the second:

    stage motion    the trapped bead is the only object that does not
                    translate with the stage. Needs a stage move.
    TRAP motion     the trapped bead is the only object that moves WITH THE
                    COMMANDED TRAP. Everything else diffuses, which is
                    uncorrelated with a command we choose.

So the drive is a there-and-back excursion and the trapped bead is identified
as the object whose displacement REVERSES with the command. A diffusing bead
has no reason to do that, and requiring the reversal is what makes this robust
in a field of ~45 particles rather than a guess among them.

⚠ THE AMPLITUDE MUST STAY INSIDE THE CAPTURE RANGE, AND IT IS SMALL
-------------------------------------------------------------------
On this repo's own trapping model (`trapping.cli force-curve`, r=2.5 um PS bead
in water at NA 1.45), the radial restoring force PEAKS at about 2.3 um of
displacement and falls beyond it. So a trap that jumps further than that
leaves the bead outside its own restoring region and simply drops it --
SAFETY.md says the same in words ("never send a trap position step larger than
the capture range with a bead trapped -- a 14 um jump simply drops it").

Hence the drive is STEPPED: `--amplitude-um` total, reached in increments of
`--step-um` (default 0.5 um, well inside the range) with a settle delay
between them, so the bead is dragged rather than abandoned. A single
`TRAP_POSITION` to the full amplitude would return 0 and drop the bead, which
is exactly the class of failure this instrument specialises in.

WHAT IT WILL NOT DO
-------------------
  · It does not send LASER_ON. Arm the laser at the GUI with the interlocks in
    view (SAFETY.md §1); `run_pattern.py` omits it for the same reason.
  · It does not send LASER_OFF or TRAP_OFF on exit, and does not close
    Turret2Shutter. Operator instruction, 2026-09-03: the OT laser may stay on
    while the camera is handed away, because the trap is the expensive thing to
    re-establish. Only the Aura illumination is taken down.
  · It does not call LOAD_PROJECT, which can restore a saved laser-on state
    (manual p.65).
  · A return code of 0 from any of this means the GUI accepted the command,
    never that it happened (SAFETY.md §0). The camera measurement below is the
    only actual confirmation, which is the whole point of the script.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ⚠ BINNING AND PIXEL SIZE, MEASURED 2026-09-06.
# `core.getPixelSizeUm()` ALREADY ACCOUNTS FOR BINNING: with the 100x-1x preset
# it returns 0.06453 at bin 1x1, 0.12906 at 2x2 and 0.25812 at 4x4 (0.065 /
# 0.130 / 0.260 before the 100x row became measured on 2026-09-09). So it must be read
# AFTER the binning is set and must NOT be multiplied by the bin factor.
# This file used to read it before setting binning and then multiply by 2, which
# gave the right 0.130 only because of that statement order -- load a config that
# already had 2x2, or reorder these two blocks, and it silently became 0.260.
# Reading it after and not scaling removes the ordering dependency entirely.
#
# `trap_from_tracking.pixel_size_um()` used to behave the OPPOSITE way -- it
# reads the table in data/pixel_size.yaml, which is keyed on objective x
# intermediate magnification only and so returned the 1x1 value at ANY binning. Fixed
# 2026-09-06: it now multiplies by the bin factor, names the binning in its
# provenance string, refuses non-square binning, and cross-checks against
# getPixelSizeUm(). The two paths now agree or refuse.

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_twocolour.cfg"
LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]
ARMS = [("Kinetix_red", "red-Abvigen"), ("Kinetix_blue", "blue-DragonGreen")]

# From trapping.cli force-curve, r=2.5 um PS in water, NA 1.45, 1064 nm: the
# radial force peaks near here and falls beyond it.
CAPTURE_RANGE_UM = 2.3


def detect(frame: np.ndarray, area_px: tuple[int, int], n_sigma: float = 8.0) -> list[dict]:
    import cv2

    f32 = frame.astype(np.float32)
    residual = f32 - cv2.GaussianBlur(f32, (0, 0), 15)
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0
    n, labels, stats, cent = cv2.connectedComponentsWithStats(
        (residual > n_sigma * scale).astype(np.uint8), 8)
    lo, hi = area_px
    return [{"x": float(cent[i][0]), "y": float(cent[i][1]), "area": int(stats[i, 4])}
            for i in range(1, n) if lo <= int(stats[i, 4]) <= hi]


def nearest(pt: dict, pool: list[dict], tol: float) -> dict | None:
    best, best_d = None, tol
    for q in pool:
        d = ((pt["x"] - q["x"]) ** 2 + (pt["y"] - q["y"]) ** 2) ** 0.5
        if d < best_d:
            best, best_d = q, d
    return best


def plan(args) -> None:
    n = max(1, int(round(args.amplitude_um / args.step_um)))
    print(f"amplitude {args.amplitude_um} um, reached in {n} steps of "
          f"{args.amplitude_um/n:.3f} um, {args.settle_s} s settle each")
    print(f"capture range is ~{CAPTURE_RANGE_UM} um (radial force peaks there and "
          f"falls beyond)")
    if args.step_um > CAPTURE_RANGE_UM:
        print(f"  !! STEP {args.step_um} um EXCEEDS IT -- the bead would be left "
              f"outside its own restoring region and dropped. Refusing.")
    if args.amplitude_um > 20:
        print(f"  !! amplitude {args.amplitude_um} um is large; the 2026-09-03 check "
              f"used 10 um")
    print(f"\ncommand sequence per excursion (trap {args.trap!r}):")
    print(f"  SIMPLE_TRAP_CREATE {args.trap!r}")
    print(f"  TRAP_POSITION {args.trap!r} {args.x0} {args.y0}")
    print(f"  TRAP_ON {args.trap!r}")
    for i in range(1, n + 1):
        print(f"  TRAP_POSITION {args.trap!r} {args.x0 + i*args.amplitude_um/n:.3f} {args.y0}"
              + ("   <- snap both cameras" if i == n else ""))
    print("  ... then the same back to x0, snapping at the end")
    print("\nNO LASER_ON, NO LASER_OFF, NO TRAP_OFF. The trap is left on.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--plan", action="store_true", help="print the plan, touch nothing")
    p.add_argument("--run", action="store_true", help="microscope PC: drive and measure")
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0, help="0 = scan 2070-2075")
    p.add_argument("--trap", default="cal-verify")
    p.add_argument("--x0", type=float, default=0.0)
    p.add_argument("--y0", type=float, default=0.0)
    p.add_argument("--amplitude-um", type=float, default=3.0)
    p.add_argument("--step-um", type=float, default=0.5)
    p.add_argument("--settle-s", type=float, default=0.25)
    p.add_argument("--cycles", type=int, default=3, help="there-and-back excursions")
    p.add_argument("--cyan", type=int, default=3)
    p.add_argument("--green", type=int, default=45)
    p.add_argument("--exposure-ms", type=float, default=10.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--bead-um", type=float, default=5.0)
    p.add_argument("--match-px", type=float, default=25.0)
    p.add_argument("--reuse-trap", action="store_true",
                   help="do not create a trap; drive the existing one by this name")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    if not (args.plan or args.run):
        p.error("pass --plan (safe) or --run")
    if args.step_um > CAPTURE_RANGE_UM:
        print(f"REFUSED: --step-um {args.step_um} exceeds the ~{CAPTURE_RANGE_UM} um "
              f"capture range; the bead would be dropped.", file=sys.stderr)
        return 1
    if args.plan:
        plan(args)
        return 0

    import cv2
    from pymmcore_plus import CMMCorePlus
    from hardware.optical_tweezers import OpticalTweezers, find_gui_port

    port = args.port or find_gui_port(host=args.host)
    if port is None:
        print("No Tweez GUI answered on 2070-2075. It must be running AND connected "
              "to its System Manager and the device.", file=sys.stderr)
        return 1
    print(f"Tweez GUI on port {port}", flush=True)

    core = CMMCorePlus()
    core.loadSystemConfiguration(args.cfg)
    core.setConfig("TwoColour", "GreenRed-Widefield")
    core.waitForConfig("TwoColour", "GreenRed-Widefield")
    core.setAutoShutter(False)
    # See the binning note at the top of the file: set binning FIRST, then read
    # the pixel size, which already includes it.
    for cam, _ in ARMS:
        core.setCameraDevice(cam)
        core.setProperty(cam, "Binning", args.binning)
        core.clearROI()
        core.setExposure(args.exposure_ms)
    binned_um = core.getPixelSizeUm()
    r = 0.5 * args.bead_um / binned_um
    area_px = (max(2, int(0.25 * np.pi * r * r)), int(4.0 * np.pi * r * r))
    print(f"objective {core.getStateLabel('Nosepiece')}, {binned_um:.4f} um/px binned",
          flush=True)

    def snap_all() -> dict:
        out = {}
        for cam, _ in ARMS:
            core.setCameraDevice(cam)
            core.snapImage()
            out[cam] = np.asarray(core.getImage())
        return out

    def ramp(t, x_from: float, x_to: float) -> None:
        """Step between two x positions in <= step_um increments, so the bead is
        dragged rather than abandoned outside the capture range."""
        n = max(1, int(np.ceil(abs(x_to - x_from) / args.step_um)))
        for i in range(1, n + 1):
            x = x_from + (x_to - x_from) * i / n
            t.set_trap_position(args.trap, round(x, 4), args.y0)
            time.sleep(args.settle_s)

    report: dict = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "objective": core.getStateLabel("Nosepiece"),
        "pixel_um_binned": binned_um,
        "amplitude_um_commanded": args.amplitude_um,
        "step_um": args.step_um,
        "cycles": args.cycles,
        "trap": args.trap,
    }
    excursions: list[dict] = []

    with OpticalTweezers(host=args.host, port=port) as t:
        if not t.is_ready():
            print("GUI is not ready -- see NOT_READY_STATUSES in the driver.",
                  file=sys.stderr)
            return 1
        try:
            for line in LINES:
                core.setProperty("Aura", line, "0")
                core.setProperty("Aura", f"{line}_Intensity", "0")
            for line, pm in (("CYAN", args.cyan), ("GREEN", args.green)):
                core.setProperty("Aura", f"{line}_Intensity", str(pm))
                core.setProperty("Aura", line, "1")
            core.setProperty("Aura", "State", "1")
            core.waitForDevice("Aura")
            print(f"light ON  CYAN {args.cyan} / GREEN {args.green}", flush=True)

            if not args.reuse_trap:
                t.create_simple_trap(args.trap)
                print(f"created trap {args.trap!r} (returned 0 -- which means the GUI "
                      f"accepted it, nothing more)", flush=True)
            t.set_trap_position(args.trap, args.x0, args.y0)
            t.trap_on(args.trap)
            time.sleep(1.0)
            print(f"trap at ({args.x0}, {args.y0}), TRAP_ON sent\n", flush=True)

            for c in range(args.cycles):
                at_x0 = snap_all()
                ramp(t, args.x0, args.x0 + args.amplitude_um)
                at_amp = snap_all()
                ramp(t, args.x0 + args.amplitude_um, args.x0)
                back = snap_all()

                for cam, label in ARMS:
                    d0 = detect(at_x0[cam], area_px)
                    d1 = detect(at_amp[cam], area_px)
                    d2 = detect(back[cam], area_px)
                    for a in d0:
                        b = nearest(a, d1, args.match_px)
                        if b is None:
                            continue
                        cc = nearest(b, d2, args.match_px)
                        if cc is None:
                            continue
                        out_v = np.array([b["x"] - a["x"], b["y"] - a["y"]])
                        back_v = np.array([cc["x"] - b["x"], cc["y"] - b["y"]])
                        out_n, back_n = np.linalg.norm(out_v), np.linalg.norm(back_v)
                        if out_n < 3.0:
                            continue
                        # the trapped bead reverses; a diffusing one does not
                        cosang = float(out_v @ back_v / (out_n * back_n + 1e-9))
                        excursions.append({
                            "cycle": c, "camera": cam, "label": label,
                            "start": [a["x"], a["y"]],
                            "out_px": out_n, "back_px": back_n,
                            "reversal_cos": cosang,
                            "out_um": out_n * binned_um,
                            "angle_deg": float(np.degrees(np.arctan2(out_v[1], out_v[0]))),
                        })
                print(f"cycle {c+1}/{args.cycles}: {len(excursions)} tracked "
                      f"displacements so far", flush=True)
        finally:
            for line in ("CYAN", "GREEN"):
                try:
                    core.setProperty("Aura", line, "0")
                    core.setProperty("Aura", f"{line}_Intensity", "0")
                except Exception:
                    pass
            try:
                core.setProperty("Aura", "State", "0")
            except Exception:
                pass
            print("\nillumination OFF. Trap and laser LEFT ON deliberately "
                  "(SAFETY.md §1).", flush=True)

    # ── which of those was the trapped bead? ────────────────────────────────
    print("\n" + "=" * 72)
    print("TRAP px->um CALIBRATION")
    print("=" * 72)
    # ── the discriminator, and why the obvious version does not work ────────
    #
    # The first version required only `reversal_cos < -0.7` plus similar
    # out/back magnitudes. That is close to useless and the arithmetic says so:
    # cos < -0.7 is an angle beyond 134 deg, which ~25% of RANDOM direction
    # pairs in 2D satisfy. On 2026-09-06 it passed 8 of 91 tracked objects --
    # FEWER than the ~23 that chance alone predicts -- and duly reported a
    # confident 79.8% calibration error from a mean displacement of 0.607 um,
    # which is just sqrt(2*D*t) for a wall-hindered 5 um bead over the ~3 s
    # between snaps (D ~ 0.04 um^2/s -> 0.49 um). It measured diffusion and
    # called it a calibration.
    #
    # A trap-driven bead differs from a diffusing one in MAGNITUDE, not
    # direction: it is dragged the commanded distance, chosen to be several
    # times the diffusive step. So estimate the diffusive scale from the
    # population itself -- almost everything in the field is diffusing -- and
    # require a candidate to stand well clear of it.
    diff_scale_px = float(np.median([e["out_px"] for e in excursions])) if excursions else 0.0
    chance_reversal = 0.253      # fraction of uniform 2D pairs with cos < -0.7
    report["n_tracked"] = len(excursions)
    report["diffusive_scale_px"] = diff_scale_px
    report["diffusive_scale_um"] = diff_scale_px * binned_um
    good = [e for e in excursions
            if e["reversal_cos"] < -0.8
            and abs(e["out_px"] - e["back_px"]) < 0.3 * e["out_px"]
            and e["out_px"] > 4.0 * diff_scale_px]
    report["n_reversing"] = len(good)
    n_loose = sum(1 for e in excursions if e["reversal_cos"] < -0.7)
    print(f"  diffusive scale (median displacement of all {len(excursions)} tracked "
          f"objects): {diff_scale_px:.1f} px = {diff_scale_px*binned_um:.3f} um")
    print(f"  {n_loose} reversed on direction alone, against "
          f"~{chance_reversal*len(excursions):.0f} expected by chance -- so direction "
          f"is NOT a discriminator")
    print(f"  {len(good)} also moved further than 4x the diffusive scale")

    if not good:
        print(f"\n  {len(excursions)} displacements tracked; none moved further than "
              f"4x the diffusive\n  scale while reversing with the command.")
        print("  -> NO BEAD IS TRAPPED. Everything moved by about what free diffusion "
              "predicts,\n     in directions uncorrelated with a motion we chose. "
              "SIMPLE_TRAP_CREATE,\n     TRAP_POSITION and TRAP_ON all returned 0 "
              "regardless -- the same state measured\n     on 2026-09-04, where those "
              "three returned 0 with the laser unarmed and\n     nothing trapped "
              "(SAFETY.md §0).")
        print("\n  USE config/tweezers/trap_sequence.py INSTEAD OF THIS SCRIPT.")
        print("  It already does look -> detect -> trap -> hold -> oscillate in one")
        print("  window, and it holds the three things from 2026-09-04 that this")
        print("  script had to do without:")
        print("    · TRAP_ORIGIN_OFFSET_UM = (-1.013, -1.015) um -- where trap (0,0)")
        print("      lands in the image, measured over 5 holds. So the trap's camera")
        print("      position is KNOWN, not unknown.")
        print("    · orientation confirmed -- handedness -1, rotation ~0, validated by")
        print("      4 ramps in 4 quadrants all following 98.6-99.8%.")
        print("    · a HELD verdict from the excursion collapsing (enter 110 nm, leave")
        print("      220 nm) rather than from correlating with a command. A free 5 um")
        print("      bead near the wall covers ~350 nm in 1.5 s; held ones read 28-61.")
        print("      That is a far better discriminator and it needs no drive at all.")
        print("\n  And the way to CATCH one needs no calibration: park the trap at the")
        print("  origin and wait for a bead to diffuse in. The origin IS the field")
        print("  centre, so no rotation, handedness or scale enters -- trap_sequence's")
        print("  HOLD stage exists for exactly this. Waiting is the step this script")
        print("  skipped: it sent TRAP_ON and began driving ~1 s later.")
        report["verdict"] = "no trapped bead -- nothing reversed with the command"
    else:
        best = min(good, key=lambda e: abs(e["reversal_cos"] + 1.0))
        measured = [e["out_um"] for e in good]
        ratios = [m / args.amplitude_um for m in measured]
        angles = [e["angle_deg"] for e in good]
        print(f"  {len(good)} of {len(excursions)} displacements reversed with the "
              f"command (cos < -0.7)")
        print(f"  identified on: {best['camera']} ({best['label']})")
        print(f"  commanded {args.amplitude_um:.3f} um  ->  measured "
              f"{np.mean(measured):.3f} +- {np.std(measured):.3f} um")
        print(f"  ratio measured/commanded = {np.mean(ratios):.4f} "
              f"+- {np.std(ratios):.4f}")
        print(f"  trap-x axis sits at {np.mean(angles):+.1f} deg in camera coordinates")
        report.update({
            "measured_um_mean": float(np.mean(measured)),
            "measured_um_sd": float(np.std(measured)),
            "ratio_mean": float(np.mean(ratios)),
            "ratio_sd": float(np.std(ratios)),
            "trap_x_angle_deg_in_camera": float(np.mean(angles)),
            "identified_camera": best["camera"],
        })
        err = abs(np.mean(ratios) - 1.0)
        if err <= 0.05:
            print(f"\n  -> CALIBRATION GOOD: within {100*err:.1f}% of 1.0. Commanded "
                  f"micrometres can be\n     trusted at this objective. Comparable to "
                  f"the 2026-09-03 check (9.967 and\n     10.085 um for 10.000 "
                  f"commanded, i.e. 0.3-0.9%).")
            report["verdict"] = f"good, {100*err:.1f}% error"
        else:
            print(f"\n  !! CALIBRATION IS OFF BY {100*err:.1f}%. Every TRAP_POSITION in "
                  f"um is wrong by that\n     factor and nothing reports it. Re-run the "
                  f"GUI's Magnification calibration for\n     this objective before any "
                  f"force or distance is taken from a commanded value.")
            report["verdict"] = f"OFF by {100*err:.1f}%"
        print(f"\n  ⚠ The angle above is not zero-by-assumption and was never recorded: "
              f"the AOD\n    axes have no stated relationship to the camera's rows and "
              f"columns. If it is not\n    ~0 or ~90 deg, a commanded x move is not a "
              f"camera-x move, and any analysis\n    that assumes it is will mix the "
              f"two axes.")

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "trap_calibration.json").write_text(
            json.dumps({**report, "excursions": excursions}, indent=2, default=str),
            encoding="utf-8")
        print(f"\n  report: {outdir / 'trap_calibration.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
