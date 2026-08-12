"""Command-line front end for the optical lens.

    python -m optics.cli check config/channels/example.yaml
    python -m optics.cli check config/channels/example.yaml --json
    python -m optics.cli dyes
    python -m optics.cli filters
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from .build import build_channels
from .checks import GRADE_NOTES
from .components import filters, fluorophores
from .gate import evaluate
from .recommend import compare_sources, recommend_labels, recommend_panel

_MARK = {
    "PASS": "PASS",
    "PASS_WITH_CHANGES": "PASS (with changes)",
    "FAIL": "FAIL",
    "BLOCKED": "BLOCKED - insufficient information",
}
_SEV = {"fail": "[FAIL]", "warn": "[WARN]", "info": "[info]"}


def _fmt(value: float, unit: str = "", pct: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    if math.isinf(value):
        return "inf" + unit
    if pct:
        return f"{value * 100:.1f}%"
    return f"{value:.3g}{unit}"


def cmd_check(args: argparse.Namespace) -> int:
    channels = build_channels(Path(args.config))
    results = []
    worst = "PASS"

    for ch in channels:
        others = [c for c in channels if c is not ch]
        verdict = evaluate(ch, others, suggest_filters=not args.no_suggest)
        results.append((ch, verdict))
        order = ["PASS", "PASS_WITH_CHANGES", "FAIL", "BLOCKED"]
        if order.index(verdict.status) > order.index(worst):
            worst = verdict.status

    if args.json:
        print(
            json.dumps(
                {
                    "overall": worst,
                    "channels": {
                        ch.name: v.to_dict() for ch, v in results
                    },
                },
                indent=2,
                default=str,
            )
        )
        return 0 if worst in {"PASS", "PASS_WITH_CHANGES"} else 1

    for ch, v in results:
        print(f"\n{'=' * 72}")
        print(f"channel: {ch.name}   dye: {ch.dye.name}   ->  {_MARK[v.status]}")
        note = GRADE_NOTES.get(v.feasibility, "")
        print(f"feasibility: {v.feasibility}  {note}")
        if v.bottleneck and v.margins:
            print(
                f"bottleneck:  {v.bottleneck}  (margin {v.margins.get(v.bottleneck):.2f})"
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
                print(f"    {m:6.2f}  {code:26s} {bar}")

        if v.metrics:
            m = v.metrics
            print("\n  metrics")
            print(f"    excitation efficiency   {_fmt(m['excitation_efficiency'], pct=True)}")
            print(f"    source delivered        {_fmt(m['source_delivery'], pct=True)}")
            print(f"    spectral collection     {_fmt(m['spectral_collection'], pct=True)}")
            print(f"    geometric collection    {_fmt(m['geometric_collection'], pct=True)}")
            print(f"    total collection        {_fmt(m['total_collection'], pct=True)}")
            print(f"    excitation blocking     {_fmt(m['blocking_od'])} OD")
            print(f"    Stokes headroom         {_fmt(m['stokes_headroom_nm'], ' nm')}")
            print(f"    Rayleigh resolution     {_fmt(m['resolution_nm'], ' nm')}")
            print(f"    depth of field          {_fmt(m['depth_of_field_nm'], ' nm')}")

        if v.findings:
            print("\n  findings")
            for f in v.findings:
                print(f"    {_SEV[f.severity]} {f.code}")
                for line in _wrap(f.message, 66):
                    print(f"           {line}")
                if f.action:
                    for i, line in enumerate(_wrap(f.action, 62)):
                        print(f"        {'-> ' if i == 0 else '   '}{line}")

        if v.ablations and args.ablation:
            print("\n  element ablation (what if we take it out?)")
            for a in v.ablations:
                gain = f"{(a.signal_gain - 1) * 100:+.0f}%"
                print(f"    {a.verdict:9s} {a.element:28s} signal {gain:>6s}  {a.reason}")

        if v.suggestions:
            print("\n  suggestions")
            for s in v.suggestions:
                for i, line in enumerate(_wrap(s, 66)):
                    print(f"    {'* ' if i == 0 else '  '}{line}")

    advances = all(v.advances for _, v in results)
    print(f"\n{'=' * 72}")
    print(f"overall: {_MARK[worst]}")
    print(
        f"optical lens verdict: {'ADVANCE' if advances else 'HOLD'}"
        + ("" if advances else "  (assumed inputs present - measure, do not infer)")
    )
    print()
    return 0 if advances else 1


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def cmd_recommend(args: argparse.Namespace) -> int:
    dyes = [d.strip() for d in args.dyes.split(",")] if args.dyes else None
    lines = [l.strip() for l in args.lines.split(",")] if args.lines else None

    if args.panel:
        panel = recommend_panel(
            args.scope, lines=lines, dye_names=dyes,
            candidates_per_line=args.candidates_per_line,
        )
        if panel is None:
            print(
                "no panel: either a line has zero candidates, or the dye "
                "list can't fill every requested line with a distinct dye "
                "(default is all lines in the scope - pass --lines to pick "
                "a subset, e.g. --lines 488,640 for a 2-colour panel)"
            )
            return 1
        print(f"\nbest simultaneous panel  ({'=' * 40})")
        print(f"grade: {panel.grade}   {GRADE_NOTES.get(panel.grade, '')}")
        print(
            f"worst single-channel margin: {panel.worst_single_margin:.2f}   "
            f"worst crosstalk margin: {panel.worst_crosstalk_margin:.2f}\n"
        )
        has_camera = any(c.camera for c in panel.choices)
        cam_w = 13 if has_camera else 0
        header = f"  {'line':6s} {'dye':16s} {'filter':16s}"
        header += f" {'camera':13s}" if has_camera else ""
        header += f" {'margin':>7s} {'bright':>8s}"
        print(header)
        for c in panel.choices:
            row = f"  {c.line:6s} {c.dye:16s} {c.filter:16s}"
            row += f" {(c.camera or ''):13s}" if has_camera else ""
            row += f" {c.single_margin:7.2f} {c.brightness:8.4f}"
            print(row)
        print(
            "\nThis ranks candidates against the four spectral checks "
            "(excitation/Stokes/blocking/collection) plus pairwise crosstalk. "
            "'bright' is excitation_efficiency x spectral_collection - relative "
            "signal on this instrument, not an absolute photon rate. It does "
            "not replace `optics.cli check` — confirm objective NA and the "
            "real camera QE before booking an experiment on this."
        )
        return 0

    by_line = recommend_labels(args.scope, dyes, top=args.top)
    for line, candidates in by_line.items():
        print(f"\nline {line} nm  ({'=' * 40})")
        if not candidates:
            print("  no candidate cleared even excitation.none")
            continue
        has_camera = any(c.camera for c in candidates)
        header = f"  {'dye':16s} {'filter':16s}"
        header += f" {'camera':13s}" if has_camera else ""
        header += f" {'margin':>7s} {'bright':>8s} {'grade':12s} evidence"
        print(header)
        for c in candidates:
            row = f"  {c.dye:16s} {c.filter:16s}"
            row += f" {(c.camera or ''):13s}" if has_camera else ""
            row += f" {c.margin:7.2f} {c.brightness:8.4f} {c.grade:12s} {c.evidence}"
            print(row)
            if c.notes and args.verbose:
                for line_txt in _wrap(c.notes[0], 70):
                    print(f"      {line_txt}")

    print(
        "\nevidence is 'assumed' unless every dye/filter curve involved was "
        "loaded from data/spectra/ rather than approximated from peak+FWHM. "
        "Use this to decide what to measure next, not as a final verdict."
    )
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    dyes = [d.strip() for d in args.dyes.split(",")] if args.dyes else None
    lines = [l.strip() for l in args.lines.split(",")] if args.lines else None

    options = compare_sources(
        args.scopes, lines=lines, dye_names=dyes,
        candidates_per_line=args.candidates_per_line,
    )

    print(f"\n{'=' * 72}")
    print("light-source options — ranked, not decided. Pick one.")
    print(f"{'=' * 72}")
    for opt in options:
        print(f"\n{opt.scope_name}  ({opt.scope_path})")
        if opt.error:
            print(f"  ERROR: {opt.error}")
            continue
        if opt.panel is None:
            print(
                "  no panel — this source can't put a distinct dye on every "
                "requested line (or a line has zero candidates)"
            )
            continue
        p = opt.panel
        print(
            f"  grade: {p.grade}   worst single margin: {p.worst_single_margin:.2f}"
            f"   crosstalk margin: {p.worst_crosstalk_margin:.2f}"
        )
        for c in p.choices:
            cam = f" -> {c.camera}" if c.camera else ""
            print(
                f"    {c.line:>5s} nm  {c.dye:16s} {c.filter:16s}"
                f"{cam:16s} bright={c.brightness:.4f}"
            )

    print(
        f"\n{'=' * 72}\n"
        "Sorted best-first by: has a panel > clears every gate > total "
        "brightness. This does not know which source suits your sample "
        "(sectioning need, photostability, what else is booked on it) - "
        "that judgment is yours. Pick a scope and re-run with "
        "`optics.cli recommend <scope> --panel` for the full detail."
    )
    return 0


def cmd_dyes(args: argparse.Namespace) -> int:
    seen = set()
    print(f"{'name':22s} {'abs':>6s} {'em':>6s} {'Stokes':>7s} {'eps*QY':>10s}  verified")
    print("-" * 68)
    for dye in fluorophores().values():
        if dye.name in seen:
            continue
        seen.add(dye.name)
        b = dye.brightness
        print(
            f"{dye.name:22s} {dye.absorption.peak_nm():6.0f} "
            f"{dye.emission.peak_nm():6.0f} {dye.stokes_shift_nm:7.0f} "
            f"{(f'{b / 1000:.0f}k' if b else '-'):>10s}  {dye.verified}"
        )
    return 0


def cmd_filters(args: argparse.Namespace) -> int:
    print(f"{'name':28s} {'kind':12s} band")
    print("-" * 68)
    for name, spec in filters().items():
        if spec.get("center_nm"):
            band = f"{spec['center_nm']}/{spec.get('fwhm_nm', '?')}"
        elif spec.get("bands"):
            band = " + ".join(f"{b[0]}/{b[1]}" for b in spec["bands"])
        elif spec.get("edge_nm"):
            band = f"edge {spec['edge_nm']}"
        elif spec.get("od") is not None:
            band = f"OD {spec['od']}"
        else:
            band = "(unspecified)"
        print(f"{name:28s} {spec.get('kind', '?'):12s} {band}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="optics", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="evaluate a channel configuration")
    c.add_argument("config", help="YAML file describing one or more channels")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-suggest", action="store_true", help="skip filter suggestions")
    c.add_argument(
        "--ablation",
        action="store_true",
        default=True,
        help="show the per-element removal analysis (default on)",
    )
    c.set_defaults(func=cmd_check)

    r = sub.add_parser(
        "recommend", help="rank dye x line x filter labeling options for a scope"
    )
    r.add_argument("scope", help="YAML system profile, e.g. config/scopes/current-laser.yaml")
    r.add_argument("--dyes", help="comma-separated dye names (default: whole registry)")
    r.add_argument(
        "--lines",
        help="comma-separated excitation lines for --panel (default: every line in "
        "the scope), e.g. --lines 488,640 for a 2-colour simultaneous panel",
    )
    r.add_argument("--top", type=int, default=5, help="candidates to show per line")
    r.add_argument("--panel", action="store_true", help="recommend one simultaneous panel")
    r.add_argument(
        "--candidates-per-line",
        type=int,
        default=4,
        help="panel search width per line (only with --panel)",
    )
    r.add_argument("--verbose", action="store_true", help="show the limiting check's message")
    r.set_defaults(func=cmd_recommend)

    s = sub.add_parser(
        "sources",
        help="compare the best panel across several light sources (one scope each)",
    )
    s.add_argument(
        "scopes", nargs="+",
        help="scope YAML files to compare, e.g. config/scopes/current-laser.yaml "
        "config/scopes/current-spectra.yaml config/scopes/current-aura.yaml",
    )
    s.add_argument("--dyes", help="comma-separated dye names (default: whole registry)")
    s.add_argument(
        "--lines",
        help="comma-separated excitation lines, matched by name against each scope "
        "(e.g. --lines 488,640) — required to get a panel when --dyes names fewer "
        "dyes than the scope has lines",
    )
    s.add_argument("--candidates-per-line", type=int, default=4)
    s.set_defaults(func=cmd_sources)

    sub.add_parser("dyes", help="list the fluorophore registry").set_defaults(
        func=cmd_dyes
    )
    sub.add_parser("filters", help="list the filter registry").set_defaults(
        func=cmd_filters
    )

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
