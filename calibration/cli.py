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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
