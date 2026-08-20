"""Quick command-line verification of the detection-lens gate.

    python -m detection.cli check --detector Kinetix22 --mode Sensitivity \\
        --na 1.45 --wavelength-em-nm 668 --mag-objective 100 \\
        --exposure-ms 80 --task-kind tracking \\
        --roi-height-px 176 --row-time-us 3.5312 \\
        --signal-e-per-s 5000 --background-e-per-s 200

(The example used to pass `--pixel-um`, which is not an argument -- pixel pitch
comes from the detector registry -- and `--row-time-us 10.28`, which is the
archive Prime95B's row time, not this camera's.)

``check`` runs the committee-lens gate (detection.gate.evaluate): sampling
(G5), saturation (G6), SNR (G7), motion blur (G8), frame-rate realizability
(G9).

``from-frame`` runs it backwards: give it one measured test frame and it
computes which readout mode and what exposure the experiment needs
(detection.recommend). The acquisition recipe for that frame -- despeckle off,
dark frame for the offset, peak measured on the *dim* population -- is written
out at the top of kb/calibrations/frame-photometry.yaml.

    python -m detection.cli from-frame --detector Kinetix22 --mode Sensitivity \\
        --exposure-ms 50 --peak-adu 1500 --background-adu 300 --offset-adu 100 \\
        --n-pix-spot 9 --target-snr 5 --target-fps 100 --task-kind tracking \\
        --roi-height-px 256
"""

from __future__ import annotations

import argparse
import sys

from optics.components import Objective, find_detector

from .gate import evaluate
from .setup import Acquisition, Camera, DetectionSetup, PhotonBudget


def cmd_check(args: argparse.Namespace) -> int:
    detector = find_detector(args.detector)
    if detector is None:
        print(
            f"unknown detector '{args.detector}'. See data/detectors.yaml.",
            file=sys.stderr,
        )
        return 1

    objective = Objective(
        label=f"{args.mag_objective:.0f}x",
        magnification=args.mag_objective,
        na=args.na,
        verified_na=args.na_measured,
    )
    camera = Camera(
        detector=detector,
        mode=args.mode,
        binning=args.binning,
        roi_height_px=args.roi_height_px,
        row_time_us=args.row_time_us,
        frame_overhead_ms=args.frame_overhead_ms,
        offset_adu=args.offset_adu,
    )
    acquisition = Acquisition(
        exposure_ms=args.exposure_ms,
        task_kind=args.task_kind,
        target_fps=args.target_fps,
    )
    photons = PhotonBudget(
        signal_e_per_s=args.signal_e_per_s,
        background_e_per_s=args.background_e_per_s,
        n_pix_spot=args.n_pix_spot,
        target_snr=args.target_snr,
        target_localization_precision_nm=args.target_precision_nm,
        diffusion_coefficient_m2_s=args.diffusion_m2_s,
    )
    setup = DetectionSetup(
        objective=objective,
        wavelength_em_nm=args.wavelength_em_nm,
        mag_objective=args.mag_objective,
        mag_intermediate=args.mag_intermediate,
        camera=camera,
        acquisition=acquisition,
        photons=photons,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    print(
        f"detector={args.detector} mode={args.mode}  exposure={args.exposure_ms} ms  "
        f"task={args.task_kind}   ->  {v.status}"
    )
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   advances: {'YES' if v.advances else 'NO'}"
    )
    if v.assumed_inputs:
        print(f"assumed:  {', '.join(v.assumed_inputs)}")
    print("=" * 72)

    if v.margins:
        print("\n  margins (achieved / required; 1.0 = exactly at the limit)")
        for code, m in sorted(v.margins.items(), key=lambda kv: kv[1]):
            bar = "#" * min(int(m * 10), 30)
            print(f"    {m:6.2f}  {code:20s} {bar}")

    if v.findings:
        print("\n  findings")
        for f in v.findings:
            mark = {"fail": "[FAIL]", "warn": "[WARN]", "info": "[info]"}.get(
                f.severity, f.severity
            )
            print(f"    {mark} {f.code}")
            print(f"           {f.message}")
            if f.action:
                print(f"        -> {f.action}")
    print()
    return 0 if v.advances or v.status == "PASS" else 1


def cmd_from_frame(args: argparse.Namespace) -> int:
    """One measured frame -> which mode, what exposure. See detection.recommend."""
    from .recommend import FrameMeasurement, compare_modes, electron_rates, validate

    detector = find_detector(args.detector)
    if detector is None:
        print(
            f"unknown detector '{args.detector}'. See data/detectors.yaml.",
            file=sys.stderr,
        )
        return 1

    frame = FrameMeasurement(
        exposure_ms=args.exposure_ms,
        mode=args.mode,
        peak_adu=args.peak_adu,
        background_adu=args.background_adu,
        offset_adu=args.offset_adu,
        n_pix_spot=args.n_pix_spot,
        despeckle_off=None if args.despeckle_unchecked else True,
        subject=args.subject,
    )

    refusals = validate(frame, detector)
    if refusals:
        print(f"\n{'=' * 72}")
        print(f"frame UNUSABLE  ({len(refusals)} problem(s))")
        print("=" * 72)
        for r in refusals:
            print(f"\n  [REFUSE] {r.code}")
            print(f"           {r.message}")
            print(f"        -> {r.action}")
        print()
        return 1

    signal, background = electron_rates(frame, detector)
    dark = detector.dark_e_per_s or 0.0

    print(f"\n{'=' * 72}")
    print(
        f"detector={args.detector}  frame taken in {args.mode} at "
        f"{args.exposure_ms} ms" + (f"  ({args.subject})" if args.subject else "")
    )
    print("=" * 72)
    print("\n  measured rates (mode-independent -- these transfer to every mode)")
    print(f"    signal      {signal:12.1f} e-/s   at the brightest pixel, background removed")
    print(f"    background  {background:12.1f} e-/s   the one input docs/04 §4 calls unmeasurable")
    print(f"    dark        {dark:12.1f} e-/s   {'registry value' if detector.dark_e_per_s else 'assumed 0'}")
    if frame.despeckle_off is None:
        print("\n  [WARN] despeckle not confirmed off. If it was on, every number")
        print("         above is invalid (docs/06-pitfalls.md C1) -- re-run with")
        print("         --despeckle-unchecked removed once verified.")

    options = compare_modes(
        frame,
        detector,
        target_snr=args.target_snr,
        roi_height_px=args.roi_height_px,
        target_fps=args.target_fps,
        task_kind=args.task_kind,
    )

    print(f"\n  modes, best first (target SNR {args.target_snr:g}", end="")
    if args.target_fps:
        print(f", {args.target_fps:g} fps", end="")
    if args.task_kind:
        print(f", {args.task_kind}", end="")
    print(")")
    header = (
        f"    {'mode':<14}{'exposure':>10}{'SNR':>7}{'max fps':>9}"
        f"{'sat ms':>10}{'read e-':>9}  binding"
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for o in options:
        mark = " " if o.feasible else "x"
        exp = f"{o.exposure_ms:.2f} ms" if o.exposure_ms is not None else "--"
        snr = f"{o.snr_achieved:.1f}" if o.snr_achieved is not None else "--"
        fps = f"{o.max_fps:.0f}" if o.max_fps is not None else "--"
        print(
            f"  {mark} {o.mode:<14}{exp:>10}{snr:>7}{fps:>9}"
            f"{o.ceiling_saturation_ms:>10.2f}{o.effective_read_noise_e:>9.2f}"
            f"  {o.binding_constraint}"
        )
        for n in o.notes:
            print(f"      - {n}")

    winner = next((o for o in options if o.feasible), None)
    print()
    if winner is None:
        print("  NO MODE WORKS on these targets. The fix is upstream of this lens:")
        print("  more light (lens 1/5), a brighter label (lens 5), a slower frame")
        print("  rate (lens 6 decides if that is acceptable), or a larger spot.")
    else:
        print(f"  -> {winner.mode} at {winner.exposure_ms:.2f} ms, SNR "
              f"{winner.snr_achieved:.1f}, limited by {winner.binding_constraint}.")
        print("     Exposure is the *minimum* that meets the target -- longer only")
        print("     adds photobleaching dose (lens 5) and motion blur (G8).")
        print()
        print("  paste into kb/calibrations/frame-photometry.yaml:")
        print(f"    - sample: {args.subject or '<name>'}")
        print("      date: <YYYY-MM-DD>")
        print(f"      detector: {args.detector}")
        print(f"      frame_mode: {args.mode}")
        print(f"      exposure_ms: {args.exposure_ms}")
        print(f"      peak_adu: {args.peak_adu}")
        print(f"      background_adu: {args.background_adu}")
        print(f"      offset_adu: {args.offset_adu}")
        print(f"      n_pix_spot: {args.n_pix_spot}")
        print(f"      signal_e_per_s: {signal:.1f}")
        print(f"      background_e_per_s: {background:.1f}")
        print(f"      despeckle_off: {str(frame.despeckle_off).lower()}")
        print(f"      recommended_mode: {winner.mode}")
        print(f"      recommended_exposure_ms: {winner.exposure_ms:.2f}")
    print()
    return 0 if winner is not None else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="detection", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G5-G9)")
    c.add_argument("--detector", default="Kinetix", help="detector name in data/detectors.yaml")
    c.add_argument("--mode", default=None, help="detector mode name (see data/detectors.yaml)")
    c.add_argument("--binning", type=int, default=1)
    c.add_argument("--na", type=float, required=True, help="objective numerical aperture")
    c.add_argument(
        "--na-measured", action="store_true", help="mark --na as read off the barrel"
    )
    c.add_argument("--mag-objective", type=float, required=True, help="objective magnification")
    c.add_argument("--mag-intermediate", type=float, default=1.0)
    c.add_argument("--wavelength-em-nm", type=float, required=True, help="dye emission peak (nm)")
    c.add_argument("--exposure-ms", type=float, required=True)
    c.add_argument("--task-kind", choices=["imaging", "tracking"], default=None)
    c.add_argument("--target-fps", type=float, default=None, help="desired frame rate, for G9")
    c.add_argument("--roi-height-px", type=int, default=None, help="ROI row count")
    c.add_argument(
        "--row-time-us", type=float, default=None,
        help="measured row/line time (overrides the detector mode's datasheet value)",
    )
    c.add_argument("--frame-overhead-ms", type=float, default=0.0)
    c.add_argument("--offset-adu", type=float, default=0.0)
    c.add_argument(
        "--signal-e-per-s", type=float, default=None,
        help="measured detected signal rate at the brightest pixel, e-/s",
    )
    c.add_argument("--background-e-per-s", type=float, default=None, help="measured background, e-/s")
    c.add_argument("--n-pix-spot", type=int, default=1)
    c.add_argument("--target-snr", type=float, default=None)
    c.add_argument("--target-precision-nm", type=float, default=None)
    c.add_argument("--diffusion-m2-s", type=float, default=None)
    c.set_defaults(func=cmd_check)

    f = sub.add_parser(
        "from-frame",
        help="one measured test frame -> which mode and what exposure",
        description=cmd_from_frame.__doc__,
    )
    f.add_argument("--detector", default="Kinetix22", help="detector name in data/detectors.yaml")
    f.add_argument(
        "--mode", required=True,
        help="the mode the FRAME was taken in -- needed for its conversion gain",
    )
    f.add_argument("--exposure-ms", type=float, required=True, help="exposure of the frame")
    f.add_argument(
        "--peak-adu", type=float, required=True,
        help="brightest pixel on the object, RAW ADU (no background subtraction)",
    )
    f.add_argument(
        "--background-adu", type=float, required=True,
        help="median of a particle-free but ILLUMINATED region, raw ADU",
    )
    f.add_argument(
        "--offset-adu", type=float, default=0.0,
        help="sensor zero from a dark frame at the same exposure",
    )
    f.add_argument(
        "--n-pix-spot", type=int, default=1,
        help="pixels the spot covers; ~2*pi*sigma_psf^2/p^2 if not counted",
    )
    f.add_argument(
        "--despeckle-unchecked", action="store_true",
        help="nobody verified despeckle was off -- results are reported but flagged",
    )
    f.add_argument("--target-snr", type=float, default=5.0)
    f.add_argument("--target-fps", type=float, default=None)
    f.add_argument("--task-kind", choices=["imaging", "tracking"], default=None)
    f.add_argument("--roi-height-px", type=int, default=None, help="ROI row count")
    f.add_argument("--subject", default=None, help="what the frame was of, for the record")
    f.set_defaults(func=cmd_from_frame)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
