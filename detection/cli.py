"""Quick command-line verification of the detection-lens gate.

    python -m detection.cli check --detector Kinetix --mode Sensitivity \\
        --na 1.45 --wavelength-em-nm 668 --mag-objective 100 \\
        --pixel-um 6.5 --exposure-ms 80 --task-kind tracking \\
        --roi-height-px 176 --row-time-us 10.28 \\
        --signal-e-per-s 5000 --background-e-per-s 200

``check`` runs the committee-lens gate (detection.gate.evaluate): sampling
(G5), saturation (G6), SNR (G7), motion blur (G8), frame-rate realizability
(G9).
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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
