"""Quick command-line verification of the compute-resource lens.

    # one camera
    python -m compute.cli check --width 1608 --height 1608 --fps 60 \\
        --disk-bandwidth-mb-s 500 --circular-buffer-frames 552 \\
        --acquisition-duration-s 60 --free-disk-gb 500

    # both Kinetix cameras at once, 8-bit Speed mode, RAM-capture path
    python -m compute.cli check \\
        --stream red:2400x2400@200:8 --stream blue:2400x2400@200:8 \\
        --disk-bandwidth-mb-s 206.8 --circular-buffer-frames 552 \\
        --acquisition-duration-s 60 --free-disk-gb 2559 --ram-capture

    # post-hoc: did this acquisition drop frames?
    python -m compute.cli drops "D:\\data\\run_1\\run_1_metadata.txt"
    python -m compute.cli scan "D:\\data" --contaminated-only

``check`` runs the committee-lens gate (compute.gate.evaluate): data rate
(G12a-c), circular buffer / capacity / real-time CPU / RAM capture
(G13a-d). ``drops`` and ``scan`` run the post-hoc half (compute.drops),
which needs no hardware and works on the existing archive.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

from .drops import DropReport, NotEnoughFrames, analyse_file, scan_tree
from .gate import evaluate
from .setup import AcquisitionResourceSetup, Stream

STREAM_SPEC_RE = re.compile(
    r"^(?P<label>[^:]+):(?P<w>\d+)x(?P<h>\d+)@(?P<fps>\d+(?:\.\d+)?)"
    r"(?::(?P<bits>\d+))?$"
)


def parse_stream(spec: str, *, fps_source: str, container_confirmed: bool) -> Stream:
    """``label:WIDTHxHEIGHT@FPS[:BITS]`` -- e.g. ``red:2400x2400@200:8``."""
    m = STREAM_SPEC_RE.match(spec)
    if not m:
        raise argparse.ArgumentTypeError(
            f"bad --stream {spec!r}; expected label:WIDTHxHEIGHT@FPS[:BITS], "
            "e.g. red:2400x2400@200:8"
        )
    return Stream(
        label=m.group("label"),
        width_px=int(m.group("w")),
        height_px=int(m.group("h")),
        fps=float(m.group("fps")),
        bit_depth=int(m.group("bits") or 16),
        container_confirmed=container_confirmed,
        fps_source=fps_source,
    )


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:
    if args.stream:
        streams = [
            parse_stream(
                s,
                fps_source=args.fps_source,
                container_confirmed=args.container_confirmed,
            )
            for s in args.stream
        ]
    elif args.width and args.height and args.fps:
        streams = [
            Stream(
                label="camera",
                width_px=args.width,
                height_px=args.height,
                fps=args.fps,
                bit_depth=args.bit_depth,
                container_confirmed=args.container_confirmed,
                fps_source=args.fps_source,
            )
        ]
    else:
        print(
            "give either --stream (repeatable) or --width/--height/--fps",
            file=sys.stderr,
        )
        return 2

    setup = AcquisitionResourceSetup(
        streams=streams,
        disk_bandwidth_mb_s=args.disk_bandwidth_mb_s,
        disk_bandwidth_path_confirmed=args.disk_bandwidth_path_confirmed,
        circular_buffer_frames=args.circular_buffer_frames,
        ram_budget_mb=args.ram_budget_mb,
        acquisition_duration_s=args.acquisition_duration_s,
        free_disk_gb=args.free_disk_gb,
        cpu_per_frame_ms=args.cpu_per_frame_ms,
        realtime_processing=args.realtime_processing,
        detector_max_fps=args.detector_max_fps,
        ram_capture=args.ram_capture,
        ram_capture_budget_mb=args.ram_capture_budget_mb,
    )
    v = evaluate(setup)

    if args.json:
        print(json.dumps(v.to_dict(), indent=2))
        return 0 if v.advances or v.status == "PASS" else 1

    label = " + ".join(
        f"{s.label} {s.width_px}x{s.height_px}@{s.fps:g} ({s.bit_depth}bit)"
        for s in streams
    )
    path_note = " [RAM capture]" if setup.ram_capture else ""
    print(f"\n{'=' * 72}")
    print(f"{label}{path_note}   ->  {v.status}")
    print(
        f"feasibility: {v.feasibility}   evidence: {v.evidence}   "
        f"confidence: {v.confidence}   advances: {'YES' if v.advances else 'NO'}"
    )
    print(f"total data rate: {setup.data_rate_bytes_s() / 1e6:.0f} MB/s")
    if v.assumed_inputs:
        print("assumed:")
        for item in v.assumed_inputs:
            print(f"  - {item}")
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


# --------------------------------------------------------------------------
# drops / scan
# --------------------------------------------------------------------------


def print_report(r: DropReport, *, max_gaps: int) -> None:
    print(f"\n{'=' * 72}")
    print(f"{r.source}")
    verdict = "CONTAMINATED" if r.contaminated else "CLEAN"
    if r.truncated:
        verdict += " but TRUNCATED"
    print(
        f"{r.n_frames} frames in {r.n_series} series over {r.span_s:.1f} s   ->  "
        f"{verdict}"
    )
    print("=" * 72)
    print(
        f"\n  cadence      {r.median_interval_ms:.2f} ms median "
        f"({r.cadence_fps:.1f} fps), {r.mean_interval_ms:.2f} ms mean"
    )
    print(f"  delivered    {r.throughput_fps:.1f} fps over the whole span")
    print(
        f"  jitter       MAD {r.mad_interval_ms:.2f} ms "
        f"({r.jitter_fraction * 100:.1f}% of cadence)"
        + ("  [quantization-limited, not meaningful]" if r.timestamps_quantized else "")
    )
    if r.timestamps_quantized and r.throughput_fps > r.cadence_fps:
        print(
            "               median and mean disagree, and delivered exceeds "
            "cadence: the true interval falls between two timestamp ticks. "
            "Trust the mean here, not the median."
        )
    if r.completion_fraction is not None:
        state = "TRUNCATED" if r.truncated else "complete"
        print(
            f"  planned      {r.planned_frames} timepoints, got "
            f"{r.frames_per_series:.0f} "
            f"({r.completion_fraction * 100:.1f}%) -- {state}"
        )
    if r.requested_vs_achieved is not None:
        print(
            f"  requested    {r.requested_interval_ms:.2f} ms  -> delivered is "
            f"{r.requested_vs_achieved:.2f}x slower  (docs/06 §C4 saw 3.0x)"
        )
    print(
        f"  drops        {r.dropped_frames} frames in {r.n_gaps} gaps "
        f"({r.dropped_fraction * 100:.2f}% of the intended series), "
        f"largest {r.largest_gap_frames}"
    )
    if r.frames_without_timestamp:
        print(f"  no timestamp {r.frames_without_timestamp} FrameKeys carried none")
    if r.short_series:
        print(f"  skipped      {r.short_series} series too short to analyse")

    if r.gaps:
        print(f"\n  gaps (largest first, showing up to {max_gaps})")
        for g in r.gaps[:max_gaps]:
            print(
                f"    after frame {g.after_frame:<7d} c{g.channel} z{g.slice}  "
                f"{g.interval_ms:8.1f} ms  ~{g.missing_frames} missing"
            )
        if len(r.gaps) > max_gaps:
            print(f"    ... {len(r.gaps) - max_gaps} more")

    if r.contaminated:
        print(
            "\n  -> Lag times in this acquisition are not uniform. Any MSD or "
            "correlation computed on a fixed frame interval is wrong by the "
            "amount above (docs/06 §C5)."
        )
    print()


def cmd_drops(args: argparse.Namespace) -> int:
    try:
        report = analyse_file(args.path)
    except NotEnoughFrames as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"{args.path}: unreadable: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report, max_gaps=args.max_gaps)
    return 1 if report.contaminated else 0


def cmd_scan(args: argparse.Namespace) -> int:
    total = clean = contaminated = truncated = skipped = 0
    skip_reasons: Counter[str] = Counter()
    rows: list[dict] = []

    for path, report, error in scan_tree(args.root, args.glob):
        total += 1
        if report is None:
            skipped += 1
            # Bucket by shape, not by the exact count in the message, so the
            # tally stays readable across a few thousand acquisitions.
            skip_reasons[re.sub(r"\d+", "N", error or "unknown")] += 1
            if not args.contaminated_only:
                print(f"  [skip] {path}: {error}")
            continue
        if report.contaminated:
            contaminated += 1
        else:
            clean += 1
        if report.truncated:
            truncated += 1

        # Truncation is a separate failure from drops, but --contaminated-only
        # is "show me what needs looking at", and a run that stopped at 6% of
        # its planned frames needs looking at.
        flagged = report.contaminated or report.truncated
        if args.json:
            rows.append(report.to_dict())
        elif flagged or not args.contaminated_only:
            mark = (
                "[DROP]"
                if report.contaminated
                else ("[TRUNC]" if report.truncated else "[ ok ]")
            )
            print(f"  {mark:7s} {report.summary_line(args.root)}")

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(
        f"\n{total} acquisitions: {clean} with clean lag times, "
        f"{contaminated} contaminated, {truncated} truncated, {skipped} skipped"
    )
    # A skipped file is not a clean one. Say why they went, or the headline
    # counts read as coverage they do not have.
    for reason, n in skip_reasons.most_common():
        print(f"  {n:6d} skipped: {reason}")
    if contaminated:
        print(
            "Contaminated sessions have non-uniform lag times -- re-check any "
            "analysis that assumed a fixed frame interval (docs/06 §C5)."
        )
    if truncated:
        print(
            "Truncated sessions stopped before their planned frame count. "
            "Their lag times may be fine; their statistics are not what was "
            "planned."
        )
    return 0


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="compute", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run the committee-lens gate (G12a-c, G13a-d)")
    c.add_argument(
        "--stream", action="append", default=[],
        help="label:WIDTHxHEIGHT@FPS[:BITS], repeatable -- one per camera",
    )
    c.add_argument("--width", type=int, default=None, help="single-stream frame width, px")
    c.add_argument("--height", type=int, default=None, help="single-stream frame height (rows), px")
    c.add_argument("--fps", type=float, default=None, help="single-stream frame rate")
    c.add_argument(
        "--bit-depth", type=int, default=16,
        help="single-stream ADC bit depth (data/detectors.yaml modes); default 16",
    )
    c.add_argument(
        "--fps-source", choices=("measured", "requested"), default="requested",
        help="is the frame rate an achieved rate or a requested one (G12b)",
    )
    c.add_argument(
        "--container-confirmed", action="store_true",
        help="MM's bytes/pixel for this bit depth has been confirmed on the real adapter (G12c)",
    )
    c.add_argument(
        "--detector-max-fps", type=float, default=None,
        help="lens 2's realizable frame rate (detection.timing.max_fps), for the G12b cross-check",
    )
    c.add_argument(
        "--disk-bandwidth-mb-s", type=float, default=None,
        help="measured sustained disk write bandwidth (calibration.disk_bandwidth)",
    )
    c.add_argument(
        "--disk-bandwidth-path-confirmed", action="store_true",
        help="that bandwidth was measured against the folder MM actually saves into",
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
    c.add_argument(
        "--ram-capture", action="store_true",
        help="hold the burst in RAM and flush afterwards (G13d instead of G12a)",
    )
    c.add_argument(
        "--ram-capture-budget-mb", type=float, default=None,
        help="RAM the capture may use; defaults to the authorized ceiling in compute.checks.LIMITS",
    )
    c.add_argument("--json", action="store_true", help="emit the Verdict as JSON")
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("drops", help="post-hoc frame-drop detection on one acquisition")
    d.add_argument("path", help="Micro-Manager *_metadata.txt")
    d.add_argument("--max-gaps", type=int, default=10, help="how many gaps to list")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_drops)

    s = sub.add_parser("scan", help="sweep a directory tree of acquisitions for drops")
    s.add_argument("root", help="directory to walk")
    s.add_argument("--glob", default="*metadata.txt")
    s.add_argument(
        "--contaminated-only", action="store_true",
        help="list only the sessions with drops or an irregular cadence",
    )
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
