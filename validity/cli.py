"""Quick command-line verification of the measurement-validity gate (lens 6).

    python -m validity.cli quantities

    python -m validity.cli power --n-particles 200 --n-frames 2000 \\
        --target-error 0.05

    python -m validity.cli check --quantity diffusion --target-error 0.05 \\
        --n-particles 200 --n-frames 2000 --pixel-size-measured \\
        --upstream-passed optics,detection,compute,sample,photo

``power`` runs G11 alone, which needs no upstream verdicts.

``check`` runs the whole gate. Because there is no orchestrator yet, the other
lenses' verdicts cannot be fetched automatically -- ``--upstream-passed`` is you
**declaring** which lenses returned a clean PASS. That is a statement of fact
you are making, not a computation, and the output says so. For real use, call
``validity.gate.evaluate`` with the actual Verdict objects.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from .gate import evaluate
from .power import relative_error, required_frames, required_particles
from .setup import QUANTITY_REQUIREMENTS, STANDING_LENSES, ValiditySetup


@dataclass
class _DeclaredVerdict:
    """A lens verdict the user asserted on the command line.

    Structurally a VerdictLike with no findings. Only for the CLI: it carries
    no computation, which is why `check` prints a warning when any is used.
    """

    status: str = "PASS"
    evidence: str = "assumed"
    feasibility: str = "UNKNOWN"
    margins: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def cmd_quantities(args: argparse.Namespace) -> int:
    print("\nintended quantity        required calibrations")
    print("-" * 72)
    for q in sorted(QUANTITY_REQUIREMENTS):
        print(f"{q:24s} {', '.join(QUANTITY_REQUIREMENTS[q])}")
    print(
        "\n'linearity' means pixel values must stay proportional to photons, "
        "which\ndespeckle and similar filters break (docs/06 C1).\n"
    )
    return 0


def cmd_power(args: argparse.Namespace) -> int:
    err = relative_error(args.n_particles, args.n_frames)
    print(f"\n{args.n_particles:.0f} particles x {args.n_frames} frames")
    print(f"  relative error   {err * 100:.3f}%")
    if args.target_error:
        met = err <= args.target_error
        print(f"  target           {args.target_error * 100:.3f}%")
        print(f"  verdict          {'meets target' if met else 'SHORT of target'}")
        if met:
            headroom = args.target_error / err if err > 0 else float("inf")
            print(f"  headroom         {headroom:.1f}x on the sample product")
        else:
            print(
                f"  to reach target  "
                f"{required_particles(args.target_error, args.n_frames):.0f}"
                f" particles at this frame count, or "
                f"{required_frames(args.target_error, args.n_particles):.0f} frames "
                "at this particle count"
            )
    print(
        "\nThis is a floor (docs/04 §7): correlated particles and long-lag MSD\n"
        "points both make the real error worse.\n"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    declared = [s.strip() for s in (args.upstream_passed or "").split(",") if s.strip()]
    unknown = [d for d in declared if d not in (*STANDING_LENSES, "trapping")]
    if unknown:
        print(
            f"unknown lens name(s): {', '.join(unknown)}. "
            f"Known: {', '.join((*STANDING_LENSES, 'trapping'))}",
            file=sys.stderr,
        )
        return 2

    setup = ValiditySetup(
        intended_quantity=args.quantity,
        target_relative_error=args.target_error,
        upstream={name: _DeclaredVerdict() for name in declared},
        n_particles=args.n_particles,
        n_frames=args.n_frames,
        pixel_size_measured=args.pixel_size_measured,
        background_measured=args.background_measured,
        dark_current_measured=args.dark_current_measured,
        flat_field_measured=args.flat_field_measured,
        despeckle_enabled=args.despeckle,
        corrections_applied=frozenset(
            s.strip() for s in (args.corrections or "").split(",") if s.strip()
        ),
        analysis_script=args.analysis_script,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    print(f"{args.quantity or '(no quantity stated)'}   ->  {v.status}")
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   advances: {'YES' if v.advances else 'NO'}"
    )
    if declared:
        print(
            f"\n  ! upstream verdicts for {', '.join(declared)} were DECLARED on "
            "the command line,\n    not computed. G23's bias ledger has nothing "
            "to review because a declared\n    verdict carries no findings — so "
            "a PASS here does not mean the biases were\n    checked. Call "
            "validity.gate.evaluate with real Verdict objects for that."
        )
    if v.assumed_inputs:
        print("\nassumed:")
        for a in v.assumed_inputs:
            print(f"  - {a}")
    print("=" * 72)

    if v.margins:
        print("\n  margins (achieved / required; 1.0 = exactly at the limit)")
        for code, m in sorted(v.margins.items(), key=lambda kv: kv[1]):
            bar = "#" * min(int(m * 10), 30)
            print(f"    {m:6.2f}  {code:38s} {bar}")

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
    p = argparse.ArgumentParser(prog="validity", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "quantities", help="show which calibrations each intended quantity needs"
    ).set_defaults(func=cmd_quantities)

    pw = sub.add_parser("power", help="statistical power alone (G11)")
    pw.add_argument("--n-particles", type=float, required=True)
    pw.add_argument("--n-frames", type=float, required=True)
    pw.add_argument("--target-error", type=float, default=None, help="e.g. 0.05 for 5%%")
    pw.set_defaults(func=cmd_power)

    c = sub.add_parser("check", help="run the committee-lens gate (G11, G23-G27)")
    c.add_argument("--quantity", default=None, help="see `quantities` for the list")
    c.add_argument("--target-error", type=float, default=None, help="e.g. 0.05 for 5%%")
    c.add_argument("--n-particles", type=float, default=None)
    c.add_argument("--n-frames", type=int, default=None)
    c.add_argument(
        "--upstream-passed", default=None,
        help="comma-separated lens names you are DECLARING returned a clean PASS",
    )
    c.add_argument("--pixel-size-measured", action="store_true")
    c.add_argument("--background-measured", action="store_true")
    c.add_argument("--dark-current-measured", action="store_true")
    c.add_argument("--flat-field-measured", action="store_true")
    c.add_argument(
        "--despeckle", action="store_true",
        help="on-camera despeckle was enabled (docs/06 C1)",
    )
    c.add_argument(
        "--corrections", default=None,
        help="comma-separated upstream finding codes that have an applied correction",
    )
    c.add_argument("--analysis-script", default=None, help="which script will process the data")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
