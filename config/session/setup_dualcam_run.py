r"""Set up and verify the two-colour dual-camera run, and MEASURE the splitter.

    python config/session/setup_dualcam_run.py --dry-run
    python config/session/setup_dualcam_run.py --fix-path --match-cameras --disable-pp
    python config/session/setup_dualcam_run.py --fix-path --match-cameras --disable-pp \
        --verify-splitter --cyan 200 --green 500

WHAT THIS IS FOR
----------------
`config/channels/aura-widefield-green-red-2color.yaml` says what the optics
should be. This says whether the instrument is actually in that state, puts it
there where it safely can, and then measures the one element that cannot be
read back at all.

    Dragon Green  em 520  -> reflect side of the splitter -> Kinetix_blue -> EM2 "488"
    Abvigen red   em ~600 -> transmit side               -> Kinetix_red  -> EM1 "555"

THE SPLITTER, AND WHY --verify-splitter IS THE POINT OF THIS SCRIPT
-------------------------------------------------------------------
The dual-camera splitter is NOT in the Micro-Manager .cfg. Nothing can read its
position, `kb/systems/current.md` records it as null "and that is the honest
value", and it was the last suspect standing in the 2026-09-04 session that
spent a day on a dark frame. Its three positions are not subtle:

    position 0  100/0 mirror   EVERYTHING to Kinetix_blue, red sees nothing
    position 1  DM A561LP      <561 -> blue, >561 -> red      ← the only one that works here
    position 2  open           EVERYTHING to Kinetix_red, blue sees nothing

`--verify-splitter` turns that into a measurement instead of a belief. It lights
ONE line at a time and reads BOTH cameras:

    CYAN alone (excites Dragon Green, em 520, below the 561 edge) -> expect BLUE
    GREEN alone (excites the red bead, em ~600, above the edge)   -> expect RED

Each position gives a different, unmistakable signature, so the four numbers
identify which one is in the beam. And the off-diagonal terms are not waste:
they are the MEASURED channel crosstalk, which the optics gate can only
approximate from parametric spectra (it reports its own crosstalk margin as
`evidence: assumed`). Two numbers no amount of computation supplies.

WHAT IT WILL AND WILL NOT WRITE
-------------------------------
Writes, with `--fix-path` / `--match-cameras` / `--disable-pp`:
    both turret shutters, CSUW1-Port, the two EM filter wheels,
    each camera's Port/Binning/ROI/exposure, the post-processing entries,
    the circular-buffer footprint, the light engine.

NEVER writes, at all, on any flag:
    Nosepiece, ZDrive, PFSOffset -- hardware.microscope.COLLISION_DEVICES.
    The objective is changed AT THE STAND (SAFETY.md §2): the Ti2 runs no
    escape on an MM nosepiece write, whatever Z the outgoing lens was at is
    where the incoming one arrives, and the 100x Oil has 130 um of working
    distance to absorb it. This script verifies the objective and refuses if it
    is not the expected one.
    The Splitter and FilterTurret2, because it cannot -- neither is software
    controllable on this stand.

TWO THINGS FOUND IN THE 4x STATE, 2026-09-06, THAT THIS SCRIPT NOW CHECKS
-------------------------------------------------------------------------
1. THE CAMERAS WERE IN DIFFERENT MODES. Kinetix_blue was in Sensitivity
   (12-bit, full well 1,000 e-, read noise 1.2) and Kinetix_red in
   Dynamic Range (16-bit, full well 15,000 e-, read noise 1.6). For a
   two-colour measurement that is not a detail: full well spans 75x across
   this camera's four modes, the conversion gain differs, and any ratio taken
   between the two channels inherits both. `--match-cameras` forces one mode
   onto both and refuses to guess which.

2. POST-PROCESSING WAS ON, ON BOTH BODIES. All four despeckle entries plus
   LARGE CLUSTER CORRECTION and FRAME AVERAGING read ENABLED = Yes
   (docs/06 C1, previously recorded only for the archive Prime95B). Despeckle
   replaces threshold-crossing pixels, so ADU stops being proportional to
   electrons and the frame cannot be repaired afterwards.

   ⚠⚠ AND TURNING IT OFF DOES NOT PERSIST. Measured 2026-09-06:
   `measure_red_bead_em1.py --disable-pp` set all six entries to No on
   Kinetix_red, and a LATER `loadSystemConfiguration` on the dual-cam config
   read them all back as Yes. So "off" survives only as long as the MMCore
   session that set it. THIS IS A PER-ACQUISITION STEP, NOT A ONE-TIME FIX --
   which is exactly why `--disable-pp` lives in the setup script rather than in
   a checklist someone did once. Any acquisition whose script did not
   explicitly turn it off was taken with despeckle ON, whatever was done in an
   earlier session.

⚠⚠ WHAT "SET UP" DOES AND DOES NOT MEAN HERE. Measured 2026-09-06 by running
this script, letting the process exit, and re-reading the state:

    Port / ReadoutRate / PixelType   PERSIST  -- camera-side and sticky
    Binning                          RESET to 1x1
    ROI                              RESET to full frame
    exposure, circular buffer        RESET (MMCore state, not the camera's)
    post-processing                  RESET to ENABLED

So this script permanently fixes the ONE thing that cannot be fixed per-run --
the two bodies being in different readout modes, which is a property of the
cameras -- and everything else it sets lasts only as long as its own MMCore
session. THE ACQUISITION SCRIPT MUST APPLY BINNING, ROI, EXPOSURE, BUFFER AND
--disable-pp ITSELF, in its own process. Import `match_cameras` and
`disable_pp` from here rather than restating them, and keep the order: Port,
then Binning, then ROI, then post-processing last.

Run standalone, this script is for VERIFICATION and for `--verify-splitter`.
It is not a state you can set once and walk away from.

SETTINGS THIS DEFAULTS TO, AND WHERE THEY COME FROM
---------------------------------------------------
    Port      Dynamic Range   16-bit, 15,000 e- full well
    Binning   2x2             0.065 um/px oversamples a 241 nm Rayleigh radius
                              by ~3.4x, so 0.130 um/px is still ~1.7x Nyquist.
                              Raises per-pixel signal 4x, cuts the bead disc
                              from 4,647 to 1,162 px (where the read-noise term
                              lives), and quarters the data rate.
    ROI       512 binned px   = 66.6 um field at 100x. Both cameras, both
                              streams: 105 MB/s against the 145 MB/s L3.1–L3.3
                              budget (compute.cli, 2026-09-06).
    exposure  1.8 ms          `detection.cli from-frame` at SNR 10, the only
                              combination that reaches 100 fps: L2.4 caps duty
                              cycle at 30%, i.e. 3 ms at 100 fps.
    buffer    800 MB          L3.4–L3.7 wants 5 s of buffer; at 200 frames/s across
                              two cameras that is 1,000 frames, and 552 frames
                              (the current setting) FAILS at margin 0.55.

⚠ THE EXPOSURE IS THE RED BEAD'S, SCALED. It comes from a 4x frame moved to
100x by the (NA/M)^2 factor 11.891, and Dragon Green's brightness on this path
has never been measured at all -- only "seen properly" qualitatively. Take a
green-only frame and run `detection.cli from-frame` on it before trusting the
green arm's exposure. The two arms are independent light budgets on independent
cameras.
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
DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_noDMD.cfg"

COLLISION_DEVICES = ("Nosepiece", "ZDrive", "PFSOffset")

# Which camera sits on which side of the splitter, and which wheel feeds it.
# kb/systems/current.md > optical_path_nis: EM1 -> Kinetix_red, EM2 -> Kinetix_blue.
ARMS = {
    "blue": {
        "camera": "Kinetix_blue",
        "wheel": "CSUW1-Filter_Blue",
        "filter": "488",            # FF01-515/30, 500-530 nm
        "side": "reflect (<561 nm)",
        "dye": "DragonGreen em 520",
        "line": "CYAN",
    },
    "red": {
        "camera": "Kinetix_red",
        "wheel": "CSUW1-Filter_Red",
        "filter": "555",            # FF01-595/31, 579.5-610.5 nm
        "side": "transmit (>561 nm)",
        "dye": "Abvigen red em ~590-610",
        "line": "GREEN",
    },
}

# (device, property-or-None, expected, why). Expected values are what the DEVICE
# ANSWERS WITH -- a Ti2 turret answers with Nikon's 1-indexed label, not MMCore's
# 0-indexed state.
PREFLIGHT = [
    ("Turret1Shutter", "State", "1", "in series with Turret2Shutter; either closed = black frame"),
    ("Turret2Shutter", "State", "1", "in series with Turret1Shutter; also the 1064 nm path"),
    ("LightPath", "Label", "4-L100", "L100 -- the port the CSU-W1 and both cameras are on"),
    ("CSUW1-Bright", "BrightFieldPort", "Bright Field", "disk bypassed for widefield epi"),
    ("CSUW1-Port", "Label", "blue_red", "BOTH cameras fed -- red_only starves Kinetix_blue"),
    ("CSUW1-Dichroic", "Label", "on", "the Di01-T405/488/568/647 quad dichroic, in path"),
    ("FilterTurret1", None, "1-MXR00724 -Empty", "the 5-band cube; its 510-531 and 589-623 bands are the two channels"),
]

FIXABLE = [
    ("Turret1Shutter", "State", "1", False),
    ("Turret2Shutter", "State", "1", False),
    ("CSUW1-Port", "Label", "blue_red", False),
]

EXPECTED_OBJECTIVE = "6-Plan Apo LmbdD0.13 100x Oil"


def _state_label(core, device: str) -> str:
    try:
        return str(core.getStateLabel(device))
    except Exception:
        try:
            return f"State-{core.getState(device)}"
        except Exception:
            return "<unreadable>"


def preflight(core, expected_objective: str) -> tuple[list[str], dict]:
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

    # Each arm's emission wheel.
    for arm, spec in ARMS.items():
        actual = _state_label(core, spec["wheel"])
        observed[spec["wheel"]] = actual
        if actual != spec["filter"]:
            problems.append(
                f"{spec['wheel']} = {actual!r}, expected {spec['filter']!r} "
                f"-- the {arm} arm ({spec['dye']}) on {spec['camera']}"
            )

    # ── The objective. VERIFIED, NEVER WRITTEN. ──────────────────────────────
    objective = _state_label(core, "Nosepiece")
    observed["Nosepiece"] = objective
    if objective != expected_objective:
        problems.append(
            f"Nosepiece = {objective!r}, expected {expected_objective!r}. "
            f"CHANGE IT AT THE STAND OR IN NIS, not from software (SAFETY.md §2): "
            f"the Ti2 runs no objective escape on an MM nosepiece write, so whatever "
            f"Z the outgoing lens was at is where the incoming one arrives, and the "
            f"100x Oil has 130 um of working distance to absorb the difference. "
            f"This script will not write it."
        )

    for device in ("ZDrive", "PFSOffset"):
        try:
            observed[device] = f"{core.getPosition(device):.3f} um"
        except Exception as exc:
            observed[device] = f"<error: {exc}>"
    for device, prop in (("IntermediateMagnification", "Magnification"),
                         ("PFS", "PFS in Range"),
                         ("PFS", "FocusMaintenance")):
        try:
            observed[f"{device}.{prop}"] = str(core.getProperty(device, prop))
        except Exception as exc:
            observed[f"{device}.{prop}"] = f"<error: {exc}>"

    # FilterTurret2 -- the 1064 path. Reported, never written; it is not
    # software controllable and its label does not name its contents.
    turret2 = _state_label(core, "FilterTurret2")
    observed["FilterTurret2"] = turret2
    if turret2 != "1-Empty":
        problems.append(
            f"FilterTurret2 = {turret2!r}, expected '1-Empty' (= MM position 0). "
            f"⚠ That label does NOT mean the slot is empty: kb/systems/current.md "
            f"records position 0 as the OT path -- OT-Dichroic-750LP (reflects "
            f">750 nm, couples 1064 to the objective) plus OT-EM-750SP (blocks "
            f">=750 nm off the cameras). The label was simply never named in NIS, "
            f"the same display artifact as FilterTurret1's '1-MXR00724 -Empty'. "
            f"Off this position the trap does not reach the sample AND the cameras "
            f"lose their 1064 blocking. Not software controllable -- set it by hand."
        )

    # ── Both cameras. Mode match is the check that matters here. ─────────────
    cams: dict = {}
    for arm, spec in ARMS.items():
        cam = spec["camera"]
        info: dict = {}
        for prop in ("Port", "ReadoutRate", "PixelType", "Binning", "Gain", "TriggerMode"):
            try:
                info[prop] = str(core.getProperty(cam, prop))
            except Exception:
                info[prop] = "<unreadable>"
        try:
            info["ROI"] = list(core.getROI(cam))
        except Exception as exc:
            info["ROI"] = f"<error: {exc}>"
        pp_on = []
        for name in core.getDevicePropertyNames(cam):
            if name.startswith("PP") and "ENABLED" in name.upper():
                try:
                    if str(core.getProperty(cam, name)).strip().lower() in {"yes", "1", "true", "on"}:
                        pp_on.append(name)
                except Exception:
                    pass
        info["pp_enabled"] = pp_on
        if pp_on:
            problems.append(
                f"{cam}: post-processing ON ({len(pp_on)} entries: {', '.join(pp_on)}). "
                f"Despeckle replaces threshold-crossing pixels, so ADU is no longer "
                f"proportional to electrons and the frame cannot be repaired later "
                f"(docs/06 C1, validity G26)."
            )
        cams[cam] = info
    observed["cameras"] = cams

    a, b = (ARMS["blue"]["camera"], ARMS["red"]["camera"])
    for prop in ("Port", "Binning", "ROI"):
        va, vb = cams[a].get(prop), cams[b].get(prop)
        if va != vb:
            problems.append(
                f"THE TWO CAMERAS DISAGREE ON {prop}: {a} = {va!r}, {b} = {vb!r}. "
                f"Full well spans 200 -> 15000 e- across this camera's four modes "
                f"(75x) and the conversion gain and read noise move with it, so any "
                f"ratio taken between the two channels inherits the mismatch."
            )
    return problems, observed


def fix_path(core) -> tuple[dict, list]:
    changed: dict = {}
    for device, prop, want, _restorable in FIXABLE:
        try:
            before = str(core.getProperty(device, prop))
        except Exception as exc:
            print(f"  ! {device}.{prop} unreadable ({exc}) -- not touched", file=sys.stderr)
            continue
        if before == want:
            continue
        core.setProperty(device, prop, want)
        core.waitForDevice(device)
        changed[f"{device}.{prop}"] = {"was": before, "now": want}
        print(f"  {device}.{prop}: {before!r} -> {want!r}")
    for arm, spec in ARMS.items():
        wheel, want = spec["wheel"], spec["filter"]
        before = _state_label(core, wheel)
        if before == want:
            continue
        core.setStateLabel(wheel, want)
        core.waitForDevice(wheel)
        got = _state_label(core, wheel)
        if got != want:
            raise RuntimeError(f"{wheel} reports {got!r} after asking for {want!r}")
        changed[wheel] = {"was": before, "now": got}
        print(f"  {wheel}: {before!r} -> {got!r}   ({arm} arm)")
    return changed, []


def disable_pp(core, cameras: list[str]) -> dict:
    changed: dict = {}
    for cam in cameras:
        for name in core.getDevicePropertyNames(cam):
            # startswith("PP"), not `"ENABLED" in name` -- the loose test also
            # matches CircularBufferEnabled, which this has no business touching.
            if not name.startswith("PP") or "ENABLED" not in name.upper():
                continue
            try:
                before = str(core.getProperty(cam, name))
            except Exception:
                continue
            if before.strip().lower() in {"no", "0", "false", "off"}:
                continue
            allowed = list(core.getAllowedPropertyValues(cam, name)) or ["No"]
            off = next((v for v in allowed
                        if str(v).strip().lower() in {"no", "0", "false", "off"}), "No")
            try:
                core.setProperty(cam, name, off)
                changed[f"{cam}.{name}"] = {"was": before, "now": str(core.getProperty(cam, name))}
                print(f"  {cam}.{name}: {before!r} -> off")
            except Exception as exc:
                print(f"  ! could not turn off {cam}.{name}: {exc}", file=sys.stderr)
    return changed


def match_cameras(core, cameras: list[str], port: str, binning: str,
                  roi_px: int, exposure_ms: float, buffer_mb: int) -> dict:
    """One mode, one binning, one ROI, one exposure on both bodies."""
    out: dict = {}
    for cam in cameras:
        # setCameraDevice FIRST. clearROI/setROI/getImageWidth act on the CORE
        # camera, not on a label -- on 2026-09-06 this loop set blue's mode and
        # then wrote blue's ROI onto RED, because Core.Camera was still
        # Kinetix_red from the .cfg. getROI(label) is per-camera and reads
        # correctly, which is what made the mismatch visible instead of silent.
        core.setCameraDevice(cam)
        # Port before Binning before ROI. Binning rescales an ROI already set
        # (a 512 px ROI became 256 px when 2x2 was applied after it), and a
        # Port change resets more than it looks like -- see disable_pp's note.
        core.setProperty(cam, "Port", port)
        core.waitForDevice(cam)
        core.setProperty(cam, "Binning", binning)
        core.waitForDevice(cam)
        core.clearROI()
        w, h = core.getImageWidth(), core.getImageHeight()
        if roi_px < min(w, h):
            core.setROI((w - roi_px) // 2, (h - roi_px) // 2, roi_px, roi_px)
            core.waitForDevice(cam)
        core.setExposure(exposure_ms)
        out[cam] = {
            "Port": str(core.getProperty(cam, "Port")),
            "ReadoutRate": str(core.getProperty(cam, "ReadoutRate")),
            "PixelType": str(core.getProperty(cam, "PixelType")),
            "Binning": str(core.getProperty(cam, "Binning")),
            "ROI": list(core.getROI(cam)),
            "frame_px": [core.getImageWidth(), core.getImageHeight()],
            "exposure_ms": float(core.getExposure()),
        }
        print(f"  {cam}: {out[cam]['Port']} / {out[cam]['PixelType']} / bin "
              f"{out[cam]['Binning']} / frame {out[cam]['frame_px']} / "
              f"{out[cam]['exposure_ms']:.2f} ms")
    core.setCircularBufferMemoryFootprint(buffer_mb)
    out["circular_buffer"] = {
        "footprint_mb": int(core.getCircularBufferMemoryFootprint()),
        "capacity_frames": int(core.getBufferTotalCapacity()),
    }
    print(f"  circular buffer: {out['circular_buffer']['footprint_mb']} MB = "
          f"{out['circular_buffer']['capacity_frames']} frames")
    return out


def light(core, device: str, line: str, per_mille: int, all_lines: list[str]) -> None:
    """Enable exactly one line. `State` is the engine's master shutter -- with
    State = 0 nothing comes out however the line is set, and Core.Shutter is
    LightEngine rather than Aura so autoshutter never opens it either."""
    for other in all_lines:
        core.setProperty(device, other, "0")
        core.setProperty(device, f"{other}_Intensity", "0")
    if line:
        core.setProperty(device, f"{line}_Intensity", str(int(per_mille)))
        core.setProperty(device, line, "1")
    core.setProperty(device, "State", "1" if line else "0")
    core.waitForDevice(device)


def snap_both(core, cameras: list[str], n_frames: int) -> dict:
    out = {}
    for cam in cameras:
        core.setCameraDevice(cam)
        frames = []
        for _ in range(n_frames):
            core.snapImage()
            frames.append(np.asarray(core.getImage(), dtype=np.float64))
        out[cam] = np.stack(frames).mean(axis=0)
    return out


def _signal(frame: np.ndarray, dark: np.ndarray) -> float:
    """Median rise above the dark frame -- offset-free and pattern-free."""
    return float(np.median(frame) - np.median(dark))


def verify_splitter(core, args, cameras: list[str]) -> dict:
    """Light one line at a time, read both cameras, identify the splitter.

    The four numbers are a fingerprint. Only position 1 puts each line on its
    own camera; the other two positions send everything to one body regardless
    of wavelength, and cannot fake this pattern.
    """
    engine = args.light_device
    lines = ["UV", "CYAN", "GREEN", "RED", "NIR"]

    light(core, engine, "", 0, lines)
    print("\n  dark reference (light off)")
    dark = snap_both(core, cameras, max(5, args.n_frames // 2))

    table: dict = {}
    for line, per_mille in (("CYAN", args.cyan), ("GREEN", args.green)):
        light(core, engine, line, per_mille, lines)
        time.sleep(args.settle_s)
        print(f"  {line} alone at {per_mille}/1000")
        got = snap_both(core, cameras, args.n_frames)
        table[line] = {cam: _signal(got[cam], dark[cam]) for cam in cameras}
        for cam in cameras:
            print(f"      {cam:14s} {table[line][cam]:+9.2f} ADU above dark")
    light(core, engine, "", 0, lines)

    blue_cam, red_cam = ARMS["blue"]["camera"], ARMS["red"]["camera"]
    cyan_b, cyan_r = table["CYAN"][blue_cam], table["CYAN"][red_cam]
    green_b, green_r = table["GREEN"][blue_cam], table["GREEN"][red_cam]

    # A camera counts as lit only well clear of the noise on a median of a
    # multi-frame average; 2 ADU is generous against the ~0.1 ADU the
    # anti-Stokes controls reached on 2026-09-06.
    lit = lambda v: v > 2.0
    result: dict = {"table": table}
    if lit(cyan_b) and lit(green_r) and green_r > green_b and cyan_b > cyan_r:
        result["splitter_position"] = 1
        result["verdict"] = (
            "SPLITTER IS AT POSITION 1 (DM A561LP) -- correct for this run. CYAN "
            "lands on Kinetix_blue and GREEN on Kinetix_red, which is only "
            "possible with a wavelength-splitting element in the beam."
        )
    elif lit(cyan_b) and lit(green_b) and not lit(cyan_r) and not lit(green_r):
        result["splitter_position"] = 0
        result["verdict"] = (
            "SPLITTER IS AT POSITION 0 (100/0 mirror) -- BOTH lines land on "
            "Kinetix_blue and Kinetix_red sees nothing at all. This is the state "
            "that cost the 2026-09-04 session. Move it to position 1 in NIS."
        )
    elif lit(cyan_r) and lit(green_r) and not lit(cyan_b) and not lit(green_b):
        result["splitter_position"] = 2
        result["verdict"] = (
            "SPLITTER IS AT POSITION 2 (open) -- BOTH lines land on Kinetix_red "
            "and Kinetix_blue sees nothing. Fine for single-camera red imaging, "
            "useless for two colours. Move it to position 1 in NIS."
        )
    else:
        result["splitter_position"] = None
        result["verdict"] = (
            "PATTERN DOES NOT MATCH ANY SPLITTER POSITION. Before blaming the "
            "splitter, check the things in series with it: both turret shutters, "
            "CSUW1-Shutter, CSUW1-Port = blue_red, and that each wheel is on its "
            "own filter. A closed shutter starves both cameras equally and looks "
            "like nothing at all."
        )

    # Off-diagonal terms = measured crosstalk. The optics gate can only
    # approximate these from parametric spectra.
    if lit(cyan_b) and lit(green_r):
        result["crosstalk_measured"] = {
            "green_into_blue_pct": 100.0 * green_b / green_r if green_r else None,
            "cyan_into_red_pct": 100.0 * cyan_r / cyan_b if cyan_b else None,
            "note": (
                "Fraction of each line's signal appearing on the WRONG camera, "
                "measured. The optics gate reports its crosstalk margin as "
                "evidence: assumed because it computes from parametric spectra; "
                "these two numbers are the real thing for this exact path. Note "
                "they include the red bead's own emission tail, which the "
                "2026-09-06 four-band test measured at 17.2% in 677-701 nm."
            ),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Set up and verify the dual-camera two-colour run.")
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--objective", default=EXPECTED_OBJECTIVE,
                   help="the objective this run expects; verified, never written")
    p.add_argument("--port", default="Dynamic Range",
                   help="readout mode, applied to BOTH cameras")
    p.add_argument("--binning", default="2x2")
    p.add_argument("--roi", type=int, default=512, help="centred square ROI in BINNED px")
    p.add_argument("--exposure-ms", type=float, default=1.8)
    p.add_argument("--buffer-mb", type=int, default=800,
                   help="circular-buffer footprint; L3.4–L3.7 wants 5 s = ~1000 frames")
    p.add_argument("--light-device", default="Aura")
    p.add_argument("--cyan", type=int, default=200, help="CYAN per-mille (0-1000) for the green arm")
    p.add_argument("--green", type=int, default=500, help="GREEN per-mille (0-1000) for the red arm")
    p.add_argument("--n-frames", type=int, default=10)
    p.add_argument("--settle-s", type=float, default=0.5)
    p.add_argument("--dry-run", action="store_true", help="preflight only: no writes, no light")
    p.add_argument("--fix-path", action="store_true", help="shutters, CSUW1-Port, both filter wheels")
    p.add_argument("--match-cameras", action="store_true", help="one mode/binning/ROI/exposure on both")
    p.add_argument("--disable-pp", action="store_true", help="post-processing off on BOTH cameras, left off")
    p.add_argument("--verify-splitter", action="store_true",
                   help="light one line at a time and identify the splitter position")
    p.add_argument("--force", action="store_true", help="proceed despite preflight problems")
    p.add_argument("--out", default=None, help="directory for the JSON report")
    args = p.parse_args(argv)

    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"loading {args.cfg}")
    core.loadSystemConfiguration(args.cfg)
    cameras = [ARMS["blue"]["camera"], ARMS["red"]["camera"]]

    report: dict = {
        "script": Path(__file__).name,
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cfg": args.cfg,
        "expected_objective": args.objective,
        "arms": {k: {kk: vv for kk, vv in v.items()} for k, v in ARMS.items()},
    }

    problems, observed = preflight(core, args.objective)
    report["observed"] = observed
    report["preflight_problems"] = problems

    print("\npath state")
    for key, value in observed.items():
        if key != "cameras":
            print(f"  {key:34s} {value}")
    print("  cameras")
    for cam, info in observed["cameras"].items():
        print(f"    {cam}")
        for k, v in info.items():
            print(f"      {k:16s} {v}")

    if problems:
        print("\npreflight problems")
        for problem in problems:
            print(f"  [FAIL] {problem}")
    else:
        print("\npreflight: clean")

    if args.dry_run:
        print("\n--dry-run: nothing written, no light enabled.")
        return 0 if not problems else 1

    if args.fix_path:
        print("\n--fix-path")
        report["path_changed"], _ = fix_path(core)
    # ⚠ ORDER IS LOAD-BEARING: --match-cameras BEFORE --disable-pp. Changing a
    # camera's `Port` RESETS its post-processing block back to enabled.
    # Measured 2026-09-06: with disable_pp running first, Kinetix_blue's six PP
    # entries read ENABLED = Yes again in the very same session after its Port
    # moved Sensitivity -> Dynamic Range, while Kinetix_red -- already in
    # Dynamic Range, so no mode change -- stayed off. Disabling post-processing
    # is therefore the LAST thing done to a camera.
    if args.match_cameras:
        print("\n--match-cameras")
        report["camera_setup"] = match_cameras(
            core, cameras, args.port, args.binning, args.roi,
            args.exposure_ms, args.buffer_mb,
        )
    if args.disable_pp:
        print("\n--disable-pp (both cameras; must follow any Port change)")
        report["pp_changed"] = disable_pp(core, cameras)

    if args.fix_path or args.disable_pp or args.match_cameras:
        problems, observed = preflight(core, args.objective)
        report["observed"] = observed
        report["preflight_problems"] = problems
        if problems:
            print("\nremaining preflight problems")
            for problem in problems:
                print(f"  [FAIL] {problem}")
        else:
            print("\npreflight after changes: clean")

    if args.verify_splitter:
        if problems and not args.force:
            print("\nREFUSED to run --verify-splitter with preflight problems "
                  "outstanding: a closed shutter or a wrong wheel produces exactly "
                  "the same 'camera sees nothing' signature as the splitter, and "
                  "the test would blame the wrong element. Fix them, or --force.")
            return 1
        print("\n" + "=" * 72)
        print("SPLITTER IDENTIFICATION -- one line at a time, both cameras")
        print("=" * 72)
        try:
            report["splitter"] = verify_splitter(core, args, cameras)
        finally:
            for line in ("UV", "CYAN", "GREEN", "RED", "NIR"):
                try:
                    core.setProperty(args.light_device, line, "0")
                    core.setProperty(args.light_device, f"{line}_Intensity", "0")
                except Exception:
                    pass
            try:
                core.setProperty(args.light_device, "State", "0")
            except Exception:
                pass
            print("\n  light OFF")
        print(f"\n  -> {report['splitter']['verdict']}")
        xt = report["splitter"].get("crosstalk_measured")
        if xt:
            print(f"\n  MEASURED crosstalk (the gate can only approximate this):")
            print(f"    GREEN leaking into Kinetix_blue: {xt['green_into_blue_pct']:.2f}%")
            print(f"    CYAN  leaking into Kinetix_red : {xt['cyan_into_red_pct']:.2f}%")

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / "dualcam-setup.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nreport: {path}")

    print("\nremaining, and none of it is software:")
    print("  · objective at the stand if the preflight flagged it (SAFETY.md §2)")
    print("  · splitter to position 1 in NIS if --verify-splitter says otherwise")
    print("  · re-verify the tweezers px->um calibration -- an objective change")
    print("    silently invalidates it and nothing reports it over TCP")
    print("  · a GREEN-ONLY frame through detection.cli from-frame: the exposure")
    print("    above is the RED bead's, scaled from 4x")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
