"""One measured frame -> which camera mode, and what exposure.

This is the inverse of ``detection.gate``, which grades settings you already
chose. Here the experimenter brings **one test frame** and the settings come
out computed (docs/04-decision-engine.md §1 steps ③-⑤, run backwards).

Why one frame is enough
-----------------------
``photon.background`` is the one input in this lens that docs/04 §4 marks
"**must be measured.** Not computable", and ``photon.signal`` needs a measured
light level that Phase 0 does not have yet (docs/07-roadmap.md). A single frame
supplies both, and it supplies them *for every mode at once*:

    the detected signal rate is a property of the sample and the light path,
    not of the readout mode

A camera mode changes conversion gain, bit depth, read noise and line time --
the digitisation. It does not change how many photoelectrons the pixel
collects. So a frame taken in Sensitivity yields ``k_det`` that is equally
valid for Dynamic Range, and all four modes can be compared off one shot.
That is the whole point of this module; it is also why the frame must record
*which* mode it was taken in, since converting ADU to electrons needs that
mode's conversion gain.

What it refuses
---------------
* despeckle on -> the ADU->electron conversion is invalid, full stop
  (docs/06-pitfalls.md C1: linearity and noise independence both break)
* a clipped peak -> the brightest pixel is a lower bound, not a measurement
* a mode with no full well or bit depth on record -> no conversion gain

Conversion gain is *derived* as ``full_well / 2**bit_depth`` rather than read
from the registry, the same way ``photometry.quantization_noise_e`` derives it.
For the Kinetix22 that reproduces the datasheet's stated per-mode conversion
gain (0.23 / 0.85 / 0.25 / 0.015 e-/count) to within the rounding of the
vendor's own two-significant-figure numbers -- except in **Speed**, where
200/256 = 0.781 against a stated 0.85, an 8.8% gap. That gap lands directly in
the ADU->electron conversion, so **take the calibration frame in Sensitivity or
DynamicRange**, not Speed. Pinned by
tests/test_detection_recommend.py::test_derived_conversion_gain_tracks_the_datasheet.

Two conventions this module had to take a position on
-----------------------------------------------------
**1. Peak pixel or spot total?** ``PhotonBudget.signal_e_per_s`` is documented
as the rate "at the brightest pixel", but ``checks.check_snr`` feeds it to
``photometry.snr`` as the numerator alongside a spot-wide read-noise term
(``n_pix * sigma^2``). Those are two different quantities: saturation is a
property of one pixel, SNR of the whole spot. The formula as written is a mix,
and settling it is a lens-2 decision that has not been made.

This module does **not** pick a side. It reports ``signal_e_per_s`` as measured
at the peak pixel -- which is what a frame actually gives you -- and computes
SNR through ``photometry.snr`` itself, so that whenever the convention is
settled, the gate and this recommender change together instead of drifting
apart. ``exposure_for_snr`` inverts exactly that same expression.

**2. Does background fill the well?** Yes, and ``checks.check_saturation``
omits it: its peak is ``signal + dark`` only. The pixel does not know which
electrons were interesting, so :func:`exposure_ceiling_saturation` includes
background. That makes this module *stricter* than the gate, never looser --
it will not propose an exposure the gate would reject. On the Kinetix22 the gap
is not academic: in Sensitivity mode the well is 1,000 e-, so a background
running at 15% of the signal rate means the gate allows an exposure ~15%
longer than the pixel can actually take.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from optics.components import Detector

from .photometry import effective_read_noise_e, localization_variance_nm2, snr
from .timing import readout_time_s

#: G6, docs/04 §4. Peak electrons must stay under this fraction of full well.
SATURATION_FRACTION = 0.7
#: G6's second half: peak ADU under this fraction of the digital ceiling.
ADU_FRACTION = 0.9
#: G8, docs/04 §5. Duty cycle at or below this keeps the shortest-lag MSD bias
#: under 10%.
DUTY_CYCLE_MAX = 0.3
#: Above this fraction of the digital ceiling the measured peak is untrustworthy
#: -- the pixel may already be clipped, so it reads as a lower bound.
CLIPPED_ADU_FRACTION = 0.95


# --------------------------------------------------------------------------
# The measurement
# --------------------------------------------------------------------------


@dataclass
class FrameMeasurement:
    """What one test frame has to supply.

    All three ADU numbers come off the *raw* frame -- no background
    subtraction, no flat-field, no filtering. ``offset_adu`` is what the sensor
    reads with no light at all; take a dark frame at the same exposure rather
    than trusting a datasheet number, since it is the zero of everything below.
    """

    #: Exposure the frame was taken at, ms.
    exposure_ms: float
    #: Which registry mode the camera was in. Required: without it there is no
    #: conversion gain and the frame cannot be read in electrons.
    mode: str
    #: Brightest pixel on the object of interest, raw ADU.
    peak_adu: float
    #: Median of a particle-free but *illuminated* region, raw ADU. This is
    #: what makes it background rather than dark: autofluorescence, scatter and
    #: out-of-focus fluorescence are all in here.
    background_adu: float
    #: Sensor zero, raw ADU, from a dark frame at the same exposure.
    offset_adu: float = 0.0
    #: How many pixels the spot covers. Drives the read-noise term in SNR;
    #: ``2*pi*sigma_psf^2 / p^2`` is a reasonable estimate if not counted.
    n_pix_spot: int = 1
    #: Whether on-camera despeckle was off. ``None`` means nobody checked, which
    #: is not the same as off (docs/06-pitfalls.md C1 -- it was enabled in every
    #: archive generation).
    despeckle_off: bool | None = None
    #: Free-text note on what the frame was of, for the record.
    subject: str | None = None


@dataclass
class FrameRefusal:
    """Why a frame cannot be used. Carries the fix, never just the complaint."""

    code: str
    message: str
    action: str


def validate(frame: FrameMeasurement, detector: Detector) -> list[FrameRefusal]:
    """Everything wrong with this frame, in one pass.

    Returns an empty list when the frame is usable. Like the gates, this does
    not stop at the first problem -- the experimenter walks to the microscope
    once.
    """
    out: list[FrameRefusal] = []
    mode = detector.modes.get(frame.mode)

    if mode is None:
        out.append(
            FrameRefusal(
                "unknown_mode",
                f"Mode {frame.mode!r} is not registered for detector "
                f"'{detector.label}'. Known: {', '.join(sorted(detector.modes)) or 'none'}.",
                "Record which readout mode the frame was taken in, or add the "
                "mode to data/detectors.yaml.",
            )
        )
    else:
        if mode.full_well_e is None or not mode.bit_depth:
            out.append(
                FrameRefusal(
                    "no_conversion_gain",
                    f"Mode {frame.mode!r} has no full well or bit depth on "
                    "record, so ADU cannot be converted to electrons.",
                    f"Add full_well_e and bit_depth for '{detector.label}' mode "
                    f"{frame.mode!r} to data/detectors.yaml.",
                )
            )
        else:
            ceiling = CLIPPED_ADU_FRACTION * (2**mode.bit_depth)
            if frame.peak_adu >= ceiling:
                out.append(
                    FrameRefusal(
                        "peak_clipped",
                        f"Peak {frame.peak_adu:.0f} ADU is at or above "
                        f"{ceiling:.0f} ({CLIPPED_ADU_FRACTION:.0%} of the "
                        f"{mode.bit_depth}-bit ceiling) -- the pixel may be "
                        "clipped, making this a lower bound, not a measurement.",
                        "Re-shoot with a shorter exposure or less light until "
                        "the peak sits comfortably mid-range.",
                    )
                )

    if frame.despeckle_off is False:
        out.append(
            FrameRefusal(
                "despeckle_on",
                "On-camera despeckle was on. It replaces threshold-crossing "
                "pixels with a neighbour value, which breaks pixel-value "
                "linearity and makes noise spatially correlated "
                "(docs/06-pitfalls.md C1).",
                "Turn despeckle off in the PVCAM post-processing properties and "
                "re-shoot. This frame cannot be repaired afterwards.",
            )
        )

    if frame.exposure_ms <= 0:
        out.append(
            FrameRefusal(
                "no_exposure",
                "Exposure must be positive to turn ADU into a rate.",
                "Record the exposure the frame was taken at.",
            )
        )

    if frame.peak_adu <= frame.background_adu:
        out.append(
            FrameRefusal(
                "no_signal",
                f"Peak {frame.peak_adu:.0f} ADU is not above background "
                f"{frame.background_adu:.0f} ADU -- there is no signal to "
                "measure.",
                "Point at an actual particle, or raise the light level and "
                "re-shoot.",
            )
        )

    if frame.background_adu < frame.offset_adu:
        out.append(
            FrameRefusal(
                "background_below_offset",
                f"Background {frame.background_adu:.0f} ADU is below the offset "
                f"{frame.offset_adu:.0f} ADU, which is unphysical.",
                "Re-measure the offset from a dark frame at this exposure; a "
                "datasheet offset from another camera or mode will not do.",
            )
        )

    return out


def electron_rates(frame: FrameMeasurement, detector: Detector) -> tuple[float, float]:
    """``(signal_e_per_s, background_e_per_s)`` from the frame.

    ``signal`` is background-subtracted, matching docs/04 §4's ``N_sig``
    (``k_det * t_exp``) -- the SNR numerator, not the well-filling total. Call
    :func:`validate` first; this assumes the frame passed.
    """
    mode = detector.modes[frame.mode]
    gain = mode.full_well_e / (2**mode.bit_depth)  # e- per count
    t_s = frame.exposure_ms * 1e-3
    signal = (frame.peak_adu - frame.background_adu) * gain / t_s
    background = (frame.background_adu - frame.offset_adu) * gain / t_s
    return signal, background


# --------------------------------------------------------------------------
# Inverting the gates
# --------------------------------------------------------------------------


def exposure_for_snr(
    signal_e_per_s: float,
    background_e_per_s: float,
    dark_e_per_s: float,
    n_pix_spot: int,
    read_noise_e: float,
    target_snr: float,
) -> float:
    """Exposure (s) that reaches ``target_snr``. Inverts docs/04 §4's SNR.

    With ``S`` the signal rate and ``B`` the background+dark rate, requiring
    ``S t / sqrt((S+B) t + n sigma^2) = SNR`` gives a quadratic in ``t``:

        S^2 t^2 - SNR^2 (S+B) t - SNR^2 n sigma^2 = 0

    The positive root is the answer. Note it is *not* proportional to
    ``SNR^2/S``: the read-noise term makes short exposures disproportionately
    expensive, which is exactly why a low-read-noise mode can beat a
    fast one.
    """
    if signal_e_per_s <= 0 or target_snr <= 0:
        return math.inf
    a = signal_e_per_s**2
    b = -(target_snr**2) * (signal_e_per_s + background_e_per_s + dark_e_per_s)
    c = -(target_snr**2) * n_pix_spot * read_noise_e**2
    disc = b * b - 4 * a * c  # c <= 0, so disc >= b^2 >= 0
    return (-b + math.sqrt(disc)) / (2 * a)


def exposure_ceiling_saturation(
    signal_e_per_s: float,
    background_e_per_s: float,
    dark_e_per_s: float,
    full_well_e: float,
    bit_depth: int,
    offset_adu: float,
) -> float:
    """Exposure (s) at which G6 starts clipping.

    Both halves of G6 are applied, and **background counts toward filling the
    well** -- the pixel does not know which electrons were interesting. (Note
    ``checks.check_saturation`` currently omits the background term from its
    peak; on a camera whose full well is 1,000 e- that omission is not small.)
    """
    rate = signal_e_per_s + background_e_per_s + dark_e_per_s
    if rate <= 0:
        return math.inf
    well_limit_e = SATURATION_FRACTION * full_well_e
    gain = full_well_e / (2**bit_depth)
    adu_limit_e = max(ADU_FRACTION * (2**bit_depth) - offset_adu, 0.0) * gain
    return min(well_limit_e, adu_limit_e) / rate


def exposure_ceiling_blur(target_fps: float) -> float:
    """Exposure (s) that keeps G8's duty cycle at or below 30%.

    ``tau_min = 1/f``, so ``t_exp <= 0.3/f``. Tracking only -- morphology
    imaging has no MSD to bias.
    """
    if target_fps <= 0:
        return math.inf
    return DUTY_CYCLE_MAX / target_fps


def exposure_ceiling_frame_rate(target_fps: float) -> float:
    """Exposure (s) that still fits inside the requested frame period.

    ``t_frame = max(t_exp + overhead, t_readout) <= 1/f``, so the exposure
    ceiling is simply ``1/f``. Readout imposes a *separate* condition —
    ``t_readout <= 1/f`` — which no exposure can rescue, so it is handled as an
    infeasibility in :func:`compare_modes` rather than folded in here.
    """
    if target_fps <= 0:
        return math.inf
    return 1.0 / target_fps


# --------------------------------------------------------------------------
# The comparison
# --------------------------------------------------------------------------


@dataclass
class ModeOption:
    """One mode, evaluated against the frame."""

    mode: str
    bit_depth: int
    conversion_gain_e_per_count: float
    read_noise_e: float
    effective_read_noise_e: float
    full_well_e: float
    line_time_us: float | None
    readout_ms: float | None
    #: Exposure needed to reach the SNR target, ms. inf when unreachable.
    exposure_for_snr_ms: float
    #: Where each gate puts its ceiling, ms.
    ceiling_saturation_ms: float
    ceiling_blur_ms: float | None
    ceiling_frame_rate_ms: float | None
    #: The exposure this module would actually use: the smallest that meets the
    #: SNR target, since anything longer only adds dose (lens 5) and blur (G8).
    exposure_ms: float | None
    snr_achieved: float | None
    max_fps: float | None
    feasible: bool
    #: Which ceiling bit first, or why it is infeasible.
    binding_constraint: str
    notes: list[str] = field(default_factory=list)

    @property
    def headroom(self) -> float:
        """Ceiling / required. Below 1.0 means the mode cannot do it."""
        lowest = min(
            c
            for c in (
                self.ceiling_saturation_ms,
                self.ceiling_blur_ms,
                self.ceiling_frame_rate_ms,
            )
            if c is not None
        )
        if self.exposure_for_snr_ms <= 0 or not math.isfinite(self.exposure_for_snr_ms):
            return 0.0
        return lowest / self.exposure_for_snr_ms


def compare_modes(
    frame: FrameMeasurement,
    detector: Detector,
    *,
    target_snr: float,
    roi_height_px: int | None = None,
    target_fps: float | None = None,
    task_kind: str | None = None,
    dark_e_per_s: float | None = None,
) -> list[ModeOption]:
    """Evaluate every registered mode against one frame, best first.

    ``task_kind`` matters: the motion-blur ceiling is only applied for
    ``"tracking"``, since morphology imaging has no MSD to bias (docs/04 §2's
    task dependence, same branch as ``checks.check_motion_blur``).

    Ranking is by whether the mode can hit the SNR target at all, then by
    headroom -- not by SNR at maximum exposure, which would just reward
    whichever mode has the deepest well regardless of whether the experiment
    needs it.
    """
    if frame.mode not in detector.modes:
        raise ValueError(
            f"mode {frame.mode!r} is not registered for '{detector.label}'. "
            "Call validate() first -- it reports this as a refusal with an action."
        )
    signal, background = electron_rates(frame, detector)
    dark = dark_e_per_s if dark_e_per_s is not None else (detector.dark_e_per_s or 0.0)

    out: list[ModeOption] = []
    for name, mode in detector.modes.items():
        if mode.full_well_e is None or not mode.bit_depth or mode.read_noise_e is None:
            continue
        gain = mode.full_well_e / (2**mode.bit_depth)
        eff_read = effective_read_noise_e(mode.read_noise_e, mode.full_well_e, mode.bit_depth)

        readout_s = (
            readout_time_s(mode.line_time_us, roi_height_px)
            if mode.line_time_us is not None and roi_height_px
            else None
        )

        t_snr = exposure_for_snr(
            signal, background, dark, frame.n_pix_spot, eff_read, target_snr
        )
        t_sat = exposure_ceiling_saturation(
            signal, background, dark, mode.full_well_e, mode.bit_depth, frame.offset_adu
        )
        t_blur = (
            exposure_ceiling_blur(target_fps)
            if target_fps and task_kind == "tracking"
            else None
        )
        t_fps = exposure_ceiling_frame_rate(target_fps) if target_fps else None

        ceilings = {"saturation (G6)": t_sat}
        if t_blur is not None:
            ceilings["motion blur (G8)"] = t_blur
        if t_fps is not None:
            ceilings["frame period (G9)"] = t_fps
        binding, lowest = min(ceilings.items(), key=lambda kv: kv[1])

        # Readout is not an exposure ceiling -- no exposure can shorten it. If
        # the rows alone take longer than the frame period, this mode cannot
        # reach the target frame rate at any exposure (docs/06-pitfalls.md C3:
        # only the row count helps, and that is an ROI decision, not a mode one).
        readout_blocks = bool(
            target_fps and readout_s is not None and readout_s > 1.0 / target_fps
        )

        feasible = math.isfinite(t_snr) and t_snr <= lowest and not readout_blocks
        t_use = t_snr if feasible else None

        snr_achieved = None
        if t_use is not None:
            # photometry.snr, not a local copy: whatever convention that
            # function settles on (see this module's docstring), the gate and
            # this recommender move together.
            snr_achieved = snr(
                signal * t_use,
                background * t_use,
                dark * t_use,
                frame.n_pix_spot,
                eff_read,
            )

        # Only meaningful once an exposure has been chosen. Reporting
        # ``1/ceiling`` for an infeasible mode printed a flattering frame rate
        # next to a row marked infeasible -- e.g. "333 fps" for a mode that
        # cannot reach the SNR target at all.
        max_fps = None
        if readout_s is not None and t_use is not None:
            period = max(t_use, readout_s)
            max_fps = 1.0 / period if period > 0 else math.inf

        notes: list[str] = []
        if readout_s is None:
            notes.append(
                "no ROI height or line time supplied -- frame rate not evaluated"
            )
        if readout_blocks:
            notes.append(
                f"readout alone is {readout_s * 1e3:.2f} ms, longer than the "
                f"{1e3 / target_fps:.2f} ms frame period -- no exposure fixes "
                "this; shrink the ROI height or lower the target"
            )
        if not feasible:
            if not math.isfinite(t_snr):
                notes.append("SNR target unreachable at any exposure")
            elif t_snr > lowest:
                notes.append(
                    f"needs {t_snr * 1e3:.2f} ms but {binding} caps it at "
                    f"{lowest * 1e3:.2f} ms"
                )
        if mode.bit_depth <= 8:
            notes.append(
                f"{mode.bit_depth}-bit: full well only {mode.full_well_e:.0f} e-"
            )

        out.append(
            ModeOption(
                mode=name,
                bit_depth=mode.bit_depth,
                conversion_gain_e_per_count=gain,
                read_noise_e=mode.read_noise_e,
                effective_read_noise_e=eff_read,
                full_well_e=mode.full_well_e,
                line_time_us=mode.line_time_us,
                readout_ms=readout_s * 1e3 if readout_s is not None else None,
                exposure_for_snr_ms=t_snr * 1e3,
                ceiling_saturation_ms=t_sat * 1e3,
                ceiling_blur_ms=t_blur * 1e3 if t_blur is not None else None,
                ceiling_frame_rate_ms=t_fps * 1e3 if t_fps is not None else None,
                exposure_ms=t_use * 1e3 if t_use is not None else None,
                snr_achieved=snr_achieved,
                max_fps=max_fps,
                feasible=feasible,
                binding_constraint=binding,
                notes=notes,
            )
        )

    out.sort(key=lambda o: (not o.feasible, -o.headroom))
    return out


def localization_precision_nm(
    option: ModeOption,
    signal_e_per_s: float,
    background_e_per_s: float,
    sigma_psf_nm: float,
    pixel_nm: float,
) -> float | None:
    """1-sigma localization precision at this option's exposure, nm.

    Reported rather than gated: turning a precision target into a *required*
    exposure needs the full Mortensen expression inverted numerically, and the
    honest thing at this stage is to state what the chosen exposure buys.
    """
    if option.exposure_ms is None:
        return None
    t_s = option.exposure_ms * 1e-3
    n_photons = signal_e_per_s * t_s
    background_e = background_e_per_s * t_s
    if n_photons <= 0:
        return None
    var = localization_variance_nm2(sigma_psf_nm, pixel_nm, n_photons, background_e)
    return math.sqrt(var)
