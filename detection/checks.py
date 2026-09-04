"""Individual detection checks -- G5 (sampling), G6 (saturation), G7 (SNR),
G8 (motion blur), G9 (frame-rate realizability). docs/04-decision-engine.md
§2, §4, §5; docs/05-consensus-gate.md §5.

Mirrors optics.checks / trapping.checks: independent margins
(achieved / required), never booleans, for the same reasons -- see
optics/checks.py's module docstring.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .photometry import (
    effective_pixel_nm,
    effective_read_noise_e,
    localization_variance_nm2,
    peak_adu,
    peak_electrons,
    snr,
)
from .timing import duty_cycle, frame_period_s, max_fps, motion_blur_bias_fraction, readout_time_s

if TYPE_CHECKING:
    from .setup import DetectionSetup

# --------------------------------------------------------------------------
# Kinds -- what it means when this check fails. See docs/05 §2.
# --------------------------------------------------------------------------
HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    "nyquist_divisor": 2.0,
    "full_well_fraction": 0.7,
    "adu_fraction": 0.9,
    "snr_target_default": 5.0,
    "duty_cycle_max": 0.3,
}


@dataclass
class CheckResult:
    code: str
    kind: str
    margin: float
    severity: str  # ok | info | warn | fail
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.margin):
            self.margin = MAX_MARGIN
        self.margin = max(0.0, min(float(self.margin), MAX_MARGIN))

    @property
    def passed(self) -> bool:
        return self.margin >= 1.0


@dataclass
class Check:
    code: str
    kind: str
    #: which facts must exist before this check means anything
    requires: tuple[str, ...]
    run: Callable[["DetectionSetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "DetectionSetup") -> set[str]:
    """Which inputs this setup actually supplies.

    A check whose ``requires`` is not satisfied is not run and not graded --
    it is reported as blocking, because a computed number would be fiction.
    """
    facts: set[str] = set()
    cam = setup.camera
    if setup.objective.na and setup.objective.na > 0:
        facts.add("objective.na")
    if setup.mag_objective and setup.mag_objective > 0:
        facts.add("magnification")
    if cam.detector.pixel_um:
        facts.add("pixel")
    if setup.acquisition.task_kind in {"imaging", "tracking"}:
        facts.add("task_kind")
    if cam.roi_height_px:
        facts.add("roi_height")
    if cam.effective_row_time_us() is not None:
        facts.add("row_time")
    if cam.effective_bit_depth() is not None:
        facts.add("detector.bit_depth")
    if cam.effective_full_well_e() is not None:
        facts.add("detector.full_well")
    if cam.effective_read_noise_e() is not None:
        facts.add("detector.read_noise")
    if setup.photons.signal_e_per_s is not None:
        facts.add("photon.signal")
    if setup.photons.background_e_per_s is not None:
        facts.add("photon.background")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_sampling(setup: "DetectionSetup") -> CheckResult:
    """G5: task-dependent pixel-size direction (docs/04 §2).

    Morphology imaging wants Nyquist (``p <= r/2``); tracking wants
    ``p`` near sigma_PSF, and mechanically applying Nyquist there makes
    localization precision *worse* (docs/06-pitfalls.md §C6) -- the finite
    optimum only exists because of background, so the tracking branch needs
    a measured photon budget to grade, not just geometry.
    """
    p_nm, p_evidence = setup.pixel_size_nm()
    r_nm = setup.objective.resolution_nm(setup.wavelength_em_nm)
    sigma_nm = setup.objective.psf_sigma_nm(setup.wavelength_em_nm)
    task = setup.acquisition.task_kind

    if task == "imaging":
        nyquist_nm = r_nm / LIMITS["nyquist_divisor"]
        margin = nyquist_nm / p_nm if p_nm > 0 else MAX_MARGIN
        ok = margin >= 1.0
        return CheckResult(
            "sampling" if ok else "sampling.undersampled",
            SOFT,
            margin,
            "ok" if ok else "fail",
            f"Pixel {p_nm:.0f} nm vs Nyquist limit {nyquist_nm:.0f} nm "
            f"(Rayleigh resolution {r_nm:.0f} nm).",
            action=None
            if ok
            else "Increase magnification/intermediate lens or reduce binning "
            "to bring the effective pixel below the Nyquist limit.",
            numbers={
                "pixel_nm": p_nm,
                "pixel_evidence": p_evidence,
                "nyquist_nm": nyquist_nm,
                "rayleigh_nm": r_nm,
            },
        )

    # tracking
    photons = setup.photons
    if photons.signal_e_per_s is None or photons.background_e_per_s is None:
        return CheckResult(
            "sampling.unconfirmed",
            INFO,
            MAX_MARGIN,
            "info",
            f"Pixel {p_nm:.0f} nm vs sigma_PSF {sigma_nm:.0f} nm -- tracking's "
            "optimal pixel size depends on the achieved photon count and "
            "background (docs/04 §2), which have not been supplied yet.",
            action="Supply photons.signal_e_per_s and photons.background_e_per_s "
            "to grade this.",
            numbers={
                "pixel_nm": p_nm,
                "pixel_evidence": p_evidence,
                "psf_sigma_nm": sigma_nm,
            },
        )

    exposure_s = setup.acquisition.exposure_ms * 1e-3
    n_photons = photons.signal_e_per_s * exposure_s
    background_e = photons.background_e_per_s * exposure_s
    var_actual = localization_variance_nm2(sigma_nm, p_nm, n_photons, background_e)
    nyquist_nm = r_nm / LIMITS["nyquist_divisor"]
    var_nyquist = localization_variance_nm2(sigma_nm, nyquist_nm, n_photons, background_e)
    margin = var_nyquist / var_actual if var_actual > 0 else MAX_MARGIN
    ok = margin >= 1.0
    return CheckResult(
        "sampling" if ok else "sampling.wrong_direction",
        BIAS,
        margin,
        "ok" if ok else "fail",
        f"At {p_nm:.0f} nm pixels the localization precision is "
        f"{math.sqrt(var_actual):.0f} nm (1 sigma); the imaging-Nyquist pixel "
        f"({nyquist_nm:.0f} nm) would give {math.sqrt(var_nyquist):.0f} nm.",
        action=None
        if ok
        else "Mechanically applying the imaging Nyquist limit to a tracking "
        "channel makes localization precision worse, not better "
        "(docs/06-pitfalls.md §C6). Choose a pixel size near sigma_PSF instead.",
        numbers={
            "pixel_nm": p_nm,
            "pixel_evidence": p_evidence,
            "psf_sigma_nm": sigma_nm,
            "loc_precision_nm": math.sqrt(var_actual),
            "nyquist_loc_precision_nm": math.sqrt(var_nyquist),
        },
    )


def check_saturation(setup: "DetectionSetup") -> CheckResult:
    """G6: peak electrons < 70% full well, peak ADU < 90% of 2**bits."""
    cam = setup.camera
    photons = setup.photons
    full_well = cam.effective_full_well_e()
    bits = cam.effective_bit_depth()
    exposure_s = setup.acquisition.exposure_ms * 1e-3
    dark_e = (cam.detector.dark_e_per_s or 0.0) * exposure_s
    signal_e = photons.signal_e_per_s * exposure_s
    peak_e = peak_electrons(signal_e, dark_e)

    e_margin = (LIMITS["full_well_fraction"] * full_well) / peak_e if peak_e > 0 else MAX_MARGIN
    adu = peak_adu(peak_e, full_well, bits, cam.offset_adu)
    adu_ceiling = LIMITS["adu_fraction"] * (2**bits)
    adu_margin = adu_ceiling / adu if adu > 0 else MAX_MARGIN
    margin = min(e_margin, adu_margin)

    if margin >= 1.0:
        return _ok(
            "saturation",
            HARD,
            margin,
            f"Peak signal {peak_e:.0f} e- of {full_well:.0f} full well; "
            f"{adu:.0f} ADU of {2**bits} ({bits}-bit).",
            peak_e=peak_e,
            full_well_e=full_well,
            peak_adu=adu,
            bit_depth=bits,
        )
    return CheckResult(
        "saturation.clipped",
        HARD,
        margin,
        "fail",
        f"Peak signal {peak_e:.0f} e- against {full_well:.0f} full well, or "
        f"{adu:.0f} ADU against a {2**bits} ({bits}-bit) ceiling -- clipped "
        "values cannot be recovered afterwards.",
        action="Lower exposure time or illumination, or bin/switch to a mode "
        "with a larger full well.",
        numbers={"peak_e": peak_e, "full_well_e": full_well, "peak_adu": adu, "bit_depth": bits},
    )


def check_snr(setup: "DetectionSetup") -> CheckResult:
    """G7: achieved SNR vs. target (docs/04 §4), including the quantization
    noise term that a 12-bit mode can let dominate read noise
    (docs/06-pitfalls.md §C2)."""
    cam = setup.camera
    photons = setup.photons
    full_well = cam.effective_full_well_e()
    bits = cam.effective_bit_depth()
    read_noise = cam.effective_read_noise_e()
    exposure_s = setup.acquisition.exposure_ms * 1e-3

    signal_e = photons.signal_e_per_s * exposure_s
    background_e = photons.background_e_per_s * exposure_s
    dark_e = (cam.detector.dark_e_per_s or 0.0) * exposure_s
    eff_read = effective_read_noise_e(read_noise, full_well, bits)
    achieved = snr(signal_e, background_e, dark_e, photons.n_pix_spot, eff_read)

    target = photons.target_snr if photons.target_snr is not None else LIMITS["snr_target_default"]
    margin = achieved / target if target > 0 else MAX_MARGIN

    default_note = "" if photons.target_snr is not None else " (default target, none supplied)"
    if margin >= 1.0:
        return _ok(
            "snr",
            SOFT,
            margin,
            f"SNR {achieved:.1f} vs target {target:.1f}{default_note} "
            f"(effective read noise {eff_read:.2f} e- at {bits}-bit).",
            snr=achieved,
            target_snr=target,
            effective_read_noise_e=eff_read,
        )
    return CheckResult(
        "snr.low",
        SOFT,
        margin,
        "fail",
        f"SNR {achieved:.1f} is below target {target:.1f}{default_note}. "
        f"Effective read noise is {eff_read:.2f} e- at {bits}-bit "
        "(quantization noise included).",
        action="Increase exposure/illumination, reduce background, or use a "
        "higher-bit-depth mode if quantization noise is the limiter.",
        numbers={"snr": achieved, "target_snr": target, "effective_read_noise_e": eff_read},
    )


def check_motion_blur(setup: "DetectionSetup") -> CheckResult:
    """G8: Savin-Doyle MSD bias, duty cycle <= 30% (docs/04 §5).

    Only applies to tracking/dynamics measurements -- morphology imaging has
    no MSD to bias, so it is reported ``INFO``, not graded.
    """
    cam = setup.camera
    acq = setup.acquisition
    row_time = cam.effective_row_time_us()
    readout_s = readout_time_s(row_time, cam.roi_height_px)
    t_frame = frame_period_s(acq.exposure_ms, readout_s, cam.frame_overhead_ms)

    if acq.task_kind != "tracking":
        return CheckResult(
            "motion_blur.not_applicable",
            INFO,
            MAX_MARGIN,
            "info",
            "Motion-blur bias applies to dynamic/tracking measurements, not "
            "morphology imaging.",
            numbers={"frame_period_s": t_frame},
        )

    duty = duty_cycle(acq.exposure_ms, t_frame)
    bias_fraction = motion_blur_bias_fraction(duty)
    margin = LIMITS["duty_cycle_max"] / duty if duty > 0 else MAX_MARGIN
    ok = margin >= 1.0

    numbers = {"duty_cycle": duty, "frame_period_s": t_frame, "bias_fraction": bias_fraction}
    d = setup.photons.diffusion_coefficient_m2_s
    if d is not None:
        exposure_s = acq.exposure_ms * 1e-3
        numbers["msd_bias_nm2"] = 2 * d * (exposure_s / 3.0) * 1e18

    if ok:
        return CheckResult(
            "motion_blur",
            BIAS,
            margin,
            "ok",
            f"Duty cycle {duty * 100:.0f}% keeps the shortest-lag MSD bias at "
            f"{bias_fraction * 100:.1f}% (limit 10%).",
            numbers=numbers,
        )
    return CheckResult(
        "motion_blur.biased",
        BIAS,
        margin,
        "fail",
        f"Duty cycle {duty * 100:.0f}% (limit {LIMITS['duty_cycle_max'] * 100:.0f}%) "
        f"gives a {bias_fraction * 100:.1f}% MSD bias at the shortest lag -- "
        "looks like a straight line, is not one (docs/04 §5).",
        action="Shorten exposure relative to the frame period, or apply the "
        "Savin-Doyle correction before fitting the MSD.",
        numbers=numbers,
    )


def check_frame_rate(setup: "DetectionSetup") -> CheckResult:
    """G9: f <= 1/max(t_exp, t_readout) (docs/04 §5).

    ``t_frame``/``max_fps`` are always computable from row time and ROI;
    grading against a target only happens once the experiment states one
    (mirrors trapping.checks.check_sampling's treatment of detector_fps).
    """
    cam = setup.camera
    acq = setup.acquisition
    row_time = cam.effective_row_time_us()
    readout_s = readout_time_s(row_time, cam.roi_height_px)
    t_frame = frame_period_s(acq.exposure_ms, readout_s, cam.frame_overhead_ms)
    fps = max_fps(t_frame)

    if acq.target_fps is None:
        return CheckResult(
            "frame_rate.unconfirmed",
            INFO,
            MAX_MARGIN,
            "info",
            f"Realizable frame rate is {fps:.0f} fps (t_frame={t_frame * 1e3:.2f} ms, "
            f"readout={readout_s * 1e3:.2f} ms); no target frame rate supplied to "
            "grade against.",
            numbers={"max_fps": fps, "frame_period_s": t_frame, "readout_s": readout_s},
        )

    margin = fps / acq.target_fps
    # Tolerance, not sloppiness: t_frame is assembled by float arithmetic from
    # exposure + overhead, so a camera set up to hit the target exactly lands a
    # few ulp below it and used to report "only 240 fps is realizable, below the
    # 240 fps target" -- a self-contradiction at the printed precision. One part
    # in 1e-9 is far tighter than any real frame-rate measurement.
    ok = margin >= 1.0 - 1e-9
    numbers = {
        "max_fps": fps,
        "target_fps": acq.target_fps,
        "frame_period_s": t_frame,
        "readout_s": readout_s,
    }
    if ok:
        return CheckResult(
            "frame_rate",
            HARD,
            margin,
            "ok",
            f"{fps:.0f} fps realizable clears the {acq.target_fps:.0f} fps target.",
            numbers=numbers,
        )
    return CheckResult(
        "frame_rate.unrealizable",
        HARD,
        margin,
        "fail",
        f"Only {fps:.0f} fps is realizable (t_frame={t_frame * 1e3:.2f} ms), "
        f"below the {acq.target_fps:.0f} fps target -- this will not run as "
        "requested.",
        action="Shrink the ROI height (width does not help, "
        "docs/06-pitfalls.md §C3), shorten exposure, or lower the target.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("sampling", SOFT, ("objective.na", "magnification", "pixel", "task_kind"), check_sampling),
    Check(
        "saturation",
        HARD,
        ("detector.full_well", "detector.bit_depth", "photon.signal"),
        check_saturation,
    ),
    Check(
        "snr",
        SOFT,
        (
            "detector.full_well",
            "detector.bit_depth",
            "detector.read_noise",
            "photon.signal",
            "photon.background",
        ),
        check_snr,
    ),
    Check("motion_blur", BIAS, ("task_kind", "row_time", "roi_height"), check_motion_blur),
    Check("frame_rate", HARD, ("row_time", "roi_height"), check_frame_rate),
]


# --------------------------------------------------------------------------
# Feasibility grading -- same table as optics.checks, kept local so this
# lens does not depend on the optical-path lens's module.
# --------------------------------------------------------------------------

GRADES: list[tuple[float, str]] = [
    (3.0, "ROUTINE"),
    (1.5, "COMFORTABLE"),
    (1.0, "TIGHT"),
    (0.5, "HARD"),
    (0.2, "MARGINAL"),
    (0.0, "INFEASIBLE"),
]

GRADE_NOTES = {
    "ROUTINE": "Comfortable headroom. If it fails, the settings are not to blame.",
    "COMFORTABLE": "Normal range.",
    "TIGHT": "No headroom. Sample preparation quality decides the outcome.",
    "HARD": "Operating at the limit. May proceed, but low success rate and poor reproducibility.",
    "MARGINAL": "Data comes out, but interpret with great care.",
    "INFEASIBLE": "Impossible without improvement.",
}


def grade(margin: float) -> str:
    for threshold, name in GRADES:
        if margin >= threshold:
            return name
    return "INFEASIBLE"


#: Grades in ascending order of quality, derived from GRADES so the two cannot
#: drift apart.
GRADE_ORDER: tuple[str, ...] = tuple(name for _, name in reversed(GRADES))


def meets_grade(feasibility: str, minimum: str = "TIGHT") -> bool:
    """Is this feasibility at least ``minimum``?

    docs/05-consensus-gate.md's Verdict schema requires ``feasibility >= TIGHT``
    for a verdict to advance. ``UNKNOWN`` -- and anything unrecognised -- does
    not: an ungraded verdict has not earned the right to move on.
    """
    if feasibility not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(feasibility) >= GRADE_ORDER.index(minimum)
