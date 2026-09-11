"""Quick command-line report from the mechanical/environmental lens (lens 8).

    python -m stability.cli check --duration-min 60 --objective 100x-Oil \\
        --emission-nm 520 \\
        --particle-radius-um 0.5 --delta-density 50 --viscosity 1e-3

    # density-matched suspension: the settling term vanishes
    python -m stability.cli check --duration-min 60 --objective 100x-Oil \\
        --emission-nm 520 \\
        --particle-radius-um 0.5 --delta-density 0 --viscosity 1e-3

``check`` runs stability.gate.evaluate, which since 2026-09-10 is a REPORT and
not a verdict: G31 (settling velocity and the time to reach the floor), G32
(evaporative concentration, or that it is unquantified) and `drift_budget` (the
drift rate this run could absorb). Every check is INFO, so **every margin reads
10.00 and none of them means anything** -- `status: REPORT`,
`feasibility: N/A`, `advances: None`. Nothing here can pass or fail.
kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md

THERE ARE NO DRIFT FLAGS AND THAT IS NOT AN OMISSION. G29 (axial drift) and
G30 (lateral drift) left this lens on 2026-09-10, with G28 (PFS lock), because
a drift rate is measured during a run and so cannot be an input to a design.
What the run CAN be told in advance is how much drift it would tolerate, and
`stability.drift_budget` reports that from the duration and the depth of field
with no extra flag. kb/decisions/2026-09-10-drift-is-not-a-design-element.md
"""

from __future__ import annotations

import argparse
import sys

from optics.components import find_objective, objective_keys

from .gate import evaluate
from .setup import StabilitySetup


def cmd_check(args: argparse.Namespace) -> int:
    objective = None
    if args.objective:
        objective = find_objective(args.objective)
        if objective is None:
            print(
                f"unknown objective {args.objective!r}. "
                f"Known: {', '.join(objective_keys())}",
                file=sys.stderr,
            )
            return 2

    setup = StabilitySetup(
        duration_min=args.duration_min,
        objective=objective,
        emission_nm=args.emission_nm,
        depth_of_field_um=args.depth_of_field_um,
        particle_radius_um=args.particle_radius_um,
        delta_density_kg_m3=args.delta_density,
        viscosity_pa_s=args.viscosity,
        chamber_height_um=args.chamber_height_um,
        chamber_sealed=args.sealed,
        evaporation_rate_ul_per_hour=args.evaporation_ul_per_hour,
        sample_volume_ul=args.sample_volume_ul,
    )
    v = evaluate(setup)

    dof = setup.resolved_dof_um
    print(f"\n{'=' * 72}")
    print(
        f"{args.duration_min:.0f} min"
        + (f"  DOF {dof:.3f} um" if dof is not None else "  DOF unknown")
        + f"   ->  {v.status}"
    )
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   "
        "advances: n/a (reporting section -- neither advances nor blocks)"
    )
    if v.assumed_inputs:
        print("assumed:")
        for a in v.assumed_inputs:
            print(f"  - {a}")
    print("=" * 72)

    # DELIBERATELY NO MARGINS BLOCK, as in photo/cli.py. Nothing here is
    # graded, so every entry would be MAX_MARGIN with a full bar -- which reads
    # as "lots of headroom" from a section that measured no limit at all, and
    # on this lens in particular that would read as "the run is stable". The
    # numbers are in `metrics`; the words are in `findings`, and every check
    # reaches it because no check returns severity "ok".

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
    return 0 if v.status == "REPORT" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="stability", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="report on settling, evaporation and the drift budget")
    c.add_argument("--duration-min", type=float, required=True, help="acquisition length")
    c.add_argument("--objective", default=None, help="key from data/objectives.yaml, for the DOF")
    c.add_argument("--emission-nm", type=float, default=None)
    c.add_argument("--depth-of-field-um", type=float, default=None, help="override the computed DOF")

    c.add_argument("--particle-radius-um", type=float, default=None)
    c.add_argument(
        "--delta-density", type=float, default=None,
        help="particle minus medium density, kg/m^3; 0 for density-matched",
    )
    c.add_argument("--viscosity", type=float, default=None, help="medium viscosity, Pa s")
    c.add_argument("--chamber-height-um", type=float, default=None)

    c.add_argument("--sealed", action="store_true", help="chamber is sealed")
    c.add_argument("--evaporation-ul-per-hour", type=float, default=None)
    c.add_argument("--sample-volume-ul", type=float, default=None)
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
