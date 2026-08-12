"""RAM-buffered burst capture: hold every frame in memory during acquisition,
write to disk only after the sequence ends.

This is the detour proposed in kb/decisions/2026-08-12-ram-buffer-detour-for-
disk-bandwidth.md to route around the D: drive's measured sustained write
bandwidth (kb/calibrations/disk-bandwidth.yaml, 206.8 MB/s) being far below
what a high-fps / large-ROI dual-camera acquisition needs (docs/04-decision-
engine.md §9, G12). Capture never touches disk; ``flush_to_disk`` is a
separate, non-real-time step the caller runs once the burst is done.

Single camera only. The lab runs two physical cameras (Kinetix_red/
Kinetix_blue) simultaneously in normal use, but MMCore's sequence-acquisition
calls are per-camera-label and this has only been exercised against
pymmcore-plus's bundled single-camera demo config (tests/test_ram_capture.py)
-- not the real PVCAM/Kinetix adapter, and not two cameras at once. Call
capture_burst_to_ram() once per camera (e.g. from two threads sharing one
CMMCorePlus, or two separate CMMCorePlus instances) if both are needed, and
confirm on the real config that they actually run concurrently rather than
serializing -- don't assume (docs/06-pitfalls.md style).

Caller is responsible for checking ``n_frames`` worth of frames fit in
available RAM before calling -- see compute.checks for the margin math this
is meant to satisfy. This module will happily try to allocate more than
physically exists and let MemoryError explain why not.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus

POLL_INTERVAL_S = 0.001

_DTYPE_BY_BYTES_PER_PIXEL = {1: np.uint8, 2: np.uint16, 4: np.uint32}


@dataclass(frozen=True)
class CaptureResult:
    frames: np.ndarray  # (n_captured, height, width)
    n_requested: int
    n_captured: int
    elapsed_s: float

    @property
    def dropped(self) -> int:
        return self.n_requested - self.n_captured

    @property
    def achieved_fps(self) -> float:
        return self.n_captured / self.elapsed_s if self.elapsed_s > 0 else 0.0


@dataclass(frozen=True)
class FlushResult:
    path: str
    bytes_written: int
    elapsed_s: float

    @property
    def mb_per_s(self) -> float:
        return self.bytes_written / self.elapsed_s / 1e6 if self.elapsed_s > 0 else float("inf")


def capture_burst_to_ram(
    core: "CMMCorePlus",
    camera: str,
    n_frames: int,
    *,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> CaptureResult:
    """Snap ``n_frames`` from ``camera`` as fast as the hardware allows,
    holding every frame in one preallocated array. No disk write happens
    here -- that is ``flush_to_disk``'s job, run after this returns.

    Stops early (fewer than ``n_frames`` captured) if the sequence ends on
    its own -- ``CaptureResult.dropped`` reports the shortfall rather than
    raising, since that mirrors how a real stall drops frames silently
    (docs/06-pitfalls.md §C5) instead of erroring.
    """
    if n_frames <= 0:
        raise ValueError(f"n_frames must be positive, got {n_frames}")

    width = core.getImageWidth()
    height = core.getImageHeight()
    bytes_per_pixel = core.getBytesPerPixel()
    dtype = _DTYPE_BY_BYTES_PER_PIXEL[bytes_per_pixel]
    frames = np.empty((n_frames, height, width), dtype=dtype)

    core.startSequenceAcquisition(camera, n_frames, 0, True)
    n_captured = 0
    start = time.perf_counter()
    try:
        while n_captured < n_frames:
            if core.getRemainingImageCount() == 0:
                if not core.isSequenceRunning(camera):
                    break
                time.sleep(poll_interval_s)
                continue
            frames[n_captured] = core.popNextImage()
            n_captured += 1
    finally:
        elapsed = time.perf_counter() - start
        if core.isSequenceRunning(camera):
            core.stopSequenceAcquisition(camera)

    return CaptureResult(
        frames=frames[:n_captured],
        n_requested=n_frames,
        n_captured=n_captured,
        elapsed_s=elapsed,
    )


def flush_to_disk(frames: np.ndarray, path: Path) -> FlushResult:
    """Write ``frames`` to ``path`` (.npy) -- the non-real-time half of the
    detour, run once the burst is already sitting in RAM. Includes an
    fsync, same rigor as calibration.disk_bandwidth, so the timing isn't
    inflated by the OS write-behind cache.
    """
    path = Path(path)
    start = time.perf_counter()
    with open(path, "wb") as f:
        np.save(f, frames)
        f.flush()
        os.fsync(f.fileno())
    elapsed = time.perf_counter() - start
    return FlushResult(path=str(path), bytes_written=frames.nbytes, elapsed_s=elapsed)
