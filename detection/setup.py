"""Detection-lens setup: the facts G5-G9 need, bundled the way
``optics.path.Channel`` and ``trapping.dynamics.TrapSetup`` bundle theirs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optics.components import Detector, DetectorMode, Objective


@dataclass
class Camera:
    detector: Detector
    #: Selects a row of ``detector.modes`` for bit depth / read noise / full
    #: well / line time. ``None`` falls back to the detector's flat fields.
    mode: str | None = None
    binning: int = 1
    #: Row count only -- readout time depends on rows, not columns
    #: (docs/06-pitfalls.md §C3), so column count is not tracked here.
    roi_height_px: int | None = None
    #: Measured row/line time; overrides the mode's ``line_time_us`` when
    #: supplied. calibration.mm_live has not been run against the real
    #: PVCAM/Kinetix adapter yet, so a datasheet mode value is a fallback,
    #: not a substitute, for a measurement.
    row_time_us: float | None = None
    frame_overhead_ms: float = 0.0
    offset_adu: float = 0.0

    def resolved_mode(self) -> DetectorMode | None:
        if self.mode is None:
            return None
        return self.detector.modes.get(self.mode)

    def effective_row_time_us(self) -> float | None:
        if self.row_time_us is not None:
            return self.row_time_us
        mode = self.resolved_mode()
        return mode.line_time_us if mode else None

    def effective_bit_depth(self) -> int | None:
        mode = self.resolved_mode()
        return mode.bit_depth if mode else None

    def effective_read_noise_e(self) -> float | None:
        mode = self.resolved_mode()
        if mode is not None and mode.read_noise_e is not None:
            return mode.read_noise_e
        return self.detector.read_noise_e

    def effective_full_well_e(self) -> float | None:
        mode = self.resolved_mode()
        if mode is not None and mode.full_well_e is not None:
            return mode.full_well_e
        return self.detector.full_well_e


@dataclass
class Acquisition:
    exposure_ms: float
    #: "imaging" (morphology/structure) or "tracking" (single-particle) --
    #: G5 and G8 go in opposite directions depending on which (docs/04 §2).
    task_kind: str | None = None
    #: Desired frame rate, from decision step (2) upstream of this lens.
    #: G9 only grades against this when it is supplied.
    target_fps: float | None = None


@dataclass
class PhotonBudget:
    #: Measured detected signal rate at the brightest pixel, e-/s
    #: (docs/04 §3's k_det -- this lens takes it as an input, it does not
    #: recompute the photon-budget chain that lens 1 owns).
    signal_e_per_s: float | None = None
    #: Measured background rate, e-/s. Cannot be computed (docs/04 §4).
    background_e_per_s: float | None = None
    #: Number of pixels the spot is spread over, for the SNR read-noise term.
    n_pix_spot: int = 1
    target_snr: float | None = None
    target_localization_precision_nm: float | None = None
    #: Optional -- only used to report the absolute (not just relative) MSD
    #: bias in a motion-blur finding's message.
    diffusion_coefficient_m2_s: float | None = None


TASK_KINDS = {"imaging", "tracking"}


@dataclass
class DetectionSetup:
    objective: Objective
    #: Emission wavelength of the dye being imaged -- a property of the
    #: experiment, not of the objective, so it is not read off ``objective``.
    wavelength_em_nm: float
    mag_objective: float
    camera: Camera
    acquisition: Acquisition
    mag_intermediate: float = 1.0
    photons: PhotonBudget = field(default_factory=PhotonBudget)
