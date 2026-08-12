"""Quick command-line verification of the compute-resource-lens gate.

    python -m compute.cli check --width 1608 --height 1608 --fps 60 \\
        --disk-bandwidth-mb-s 500 --circular-buffer-frames 552 \\
        --acquisition-duration-s 60 --free-disk-gb 500

``check`` runs the committee-lens gate (compute.gate.evaluate): data rate
(G12), circular buffer / capacity / real-time CPU (G13).
"""

from __future__ import annotations

import argparse
import sys

from .gate import evaluate
from .setup import AcquisitionResourceSetup


def cmd_check(args: argparse.Namespace) -> int:
    setup = AcquisitionResourceSetup(
        frame_width_px=args.width,
        frame_height_px=args.height,
        fps=args.fps,
        disk_bandwidth_mb_s=args.disk_bandwidth_mb_s,
        circular_buffer_frames=args.circular_buffer_frames,
        ram_budget_mb=args.ram_budget_mb,
        acquisition_duration_s=args.acquisition_duration_s,
        free_disk_gb=args.free_disk_gb,
        cpu_per_frame_ms=args.cpu_per_frame_ms,
        realtime_processing=args.realtime_processing,
    )
    v = evaluate(setup)

    print(f"\n{'=' * 72}")
    print(
        f"{args.width}x{args.height} @ {args.fps:.0f} fps   ->  {v.status}"
    )
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   advances: {'YES' if v.advances else 'NO'}"
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
    p = argparse.ArgumentParser(prog="compute", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G12-G13)")
    c.add_argument("--width", type=int, required=True, help="frame width, px")
    c.add_argument("--height", type=int, required=True, help="frame height (rows), px")
    c.add_argument("--fps", type=float, required=True, help="achieved (not requested) frame rate")
    c.add_argument(
        "--disk-bandwidth-mb-s", type=float, default=None,
        help="measured sustained disk write bandwidth (calibration.disk_bandwidth)",
    )
    c.add_argument("--circular-buffer-frames", type=int, default=None, help="MM CircularBufferFrameCount")
    c.add_argument(
        "--ram-budget-mb", type=float, default=None,
        help="available RAM to derive a buffer frame count from, if CircularBufferFrameCount is unknown",
    )
    c.add_argument("--acquisition-duration-s", type=float, default=None)
    c.add_argument("--free-disk-gb", type=float, default=None)
    c.add_argument("--cpu-per-frame-ms", type=float, default=None)
    c.add_argument("--realtime-processing", action="store_true")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
