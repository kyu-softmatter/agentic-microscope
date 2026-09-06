r"""Live 2x2 dual-camera view: detect, classify and track particle counts.

    python config/session/live_dualcam_view.py --cyan 3 --green 40 --exposure-ms 10
    python config/session/live_dualcam_view.py --save-composite D:\data\panel.png --frames 3

    panel 1 (top-left)      Kinetix_red   -- Abvigen red, GREEN line, 589-610 nm
    panel 2 (top-right)     Kinetix_blue  -- Dragon Green, CYAN line, 510-530 nm
    panel 3 (bottom-left)   overlay, red + blue, with co-located marks
    panel 4 (bottom-right)  counts against time

FIELD SELECTION AND SETUP ONLY -- NEVER A MEASUREMENT
-----------------------------------------------------
This samples the newest frame from each camera in turn at a few Hz and drops
everything in between, by design. No MSD, no photometry and no rate can come
out of it; `config/session/run_wall_diffusion.py` drains every frame with its
timestamp for that. The same warning is on `live_view.py`, and one measured
consequence is worth repeating: a live view running during an acquisition
degraded timing ~20x (TCP round trip 2.93 ms quiet against 51.4 ms with the
viewer up). CLOSE THIS BEFORE A RUN YOU INTEND TO MEASURE FROM.

⚠⚠ PANEL 3 IS NOT REGISTERED, AND THAT IS NOT A DETAIL
-------------------------------------------------------
The two images come from two SEPARATE CAMERA BODIES on the two sides of the
DM A561LP splitter. Nothing on this instrument has ever measured the transform
between them, and there are three independent unknowns:

    translation   a few px to tens of px of offset, from camera mounting
    handedness    RESOLVED 2026-09-06, by operator observation: the blue image
                  is UPSIDE DOWN relative to the red one, so `--flip-y` is the
                  default. This is the expected signature of the arm it sits
                  on -- Kinetix_blue is the REFLECT side of the DM A561LP
                  splitter and a reflection reverses handedness -- which is why
                  it is worth trusting rather than treating as one person's
                  impression. The axis was NOT predictable from the record: the
                  fold geometry is written down nowhere.
    scale/rotation both bodies are Kinetix22 with 6.5 um pixels behind one
                  objective, so scale should be 1.000 and rotation ~0 -- but
                  "should" is doing the work in that sentence.

So a particle at (x, y) on red is NOT at (x, y) on blue until someone measures
it. The vertical flip is now applied; TRANSLATION AND SCALE ARE STILL
UNMEASURED, so the alignment remains uncalibrated. Until they are measured:

  · the overlay is a VISUAL AID for choosing a field, not evidence of
    co-localization;
  · `co-located` counts in panel 4 are labelled `unregistered` and must not be
    read as "one particle seen in both channels";
  · `--dx/--dy/--flip-x/--flip-y` let you align it BY EYE and the arrow keys
    nudge live. That is a working alignment, not a calibration -- it is not
    written anywhere and does not survive the session.

The honest fix is a registration target imaged in both channels. Cross-
correlating the two live images will NOT do it: the two species are different
particles in different places, so there is no common signal to correlate. What
would work is one object visible in BOTH bands -- the red bead's own 17.2%
emission tail into 677-701 nm (measured 2026-09-06) means a red bead is
faintly visible on a 647 filter, and a bead-on-both-cameras field would give
the transform directly.

CLASSIFICATION ("sorting")
--------------------------
Each detection is assigned by WHICH CAMERA SAW IT, which is the whole point of
straddling the splitter:

    RED    on Kinetix_red only    -> abvigen-red-5um-cooh
    GREEN  on Kinetix_blue only   -> bangs-dragongreen-5um-cooh
    BOTH   within --match-px      -> AMBIGUOUS, and reported as such rather
                                     than as a species. Three things produce
                                     it and this view cannot separate them:
                                     misregistration (above), a genuine
                                     aggregate of one of each, or channel
                                     crosstalk. The optics gate puts computed
                                     crosstalk at its scale maximum for this
                                     pair, so misregistration is the leading
                                     explanation while panel 3 is unaligned.

Detections are sorted by integrated brightness, brightest first, and the ID
drawn on each particle is that rank -- so `#1` is the brightest particle in the
frame and the labels are stable in meaning even as particles diffuse.

LIGHT, PER ARM AND INDEPENDENTLY
--------------------------------
The two arms need different levels, and the factor is large: measured
2026-09-06 at 10 ms and bin 2x2, Dragon Green on CYAN gives ~15,400 ADU per
per-mille against ~527 for the Abvigen red bead on GREEN -- ~29x. Dragon Green
saturates the 16-bit ceiling at CYAN 8/1000. So the defaults here are CYAN 3
and GREEN 40, they are separate flags, and they are separately adjustable live:

    1 / 2   CYAN  down / up      (the green-bead arm)
    3 / 4   GREEN down / up      (the red-bead arm)
    arrows  nudge the panel-3 alignment
    x / y   toggle the panel-3 mirror on that axis
    s       save the current composite next to --save-composite
    q, Esc  quit -- takes the light down on the way out

A channel over 95% of the 16-bit ceiling is drawn with a SATURATED banner,
because above that a peak is a lower bound rather than a measurement and a
clipped bead has a flat top that destroys its centroid.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ⚠ BINNING AND PIXEL SIZE, MEASURED 2026-09-06.
# `core.getPixelSizeUm()` ALREADY ACCOUNTS FOR BINNING: with the 100x-1x preset
# it returns 0.065 at bin 1x1, 0.130 at 2x2 and 0.260 at 4x4. So it must be read
# AFTER the binning is set and must NOT be multiplied by the bin factor.
# This file used to read it before setting binning and then multiply by 2, which
# gave the right 0.130 only because of that statement order -- load a config that
# already had 2x2, or reorder these two blocks, and it silently became 0.260.
# Reading it after and not scaling removes the ordering dependency entirely.
#
# `trap_from_tracking.pixel_size_um()` used to behave the OPPOSITE way -- it
# reads the table in data/pixel_size.yaml, which is keyed on objective x
# intermediate magnification only and so returned 0.065 at ANY binning. Fixed
# 2026-09-06: it now multiplies by the bin factor, names the binning in its
# provenance string, refuses non-square binning, and cross-checks against
# getPixelSizeUm(). The two paths now agree or refuse.

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_twocolour.cfg"


def _trap_origin_offset_um() -> tuple[float, float] | None:
    """Where trap (0, 0) lands, as an offset from the frame centre in image um.

    Imported from `config/tweezers/trap_sequence.py` rather than copied, so
    there is one source of truth -- that module measured it and owns it.
    MEASURED 2026-09-04: five beads ramped to the trap origin all came to rest
    at (584.42, 584.38) +- (0.68, 0.48) px in a 1200x1200 ROI at 0.065 um/px,
    i.e. (-15.58, -15.62) px from centre. The two axes agree to 0.04 px against
    a 1.30 px per-hold scatter, which is what makes it a systematic offset
    rather than five coincidences.

    Held in um because it is a physical place: the pixel offset scales with the
    pixel size, so it stays correct at this session's 0.130 um/px even though
    it was taken at 0.065.
    """
    import importlib.util
    src = REPO / "config" / "tweezers" / "trap_sequence.py"
    try:
        spec = importlib.util.spec_from_file_location("_trap_sequence", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return tuple(mod.TRAP_ORIGIN_OFFSET_UM)
    except Exception as exc:
        print(f"  ! could not read TRAP_ORIGIN_OFFSET_UM from {src}: {exc}",
              file=sys.stderr)
        return None

LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]
CEILING = 65535.0
CLIP_FRACTION = 0.95

# camera, Aura line, species, panel label, BGR draw colour
RED_ARM = ("Kinetix_red", "GREEN", "abvigen-red", "RED", (60, 60, 255))
BLUE_ARM = ("Kinetix_blue", "CYAN", "bangs-dragongreen", "GREEN", (60, 230, 60))


def light_off(core, engine: str) -> None:
    for line in LINES:
        for prop, value in ((line, "0"), (f"{line}_Intensity", "0")):
            try:
                core.setProperty(engine, prop, value)
            except Exception:
                pass
    try:
        core.setProperty(engine, "State", "0")
    except Exception:
        pass


def set_levels(core, engine: str, cyan: int, green: int) -> None:
    """Both lines, independently. `State` is the engine's master shutter --
    without it nothing comes out however the lines are set."""
    for line in LINES:
        core.setProperty(core_engine := engine, line, "0")
        core.setProperty(core_engine, f"{line}_Intensity", "0")
    for line, per_mille in (("CYAN", cyan), ("GREEN", green)):
        if per_mille > 0:
            core.setProperty(engine, f"{line}_Intensity", str(int(per_mille)))
            core.setProperty(engine, line, "1")
    core.setProperty(engine, "State", "1" if (cyan > 0 or green > 0) else "0")


def bead_area_window(pixel_um: float, bead_um: float) -> tuple[int, int]:
    r = 0.5 * bead_um / max(pixel_um, 1e-9)
    area = np.pi * r * r
    return max(2, int(0.25 * area)), int(4.0 * area)


def detect(frame: np.ndarray, area_px: tuple[int, int], n_sigma: float = 8.0) -> list[dict]:
    """Particles in one frame, sorted by integrated brightness, brightest first.

    Local-background subtraction rather than a global threshold: on a widefield
    field the illumination profile alone spans tens of percent, so a global cut
    selects the bright middle of the field instead of the particles in it.
    """
    import cv2

    f32 = frame.astype(np.float32)
    smooth = cv2.GaussianBlur(f32, (0, 0), 15)
    residual = f32 - smooth
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0
    mask = (residual > n_sigma * scale).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)

    lo, hi = area_px
    out: list[dict] = []
    for i in range(1, n):
        area = int(stats[i, 4])
        if not (lo <= area <= hi):
            continue
        sel = labels == i
        out.append({
            "x": float(centroids[i][0]),
            "y": float(centroids[i][1]),
            "area": area,
            "peak": float(residual[sel].max()),
            "flux": float(residual[sel].sum()),
        })
    out.sort(key=lambda d: -d["flux"])
    for rank, d in enumerate(out, start=1):
        d["rank"] = rank
    return out


def median_dia_um(dets: list[dict], pixel_um: float) -> float:
    """Median equivalent-disc diameter of the detections, in um.

    An independent size check the operator can watch live, and a cheap guard
    against the detector drifting off beads onto debris: both species here are
    ~5 um. Measured 2026-09-06 at 8 sigma it reads 5.58 um on the red arm and
    5.11 um on the blue, against 5.0 nominal and the 4.95 um Bangs lot mean --
    a few percent high, because the threshold contour sits outside the bead's
    physical edge rather than on it. Read it as a consistency check, not a
    sizing measurement.
    """
    if not dets:
        return 0.0
    areas = np.array([d["area"] for d in dets], float)
    return float(np.median(2.0 * np.sqrt(areas / np.pi)) * pixel_um)


def to_8bit(frame: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.9) -> np.ndarray:
    lo, hi = np.percentile(frame, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((frame - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def transform_point(pt, shape, dx: int, dy: int, flip_x: bool, flip_y: bool):
    """Put a point through the same transform `transform()` puts the image
    through, so an overlay drawn in RED-camera coordinates lands in the right
    place on a flipped/rolled BLUE panel instead of the mirrored one."""
    h, w = shape
    x, y = pt
    if flip_x:
        x = (w - 1) - x
    if flip_y:
        y = (h - 1) - y
    return (x + dx, y + dy)


def transform(frame: np.ndarray, dx: int, dy: int, flip_x: bool, flip_y: bool) -> np.ndarray:
    out = frame
    if flip_x:
        out = out[:, ::-1]
    if flip_y:
        out = out[::-1, :]
    if dx or dy:
        out = np.roll(np.roll(out, dy, axis=0), dx, axis=1)
    return out


#: Half-extent of the addressable AOD square, um, at 100x. Operator statement
#: 2026-09-06: "trapping area is always square, the center of the square is
#: located in the middle of the camera view, the square size is around
#: (-40um to 40um) in x and y." Mirrored into
#: config/tweezers/active-microrheology-drive.yaml > trapping_range, which
#: carries the full reasoning and the objective caveat.
TRAP_HALF_RANGE_UM = 40.0


def px_to_trap_um(px, p0_px, um_per_px) -> tuple[float, float]:
    """Camera pixels -> trap micrometres.

    The inverse of `provisional_transform`'s `px = p0 + diag([1,-1])/um_per_px @ um`,
    and it has NO fitted parameter in it. Three facts remove them all:

      origin      trap (0,0) is the camera field centre -- stated by the
                  operator and independently measured to ~1 um over 5 holds
                  (TRAP_ORIGIN_OFFSET_UM).
      handedness  y is inverted (image y runs down), confirmed by 4 ramps in 4
                  quadrants following home at 98.6-99.8%.
      scale       the Tweez software commands MICROMETRES AT THE SAMPLE, so
                  trap um -> image um is 1:1 and the pixel size is the whole
                  conversion. Which is why binning is not an obstacle: it
                  changes um_per_px and nothing else.
    """
    return ((px[0] - p0_px[0]) * um_per_px, -(px[1] - p0_px[1]) * um_per_px)


def draw_trap_range(bgr, p0_px, size: int, frame_w: int, um_per_px: float,
                    half_um: float = TRAP_HALF_RANGE_UM) -> None:
    """The square the trap can actually reach, centred on trap (0,0).

    Worth drawing rather than merely knowing: a bead outside it cannot be
    trapped at all, and points commanded outside are CLIPPED TO THE EDGE
    SILENTLY, returning 0 like everything else on this interface.
    """
    import cv2
    s = size / float(frame_w)
    half_px = (half_um / um_per_px) * s
    cx, cy = p0_px[0] * s, p0_px[1] * s
    a = (int(cx - half_px), int(cy - half_px))
    b = (int(cx + half_px), int(cy + half_px))
    cv2.rectangle(bgr, a, b, (120, 120, 255), 1, cv2.LINE_AA)
    # Label under the BOTTOM edge: above the top edge it collided with the
    # per-panel stats block, which now runs to ~7 lines.
    cv2.putText(bgr, f"trap range +-{half_um:g}um", (max(2, a[0] + 3), min(size - 4, b[1] + 13)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.34, (120, 120, 255), 1, cv2.LINE_AA)


def draw_trap_marker(bgr, p0_px, size: int, frame_w: int) -> None:
    """Crosshair at the trap origin, in RED-CAMERA coordinates.

    Drawn only on the red panel and the overlay, and deliberately NOT on the
    blue panel: the offset was measured on Kinetix_red (2026-09-04 used the
    single-camera red config), and putting it on the blue image would need the
    inter-camera translation, which is exactly the part still unmeasured.
    """
    import cv2
    s = size / float(frame_w)
    cx, cy = int(p0_px[0] * s), int(p0_px[1] * s)
    for a, b in (((cx - 11, cy), (cx - 4, cy)), ((cx + 4, cy), (cx + 11, cy)),
                 ((cx, cy - 11), (cx, cy - 4)), ((cx, cy + 4), (cx, cy + 11))):
        cv2.line(bgr, a, b, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(bgr, (cx, cy), 3, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(bgr, "trap 0,0", (cx + 13, cy + 4), cv2.FONT_HERSHEY_SIMPLEX,
                0.34, (0, 255, 255), 1, cv2.LINE_AA)


def draw_panel(gray8: np.ndarray, dets: list[dict], colour, title: str,
               stats_lines: list[str], size: int, saturated: bool,
               trap_px=None, um_per_px: float = 0.0) -> np.ndarray:
    import cv2

    h, w = gray8.shape
    # Resize FIRST, then annotate in display coordinates. Drawing on the full
    # 1200 px frame and shrinking it to 440 divides every circle and glyph by
    # 2.7, which made the markers thinner than a line and smaller than the
    # beads they were marking -- they read as separate small objects sitting
    # next to unmarked beads.
    bgr = cv2.cvtColor(cv2.resize(gray8, (size, size), interpolation=cv2.INTER_AREA),
                       cv2.COLOR_GRAY2BGR)
    s = size / float(w)
    for d in dets:
        r = max(3, int(np.sqrt(d["area"] / np.pi) * s))
        c = (int(d["x"] * s), int(d["y"] * s))
        # A bead the trap cannot reach is drawn thin and unlabelled: it is not a
        # candidate, and giving it a number invites reading off the wrong list.
        reach_rank = d.get("reach_rank")
        if reach_rank:
            cv2.circle(bgr, c, r, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(bgr, f"R{reach_rank}", (c[0] + r + 2, c[1] - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.circle(bgr, c, r, colour, 1, cv2.LINE_AA)
    if trap_px is not None:
        if um_per_px:
            draw_trap_range(bgr, trap_px, size, w, um_per_px)
        draw_trap_marker(bgr, trap_px, size, w)
    cv2.rectangle(bgr, (0, 0), (size - 1, size - 1), colour, 1)
    cv2.putText(bgr, title, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)
    for i, line in enumerate(stats_lines):
        cv2.putText(bgr, line, (8, 42 + 17 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (220, 220, 220), 1, cv2.LINE_AA)
    if saturated:
        cv2.rectangle(bgr, (0, 0), (size - 1, size - 1), (0, 200, 255), 3)
        cv2.putText(bgr, "SATURATED - peak is a lower bound",
                    (8, size - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (0, 200, 255), 1, cv2.LINE_AA)
    return bgr


def draw_overlay(red8: np.ndarray, blue8: np.ndarray, matched: list[tuple],
                 size: int, dx: int, dy: int, flip_x: bool, flip_y: bool,
                 n_amb: int, trap_px=None, um_per_px: float = 0.0) -> np.ndarray:
    import cv2

    h, w = red8.shape
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:, :, 2] = red8                      # red channel  <- Kinetix_red
    bgr[:, :, 1] = blue8                     # green channel <- Kinetix_blue
    for (rx, ry) in matched:
        cv2.circle(bgr, (int(rx), int(ry)), 14, (0, 220, 255), 1, cv2.LINE_AA)
    bgr = cv2.resize(bgr, (size, size), interpolation=cv2.INTER_AREA)
    if trap_px is not None and um_per_px:
        # Exact here: panel 3 is composed in RED-camera coordinates, which is
        # the frame the trap origin was measured in.
        draw_trap_range(bgr, trap_px, size, w, um_per_px)
        draw_trap_marker(bgr, trap_px, size, w)
    cv2.rectangle(bgr, (0, 0), (size - 1, size - 1), (200, 200, 200), 1)
    cv2.putText(bgr, "3  overlay  red=Abvigen  green=DragonGreen", (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.putText(bgr, f"dx={dx} dy={dy} flipX={int(flip_x)} flipY={int(flip_y)}",
                (8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(bgr, "UNREGISTERED - alignment is by eye, not calibrated",
                (8, size - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(bgr, f"{n_amb} ambiguous (NOT co-localization)", (8, size - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 255), 1, cv2.LINE_AA)
    return bgr


def draw_timeseries(hist: deque, size: int, window_s: float) -> np.ndarray:
    import cv2

    bgr = np.full((size, size, 3), 18, np.uint8)
    cv2.rectangle(bgr, (0, 0), (size - 1, size - 1), (200, 200, 200), 1)
    cv2.putText(bgr, "4  counts vs time", (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (230, 230, 230), 1, cv2.LINE_AA)
    if len(hist) < 2:
        cv2.putText(bgr, "collecting...", (8, 44), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (160, 160, 160), 1, cv2.LINE_AA)
        return bgr

    pad_l, pad_r, pad_t, pad_b = 40, 10, 48, 26
    plot_w, plot_h = size - pad_l - pad_r, size - pad_t - pad_b
    t = np.array([h["t"] for h in hist], float)
    t0, t1 = t[0], max(t[-1], t[0] + 1e-6)
    series = [
        ("red", np.array([h["n_red"] for h in hist], float), (60, 60, 255)),
        ("green", np.array([h["n_green"] for h in hist], float), (60, 230, 60)),
        ("ambig", np.array([h["n_amb"] for h in hist], float), (0, 200, 255)),
    ]
    ymax = max(4.0, max(float(s[1].max()) for s in series) * 1.15)

    for frac in (0.0, 0.5, 1.0):
        y = int(pad_t + plot_h * (1 - frac))
        cv2.line(bgr, (pad_l, y), (pad_l + plot_w, y), (55, 55, 55), 1)
        cv2.putText(bgr, f"{int(ymax*frac):>3d}", (6, y + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (140, 140, 140), 1, cv2.LINE_AA)
    for name, vals, colour in series:
        pts = [(int(pad_l + plot_w * (tt - t0) / (t1 - t0)),
                int(pad_t + plot_h * (1 - v / ymax))) for tt, v in zip(t, vals)]
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(bgr, a, b, colour, 1, cv2.LINE_AA)
    for i, (name, vals, colour) in enumerate(series):
        cv2.putText(bgr, f"{name} {int(vals[-1])}", (pad_l + 4 + i * 74, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, colour, 1, cv2.LINE_AA)
    cv2.putText(bgr, f"last {t1-t0:.0f} s of {window_s:.0f} s window",
                (pad_l, size - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                (150, 150, 150), 1, cv2.LINE_AA)
    return bgr


def match_across(red: list[dict], blue: list[dict], tol_px: float) -> list[tuple]:
    """Greedy nearest-neighbour pairs within `tol_px`. Deliberately crude --
    while panel 3 is unregistered a careful matcher would only lend false
    authority to pairs whose coordinates are not comparable yet."""
    if not red or not blue:
        return []
    out, used = [], set()
    for r in red:
        best, best_d = None, tol_px
        for j, b in enumerate(blue):
            if j in used:
                continue
            d = ((r["x"] - b["x"]) ** 2 + (r["y"] - b["y"]) ** 2) ** 0.5
            if d < best_d:
                best, best_d = j, d
        if best is not None:
            used.add(best)
            out.append((r["x"], r["y"]))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--no-preset", action="store_true")
    p.add_argument("--light-device", default="Aura")
    p.add_argument("--cyan", type=int, default=3, help="CYAN per-mille -> Kinetix_blue (Dragon Green)")
    p.add_argument("--green", type=int, default=40, help="GREEN per-mille -> Kinetix_red (Abvigen red)")
    p.add_argument("--step", type=int, default=1, help="per-mille per keypress for CYAN")
    p.add_argument("--step-green", type=int, default=5, help="per-mille per keypress for GREEN")
    p.add_argument("--exposure-ms", type=float, default=10.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--roi", type=int, default=0, help="centred square ROI in binned px; 0 = full")
    p.add_argument("--bead-um", type=float, default=5.0)
    p.add_argument("--panel", type=int, default=440, help="one panel's on-screen size, px")
    p.add_argument("--match-px", type=float, default=15.0)
    p.add_argument("--dx", type=int, default=0)
    p.add_argument("--dy", type=int, default=0)
    # flip_y DEFAULTS TRUE, on operator observation 2026-09-06: the blue image
    # is upside down relative to the red one. That is the expected signature of
    # the arm it sits on -- Kinetix_blue is the REFLECT side of the DM A561LP
    # splitter, and a reflection reverses handedness. So this is not a nuisance
    # correction, it is the one registration unknown of the three that is now
    # settled. --no-flip-y to disable.
    p.add_argument("--flip-x", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--flip-y", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--alternate", action=argparse.BooleanOptionalAction, default=True,
                   help="STROBE the two lines instead of running both at once: CYAN "
                        "for the blue frame, GREEN for the red frame. Default ON, "
                        "because with both lit the red camera sees BOTH species -- "
                        "see the crosstalk note in the module docstring.")
    p.add_argument("--sort-on-space", action="store_true",
                   help="SPACE runs the two-species sort on the field as it stands. "
                        "Needs the Tweez GUI up; pass --sort-laser-on to send LASER_ON.")
    p.add_argument("--sort-laser-on", action="store_true")
    p.add_argument("--per-species", type=int, default=3)
    p.add_argument("--slot-x-um", type=float, default=18.0)
    p.add_argument("--isolation-um", type=float, default=8.0)
    p.add_argument("--no-trap-marker", action="store_true",
                   help="do not mark the measured trap origin on the red panel")
    p.add_argument("--strobe-settle-s", type=float, default=0.05,
                   help="settle after switching lines in --alternate mode")
    p.add_argument("--window-s", type=float, default=120.0)
    p.add_argument("--seconds", type=float, default=0.0, help="0 = until q/Esc")
    p.add_argument("--frames", type=int, default=0, help="0 = unlimited; useful with --save-composite")
    p.add_argument("--save-composite", default=None,
                   help="write the composite here each time 's' is pressed, and once at start")
    p.add_argument("--headless", action="store_true",
                   help="no window; only useful with --save-composite and --frames")
    args = p.parse_args(argv)

    import cv2
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"loading {args.cfg}", flush=True)
    core.loadSystemConfiguration(args.cfg)
    if not args.no_preset:
        core.setConfig("TwoColour", "GreenRed-Widefield")
        core.waitForConfig("TwoColour", "GreenRed-Widefield")
        print("applied TwoColour/GreenRed-Widefield", flush=True)

    print(f"objective {core.getStateLabel('Nosepiece')}", flush=True)

    core.setAutoShutter(False)
    for cam, *_ in (RED_ARM, BLUE_ARM):
        core.setCameraDevice(cam)
        core.setProperty(cam, "Binning", args.binning)
        core.clearROI()
        if args.roi:
            w, h = core.getImageWidth(), core.getImageHeight()
            if args.roi < min(w, h):
                core.setROI((w - args.roi) // 2, (h - args.roi) // 2, args.roi, args.roi)
        core.setExposure(args.exposure_ms)

    # Pixel size AFTER the binning is set, and not scaled -- see the note at the
    # top of the file. Read the other way round it is right only by accident.
    binned_um = core.getPixelSizeUm()
    area_px = bead_area_window(binned_um, args.bead_um)
    print(f"{binned_um:.4f} um/px at bin {args.binning}; a {args.bead_um} um bead is "
          f"{args.bead_um/binned_um:.1f} px across -> area window {area_px[0]}-{area_px[1]} px",
          flush=True)

    sort_note = ""
    trap_px = None
    if not args.no_trap_marker:
        off = _trap_origin_offset_um()
        if off is not None:
            h = w = core.getImageWidth()
            trap_px = (w / 2.0 + off[0] / binned_um, h / 2.0 + off[1] / binned_um)
            print(f"trap (0,0) is at pixel ({trap_px[0]:.1f}, {trap_px[1]:.1f}) in the "
                  f"red frame\n  from TRAP_ORIGIN_OFFSET_UM = {off} um, measured "
                  f"2026-09-04 over 5 holds", flush=True)

    cyan, green = args.cyan, args.green
    dx, dy, flip_x, flip_y = args.dx, args.dy, args.flip_x, args.flip_y
    hist: deque = deque()
    win = ("dual-cam live  [SPACE sort  1/2 CYAN  3/4 GREEN  arrows align  "
           "x/y flip  s save  q quit]" if args.sort_on_space else
           "dual-cam live  [1/2 CYAN  3/4 GREEN  arrows align  x/y flip  s save  q quit]")
    sorter = None
    if args.sort_on_space:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "_sort_core", str(REPO / "config" / "session" / "sort_core.py"))
        sorter = _ilu.module_from_spec(_spec)
        sys.modules["_sort_core"] = sorter
        _spec.loader.exec_module(sorter)
        from hardware.optical_tweezers import find_gui_port as _fgp
        _port = _fgp()
        if _port is None:
            print("!! no Tweez GUI answered on 2070-2075 -- SPACE will do nothing",
                  flush=True)
            sorter = None
        else:
            print(f"sort armed: Tweez GUI on port {_port}. Press SPACE to sort the "
                  f"field as it stands.", flush=True)
    t0 = time.perf_counter()
    n_done = 0
    last_composite = None

    try:
        set_levels(core, args.light_device, cyan, green)
        core.waitForDevice(args.light_device)
        print(f"light ON  CYAN {cyan}/1000 -> Kinetix_blue    GREEN {green}/1000 -> Kinetix_red",
              flush=True)
        if not args.headless:
            cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

        while True:
            frames, dets, sat = {}, {}, {}
            for cam, line, species, label, colour in (RED_ARM, BLUE_ARM):
                if args.alternate:
                    # ONE line at a time, each camera read under its OWN line.
                    # Measured 2026-09-06 with the lines separated:
                    #     GREEN only -> red cam 33 beads, blue cam 0
                    #     CYAN  only -> red cam 56 beads, blue cam 29
                    # CYAN alone puts MORE on the red camera than GREEN does,
                    # and since CYAN excites the Abvigen dye more weakly than
                    # GREEN the excess cannot be red beads -- Dragon Green
                    # bleeds into the red arm. It is bright enough to
                    # (29x more signal per per-mille) that its emission tail
                    # past 561 nm gets through the splitter and FF01-595/31.
                    # With both lines lit, 33 red + 29 green ~ the 58 the red
                    # camera reports, so "seen on red" stops meaning "red bead"
                    # and the species assignment collapses.
                    set_levels(core, args.light_device,
                               cyan if line == "CYAN" else 0,
                               green if line == "GREEN" else 0)
                    core.waitForDevice(args.light_device)
                    time.sleep(args.strobe_settle_s)
                core.setCameraDevice(cam)
                core.snapImage()
                f = np.asarray(core.getImage())
                frames[cam] = f
                dets[cam] = detect(f, area_px)
                sat[cam] = float(f.max()) >= CLIP_FRACTION * CEILING  # float() first: uint16 wraps

            red_f, blue_f = frames[RED_ARM[0]], frames[BLUE_ARM[0]]
            h_f, w_f = red_f.shape
            red_d = dets[RED_ARM[0]]

            # ⚠ THE BLUE DETECTIONS MUST GO THROUGH THE SAME TRANSFORM AS THE
            # BLUE IMAGE. They are found on the RAW frame, so their coordinates
            # are in unflipped space; drawing them over a flipped image puts
            # every circle at its mirror position, and -- worse -- handing them
            # to match_across() compares RED coordinates against UNFLIPPED BLUE
            # ones, so the "ambiguous" count was comparing two different frames
            # and meant nothing. Operator spotted the mirrored circles
            # 2026-09-06; the broken matching was the part that did not show.
            blue_d = []
            for d in dets[BLUE_ARM[0]]:
                x, y = transform_point((d["x"], d["y"]), (h_f, w_f),
                                       dx, dy, flip_x, flip_y)
                blue_d.append({**d, "x": x, "y": y})
            blue_d.sort(key=lambda d: -d["flux"])
            for i, d in enumerate(blue_d, start=1):
                d["rank"] = i

            red8 = to_8bit(red_f)
            blue8_raw = to_8bit(blue_f)
            blue8 = transform(blue8_raw, dx, dy, flip_x, flip_y)
            matched = match_across(red_d, blue_d, args.match_px)
            n_amb = len(matched)

            # trap coordinates of the detections, which is the conversion
            # matrix made concrete: reachable count, and where the brightest is.
            # Reachability and a SEPARATE ranking among the reachable set.
            # Ranking the whole frame is the wrong list to read off: on
            # 2026-09-06 the brightest bead in the field sat at trap
            # (-26.5, +43.1) um -- outside the square on y -- so frame-rank #1
            # was not targetable at all. The rank that matters is rank among
            # what the trap can actually reach.
            n_reach, reach = 0, []
            if trap_px:
                for d in red_d:
                    u = px_to_trap_um((d["x"], d["y"]), trap_px, binned_um)
                    d["trap_um"] = u
                    d["reachable"] = (abs(u[0]) <= TRAP_HALF_RANGE_UM
                                      and abs(u[1]) <= TRAP_HALF_RANGE_UM)
                    if d["reachable"]:
                        reach.append(d)
                reach.sort(key=lambda d: -d["flux"])
                for i, d in enumerate(reach, start=1):
                    d["reach_rank"] = i
                n_reach = len(reach)

            t = time.perf_counter() - t0
            hist.append({"t": t, "n_red": len(red_d), "n_green": len(blue_d), "n_amb": n_amb})
            while hist and t - hist[0]["t"] > args.window_s:
                hist.popleft()

            size = args.panel
            p1 = draw_panel(red8, red_d, RED_ARM[4],
                            "1  Kinetix_red  Abvigen-red  GREEN 589-610nm",
                            [f"{len(red_d)} particles   GREEN {green}/1000",
                             f"peak {float(red_f.max()):.0f} ADU  {100.0*float(red_f.max())/CEILING:.1f}% ceil",
                             f"median dia {median_dia_um(red_d, binned_um):.2f} um",
                             (f"{n_reach}/{len(red_d)} inside trap range, sorted:"
                              if trap_px else "")]
                            + [f"  R{d['reach_rank']}  trap ({d['trap_um'][0]:+6.1f},"
                               f" {d['trap_um'][1]:+6.1f}) um  flux {d['flux']:.0f}"
                               for d in reach[:3]],
                            size, sat[RED_ARM[0]], trap_px=trap_px,
                            um_per_px=binned_um)
            # Panel 2 gets the SAME handedness correction as the overlay, or the
            # two panels show mirror images of each other and the operator has
            # to hold the flip in their head while comparing them.
            trap_px_blue = (transform_point(trap_px, (h_f, w_f), dx, dy, flip_x, flip_y)
                            if trap_px else None)
            p2 = draw_panel(transform(blue8_raw, dx, dy, flip_x, flip_y), blue_d, BLUE_ARM[4],
                            "2  Kinetix_blue  DragonGreen  CYAN 510-530nm",
                            [f"{len(blue_d)} particles   CYAN {cyan}/1000",
                             f"peak {float(blue_f.max()):.0f} ADU  {100.0*float(blue_f.max())/CEILING:.1f}% ceil",
                             f"median dia {median_dia_um(blue_d, binned_um):.2f} um",
                             "box assumes zero camera offset"],
                            size, sat[BLUE_ARM[0]], trap_px=trap_px_blue,
                            um_per_px=binned_um)
            p3 = draw_overlay(red8, blue8, matched, size, dx, dy, flip_x, flip_y,
                              n_amb, trap_px=trap_px, um_per_px=binned_um)
            p4 = draw_timeseries(hist, size, args.window_s)
            composite = np.vstack([np.hstack([p1, p2]), np.hstack([p3, p4])])

            n_done += 1
            last_composite = composite
            if not args.headless:
                cv2.imshow(win, composite)
                k = cv2.waitKey(1) & 0xFF
                if k in (ord("q"), 27):
                    break
                if k in (ord("1"), ord("2"), ord("3"), ord("4")) and not args.alternate:
                    pass   # levels re-applied below
                elif k == ord("1"):
                    cyan = max(0, cyan - args.step)
                elif k == ord("2"):
                    cyan = min(1000, cyan + args.step)
                elif k == ord("3"):
                    green = max(0, green - args.step_green)
                elif k == ord("4"):
                    green = min(1000, green + args.step_green)
                elif k == ord("x"):
                    flip_x = not flip_x
                elif k == ord("y"):
                    flip_y = not flip_y
                elif k == 81:
                    dx -= 2
                elif k == 83:
                    dx += 2
                elif k == 82:
                    dy -= 2
                elif k == 84:
                    dy += 2
                elif k == 32 and sorter is not None:
                    # SPACE. The live view already owns both cameras and the
                    # illumination, so the sort runs IN THIS PROCESS on the
                    # field currently displayed -- shelling out to
                    # sort_two_species.py could not work, PVCAM gives a Kinetix
                    # to one owner at a time.
                    from hardware.optical_tweezers import OpticalTweezers as _OT
                    print("\n" + "=" * 66, flush=True)
                    print("SPACE -- sorting the current field", flush=True)
                    print("=" * 66, flush=True)
                    # The sort runs in this thread and owns both cameras,
                    # so the 2x2 composite loop below cannot tick while it
                    # works -- the window would simply freeze. Give the
                    # sort a frame sink and draw ITS frames instead, into
                    # the same window at the same size so nothing resizes.
                    _slog: list[str] = []
                    _spanels: dict = {}

                    def _sort_log(m, _s=_slog):
                        print(m, flush=True)
                        _s.append(str(m).rstrip())

                    def _sort_frame(cam, frame, phase, _p=_spanels, _s=_slog):
                        _g = to_8bit(np.asarray(frame))
                        if cam == BLUE_ARM[0]:
                            # The composite runs blue through this and the sort
                            # view did not, so blue came up un-flipped while a
                            # sort was running -- operator spotted it
                            # 2026-09-05. Display only: the sort's own geometry
                            # goes through blue_to_red(), which applies
                            # (h-1)-y independently of this transform, so the
                            # destinations were never affected.
                            _g = transform(_g, dx, dy, flip_x, flip_y)
                        _p[cam] = _g
                        sz = args.panel
                        canvas = np.zeros((2 * sz, 2 * sz, 3), np.uint8)
                        for i, (nm, colour, ttl) in enumerate((
                                ("Kinetix_red", (90, 90, 255),
                                 "1  Kinetix_red   Abvigen red"),
                                ("Kinetix_blue", (255, 200, 90),
                                 "2  Kinetix_blue  Dragon Green"))):
                            g = _p.get(nm)
                            if g is None:
                                continue
                            canvas[0:sz, i * sz:(i + 1) * sz] = draw_panel(
                                g, [], colour, ttl, [f"SORTING -- {phase}"],
                                sz, False)
                        cv2.putText(canvas, f"SORTING -- {phase}",
                                    (10, sz + 22), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.55, (0, 220, 255), 1, cv2.LINE_AA)
                        cv2.putText(canvas, "unregistered overlay omitted "
                                    "while sorting", (10, 2 * sz - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                                    (150, 150, 150), 1, cv2.LINE_AA)
                        for j, line in enumerate(_s[-14:]):
                            cv2.putText(canvas, line[:112],
                                        (10, sz + 48 + 19 * j),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                                        (210, 210, 210), 1, cv2.LINE_AA)
                        cv2.imshow(win, canvas)
                        cv2.waitKey(1)

                    opts = sorter.SortOpts(
                        per_species=args.per_species, slot_x_um=args.slot_x_um,
                        isolation_um=args.isolation_um, cyan=cyan, green=green,
                        laser_on=args.sort_laser_on,
                        log=_sort_log, on_frame=_sort_frame)
                    try:
                        with _OT(port=_port) as _ot:
                            if _ot.is_ready():
                                res = sorter.sort_until_full(core, _ot, opts)
                                _mv = sum(len(x["moved"]) for x in res["rounds"])
                                _ls = sum(len(x["lost"]) for x in res["rounds"])
                                _cap = res["cap_per_species"] * 2
                                sort_note = (f"{_mv}/{_cap} slots filled in "
                                             f"{len(res['rounds'])} round(s), "
                                             f"{_ls} not moved")
                            else:
                                sort_note = "Tweez GUI not ready"
                                print("  " + sort_note, flush=True)
                    except Exception as exc:
                        sort_note = f"sort failed: {exc}"
                        print(f"  {sort_note}", flush=True)
                    print("=" * 66, flush=True)
                elif k == ord("s") and args.save_composite:  # noqa: SIM114
                    Path(args.save_composite).parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(args.save_composite, composite)
                    print(f"wrote {args.save_composite}", flush=True)

            if not args.alternate:
                set_levels(core, args.light_device, cyan, green)
            if args.frames and n_done >= args.frames:
                break
            if args.seconds and t >= args.seconds:
                break
        # Written at the END, not at the start: panel 4 has no time series to
        # draw until several frames have accumulated, so saving on frame 1
        # always produced a composite with an empty "collecting..." panel.
        if args.save_composite and last_composite is not None:
            Path(args.save_composite).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(args.save_composite, last_composite)
            print(f"wrote {args.save_composite}", flush=True)
    finally:
        light_off(core, args.light_device)
        try:
            import cv2 as _cv2
            _cv2.destroyAllWindows()
        except Exception:
            pass
        print("\nlight OFF", flush=True)

    if hist:
        print(f"\nlast frame: {hist[-1]['n_red']} red, {hist[-1]['n_green']} green, "
              f"{hist[-1]['n_amb']} ambiguous", flush=True)
        print(f"alignment used: dx={dx} dy={dy} flip_x={flip_x} flip_y={flip_y} "
              f"-- BY EYE, not recorded anywhere", flush=True)
        print(f"light left at:  CYAN {cyan}/1000, GREEN {green}/1000", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
