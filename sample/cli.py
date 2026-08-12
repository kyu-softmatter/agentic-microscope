"""Quick command-line verification of the sample-geometry-lens gate (lens 4).

    python -m sample.cli check --label "100x Oil" --mag 100 --na 1.45 \\
        --immersion oil --wd-um 130 --imaging-depth-um 15

    # the same depth with the index-matched water objective
    python -m sample.cli check --label "40x WI" --mag 40 --na 1.25 \\
        --immersion water --wd-um 200 --imaging-depth-um 15

``check`` runs the committee-lens gate (sample.gate.evaluate): NA
feasibility (G15), working distance (G16), refractive-index mismatch (G17),
coverslip thickness (G18), count in field (G19).

Objective values for the six objectives on the current nosepiece are recorded
in kb/systems/current.md > objectives.
"""

from __future__ import annotations

import argparse
import sys

from optics.components import Objective

from .gate import evaluate
from .setup import SampleSetup


def cmd_check(args: argparse.Namespace) -> int:
    objective = Objective(
        label=args.label,
        magnification=args.mag,
        na=args.na,
        immersion=args.immersion,
        wd_um=args.wd_um,
        coverslip_um=args.coverslip_design_um,
        correction_collar=args.correction_collar,
        verified_na=args.verified_na,
    )
    setup = SampleSetup(
        objective=objective,
        imaging_depth_um=args.imaging_depth_um,
        n_sample=args.n_sample,
        coverslip_actual_um=args.coverslip_actual_um,
        multiphase=args.multiphase,
        birefringent=args.birefringent,
        concentration_per_ml=args.concentration_per_ml,
        field_width_um=args.field_width_um,
        field_height_um=args.field_height_um,
        emission_nm=args.emission_nm,
        collar_adjusted=args.collar_adjusted,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    print(
        f"{args.label}  NA {args.na:.2f} {args.immersion}"
        + (f"  depth {args.imaging_depth_um:.1f} um" if args.imaging_depth_um else "")
        + f"   ->  {v.status}"
    )
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   advances: {'YES' if v.advances else 'NO'}"
    )
    if v.assumed_inputs:
        print("assumed:")
        for a in v.assumed_inputs:
            print(f"  - {a}")
    print("=" * 72)

    if v.margins:
        print("\n  margins (achieved / required; 1.0 = exactly at the limit)")
        for code, m in sorted(v.margins.items(), key=lambda kv: kv[1]):
            bar = "#" * min(int(m * 10), 30)
            print(f"    {m:6.2f}  {code:28s} {bar}")

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
    p = argparse.ArgumentParser(prog="sample", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G15-G19)")
    c.add_argument("--label", default="objective", help="objective label, for messages")
    c.add_argument("--mag", type=float, default=100.0, help="magnification")
    c.add_argument("--na", type=float, required=True, help="engraved numerical aperture")
    c.add_argument(
        "--immersion", default="oil",
        help="air | dry | water | glycerol | silicone | oil (optics.components.IMMERSION_N)",
    )
    c.add_argument("--wd-um", type=float, default=None, help="working distance, um")
    c.add_argument("--imaging-depth-um", type=float, default=None, help="depth past the coverslip, um")
    c.add_argument(
        "--n-sample", type=float, default=None,
        help="sample-medium refractive index; omitted, the water default 1.333 is assumed",
    )
    c.add_argument("--coverslip-design-um", type=float, default=170.0)
    c.add_argument(
        "--coverslip-actual-um", type=float, default=None,
        help="measured coverslip thickness; omitted, the design value is assumed",
    )
    c.add_argument("--correction-collar", action="store_true", help="objective has a correction collar")
    c.add_argument("--collar-adjusted", action="store_true", help="the collar was adjusted for this coverslip")
    c.add_argument("--verified-na", action="store_true", help="NA confirmed against the barrel/catalogue")
    c.add_argument("--multiphase", action="store_true", help="ATPS or other multi-phase sample")
    c.add_argument("--birefringent", action="store_true", help="liquid crystal or other birefringent sample")
    c.add_argument("--concentration-per-ml", type=float, default=None)
    c.add_argument("--field-width-um", type=float, default=None)
    c.add_argument("--field-height-um", type=float, default=None)
    c.add_argument("--emission-nm", type=float, default=None, help="for the overlap/resolution comparison")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
