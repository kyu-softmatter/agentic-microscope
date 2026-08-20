"""Compute-resource setup: the facts G12-G13 need.

One acquisition is a *set* of frame streams, not one frame size. The lab
runs two cameras at once (Kinetix_red/Kinetix_blue, kb/systems/current.md),
and a z-stack or a multi-channel loop multiplies the frames a single camera
delivers. Before 2026-08-19 this held one ``frame_width_px`` and the dual-cam
case had to be smuggled in by doubling the width by hand -- see the gate
invocation recorded in kb/decisions/2026-08-12-ram-buffer-detour-for-disk-
bandwidth.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .resources import bytes_per_pixel_for_bit_depth, frame_bytes

#: Accepted values for ``Stream.fps_source``. Anything other than "measured"
#: means the frame rate has not been observed on this system, and docs/06
#: §C4 is the reason that matters: a 176-row ROI at 10 ms exposure has a
#: ~85 Hz camera limit but delivered 28 Hz.
FPS_SOURCES = ("measured", "requested")


@dataclass
class Stream:
    """One camera's frame stream into MMCore's circular buffer."""

    label: str
    width_px: int
    height_px: int
    #: Frames per second **this stream actually delivers to the buffer** --
    #: not the timepoint rate of a multi-dimensional acquisition. Use
    #: ``from_dimensions`` to fold z/channel/position counts in.
    fps: float
    #: ADC bit depth of the readout mode in use (data/detectors.yaml
    #: ``modes``). Lens 2 already selects a mode this way
    #: (detection.setup.Camera.effective_bit_depth); this is the same fact.
    bit_depth: int = 16
    #: Has the bytes/pixel MM actually writes for this bit depth been
    #: confirmed on this system? Only meaningful for <=8-bit modes -- see
    #: ``resources.bytes_per_pixel_for_bit_depth``.
    container_confirmed: bool = False
    #: "measured" | "requested" -- see FPS_SOURCES.
    fps_source: str = "requested"

    def __post_init__(self) -> None:
        if self.fps_source not in FPS_SOURCES:
            raise ValueError(
                f"fps_source must be one of {FPS_SOURCES}, got {self.fps_source!r}"
            )

    @classmethod
    def from_dimensions(
        cls,
        label: str,
        width_px: int,
        height_px: int,
        *,
        timepoints_per_s: float,
        z_slices: int = 1,
        channels: int = 1,
        positions: int = 1,
        **kwargs,
    ) -> "Stream":
        """Build a stream from MM's acquisition dimensions.

        ``fps = timepoints/s * z * c * positions`` is the **average** frame
        rate. If the z/channel sweep is a burst that finishes well inside one
        timepoint interval, the instantaneous rate into the circular buffer is
        higher than this and G13a comes out optimistic -- pass that burst rate
        as ``fps`` directly instead of using this constructor.
        """
        return cls(
            label=label,
            width_px=width_px,
            height_px=height_px,
            fps=timepoints_per_s * z_slices * channels * positions,
            **kwargs,
        )

    @property
    def bytes_per_pixel(self) -> int:
        return bytes_per_pixel_for_bit_depth(self.bit_depth)

    @property
    def container_is_assumed(self) -> bool:
        """True when this stream's bytes/pixel rests on an unconfirmed guess."""
        return self.bit_depth <= 8 and not self.container_confirmed

    def frame_bytes(self) -> float:
        return frame_bytes(self.width_px, self.height_px, self.bytes_per_pixel)

    def data_rate_bytes_s(self) -> float:
        return self.frame_bytes() * self.fps


@dataclass
class AcquisitionResourceSetup:
    streams: list[Stream] = field(default_factory=list)
    #: Measured sustained write bandwidth (calibration.disk_bandwidth).
    #: Cannot be computed -- docs/04 §9 marks this "measurement required".
    disk_bandwidth_mb_s: float | None = None
    #: Was that bandwidth measured against the folder Micro-Manager actually
    #: streams into? kb/calibrations/disk-bandwidth.yaml records 206.8 MB/s
    #: for the D: drive's _bench folder and says in its own note that this is
    #: not confirmed to be the MM save directory. A number measured somewhere
    #: else on the same drive is a plausible number, not a measured one.
    disk_bandwidth_path_confirmed: bool = False
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
    #: Lens 2's realizable frame rate (detection.timing.max_fps) for the
    #: fastest stream. Cross-lens 2<->3: this lens does not own frame rate,
    #: so without lens 2's ceiling it can only warn, not gate (the same
    #: arrangement as trapping.checks.check_sampling's detector_fps).
    detector_max_fps: float | None = None
    #: RAM-capture path: hold the whole burst in memory and flush afterwards,
    #: which removes G12's real-time disk constraint and replaces it with
    #: G13d. kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md,
    #: implemented in calibration/ram_capture.py.
    ram_capture: bool = False
    #: RAM the capture buffer may use. ``None`` falls back to the authorized
    #: ceiling in compute.checks.LIMITS, not to the machine's total RAM.
    ram_capture_budget_mb: float | None = None

    # -- derived ---------------------------------------------------------

    def data_rate_bytes_s(self) -> float:
        return sum(s.data_rate_bytes_s() for s in self.streams)

    def frames_per_s(self) -> float:
        return sum(s.fps for s in self.streams)

    def mean_frame_bytes(self) -> float:
        """Bytes of the average frame arriving at the shared circular buffer.

        Weighted by each stream's share of the frame rate, so
        ``mean_frame_bytes * frames_per_s == data_rate_bytes_s``.
        """
        rate = self.frames_per_s()
        return self.data_rate_bytes_s() / rate if rate > 0 else 0.0

    def resolved_buffer_frames(self) -> int | None:
        if self.circular_buffer_frames is not None:
            return self.circular_buffer_frames
        if self.ram_budget_mb is not None:
            fb = self.mean_frame_bytes()
            return int(self.ram_budget_mb * 1e6 / fb) if fb > 0 else None
        return None

    def unverified_fps_streams(self) -> list[Stream]:
        return [s for s in self.streams if s.fps_source != "measured"]

    def assumed_container_streams(self) -> list[Stream]:
        return [s for s in self.streams if s.container_is_assumed]

    # -- convenience -----------------------------------------------------

    @classmethod
    def single(
        cls,
        *,
        frame_width_px: int,
        frame_height_px: int,
        fps: float,
        bit_depth: int = 16,
        container_confirmed: bool = False,
        fps_source: str = "requested",
        label: str = "camera",
        **kwargs,
    ) -> "AcquisitionResourceSetup":
        """The one-camera case, which is still the common one."""
        stream = Stream(
            label=label,
            width_px=frame_width_px,
            height_px=frame_height_px,
            fps=fps,
            bit_depth=bit_depth,
            container_confirmed=container_confirmed,
            fps_source=fps_source,
        )
        return cls(streams=[stream], **kwargs)
