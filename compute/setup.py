"""Compute-resource setup: the facts G12-G13 need."""

from __future__ import annotations

from dataclasses import dataclass

from .resources import frame_bytes


@dataclass
class AcquisitionResourceSetup:
    frame_width_px: int
    frame_height_px: int
    #: Achieved (not requested) frame rate -- docs/06-pitfalls.md §C4 is
    #: exactly the case where these differ by 3x.
    fps: float
    #: Measured sustained write bandwidth (calibration.disk_bandwidth).
    #: Cannot be computed -- docs/04 §9 marks this "measurement required".
    disk_bandwidth_mb_s: float | None = None
    #: MM's CircularBufferFrameCount, read directly if known.
    circular_buffer_frames: int | None = None
    #: Fallback for circular_buffer_frames when the literal MM setting is
    #: not known: derive a frame count from an available-RAM budget instead.
    ram_budget_mb: float | None = None
    acquisition_duration_s: float | None = None
    free_disk_gb: float | None = None
    #: Per-frame processing time, only meaningful if realtime_processing.
    cpu_per_frame_ms: float | None = None
    realtime_processing: bool = False

    def resolved_buffer_frames(self) -> int | None:
        if self.circular_buffer_frames is not None:
            return self.circular_buffer_frames
        if self.ram_budget_mb is not None:
            fb = frame_bytes(self.frame_width_px, self.frame_height_px)
            return int(self.ram_budget_mb * 1e6 / fb) if fb > 0 else None
        return None
