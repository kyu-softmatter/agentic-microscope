"""Quick command-line verification against the GOA MATLAB output shape.

    python -m trapping.cli force-curve --dial 50 --n-traps 1
    python -m trapping.cli force-curve --dial 50 --n-traps 3 --radius-um 2.5
    python -m trapping.cli check --dial 50 --n-traps 1

``force-curve`` prints radial/axial force (and radial stiffness) vs. bead
displacement -- the same sweep GOA_ab.m plots, but as a table, and with the
laser dial and trap-splitting the MATLAB script does not model. ``check``
runs the committee-lens gate (trapping.gate.evaluate): confinement, trap
depth (U/kT), and G14 sampling (corner frequency).
"""

from __future__ import annotations

import argparse
import sys

from .dynamics import TrapSetup, water_viscosity_pa_s
from .gate import evaluate
from .goa import Bead, Medium, ObjectiveBeam, radial_stiffness_n_per_m, ray_optics_regime, trap_force
from .laser import LaserCalibration, power_per_trap


def cmd_force_curve(args: argparse.Namespace) -> int:
    bead = Bead(radius_m=args.radius_um * 1e-6, n=args.n_bead)
    medium = Medium(n=args.n_medium)
    beam = ObjectiveBeam(na=args.na, wavelength_m=args.wavelength_nm * 1e-9)

    regime, x = ray_optics_regime(bead, beam, medium)
    if regime != "ray_optics":
        print(
            f"refusing: Mie size parameter x={x:.2f} puts this bead in the "
            f"'{regime}' regime, not ray optics -- a GOA number here would be "
            "fiction.",
            file=sys.stderr,
        )
        return 1

    cal = LaserCalibration(placeholder_max_w=args.max_power_w)
    if not cal.measured:
        print(
            f"note: laser calibration is a placeholder (linear to "
            f"{args.max_power_w * 1000:.1f} mW at dial=100%) -- not measured. "
            "Pass measured dial%->W points before trusting absolute force "
            "numbers.\n",
            file=sys.stderr,
        )

    power_w = power_per_trap(cal, args.dial, args.n_traps)[0]
    na_eff = beam.effective_na(medium)
    print(
        f"bead: r={args.radius_um} um  n={args.n_bead}   medium n={args.n_medium}"
        f"   NA={args.na}  lambda0={args.wavelength_nm} nm"
    )
    if beam.clipped_by_tir(medium):
        print(
            f"      NA clipped {args.na} -> {na_eff:.4g} by total internal "
            f"reflection at the coverslip/sample interface; forces below are an "
            f"UPPER BOUND (transmission -> 0 at the critical angle, and "
            f"spherical aberration is not modelled)."
        )
    print(
        f"laser: dial={args.dial}%  n_traps={args.n_traps}  "
        f"-> {power_w * 1000:.4f} mW at this trap\n"
    )

    print(f"{'dx (um)':>10s} {'F_radial (pN)':>15s} {'F_axial (pN)':>15s}")
    n_steps = args.n_points
    max_dx = 0.98 * args.radius_um  # stay inside the model's valid geometry
    for i in range(n_steps):
        dx_um = max_dx * i / (n_steps - 1)
        f_radial, f_axial = trap_force(power_w, dx_um * 1e-6, bead, medium, beam)
        print(f"{dx_um:10.3f} {f_radial * 1e12:15.4f} {f_axial * 1e12:15.4f}")

    kappa = radial_stiffness_n_per_m(power_w, bead, medium, beam)
    print(f"\nradial stiffness at x=0: {kappa * 1e-6 * 1e12:.4f} pN/um")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    bead = Bead(radius_m=args.radius_um * 1e-6, n=args.n_bead)

    viscosity = args.viscosity_pa_s
    if viscosity is None:
        if abs(args.n_medium - 1.33) > 1e-6:
            print(
                "no --viscosity-pa-s given, and --n-medium is not water's "
                "1.33 -- cannot default a viscosity for an unknown medium.",
                file=sys.stderr,
            )
            return 1
        viscosity = water_viscosity_pa_s(args.temperature_c)
    medium = Medium(n=args.n_medium, viscosity_pa_s=viscosity)
    beam = ObjectiveBeam(na=args.na, wavelength_m=args.wavelength_nm * 1e-9)
    cal = LaserCalibration(placeholder_max_w=args.max_power_w)
    weights = [float(w) for w in args.weights.split(",")] if args.weights else None

    setup = TrapSetup(
        bead=bead,
        medium=medium,
        beam=beam,
        calibration=cal,
        dial_percent=args.dial,
        n_traps=args.n_traps,
        weights=weights,
        temperature_k=args.temperature_c + 273.15,
        temperature_measured=args.temperature_measured,
        detector_fps=args.detector_fps,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    na_eff = beam.effective_na(medium)
    print(
        f"trap: r={args.radius_um} um bead, n_traps={args.n_traps}, "
        f"dial={args.dial}%   ->  {v.status}"
    )
    print(
        f"NA:       design {args.na}"
        + (
            f"  ->  effective {na_eff:.4g} (clipped by TIR in n={args.n_medium})"
            if beam.clipped_by_tir(medium)
            else f"  (fully admitted by n={args.n_medium})"
        )
    )
    print(
        f"evidence: {v.evidence}   confidence: {v.confidence}   "
        f"advances: {'YES' if v.advances else 'NO'}"
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
            mark = {"fail": "[FAIL]", "info": "[info]"}.get(f.severity, f.severity)
            print(f"    {mark} {f.code}")
            print(f"           {f.message}")
            if f.action:
                print(f"        -> {f.action}")
    print()
    return 0 if v.status == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trapping", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("force-curve", help="print radial/axial force vs. displacement")
    f.add_argument("--dial", type=float, default=100.0, help="laser dial setting, 0-100%%")
    f.add_argument("--n-traps", type=int, default=1, help="number of simultaneous traps sharing the beam")
    f.add_argument("--max-power-w", type=float, default=1.0, help="placeholder power at dial=100%% (W) until calibrated")
    f.add_argument("--radius-um", type=float, default=2.5, help="bead radius (um)")
    f.add_argument("--n-bead", type=float, default=1.45, help="bead refractive index")
    f.add_argument("--n-medium", type=float, default=1.33, help="medium refractive index")
    f.add_argument("--na", type=float, default=1.33, help="objective numerical aperture")
    f.add_argument("--wavelength-nm", type=float, default=1064.0, help="laser wavelength (nm)")
    f.add_argument("--n-points", type=int, default=15, help="number of displacement steps")
    f.set_defaults(func=cmd_force_curve)

    c = sub.add_parser("check", help="run the committee-lens gate (confinement, U/kT, G14 sampling)")
    c.add_argument("--dial", type=float, default=100.0, help="laser dial setting, 0-100%%")
    c.add_argument("--n-traps", type=int, default=1, help="number of simultaneous traps sharing the beam")
    c.add_argument("--weights", help="comma-separated per-trap power-split weights (default: equal split)")
    c.add_argument("--max-power-w", type=float, default=1.0, help="placeholder power at dial=100%% (W) until calibrated")
    c.add_argument("--radius-um", type=float, default=2.5, help="bead radius (um)")
    c.add_argument("--n-bead", type=float, default=1.45, help="bead refractive index")
    c.add_argument("--n-medium", type=float, default=1.33, help="medium refractive index")
    c.add_argument("--na", type=float, default=1.33, help="objective numerical aperture")
    c.add_argument("--wavelength-nm", type=float, default=1064.0, help="laser wavelength (nm)")
    c.add_argument(
        "--temperature-c", type=float, default=20.0,
        help="medium temperature in Celsius (default 20 -- this project's room-temperature default)",
    )
    c.add_argument(
        "--temperature-measured", action="store_true",
        help="mark --temperature-c as an actual measurement rather than the 20C default",
    )
    c.add_argument(
        "--viscosity-pa-s", type=float, default=None,
        help="medium dynamic viscosity, Pa*s (default: looked up for water at --temperature-c; "
        "required explicitly if --n-medium isn't water's 1.33)",
    )
    c.add_argument(
        "--detector-fps", type=float, default=None,
        help="achieved camera frame rate from lens 2, to gate G14 sampling directly",
    )
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
