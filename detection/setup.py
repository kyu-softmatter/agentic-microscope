"""Detection-lens setup: the facts L2.1-L2.5 need, bundled the way
``optics.path.Channel`` and ``trapping.dynamics.TrapSetup`` bundle theirs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optics.components import Detector, DetectorMode, Objective

#: Accepted values for ``Acquisition.fps_source``. The first two are the same
#: tokens as ``compute.setup.FPS_SOURCES``, on purpose -- see that property.
FPS_SOURCES = ("measured", "requested", "undecided")


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
    #: Column count. **Not used for readout**, for the reason directly above.
    #: It is here because the FIELD needs both dimensions and lens 2 is the
    #: lens that can compute one: the field is ROI x the pixel at the sample,
    #: and the pixel at the sample is this lens's number. Lens 3's data rate
    #: needs it too, and takes it from the brief rather than from here.
    roi_width_px: int | None = None
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
    #: L2.1 and L2.4 go in opposite directions depending on which (docs/04 §2).
    task_kind: str | None = None
    #: Desired frame rate, from decision step (2) upstream of this lens.
    #: L2.5 only grades against this when it is supplied.
    target_fps: float | None = None
    #: OBSERVED frame rate, from an acquisition's own timestamps. Outranks
    #: ``target_fps`` everywhere: docs/06 §C4 measured a 3x gap between a
    #: requested rate and a delivered one on this archive.
    achieved_fps: float | None = None

    @property
    def decided_fps(self) -> float | None:
        """The frame rate to judge against, or ``None`` if nobody has decided.

        Neither L2.4 nor L2.5 owns the frame period. L2.5 asks whether a rate is
        realizable (hardware, ``hard``); L2.4 asks whether the exposure is a
        small enough fraction of the period actually run (measurement,
        ``bias``). Both consume this, and when it is ``None`` both report
        instead of grading -- the rate is settled later, in synthesis with the
        other lenses' results (KH, 2026-09-09).
        """
        return self.achieved_fps if self.achieved_fps is not None else self.target_fps

    @property
    def fps_source(self) -> str:
        """``measured`` | ``requested`` | ``undecided``.

        Derived rather than stored so it cannot disagree with the fields it
        describes. ``measured`` and ``requested`` are deliberately the same two
        tokens as ``compute.setup.FPS_SOURCES`` -- lens 3's L3.2 is the same
        distinction seen from the data-rate side, and
        ``tests/test_detection_gate.py`` fails if the two vocabularies drift
        apart. ``undecided`` is lens 2's only addition: lens 3 always has a
        rate, because it cannot compute a data rate without one.
        """
        if self.achieved_fps is not None:
            return "measured"
        if self.target_fps is not None:
            return "requested"
        return "undecided"


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


@dataclass(frozen=True)
class FrameRateWindow:
    """Both ends of the frame-rate window, and the usable rate between them.

    A triple rather than one number because L2.4 and L2.5 each report one end
    and lens 3 is judged against the pair (CLAUDE.md §2 E5): a rate that fits
    the readout and busts the duty limit is not usable, and which of the two
    binds is the actionable part.
    """

    #: 1/t_frame at this exposure and ROI -- the fastest the camera goes.
    fps_hardware_max: float | None
    #: 0.3/t_exp -- the fastest this exposure keeps motion blur under L2.4.
    fps_at_duty_limit: float | None
    #: The min of the two, or None where either end is unknown.
    fps_usable_max: float | None

    @property
    def binding(self) -> str | None:
        if self.fps_usable_max is None:
            return None
        return (
            "blur (L2.4)"
            if self.fps_at_duty_limit < self.fps_hardware_max
            else "readout (L2.5)"
        )


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
    #: THE SYSTEM UNDER STUDY, not the instrument -- the length and the time
    #: the experiment is trying to see. Every other field here describes the
    #: microscope; these two describe what it is pointed at, and L2.6 is the
    #: only check that reads them.
    #:
    #: They are here because the operator's own parameter inventory bounds
    #: eight settings from below by these two numbers and by nothing else
    #: (objective, intermediate magnification, ROI, fps, sensor size, binning,
    #: exposure, frame interval), and until 2026-09-14 no setup object in this
    #: repository carried either. A refiner that harvests `missing.*` findings
    #: therefore could not ask for them -- which is the falsifying condition
    #: kb/decisions/2026-09-13-the-planning-layer.md set for itself.
    characteristic_length_um: float | None = None
    characteristic_time_s: float | None = None

    def field_of_view_um(self) -> tuple[float | None, float | None]:
        """The field at the sample, um, as (width, height).

        **Lens 4 consumes this and does not compute it** (`sample/setup.py`
        says so of `field_width_um` in as many words: "Owned by lenses 1/2
        (objective + camera); lens 4 only consumes it"). Until 2026-09-14
        nothing carried it across that boundary, so L4.6's particle count only
        ever ran when a human typed the field into `sample/cli.py` -- in the
        designer's path it was silently unevaluated.

        Returns ``(None, None)`` for either dimension the ROI does not give.
        The pixel comes from ``pixel_size_nm()``, so the field inherits the
        same provenance the sampling check is graded on rather than a second
        derivation of the same quantity.
        """
        pixel_um = self.pixel_size_nm()[0] / 1000.0
        cam = self.camera
        return (
            None if cam.roi_width_px is None else cam.roi_width_px * pixel_um,
            None if cam.roi_height_px is None else cam.roi_height_px * pixel_um,
        )

    def frame_rate_window(self) -> "FrameRateWindow":
        """The rate window this camera and this exposure allow, from both ends.

        **One definition of three numbers that had two readers and now has
        three.** L2.4 computed ``fps_at_duty_limit`` and L2.5 computed it again
        beside ``fps_usable_max``; lens 3's ``usable_fps_ceiling`` is the third
        reader, and it was getting ``None`` -- so L3.2, the check CLAUDE.md §2
        E5 exists for, refused with `missing.usable_fps_ceiling` on every brief
        the designer ever ran. ``designer/run.py``'s INTRA_TIER already ordered
        lens 2 before lens 3 *for this number* and nothing carried it, which is
        a broken handoff wearing a missing gate's clothes.

        Every field is ``None`` where an input is. The duty limit needs only the
        exposure, so it can exist while the hardware ceiling does not.
        """
        from .checks import LIMITS
        from .timing import frame_period_s, max_fps, readout_time_s

        cam, acq = self.camera, self.acquisition
        row_time = cam.effective_row_time_us()
        hardware = None
        if row_time is not None and cam.roi_height_px is not None:
            readout_s = readout_time_s(row_time, cam.roi_height_px)
            hardware = max_fps(
                frame_period_s(acq.exposure_ms, readout_s, cam.frame_overhead_ms)
            )

        exposure_s = acq.exposure_ms * 1e-3
        duty = LIMITS["duty_cycle_max"] / exposure_s if exposure_s > 0 else float("inf")

        # The min is the usable rate ONLY where both ends exist. With one end
        # missing the other is not the window -- reporting it as such is how a
        # single bound starts reading as a cleared pair (§3).
        usable = min(hardware, duty) if hardware is not None else None
        return FrameRateWindow(
            fps_hardware_max=hardware, fps_at_duty_limit=duty, fps_usable_max=usable
        )

    def pixel_size_nm(self) -> tuple[float, str]:
        """Effective pixel at the sample, in nm, with where the number came from.

        Three sources, in this order, and the order is the point:

        ``"measured"``
            ``data/pixel_size.yaml`` has a row that **departs** from the nominal
            quotient. Today that is the 20x alone -- 0.32373 um/px against a
            nominal 0.325, i.e. a real magnification of 20.078x. Only this tier
            tells you something the formula cannot.
        ``"nominal"``
            the recorded table agrees with ``p_sensor / (M_obj * M_int)`` to
            every digit it carries, so the lookup and the formula return the
            same float. Reported separately from ``computed`` only so a reader
            can see the table was consulted and had nothing to add.
        ``"computed"``
            no row for this combination; the formula stands alone.

        **A ``nominal`` hit is not evidence.** Lens 6 owns pixel calibration
        (L6.2-L6.1) and grades on ``measured`` vs ``assumed``; promoting eleven
        quotients to measurements because they happen to sit in a file called
        `calibration` is the failure this repository is built against. See the
        header of ``data/pixel_size.yaml``.
        """
        from optics.components import recorded_pixel_um

        from .photometry import effective_pixel_nm

        hit = recorded_pixel_um(self.mag_objective, self.mag_intermediate, self.camera.binning)
        if hit is not None:
            um, evidence = hit
            return um * 1000.0, evidence
        return (
            effective_pixel_nm(
                self.camera.detector.pixel_um,
                self.camera.binning,
                self.mag_objective,
                self.mag_intermediate,
            ),
            "computed",
        )
