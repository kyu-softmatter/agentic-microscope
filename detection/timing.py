"""Frame timing formulas (docs/04-decision-engine.md §5).

Pure functions, no dataclasses. A rolling-shutter sCMOS's readout time
depends only on row count -- narrowing width does not speed anything up
(docs/06-pitfalls.md §C3), so these take a row/height count, never a width.
"""

from __future__ import annotations


def readout_time_s(row_time_us: float, roi_height_px: int) -> float:
    """Rolling-shutter readout: proportional to row count only."""
    return row_time_us * roi_height_px * 1e-6


def frame_period_s(exposure_ms: float, readout_s: float, overhead_ms: float = 0.0) -> float:
    """``t_frame = max(t_exp + t_overhead, t_readout)``."""
    return max((exposure_ms + overhead_ms) * 1e-3, readout_s)


def max_fps(frame_period_s_: float) -> float:
    return 1.0 / frame_period_s_ if frame_period_s_ > 0 else float("inf")


def duty_cycle(exposure_ms: float, frame_period_s_: float) -> float:
    """``t_exp / t_frame`` -- the fraction of each frame spent exposing."""
    return (exposure_ms * 1e-3) / frame_period_s_ if frame_period_s_ > 0 else float("inf")


def motion_blur_bias_fraction(duty_cycle_: float) -> float:
    """Relative Savin-Doyle MSD bias at the shortest lag ``tau_min = t_frame``.

    ``|(t_exp/3) / tau_min| = duty_cycle / 3``. The docs/04 §5 gate keeps
    this under 0.1, i.e. duty cycle <= 30%.
    """
    return duty_cycle_ / 3.0
