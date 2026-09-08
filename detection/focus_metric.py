"""The focus score, in one place.

Extracted from `config/session/focus_monitor.py` on 2026-09-07, when the
autofocus sequence (`hardware/focus.py`) needed the same metric. Two copies of
a score is how the 4x bead-area window survived into a 100x run and counted
debris instead of beads -- the same failure `data/pixel_size.yaml` warns about
for calibrations held in two files.

THE METRIC
----------
Tenengrad (Sobel gradient energy) normalised by the frame's own median, so it
measures SHARPNESS and not brightness. A defocused fluorescent bead is both
dimmer and softer, and a raw gradient sum would reward "brighter" -- turn the
illuminator up and an unchanged focus would score better. Dividing by the
median squared removes the level, because the gradient of a scaled image scales
with it.

Reported alongside, because one scalar hides the ways focus can lie:

    beads       compact objects whose area falls in a window COMPUTED from the
                effective pixel size and the feature diameter, not a fixed one.
    area        median area of those objects, px. The check on the count: far
                from what the feature should cover means the things being
                counted are not the feature.
    %ceil       brightest pixel as a percentage of the digitiser ceiling. Above
                `CLIP_FRACTION` a peak is a lower bound rather than a
                measurement, and a Tenengrad computed across clipped pixels
                UNDER-reports sharpness -- the gradient is flattened by the
                clip, so a saturated frame can score lower than the same field
                exposed properly and read as defocused. That coupling is why
                the caller is told, and why `score_frame` never silently
                proceeds without a ceiling it can justify.

THE CEILING IS NOT A CONSTANT ON THIS INSTRUMENT
------------------------------------------------
`focus_monitor.py` carries `CEILING = 65535.0`, which is right only while the
camera sits on a 16-bit port. These Kinetix bodies read 12-bit (ceiling 4095)
on their default port; `Port = "Dynamic Range"` is the confirmed 16-bit escape.
So `ceiling_from_bit_depth(core.getImageBitDepth())` is the honest source and
`DEFAULT_CEILING` exists only to keep the older script byte-identical in
behaviour. Pass the measured one wherever a %ceil verdict matters.
"""

from __future__ import annotations

import numpy as np

#: Back-compatibility only -- the value `focus_monitor.py` has always used.
#: New callers pass a ceiling read off the camera. See the module docstring.
DEFAULT_CEILING = 65535.0

#: A pixel this close to the ceiling is already unusable, whether or not it has
#: reached it. `>= CEILING` exactly is the wrong test and gave 0.000% clipping
#: on 2026-09-06 while Kinetix_blue's brightest bead sat at 65,235 ADU -- 99.5%
#: of full scale. kb/calibrations/frame-photometry.yaml puts the usable bar at
#: 95%: above that a peak is a lower bound rather than a measurement, and
#: `detection.cli from-frame` refuses it.
CLIP_FRACTION = 0.95


def ceiling_from_bit_depth(bit_depth: int) -> float:
    """Digitiser ceiling in ADU for a given bit depth.

    `core.getImageBitDepth()` answers 12 on these cameras' default port and 16
    on `Port = "Dynamic Range"`, so this is the one number that must not be
    hard-coded -- a 12-bit frame scored against 65535 reads 6% of ceiling while
    it is actually clipping.
    """
    if not 1 <= int(bit_depth) <= 32:
        raise ValueError(f"implausible bit depth: {bit_depth!r}")
    return float(2 ** int(bit_depth) - 1)


def bead_area_window(pixel_um: float, feature_um: float,
                     lo_factor: float = 0.25, hi_factor: float = 4.0) -> tuple[int, int]:
    """Plausible connected-component area, in px, for a feature of `feature_um`.

    Computed rather than hard-coded, because a fixed window silently stops
    meaning "a bead" the moment the sampling changes. Measured on 2026-09-06:
    the 2-40 px window that was right at 4x (1.625 um/px, a 5 um bead ~3 px
    across, ~7 px area) became 2-400 px here by guesswork, while a 5 um bead at
    0.130 um/px is ~38 px across and ~1160 px in AREA -- so the filter excluded
    every real bead and counted only small debris and noise. The counts it
    printed were not bead counts.

    The window is generous on purpose: a defocused bead spreads, a touching
    pair merges, and the point is to track focus rather than to segment
    perfectly.
    """
    radius_px = 0.5 * feature_um / max(pixel_um, 1e-9)
    area = np.pi * radius_px * radius_px
    return max(2, int(lo_factor * area)), int(hi_factor * area)


def tenengrad(frame: np.ndarray) -> float:
    """Sobel gradient energy per pixel, normalised by the frame's own median.

    The normalisation is what makes this a sharpness measure rather than a
    brightness one -- see the module docstring.
    """
    import cv2

    f32 = np.asarray(frame, dtype=np.float32)
    median = float(np.median(f32))
    gx = cv2.Sobel(f32, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f32, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy)) / max(median, 1.0) ** 2


def score_frame(frame: np.ndarray,
                area_px: tuple[int, int] | None = None,
                ceiling: float = DEFAULT_CEILING) -> dict:
    """Sharpness, feature count and headroom for one frame.

    `area_px=None` skips the connected-component pass, which is the right call
    for a target that is not a compact blob -- an edge, a ruled graticule, a
    scratch. The sharpness and headroom numbers are unaffected by it.
    """
    import cv2

    f32 = np.asarray(frame, dtype=np.float32)
    median = float(np.median(f32))

    gx = cv2.Sobel(f32, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f32, cv2.CV_32F, 0, 1, ksize=3)
    sharp = float(np.mean(gx * gx + gy * gy)) / max(median, 1.0) ** 2

    smooth = cv2.GaussianBlur(f32, (0, 0), 15)
    residual = f32 - smooth
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0

    beads = 0
    bead_area_med = 0.0
    if area_px is not None:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(
            (residual > 8.0 * scale).astype(np.uint8), 8
        )
        areas = stats[1:, 4]
        lo, hi = area_px
        keep = (areas >= lo) & (areas <= hi)
        beads = int(keep.sum())
        bead_area_med = float(np.median(areas[keep])) if keep.any() else 0.0

    peak_abs = float(np.asarray(frame).max())
    return {
        "sharp": sharp,
        "beads": beads,
        "bead_area_med": bead_area_med,
        "peak": float(residual.max()),
        "peak_abs": peak_abs,
        "peak_pct_ceiling": 100.0 * peak_abs / ceiling,
        "median": median,
        "clip_frac": float((np.asarray(frame) >= CLIP_FRACTION * ceiling).mean()),
        "saturated": peak_abs >= CLIP_FRACTION * ceiling,
    }
