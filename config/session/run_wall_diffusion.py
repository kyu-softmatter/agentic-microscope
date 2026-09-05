"""Wall-hindered Brownian motion of sedimented beads: one timestamped block.

    python config/session/run_wall_diffusion.py --cfg CFG --seconds 60 \
        --temperature-c 20.0 --trap-emission-off --out D:\\data\\wall\\f01

WHY THIS EXISTS RATHER THAN `calibration.cli ram-burst`
-------------------------------------------------------
`ram_capture.py` runs the burst but calls ``popNextImage()``, which throws the
per-frame metadata away and reports one ``elapsed_s`` for the whole sequence.
Two things this measurement cannot do without that metadata:

  * **The lag axis.** This camera does not honour a requested frame interval
    (measured 2026-09-03, kb/decisions/2026-09-03-three-subsystems-first-light.md
    §7: ``intervalMs`` in ``startSequenceAcquisition`` is ignored; the frame
    period equals the exposure because readout is pipelined). So the interval
    is not a setting we chose -- it is an outcome we have to read back, from
    ``ElapsedTime-ms``. An MSD computed against a nominal interval is an MSD
    against a number nobody measured.
  * **Proving no frame was dropped.** MMCore raises nothing when it loses a
    frame (compute/drops.py). ``ImageNumber`` gaps are the only proof, and
    ``popNextImage()`` does not return them. A silent drop does not just lose
    data -- it shifts the assumed lag of every pair that straddles it.

`calibration/timestamped_capture.py` keeps both. It has no CLI; this is it,
with the preconditions this particular measurement needs bolted to the front.

WHAT IT REFUSES, AND WHY REFUSING BEATS FIXING
----------------------------------------------
Every precondition below is checked and *reported*, and the ones that would
silently corrupt the measurand are hard refusals. None of them is repaired
automatically, because each repair is a device motion or a state change whose
consequences belong to a human:

  * **Nosepiece** must already read the objective you claim. Rotating it is a
    COLLISION_DEVICES operation and the stand runs no escape
    (hardware/microscope.NOSEPIECE_HAS_NO_ESCAPE) -- this script will not turn
    a turret with a 0.15 mm working distance under a sample.
  * **IntermediateMagnification** must read 1.0x, via
    ``getMagnificationFactor()``. It is a **MagnifierDevice**, not a
    StateDevice (measured 2026-09-04: ``getDeviceType`` -> 13,
    ``getNumberOfStates`` -> -1, ``getState`` raises "wrong type for the
    requested operation"), and its ``Magnification`` property is read-only with
    allowed values ``['1.0x', '1.5x']`` -- a manual knob whose position MM
    reports but cannot set. So the check is a software read, not the
    bead-diameter eyeball it was first written as.
    ``calibration.cli intermediate-mag`` treats it as a state device and
    reports "0 positions"; that is the tool mismatching the device.
    Why it matters: data/pixel_size.yaml's presets key on the Nosepiece alone,
    so if MM does *not* divide the pixel size by this factor then at 1.5x the
    pixel size is wrong by 1.5x and **D, which goes as pixel squared, is wrong
    by 2.25x** -- indistinguishable from a wall hindrance near 2. Whether MM
    divides is untested on this instrument; turning the knob to 1.5x and
    reading ``getPixelSizeUm()`` settles it in ten seconds (1.5x applied ->
    0.07222 at 60x; not applied -> 0.10833).
  * **Both turret shutters** must be open. Either one closed blocks the image
    (config/micromanager/live_view.py header). Note what this means for the
    1064 nm trap: the shutter is *not* how you keep the trap out of the
    sample, because closing it also blocks your own fluorescence. Emission off
    at the Aresis is, and that is off-ledger -- not in MM, not checkable from
    here. Hence ``--trap-emission-off`` as an explicit assertion that gets
    written into the run record rather than assumed.
  * **PVCAM post-processing** is recorded and then **turned off in this
    process**, which is the one precondition here that is repaired rather than
    refused -- because it has to be, every run. Measured 2026-09-04: setting
    the six ``PP  N   ENABLED`` flags to ``No`` and reading them back works,
    but a new process loading the same ``.cfg`` finds all six at ``Yes``
    again, and the ``.cfg`` has no ``PP`` lines (zero grep hits). PVCAM
    restores the camera's own defaults on device initialisation. That is
    almost certainly why docs/06 C1 found despeckle enabled in every archive
    generation -- a sticky camera default, not carelessness.
    It modifies data rather than merely being available: same camera, same
    33.3 ms exposure, minutes apart, dark-frame maximum **148 ADU with the
    flags on and 1193 ADU with them off**. Despeckle was erasing hot pixels,
    so ADU was not proportional to electrons.

TEMPERATURE IS A REQUIRED ARGUMENT
----------------------------------
``D = kT/gamma`` and water's viscosity moves about -2.4%/K, so ``dD/D`` is
2.74% per K. Nothing on this instrument measures the sample temperature and no
setup dataclass in this repository has a field for it, which is why it is a
mandatory flag here instead: an unrecorded temperature is a multiplicative
error on the answer of the same order as the pixel calibration, and it is
one-sided (an oil objective bridges heat into the coverslip, so the sample runs
warm, so D reads high, so the wall effect reads weak).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from calibration.timestamped_capture import capture_timestamped  # noqa: E402

#: Free-run. Passed explicitly rather than left to default so the reason is
#: visible at the call site: a requested interval is ignored by this camera
#: (2026-09-03 §7), so asking for one would put a number in the record that
#: the hardware never honoured.
#:
#: ``--request-interval-ms`` overrides it, because the claim is cheap to
#: re-test and worth re-testing on a different ROI or adapter build. Note what
#: the argument means before using it: MMCore's ``intervalMs`` is the frame
#: **period**, not dead time added after the exposure. Asking for 3 ms with a
#: 30 ms exposure is asking for 333 fps at a 30 ms exposure -- self
#: contradictory. The value that would mean "30 ms exposure, 33.3 ms period"
#: is ``33.3333``, and that is the exact case 2026-09-03 §7 measured as
#: ignored (33.333 requested at a 5 ms exposure delivered 5.000 ms).
#: Either way the script reports requested against achieved, so the answer
#: comes from the camera clock rather than from this comment.
REQUESTED_INTERVAL_MS = 0.0

TURRET_SHUTTERS = ("Turret1Shutter", "Turret2Shutter")

#: Read and reported, never set. The PVCAM adapter exposes post-processing as
#: individual properties whose names vary by build, so the script prints every
#: property whose name matches instead of naming four it may not have.
POST_PROCESSING_HINTS = ("despeckle", "denoise", "post", "pp ")


def _get(core, device: str, prop: str) -> str | None:
    try:
        return str(core.getProperty(device, prop))
    except Exception:
        return None


def _state_label(core, device: str) -> str | None:
    """A state device's current label, or None if its positions were never named.

    Two devices on this instrument answer "Cannot get current position label"
    (CSUW1-Bright, LUNF-Blanking, measured 2026-09-03), so this cannot assume
    a label exists.
    """
    try:
        return str(core.getStateLabel(device))
    except Exception:
        return None


def _post_processing(core, camera: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        names = list(core.getDevicePropertyNames(camera))
    except Exception:
        return out
    for name in names:
        low = name.lower()
        if any(h in low for h in POST_PROCESSING_HINTS):
            value = _get(core, camera, name)
            if value is not None:
                out[name] = value
    return out


def disable_post_processing(core, camera: str) -> tuple[dict[str, str], list[str]]:
    """Turn every post-processing feature off, in this process. Returns (before, refusals).

    **This has to run after the config load and before the first frame, every
    single time**, and that is the whole reason this function exists rather
    than a note telling the operator to set it once.

    Measured 2026-09-04: the six ``PP  N   ENABLED`` flags on this Kinetix22
    were set to ``No`` and read back as ``No``; a *new* process then loaded the
    same ``.cfg`` and found all six at ``Yes`` again. The ``.cfg`` contains no
    ``PP`` lines at all (grep: zero hits), so the revert does not come from the
    configuration -- PVCAM restores the camera's own stored defaults when the
    device initialises. Turning despeckle off is not a setting you make once.

    That also explains docs/06 C1's finding that despeckle was enabled in every
    archive generation. It reads as carelessness and is not: it is a sticky
    camera default that comes back on every load.

    And it demonstrably modifies data rather than merely being available --
    same camera, same 33.3 ms exposure, minutes apart, dark-frame maximum
    148 ADU with the flags on and 1193 ADU with them off. Despeckle was
    erasing hot pixels, so ADU was not proportional to electrons.
    """
    before = _post_processing(core, camera)
    on = [k for k, v in before.items()
          if v == "Yes" and k.upper().rstrip().endswith("ENABLED")]
    refusals: list[str] = []
    if not on:
        print("  post-processing: nothing enabled")
        return before, refusals
    print(f"  post-processing: {len(on)} enabled -> disabling in-process")
    for name in on:
        try:
            core.setProperty(camera, name, "No")
        except Exception as exc:
            refusals.append(f"could not disable {name!r}: {exc}")
    still = [n for n in on if _get(core, camera, n) == "Yes"]
    if still:
        refusals.append(
            f"post-processing still enabled after being set to No: {still}. "
            "docs/06 C1: this breaks the ADU-to-electron proportionality and "
            "the frames cannot be repaired afterwards."
        )
    else:
        print(f"    all {len(on)} now No")
    return before, refusals


def preflight(core, args) -> tuple[dict, list[str]]:
    """Read the state this measurement depends on. Returns (record, refusals)."""
    refusals: list[str] = []
    rec: dict = {}

    camera = args.camera or core.getCameraDevice()
    rec["camera"] = camera
    if not camera:
        refusals.append("no camera device is set on the core")
        return rec, refusals

    # --- the objective, and the magnification that decides the pixel size ---
    rec["nosepiece"] = _state_label(core, "Nosepiece")
    if rec["nosepiece"] is None:
        refusals.append(
            "cannot read the Nosepiece label, so the objective is unknown and "
            "the pixel size cannot be attributed"
        )
    elif args.expect_objective.lower() not in rec["nosepiece"].lower():
        refusals.append(
            f"Nosepiece reads {rec['nosepiece']!r}, not the expected "
            f"{args.expect_objective!r}. Not rotating it -- that is a "
            "COLLISION_DEVICES move and the stand runs no escape. Set the "
            "objective yourself, or pass --expect-objective to match."
        )

    # IntermediateMagnification is a MagnifierDevice, NOT a StateDevice
    # (measured 2026-09-04: getDeviceType -> 13, getNumberOfStates -> -1, and
    # getState raises "wrong type for the requested operation"). So the position
    # comes from getMagnificationFactor(), and the read-only `Magnification`
    # property carries the label. calibration.cli intermediate-mag treats it as
    # a state device and therefore reports "0 positions" -- that is the tool
    # mismatching the device, not the device being unnamed.
    rec["intermediate_magnification"] = _get(core, "IntermediateMagnification",
                                             "Magnification")
    try:
        rec["magnification_factor"] = float(core.getMagnificationFactor())
    except Exception as exc:
        rec["magnification_factor"] = None
        refusals.append(
            f"cannot read getMagnificationFactor() ({exc}), so the intermediate "
            "magnification is unknown and the pixel size cannot be attributed"
        )
    mf = rec["magnification_factor"]

    try:
        px_mm = float(core.getPixelSizeUm())
    except Exception:
        px_mm = 0.0
    rec["pixel_size_um_from_mm"] = px_mm
    if not px_mm:
        refusals.append(
            "getPixelSizeUm() answers 0.0, so the .cfg has no PixelSize preset "
            "for this nosepiece position. See config/micromanager/set_pixel_size.py"
        )

    # The pixel size is taken from the RECORDED TABLE indexed by (objective,
    # magnification factor), not from MM, and MM is then used to cross-check it.
    #
    # Refusing whenever the factor is not 1.0 would be over-conservative -- at
    # 1.5x the right pixel size is simply the table's 1.5x row (KH 2026-09-04).
    # But "just divide getPixelSizeUm() by 1.5" is not safe either, because
    # whether MMCore already divides by getMagnificationFactor() is untested on
    # this instrument. If it does and we divide again, the pixel size is wrong
    # by 1.5x and D by 2.25x -- the same error, mirrored. So: take the table
    # value, which is unambiguous, and let the comparison against MM report
    # which convention MM follows. At 1.0x the two agree either way, which is
    # exactly why this has never been settled.
    obj_mag = None
    if rec.get("nosepiece"):
        import re as _re
        hit = _re.search(r"(\d+(?:\.\d+)?)\s*[xX]", rec["nosepiece"])
        if hit:
            obj_mag = float(hit.group(1))
    rec["objective_magnification"] = obj_mag

    px_table, px_evidence = None, None
    if obj_mag is not None and mf is not None:
        from optics.components import recorded_pixel_um  # noqa: PLC0415
        hit2 = recorded_pixel_um(obj_mag, mf)
        if hit2 is not None:
            px_table, px_evidence = hit2
    rec["pixel_size_um"] = px_table
    rec["pixel_size_evidence"] = px_evidence
    rec["pixel_size_source"] = (
        f"data/pixel_size.yaml [{obj_mag:g}x, {mf:g}x]" if px_table else "unresolved"
    )

    if px_table is None:
        refusals.append(
            f"no pixel-size row for objective {obj_mag}x at magnification "
            f"factor {mf}. D goes as pixel squared, so this is the one input "
            "that cannot be left to a fallback."
        )
    elif px_mm:
        ratio = px_mm / px_table
        rec["mm_applies_magnifier"] = (
            "n/a at 1.0x" if mf is not None and abs(mf - 1.0) < 1e-6
            else abs(ratio - 1.0) < 0.01
        )
        print(f"  pixel size: table {px_table:.5f} um/px ({px_evidence}), "
              f"MM reports {px_mm:.5f} -> ratio {ratio:.4f}")
        if abs(ratio - 1.0) > 0.01:
            print(f"    MM and the table DISAGREE by {ratio:.4f}x.")
            explained = mf is not None and abs(ratio - mf) < 0.01
            if explained:
                print("    That ratio IS the magnification factor, so MM does "
                      "not apply it. The table value is the right one, and "
                      "this run answers a question open since 2026-09-04.")
            else:
                print("    That is not the magnification factor either.")
                refusals.append(
                    f"MM's pixel size and the recorded table disagree by "
                    f"{ratio:.4f}x, which is not the magnification factor "
                    f"({mf}). Unexplained, and it scales D by its square."
                )

    # --- the imaging path ---
    for label in TURRET_SHUTTERS:
        try:
            is_open = bool(core.getShutterOpen(label))
        except Exception as exc:
            rec[f"{label}_open"] = f"unreadable ({exc})"
            refusals.append(f"cannot read {label}; either one closed blocks the image")
            continue
        rec[f"{label}_open"] = is_open
        if not is_open:
            refusals.append(
                f"{label} is closed, which blocks the image. Both turret "
                "shutters are in series with the detection path. Note this is "
                "not how you exclude the 1064 nm trap -- closing Turret2Shutter "
                "also blocks your own fluorescence; emission off at the Aresis is."
            )

    for label in ("FilterTurret1", "FilterTurret2", "LappMainBranch1",
                  "CSUW1-Bright", "LightPath", "CondenserTurret"):
        rec[label] = _state_label(core, label)

    rec["pfs_in_range"] = _get(core, "PFS", "PFS in Range")
    rec["pfs_focus_maintenance"] = _get(core, "PFS", "FocusMaintenance")
    try:
        rec["zdrive_um"] = float(core.getPosition("ZDrive"))
    except Exception:
        rec["zdrive_um"] = None

    # --- the camera, and the one post-processing setting that voids the data ---
    rec["camera_mode"] = _get(core, camera, "ReadoutRate") or _get(core, camera, "Mode")
    rec["binning"] = _get(core, camera, "Binning")
    rec["pixel_type"] = _get(core, camera, "PixelType")
    try:
        rec["roi"] = list(core.getROI())
        rec["bytes_per_pixel"] = int(core.getBytesPerPixel())
    except Exception:
        rec["roi"], rec["bytes_per_pixel"] = None, None
    # Recorded here; DISABLED by the caller via disable_post_processing()
    # after preflight, because it has to happen in this process every run.
    rec["post_processing_before"] = _post_processing(core, camera)

    # PixelType lies on this camera: it reports 12bit while the data is 16-bit
    # (2026-09-03 §7 -- one 512x512 frame held 12,441 distinct values, max
    # 34,917). bytes_per_pixel is the honest field, so check that instead and
    # say so rather than trusting the string.
    if rec["bytes_per_pixel"] not in (None, 2):
        refusals.append(
            f"bytes per pixel is {rec['bytes_per_pixel']}, not 2. This run "
            "assumes a 16-bit container; an 8-bit mode would also cost the "
            "full well the saturation margin was computed against."
        )
    return rec, refusals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--cfg", required=True, help="Micro-Manager .cfg")
    ap.add_argument("--out", required=True, metavar="STEM",
                    help="output stem; writes STEM.npy, STEM_timestamps.csv, "
                         "STEM_settings.json, STEM_run.json")
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="block length. Frame count is derived from the "
                         "exposure, because the period equals the exposure on "
                         "this camera (default 60)")
    ap.add_argument("--exposure-ms", type=float, default=33.3333,
                    help="also sets the frame period: readout is pipelined, so "
                         "period = max(exposure, readout) and 33.3333 ms was "
                         "measured to deliver 29.9980 fps with jitter 0.00000 "
                         "(default 33.3333)")
    ap.add_argument("--request-interval-ms", type=float, default=REQUESTED_INTERVAL_MS,
                    metavar="MS",
                    help="frame PERIOD to request (not dead time added after "
                         "the exposure). Default 0 = free-run. Measured ignored "
                         "on this camera 2026-09-03; set it to re-test, and "
                         "compare the requested against the achieved period "
                         "this script prints")
    ap.add_argument("--roi", type=int, default=None, metavar="PX",
                    help="centred square ROI in sensor pixels; unset = full "
                         "frame. At a 33 ms exposure this costs NOTHING but "
                         "field of view: the frame period is "
                         "max(exposure, readout) and the 33 ms exposure "
                         "dominates the 9 ms full-frame readout, so cropping "
                         "changes neither the rate nor the duty cycle -- only "
                         "bytes per frame. (That is specific to a long "
                         "exposure. At a 2 ms exposure readout sets the "
                         "period and cropping makes the duty cycle WORSE.)")
    ap.add_argument("--ome-tiff", action="store_true",
                    help="also write an OME-TIFF plus the MM-shaped "
                         "_metadata.txt sidecar. The sidecar is the point: "
                         "compute/mm_metadata.py scans *metadata.txt for "
                         "FrameKey/ElapsedTime tokens, which is how this "
                         "repository reads acquisitions, and it does not parse "
                         "OME-XML. Doubles the disk footprint, so it is opt-in")
    ap.add_argument("--camera", default=None, help="camera label; default the core's")
    ap.add_argument("--light-device", default="Aura",
                    help="Aura (AuraIII, COM7) or LightEngine (SpectraIII). "
                         "Aura, because SpectraIII on this stand needs the DMD "
                         "on as well and is not plain widefield (default Aura)")
    ap.add_argument("--line", default="GREEN",
                    help="named line -- this engine reports UV/CYAN/GREEN/RED/NIR, "
                         "not numeric keys (default GREEN)")
    ap.add_argument("--intensity", type=float, default=20.0,
                    help="per-mille, 0-1000, NOT percent (default 20 = 2%%)")
    ap.add_argument("--temperature-c", type=float, required=True,
                    help="measured sample temperature. Required: dD/D is 2.74%%/K "
                         "and nothing here measures it")
    ap.add_argument("--trap-emission-off", action="store_true",
                    help="assert the 1064 nm Aresis emission is off. Off-ledger, "
                         "so this is recorded as your assertion, not a check")
    ap.add_argument("--expect-objective", default="60x",
                    help="substring the Nosepiece label must contain (default 60x)")
    ap.add_argument("--note", default="", help="free text into the run record")
    ap.add_argument("--force", action="store_true",
                    help="proceed despite refusals. Every refusal is still "
                         "written to the run record")
    args = ap.parse_args(argv)

    if not args.trap_emission_off:
        print(
            "REFUSING: pass --trap-emission-off once you have confirmed the "
            "1064 nm emission is off at the Aresis.\n"
            "  Water absorbs 240x more strongly at 1064 nm than at 555 nm, and a "
            "parked trap puts the beads on a temperature gradient -- a "
            "position-dependent bias on D in a measurement whose measurand IS "
            "position dependence. No lens in this repository computes it "
            "(docs/06 D6, ungated by decision).\n"
            "  Closing Turret2Shutter is NOT the fix: it blocks the image too.",
            file=sys.stderr,
        )
        return 2

    from pymmcore_plus import CMMCorePlus  # noqa: PLC0415  (slow import)

    core = CMMCorePlus()
    core.loadSystemConfiguration(str(args.cfg))

    # One run, one folder. --out names the run and the files land inside a
    # directory of that name: a single run already writes .npy,
    # _timestamps.csv, _settings.json and _run.json, plus the OME-TIFF pair
    # when asked, and six files per run flattened into one date folder stops
    # being navigable after a handful of runs (KH 2026-09-04).
    out_stem = Path(args.out) / Path(args.out).name

    print(f"\nconfig: {args.cfg}")
    print(f"run folder: {out_stem.parent}")

    if args.roi:
        # Centre on the SENSOR, not on whatever ROI happens to be set, so the
        # field is reproducible between runs. clearROI() first for that reason.
        core.clearROI()
        sw, sh = core.getImageWidth(), core.getImageHeight()
        w = min(int(args.roi), sw)
        h = min(int(args.roi), sh)
        core.setROI((sw - w) // 2, (sh - h) // 2, w, h)
        x0, y0, rw, rh = core.getROI()
        print(f"ROI: {rw}x{rh} at ({x0},{y0}) on the {sw}x{sh} sensor "
              f"-- field {rw * 0.10833:.1f} x {rh * 0.10833:.1f} um at 60x/1.0x")

    record, refusals = preflight(core, args)
    camera = record["camera"]

    print("\nstate read:")
    for key in ("nosepiece", "intermediate_magnification",
                "magnification_factor", "pixel_size_um",
                "FilterTurret1", "FilterTurret2", "LappMainBranch1",
                "CSUW1-Bright", "LightPath", "Turret1Shutter_open",
                "Turret2Shutter_open", "pfs_in_range", "pfs_focus_maintenance",
                "zdrive_um", "camera_mode", "binning", "pixel_type", "roi"):
        if key in record:
            print(f"  {key:32s} {record[key]}")

    if refusals:
        print("\nREFUSALS:")
        for r in refusals:
            print(f"  - {r}")
        if not args.force:
            print("\nNothing was acquired. Fix these, or pass --force to "
                  "proceed with them recorded.", file=sys.stderr)
            record["refusals"] = refusals
            return 1
        print("\n--force given: proceeding with the above recorded.")

    print("\ndisabling camera post-processing (must happen every run -- "
          "PVCAM restores the camera's defaults on every config load):")
    pp_before, pp_refusals = disable_post_processing(core, camera)
    record["post_processing_before"] = pp_before
    record["post_processing_after"] = _post_processing(core, camera)
    if pp_refusals:
        print("\nREFUSALS (post-processing):")
        for r in pp_refusals:
            print(f"  - {r}")
        refusals.extend(pp_refusals)
        if not args.force:
            record["refusals"] = refusals
            print("\nNothing was acquired.", file=sys.stderr)
            return 1

    core.setExposure(float(args.exposure_ms))
    actual_exposure = float(core.getExposure())
    if 0.0 < args.request_interval_ms < actual_exposure:
        print(
            f"\nNOTE: --request-interval-ms {args.request_interval_ms:g} is SHORTER "
            f"than the {actual_exposure:.4f} ms exposure. MMCore's intervalMs is "
            "the frame period, not dead time added after the exposure, so this "
            "asks for a period the exposure alone already exceeds. If you meant "
            f"'{actual_exposure:.0f} ms exposure, {actual_exposure + args.request_interval_ms:.4f} ms "
            f"period', pass --request-interval-ms {actual_exposure + args.request_interval_ms:.4f}.",
            file=sys.stderr,
        )
    # Frames are derived from the exposure, not from the requested interval:
    # the period equals the exposure unless something outside MM enforces
    # otherwise, so sizing the block off a request that may be ignored would
    # make the block length itself a guess.
    n_frames = max(1, int(round(args.seconds * 1000.0 / actual_exposure)))
    print(f"\nexposure set to {actual_exposure:.4f} ms -> {n_frames} frames "
          f"for {args.seconds:.0f} s (free-run; the interval is an outcome, "
          f"not a request)")

    lit = False
    prior_shutter = None
    try:
        engine = args.light_device
        props = {p for p in core.getDevicePropertyNames(engine)}
        if args.line not in props:
            print(f"{engine} has no line {args.line!r}. Named lines: "
                  f"{', '.join(sorted(p for p in props if p.isupper()))}",
                  file=sys.stderr)
            return 2
        core.setProperty(engine, f"{args.line}_Intensity", args.intensity)
        core.setProperty(engine, args.line, 1)
        # The shutter role points at whichever engine the .cfg named, which need
        # not be the one being driven -- opening it would then open the *other*
        # engine and leave this one dark (config/micromanager/live_view.py).
        prior_shutter = core.getShutterDevice()
        core.setShutterDevice(engine)
        core.setShutterOpen(True)
        lit = True
        print(f"light: {engine}.{args.line} at {args.intensity:.0f}/1000 "
              f"({args.intensity / 10:.1f}%)")

        result = capture_timestamped(
            core, n_frames,
            interval_ms=args.request_interval_ms,
            camera=camera,
        )
    finally:
        if lit:
            try:
                core.setShutterOpen(False)
                core.setProperty(engine, args.line, 0)
                if prior_shutter:
                    core.setShutterDevice(prior_shutter)
                print("light off.")
            except Exception as exc:
                print(f"WARNING: could not turn the light off ({exc}) -- "
                      "check the engine by hand.", file=sys.stderr)
        # Turret shutters are deliberately left as they were. Closing
        # Turret2Shutter would drop a live trap, and it is not this script's
        # to decide (config/micromanager/live_view.py).

    # --- SAVE FIRST. Analysis second. ---
    #
    # This order is not cosmetic. The first version of this script reported the
    # drop statistics before calling write(), and a single wrong attribute
    # access -- `image_number_gaps()` on what is a @property -- raised
    # TypeError after a clean 1800-frame, 60 s acquisition and took the whole
    # burst down with it (2026-09-04). The frames only exist in this process's
    # RAM until write() runs, so every line between the capture and the write
    # is a line that can destroy the measurement. There are now none.
    paths = result.write(out_stem)
    for what, path in paths.items():
        print(f"wrote {what}: {path}")
    if args.ome_tiff:
        # pixel_size_um comes from the recorded table via preflight, which is
        # the only provenance this run has -- write_ome_tiff's own docstring
        # warns against passing a number whose origin you cannot name.
        try:
            ome = result.write_ome_tiff(out_stem,
                                        pixel_size_um=record.get("pixel_size_um"))
            for what, path in ome.items():
                print(f"wrote {what}: {path}")
        except Exception as exc:
            print(f"OME-TIFF not written ({exc}) -- the .npy and CSV are safe",
                  file=sys.stderr)

    # --- what actually arrived ---
    print(f"\ncaptured {result.n_captured}/{result.n_requested} frames "
          f"in {result.wall_elapsed_s:.2f} s wall")
    if not result.complete:
        # Short of the request is NOT the same as a drop. A drop shows up as an
        # ImageNumber gap; ending early just means the sequence stopped before
        # the last requested frame arrived -- usually because seconds/exposure
        # does not divide evenly and the frame count was rounded up. Harmless
        # for an MSD built on contiguous frames, but it must not pass in
        # silence, because "5400/5401" and "5400 with one dropped" look alike
        # and mean different things.
        print(f"  NOTE: {result.n_requested - result.n_captured} frame(s) short "
              "of the request. Read this together with the ImageNumber gaps "
              "below -- 0 gaps means the sequence ended early, not that a "
              "frame was lost.")
    fps = result.achieved_fps
    print(f"  achieved fps (camera clock, span/(n-1)): "
          f"{fps:.4f}" if fps else "  achieved fps: unavailable")
    if fps:
        achieved_ms = 1000.0 / fps
        print(f"  achieved period: {achieved_ms:.4f} ms  "
              f"(exposure {actual_exposure:.4f} ms, "
              f"interval requested {args.request_interval_ms:g} ms)")
        if args.request_interval_ms > 0:
            honoured = abs(achieved_ms - args.request_interval_ms) < 0.5
            print(f"  -> requested interval was "
                  f"{'HONOURED' if honoured else 'IGNORED'}"
                  f" (2026-09-03 §7 measured it ignored; this run "
                  f"{'contradicts' if honoured else 'confirms'} that)")
            record["interval_honoured"] = honoured
    print(f"  frames without a timestamp: {result.frames_without_timestamp}")
    # image_number_gaps, dropped_by_image_number and host_vs_camera_drift_ms
    # are @property on CaptureResult; drop_report(), write() and
    # timestamps_csv() are methods. Calling a property cost one 60 s
    # acquisition on 2026-09-04, which is why the write now happens above.
    gaps = result.image_number_gaps
    print(f"  ImageNumber gaps: {len(gaps)}  "
          f"-> {result.dropped_by_image_number} frame(s) lost")
    for lo, hi in gaps[:10]:
        print(f"    gap between ImageNumber {lo} and {hi}")
    drift = result.host_vs_camera_drift_ms
    if drift is not None:
        print(f"  host clock drifted {drift:.2f} ms from the camera clock "
              "(cross-check only)")

    try:
        dr = result.drop_report()
        print(f"  drops: median interval {dr.median_interval_ms:.3f} ms, "
              f"mean {dr.mean_interval_ms:.3f} ms, MAD {dr.mad_interval_ms:.3f} ms, "
              f"jitter {dr.jitter_fraction:.5f}")
        print(f"  cadence {dr.cadence_fps:.4f} fps, "
              f"throughput {dr.throughput_fps:.4f} fps")
        record["drop_report"] = {
            "median_interval_ms": dr.median_interval_ms,
            "mean_interval_ms": dr.mean_interval_ms,
            "mad_interval_ms": dr.mad_interval_ms,
            "jitter_fraction": dr.jitter_fraction,
            "cadence_fps": dr.cadence_fps,
            "throughput_fps": dr.throughput_fps,
        }
    except Exception as exc:
        print(f"  drop report unavailable ({exc})")

    # --- the run record: the facts a later reader cannot recover from the .npy ---
    record.update({
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cfg": str(args.cfg),
        "exposure_ms_commanded": args.exposure_ms,
        "exposure_ms_actual": actual_exposure,
        "requested_interval_ms": args.request_interval_ms,
        "n_frames": n_frames,
        "achieved_fps": fps,
        "light_device": args.light_device,
        "line": args.line,
        "intensity_per_mille": args.intensity,
        "temperature_c": args.temperature_c,
        "trap_emission_off_asserted": True,
        "refusals": refusals,
        "note": args.note,
        # Standing interpretations this block was acquired under. Recorded so an
        # accepted bias is distinguishable from an overlooked one -- the
        # registries in validity/setup.py have no category for either of these.
        "committee": {
            "wall_drag_is_measurand": (
                "sample G16c margin 0.19 is signal, not risk. "
                "LIMITS['wall_drag_suppression'] = 0.10 is a screening limit "
                "for nuisance drag; this experiment measures the drag. "
                "docs/06-pitfalls.md D8 grants lens 6 the ruling."
            ),
            "wall_drag_bound_invalid_here": (
                "sample/aberration.py's 9a/16h is documented as an upper bound "
                "but the claim inverts below h/a = 1.70, so the printed "
                "suppression is NOT a bound at this geometry. Use "
                "Goldman-Cox-Brenner or the full Faxen series."
            ),
            "sampling_wrong_direction_out_of_domain": (
                "detection G5's tracking branch applies a point-emitter "
                "localization model to a 46-px resolved sphere. Withdrawn; "
                "sigma comes from the fitted MSD intercept and the stuck-bead "
                "plateau instead."
            ),
            "motion_blur_correction": (
                "duty is 100% in free-run because period = exposure. "
                "MSD = 2D(dt - t_exp/3) + 2*sigma^2 is exact for uniform "
                "illumination and is an x-axis offset of t_exp/3, not a shape "
                "distortion. Fit from lag 2 so the largest correction is 17%, "
                "not 33%."
            ),
            "analysis": (
                "Fit the ENSEMBLE-averaged MSD against (ElapsedTime lag - "
                "t_exp/3), lags 2-15, per axis. Drift reference: fixed "
                "fiducials on the glass, NOT the free-bead ensemble mean "
                "(which removes real diffusion and biases D down by 1/N). "
                "Tracker must be intensity-scale invariant."
            ),
        },
    })
    run_path = out_stem.with_name(out_stem.name + "_run.json")
    run_path.write_text(json.dumps(record, indent=2, default=str) + "\n",
                        encoding="utf-8")
    print(f"wrote run record: {run_path}")

    if gaps and not args.force:
        print("\nFrames were dropped. The lag of every pair straddling a gap is "
              "wrong unless the analysis uses ElapsedTime rather than frame "
              "index -- which it should anyway.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
