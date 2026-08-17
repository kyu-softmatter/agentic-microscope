"""Quick command-line verification of the mechanical/environmental gate (lens 8).

    python -m stability.cli check --duration-min 60 --objective 100x-Oil \\
        --emission-nm 520 --axial-drift-nm-per-min 5 --pfs-on --pfs-in-range \\
        --particle-radius-um 0.5 --delta-density 50 --viscosity 1e-3

    # density-matched suspension: the settling term vanishes
    python -m stability.cli check --duration-min 60 --objective 100x-Oil \\
        --emission-nm 520 --axial-drift-nm-per-min 5 --pfs-on --pfs-in-range \\
        --particle-radius-um 0.5 --delta-density 0 --viscosity 1e-3

``check`` runs the committee-lens gate (stability.gate.evaluate): PFS lock
(G28), axial drift (G29), lateral drift (G30), sedimentation (G31), evaporation
(G32).

There is no measured drift rate anywhere in the repo, so --axial-drift-nm-per-min
has to be supplied and the gate BLOCKS without it. That is the honest state, not
a CLI limitation: see the module docstring.
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
        axial_drift_rate_nm_per_min=args.axial_drift_nm_per_min,
        lateral_drift_rate_nm_per_min=args.lateral_drift_nm_per_min,
        lateral_tolerance_um=args.lateral_tolerance_um,
        pfs_enabled=args.pfs_on if args.pfs_on or args.pfs_off else None,
        pfs_in_range=args.pfs_in_range if args.pfs_in_range or args.pfs_out_of_range else None,
        particle_radius_um=args.particle_radius_um,
        delta_density_kg_m3=args.delta_density,
        viscosity_pa_s=args.viscosity,
        chamber_height_um=args.chamber_height_um,
        chamber_sealed=args.sealed,
        evaporation_rate_ul_per_hour=args.evaporation_ul_per_hour,
        sample_volume_ul=args.sample_volume_ul,
        vibration_measured=args.vibration_measured,
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
            print(f"    {m:6.2f}  {code:30s} {bar}")

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
    p = argparse.ArgumentParser(prog="stability", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G28-G32)")
    c.add_argument("--duration-min", type=float, required=True, help="acquisition length")
    c.add_argument("--objective", default=None, help="key from data/objectives.yaml, for the DOF")
    c.add_argument("--emission-nm", type=float, default=None)
    c.add_argument("--depth-of-field-um", type=float, default=None, help="override the computed DOF")

    c.add_argument(
        "--axial-drift-nm-per-min", type=float, default=None,
        help="MEASURED axial drift rate; nothing in kb/calibrations/ has one",
    )
    c.add_argument("--lateral-drift-nm-per-min", type=float, default=None)
    c.add_argument(
        "--lateral-tolerance-um", type=float, default=None,
        help="for tracking this is the search window, not the field",
    )

    c.add_argument("--pfs-on", action="store_true", help="PFS-FocusMaintenance was On")
    c.add_argument("--pfs-off", action="store_true", help="PFS-FocusMaintenance was Off")
    c.add_argument("--pfs-in-range", action="store_true", help="PFS in Range")
    c.add_argument("--pfs-out-of-range", action="store_true", help="PFS reported Out of Range")

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
    c.add_argument("--vibration-measured", action="store_true")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    if args.pfs_on and args.pfs_off:
        print("--pfs-on and --pfs-off are contradictory", file=sys.stderr)
        return 2
    if args.pfs_in_range and args.pfs_out_of_range:
        print("--pfs-in-range and --pfs-out-of-range are contradictory", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
