"""Quick command-line verification of the photo-perturbation-lens gate (lens 5).

    python -m photo.cli check --dye FITC --power-mw 2.0 --area-um2 10000 \\
        --wavelength-nm 488 --exposure-ms 50 --n-frames 1000 \\
        --bleach-photons 3e4

``check`` runs the committee-lens gate (photo.gate.evaluate): photobleaching
(G10), saturation / triplet shelving (G20), light-driving (G21), total dose
(G22), plus the unowned trap-heating notice.

``--dye`` pulls epsilon, quantum yield and lifetime from
data/fluorophores.yaml. Note that no dye in that registry has bleach_photons,
so G10 blocks until --bleach-photons is supplied -- and no source line has a
measured sample-plane power, so --power-mw has to be supplied too. Both gaps
are real, not CLI limitations: see docs/07-roadmap.md Phase 0.
"""

from __future__ import annotations

import argparse
import sys

from optics.components import find_dye

from .gate import evaluate
from .setup import IlluminationSetup


def cmd_check(args: argparse.Namespace) -> int:
    ext_coeff = args.ext_coeff
    quantum_yield = args.quantum_yield
    lifetime_ns = args.lifetime_ns
    bleach_photons = args.bleach_photons
    label = args.dye or "dye"

    if args.dye:
        dye = find_dye(args.dye)
        if dye is None:
            print(f"unknown dye {args.dye!r}", file=sys.stderr)
            return 2
        label = dye.name
        ext_coeff = ext_coeff if ext_coeff is not None else dye.ext_coeff
        quantum_yield = quantum_yield if quantum_yield is not None else dye.quantum_yield
        lifetime_ns = lifetime_ns if lifetime_ns is not None else dye.lifetime_ns
        bleach_photons = (
            bleach_photons if bleach_photons is not None else dye.bleach_photons
        )

    setup = IlluminationSetup(
        power_mw_at_sample=args.power_mw,
        illuminated_area_um2=args.area_um2,
        wavelength_nm=args.wavelength_nm,
        exposure_ms=args.exposure_ms,
        n_frames=args.n_frames,
        frame_interval_ms=args.frame_interval_ms,
        ext_coeff_m1cm1=ext_coeff,
        quantum_yield=quantum_yield,
        lifetime_ns=lifetime_ns,
        bleach_photons=bleach_photons,
        photoresponsive=args.photoresponsive,
        light_driving_threshold_w_cm2=args.light_driving_threshold,
        dose_limit_j_cm2=args.dose_limit,
        trap_on=args.trap_on,
    )
    v = evaluate(setup)

    irr = setup.resolved_irradiance
    print(f"\n{'=' * 72}")
    print(
        f"{label}"
        + (f" @ {args.wavelength_nm:.0f} nm" if args.wavelength_nm else "")
        + (f"  {irr:.1f} W/cm^2" if irr is not None else "  irradiance unknown")
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
            print(f"    {m:6.2f}  {code:36s} {bar}")

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
    p = argparse.ArgumentParser(prog="photo", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G10, G20-G22)")
    c.add_argument("--dye", default=None, help="key from data/fluorophores.yaml, e.g. FITC")
    c.add_argument(
        "--power-mw", type=float, default=None,
        help="MEASURED mW at the sample plane. Empty in data/light_sources.yaml "
        "for every line, so it must be supplied until a power meter reading exists.",
    )
    c.add_argument("--area-um2", type=float, default=None, help="illuminated area at the sample")
    c.add_argument("--wavelength-nm", type=float, default=None, help="excitation line centre")
    c.add_argument("--exposure-ms", type=float, default=None)
    c.add_argument("--n-frames", type=int, default=None)
    c.add_argument("--frame-interval-ms", type=float, default=None, help="for the duty cycle")
    c.add_argument("--ext-coeff", type=float, default=None, help="override epsilon, M^-1 cm^-1")
    c.add_argument("--quantum-yield", type=float, default=None)
    c.add_argument("--lifetime-ns", type=float, default=None)
    c.add_argument(
        "--bleach-photons", type=float, default=None,
        help="mean photons emitted before bleaching; no dye in the registry has one",
    )
    c.add_argument(
        "--photoresponsive", action="store_true",
        help="the light can drive this sample (active particles, photo-crosslinking, LC)",
    )
    c.add_argument(
        "--light-driving-threshold", type=float, default=None,
        help="W/cm^2 above which the sample responds; required if --photoresponsive",
    )
    c.add_argument("--dose-limit", type=float, default=None, help="J/cm^2 ceiling, if any")
    c.add_argument("--trap-on", action="store_true", help="the 1064 nm trap is in use")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
