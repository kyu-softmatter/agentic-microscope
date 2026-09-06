r"""Which emission band does the Abvigen red bead actually emit in?

    python config/session/measure_red_bead_em1.py --intensity 50 --exposure-ms 33.33
    python config/session/measure_red_bead_em1.py --intensity 50 --dry-run   # no light, no writes

THE QUESTION
------------
`data/particles.yaml > abvigen-red-5um-cooh` carries the vendor's 620/680 nm
ex/em, and the 2026-09-05 on-instrument measurement DISPROVES the excitation
half: the observed ordering was GREEN > CYAN >> RED, with RED producing nothing,
which is the reverse of what a 620 nm excitation peak predicts. That fits a
rhodamine/TRITC-class dye excited near 530-560 nm -- and if the excitation is
wrong, the 680 nm emission figure from the same page is in doubt too.

Two emission filters in the EM1 wheel bracket the two hypotheses:

    position 3  label "555"   FF01-595/31   579.5-610.5 nm   -> TRITC-class
    position 4  label "647"   FF01-680/42   659.0-701.0 nm   -> vendor's 680

MXR00724-EM passes BOTH bands (589-623 and 677-711), so the cube does not
prejudge the answer. This script excites with one line, images the same field
through both filters, and returns the ratio. That ratio replaces a guess in
`data/fluorophores.yaml > AbvigenRed680` -- an entry currently built on two
published peaks, one of which is already known to be wrong, its name included.

WHY THE ORDER IS 555 -> 647 -> 555
----------------------------------
A single pass cannot tell a filter difference from photobleaching or focus
drift: both would make the second measurement dimmer whatever the dye does. So
position 3 is measured twice, bracketing position 4, and the 555b/555a ratio
bounds everything that changed with TIME rather than with the FILTER. If that
bracket is not close to 1, the 647/555 ratio is not interpretable and the script
says so instead of reporting a number.

WHAT IT WRITES TO THE INSTRUMENT
--------------------------------
Only three things: `CSUW1-Filter_Red` state, the light engine's line and
intensity, and the camera's exposure/ROI. Nothing else -- and in particular
nothing in `hardware.microscope.COLLISION_DEVICES` (Nosepiece, ZDrive,
PFSOffset), which are read and reported but never written (SAFETY.md §2). The
objective must already be the one you want, changed at the stand.

Light is OFF unless `--intensity` is given, autoshutter is turned off so the
state is exactly what was asked for, and the `finally` block takes the line down
and restores the filter wheel. Per SAFETY.md §6, intensity is PER-MILLE (0-1000)
-- 50 is 5%.

PREFLIGHT
---------
The path state below is checked before any light goes on, because each of these
has already cost a session:

  Turret1Shutter / Turret2Shutter   in series; either closed = a black frame
                                    (SAFETY.md §5, cost two live-view sessions)
  LightPath = 3 (L100)              the port the cameras are on (2026-09-04)
  CSUW1-Bright = Bright Field       disk bypassed, for widefield
  CSUW1-Port = red_only             everything to Kinetix_red
  FilterTurret1 = MXR00724          the 5-band cube; its 589-623 and 677-711
                                    bands are what make this test symmetric
  camera PP entries                 despeckle OFF, or ADU is not proportional
                                    to electrons and the frame is unusable
                                    (docs/06 C1, validity G26)

A failed preflight refuses by default. `--force` proceeds anyway and stamps the
report `preflight_forced: true`, because a measurement taken over a warning
should say so in the file rather than in somebody's memory.

Run with `--dry-run` first: it does the preflight, prints the state, and exits
without enabling light or moving the wheel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CFG = REPO / "config" / "micromanager" / "single_cam_red_noDMD.cfg"

# Never written. Read and reported only -- SAFETY.md §2, and
# hardware.microscope.COLLISION_DEVICES says the same thing to the config layer.
COLLISION_DEVICES = ("Nosepiece", "ZDrive", "PFSOffset")

# (device, property-or-None, expected, why it matters)
#
# ⚠ The expected value is whatever the device ANSWERS WITH, which for a Ti2
# turret is Nikon's 1-indexed label and not MMCore's 0-indexed state. LightPath
# at the cameras' port reads `State = 3` and `Label = "4-L100"`; comparing the
# label against "3" reports a false failure, which this table did on its first
# run (2026-09-06). Where a device is not a state device at all -- CSUW1-Bright
# carries `BrightFieldPort`, IntermediateMagnification carries a read-only
# `Magnification` -- the property is named explicitly instead.
PREFLIGHT = [
    ("Turret1Shutter", "State", "1", "in series with Turret2Shutter; either closed = black frame"),
    ("Turret2Shutter", "State", "1", "in series with Turret1Shutter; also the 1064 nm path"),
    ("LightPath", "Label", "4-L100", "L100 -- the port the CSU-W1 and both cameras are on"),
    ("CSUW1-Bright", "BrightFieldPort", "Bright Field", "disk bypassed for widefield epi"),
    ("CSUW1-Port", "Label", "red_only", "send all emission to Kinetix_red"),
    ("CSUW1-Dichroic", "Label", "on", "the Di01-T405/488/568/647 quad dichroic, in path"),
    ("FilterTurret1", None, "1-MXR00724 -Empty", "the 5-band cube -- passes 589-623 AND 677-711"),
]

# What `--fix-path` is allowed to write, and whether it may be put back.
# CSUW1-Port is restored; the turret shutters are NOT -- SAFETY.md §8 "Never
# close Turret2Shutter to tidy up", because it is also the 1064 nm path and a
# trap may depend on it staying open.
FIXABLE = [
    ("Turret1Shutter", "State", "1", False),
    ("Turret2Shutter", "State", "1", False),
    ("CSUW1-Port", "Label", "red_only", True),
]


def _state_label(core, device: str) -> str:
    try:
        return str(core.getStateLabel(device))
    except Exception:
        try:
            return f"State-{core.getState(device)}"
        except Exception:
            return "<unreadable>"


def preflight(core, camera: str) -> tuple[list[str], dict]:
    """Read the path state. Returns (problems, observed) and writes nothing."""
    problems: list[str] = []
    observed: dict = {}

    for device, prop, expected, why in PREFLIGHT:
        try:
            actual = core.getProperty(device, prop) if prop else _state_label(core, device)
        except Exception as exc:
            observed[device] = f"<error: {exc}>"
            problems.append(f"{device}: could not be read ({exc}) -- {why}")
            continue
        observed[device] = str(actual)
        if str(actual) != expected:
            problems.append(f"{device} = {actual!r}, expected {expected!r} -- {why}")

    # Collision devices: reported so the report records which objective the
    # numbers belong to. Read-only; getStateLabel is a table lookup and
    # getPosition reads a stage. Neither writes (SAFETY.md §2).
    observed["Nosepiece"] = _state_label(core, "Nosepiece")
    for device in ("ZDrive", "PFSOffset"):
        try:
            observed[device] = f"{core.getPosition(device):.3f} um"
        except Exception as exc:
            observed[device] = f"<error: {exc}>"

    # The intermediate turret is READ-ONLY over MM -- it has one property,
    # `Magnification`, and no way to set it. So 1.0x vs 1.5x is a manual change
    # at the stand, and the pixel size follows it (data/pixel_size.yaml).
    for device, prop in (("IntermediateMagnification", "Magnification"),
                         ("PFS", "PFS in Range"),
                         ("PFS", "FocusMaintenance")):
        try:
            observed[f"{device}.{prop}"] = str(core.getProperty(device, prop))
        except Exception as exc:
            observed[f"{device}.{prop}"] = f"<error: {exc}>"

    # Camera post-processing. Despeckle breaks ADU -> electron proportionality
    # and the frame cannot be repaired afterwards (docs/06 C1).
    pp: dict[str, str] = {}
    for name in core.getDevicePropertyNames(camera):
        if "-PP" in name or "PP " in name or "Despeckle" in name:
            try:
                pp[name] = str(core.getProperty(camera, name))
            except Exception as exc:
                pp[name] = f"<error: {exc}>"
    observed["camera_pp"] = pp
    for name, value in pp.items():
        if "ENABLED" in name.upper() and str(value).strip().lower() in {"yes", "1", "true", "on"}:
            problems.append(
                f"{name} = {value!r} -- camera post-processing is ON. Despeckle "
                "replaces threshold-crossing pixels, so ADU is no longer "
                "proportional to electrons (docs/06 C1). Turn all PP entries off."
            )

    for prop in ("Binning", "PixelType", "ReadoutRate", "Gain", "Port"):
        try:
            observed[f"camera.{prop}"] = str(core.getProperty(camera, prop))
        except Exception:
            pass
    if observed.get("camera.Binning", "1x1") not in {"1x1", "1"}:
        problems.append(f"camera Binning = {observed['camera.Binning']!r}, expected 1x1")

    return problems, observed


def fix_path(core) -> tuple[dict, list[tuple[str, str, str]]]:
    """Write the FIXABLE path state. Returns (what changed, what to restore)."""
    changed: dict = {}
    restore: list[tuple[str, str, str]] = []
    for device, prop, want, restorable in FIXABLE:
        try:
            before = str(core.getProperty(device, prop))
        except Exception as exc:
            print(f"  ! {device}.{prop} unreadable ({exc}) -- not touched", file=sys.stderr)
            continue
        if before == want:
            continue
        core.setProperty(device, prop, want)
        core.waitForDevice(device)
        changed[f"{device}.{prop}"] = {"was": before, "now": want, "restored_after": restorable}
        if restorable:
            restore.append((device, prop, before))
        print(f"  {device}.{prop}: {before!r} -> {want!r}"
              + ("" if restorable else "   (left as-is afterwards, SAFETY.md §8)"))
    return changed, restore


def disable_pp(core, camera: str) -> dict:
    """Turn every camera post-processing ENABLED entry off.

    Not restored afterwards, deliberately. Despeckle-on is not a setting to be
    polite about: it replaces threshold-crossing pixels with a neighbour value,
    so ADU stops being proportional to electrons and the frame cannot be
    repaired later (docs/06 C1, validity G26). Off is the correct state for
    every quantitative acquisition on this instrument, so this leaves it off
    and records what it found.
    """
    changed: dict = {}
    for name in core.getDevicePropertyNames(camera):
        # `startswith("PP")`, not `"ENABLED" in name` -- the loose test also
        # matches `CircularBufferEnabled`, which this function has no business
        # touching and switched off on its first run (2026-09-06). It is the
        # acquisition buffer, not post-processing.
        if not name.startswith("PP") or "ENABLED" not in name.upper():
            continue
        try:
            before = str(core.getProperty(camera, name))
        except Exception:
            continue
        if before.strip().lower() in {"no", "0", "false", "off"}:
            continue
        allowed = list(core.getAllowedPropertyValues(camera, name)) or ["No"]
        off = next((v for v in allowed if str(v).strip().lower() in {"no", "0", "false", "off"}), "No")
        try:
            core.setProperty(camera, name, off)
            changed[name] = {"was": before, "now": str(core.getProperty(camera, name))}
            print(f"  {name}: {before!r} -> {changed[name]['now']!r}")
        except Exception as exc:
            print(f"  ! could not turn off {name}: {exc}", file=sys.stderr)
    return changed


def burst(core, camera: str, n_frames: int) -> np.ndarray:
    """`n_frames` snaps as a float64 stack. Snap, not a sequence acquisition:
    this measures brightness, not timing, and snapImage is the path with no
    intervalMs lie in it (SAFETY.md §7)."""
    frames = []
    for _ in range(n_frames):
        core.snapImage()
        frames.append(np.asarray(core.getImage(), dtype=np.float64))
    return np.stack(frames)


def light(core, device: str, line: str, per_mille: int) -> None:
    """Enable one line on a Lumencor engine.

    ⚠ THREE properties, not two. `<LINE>` and `<LINE>_Intensity` select and
    level the line, but the engine also has a master `State` (0/1) which is its
    shutter -- and with `State = 0` nothing comes out however the line is set.
    The first run of this script (2026-09-06) set only the first two, got a
    field indistinguishable from a dark frame, and the ratio it printed was
    computed on the camera's own hot pixels. `Core.Shutter` is `LightEngine`
    (the SpectraIII), not `Aura`, so autoshutter never opens this engine
    either -- and autoshutter is off here by design (SAFETY.md §6).
    """
    core.setProperty(device, f"{line}_Intensity", str(int(per_mille)))
    core.setProperty(device, line, "1" if per_mille > 0 else "0")
    core.setProperty(device, "State", "1" if per_mille > 0 else "0")
    core.waitForDevice(device)


def light_off(core, device: str, line: str) -> None:
    # Master State first, then the line, then the level: each step alone leaves
    # the sample darker than the step before, so a failure part-way through
    # cannot leave the engine brighter than intended.
    for prop, value in (("State", "0"), (line, "0"), (f"{line}_Intensity", "0")):
        try:
            core.setProperty(device, prop, value)
        except Exception as exc:  # keep going -- the other steps still matter
            print(f"  ! could not set {device}.{prop} = {value}: {exc}", file=sys.stderr)


def _local_residual(frame: np.ndarray, sigma: float = 15.0) -> tuple[np.ndarray, float]:
    """Frame minus its own smooth part, plus a robust noise scale.

    The subtraction is what makes the comparison trustworthy. A global
    threshold on a 4x field selects the ILLUMINATION SHAPE -- on 2026-09-06 it
    took in 6.6% of the frame, where 12,800 five-micron beads at 1.625 um/px
    cover about 4%. Worse, the smooth part is not the same in the two filter
    bands (median 166 ADU through 555 against 112 through 647), so a global
    mask silently compares different things. Removing each frame's own smooth
    part leaves the compact objects, and makes every number below independent
    of both the illumination profile and the camera offset -- which matters
    here because the dark frame's baseline was still settling.
    """
    import cv2

    smooth = cv2.GaussianBlur(frame.astype(np.float32), (0, 0), sigma)
    residual = frame - smooth
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826
    return residual, scale or 1.0


def bead_mask(
    stacks: dict[str, np.ndarray],
    dark_mean: np.ndarray,
    n_sigma: float = 8.0,
    area_px: tuple[int, int] = (2, 40),
) -> tuple[np.ndarray, dict]:
    """Pixels belonging to compact objects present in BOTH 555 passes.

    Three filters, each removing a way to be fooled:

      compact      2-40 px, so an illumination gradient cannot qualify. A 5 um
                   bead is ~3 px across at 4x (1.625 um/px), ~7 px in area.
      not hot      a pixel that is also compact-and-bright in the DARK frame is
                   the sensor's, not the sample's. The first run's ratio was
                   computed almost entirely on these.
      reproducible present in 555a AND 555b. A one-pass detection cannot
                   distinguish a bead from a cosmic ray or a noise excursion.

    The mask is built from the 555 frames on purpose, never from 647: if the
    647 hypothesis is the wrong one, a mask built there is pure noise. Building
    it from the brighter band and then MEASURING both bands on those same
    pixels is what keeps the ratio meaningful when one band is near zero.
    """
    import cv2

    dark_residual, dark_scale = _local_residual(dark_mean)
    hot = dark_residual > n_sigma * dark_scale

    lo, hi = area_px
    masks: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    on_hot = 0
    for tag in ("555a", "555b"):
        residual, scale = _local_residual(stacks[tag].mean(axis=0))
        n, labels, stats_, _ = cv2.connectedComponentsWithStats(
            (residual > n_sigma * scale).astype(np.uint8), 8
        )
        areas = stats_[1:, 4]
        keep = np.flatnonzero((areas >= lo) & (areas <= hi)) + 1
        # Vectorised: a per-label `in set(...)` test is quadratic and hung for
        # >300 s on 12,800 objects the first time this was written.
        hot_labels = np.unique(labels[hot])
        clean = np.setdiff1d(keep, hot_labels, assume_unique=False)
        on_hot += int(len(keep) - len(clean))
        masks[tag] = np.isin(labels, clean)
        counts[tag] = int(len(clean))

    mask = masks["555a"] & masks["555b"]
    union = masks["555a"] | masks["555b"]
    info = {
        "objects_555a": counts["555a"],
        "objects_555b": counts["555b"],
        "objects_on_hot_px": on_hot,
        "mask_px": int(mask.sum()),
        "mask_frac": float(mask.mean()),
        "reproducible_frac": float(mask.sum() / union.sum()) if union.any() else 0.0,
        "n_sigma": n_sigma,
        "area_px": list(area_px),
    }
    return mask, info


def stats(stack: np.ndarray, offset: float, mask: np.ndarray | None) -> dict:
    mean_frame = stack.mean(axis=0)
    out = {
        "n_frames": int(stack.shape[0]),
        "max_adu": float(mean_frame.max()),
        "p99_99_adu": float(np.percentile(mean_frame, 99.99)),
        "p99_9_adu": float(np.percentile(mean_frame, 99.9)),
        "median_adu": float(np.median(mean_frame)),
        "clipped_px": int((stack >= 65535).sum()),
    }
    out["background_minus_offset"] = out["median_adu"] - offset
    out["peak_minus_offset"] = out["max_adu"] - offset
    if mask is not None and mask.any():
        # Measured against each frame's OWN smooth part, not against a global
        # median or the dark offset -- see _local_residual for why both of
        # those bias the comparison between the two filter bands.
        residual, scale = _local_residual(mean_frame)
        out["mask_px"] = int(mask.sum())
        out["mask_mean_minus_background"] = float(residual[mask].mean())
        out["mask_residual_sd"] = scale
        out["mask_snr"] = float(residual[mask].mean() / scale)
    # Bleaching within this burst: first third vs last third, per SAFETY.md §6.
    if stack.shape[0] >= 6:
        third = stack.shape[0] // 3
        first = float(stack[:third].mean())
        last = float(stack[-third:].mean())
        out["within_burst_drift_pct"] = 100.0 * (last - first) / max(first - offset, 1e-9)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Red bead through EM1 position 3 (555) and 4 (647), bracketed.",
    )
    p.add_argument("--cfg", default=str(DEFAULT_CFG), help="Micro-Manager .cfg")
    p.add_argument("--camera", default="Kinetix_red")
    p.add_argument("--filter-device", default="CSUW1-Filter_Red", help="EM1 wheel")
    p.add_argument("--light-device", default="Aura", help="Aura (COM7) or LightEngine (COM3)")
    p.add_argument("--line", default="GREEN", help="NAMED line: UV/CYAN/GREEN/RED/NIR")
    p.add_argument(
        "--intensity", type=int, default=None,
        help="line intensity, PER-MILLE 0-1000 (50 = 5%%). Light stays OFF unless given.",
    )
    p.add_argument("--exposure-ms", type=float, default=33.33)
    p.add_argument("--roi", type=int, default=None, help="centred square ROI in sensor px")
    p.add_argument(
        "--positions", default="405,488,555,647",
        help="EM1 wheel labels to measure, comma separated. 555 is always "
             "measured first and last as the time bracket, wherever it appears. "
             "The default is all four single-band positions: with GREEN "
             "excitation (544-565 through MXR00724-EX) the 405 and 488 bands sit "
             "BLUEWARD of the excitation, so they are anti-Stokes and must read "
             "~zero -- they are the controls that turn a two-point ratio into a "
             "bounded emission band.",
    )
    p.add_argument("--n-frames", type=int, default=20, help="frames per filter position")
    p.add_argument("--settle-s", type=float, default=0.5, help="wait after a wheel move")
    p.add_argument("--dry-run", action="store_true", help="preflight only: no light, no writes")
    p.add_argument("--force", action="store_true", help="proceed despite preflight problems")
    p.add_argument(
        "--fix-path", action="store_true",
        help="open both turret shutters and set CSUW1-Port=red_only, then re-run "
             "the preflight. The shutters are NOT closed again afterwards "
             "(SAFETY.md §8); CSUW1-Port is restored.",
    )
    p.add_argument(
        "--disable-pp", action="store_true",
        help="turn every camera post-processing ENABLED entry off and LEAVE it "
             "off. Required for a quantitative frame -- despeckle breaks "
             "ADU-to-electron proportionality (docs/06 C1).",
    )
    p.add_argument(
        "--out", default=None,
        help="directory for the report and the averaged frames (default: skip saving)",
    )
    args = p.parse_args(argv)

    if not args.dry_run and args.intensity is None:
        p.error("--intensity is required to enable light (per-mille, 0-1000). "
                "Use --dry-run to check the path state with the light off.")

    from pymmcore_plus import CMMCorePlus  # deferred: --help must work anywhere

    core = CMMCorePlus()
    print(f"loading {args.cfg}")
    core.loadSystemConfiguration(args.cfg)

    report: dict = {
        "script": Path(__file__).name,
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cfg": args.cfg,
        "camera": args.camera,
        "light": {"device": args.light_device, "line": args.line, "per_mille": args.intensity},
        "exposure_ms": args.exposure_ms,
        "n_frames_per_position": args.n_frames,
    }

    problems, observed = preflight(core, args.camera)
    report["observed_path_state"] = observed
    report["preflight_problems"] = problems

    print("\npath state")
    for key, value in observed.items():
        if key != "camera_pp":
            print(f"  {key:32s} {value}")
    if observed.get("camera_pp"):
        print("  camera post-processing")
        for key, value in observed["camera_pp"].items():
            print(f"    {key:38s} {value}")

    if problems:
        print("\npreflight problems")
        for problem in problems:
            print(f"  [FAIL] {problem}")
    else:
        print("\npreflight: clean")

    if args.dry_run:
        print("\n--dry-run: nothing was enabled and nothing was moved.")
        return 0 if not problems else 1

    restore_path: list[tuple[str, str, str]] = []
    if problems and (args.fix_path or args.disable_pp):
        if args.fix_path:
            print("\n--fix-path: writing path state")
            report["path_changed"], restore_path = fix_path(core)
        if args.disable_pp:
            print("\n--disable-pp: turning camera post-processing off (and leaving it off)")
            report["pp_changed"] = disable_pp(core, args.camera)
        problems, observed = preflight(core, args.camera)
        report["observed_path_state"] = observed
        report["preflight_problems"] = problems
        if problems:
            print("\nremaining preflight problems")
            for problem in problems:
                print(f"  [FAIL] {problem}")
        else:
            print("\npreflight after fixes: clean")

    if problems and not args.force:
        print("\nREFUSED. Fix the above, or re-run with --force to record the "
              "measurement as taken over a warning.")
        return 1
    report["preflight_forced"] = bool(problems and args.force)

    core.setCameraDevice(args.camera)
    core.setAutoShutter(False)
    core.setExposure(args.exposure_ms)
    if args.roi:
        w, h = core.getImageWidth(), core.getImageHeight()
        core.setROI((w - args.roi) // 2, (h - args.roi) // 2, args.roi, args.roi)
    report["roi"] = list(core.getROI(args.camera))
    report["exposure_ms_actual"] = float(core.getExposure())

    filter_before = _state_label(core, args.filter_device)
    report["filter_position_before"] = filter_before
    print(f"\n{args.filter_device} was at {filter_before!r} -- will be restored")

    results: dict = {}
    try:
        # Warm-up, discarded. The first frames after a mode or PP write sit on
        # a settling baseline: on 2026-09-06 the dark median read 124.6 ADU
        # immediately after those writes and 113.8 a few seconds later, which
        # made every light-minus-dark difference NEGATIVE.
        print(f"\nwarm-up ({args.n_frames} frames, discarded)")
        burst(core, args.camera, args.n_frames)

        # ── dark frame: the offset under every number below (recipe step 5) ──
        print(f"dark frame ({args.n_frames} frames, light off)")
        dark = burst(core, args.camera, args.n_frames)
        offset = float(np.median(dark))
        dark_mean = dark.mean(axis=0)
        report["offset_adu"] = offset
        report["dark_max_adu"] = float(dark_mean.max())
        dark_sd = float(np.median(np.abs(dark_mean - offset))) * 1.4826 or 1.0
        report["dark_robust_sd_adu"] = dark_sd
        print(f"  offset (median) = {offset:.1f} ADU   robust sd = {dark_sd:.2f}   "
              f"max = {report['dark_max_adu']:.1f} (hot pixels)")

        light(core, args.light_device, args.line, args.intensity)
        print(f"\nlight ON: {args.light_device} {args.line} = {args.intensity}/1000 "
              f"(State=1)")

        # ── did the light actually arrive? ───────────────────────────────────
        # The guard that was missing on 2026-09-06. A closed engine shutter, a
        # closed turret shutter or a wrong line all produce a frame that is
        # simply the dark frame -- and every ratio computed downstream is then
        # the ratio of two hot-pixel patterns, which looks like a result.
        core.setStateLabel(args.filter_device, "multi")
        core.waitForDevice(args.filter_device)
        time.sleep(args.settle_s)
        lit = burst(core, args.camera, max(5, args.n_frames // 4)).mean(axis=0)
        rise = float(np.median(lit) - offset)
        report["light_check"] = {
            "filter": "multi",
            "median_rise_adu": rise,
            "px_above_dark_10sd": int((lit > offset + 10 * dark_sd).sum()),
        }
        print(f"  light check through 'multi': median rise {rise:+.1f} ADU, "
              f"{report['light_check']['px_above_dark_10sd']} px above dark+10sd")
        if rise <= 0:
            raise RuntimeError(
                f"the illuminated field is not brighter than the dark frame "
                f"(median rise {rise:+.1f} ADU through the widest filter in the "
                f"wheel). No light is reaching the camera, so there is nothing "
                f"to compare between positions 3 and 4. Check: {args.light_device} "
                f"State/{args.line}, both turret shutters, and CSUW1-Shutter."
            )

        # 555 first and last, everything else in between. The two 555 passes
        # bracket time; the bands BLUEWARD of the excitation are zero controls.
        others = [p for p in args.positions.split(",") if p.strip() and p.strip() != "555"]
        order = ([("555a", "555")]
                 + [(p.strip(), p.strip()) for p in others]
                 + [("555b", "555")])
        report["order"] = [tag for tag, _ in order]
        stacks: dict[str, np.ndarray] = {}
        for tag, label in order:
            core.setStateLabel(args.filter_device, label)
            core.waitForDevice(args.filter_device)
            time.sleep(args.settle_s)
            actual = _state_label(core, args.filter_device)
            if actual != label:
                raise RuntimeError(
                    f"{args.filter_device} reports {actual!r} after asking for {label!r}"
                )
            print(f"  {tag}: {args.filter_device} = {actual}  ...", end="", flush=True)
            stacks[tag] = burst(core, args.camera, args.n_frames)
            print(f" mean {stacks[tag].mean():.1f} ADU")

        mask, mask_info = bead_mask(stacks, dark_mean)
        report["mask"] = mask_info
        print(f"\n  bead mask: {mask_info['mask_px']} px on "
              f"{mask_info['objects_555a']} / {mask_info['objects_555b']} compact "
              f"objects, {mask_info['reproducible_frac']:.0%} reproducible between "
              f"the two 555 passes ({mask_info['objects_on_hot_px']} on hot pixels)")
        if mask_info["mask_px"] == 0:
            raise RuntimeError(
                "no compact objects found in either 555 frame. Light is reaching "
                "the camera (the check above passed) but nothing in the field is "
                "a resolved particle -- focus the sample and confirm beads are "
                "visible before measuring a ratio."
            )

        for tag in stacks:
            results[tag] = stats(stacks[tag], offset, mask)
        report["positions"] = results

        if args.out:
            outdir = Path(args.out)
            outdir.mkdir(parents=True, exist_ok=True)
            for tag, stack in stacks.items():
                np.save(outdir / f"mean_{tag}.npy", stack.mean(axis=0))
            np.save(outdir / "mean_dark.npy", dark.mean(axis=0))
            report["saved_to"] = str(outdir)

    finally:
        light_off(core, args.light_device, args.line)
        print(f"\nlight OFF: {args.light_device} {args.line}")
        try:
            core.setStateLabel(args.filter_device, filter_before)
            core.waitForDevice(args.filter_device)
            print(f"{args.filter_device} restored to {filter_before!r}")
        except Exception as exc:
            print(f"! could not restore {args.filter_device}: {exc}", file=sys.stderr)
        for device, prop, before in restore_path:
            try:
                core.setProperty(device, prop, before)
                core.waitForDevice(device)
                print(f"{device}.{prop} restored to {before!r}")
            except Exception as exc:
                print(f"! could not restore {device}.{prop}: {exc}", file=sys.stderr)

    # ── verdict ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("signal above local background, on the bead mask")
    print("=" * 72)
    key = "mask_mean_minus_background"
    # The passband each label actually delivers: the FF01 filter intersected
    # with the MXR00724 cube band it sits inside (config/scopes/current-laser.yaml,
    # kb/decisions/2026-09-03-three-subsystems-first-light.md §4).
    NET_BAND = {
        "405": "414-450 nm   (anti-Stokes control)",
        "488": "510-530 nm   (anti-Stokes control)",
        "555": "589-610 nm",
        "647": "677-701 nm",
        "multi": "quad-band",
        "open": "cube only",
    }
    for tag, _label in order:
        r = results[tag]
        band = NET_BAND.get(tag.rstrip("ab") if tag.startswith("555") else tag, "")
        print(f"  {tag:5s} {band:28s} {r.get(key, float('nan')):9.1f} ADU"
              f"   SNR {r.get('mask_snr', float('nan')):7.1f}   clipped {r['clipped_px']}")

    a, b = results["555a"].get(key), results["555b"].get(key)
    bracket = b / a if a else float("nan")
    report["bracket_555b_over_555a"] = bracket
    print(f"\n  time bracket 555b/555a = {bracket:.3f}")

    if not np.isfinite(bracket) or not (0.85 <= bracket <= 1.15):
        print("  ⚠ the bracket is more than 15% off 1.0, so something changed with "
              "TIME -- bleaching, focus drift or light-engine drift. The filter "
              "ratio below is NOT interpretable until that is fixed.")
        report["verdict"] = "INCONCLUSIVE -- time bracket failed"
    else:
        mean555 = 0.5 * (a + b)
        report["band_ratios_over_555"] = {
            tag: (results[tag].get(key, float("nan")) / mean555 if mean555 else float("nan"))
            for tag, _ in order if not tag.startswith("555")
        }
        for tag, value in report["band_ratios_over_555"].items():
            print(f"  {tag}/555 = {value:.3f}")

        # The anti-Stokes bands are the control. With GREEN excitation they sit
        # blueward of the excitation and cannot carry fluorescence, so whatever
        # they read is the floor of this method -- scatter, leakage, and the
        # residual of the local-background subtraction. A 647 reading at or
        # below that floor means the 677-701 band is EMPTY; a 647 reading well
        # above it is a real emission that happens to be weaker.
        controls = [report["band_ratios_over_555"][t]
                    for t in ("405", "488") if t in report["band_ratios_over_555"]]
        floor = max(controls) if controls else None
        report["anti_stokes_floor_ratio"] = floor
        if floor is not None:
            print(f"  anti-Stokes floor (max of the 405/488 controls) = {floor:.3f}")

        ratio = report["band_ratios_over_555"].get("647", float("nan"))
        report["ratio_647_over_555"] = ratio
        if floor is not None and np.isfinite(ratio) and ratio <= 2.0 * floor:
            verdict = (
                f"EMISSION IS IN THE 589-610 BAND, and the 677-701 band is EMPTY: "
                f"647/555 = {ratio:.3f} is within 2x of the anti-Stokes floor "
                f"{floor:.3f}, i.e. not distinguishable from bands that CANNOT "
                f"carry fluorescence. The vendor's 680 nm emission is wrong, as "
                f"its 620 nm excitation already was. Use FF01-595/31 (position 3)."
            )
        elif ratio > 3.0:
            verdict = ("EMISSION IS IN THE 677-711 BAND. The vendor's 680 nm is "
                       "supported; keep FF01-680/42 (position 4) in the red arm.")
        elif ratio < 0.33:
            tail = ""
            if floor is not None and np.isfinite(ratio) and ratio > 2.0 * floor:
                tail = (
                    f" The 677-701 band is NOT empty, though: at {ratio:.3f} it sits "
                    f"{ratio / floor:.0f}x above the anti-Stokes floor {floor:.3f}, so "
                    f"it carries real emission -- a broad red TAIL of one emitter, "
                    f"which is what a rhodamine-class dye looks like, rather than a "
                    f"second population. That tail is what will cross-talk into any "
                    f"647 channel added later."
                )
            verdict = ("PEAK EMISSION IS IN THE 589-610 BAND, not at 680. The dye is "
                       "rhodamine/TRITC-class; the vendor's 680 nm emission is wrong, "
                       "as its 620 nm excitation already was. Use FF01-595/31 "
                       "(position 3) in the red arm." + tail
                       + " NOTE this brackets the band, it does not locate the peak: "
                         "two filters cannot, and 589-610 catches the flank of "
                         "anything peaking between ~570 and ~610.")
        else:
            verdict = ("SPLIT BETWEEN BOTH BANDS -- the emission is broad or sits "
                       "between them. Neither filter is clearly right; this needs "
                       "a spectrum, not a two-point ratio.")
        report["verdict"] = verdict
        print(f"\n  -> {verdict}")

    if any(results[t]["clipped_px"] for t in results):
        print("\n  ⚠ CLIPPED PIXELS PRESENT. A clipped peak is a lower bound, not a "
              "measurement -- the ratio is compressed toward 1. Drop the exposure "
              "or the intensity and re-run.")

    print("\nnext: paste the numbers into kb/calibrations/frame-photometry.yaml "
          "(the recipe is at the top of that file), correct "
          "data/fluorophores.yaml > AbvigenRed680, then re-run\n"
          "  python -m optics.cli check config/channels/aura-widefield-green-red-2color.yaml")

    if args.out:
        path = Path(args.out) / "em1-555-vs-647.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
