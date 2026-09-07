r"""Target the brightest reachable, isolated bead on Kinetix_red and trap it.

    python config/session/trap_brightest.py --plan          # picks a target, sends nothing
    python config/session/trap_brightest.py --run
    python config/session/trap_brightest.py --run --ramp-to-origin

WHAT MAKES THIS POSSIBLE WITHOUT A BEAD ALREADY IN THE TRAP
-----------------------------------------------------------
Choosing WHICH bead to grab needs the pixel -> trap-um transform, and until
2026-09-06 that carried an unmeasured scale. Three facts closed it, and none of
them needs a trapped bead:

  origin       the addressable square is CENTRED on the camera field (operator,
               2026-09-06), so trap (0,0) is the field centre -- independently
               MEASURED as TRAP_ORIGIN_OFFSET_UM = (-1.013, -1.015) um over
               five holds on 2026-09-04, which agrees to about a micrometre.
  orientation  the square is square, so one scale serves both axes; handedness
               -1 (image y runs down) was confirmed by four ramps in four
               quadrants all following home at 98.6-99.8%.
  scale        the Tweez software commands MICROMETRES AT THE SAMPLE, so
               trap um -> image um is 1:1 and the pixel size is the whole
               conversion.

    px = p0 + diag([1, -1]) / um_per_px @ um

Binning is not an obstacle: it changes um_per_px and nothing else.

WHY "BRIGHTEST" IS NOT THE ONLY CRITERION
-----------------------------------------
Two more filters apply before brightness, and both would otherwise cost a
grab:

  REACHABLE   |x| and |y| <= 40 um, the half-extent of the addressable square
              at 100x. A point commanded outside is CLIPPED TO THE EDGE
              SILENTLY and returns 0 like everything else on this interface
              (SAFETY.md §0), so the trap would land somewhere it was not asked
              to go and grab whatever is there. Measured live 2026-09-06: only
              5 of 47 detected beads were inside the square, and the BRIGHTEST
              one sat at (-26.5, +43.1) um -- outside on y. So this filter is
              not hypothetical; it changes the answer.
  ISOLATED    nearest neighbour at least --isolation-um away, default 12 um,
              the figure trap_sequence.py uses. It is set by localization
              geometry rather than hydrodynamics: the bead disc is ~27 px in
              radius at 0.065 um/px, so a centroid window big enough to hold
              one cannot exclude a closer neighbour. A close pair also risks
              being caught together, which reads as one very bright bead.

ORDER OF OPERATIONS, AND WHY TRAP_OFF COMES FIRST
-------------------------------------------------
    TRAP_OFF -> TRAP_POSITION(target) -> TRAP_ON

Position BEFORE turning on, always. The other order leaves the beam wherever
the trap was last -- (0,0) on a fresh run, the previous bead on a repeat -- and
then sweeps a LIVE trap across the field to the target, grabbing whatever it
crosses on the way. trap_sequence.py states the same rule for the same reason.

The leading TRAP_OFF is a deliberate release of whatever is held, not tidying
up: SAFETY.md §1 forbids sending TRAP_OFF "merely to release the camera or to
tidy up on exit", and this is the sanctioned case rather than that one --
trap_sequence.py sends it explicitly at stage 1 and on restart, calling it "the
honest release", because it lets a held bead go where it is instead of dragging
it to wherever the next target happens to be.

TRAP STRENGTH IS NOT OPTIONAL
-----------------------------
`SIMPLE_TRAP_CREATE` does not give you a trap at full strength, and a trap at
zero strength accepts `TRAP_POSITION` and `TRAP_ON` and answers 0 to both while
holding nothing whatsoever. Three catches failed on 2026-09-06 before this was
sent: the transform was right, the target was right, the commands all returned
0, and there was simply no trap. `TRAP_STRENGTH` goes before `TRAP_ON`.

That is the same lesson as SAFETY.md §0 in a new place -- the interface answers
0 for "accepted", and the list of things it will accept while doing nothing is
longer than the manual's.

CONFIRMING THE CATCH -- BY MEASUREMENT, NOT BY RETURN CODE
----------------------------------------------------------
Every command above returns 0 whether or not anything happened. So the catch is
confirmed from the images, by the discriminator trap_sequence.py measured:

  a HELD bead's excursion COLLAPSES. A free 5 um bead near the coverslip
  covers ~350 nm RMS in 1.5 s at the D measured on 2026-09-04
  (0.0395 um^2/s); held ones read 28-61 nm. The threshold is 110 nm entering.

The first GRAB_SETTLE_S = 0.8 s after TRAP_ON is DISCARDED, because the bead is
being pulled INTO the trap from wherever it was and that approach is not
thermal motion in a well. Measured 2026-09-04: two beads were called "still
diffusing" at 208 and 189 nm RMS while in fact held the whole time, purely
because that first second was included.

WHAT IT WILL NOT DO
-------------------
  · no LASER_ON unless --laser-on is passed. SAFETY.md §1 puts arming at the
    GUI with the interlocks in view and run_pattern.py sends it never; the flag
    exists because the operator asked for it on 2026-09-06.
  · no LASER_OFF, and no TRAP_OFF at exit: the trap is LEFT HOLDING. Only the
    Aura illumination is taken down.
  · it does not write ZDrive, the Nosepiece or any COLLISION_DEVICE.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_twocolour.cfg"
LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]
CAM = "Kinetix_red"          # the camera the trap origin was measured on
#: NO MODULE-LEVEL TRAP RANGE, as of 2026-09-06. `--half-range-um` now
#: defaults to None and is resolved from the objective in place through
#: `sort_core.resolve_half_range_um` -> `data/trapping_range.yaml`. The +-40 um
#: that used to sit here is the **100x** figure and this script does not check
#: the objective, so at 40x it was silently the wrong quantity.


def _trap_sequence():
    """The module that owns the measured trap constants."""
    src = REPO / "config" / "tweezers" / "trap_sequence.py"
    spec = importlib.util.spec_from_file_location("_trap_sequence", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_trap_sequence"] = mod        # dataclasses need it registered
    spec.loader.exec_module(mod)
    return mod


def detect(frame, area_px, n_sigma=8.0):
    import cv2

    f32 = frame.astype(np.float32)
    residual = f32 - cv2.GaussianBlur(f32, (0, 0), 15)
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0
    n, labels, stats, cent = cv2.connectedComponentsWithStats(
        (residual > n_sigma * scale).astype(np.uint8), 8)
    lo, hi = area_px
    out = []
    for i in range(1, n):
        area = int(stats[i, 4])
        if not (lo <= area <= hi):
            continue
        sel = labels == i
        out.append({"x": float(cent[i][0]), "y": float(cent[i][1]), "area": area,
                    "flux": float(residual[sel].sum()),
                    "peak": float(residual[sel].max())})
    out.sort(key=lambda d: -d["flux"])
    return out


def px_to_trap_um(px, p0, um_per_px):
    return ((px[0] - p0[0]) * um_per_px, -(px[1] - p0[1]) * um_per_px)


def trap_um_to_px(um, p0, um_per_px):
    return (p0[0] + um[0] / um_per_px, p0[1] - um[1] / um_per_px)


def choose_many(dets, p0, um_per_px, isolation_um, half_um, n_traps,
                collision_um, bead_um, area_tol=1.5):
    """Up to `n_traps` beads: brightest first, none colliding with another pick.

    "Sorted considering particle collision" means two separate constraints, and
    conflating them loses one:

      ISOLATION   a candidate must have no NEIGHBOUR (picked or not) closer
                  than `isolation_um`. This is about DETECTION -- the bead disc
                  is tens of px across, so a centroid window big enough to hold
                  one cannot exclude a closer neighbour, and a close pair reads
                  as a single very bright object.
      COLLISION   two PICKED beads must be at least `collision_um` apart. This
                  is about the beads physically touching: two 5 um spheres
                  collide centre-to-centre at 5 um, so the default is that
                  contact distance plus a margin. Traps hold beads to within
                  their own excursion and the beads still diffuse inside the
                  well, so picking two at 6 um apart invites contact even
                  though neither trap moved.

    Greedy by flux, which is the right shape for this: brightest first, and a
    candidate is dropped if it collides with something already picked. That
    yields the brightest achievable non-colliding set for a monotone objective,
    and it is the ordering the operator asked for.

    ⚠ AND EVERY EXTRA TRAP WEAKENS ALL OF THEM. The AOD time-shares ONE beam
    across the traps, so N traps get about 1/N of the power each and stiffness
    falls with it -- `trapping.cli check --n-traps N` models exactly that. Two
    traps is not two independent tweezers; it is one tweezers doing half the
    job twice. The caller is told the per-trap share rather than left to
    discover it.
    """
    picks, why = [], []
    if not dets:
        return [], "no beads detected"
    iso_px = isolation_um / um_per_px
    coll_px = collision_um / um_per_px

    # ── AREA BOUND: reject aggregates ────────────────────────────────────────
    # Isolation measures the DISTANCE to the nearest neighbour, so it cannot see
    # two beads that are touching -- they merge into one connected component
    # with one centroid, and no neighbour is nearby because the neighbour IS the
    # blob. Sorting by flux then actively PREFERS them, because a doublet is
    # twice as bright as a single bead.
    #
    # Measured 2026-09-06: a pick with area 2972 px and flux 15.4M against a
    # typical 1550 px / 9M -- almost exactly double -- was targeted, and its
    # excursion came out at 272 nm RMS against a 225 nm free expectation. It was
    # a freely diffusing doublet, and the trap did not hold it.
    #
    # The reference is the MEDIAN area of everything detected, not a constant:
    # most objects in the field are single beads, so the median tracks focus,
    # binning and threshold without being told about any of them.
    areas = np.array([d["area"] for d in dets], float)
    med_area = float(np.median(areas))
    lo_area, hi_area = med_area / area_tol, med_area * area_tol

    n_unreach = n_crowded = n_collide = n_aggregate = 0
    for d in dets:                                   # already flux-sorted
        if not (lo_area <= d["area"] <= hi_area):
            n_aggregate += 1
            continue
        u = px_to_trap_um((d["x"], d["y"]), p0, um_per_px)
        if abs(u[0]) > half_um or abs(u[1]) > half_um:
            n_unreach += 1
            continue
        nn = min((math.hypot(d["x"] - o["x"], d["y"] - o["y"])
                  for o in dets if o is not d), default=float("inf"))
        if nn < iso_px:
            n_crowded += 1
            continue
        if any(math.hypot(d["x"] - q["x"], d["y"] - q["y"]) < coll_px for q in picks):
            n_collide += 1
            continue
        picks.append({**d, "trap_um": u, "nn_um": nn * um_per_px})
        if len(picks) >= n_traps:
            break
    for i, q in enumerate(picks, start=1):
        q["trap_rank"] = i
    return picks, (f"{len(picks)} picked from {len(dets)} detected "
                   f"({n_aggregate} outside {lo_area:.0f}-{hi_area:.0f} px "
                   f"(median {med_area:.0f}, aggregates/fragments), "
                   f"{n_unreach} outside the +-{half_um:g} um square, "
                   f"{n_crowded} with a neighbour under {isolation_um:g} um, "
                   f"{n_collide} colliding with an earlier pick under "
                   f"{collision_um:g} um)")


def choose(dets, p0, um_per_px, isolation_um, half_um):
    """Brightest bead that is both reachable and isolated. Returns (pick, why)."""
    if not dets:
        return None, "no beads detected"
    iso_px = isolation_um / um_per_px
    reachable, rejected = [], {"unreachable": 0, "crowded": 0}
    for d in dets:
        u = px_to_trap_um((d["x"], d["y"]), p0, um_per_px)
        if abs(u[0]) > half_um or abs(u[1]) > half_um:
            rejected["unreachable"] += 1
            continue
        nn = min((math.hypot(d["x"] - o["x"], d["y"] - o["y"])
                  for o in dets if o is not d), default=float("inf"))
        if nn < iso_px:
            rejected["crowded"] += 1
            continue
        d = {**d, "trap_um": u, "nn_um": nn * um_per_px}
        reachable.append(d)
    if not reachable:
        return None, (f"none of {len(dets)} beads qualify: "
                      f"{rejected['unreachable']} outside the +-{half_um:g} um square, "
                      f"{rejected['crowded']} with a neighbour closer than "
                      f"{isolation_um:g} um")
    return max(reachable, key=lambda d: d["flux"]), (
        f"{len(reachable)} of {len(dets)} qualify "
        f"({rejected['unreachable']} unreachable, {rejected['crowded']} crowded)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--plan", action="store_true", help="pick a target, send nothing")
    p.add_argument("--run", action="store_true", help="position and TRAP_ON")
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--trap", default="cal-verify")
    p.add_argument("--create", action="store_true", help="SIMPLE_TRAP_CREATE first")
    p.add_argument("--strength", type=float, default=1.0,
                   help="TRAP_STRENGTH per trap, 0-1. NOT optional in practice: a "
                        "freshly created trap does not come at full strength, and a "
                        "trap at zero strength accepts TRAP_POSITION and TRAP_ON and "
                        "returns 0 for both while holding nothing.")
    p.add_argument("--laser-on", action="store_true",
                   help="send LASER_ON. Class-4 1064 nm. Off by default because "
                        "SAFETY.md §1 puts arming at the GUI with the interlocks in "
                        "view; use this only when the operator has said to.")
    p.add_argument("--n-traps", type=int, default=1,
                   help="how many beads to trap. The AOD time-shares ONE beam, so "
                        "N traps get ~1/N of the power each and stiffness falls with "
                        "it (trapping.cli check --n-traps N).")
    p.add_argument("--area-tol", type=float, default=1.5,
                   help="accept a candidate whose blob area is within this factor of "
                        "the frame's MEDIAN area. Rejects touching pairs, which "
                        "isolation cannot see and flux-sorting actively prefers.")
    p.add_argument("--collision-um", type=float, default=8.0,
                   help="minimum centre-to-centre separation between PICKED beads. "
                        "Two 5 um spheres touch at 5 um, so the default leaves a 3 um "
                        "margin for the excursion each keeps inside its own well.")
    p.add_argument("--isolation-um", type=float, default=12.0)
    p.add_argument("--exclude-px", type=float, nargs=2, default=None,
                   metavar=("X", "Y"),
                   help="drop any detection within --exclude-radius-um of this "
                        "pixel before picking -- for skipping a bead already "
                        "found stuck to the coverslip on a previous run")
    p.add_argument("--exclude-radius-um", type=float, default=5.0)
    p.add_argument("--preview-png", default=None, metavar="PATH",
                   help="drop the newest frame here as a PNG, at most 1 Hz, so "
                        "a human can watch the run. Off by default; needs "
                        "pillow, and never fails the run if it cannot write")
    p.add_argument("--half-range-um", type=float, default=None,
                   help="addressable trap half-extent, um. Default: read for the "
                        "objective in place from data/trapping_range.yaml, which "
                        "REFUSES rather than guessing when that objective's extent "
                        "has never been stated (only the 100x has, so far).")
    p.add_argument("--bead-um", type=float, default=5.0)
    p.add_argument("--green", type=int, default=45)
    p.add_argument("--exposure-ms", type=float, default=10.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--hold-frames", type=int, default=30)
    p.add_argument("--min-ramp-um", type=float, default=5.0,
                   help="the ramp test reports nothing below this much travel. A bead "
                        "that started near the origin cannot be dragged anywhere, so "
                        "'followed' and 'stayed' become the same measurement.")
    p.add_argument("--ramp-to-origin", action="store_true",
                   help="after the catch, ramp the bead to (0,0) in <=0.5 um steps "
                        "and check it arrives at p0 -- a test of the whole transform")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    if not (args.plan or args.run):
        p.error("pass --plan (safe) or --run")

    from pymmcore_plus import CMMCorePlus
    from hardware.optical_tweezers import OpticalTweezers, find_gui_port

    TS = _trap_sequence()
    settle_s = float(TS.GRAB_SETTLE_S)
    held_nm = float(TS.HELD_ENTER_NM)
    leave_nm = float(TS.HELD_LEAVE_NM)
    offset = tuple(TS.TRAP_ORIGIN_OFFSET_UM)

    core = CMMCorePlus()
    core.loadSystemConfiguration(args.cfg)
    try:
        core.setConfig("TwoColour", "GreenRed-Widefield")
        core.waitForConfig("TwoColour", "GreenRed-Widefield")
    except ValueError:
        # single_cam_red_noDMD.cfg has no "TwoColour" preset (that lives on
        # dualcam_twocolour.cfg) -- set the same widefield-epi path by hand,
        # the same properties measure_red_bead_em1.py's preflight checks for
        # and fix_path() writes, 2026-09-07.
        core.setProperty("Turret1Shutter", "State", "1")
        core.setProperty("Turret2Shutter", "State", "1")
        core.setProperty("CSUW1-Bright", "BrightFieldPort", "Bright Field")
        core.setStateLabel("FilterTurret1", "1-MXR00724 -Empty")
        core.setProperty("Aura", "GREEN_Intensity", str(int(args.green)))
        core.setProperty("Aura", "GREEN", "1")
        core.setProperty("Aura", "State", "1")
        core.waitForDevice("Aura")
    core.setAutoShutter(False)
    core.setCameraDevice(CAM)
    core.setProperty(CAM, "Binning", args.binning)
    core.clearROI()
    core.setExposure(args.exposure_ms)
    um_per_px = core.getPixelSizeUm()          # includes binning
    w, h = core.getImageWidth(), core.getImageHeight()
    p0 = (w / 2.0 + offset[0] / um_per_px, h / 2.0 + offset[1] / um_per_px)
    r = 0.5 * args.bead_um / um_per_px
    area_px = (max(2, int(0.25 * math.pi * r * r)), int(4.0 * math.pi * r * r))

    print(f"objective {core.getStateLabel('Nosepiece')}, {um_per_px:.4f} um/px "
          f"at bin {args.binning}, frame {w}x{h}", flush=True)
    if args.half_range_um is None:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "_sort_core", str(REPO / "config" / "session" / "sort_core.py"))
        _core = _ilu.module_from_spec(_spec)
        sys.modules["_sort_core"] = _core
        _spec.loader.exec_module(_core)
        args.half_range_um = _core.resolve_half_range_um(core)
        source = "data/trapping_range.yaml, for the objective in place"
    else:
        source = "--half-range-um, overriding the recorded value"
    print(f"trap (0,0) at pixel ({p0[0]:.1f}, {p0[1]:.1f}); addressable square "
          f"+-{args.half_range_um:g} um  [{source}]", flush=True)

    _preview_state = {"last": 0.0}

    def _save_preview(frame):
        """Drop the newest frame to a PNG so a human can watch a run.

        Rate-limited to 1 Hz: the point is "let someone see this happening",
        not a recording, and the ramp loop's own cadence is 0.12 s.

        Never allowed to fail the run. A preview is a courtesy, and on Windows
        the swap below *will* raise PermissionError [WinError 5] whenever a
        reader holds the target open -- measured 2026-09-07, when exactly that
        killed a preview loop mid-acquisition.
        """
        if args.preview_png is None:
            return
        now = time.time()
        if now - _preview_state["last"] < 1.0:
            return
        _preview_state["last"] = now
        try:
            from PIL import Image as _Image
            f = frame.astype(np.float32)
            lo, hi = np.percentile(f, [1, 99.5])
            stretched = np.clip((f - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
            out = Path(args.preview_png)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp.png")
            _Image.fromarray(stretched).save(tmp)
            for _ in range(5):
                try:
                    tmp.replace(out)
                    break
                except PermissionError:
                    time.sleep(0.1)
        except Exception as exc:
            print(f"  (preview not written: {exc})", flush=True)

    def burst(n):
        out = []
        for _ in range(n):
            core.snapImage()
            out.append(np.asarray(core.getImage()))
        _save_preview(out[-1])
        return out

    report = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "um_per_px": um_per_px, "p0_px": list(p0),
              "objective": core.getStateLabel("Nosepiece")}

    try:
        for line in LINES:
            core.setProperty("Aura", line, "0")
            core.setProperty("Aura", f"{line}_Intensity", "0")
        core.setProperty("Aura", "GREEN_Intensity", str(args.green))
        core.setProperty("Aura", "GREEN", "1")
        core.setProperty("Aura", "State", "1")
        core.waitForDevice("Aura")
        time.sleep(0.4)

        dets = detect(burst(5)[-1], area_px)
        if args.exclude_px is not None:
            ex, ey = args.exclude_px
            r_px = args.exclude_radius_um / um_per_px
            before = len(dets)
            dets = [d for d in dets
                    if math.hypot(d["x"] - ex, d["y"] - ey) > r_px]
            print(f"  excluded {before - len(dets)} detection(s) within "
                  f"{args.exclude_radius_um:g} um of ({ex:.1f}, {ey:.1f}) px",
                  flush=True)
        picks, why = choose_many(dets, p0, um_per_px, args.isolation_um,
                                 args.half_range_um, args.n_traps,
                                 args.collision_um, args.bead_um, args.area_tol)
        print(f"\n{why}", flush=True)
        if not picks:
            print("  -> no target. Nothing sent.", flush=True)
            report["verdict"] = f"no target: {why}"
            return 1
        if len(picks) < args.n_traps:
            print(f"  !! only {len(picks)} of the {args.n_traps} traps asked for could "
                  f"be placed\n     without a collision. Proceeding with {len(picks)}.",
                  flush=True)

        print(f"\n  sorted by flux, collision-free at >= {args.collision_um:g} um:",
              flush=True)
        for q in picks:
            print(f"    T{q['trap_rank']}  px ({q['x']:7.1f},{q['y']:7.1f})  "
                  f"trap ({q['trap_um'][0]:+7.2f},{q['trap_um'][1]:+7.2f}) um  "
                  f"flux {q['flux']:11.0f}  area {q['area']:5d}  "
                  f"nn {q['nn_um']:5.1f} um", flush=True)
        if len(picks) > 1:
            sep = min(math.hypot(a["x"] - b["x"], a["y"] - b["y"]) * um_per_px
                      for i, a in enumerate(picks) for b in picks[i + 1:])
            report["closest_pick_pair_um"] = sep
            print(f"    closest pair among the picks: {sep:.1f} um "
                  f"(two 5 um beads touch at 5.0)", flush=True)
            print(f"\n  ⚠ {len(picks)} traps SHARE ONE BEAM. The AOD time-shares it, so "
                  f"each gets about\n     1/{len(picks)} of the power and the stiffness "
                  f"per trap falls with it -- N traps is not\n     N independent "
                  f"tweezers. Model it with:\n     python -m trapping.cli check "
                  f"--n-traps {len(picks)} --radius-um 2.5 --na 1.45 "
                  f"--n-bead 1.57154\n       --n-medium 1.32453 --wavelength-nm 1064 "
                  f"--viscosity-pa-s 0.001002", flush=True)
        report["targets"] = [{"rank": q["trap_rank"], "px": [q["x"], q["y"]],
                              "trap_um": list(q["trap_um"]), "area": q["area"],
                              "nn_um": q["nn_um"]} for q in picks]
        pick = picks[0]
        tx, ty = pick["trap_um"]

        if not args.run:
            print(f"\n--plan: would send TRAP_OFF, TRAP_POSITION {args.trap!r} "
                  f"{tx:.3f} {ty:.3f}, TRAP_ON. Nothing sent.", flush=True)
            return 0

        port = args.port or find_gui_port(host=args.host)
        if port is None:
            print("No Tweez GUI answered on 2070-2075.", file=sys.stderr)
            return 1
        with OpticalTweezers(host=args.host, port=port) as t:
            if not t.is_ready():
                print("Tweez GUI is not ready.", file=sys.stderr)
                return 1
            if args.laser_on:
                # Class-4 1064 nm. Sent only on the operator's explicit
                # instruction (2026-09-06: "you have to set the trap strength
                # and master laser on", then "laser is armed now"). SAFETY.md §1
                # otherwise puts arming at the GUI with the interlocks in view,
                # and run_pattern.py deliberately sends no LASER_ON at all --
                # so this stays behind its own flag rather than becoming the
                # default.
                t.laser_on()
                report["laser_on_sent"] = True
                print("  LASER_ON sent (class-4 1064 nm, on operator instruction)",
                      flush=True)

            names = ([args.trap] if len(picks) == 1
                     else [f"{args.trap}-{q['trap_rank']}" for q in picks])
            report["trap_names"] = names
            report["strength"] = args.strength
            for q, nm in zip(picks, names):
                qx, qy = q["trap_um"]
                if args.create or len(picks) > 1:
                    # Traps ACCUMULATE in the GUI and there is a ceiling. This
                    # script leaves them on by design (SAFETY.md §1: never send
                    # TRAP_OFF to tidy up), so a few runs later
                    # SIMPLE_TRAP_CREATE answers -20 "requested resource not
                    # supported" -- measured 2026-09-06 after earlier runs had
                    # left `cal-verify` plus `cal-verify-1..4` in place. Note it
                    # is -20 and NOT -24 "element already exists", so it is the
                    # trap LIMIT rather than the name that is the problem, and
                    # reusing the name does not help by itself.
                    #
                    # Delete first, then create. TRAP_DELETE on a name that is
                    # not there answers -22 or -25 and is harmless, so this is
                    # idempotent; and deleting a trap THIS script created is not
                    # the "TRAP_OFF to tidy up" that SAFETY.md forbids -- that
                    # rule is about dropping a bead someone is holding.
                    try:
                        t.delete_trap(nm)
                    except Exception:
                        pass
                    try:
                        t.create_simple_trap(nm)
                    except Exception as exc:
                        print(f"  ! SIMPLE_TRAP_CREATE {nm!r}: {exc}", file=sys.stderr)
                        print(f"    proceeding on the assumption the trap exists -- "
                              f"if it does not, TRAP_POSITION\n    and TRAP_ON will "
                              f"still answer 0 and nothing will be held.",
                              file=sys.stderr)
                # STRENGTH BEFORE TRAP_ON, and never skipped. A freshly created
                # trap does not come at full strength, and a trap at zero
                # strength accepts TRAP_POSITION and TRAP_ON and answers 0 to
                # both while holding nothing -- which is precisely what the
                # three failed catches earlier on 2026-09-06 were: the transform
                # was right, the target was right, and there was no trap.
                t.set_trap_strength(nm, args.strength)
                # OFF -> POSITION -> ON, per trap. See the module docstring:
                # turning on first leaves the beam wherever the trap was and
                # then sweeps it across the field, grabbing what it crosses.
                t.trap_off(nm)
                t.set_trap_position(nm, round(qx, 4), round(qy, 4))
                t.trap_on(nm)
                print(f"  T{q['trap_rank']} {nm!r}: STRENGTH {args.strength:g} / "
                      f"TRAP_OFF / TRAP_POSITION({qx:+.3f}, {qy:+.3f}) / TRAP_ON",
                      flush=True)
            print(f"\n  every command returned 0, which means the GUI accepted them "
                  f"and nothing more", flush=True)

            time.sleep(settle_s)
            print(f"  discarded the first {settle_s:g} s (the bead is pulled INTO the "
                  f"trap over that\n  window, which is not thermal motion in a well)",
                  flush=True)

            t_burst = time.perf_counter()
            frames = burst(args.hold_frames)
            burst_s = time.perf_counter() - t_burst
            # The free-bead reference MUST scale with the observation window --
            # sqrt(2*D*t). trap_sequence's "free ~350 nm" is for a 1.5 s window;
            # this burst is ~0.6 s, where free is only ~220 nm. Quoting the
            # 1.5 s figure against a 0.6 s measurement makes every bead look
            # suspiciously still.
            free_nm = math.sqrt(2.0 * 0.0395 * max(burst_s, 1e-3)) * 1000.0
            target_px = trap_um_to_px((tx, ty), p0, um_per_px)
            track = []
            for f in frames:
                ds = detect(f, area_px)
                if not ds:
                    continue
                near = min(ds, key=lambda d: math.hypot(d["x"] - target_px[0],
                                                        d["y"] - target_px[1]))
                if math.hypot(near["x"] - target_px[0], near["y"] - target_px[1]) < \
                        args.isolation_um / um_per_px:
                    track.append((near["x"], near["y"]))

            if len(track) < 5:
                print(f"\n  !! only {len(track)} frames found a bead within "
                      f"{args.isolation_um:g} um of the commanded\n     position. "
                      f"Either the grab missed or the bead left. NOT HELD.", flush=True)
                report["verdict"] = "no bead at the commanded position"
            else:
                arr = np.array(track)
                rms_nm = float(np.sqrt(((arr - arr.mean(axis=0)) ** 2).sum(axis=1).mean())
                               * um_per_px * 1000.0)
                err_um = float(math.hypot(arr[:, 0].mean() - target_px[0],
                                          arr[:, 1].mean() - target_px[1]) * um_per_px)
                report.update({"rms_excursion_nm": rms_nm,
                               "position_error_um": err_um,
                               "n_frames_tracked": len(track)})
                print(f"\n  over {len(track)} frames:", flush=True)
                print(f"    RMS excursion   {rms_nm:7.1f} nm   over {burst_s:.2f} s"
                      f"   (held < {held_nm:g}; free ~{free_nm:.0f} for THIS window)",
                      flush=True)
                print(f"    offset from the commanded position  {err_um:.3f} um",
                      flush=True)
                # Implied stiffness from equipartition, <r^2> = 2kT/kappa in 2D.
                # Printed because it converts an RMS in nm into something with a
                # sanity check attached: this repo's own force curve puts a
                # 5 um PS bead at ~175 pN/um, so an excursion implying a
                # thousandth of that is telling you the bead is not in a trap
                # even when the number looks reassuringly small.
                kT = 1.380649e-23 * 293.15
                # N/m -> pN/um is x1e6 (1e12 pN per N, 1e6 um per m), not x1e-6.
                # The wrong sign of exponent printed 0.00 for every excursion,
                # which is the least useful possible failure: a plausible-looking
                # zero rather than a number that disagrees with the model.
                kappa_pn_um = (2.0 * kT / (rms_nm * 1e-9) ** 2) * 1e6 if rms_nm else 0.0
                report["implied_kappa_pn_um"] = kappa_pn_um
                print(f"    implied stiffness  {kappa_pn_um:8.2f} pN/um   "
                      f"(model says ~175 for this bead)", flush=True)

                # ⚠ THE EXCURSION TEST ASSUMES THE UNTRAPPED POPULATION IS
                # MOBILE, and on 2026-09-06 it was not: 21 tracked beads gave a
                # MEDIAN of 114.9 nm against a 259 nm free expectation, with
                # 8/21 below 110 nm and only 1/21 above 220. Most of the beads
                # were stuck to the coverslip. On a sample like that a "held"
                # reading is indistinguishable from a typical bead and this
                # whole test is blind -- only the ramp (does it FOLLOW?) can
                # tell. Survey the population before trusting any verdict here.
                if held_nm <= rms_nm <= leave_nm:
                    print(f"\n  -> AMBIGUOUS. {rms_nm:.0f} nm sits in the hysteresis "
                          f"band this instrument needs\n     ({held_nm:g}-{leave_nm:g} "
                          f"nm). trap_sequence.py records 55, 152, 61, 155, 143, 151, "
                          f"149 nm\n     in sequence on ONE bead, which is why a single "
                          f"cut flips on noise alone.\n     It is also well below the "
                          f"~310 nm this window would give a free bead, so\n     the "
                          f"bead is NOT simply diffusing.", flush=True)
                    print(f"\n     TWO EXPLANATIONS, AND THE EXCURSION CANNOT SEPARATE "
                          f"THEM:", flush=True)
                    print(f"       weakly held -- but {kappa_pn_um:.2f} pN/um against a "
                          f"modelled ~175 would mean\n                      almost no "
                          f"laser power reaching the trap;", flush=True)
                    print(f"       STUCK to the glass -- a stuck bead reads as still as "
                          f"a trapped one, and\n                      that is exactly "
                          f"what broke the 2026-09-04 catch test.", flush=True)
                    print(f"\n     THE TEST THAT SEPARATES THEM: move the trap and see "
                          f"whether the bead follows.\n     A held bead comes with it, a "
                          f"stuck one stays behind, and it needs no\n     calibration. "
                          f"Re-run with --ramp-to-origin.", flush=True)
                    report["verdict"] = f"ambiguous, {rms_nm:.0f} nm RMS"
                elif rms_nm < held_nm:
                    print(f"\n  -> excursion says HELD ({rms_nm:.0f} < {held_nm:g} nm).",
                          flush=True)
                    print(f"\n     ⚠ BUT ON THIS SAMPLE THAT IS NOT EVIDENCE. The "
                          f"UNTRAPPED population median\n     was 114.9 nm on "
                          f"2026-09-06 (21 beads, 8/21 under 110 nm, only 1/21 over "
                          f"220),\n     because most of the beads are stuck to the "
                          f"coverslip -- see\n     data/particles.yaml > "
                          f"abvigen-red-5um-cooh > sticking. A stuck bead reads as "
                          f"held.\n     So a sub-threshold excursion here says almost "
                          f"nothing, and the implied\n     {kappa_pn_um:.2f} pN/um "
                          f"against a modelled ~175 says the same thing louder.",
                          flush=True)
                    print(f"\n     CONFIRM WITH --ramp-to-origin, which asks the only "
                          f"question that separates\n     them: does the bead FOLLOW "
                          f"the trap?", flush=True)
                    print(f"     And the {err_um:.3f} um offset is a direct check on "
                          f"the transform: the bead\n     sits where the trap was "
                          f"COMMANDED to be, so origin, handedness and\n     scale are "
                          f"all right together. A wrong scale or a flipped axis puts "
                          f"the\n     trap somewhere else and catches nothing.",
                          flush=True)
                    report["verdict"] = f"HELD, {rms_nm:.0f} nm RMS"
                else:
                    print(f"\n  -> NOT HELD: {rms_nm:.0f} nm is free-bead motion. The "
                          f"trap is on and\n     positioned, but this bead is not in "
                          f"it. Check the laser is armed at the\n     GUI -- TRAP_ON "
                          f"returns 0 either way (SAFETY.md §0).", flush=True)
                    report["verdict"] = f"not held, {rms_nm:.0f} nm RMS"

                if args.ramp_to_origin and rms_nm <= leave_nm:
                    print(f"\n  ramping to (0,0) in 0.5 um steps ...", flush=True)
                    n = max(1, int(math.ceil(math.hypot(tx, ty) / 0.5)))
                    for i in range(1, n + 1):
                        t.set_trap_position(args.trap, round(tx * (1 - i / n), 4),
                                            round(ty * (1 - i / n), 4))
                        time.sleep(0.12)
                    time.sleep(settle_s)
                    ds = detect(burst(10)[-1], area_px)
                    if ds:
                        near = min(ds, key=lambda d: math.hypot(d["x"] - p0[0],
                                                                d["y"] - p0[1]))
                        d_um = math.hypot(near["x"] - p0[0], near["y"] - p0[1]) * um_per_px
                        # Did anything stay at the ORIGINAL place? That is the
                        # cleaner half of the test. Arrival at p0 could in
                        # principle be some other bead that happened to sit near
                        # the centre; a bead still at the start after the trap
                        # has left is unambiguous.
                        left_behind = min(
                            (math.hypot(d["x"] - target_px[0], d["y"] - target_px[1])
                             for d in ds), default=float("inf")) * um_per_px
                        moved = math.hypot(tx, ty)
                        report["ramp_arrival_um_from_p0"] = d_um
                        report["ramp_left_behind_um"] = left_behind
                        report["ramp_distance_um"] = moved
                        print(f"    trap travelled {moved:.1f} um to the origin",
                              flush=True)
                        print(f"    nearest bead to p0 is now        {d_um:7.3f} um away",
                              flush=True)
                        print(f"    nearest bead to the START is now {left_behind:7.3f} "
                              f"um away", flush=True)
                        # Thresholds RELATIVE to the distance the trap moved,
                        # not absolute. An absolute 1.5 um cutoff called a bead
                        # sitting 1.525 um from the start "inconclusive" after
                        # the trap had left it by 29.3 um -- 1.5 um is a fifth
                        # of a bead diameter and inside its own wander over the
                        # ramp, so that was plainly "stayed put".
                        stayed = left_behind < max(2.0, 0.15 * moved)
                        arrived = d_um < max(1.5, 0.1 * moved)
                        # ⚠ THE TEST NEEDS ROOM. If the bead started near the
                        # origin the trap barely moves, and then "followed" and
                        # "stayed" are the same measurement: the bead is within
                        # the travel distance of BOTH places. Measured
                        # 2026-09-06: a pick at trap (+1.25, -0.07) gave a
                        # 1.3 um ramp, and the thresholds duly returned STUCK on
                        # a bead that had nowhere to be dragged to. Below a bead
                        # diameter of travel this reports nothing.
                        if moved < args.min_ramp_um:
                            print(f"\n    -> NOT A TEST. The trap only moved "
                                  f"{moved:.1f} um, under the {args.min_ramp_um:g} um "
                                  f"this\n       needs to discriminate: the bead "
                                  f"started {moved:.1f} um from the origin, so "
                                  f"'followed'\n       and 'stayed' are within each "
                                  f"other's error. It says nothing about whether\n"
                                  f"       the bead is held. Re-run -- the picks move "
                                  f"as the beads diffuse -- or\n       target one "
                                  f"further out.", flush=True)
                            report["verdict"] = (f"ramp uninformative: only "
                                                 f"{moved:.1f} um of travel")
                        elif arrived and not stayed:
                            print(f"\n    -> IT FOLLOWED, so it was HELD, not stuck. "
                                  f"And since the origin needs no\n       calibration, "
                                  f"arriving there confirms the whole transform at "
                                  f"once.", flush=True)
                            report["verdict"] = "HELD -- followed the ramp to the origin"
                        elif stayed:
                            print(f"\n    -> IT STAYED PUT. A bead is still sitting at "
                                  f"the start while the trap has\n       moved "
                                  f"{moved:.1f} um away, so it is STUCK TO THE "
                                  f"COVERSLIP, not trapped. Its\n       small excursion "
                                  f"was adhesion, not confinement -- which is exactly "
                                  f"the\n       failure mode that broke the 2026-09-04 "
                                  f"catch test, and exactly why the\n       excursion "
                                  f"test alone cannot be trusted.", flush=True)
                            report["verdict"] = "STUCK -- did not follow the trap"
                        else:
                            print(f"\n    -> INCONCLUSIVE: nothing at the origin and "
                                  f"nothing at the start. The bead may\n       have "
                                  f"been dropped mid-ramp, which happens if a step "
                                  f"exceeds the ~2.3 um\n       capture range or if the "
                                  f"trap is too weak to overcome drag.", flush=True)
                            report["verdict"] = "inconclusive ramp"
    finally:
        for line in ("CYAN", "GREEN"):
            try:
                core.setProperty("Aura", line, "0")
                core.setProperty("Aura", f"{line}_Intensity", "0")
            except Exception:
                pass
        try:
            core.setProperty("Aura", "State", "0")
        except Exception:
            pass
        print("\nillumination OFF. Trap and laser LEFT ON (SAFETY.md §1).", flush=True)

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "trap_brightest.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"report: {outdir / 'trap_brightest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
