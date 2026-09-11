"""Quick command-line check of the velocity gate (lens 9).

    python -m velocity.cli check --velocity 20 --driver piezo_stage \\
        --step-ms 60 --radius-um 2.5 --viscosity 1e-3 --kappa 3.87 \\
        --sigma-nm 10 --fps 520 --target-error 0.05

    # the window alone, with no velocity proposed yet
    python -m velocity.cli window --radius-um 2.5 --viscosity 1e-3 \\
        --kappa 3.87 --sigma-nm 10 --target-error 0.05

``window`` is the useful one before a velocity has been chosen: both ends are
derived -- the floor from the precision target against the localization sigma,
the ceiling from the trap model's own refusal past the bead radius -- so it
answers "what may I command" rather than grading a guess.

⚠ ``check`` FAILS on every real configuration today, on L9.1, because no
commanded-versus-actual velocity exists anywhere in this repository. That is
the finding the lens was built to surface, not a defect in the CLI.
"""

from __future__ import annotations

import argparse
import sys

from .gate import evaluate
from .kinematics import (
    drag_coefficient_pn_s_per_um,
    minimum_offset_um,
    settling_time_constants,
    velocity_for_offset_um_per_s,
)
from .setup import DRIVERS, VelocitySetup


def cmd_window(args: argparse.Namespace) -> int:
    gamma = drag_coefficient_pn_s_per_um(args.radius_um, args.viscosity)
    x_min = minimum_offset_um(args.sigma_nm, args.target_error)
    v_min = velocity_for_offset_um_per_s(x_min, gamma, args.kappa)
    v_max = velocity_for_offset_um_per_s(args.radius_um, gamma, args.kappa)
    tau_ms = gamma / args.kappa * 1000
    n = settling_time_constants(args.target_error)

    print(f"\n{'=' * 72}")
    print(
        f"a = {args.radius_um} um   eta = {args.viscosity:g} Pa s   "
        f"kappa = {args.kappa} pN/um   sigma = {args.sigma_nm} nm   "
        f"target = {args.target_error:.0%}"
    )
    print("=" * 72)
    print(f"  gamma                 {gamma:.5f} pN s/um")
    print(f"  tau = gamma/kappa     {tau_ms:.2f} ms")
    print(f"  offset per um/s       {gamma / args.kappa * 1000:.2f} nm\n")
    print(f"  offset floor          {x_min * 1000:7.1f} nm   = sigma / target")
    print(
        f"  offset ceiling        {args.radius_um * 1000:7.1f} nm   "
        "= bead radius, where trap_force refuses"
    )
    print(f"\n  VELOCITY WINDOW       {v_min:.2f} - {v_max:.1f} um/s")
    print(f"  step duration         >= {n * tau_ms:.1f} ms  ({n:.2f} tau)")
    print(
        "\n  Neither end is a chosen constant: the floor is the precision you\n"
        "  asked for against the localization noise, the ceiling is the trap\n"
        "  model's own stated limit. Stay well inside the top -- linearity\n"
        "  departs a few percent by 20-40% of the radius, long before the\n"
        "  focus leaves the bead.\n"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    setup = VelocitySetup(
        commanded_velocity_um_per_s=args.velocity,
        driver=args.driver,
        step_duration_ms=args.step_ms,
        particle_radius_um=args.radius_um,
        viscosity_pa_s=args.viscosity,
        stiffness_pn_per_um=args.kappa,
        localization_sigma_nm=args.sigma_nm,
        achieved_fps=args.fps,
        target_relative_error=args.target_error,
        velocity_time_base_verified=args.time_base_verified,
        velocity_scale_ratio=args.scale_ratio,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    print(
        f"{args.velocity:g} um/s"
        + (f" on the {args.driver}" if args.driver else "")
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
            print(f"    {m:6.2f}  {code:34s} {bar}")

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
    return 0 if v.advances else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="velocity", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(q):
        q.add_argument("--radius-um", type=float, required=True)
        q.add_argument("--viscosity", type=float, required=True, help="Pa*s")
        q.add_argument("--kappa", type=float, required=True, help="pN/um, from lens 7")
        q.add_argument("--sigma-nm", type=float, required=True, help="from lens 2")
        q.add_argument(
            "--target-error", type=float, required=True,
            help="e.g. 0.05 -- EVERY bound here is derived from it",
        )

    w = sub.add_parser("window", help="the usable velocity window, both ends derived")
    common(w)
    w.set_defaults(func=cmd_window)

    c = sub.add_parser("check", help="run the committee-lens gate (L9.1-L9.5)")
    c.add_argument("--velocity", type=float, required=True, help="commanded, um/s")
    c.add_argument("--driver", choices=DRIVERS, default=None)
    c.add_argument("--step-ms", type=float, required=True, help="one velocity step")
    common(c)
    c.add_argument("--fps", type=float, default=None, help="achieved, from lens 2")
    c.add_argument(
        "--time-base-verified", action="store_true",
        help="a commanded um/s has been checked against the camera's timestamps "
        "-- NOT satisfied by the controller being closed-loop",
    )
    c.add_argument("--scale-ratio", type=float, default=None, help="actual/commanded")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
