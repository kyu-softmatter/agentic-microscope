"""Quick command-line verification of the sample-geometry-lens gate (lens 4).

    python -m sample.cli list

    python -m sample.cli check --objective 100x-Oil --imaging-depth-um 15
    python -m sample.cli check --objective 40x-WI   --imaging-depth-um 15

    # "what if this water objective were used dry" -- G15 refuses
    python -m sample.cli check --objective 40x-WI --immersion air \\
        --imaging-depth-um 10

``check`` runs the committee-lens gate (sample.gate.evaluate): NA
feasibility (G15), working distance (G16), refractive-index mismatch (G17),
coverslip thickness (G18), count in field (G19).

``--objective`` reads NA, immersion, working distance, design coverslip and
correction collar from the data/objectives.yaml registry, which
config/scopes/*.yaml reference as the nosepiece. Source of truth for those
values is kb/systems/current.md > objectives. Pass --na/--immersion/--wd-um to
override a registry entry, or all of them plus --label for an objective that
is not on the nosepiece.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from optics.components import Objective, find_objective, objective_keys, objectives

from .gate import evaluate
from .setup import SampleSetup


def cmd_list(args: argparse.Namespace) -> int:
    """Show the nosepiece as recorded in data/objectives.yaml."""
    reg = objectives()
    print(f"\n{'key':12s} {'NA':>5s} {'immersion':10s} {'WD um':>7s} {'collar':>7s}  label")
    for key in objective_keys():
        obj = reg[key.lower()]
        wd = f"{obj.wd_um:.0f}" if obj.wd_um is not None else "-"
        print(
            f"{key:12s} {obj.na:5.2f} {obj.immersion:10s} {wd:>7s} "
            f"{'yes' if obj.correction_collar else '-':>7s}  {obj.label}"
        )
    print()
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if args.objective:
        objective = find_objective(args.objective)
        if objective is None:
            print(
                f"unknown objective {args.objective!r}. "
                f"Known: {', '.join(objective_keys())}",
                file=sys.stderr,
            )
            return 2
        # Any of these three supplied means "the registry entry, but with this
        # changed" -- which is how you ask what-if questions like using a water
        # objective dry. Each is applied independently.
        overrides = {
            k: v
            for k, v in (
                ("na", args.na),
                ("immersion", args.immersion),
                ("wd_um", args.wd_um),
            )
            if v is not None
        }
        if overrides:
            objective = replace(objective, **overrides)
    else:
        if args.na is None:
            print(
                "supply --objective <key> (see `list`) or --na for a manual "
                "objective",
                file=sys.stderr,
            )
            return 2
        objective = Objective(
            label=args.label,
            magnification=args.mag,
            na=args.na,
            immersion=args.immersion or "oil",
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
        f"{objective.label}  NA {objective.na:.2f} {objective.immersion}"
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

    sub.add_parser("list", help="show the nosepiece from data/objectives.yaml").set_defaults(
        func=cmd_list
    )

    c = sub.add_parser("check", help="run the committee-lens gate (G15-G19)")
    c.add_argument(
        "--objective", default=None,
        help="key from data/objectives.yaml, e.g. 100x-Oil or 40x-WI (see `list`). "
        "NA/WD/immersion/coverslip/collar all come from the registry.",
    )
    c.add_argument("--label", default="objective", help="label for a manual objective")
    c.add_argument("--mag", type=float, default=100.0, help="magnification, manual objective")
    c.add_argument(
        "--na", type=float, default=None,
        help="engraved numerical aperture; required unless --objective is given, "
        "and overrides the registry value if both are given",
    )
    c.add_argument(
        "--immersion", default=None,
        help="air | dry | water | glycerol | silicone | oil "
        "(optics.components.IMMERSION_N). Overrides the registry -- this is how "
        "you ask 'what if this objective were used dry'.",
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
