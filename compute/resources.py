"""Data rate / buffer / capacity formulas (docs/04-decision-engine.md §8).

Pure functions, no dataclasses. Micro-Manager stores 9..16-bit frames in a
16-bit container regardless of the ADC's actual bit depth (a 12-bit camera
still costs 2 bytes/pixel on disk) -- ``bytes_per_pixel_for_bit_depth``
carries that rule, and every byte count here goes through it rather than
through the camera's nominal bit depth.
"""

from __future__ import annotations

#: MM's on-disk container for any mode deeper than 8 bit. Kept as a module
#: constant because it is the default every caller wants; use
#: ``bytes_per_pixel_for_bit_depth`` when a mode's bit depth is known.
BYTES_PER_PIXEL = 2

#: The widest container this module models. Nothing on this system reads out
#: deeper than 16 bit (data/detectors.yaml, Kinetix DynamicRange mode).
MAX_MODELLED_BIT_DEPTH = 16


def bytes_per_pixel_for_bit_depth(bit_depth: int) -> int:
    """MM's storage width for one pixel of a given ADC bit depth.

    ``9..16 -> 2`` is documented and observed (docs/04 §8: a 12-bit mode
    still costs 2 bytes/pixel).

    ``<=8 -> 1`` is what MMCore's ``getBytesPerPixel()`` reports for an
    8-bit pixel type, but it has **not** been confirmed against this lab's
    PVCAM/Kinetix adapter -- an adapter is free to hand MMCore 16-bit
    pixels from an 8-bit sensor mode. The Kinetix's Speed mode is 8-bit at
    500 fps full frame (data/detectors.yaml), i.e. exactly the regime where
    G12 binds, so getting this wrong moves the data rate by 2x in the one
    place it matters. ``compute.checks.check_pixel_container`` refuses to
    call an unconfirmed 8-bit container measured.
    """
    if bit_depth <= 0:
        raise ValueError(f"bit_depth must be positive, got {bit_depth}")
    if bit_depth > MAX_MODELLED_BIT_DEPTH:
        raise ValueError(
            f"no MM container wider than {MAX_MODELLED_BIT_DEPTH} bit is "
            f"modelled, got {bit_depth}"
        )
    return 1 if bit_depth <= 8 else 2


def frame_bytes(
    width_px: int, height_px: int, bytes_per_pixel: int = BYTES_PER_PIXEL
) -> float:
    return width_px * height_px * bytes_per_pixel


def data_rate_bytes_s(
    width_px: int,
    height_px: int,
    fps: float,
    bytes_per_pixel: int = BYTES_PER_PIXEL,
) -> float:
    """``R = W * H * (bits/8) * f``, with the container width from
    ``bytes_per_pixel_for_bit_depth`` rather than the ADC's bit depth."""
    return frame_bytes(width_px, height_px, bytes_per_pixel) * fps


def buffer_bytes(
    frame_count: int,
    width_px: int,
    height_px: int,
    bytes_per_pixel: int = BYTES_PER_PIXEL,
) -> float:
    """``buffer = N_frames * W * H * bytes_per_pixel``."""
    return frame_count * frame_bytes(width_px, height_px, bytes_per_pixel)


def buffer_seconds(buffer_bytes_: float, data_rate_bytes_s_: float) -> float:
    return buffer_bytes_ / data_rate_bytes_s_ if data_rate_bytes_s_ > 0 else float("inf")


def buffer_seconds_from_frames(buffer_frames: int, frames_per_s: float) -> float:
    """Seconds of headroom in a buffer counted in *frames*.

    MMCore's circular buffer is sized in images, not bytes, and it is shared
    across cameras -- so with several streams running the answer is just
    ``N_buffered / N_arriving_per_second`` and the frame geometry cancels
    out. Equivalent to ``buffer_seconds`` for a single stream; the two are
    kept separate because only this one stays correct when the streams have
    different frame sizes.
    """
    return buffer_frames / frames_per_s if frames_per_s > 0 else float("inf")


def total_capacity_bytes(data_rate_bytes_s_: float, duration_s: float) -> float:
    return data_rate_bytes_s_ * duration_s


def flush_seconds(total_bytes: float, disk_bandwidth_mb_s: float) -> float:
    """How long it takes to write a RAM-held burst out afterwards.

    The RAM-capture path (kb/decisions/2026-08-12-ram-buffer-detour-for-disk-
    bandwidth.md) trades G12's real-time disk constraint for this one-off,
    non-real-time write. It is not a gate -- nothing is lost if it is slow --
    but the number decides whether the microscope is tied up for one minute
    or for twenty.
    """
    if disk_bandwidth_mb_s <= 0:
        return float("inf")
    return total_bytes / (disk_bandwidth_mb_s * 1e6)
