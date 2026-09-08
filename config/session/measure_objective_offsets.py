r"""Measure the x/y/z offsets between objectives, one lens at a time.

    # the dry + water pass, operator rotating the nosepiece at the stand
    python config/session/measure_objective_offsets.py --allow-motion \
        --objectives 4x,10x,20x,40x-WI --allow-immersion-change \
        --out D:\data\offsets

    # the oil pass, after the sample change
    python config/session/measure_objective_offsets.py --allow-motion \
        --objectives 20x,60x-Oil,100x-Oil --allow-immersion-change \
        --out D:\data\offsets

This is steps 4-5 of the operator's sequence (user, 2026-09-07): change to the
objective you want, then adjust x, y and z to get the best focus. The numbers
it records are what make step 4 unnecessary next time -- "in real experiment you
can go directly using offset values we will measure today".

WHAT AN OFFSET MEANS HERE
-------------------------
Per objective it records three things, with the XY stage **held still** for the
whole pass:

    z   the ZDrive position of peak focus, absolute um. The difference between
        two objectives is their PARFOCAL offset.
    x,y where the fiducial sits in the image, converted to um through that
        objective's own pixel size. The difference between two objectives is
        their PARCENTRIC offset -- how far the field centre shifts on rotation.

Holding the stage still is what makes x/y meaningful: if the stage moves between
lenses, the fiducial's image position changes for two reasons at once and
neither can be recovered from the sum. The consequence is that the fiducial has
to stay in the field at the HIGHEST magnification in the pass, which is a real
constraint on where you park it -- 100x/1x on a Kinetix is a ~139 um field.

**Offsets come out in CAMERA um, not stage um**, unless `--calibrate-xy` is
given. The camera's axes are not the stage's: image y runs down, and the
rotation between them has never been measured for this path (only the
OT->camera one has, `TRAP_ORIGIN_OFFSET_UM`). `--calibrate-xy` measures it, per
objective, by stepping the stage a known amount and watching the fiducial move
-- and then the offsets are also reported as the `setXYPosition` move that
applies them.

THE NUMBER THAT BOUNDS EVERY OTHER NUMBER
-----------------------------------------
The safe way to change an objective retracts Z clear of the sample first
(SAFETY.md §2: `Z -> 0`, rotate, `Z -> 2800`, re-focus). So every parfocal
offset is a difference between two absolute Z values measured either side of a
full retract-and-return cycle, and it is therefore only as good as ZDrive's
return repeatability -- **which nobody has measured on this stand.**

So the pass ends where it started: it returns to the first objective and
re-measures it. The disagreement is the loop-closure error, and it is reported
as an uncertainty on every offset in the table. An offset smaller than the
closure is not a measurement. This is the same discipline
`trap_from_tracking.py calibrate` applies to itself -- a fit that fails its own
checks is a refusal, not a result.

IMMERSION IS A HAZARD THIS SCRIPT WILL NOT DECIDE FOR YOU
---------------------------------------------------------
The nosepiece mixes three immersion classes: 4x/10x/20x air, 40x WI water,
60x/100x oil (`data/objectives.yaml`). Rotating a dry lens past an oiled or
watered coverslip can wet it, and oil on a water-immersion front element
cross-contaminates. Any pass that crosses classes is refused unless
`--allow-immersion-change` says you have thought about it, and the crossing is
named in the prompt each time it happens.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

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
    FocusAxis,
    FocusError,
    best_z_um,
    free_working_distance_um,
    registry_key,
)
from hardware.microscope import SAMPLE_Z_WINDOW_UM

from autofocus import LINES, disable_pp, light_off, light_on, light_on_transmitted, make_grab

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CFG = REPO / "config" / "micromanager" / "single_cam_red_noDMD.cfg"

#: Where the operator's own objective-change sequence parks Z before rotating,
#: and where it returns to afterwards -- SAFETY.md §2. 2800 is the NEAR EDGE of
#: SAMPLE_Z_WINDOW_UM, deliberately not the 2959 um sample plane: it is a place
#: to start searching from, not a focus.
ROTATE_Z_UM = 0.0
RETURN_Z_UM = SAMPLE_Z_WINDOW_UM[0]


def nosepiece_positions() -> dict[str, int]:
    """Registry key -> Nosepiece state index, from data/objectives.yaml.

    `optics.components.Objective` does not carry `position`, so this reads the
    registry directly rather than inventing a mapping from the label's leading
    digit -- the label reads "6-Plan Apo ... 100x Oil" and the state is 5.
    """
    raw = yaml.safe_load((REPO / "data" / "objectives.yaml").read_text(encoding="utf-8"))
    out = {}
    for key, spec in (raw.get("objectives") or {}).items():
        if spec.get("position") is not None:
            out[str(key)] = int(spec["position"])
    return out


def immersion_of(key: str) -> str:
    from optics.components import find_objective

    obj = find_objective(key)
    return (obj.immersion if obj else "unknown") or "unknown"


# --------------------------------------------------------------------------
# where is the fiducial?
# --------------------------------------------------------------------------

def locate_centroid(frame: np.ndarray, k_mad: float = 8.0) -> tuple[float, float, dict]:
    """Sub-pixel centroid of the brightest compact feature. (u, v) in px.

    Intensity-weighted inside the largest above-threshold component, so it is
    not quantised to the pixel grid -- a whole-pixel centroid at 4x is a 1.6 um
    quantisation on an offset that may itself only be a few um.

    The threshold is median + k x MAD on a high-pass residual, the same
    construction `detection.focus_metric.score_frame` uses for its bead count,
    so a feature this finds is a feature that scored.
    """
    import cv2

    f32 = np.asarray(frame, dtype=np.float32)
    smooth = cv2.GaussianBlur(f32, (0, 0), 15)
    residual = f32 - smooth
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0
    mask = (residual > k_mad * scale).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        raise FocusError(
            f"no feature above median + {k_mad:g} x MAD in this frame. Either the "
            f"fiducial is out of the field at this magnification, or the light is "
            f"too low -- nothing to locate."
        )
    idx = 1 + int(np.argmax(stats[1:, 4]))
    x, y, w, h, area = stats[idx]
    sub = residual[y:y + h, x:x + w] * (labels[y:y + h, x:x + w] == idx)
    sub = np.clip(sub, 0, None)
    total = float(sub.sum()) or 1.0
    vv, uu = np.mgrid[0:h, 0:w]
    u = x + float((sub * uu).sum()) / total
    v = y + float((sub * vv).sum()) / total
    return u, v, {"mode": "centroid", "area_px": int(area),
                  "n_components": int(n - 1), "bbox": [int(x), int(y), int(w), int(h)]}


def locate_by_correlation(frame: np.ndarray, reference: np.ndarray,
                          mag_ratio: float) -> tuple[float, float, dict]:
    """Fiducial position by phase correlation against a rescaled reference.

    The mode for a target that is not a blob -- an edge, a graticule, a scratch.
    The reference frame (from the first objective) is rescaled by the
    magnification ratio so the two images have features of the same size, then
    `cv2.phaseCorrelate` gives the shift between them.

    Returns the fiducial position implied by that shift, in the CURRENT frame's
    pixels, so it is directly comparable with `locate_centroid`'s answer.
    """
    import cv2

    cur = np.asarray(frame, dtype=np.float32)
    ref = np.asarray(reference, dtype=np.float32)
    scaled = cv2.resize(ref, None, fx=mag_ratio, fy=mag_ratio,
                        interpolation=cv2.INTER_AREA if mag_ratio < 1 else cv2.INTER_CUBIC)

    # Match sizes by centre-cropping or centre-padding the rescaled reference.
    h, w = cur.shape
    sh, sw = scaled.shape
    if sh >= h and sw >= w:
        oy, ox = (sh - h) // 2, (sw - w) // 2
        scaled = scaled[oy:oy + h, ox:ox + w]
    else:
        pad = np.full((h, w), float(np.median(scaled)), dtype=np.float32)
        oy, ox = (h - sh) // 2, (w - sw) // 2
        pad[max(oy, 0):max(oy, 0) + min(sh, h), max(ox, 0):max(ox, 0) + min(sw, w)] = \
            scaled[:min(sh, h), :min(sw, w)]
        scaled = pad

    win = cv2.createHanningWindow((w, h), cv2.CV_32F)
    (du, dv), response = cv2.phaseCorrelate(scaled - scaled.mean(), cur - cur.mean(), win)
    return (w / 2.0 + du, h / 2.0 + dv,
            {"mode": "correlate", "mag_ratio": mag_ratio, "response": float(response),
             "shift_px": [float(du), float(dv)]})


# --------------------------------------------------------------------------
# the per-objective measurement
# --------------------------------------------------------------------------

def prompt_rotate(key: str, state: int | None, from_key: str | None,
                  crossing: str | None, no_prompt: bool) -> None:
    print("\n" + "-" * 72, flush=True)
    print(f"CHANGE OBJECTIVE -> {key}"
          + (f"  (Nosepiece state {state})" if state is not None else ""), flush=True)
    print("-" * 72, flush=True)
    if crossing:
        print(f"  !! IMMERSION CHANGE: {crossing}. A dry lens rotated past an oiled "
              f"or\n     watered coverslip can be wetted, and oil on a WI front "
              f"element\n     cross-contaminates. Clean the coverslip if that is the "
              f"plan.", flush=True)
    print(f"  Z is retracted to {ROTATE_Z_UM:.0f} um. The stand runs NO "
          f"objective-escape, so\n  the incoming lens arrives at whatever Z the "
          f"outgoing one was at -- which is\n  why the retract came first "
          f"(SAFETY.md §2).", flush=True)
    print(f"  Rotate to {key} at the stand or in NIS, then press Enter.", flush=True)
    if not no_prompt:
        try:
            input("  > ")
        except EOFError:
            print("  (no console -- continuing)", flush=True)


def measure_one(core, axis_factory, key: str, args, reference: dict | None,
                log=print) -> dict:
    """Autofocus, then locate the fiducial. Returns the record for one objective."""
    label = core.getStateLabel("Nosepiece")
    seen = registry_key(label)
    if seen != key:
        raise FocusError(
            f"asked to measure {key} but the Nosepiece reads {seen} ({label!r}). "
            f"Refusing: every number below would be attributed to the wrong lens."
        )
    camera = core.getCameraDevice()
    fwd = free_working_distance_um(key)
    pixel_um = core.getPixelSizeUm()
    ceiling = ceiling_from_bit_depth(core.getImageBitDepth())
    area_px = (bead_area_window(pixel_um, args.feature_um)
               if args.feature_um and pixel_um else None)
    log(f"  {key}: free WD {fwd:.0f} um, {pixel_um:.4f} um/px, "
        f"{core.getImageWidth()}x{core.getImageHeight()} "
        f"= {core.getImageWidth() * pixel_um:.1f} x "
        f"{core.getImageHeight() * pixel_um:.1f} um field")

    axis = axis_factory(key)
    axis.require_pfs_quiet(disable=args.disable_pfs)

    def score(frame):
        return score_frame(frame, area_px, ceiling)

    grab = make_grab(core)
    half_range = (args.half_range if args.half_range is not None
                  else min(0.25 * fwd, 150.0))
    z_center = args.z_center if args.z_center is not None else axis.position_um()

    coarse, fine = axis.autofocus(
        z_center, half_range, grab, coarse_step_um=args.coarse_step,
        fine=not args.no_fine, score=score,
        settle_coarse_s=args.settle_coarse_s, settle_fine_s=args.settle_fine_s,
        emission_nm=args.emission_nm,
    )
    z_best, provenance = best_z_um(coarse, fine)
    rec: dict = {
        "objective_key": key, "objective_label": label, "camera": camera,
        "free_wd_um": fwd, "pixel_um": pixel_um,
        "frame_px": [core.getImageWidth(), core.getImageHeight()],
        "bit_depth": core.getImageBitDepth(),
        "z_focus_um": z_best, "z_provenance": provenance,
        "coarse_verdict": coarse.verdict(MIN_CONTRAST_COARSE)[1],
        "fine_verdict": (fine.verdict(MIN_CONTRAST_FINE)[1] if fine else None),
        "utc": datetime.now(timezone.utc).isoformat(),
    }
    if z_best is None:
        log(f"  {key}: NO FOCUS -- {provenance}")
        return rec

    axis.park_at(z_best)
    rec["z_parked_um"] = axis.position_um()

    # One frame at focus, for the x/y measurement and as the reference for any
    # later correlation.
    frame = grab()
    rec["at_focus"] = score(frame)
    try:
        if args.locate == "correlate":
            if reference is None:
                # The FIRST objective in correlate mode defines the origin: its
                # own frame centre is (0, 0) and every later lens is measured as
                # a shift from it. Falling back to a centroid here would defeat
                # the point of the mode -- an edge or a graticule has no blob to
                # find, which is why correlate exists.
                h0, w0 = frame.shape
                u, v = w0 / 2.0, h0 / 2.0
                diag = {"mode": "correlate-reference",
                        "note": "origin by definition; later lenses are shifts from this"}
            else:
                ratio = pixel_um and (reference["pixel_um"] / pixel_um)
                u, v, diag = locate_by_correlation(
                    frame, np.asarray(reference["frame"]), float(ratio))
        else:
            u, v, diag = locate_centroid(frame)
    except FocusError as exc:
        log(f"  {key}: fiducial not located -- {exc}")
        rec["locate_error"] = str(exc)
        return rec

    h, w = frame.shape
    shift_um = [(u - w / 2.0) * pixel_um, (v - h / 2.0) * pixel_um]

    # In correlate mode the measured quantity is a shift relative to the
    # PREVIOUS lens, so the running offset accumulates. The chain is deliberate:
    # correlating every lens against the FIRST one means rescaling its frame by
    # the full magnification ratio -- 10x from 4x to 40x -- and a 4x frame
    # interpolated up 10x carries no detail at the scale the 40x image has
    # structure on. Adjacent steps are 1.5-2.5x, where the rescale is honest.
    #
    # The cost is that errors add along the chain rather than being independent,
    # which is exactly what the loop-closure repeat at the end measures.
    base = [0.0, 0.0]
    if args.locate == "correlate" and reference is not None:
        base = list(reference.get("offset_um") or [0.0, 0.0])
    offset_um = [base[0] + shift_um[0], base[1] + shift_um[1]]

    rec.update({
        "fiducial_px": [u, v],
        "fiducial_offset_px": [u - w / 2.0, v - h / 2.0],
        "fiducial_shift_um": shift_um,
        "fiducial_offset_um": offset_um,
        "locate": diag,
        "xy_stage_um": list(core.getXYPosition()),
        "frame": frame,  # stripped before serialising; kept for correlation
    })
    log(f"  {key}: focus Z {z_best:.3f} um; fiducial at ({u:.2f}, {v:.2f}) px "
        f"= ({rec['fiducial_offset_um'][0]:+.3f}, "
        f"{rec['fiducial_offset_um'][1]:+.3f}) um from centre")
    return rec


def calibrate_stage_to_camera(core, grab, step_um: float, log=print) -> dict | None:
    """Measure the 2x2 stage->camera matrix by stepping the stage twice.

    Without this the parcentric offsets are in camera um and cannot be turned
    into a `setXYPosition` move: image y runs down, and the rotation between the
    camera and the stage has never been measured for this path.

    Returns the matrix mapping a stage move (um) to the resulting image-plane
    displacement (px), plus its inverse, which is the useful direction.
    """
    x0, y0 = core.getXYPosition()
    try:
        u0, v0, _ = locate_centroid(grab())
        core.setXYPosition(x0 + step_um, y0)
        core.waitForDevice(core.getXYStageDevice())
        time.sleep(0.3)
        ux, vx, _ = locate_centroid(grab())
        core.setXYPosition(x0, y0 + step_um)
        core.waitForDevice(core.getXYStageDevice())
        time.sleep(0.3)
        uy, vy, _ = locate_centroid(grab())
    except Exception as exc:
        log(f"  xy calibration failed: {exc}")
        return None
    finally:
        core.setXYPosition(x0, y0)
        try:
            core.waitForDevice(core.getXYStageDevice())
        except Exception:
            pass

    # Columns: image displacement per um of stage x, and per um of stage y.
    m = np.array([[(ux - u0) / step_um, (uy - u0) / step_um],
                  [(vx - v0) / step_um, (vy - v0) / step_um]], dtype=float)
    det = float(np.linalg.det(m))
    if abs(det) < 1e-9:
        log(f"  xy calibration degenerate (det {det:.3g}) -- the fiducial did not "
            f"move, or moved the same way for both axes")
        return None
    return {"stage_to_camera_px_per_um": m.tolist(),
            "camera_px_to_stage_um": np.linalg.inv(m).tolist(),
            "step_um": step_um, "det": det}


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--objectives", required=True,
                   help="comma-separated registry keys, IN THE ORDER TO VISIT. "
                        "Start at the lowest magnification: its working distance "
                        "is millimetres, so the first search is the safe one")
    p.add_argument("--locate", default="centroid", choices=["centroid", "correlate"],
                   help="centroid for a bead or bright dot; correlate for an edge, "
                        "a graticule or a scratch")
    p.add_argument("--feature-um", type=float, default=None,
                   help="feature diameter, for the count/area diagnostic only")
    p.add_argument("--half-range", type=float, default=None)
    p.add_argument("--z-center", type=float, default=None,
                   help="sweep centre for the FIRST objective; later ones re-centre "
                        f"on {RETURN_Z_UM:.0f} um after the retract")
    p.add_argument("--coarse-step", type=float, default=None)
    p.add_argument("--no-fine", action="store_true")
    p.add_argument("--emission-nm", type=float, default=DEFAULT_EMISSION_NM)
    p.add_argument("--light-device", default="Aura",
                   choices=["Aura", "DiaLamp"],
                   help="Aura line for fluorescence; DiaLamp for transmitted brightfield")
    p.add_argument("--line", default="GREEN", choices=LINES)
    p.add_argument("--level", type=int, default=80, help="per-mille or percent")
    p.add_argument("--exposure-ms", type=float, default=20.0)
    p.add_argument("--binning", default=None)
    p.add_argument("--settle-coarse-s", type=float, default=0.05)
    p.add_argument("--settle-fine-s", type=float, default=0.20)
    p.add_argument("--allow-motion", action="store_true",
                   help="REQUIRED to write ZDrive. Without it this plans and prints")
    p.add_argument("--disable-pfs", action="store_true")
    p.add_argument("--allow-immersion-change", action="store_true",
                   help="permit a pass that crosses air/water/oil. Read the module "
                        "docstring first")
    p.add_argument("--calibrate-xy", type=float, default=None, metavar="STEP_UM",
                   help="measure the stage->camera matrix at each objective by "
                        "stepping the stage this far. Moves the XY stage")
    p.add_argument("--no-prompt", action="store_true",
                   help="do not wait for Enter at each objective change. Only "
                        "sensible with a single objective, or in a rehearsal")
    p.add_argument("--no-close-loop", action="store_true",
                   help="skip the return to the first objective. You then have no "
                        "bound on any offset -- see the module docstring")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    try:
        keys = [registry_key(k.strip()) for k in args.objectives.split(",") if k.strip()]
    except FocusError as exc:
        # A mistyped objective is an operator error, not a crash. A traceback
        # here buries the one useful line -- the list of keys that do exist.
        print(f"REFUSED: {exc}", flush=True)
        return 2
    if len(keys) < 2 and not args.no_close_loop:
        print("need at least two objectives for an offset (or --no-close-loop to "
              "measure a single one)", flush=True)
        return 2

    immersions = {k: immersion_of(k) for k in keys}
    classes = sorted(set(immersions.values()))
    if len(classes) > 1 and not args.allow_immersion_change:
        print(f"REFUSED: this pass crosses immersion classes -- "
              + ", ".join(f"{k} ({v})" for k, v in immersions.items())
              + ".\nRotating a dry lens past an oiled or watered coverslip can wet "
                "it, and oil on\na water-immersion front element cross-contaminates. "
                "Pass --allow-immersion-change\nif that is handled, or split the pass "
                "by class.", flush=True)
        return 2

    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"loading {args.cfg}", flush=True)
    core.loadSystemConfiguration(args.cfg)
    camera = core.getCameraDevice()
    core.setAutoShutter(False)
    if args.binning:
        core.setProperty(camera, "Binning", args.binning)
    core.setExposure(args.exposure_ms)
    for name, what in disable_pp(core, camera).items():
        print(f"  post-processing {name}: {what}", flush=True)

    positions = nosepiece_positions()
    order = list(keys) + ([] if args.no_close_loop else [keys[0]])
    print(f"\nvisiting: {' -> '.join(order)}"
          + ("" if args.no_close_loop else "   (the last is the loop-closure repeat)"),
          flush=True)
    for k in keys:
        print(f"  {k:9s} {immersions[k]:6s} state "
              f"{positions.get(k, '?')}   WD {free_working_distance_um(k):.0f} um",
              flush=True)
    if not args.allow_motion:
        print("\n  --allow-motion NOT set: planning only, nothing will move.", flush=True)

    def axis_factory(key: str) -> FocusAxis:
        return FocusAxis(core, key, allow_motion=args.allow_motion,
                         dry_run=not args.allow_motion)

    records: list[dict] = []
    reference: dict | None = None
    try:
        if args.light_device == "Aura":
            light_on(core, args.light_device, args.line, args.level)
            print(f"\nlight ON: {args.line} {args.level}/1000", flush=True)
        else:
            light_on_transmitted(core, args.level)
            print(f"\nlight ON: transmitted DiaLamp {args.level}%", flush=True)

        last_focus_z: float | None = None
        for i, key in enumerate(order):
            if i > 0:
                # Retract BEFORE the rotation. The stand runs no escape, so the
                # incoming lens arrives at whatever Z the outgoing one was at.
                try:
                    axis_factory(order[i - 1]).move_to(ROTATE_Z_UM)
                except FocusError as exc:
                    print(f"\nREFUSED while retracting to rotate: {exc}", flush=True)
                    break
                crossing = (None if immersions.get(key) == immersions.get(order[i - 1])
                            else f"{immersions.get(order[i-1])} -> {immersions.get(key)}")
                prompt_rotate(key, positions.get(key), order[i - 1],
                              crossing, args.no_prompt)

                # Where to come back to. NOT the near edge of the sample window:
                # at high NA the searchable span is smaller than the window is
                # wide -- +/-52 um of WD budget at 100x Oil against a 400 um
                # window -- so a sweep centred on 2800 cannot reach a sample
                # plane at 2959 and would honestly report "no interior peak".
                #
                # The previous lens's focus is the right centre, and using it is
                # not a shortcut: it is the whole reason the sequence starts at
                # low magnification, where +/-150 um sweeps are safe. Every lens
                # after the first inherits a plane already found.
                target_center = last_focus_z if last_focus_z is not None else RETURN_Z_UM
                ax = axis_factory(key)
                fwd_in = free_working_distance_um(key)
                backoff = max(0.5 * fwd_in, 5.0)
                arrive_at = max(ax.z_floor_um,
                                min(target_center - backoff, ax.z_ceiling_um))
                print(f"\n  returning to {arrive_at:.3f} um -- {backoff:.0f} um "
                      f"retracted from the {('previous focus at ' + format(last_focus_z, '.3f')) if last_focus_z is not None else 'window edge'}"
                      f" um, i.e. half of {key}'s {fwd_in:.0f} um working distance.",
                      flush=True)
                if last_focus_z is not None and 2.0 * fwd_in < (
                        SAMPLE_Z_WINDOW_UM[1] - SAMPLE_Z_WINDOW_UM[0]):
                    print(f"     ({key} cannot be blind-searched: its whole WD is "
                          f"{fwd_in:.0f} um against a {SAMPLE_Z_WINDOW_UM[1]-SAMPLE_Z_WINDOW_UM[0]:.0f} um\n"
                          f"      sample window. If the sweep finds no interior peak, "
                          f"the parfocal offset\n      exceeds the budget -- re-centre "
                          f"with --z-center in steps, do not widen blindly.)",
                          flush=True)
                try:
                    ax.move_to(arrive_at, allow_ascent_um=arrive_at + 1.0)
                except FocusError as exc:
                    print(f"\nREFUSED while returning after rotation: {exc}", flush=True)
                    break

            per_obj_args = argparse.Namespace(**vars(args))
            if i > 0:
                # Centre the sweep on the inherited plane, not on wherever the
                # return move happened to stop.
                per_obj_args.z_center = (last_focus_z if last_focus_z is not None
                                         else None)
            try:
                rec = measure_one(core, axis_factory, key, per_obj_args, reference)
            except FocusError as exc:
                print(f"\nREFUSED at {key}: {exc}", flush=True)
                break
            rec["visit_index"] = i
            rec["is_loop_closure"] = (i == len(order) - 1 and not args.no_close_loop)
            if args.calibrate_xy and args.allow_motion:
                rec["xy_calibration"] = calibrate_stage_to_camera(
                    core, make_grab(core), args.calibrate_xy)
            # Chain the correlation reference to the lens just measured, so the
            # next rescale is between ADJACENT magnifications. In centroid mode
            # each frame is located absolutely, so only the first is kept (it
            # costs nothing and makes the two modes' bookkeeping identical).
            if "frame" in rec and (args.locate == "correlate" or reference is None):
                reference = {"pixel_um": rec["pixel_um"], "frame": rec["frame"],
                             "offset_um": rec.get("fiducial_offset_um") or [0.0, 0.0],
                             "objective_key": key}
            records.append(rec)
            if rec.get("z_focus_um") is not None:
                # The plane the NEXT lens inherits. Deliberately not updated on a
                # failed focus: carrying a stale-but-real plane forward is better
                # than centring the next sweep on a lens that never focused.
                last_focus_z = rec["z_focus_um"]
    except KeyboardInterrupt:
        print("\ninterrupted", flush=True)
    finally:
        light_off(core, args.light_device)
        print("\nlight OFF", flush=True)

    return report(records, args, keys)


def report(records: list[dict], args, keys: list[str]) -> int:
    ok = [r for r in records if r.get("z_focus_um") is not None]
    if not ok:
        print("\nno objective yielded a focus. Nothing to offset.", flush=True)
        return 1

    print("\n" + "=" * 78, flush=True)
    print("PER-OBJECTIVE", flush=True)
    print("=" * 78, flush=True)
    print(f"{'objective':10s} {'visit':>5s} {'focus Z um':>12s} "
          f"{'x um':>9s} {'y um':>9s} {'um/px':>8s}", flush=True)
    for r in records:
        off = r.get("fiducial_offset_um") or [float("nan")] * 2
        z = r.get("z_focus_um")
        print(f"{r['objective_key']:10s} {r['visit_index']:5d} "
              f"{'--' if z is None else f'{z:12.3f}'} "
              f"{off[0]:9.3f} {off[1]:9.3f} {r['pixel_um']:8.4f}"
              + ("   <- loop closure" if r.get("is_loop_closure") else ""), flush=True)

    # ---- loop closure: the bound on everything below --------------------
    closure = None
    first = next((r for r in ok if r["visit_index"] == 0), None)
    last = next((r for r in ok if r.get("is_loop_closure")), None)
    print("\n" + "=" * 78, flush=True)
    print("LOOP CLOSURE -- the uncertainty on every offset", flush=True)
    print("=" * 78, flush=True)
    if first is None or last is None:
        print("  NOT MEASURED. Without it these offsets have no error bar: each one "
              "is a\n  difference across a full Z retract-and-return, and ZDrive's "
              "return\n  repeatability has never been measured on this stand.", flush=True)
    else:
        dz = last["z_focus_um"] - first["z_focus_um"]
        closure = {"dz_um": dz}
        print(f"  {first['objective_key']} measured twice, either side of "
              f"{len(ok) - 1} objective change(s):", flush=True)
        print(f"    focus Z  {first['z_focus_um']:.3f} -> {last['z_focus_um']:.3f} um"
              f"   =>  dz = {dz:+.3f} um", flush=True)
        if first.get("fiducial_offset_um") and last.get("fiducial_offset_um"):
            dx = last["fiducial_offset_um"][0] - first["fiducial_offset_um"][0]
            dy = last["fiducial_offset_um"][1] - first["fiducial_offset_um"][1]
            closure.update({"dx_um": dx, "dy_um": dy})
            print(f"    fiducial ({dx:+.3f}, {dy:+.3f}) um", flush=True)
        print(f"\n  Read every offset below as +/- these numbers. An offset smaller "
              f"than the\n  closure is not a measurement.", flush=True)

    # ---- the offsets ----------------------------------------------------
    ref = first or ok[0]
    print("\n" + "=" * 78, flush=True)
    print(f"OFFSETS relative to {ref['objective_key']}", flush=True)
    print("=" * 78, flush=True)
    print("  dz > 0 means the incoming lens focuses at a HIGHER ZDrive, i.e. closer "
          "to\n  the sample (Z_RETRACT_DIRECTION = -1). dx/dy are CAMERA um"
          + (" and stage um." if args.calibrate_xy else
             "; pass --calibrate-xy to also get the stage move that applies them.")
          + "\n", flush=True)
    print(f"{'objective':10s} {'dz um':>9s} {'dx um':>9s} {'dy um':>9s}", flush=True)
    offsets: dict[str, dict] = {}
    for r in ok:
        if r is ref or r.get("is_loop_closure"):
            continue
        dz = r["z_focus_um"] - ref["z_focus_um"]
        entry: dict = {"dz_um": dz}
        dx = dy = float("nan")
        if r.get("fiducial_offset_um") and ref.get("fiducial_offset_um"):
            dx = r["fiducial_offset_um"][0] - ref["fiducial_offset_um"][0]
            dy = r["fiducial_offset_um"][1] - ref["fiducial_offset_um"][1]
            entry.update({"dx_camera_um": dx, "dy_camera_um": dy})
            cal = r.get("xy_calibration")
            if cal:
                inv = np.asarray(cal["camera_px_to_stage_um"], dtype=float)
                px = np.array([dx / r["pixel_um"], dy / r["pixel_um"]])
                sx, sy = inv @ px
                entry.update({"dx_stage_um": float(sx), "dy_stage_um": float(sy)})
        offsets[r["objective_key"]] = entry
        print(f"{r['objective_key']:10s} {dz:9.3f} {dx:9.3f} {dy:9.3f}"
              + (f"   stage ({entry['dx_stage_um']:+.3f}, {entry['dy_stage_um']:+.3f})"
                 if "dx_stage_um" in entry else ""), flush=True)

    if closure and abs(closure["dz_um"]) > 0:
        marginal = [k for k, v in offsets.items()
                    if abs(v["dz_um"]) <= abs(closure["dz_um"])]
        if marginal:
            print(f"\n  !! {', '.join(marginal)}: |dz| is within the loop closure. "
                  f"Those lenses are\n     parfocal to the resolution of this "
                  f"measurement -- report that, not a number.", flush=True)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        stem = f"objective-offsets-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        payload = {
            "utc": datetime.now(timezone.utc).isoformat(),
            "cfg": args.cfg, "objectives": keys,
            "reference": ref["objective_key"],
            "locate_mode": args.locate,
            "line": args.line, "level_per_mille": args.level,
            "exposure_ms": args.exposure_ms,
            "loop_closure": closure,
            "offsets": offsets,
            "records": [{k: v for k, v in r.items() if k != "frame"} for r in records],
            "caveat": (
                "dx/dy are camera-frame um unless dx_stage_um is present. Every dz "
                "spans a Z retract-and-return, so loop_closure bounds it."
            ),
        }
        (out / f"{stem}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {out / stem}.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
