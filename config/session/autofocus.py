r"""Find focus by driving ZDrive, instead of asking the operator to turn the knob.

    # plan only -- prints every Z it would command, moves nothing
    python config/session/autofocus.py

    # actually sweep, park at the peak, then hand it to PFS to hold
    python config/session/autofocus.py --allow-motion --park --hold-pfs

    # a wide first pass at low mag, where the working distance is millimetres
    python config/session/autofocus.py --allow-motion --half-range 150 --coarse-step 5

This is steps 1-3 of the operator's sequence (user, 2026-09-07): go to an
objective, move Z until the edge is sharpest, record the focus value. Step 4-5
-- change objective and re-acquire -- are
`config/session/measure_objective_offsets.py`, which calls this same machinery
once per lens.

WHAT MOVES, AND WHAT HAS TO BE TRUE FIRST
-----------------------------------------
It writes `ZDrive`, which is in `hardware.microscope.COLLISION_DEVICES`, on a
stand that runs **no objective-escape** (SAFETY.md §2). Every guard lives in
`hardware/focus.py` and is tested in `tests/test_focus.py`; the two that matter
most here:

  * **Without `--allow-motion` nothing moves.** The script still runs, plans the
    sweep, and prints every Z -- so the plan is reviewable before it is a
    motion. That is the default on purpose.
  * **The sweep is capped by the objective's working distance**, not by taste:
    +/-52 um at 100x Oil (0.4 x 130 um), and by the 2800-3200 um sample window
    at low mag where the WD is millimetres. A request past either is refused
    with both numbers in the message.

PFS MUST BE OFF TO SWEEP, AND IS THE RIGHT PLACE TO END
-------------------------------------------------------
A servoing PFS drives Z back while the sweep commands it away, and the recorded
curve then describes planes the stage never held. 2026-09-07 lost time to the
other half of the same fact: "PFS holds a focus, it does not find one". So
`--disable-pfs` switches it off before sweeping (off is the safe direction --
it stops the servo, it does not move), and `--hold-pfs` switches it back on at
the end, which is what PFS is actually for. `--hold-pfs` commands motion: the
servo drives Z to acquire its lock, and the script reports how far it went.

LIGHT
-----
One line, on for the sweep only, off in a `finally` -- including the engine's
master `State`, whose omission produced a whole fake measurement on 2026-09-06.
A sweep is a dose: n_points frames at the chosen level, so a 400-point fine
sweep at 200/1000 is not a free measurement (lens 5).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from detection.focus_metric import bead_area_window, ceiling_from_bit_depth, score_frame
from hardware.focus import (
    DEFAULT_EMISSION_NM,
    MIN_CONTRAST_COARSE,
    MIN_CONTRAST_FINE,
    SWEEP_WD_FRACTION,
    FocusAxis,
    FocusError,
    best_z_um,
    free_working_distance_um,
    registry_key,
    suggest_step_um,
)

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CFG = REPO / "config" / "micromanager" / "single_cam_red_noDMD.cfg"

#: The Aura's lines. All of them are driven to zero by `light_off`, because
#: leaving one at a non-zero intensity with `State` off is a trap for the next
#: run -- it comes back on the moment anything writes `State`.
LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]


def light_off(core, engine: str) -> None:
    """Everything dark, whichever source was used.

    Deliberately not "switch off the engine I was told about": the `finally`
    that calls this wants the instrument dark, and since 2026-09-07 the
    transmitted path is a second source. Switching off only the named one would
    leave the other burning after a crash.
    """
    #: `hasProperty` FIRST, not try/except. Both work, but writing "UV" to the
    #: DiaLamp and catching the failure makes pymmcore-plus emit a full
    #: traceback per line from inside its property-change machinery -- ten of
    #: them, which on 2026-09-07 buried the actual sweep output. A refusal that
    #: is expected should not be raised at all.
    for prop, value in ([("State", "0")]
                        + [(l, "0") for l in LINES]
                        + [(f"{l}_Intensity", "0") for l in LINES]):
        try:
            if core.hasProperty(engine, prop):
                core.setProperty(engine, prop, value)
        except Exception:
            pass
    try:
        if core.hasProperty("DiaLamp", "State"):
            core.setProperty("DiaLamp", "State", "0")
    except Exception:
        pass


def light_on(core, engine: str, line: str, per_mille: int) -> None:
    """One line. `State` is the engine's master shutter -- without it nothing
    comes out however the lines are set, and Core.Shutter is LightEngine rather
    than Aura, so autoshutter never opens this one."""
    for other in LINES:
        core.setProperty(engine, other, "0")
        core.setProperty(engine, f"{other}_Intensity", "0")
    core.setProperty(engine, f"{line}_Intensity", str(int(per_mille)))
    core.setProperty(engine, line, "1")
    core.setProperty(engine, "State", "1")
    core.waitForDevice(engine)


#: Ceiling on `DiaLamp > Intensity`, read off the device 2026-09-07. Used only
#: as the fallback when the adapter does not report limits -- the live value is
#: preferred, because a hard-coded ceiling is how a "percentage" gets written
#: into a property that does not take one.
DIALAMP_INTENSITY_MAX = 2100.0


def light_on_transmitted(core, intensity: float) -> float:
    """DiaLamp transmitted brightfield -- for an ABSORBING fiducial.

    A Sharpie cross, a scratch or a graticule has no fluorescence to excite: its
    contrast is in transmission. Epi-illuminating it would measure whatever the
    ink happens to emit, which is not the edge being focused on.

    Two things measured on the device 2026-09-07, both of which the first
    version of this function got wrong:

      * **`Intensity` runs 0..2100, not 0..100.** Taken from
        `getPropertyUpperLimit` rather than assumed, and clamped -- a "50"
        meant as a percentage is 2.4% of this lamp, which reads as darkness.
      * **`State` is a separate master switch, and it was `0`.** Setting
        `Intensity` alone leaves the lamp off, so every frame of the sweep comes
        back black, the focus curve is flat, and the run reports "no peak" for a
        reason that has nothing to do with focus. That is the same failure as
        the Aura's `State` on 2026-09-06, on a different device.

    Returns the intensity actually commanded, so the caller prints what the
    lamp got rather than what it was asked for.
    """
    hi = DIALAMP_INTENSITY_MAX
    try:
        if core.hasPropertyLimits("DiaLamp", "Intensity"):
            hi = float(core.getPropertyUpperLimit("DiaLamp", "Intensity"))
    except Exception:
        pass
    level = max(0.0, min(float(intensity), hi))
    core.setProperty("DiaLamp", "Intensity", str(int(level)))
    core.setProperty("DiaLamp", "State", "1")
    core.waitForDevice("DiaLamp")
    return level


def disable_pp(core, camera: str) -> dict:
    """Turn every camera post-processing ENABLED entry off, and leave it off.

    Despeckle is back on after every config load (six `PP * ENABLED` entries,
    2026-09-07) and it replaces threshold-crossing pixels with a neighbour
    value -- so it edits exactly the sharp features a Tenengrad score is
    measuring. A focus curve taken with despeckle on is a curve of a smoothed
    image.

    `startswith("PP")`, not `"ENABLED" in name` -- the loose test also matches
    `CircularBufferEnabled`, which this has no business touching.
    """
    changed: dict = {}
    for name in core.getDevicePropertyNames(camera):
        if not name.startswith("PP") or "ENABLED" not in name.upper():
            continue
        try:
            before = str(core.getProperty(camera, name))
        except Exception:
            continue
        if before.strip().lower() in {"no", "0", "false", "off"}:
            continue
        allowed = list(core.getAllowedPropertyValues(camera, name)) or ["No"]
        off = next((v for v in allowed
                    if str(v).strip().lower() in {"no", "0", "false", "off"}), "No")
        try:
            core.setProperty(camera, name, off)
            changed[name] = f"{before} -> {off}"
        except Exception as exc:
            changed[name] = f"{before} -> FAILED: {exc}"
    return changed


def make_grab(core):
    """A frame per call. `snapImage` is always paired with `getImage`.

    An unretrieved flush frame throws "Unknown error in the device (1)" at the
    next strobe switch, which reads like a camera fault and is not one.
    """
    def grab():
        core.snapImage()
        return np.asarray(core.getImage())
    return grab


def write_curve(out_dir: Path, stem: str, curves: dict, summary: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    rows = []
    for pass_name, curve in curves.items():
        if curve is None:
            continue
        for p in curve.points:
            rows.append({"pass": pass_name, "z_um": p.z_um,
                         "z_readback_um": p.z_readback_um, **p.diagnostics})
    if rows:
        keys = list(rows[0].keys())
        with (out_dir / f"{stem}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"\nwrote {out_dir / stem}.json and .csv", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--objective", default=None,
                   help="registry key or MM label; default reads the Nosepiece")
    p.add_argument("--z-center", type=float, default=None,
                   help="sweep centre in ZDrive um; default is the current position")
    p.add_argument("--half-range", type=float, default=None,
                   help="um either side of centre; default is 0.25 x the free "
                        "working distance, capped at 150 um")
    p.add_argument("--coarse-step", type=float, default=None,
                   help="um; default spreads ~40 points over the range, never "
                        "finer than half the depth of field")
    p.add_argument("--no-fine", action="store_true",
                   help="coarse pass only")
    p.add_argument("--emission-nm", type=float, default=DEFAULT_EMISSION_NM,
                   help="for the depth-of-field-derived step size")
    p.add_argument("--light-device", default="Aura",
                   choices=["Aura", "DiaLamp"],
                   help="Aura line for fluorescence; DiaLamp for transmitted brightfield")
    p.add_argument("--line", default="GREEN", choices=LINES)
    p.add_argument("--level", type=int, default=80, help="per-mille on that line")
    p.add_argument("--exposure-ms", type=float, default=20.0)
    p.add_argument("--binning", default=None, help="e.g. 1x1; default leaves it as found")
    p.add_argument("--feature-um", type=float, default=None,
                   help="feature diameter for the count/area diagnostic. Omit for "
                        "an edge or a graticule, which is not a blob")
    p.add_argument("--settle-coarse-s", type=float, default=0.05)
    p.add_argument("--settle-fine-s", type=float, default=0.20)
    p.add_argument("--allow-motion", action="store_true",
                   help="REQUIRED to write ZDrive. Without it this plans and prints")
    p.add_argument("--disable-pfs", action="store_true",
                   help="switch PFS off before sweeping (off moves nothing)")
    p.add_argument("--hold-pfs", action="store_true",
                   help="after parking at the peak, enable PFS to hold it. "
                        "COMMANDS MOTION: the servo drives Z to acquire lock")
    p.add_argument("--park", action="store_true",
                   help="leave the stage at the found peak, approached from below")
    p.add_argument("--out", default=None, help="directory for the curve CSV/JSON")
    args = p.parse_args(argv)

    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"loading {args.cfg}", flush=True)
    core.loadSystemConfiguration(args.cfg)

    camera = core.getCameraDevice()
    label = core.getStateLabel("Nosepiece")
    key = registry_key(args.objective or label)
    fwd = free_working_distance_um(key)
    print(f"objective: {label!r}  ->  registry {key}   free WD {fwd:.0f} um", flush=True)
    if args.objective and registry_key(label) != key:
        print(f"  !! the Nosepiece reads {registry_key(label)}, you named {key}. "
              f"The working-distance bound will use {key} -- make sure that is the "
              f"lens actually in the path.", flush=True)

    core.setAutoShutter(False)
    if args.binning:
        core.setProperty(camera, "Binning", args.binning)
    core.setExposure(args.exposure_ms)
    changed = disable_pp(core, camera)
    for name, what in changed.items():
        print(f"  post-processing {name}: {what}", flush=True)

    ceiling = ceiling_from_bit_depth(core.getImageBitDepth())
    pixel_um = core.getPixelSizeUm()
    area_px = (bead_area_window(pixel_um, args.feature_um)
               if args.feature_um and pixel_um else None)
    print(f"  {camera}: bin {core.getProperty(camera, 'Binning')} "
          f"{core.getImageWidth()}x{core.getImageHeight()} "
          f"{core.getExposure():.1f} ms, {core.getImageBitDepth()}-bit "
          f"(ceiling {ceiling:.0f} ADU), {pixel_um:.4f} um/px", flush=True)
    if area_px:
        print(f"  a {args.feature_um} um feature counts as {area_px[0]}-{area_px[1]} px",
              flush=True)

    axis = FocusAxis(core, key, allow_motion=args.allow_motion,
                     dry_run=not args.allow_motion)
    z_now = axis.position_um()
    z_center = args.z_center if args.z_center is not None else z_now
    half_range = (args.half_range if args.half_range is not None
                  else min(0.25 * fwd, 150.0))
    print(f"\nZDrive now {z_now:.3f} um; sweeping +/-{half_range:.1f} um about "
          f"{z_center:.3f} um", flush=True)
    print(f"  step floor from depth of field: {suggest_step_um(key, args.emission_nm):.4f} um; "
          f"WD budget {SWEEP_WD_FRACTION:g} x {fwd:.0f} = "
          f"{SWEEP_WD_FRACTION * fwd:.1f} um", flush=True)
    if not args.allow_motion:
        print("  --allow-motion NOT set: planning only, nothing will move.", flush=True)

    def score(frame):
        return score_frame(frame, area_px, ceiling)

    coarse = fine = None
    summary: dict = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "cfg": args.cfg, "camera": camera, "objective_label": label,
        "objective_key": key, "free_wd_um": fwd,
        "pixel_um": pixel_um, "bit_depth": core.getImageBitDepth(),
        "ceiling_adu": ceiling, "exposure_ms": core.getExposure(),
        "binning": str(core.getProperty(camera, "Binning")),
        "line": args.line, "level_per_mille": args.level,
        "z_start_um": z_now, "z_center_um": z_center, "half_range_um": half_range,
        "allow_motion": bool(args.allow_motion),
        "post_processing_changed": changed,
    }
    try:
        axis.require_pfs_quiet(disable=args.disable_pfs)
    except FocusError as exc:
        print(f"\nREFUSED: {exc}", flush=True)
        return 2

    try:
        if args.light_device == "Aura":
            light_on(core, args.light_device, args.line, args.level)
            print(f"\nlight ON: {args.line} {args.level}/1000\n", flush=True)
        else:
            level = light_on_transmitted(core, args.level)
            print(f"\nlight ON: transmitted DiaLamp {level:.0f}/2100\n", flush=True)
        coarse, fine = axis.autofocus(
            z_center, half_range, make_grab(core),
            coarse_step_um=args.coarse_step, fine=not args.no_fine,
            score=score, settle_coarse_s=args.settle_coarse_s,
            settle_fine_s=args.settle_fine_s, emission_nm=args.emission_nm,
        )
    except FocusError as exc:
        print(f"\nREFUSED: {exc}", flush=True)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted -- the stage is wherever the last step left it", flush=True)
    finally:
        light_off(core, args.light_device)
        print("\nlight OFF", flush=True)

    if coarse is None:
        return 1

    print("\n" + "=" * 72, flush=True)
    print("FOCUS", flush=True)
    print("=" * 72, flush=True)
    # Each pass judged against ITS OWN bar. Using one bar for both printed
    # "fine NO" directly above a conclusion that read "fine pass: ..." on
    # 2026-09-07 -- the table contradicted the answer under it.
    for name, curve, bar in (("coarse", coarse, MIN_CONTRAST_COARSE),
                             ("fine", fine, MIN_CONTRAST_FINE)):
        if curve is None:
            print(f"  {name:6s} skipped", flush=True)
            continue
        ok, why = curve.verdict(bar)
        print(f"  {name:6s} {'OK ' if ok else 'NO '} {why}", flush=True)
        print(f"         {len(curve.points)} points, "
              f"{curve.span.lo_um:.3f} -> {curve.span.hi_um:.3f} um "
              f"@ {curve.span.step_um:.4f} um", flush=True)

    z_best, provenance = best_z_um(coarse, fine)
    summary["z_best_um"] = z_best
    summary["provenance"] = provenance
    summary["coarse_verdict"] = coarse.verdict(MIN_CONTRAST_COARSE)[1]
    summary["fine_verdict"] = (fine.verdict(MIN_CONTRAST_FINE)[1] if fine else None)
    print(f"\n  best Z: {'-- none --' if z_best is None else f'{z_best:.3f} um'}"
          f"\n  {provenance}", flush=True)

    if z_best is None:
        print("\n  Nothing to park at. Widen --half-range, or re-centre --z-center "
              "on where you think the sample is (2800-3200 um on this instrument).",
              flush=True)
    elif args.park:
        try:
            landed = axis.park_at(z_best)
            summary["z_parked_um"] = landed
            print(f"\n  parked at {landed:.3f} um (approached from below, matching "
                  f"the sweep)", flush=True)
            if args.hold_pfs:
                summary["pfs"] = axis.enable_pfs_hold()
        except FocusError as exc:
            print(f"\nREFUSED while parking: {exc}", flush=True)
    else:
        print("\n  --park not set: the stage is at the end of the last sweep, "
              "not at the peak.", flush=True)

    if args.out:
        stem = f"autofocus-{key}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        write_curve(Path(args.out), stem, {"coarse": coarse, "fine": fine}, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
