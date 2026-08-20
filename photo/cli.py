"""Quick command-line verification of the photo-perturbation-lens gate (lens 5).

    python -m photo.cli check --channel config/channels/proposed-2color.yaml \\
        --channel-name 488-FITC --power-mw 2.0 --area-um2 10000 \\
        --exposure-ms 50 --n-frames 1000 --bleach-photons 3e4 \\
        --not-photoresponsive

    python -m photo.cli check --dye FITC --power-mw 2.0 --area-um2 10000 \\
        --wavelength-nm 488 --exposure-ms 50 --n-frames 1000 \\
        --bleach-photons 3e4 --not-photoresponsive

``check`` runs the committee-lens gate (photo.gate.evaluate): photobleaching
(G10), saturation / triplet shelving (G20), light-driving (G21), total dose
(G22), plus the unowned trap-heating notice.

**Prefer ``--channel``.** It takes k_ex and k_em from lens 1
(``optics.path.Channel``), which weights the absorption cross-section by how
well the delivered spectrum actually overlaps the dye's absorption band. The
``--dye`` path has no spectra and so assumes that overlap is perfect unless
``--excitation-coupling`` says otherwise, which overstates k_ex and makes G10
and G20 stricter than the instrument warrants. Either way the verdict says
which path it took, under ``assumed``.

``--dye`` pulls epsilon, quantum yield and lifetime from
data/fluorophores.yaml. Note that no dye in that registry has bleach_photons,
so G10 blocks until --bleach-photons is supplied -- and no source line has a
measured sample-plane power, so --power-mw has to be supplied too. Both gaps
are real, not CLI limitations: see docs/07-roadmap.md Phase 0 (where laser
power measurement is deferred by decision as of 2026-08-19).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from optics.build import build_channels
from optics.components import find_dye

from .gate import evaluate
from .setup import IlluminationSetup


def _from_channel(args: argparse.Namespace) -> tuple[IlluminationSetup, str] | None:
    """Build from a lens 1 channel. The path where k_ex is right."""
    fixed = [
        name
        for name, value in (
            ("--dye", args.dye),
            ("--wavelength-nm", args.wavelength_nm),
            ("--ext-coeff", args.ext_coeff),
            ("--quantum-yield", args.quantum_yield),
            ("--excitation-coupling", args.excitation_coupling),
        )
        if value is not None
    ]
    if fixed:
        print(
            f"--channel already fixes {', '.join(fixed)}: the channel names "
            "its own dye and lens 1 has already used it to compute the "
            "excitation rate. Overriding one here would leave those rates "
            "inconsistent with the values they came from.",
            file=sys.stderr,
        )
        return None

    channels = build_channels(Path(args.channel))
    names = ", ".join(ch.name for ch in channels)
    if args.channel_name:
        picked = [ch for ch in channels if ch.name == args.channel_name]
        if not picked:
            print(
                f"no channel named {args.channel_name!r} in {args.channel}. "
                f"available: {names}",
                file=sys.stderr,
            )
            return None
        ch = picked[0]
    elif len(channels) == 1:
        ch = channels[0]
    else:
        print(
            f"{args.channel} holds {len(channels)} channels, so pick one with "
            f"--channel-name: {names}",
            file=sys.stderr,
        )
        return None

    setup = IlluminationSetup.from_channel(
        ch,
        power_mw_at_sample=args.power_mw,
        illuminated_area_um2=args.area_um2,
        exposure_ms=args.exposure_ms,
        n_frames=args.n_frames,
        frame_interval_ms=args.frame_interval_ms,
        photoresponsive=args.photoresponsive,
        light_driving_threshold_w_cm2=args.light_driving_threshold,
        dose_limit_j_cm2=args.dose_limit,
        trap_on=args.trap_on,
    )
    # These two stay overridable: no dye in the registry has bleach_photons and
    # only some have a lifetime, and neither feeds the rates lens 1 already
    # computed, so supplying them here leaves nothing inconsistent.
    overrides = {
        key: value
        for key, value in (
            ("bleach_photons", args.bleach_photons),
            ("lifetime_ns", args.lifetime_ns),
        )
        if value is not None
    }
    if overrides:
        setup = replace(setup, **overrides)
    return setup, f"{ch.name} ({ch.dye.name})"


def _from_flags(args: argparse.Namespace) -> tuple[IlluminationSetup, str] | None:
    """Build from bare numbers. No spectra, so no overlap weighting."""
    ext_coeff = args.ext_coeff
    quantum_yield = args.quantum_yield
    lifetime_ns = args.lifetime_ns
    bleach_photons = args.bleach_photons
    label = args.dye or "dye"

    if args.dye:
        dye = find_dye(args.dye)
        if dye is None:
            print(f"unknown dye {args.dye!r}", file=sys.stderr)
            return None
        label = dye.name
        ext_coeff = ext_coeff if ext_coeff is not None else dye.ext_coeff
        quantum_yield = quantum_yield if quantum_yield is not None else dye.quantum_yield
        lifetime_ns = lifetime_ns if lifetime_ns is not None else dye.lifetime_ns
        bleach_photons = (
            bleach_photons if bleach_photons is not None else dye.bleach_photons
        )

    return (
        IlluminationSetup(
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
            excitation_coupling=args.excitation_coupling,
            photoresponsive=args.photoresponsive,
            light_driving_threshold_w_cm2=args.light_driving_threshold,
            dose_limit_j_cm2=args.dose_limit,
            trap_on=args.trap_on,
        ),
        label,
    )


def cmd_check(args: argparse.Namespace) -> int:
    built = _from_channel(args) if args.channel else _from_flags(args)
    if built is None:
        return 2
    setup, label = built
    v = evaluate(setup)

    irr = setup.resolved_irradiance
    print(f"\n{'=' * 72}")
    print(
        f"{label}"
        + (f" @ {setup.wavelength_nm:.0f} nm" if setup.wavelength_nm else "")
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
    c.add_argument(
        "--channel", default=None, metavar="CONFIG",
        help="channel YAML (config/channels/*.yaml). Takes k_ex and k_em from "
        "lens 1, the only path that gets the spectral overlap right. Preferred.",
    )
    c.add_argument(
        "--channel-name", default=None,
        help="which channel in that file, if it holds more than one",
    )
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
        "--excitation-coupling", type=float, default=None,
        help="transmission-weighted mean absorption over the delivered band "
        "(lens 1's excitation_efficiency/source_delivery). Without it the "
        "--dye path assumes 1.0 and reports k_ex as assumed. --channel "
        "carries it already.",
    )
    resp = c.add_mutually_exclusive_group()
    resp.add_argument(
        "--photoresponsive", dest="photoresponsive", action="store_true", default=None,
        help="the light can drive this sample (active particles, photo-crosslinking, LC)",
    )
    resp.add_argument(
        "--not-photoresponsive", dest="photoresponsive", action="store_false", default=None,
        help="confirmed inert to this light. Say it explicitly -- left "
        "unanswered, G21 warns instead of passing (docs/06 D2)",
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
