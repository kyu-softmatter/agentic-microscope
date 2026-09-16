"""Command-line front end for Phase-0 hardware calibration measurements.

    python -m calibration.cli disk-bandwidth D:\\data\\_bench --size-gb 4
    python -m calibration.cli intermediate-mag "C:\\...\\single_cam_red_noDMD.cfg"
    python -m calibration.cli camera-readout "C:\\...\\DMD_dualcam.cfg"
    python -m calibration.cli camera-probe "C:\\...\\DMD_dualcam.cfg" --cameras Camera-1,Camera-2
    python -m calibration.cli ram-burst "C:\\...\\DMD_dualcam.cfg" --camera Camera-1 \\
        --n-frames 200 --out D:\\data\\_bench\\burst.npy

The last three need pymmcore-plus and a working Micro-Manager device-adapter
install (``mmcore install``, or the lab's own MM2 setup) -- run them once
this repo is reconnected to the microscope PC, not on the offline work PC.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .disk_bandwidth import measure_write_bandwidth


def cmd_disk_bandwidth(args: argparse.Namespace) -> int:
    result = measure_write_bandwidth(
        Path(args.directory), total_bytes=int(args.size_gb * 1e9)
    )
    print(
        f"wrote {result.bytes_written / 1e9:.2f} GB to {result.directory} "
        f"in {result.seconds:.1f} s"
    )
    print(f"sustained write bandwidth: {result.mb_per_s:.1f} MB/s")
    print(
        "\nrecord this in kb/systems/current.md (e.g. a `calibrations:` "
        "block) -- G12 needs it as disk_bandwidth_mb_s to gate camera data "
        "rate at 0.7x this value (docs/04-decision-engine.md §9)."
    )
    return 0


def cmd_intermediate_mag(args: argparse.Namespace) -> int:
    """Read the intermediate-magnification turret and emit the .cfg lines for it.

    The one reading this repository cannot take from the offline PC, and the
    one thing standing between ``data/pixel_size.yaml`` and Micro-Manager
    answering ``getPixelSizeUm()`` for itself. Run it at the microscope, paste
    what it prints.
    """
    from . import mm_live  # deferred: only this subcommand needs pymmcore-plus

    from optics.components import recorded_pixel_um

    core = mm_live.connect(args.config)
    device = args.device

    try:
        positions = mm_live.state_device_positions(core, device)
    except Exception as exc:
        print(f"could not read {device!r}: {exc}")
        print("\nis it loaded in this config? `Device,<label>,NikonTi2,...`")
        return 1

    print(f"{device}: {len(positions)} positions")
    for state, label in positions:
        shown = repr(label) if label else "(unnamed)"
        print(f"  state {state} -> {shown}")

    unnamed = [s for s, lab in positions if not lab]
    print(
        "\nWhich state is 1x and which is 1.5x is a fact about the stand, not "
        "about this output. Turn the turret by hand, confirm, then name them:"
    )
    for state, label in positions:
        suggested = label or ("1x" if state == 0 else "1.5x")
        print(f"  Label,{device},{state},{suggested}")
    if unnamed:
        print(
            f"\n  ^ {len(unnamed)} of those are guesses at the ordering. "
            "Confirm before pasting."
        )

    # The pixel-size block, one preset per objective x intermediate.
    print("\n# PixelSize settings   -- paste under the .cfg's own header")
    nosepiece = args.nosepiece
    for state, label in positions:
        factor_label = label or ("1x" if state == 0 else "1.5x")
        try:
            factor = float(factor_label.rstrip("xX"))
        except ValueError:
            print(f"# {factor_label!r} is not a magnification -- skipped")
            continue
        for obj_state, obj_label in mm_live.state_device_positions(core, nosepiece):
            from hardware.microscope import _objective_mag_from_label

            mag = _objective_mag_from_label(obj_label)
            if mag is None:
                continue
            hit = recorded_pixel_um(mag, factor)
            if hit is None:
                print(f"# no recorded pixel size for {mag:g}x x {factor:g}x")
                continue
            um, evidence = hit
            preset = f"{mag:g}x-{factor_label}"
            print(f"ConfigPixelSize,{preset},{nosepiece},Label,{obj_label}")
            print(f"ConfigPixelSize,{preset},{device},Label,{factor_label}")
            print(f"PixelSize_um,{preset},{um}   # {evidence}")
    print(
        "\nA preset matches only when EVERY property line in it matches, so at "
        "an unlisted combination MM reports 0.0 rather than a wrong number."
    )
    return 0


def cmd_camera_readout(args: argparse.Namespace) -> int:
    from . import mm_live  # deferred: only this subcommand needs pymmcore-plus

    core = mm_live.connect(args.config)
    cameras = [args.camera] if args.camera else mm_live.list_cameras(core)
    if not cameras:
        print("no camera devices found in this config")
        return 1

    for cam in cameras:
        height = mm_live.roi_height(core, cam)
        print(f"\n{cam}: ROI height = {height} rows")
        candidates = mm_live.readout_time_candidates(core, cam)
        if not candidates:
            print("  no property name looked like a readout time -- dumping all properties:")
            for name in core.getDevicePropertyNames(cam):
                print(f"    {name!r} = {core.getProperty(cam, name)!r}")
            continue
        for c in candidates:
            print(f"  candidate property {c.name!r} = {c.raw_value!r}")
            if args.unit:
                raw = float(c.raw_value)
                total_ns = {"ns": raw, "us": raw * 1e3, "ms": raw * 1e6}[args.unit]
                print(f"    if this is in {args.unit}: row time = {total_ns / height:.1f} ns/row")
            else:
                print(
                    "    pass --unit {ns,us,ms} once you've confirmed the "
                    "adapter's units (its manual or property description) "
                    "to compute row time -- do not assume a unit."
                )
    return 0


def cmd_camera_probe(args: argparse.Namespace) -> int:
    from . import mm_live  # deferred: only this subcommand needs pymmcore-plus

    core = mm_live.connect(args.config)
    cameras = args.cameras.split(",")
    print(
        f"probing {cameras} every {args.interval:.1f}s -- toggle EM1/EM2 in "
        "NIS-Elements between prints and watch which camera's mean intensity "
        "moves. Ctrl+C to stop."
    )
    try:
        while True:
            stamp = time.strftime("%H:%M:%S")
            readings = [
                f"{cam}={mm_live.snap_mean_intensity(core, cam):8.1f}" for cam in cameras
            ]
            print(f"  {stamp}  " + "  ".join(readings))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


def cmd_ram_burst(args: argparse.Namespace) -> int:
    from . import mm_live, ram_capture  # deferred: only this subcommand needs pymmcore-plus

    core = mm_live.connect(args.config)
    result = ram_capture.capture_burst_to_ram(core, args.camera, args.n_frames)
    print(
        f"captured {result.n_captured}/{result.n_requested} frames "
        f"({result.dropped} dropped) in {result.elapsed_s:.2f} s "
        f"-- achieved {result.achieved_fps:.1f} fps, shape {result.frames.shape}"
    )
    if args.out:
        flushed = ram_capture.flush_to_disk(result.frames, args.out)
        print(
            f"flushed {flushed.bytes_written / 1e6:.1f} MB to {flushed.path} "
            f"in {flushed.elapsed_s:.1f} s ({flushed.mb_per_s:.1f} MB/s)"
        )
    return 0


def cmd_drag_prepare(args: argparse.Namespace) -> int:
    """The step between what is on disk and what `drag-slope` reads.

    The position files are two columns `x y` in pixels with no time column, and
    the speed is in the filename. So `t_s` has to be constructed, and the period
    it is constructed from is the one number `analysis/matlab/README.md` says is
    hardcoded at 0.02 s and never read from metadata. This command therefore
    refuses to invent it and records where it came from.
    """
    from .drag_slope import HARDCODED_FRAME_PERIOD_MS, prepare_rows

    paths = [Path(p) for p in args.positions]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print(f"no such file(s): {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 2

    if not args.frame_period_source.strip():
        print(
            "--frame-period-source is empty. Refusing: a constructed time axis "
            "whose provenance is blank cannot be told from one measured, and "
            "nothing downstream can recover it",
            file=sys.stderr,
        )
        return 1

    if args.frame_period_ms == HARDCODED_FRAME_PERIOD_MS:
        print(
            f"⚠ {HARDCODED_FRAME_PERIOD_MS} ms is exactly the value hardcoded in "
            "every MATLAB file and never read from metadata "
            "(analysis/matlab/README.md). That is not an error -- the standing "
            "exposure is 20.0 ms -- but a requested rate is not evidence (G12b). "
            f"Recorded source: {args.frame_period_source!r}",
            file=sys.stderr,
        )

    try:
        rows = prepare_rows(paths, frame_period_ms=args.frame_period_ms, rung=args.rung)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    header = [
        "# Prepared by `python -m calibration.cli drag-prepare` from two-column",
        "# `x y` position files. x stays in PIXELS -- drag-slope needs",
        "# --pixel-size-um, which it refuses to default.",
        f"# frame_period_ms: {args.frame_period_ms}",
        f"# frame_period_source: {args.frame_period_source}",
        "# t_s is CONSTRUCTED from that period, not measured per frame. If a",
        "# timestamp column exists for this acquisition, use it instead: the",
        "# achieved period equals the exposure on this camera and a requested",
        "# rate is not evidence (G12b).",
        "# source files, in segment order:",
    ] + [f"#   {i}: {p}" for i, p in enumerate(paths)]

    text = "\n".join(header + rows) + "\n"
    if args.out:
        out = Path(args.out)
        if out.exists():
            print(f"{out} exists -- refusing to overwrite", file=sys.stderr)
            return 1
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} -- {len(rows) - 1} rows from {len(paths)} file(s)")
    else:
        print(text)
    return 0


def cmd_drag_slope(args: argparse.Namespace) -> int:
    """P7, run where the data already is.

    numpy only: no Micro-Manager, no instrument, no edit to the analysis PC's
    own code. What returns to version control is the `kb/calibrations/` entry
    with the input's hash, not a copy of the raw positions.
    """
    import platform
    from datetime import date as _date

    from .drag_slope import as_calibration_entry, fit_file, summarise

    path = Path(args.positions)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2

    try:
        fits = fit_file(
            path,
            settle_s=args.settle_s,
            pixel_size_um=args.pixel_size_um,
            temperature_c=args.temperature_c,
        )
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    print(summarise(fits))

    entry = as_calibration_entry(
        path,
        fits,
        settle_s=args.settle_s,
        pixel_size_um=args.pixel_size_um,
        temperature_c=args.temperature_c,
        date=_date.today().isoformat(),
        machine=f"{platform.node()} ({platform.system()})",
    )

    import yaml

    text = "# Written by `python -m calibration.cli drag-slope`. Review before committing:\n" \
           "# `verified: false` until a person has read it, and the entry may be a gate\n" \
           "# threshold only because it was measured on this instrument.\n" \
           + yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=88)

    if args.out:
        out = Path(args.out)
        if out.exists():
            print(f"{out} exists -- refusing to overwrite", file=sys.stderr)
            return 1
        out.write_text(text, encoding="utf-8")
        print(f"\nwrote {out}")
    else:
        print("\n" + text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="calibration", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser(
        "disk-bandwidth", help="measure sustained sequential write bandwidth (G12)"
    )
    d.add_argument("directory", help="folder on the target disk to write the test file into")
    d.add_argument(
        "--size-gb", type=float, default=2.0,
        help="test file size in GB (default 2 -- large enough that OS cache can't absorb it)",
    )
    d.set_defaults(func=cmd_disk_bandwidth)

    i = sub.add_parser(
        "intermediate-mag",
        help="read the intermediate-magnification turret and emit its .cfg lines",
    )
    i.add_argument("config", help="Micro-Manager .cfg path (on the microscope PC)")
    i.add_argument(
        "--device", default="IntermediateMagnification",
        help="state-device label of the magnification changer",
    )
    i.add_argument(
        "--nosepiece", default="Nosepiece",
        help="state-device label of the objective turret",
    )
    i.set_defaults(func=cmd_intermediate_mag)

    r = sub.add_parser(
        "camera-readout",
        help="find candidate readout-time properties and compute row time",
    )
    r.add_argument("config", help="Micro-Manager .cfg path (on the microscope PC)")
    r.add_argument("--camera", help="camera device label (default: every camera in the config)")
    r.add_argument(
        "--unit", choices=["ns", "us", "ms"],
        help="unit of the readout-time property, once confirmed against the adapter's docs",
    )
    r.set_defaults(func=cmd_camera_readout)

    e = sub.add_parser(
        "camera-probe",
        help="live per-camera mean intensity, to find which camera EM1/EM2 feed",
    )
    e.add_argument("config", help="Micro-Manager .cfg path (on the microscope PC)")
    e.add_argument(
        "--cameras", required=True,
        help="comma-separated camera device labels, e.g. Camera-1,Camera-2",
    )
    e.add_argument("--interval", type=float, default=2.0, help="seconds between snaps")
    e.set_defaults(func=cmd_camera_probe)

    b = sub.add_parser(
        "ram-burst",
        help="capture a burst into RAM (no disk write), then optionally flush -- single camera only",
    )
    b.add_argument("config", help="Micro-Manager .cfg path (on the microscope PC)")
    b.add_argument("--camera", required=True, help="camera device label")
    b.add_argument("--n-frames", type=int, required=True, help="frames to capture into RAM")
    b.add_argument("--out", help="if given, flush the captured burst to this .npy path after capture")
    b.set_defaults(func=cmd_ram_burst)

    q = sub.add_parser(
        "drag-prepare",
        help="two-column x y position files -> the drag-slope input contract (P7 step 2)",
    )
    q.add_argument("positions", nargs="+", help="position files, in the order they become segments")
    q.add_argument(
        "--frame-period-ms", type=float, required=True,
        help="the ACHIEVED period, which equals the exposure on this camera. Required: there is no time column in these files and this is the number analysis/matlab/README.md says is hardcoded at 20 ms and never read from metadata",
    )
    q.add_argument(
        "--frame-period-source", required=True,
        help="where that period came from -- a timestamp column, a run report's achieved rate, or the exposure setting. Recorded in the output, because nothing downstream can recover it",
    )
    q.add_argument("--rung", default="0", help="height id, if the files are one rung of a ladder")
    q.add_argument("--out", help="write here instead of printing")
    q.set_defaults(func=cmd_drag_prepare)

    s = sub.add_parser(
        "drag-slope",
        help="fit x_eq(v) on tracked positions and report the per-rung scatter on gamma (P7)",
    )
    s.add_argument("positions", help="tracked-positions file -- see calibration/drag_slope.py for the contract")
    s.add_argument(
        "--settle-s", type=float, required=True,
        help="seconds to discard after each segment starts; the plan uses 3.5/(2*pi*f_c), 0.056 at a = 4.95 um. Required, because it is a physical number",
    )
    s.add_argument(
        "--pixel-size-um", type=float,
        help="needed only when the file gives x_px. Never defaulted",
    )
    s.add_argument(
        "--temperature-c", type=float,
        help="measured sample temperature. Without it the equipartition cross-check is BLOCKED rather than computed from an assumed 20 C (plan P3)",
    )
    s.add_argument("--out", help="write the kb/calibrations/ entry here as YAML instead of printing it")
    s.set_defaults(func=cmd_drag_slope)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
