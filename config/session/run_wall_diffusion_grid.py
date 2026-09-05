"""Several fields of wall-diffusion, on a non-overlapping grid, one folder each.

    python config/session/run_wall_diffusion_grid.py --cfg CFG \
        --out-dir "D:\\Kyu Hwan Choi\\agentic_microscope\\2026-09-04" \
        --prefix wall-diffusion --start 4 --seconds 30 \
        --temperature-c 20.0 --trap-emission-off

WHY A GRID OF SHORT BLOCKS RATHER THAN ONE LONG ONE
---------------------------------------------------
Lens 6's ruling on this measurement is that **the independent unit is the
field, not the trajectory**: fit D per field and take the scatter across
fields as the error bar, because that absorbs the shared drift reference, the
per-field temperature and the per-field bead population, none of which any
analytic formula in this repository models. So more fields beats longer
fields. At 30 s and 30 fps a field yields ~900 frames x ~39 usable beads,
which is ~17,000 displacement samples at the shortest fitted lag -- far past
what the fit needs. Nine fields put ~25% uncertainty on the standard error
itself; three would put 71% on it and the error bar would mean nothing.

WHY THE SPACING IS WHAT IT IS
-----------------------------
The field is 2400 px x 0.10833 um = 260 um. Fields must not overlap or they
share beads and stop being independent samples. A 3x3 grid at **300 um**
spacing is the smallest grid that clears 260 um on every pair, diagonals
included, and it fits inside the +-300 um of stage travel authorized by the
operator (KH, 2026-09-04). At +-200 um only 5 positions are clean.

WHY FULL FRAME AND NOT A CROP
-----------------------------
Cropping does not reduce the bead *density*, only the number of candidates,
and the isolation cut is not optional: it is set by the localization geometry.
A bead's disk is ~27 px in radius at the working threshold, so a clean
centroid window needs the nearest neighbour beyond about twice that. Measured
2026-09-04 on this sample: at 500 px, 1 of 8 interior beads passes
nn >= 12 um; at 2400 px, 39 of 266 do. Same density, 25x the area, 39x the
yield.

THE PRE-CHECK, AND WHY IT EARNS ITS KEEP
----------------------------------------
Bead density is not uniform across the coverslip, and a 30 s full-frame block
costs 10.4 GB. So each field is snapped once and scored *before* it is
committed: count the interior beads whose nearest neighbour clears the
isolation cut, and skip the field if too few. The skip and its count go into
the record either way, so a thin region becomes data about the sample rather
than a silently missing field.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from calibration.timestamped_capture import capture_timestamped  # noqa: E402
from config.session.run_wall_diffusion import (  # noqa: E402
    disable_post_processing,
    preflight,
)

#: Hard travel limit from the origin, um. The operator authorized +-300
#: (KH 2026-09-04); this carries a little margin for rounding and refuses
#: anything beyond. It is a refusal, not a clamp -- silently moving somewhere
#: other than where the caller asked is worse than not moving at all.
MAX_OFFSET_UM = 320.0

#: 3x3 grid in units of --step-um. Centre first, so the field the operator has
#: already inspected is acquired while the enclosure is least disturbed.
GRID = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1)]

#: Dark offset in ADU, measured 2026-09-04 from a dark frame at this exposure.
#: Only used to background-subtract the pre-check snap, so a few ADU either way
#: changes no decision -- but it is a measurement rather than a datasheet value,
#: which is the reason it is named here instead of being a literal in the code.
OFFSET_ADU = 102.0


def detect(f, px_um, edge_px=32, mask_r=45, thr_frac=0.30, max_n=800):
    """Interior bead centres, and each one's nearest-neighbour distance in um.

    Brightest-pixel-then-mask rather than a circle fit, because this only has
    to *count* candidates. The nearest-neighbour distance is measured against
    every detection including the ones outside the interior, since a neighbour
    just off the edge contaminates a centroid exactly as much as one inside.
    """
    a = f.copy()
    bg = np.percentile(a, 20)
    thr = bg + thr_frac * (np.percentile(a, 99.9) - bg)
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W]
    cen = []
    for _ in range(max_n):
        i = int(np.argmax(a))
        py, px = divmod(i, W)
        if a[py, px] < thr:
            break
        r = 26
        y0, y1 = max(0, py - r), min(H, py + r + 1)
        x0, x1 = max(0, px - r), min(W, px + r + 1)
        w = np.clip(a[y0:y1, x0:x1] - thr, 0, None)
        t = w.sum()
        cx = (w * np.arange(x0, x1)[None, :]).sum() / t if t > 0 else float(px)
        cy = (w * np.arange(y0, y1)[:, None]).sum() / t if t > 0 else float(py)
        cen.append((cx, cy))
        a[(yy - py) ** 2 + (xx - px) ** 2 < mask_r ** 2] = bg
    if len(cen) < 2:
        return np.empty((0, 2)), np.empty(0)
    c = np.array(cen)
    d = np.linalg.norm(c[:, None] - c[None, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1) * px_um
    inside = ((c[:, 0] >= edge_px) & (c[:, 0] <= W - edge_px)
              & (c[:, 1] >= edge_px) & (c[:, 1] <= H - edge_px))
    return c[inside], nn[inside]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--out-dir", required=True,
                    help="date folder; each field gets its own run folder inside")
    ap.add_argument("--prefix", default="wall-diffusion")
    ap.add_argument("--start", type=int, default=1,
                    help="first run number, so a grid can extend an existing day")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--exposure-ms", type=float, default=33.3333)
    ap.add_argument("--step-um", type=float, default=300.0,
                    help="grid pitch. Must exceed the field width or fields "
                         "share beads and stop being independent (default 300)")
    ap.add_argument("--settle-s", type=float, default=15.0,
                    help="dwell after each stage move, before the pre-check. "
                         "Post-move creep decays over seconds -- the only "
                         "measured figure on this instrument is the piezo's "
                         "9-33 nm/s -- and a block started on the steep part "
                         "of that curve carries drift the short-lag fit window "
                         "cannot see and cannot remove (default 15)")
    ap.add_argument("--min-isolated", type=int, default=10,
                    help="skip a field with fewer interior beads past the "
                         "isolation cut (default 10)")
    ap.add_argument("--isolation-um", type=float, default=12.0)
    ap.add_argument("--intensity", type=float, default=20.0,
                    help="per-mille, 0-1000, NOT percent (default 20 = 2%%)")
    ap.add_argument("--line", default="GREEN")
    ap.add_argument("--light-device", default="Aura")
    ap.add_argument("--temperature-c", type=float, required=True,
                    help="measured sample temperature; dD/D is 2.74%%/K and "
                         "nothing on this instrument measures it")
    ap.add_argument("--trap-emission-off", action="store_true")
    ap.add_argument("--fields", type=int, default=9)
    ap.add_argument("--dry-run", action="store_true",
                    help="move, settle and pre-check every field, acquire "
                         "nothing. Use it to map the density before spending disk")
    args = ap.parse_args(argv)

    if not args.trap_emission_off:
        print("REFUSING: pass --trap-emission-off once the 1064 nm emission is "
              "confirmed off at the Aresis. Closing Turret2Shutter is not the "
              "fix -- it blocks the image too.", file=sys.stderr)
        return 2

    from pymmcore_plus import CMMCorePlus  # noqa: PLC0415  (slow import)
    core = CMMCorePlus()
    core.loadSystemConfiguration(str(args.cfg))

    class _Args:
        camera = None
        expect_objective = "60x"

    rec0, refusals = preflight(core, _Args())
    camera = rec0["camera"]
    px_um = rec0.get("pixel_size_um") or 0.10833
    if refusals:
        print("\nREFUSALS:")
        for r in refusals:
            print(f"  - {r}")
        print("\nNothing acquired.", file=sys.stderr)
        return 1

    field_um = core.getImageWidth() * px_um
    if args.step_um <= field_um:
        print(f"REFUSING: a {args.step_um:.0f} um pitch does not clear the "
              f"{field_um:.0f} um field, so neighbouring fields would share "
              "beads and stop being independent samples.", file=sys.stderr)
        return 2
    print(f"\nfield {field_um:.0f} um, grid pitch {args.step_um:.0f} um "
          f"-> fields do not overlap")

    _, pp_refusals = disable_post_processing(core, camera)
    if pp_refusals:
        for r in pp_refusals:
            print(f"  - {r}", file=sys.stderr)
        return 1

    core.setExposure(float(args.exposure_ms))
    exposure = float(core.getExposure())
    n_frames = max(1, int(round(args.seconds * 1000.0 / exposure)))
    gb = n_frames * core.getImageWidth() * core.getImageHeight() * 2 / 1e9
    print(f"exposure {exposure:.4f} ms -> {n_frames} frames per field "
          f"({gb:.1f} GB each)")

    pfs_before = core.getProperty("PFS", "FocusMaintenance")
    core.setProperty("PFS", "FocusMaintenance", "On")
    print(f"PFS FocusMaintenance: {pfs_before!r} -> "
          f"{core.getProperty('PFS', 'FocusMaintenance')!r}")

    ox, oy = core.getXPosition(), core.getYPosition()
    print(f"origin ({ox:.2f}, {oy:.2f}) um; travel refused beyond "
          f"+-{MAX_OFFSET_UM:.0f} um from it")

    engine = args.light_device
    prior_role = core.getShutterDevice()
    core.setProperty(engine, f"{args.line}_Intensity", args.intensity)
    log = []
    try:
        for k, (gx, gy) in enumerate(GRID[:args.fields]):
            dx, dy = gx * args.step_um, gy * args.step_um
            if max(abs(dx), abs(dy)) > MAX_OFFSET_UM:
                print(f"\n[{k}] offset ({dx:+.0f},{dy:+.0f}) um exceeds the "
                      f"+-{MAX_OFFSET_UM:.0f} um limit -- refused, not clamped")
                log.append({"index": k, "offset_um": [dx, dy],
                            "skipped": "over the travel limit"})
                continue

            name = f"{args.prefix}-{args.start + k:03d}"
            print(f"\n[{k}] {name}   offset ({dx:+.0f},{dy:+.0f}) um")
            core.setXYPosition(ox + dx, oy + dy)
            core.waitForDevice(core.getXYStageDevice())
            time.sleep(args.settle_s)
            x, y = core.getXPosition(), core.getYPosition()
            in_range = core.getProperty("PFS", "PFS in Range")
            z = core.getPosition("ZDrive")
            print(f"     at ({x:.2f}, {y:.2f})  settled {args.settle_s:.0f} s  "
                  f"ZDrive {z:.3f}  PFS {in_range!r}")

            core.setProperty(engine, args.line, 1)
            core.setShutterDevice(engine)
            core.setShutterOpen(True)
            core.snapImage()
            pre = np.asarray(core.getImage(), dtype=float) - OFFSET_ADU
            cen, nn = detect(pre, px_um, edge_px=32)
            n_iso = int((nn >= args.isolation_um).sum()) if nn.size else 0
            print(f"     pre-check: {len(cen)} interior, {n_iso} with "
                  f"nn >= {args.isolation_um:.0f} um")

            entry = {"index": k, "name": name, "offset_um": [dx, dy],
                     "xy_um": [x, y], "zdrive_um": z,
                     "pfs_in_range": in_range, "settle_s": args.settle_s,
                     "n_interior": int(len(cen)), "n_isolated": n_iso}

            if args.dry_run or n_iso < args.min_isolated:
                core.setShutterOpen(False)
                core.setProperty(engine, args.line, 0)
                why = ("dry run" if args.dry_run
                       else f"only {n_iso} isolated beads, wanted "
                            f"{args.min_isolated}")
                entry["skipped"] = why
                print(f"     SKIPPED ({why})")
                log.append(entry)
                continue

            stem = Path(args.out_dir) / name / name
            res = capture_timestamped(core, n_frames, interval_ms=0.0,
                                      camera=camera)
            core.setShutterOpen(False)
            core.setProperty(engine, args.line, 0)
            # Save before reporting, for the reason run_wall_diffusion.py
            # records: the frames live only in this process's RAM until
            # write() runs, so nothing goes between the capture and the write.
            paths = res.write(stem)
            fps = res.achieved_fps
            gaps = res.image_number_gaps
            print(f"     captured {res.n_captured}/{res.n_requested}  "
                  f"{fps:.4f} fps  ImageNumber gaps {len(gaps)}  "
                  f"-> {stem.parent}")
            entry.update({"n_captured": res.n_captured,
                          "n_requested": res.n_requested,
                          "achieved_fps": fps,
                          "image_number_gaps": len(gaps),
                          "dropped": res.dropped_by_image_number,
                          "files": {kk: str(vv) for kk, vv in paths.items()}})
            log.append(entry)
    finally:
        try:
            core.setShutterOpen(False)
            core.setProperty(engine, args.line, 0)
            core.setShutterDevice(prior_role)
            core.setXYPosition(ox, oy)
            core.waitForDevice(core.getXYStageDevice())
            core.setProperty("PFS", "FocusMaintenance", pfs_before)
            print(f"\nrestored: XY ({core.getXPosition():.2f}, "
                  f"{core.getYPosition():.2f}) um, PFS FocusMaintenance "
                  f"{core.getProperty('PFS', 'FocusMaintenance')!r}, light off")
        except Exception as exc:
            print(f"\nWARNING: restore failed ({exc}) -- check XY, PFS and the "
                  "light engine by hand.", file=sys.stderr)

    summary = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cfg": str(args.cfg),
        "origin_xy_um": [ox, oy],
        "step_um": args.step_um,
        "field_um": field_um,
        "exposure_ms": exposure,
        "n_frames": n_frames,
        "seconds": args.seconds,
        "settle_s": args.settle_s,
        "temperature_c": args.temperature_c,
        "isolation_um": args.isolation_um,
        "min_isolated": args.min_isolated,
        "intensity_per_mille": args.intensity,
        "line": args.line,
        "light_device": args.light_device,
        "trap_emission_off_asserted": True,
        "pixel_size_um": px_um,
        "pixel_size_source": rec0.get("pixel_size_source"),
        "fields": log,
    }
    sp = Path(args.out_dir) / f"{args.prefix}_grid_{args.start:03d}_summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2, default=str) + "\n",
                  encoding="utf-8")
    print(f"wrote grid summary: {sp}")
    got = [e for e in log if "n_captured" in e]
    print(f"\n{len(got)} of {min(args.fields, len(GRID))} fields acquired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
