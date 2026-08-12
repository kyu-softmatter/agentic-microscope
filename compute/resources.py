"""Data rate / buffer / capacity formulas (docs/04-decision-engine.md §8).

Pure functions, no dataclasses. Micro-Manager always stores frames in a
16-bit container regardless of the ADC's actual bit depth (a 12-bit camera
still costs 2 bytes/pixel on disk) -- every byte count here reflects that,
not the camera's nominal bit depth.
"""

from __future__ import annotations

#: MM's on-disk container, independent of the camera's ADC bit depth.
BYTES_PER_PIXEL = 2


def frame_bytes(width_px: int, height_px: int) -> float:
    return width_px * height_px * BYTES_PER_PIXEL


def data_rate_bytes_s(width_px: int, height_px: int, fps: float) -> float:
    """``R = W * H * (bits/8) * f``, with bits fixed at MM's 16-bit container."""
    return frame_bytes(width_px, height_px) * fps


def buffer_bytes(frame_count: int, width_px: int, height_px: int) -> float:
    """``buffer = N_frames * W * H * 2 bytes``."""
    return frame_count * frame_bytes(width_px, height_px)


def buffer_seconds(buffer_bytes_: float, data_rate_bytes_s_: float) -> float:
    return buffer_bytes_ / data_rate_bytes_s_ if data_rate_bytes_s_ > 0 else float("inf")


def total_capacity_bytes(data_rate_bytes_s_: float, duration_s: float) -> float:
    return data_rate_bytes_s_ * duration_s
