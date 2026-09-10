"""Tests for detection.gate.evaluate -- mirrors tests/test_trapping_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

import pytest

from optics.components import Detector, DetectorMode, Objective
from optics.spectra import Spectrum

from detection.checks import check_sampling
from detection.gate import evaluate
from detection.setup import Acquisition, Camera, DetectionSetup, PhotonBudget

OBJECTIVE_100X = Objective("100x/1.45", 100.0, 1.45, "oil", verified_na=True)


def _detector(**overrides) -> Detector:
    defaults = dict(
        label="TestCam",
        qe=Spectrum.constant(0.9, "TestCam.QE"),
        pixel_um=11.0,
        dark_e_per_s=0.0,
        modes={
            "Fast": DetectorMode(
                "Fast", bit_depth=12, read_noise_e=1.6, full_well_e=62000, line_time_us=3.53125
            ),
            "Slow": DetectorMode(
                "Slow", bit_depth=16, read_noise_e=1.3, full_well_e=80000, line_time_us=10.28
            ),
        },
    )
    defaults.update(overrides)
    return Detector(**defaults)


def _setup(**overrides) -> DetectionSetup:
    camera = overrides.pop(
        "camera", Camera(detector=_detector(), mode="Slow", roi_height_px=176)
    )
    acquisition = overrides.pop(
        "acquisition", Acquisition(exposure_ms=10.0, task_kind="imaging")
    )
    photons = overrides.pop(
        "photons", PhotonBudget(signal_e_per_s=5000.0, background_e_per_s=200.0)
    )
    defaults = dict(
        objective=OBJECTIVE_100X,
        wavelength_em_nm=668.0,
        mag_objective=100.0,
        mag_intermediate=1.5,  # -> 73.3 nm pixel, the legacy 100x/1.5x setup
        camera=camera,
        acquisition=acquisition,
        photons=photons,
    )
    defaults.update(overrides)
    return DetectionSetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_when_na_is_missing():
    v = evaluate(_setup(objective=Objective("no-na", 100.0, 0.0)))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.na" for f in v.findings)


def test_blocked_when_pixel_pitch_is_missing():
    camera = Camera(detector=_detector(pixel_um=None), mode="Slow", roi_height_px=176)
    v = evaluate(_setup(camera=camera))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.pixel_um" for f in v.findings)


def test_blocked_when_task_kind_is_not_specified():
    v = evaluate(_setup(acquisition=Acquisition(exposure_ms=10.0, task_kind=None)))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.task_kind" for f in v.findings)


def test_blocked_when_detector_mode_is_unresolved():
    camera = Camera(detector=_detector(), mode=None, roi_height_px=176)
    v = evaluate(_setup(camera=camera))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.detector_mode" for f in v.findings)


def test_blocked_when_row_time_is_missing():
    det = _detector(
        modes={
            "NoTiming": DetectorMode(
                "NoTiming", bit_depth=16, read_noise_e=1.3, full_well_e=80000, line_time_us=None
            )
        }
    )
    camera = Camera(detector=det, mode="NoTiming", roi_height_px=176)
    v = evaluate(_setup(camera=camera))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.row_time" for f in v.findings)


def test_blocked_when_photon_facts_are_missing():
    v = evaluate(_setup(photons=PhotonBudget()))
    assert v.status == "BLOCKED"


# ------------------------------------------------------- Phase 1/2, pass ---


def test_passes_imaging_with_measured_inputs():
    camera = Camera(
        detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28
    )
    v = evaluate(_setup(camera=camera))
    assert v.status == "PASS"
    assert v.evidence == "measured"
    assert v.advances is True


def test_evidence_downgrades_to_assumed_with_datasheet_row_time():
    """No explicit row_time_us -- falls back to the mode's datasheet
    line_time_us, which is a fallback, not a substitute, for a measurement
    (calibration.mm_live has not been run against the real adapter)."""
    v = evaluate(_setup())
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert any("row time" in i for i in v.assumed_inputs)
    assert v.advances is False


def test_evidence_downgrades_to_assumed_with_unmeasured_dark_current():
    camera = Camera(
        detector=_detector(dark_e_per_s=None), mode="Slow", roi_height_px=176, row_time_us=10.28
    )
    v = evaluate(_setup(camera=camera))
    assert v.evidence == "assumed"
    assert any("dark current" in i for i in v.assumed_inputs)


def test_frame_rate_is_informational_without_a_target_fps():
    """G9's max_fps is always computable; grading only happens once a
    target frame rate is stated (mirrors trapping.checks.check_sampling's
    treatment of detector_fps)."""
    v = evaluate(_setup())
    unconfirmed = [f for f in v.findings if f.code == "frame_rate.unconfirmed"]
    assert len(unconfirmed) == 1
    assert unconfirmed[0].severity == "info"


def test_motion_blur_is_not_applicable_to_imaging():
    v = evaluate(_setup())  # default task_kind="imaging"
    assert any(f.code == "motion_blur.not_applicable" for f in v.findings)


# ------------------------------------------------------- Phase 1/2, fail ---


def test_fails_saturation_when_signal_exceeds_full_well():
    photons = PhotonBudget(signal_e_per_s=8_000_000.0, background_e_per_s=200.0)
    v = evaluate(_setup(photons=photons))
    assert v.status == "FAIL"
    assert v.bottleneck == "saturation.clipped"


def test_snr_below_target_only_downgrades_to_pass_with_changes():
    """SNR is a soft gate (docs/05 §2) -- a low SNR is 'noisier', not a
    hard stop, so it must not flip status to FAIL."""
    photons = PhotonBudget(signal_e_per_s=50.0, background_e_per_s=20.0)
    camera = Camera(detector=_detector(), mode="Fast", roi_height_px=176, row_time_us=10.28)
    v = evaluate(_setup(camera=camera, photons=photons))
    assert v.status == "PASS_WITH_CHANGES"
    assert v.bottleneck == "snr.low"


def test_check_sampling_tracking_is_informational_without_photon_facts():
    """Unit-level: tracking's optimal pixel size depends on photon counts
    the gate cannot fabricate. Exercised directly on the check function,
    since in the full gate this case is already unreachable -- saturation
    and SNR require the same photon facts and would BLOCK Phase 0 first."""
    setup = _setup(
        acquisition=Acquisition(exposure_ms=10.0, task_kind="tracking"),
        photons=PhotonBudget(),
    )
    result = check_sampling(setup)
    assert result.code == "sampling.unconfirmed"
    assert result.severity == "info"


def test_the_legacy_pixel_is_at_the_optimum_not_past_it():
    """RETARGETED 2026-09-09. This asserted the opposite until G5's
    counterfactual was corrected, and the old assertion was an artifact.

    The legacy 100x/1.5x pixel is 73.3 nm and the optimum for this camera and
    photon budget is ~72 nm, so 73.3 nm is essentially ON it: 8.67 nm against
    the Nyquist pixel's 9.30 nm. The old code reported 27.42 nm here and put
    the optimum at 292 nm, because it squared a background *count* as if it
    were a noise and held it fixed while changing the pixel.
    kb/decisions/2026-09-09-g5-localization-variance-corrected.md
    """
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=0.5, task_kind="tracking")
    photons = PhotonBudget(signal_e_per_s=800_000.0, background_e_per_s=32_000.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.margins["sampling"] > 1.0
    assert v.bottleneck != "sampling.wrong_direction"


def test_a_pixel_far_below_the_optimum_still_trips_c6():
    """docs/06-pitfalls.md §C6 has to remain reachable, or the correction
    above would have deleted the pitfall rather than fixed the arithmetic.

    Same optics, a 4 um sensor pixel instead of 11 um -> 26.7 nm at the
    sample, well below the ~72 nm optimum. Background is scaled to that pixel
    area, as the physics requires.
    """
    fine = _detector(pixel_um=4.0)
    camera = Camera(detector=fine, mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=0.5, task_kind="tracking")
    # 32,000 e-/s at 73.3 nm scaled to 26.7 nm pixels: x (26.7/73.3)^2
    photons = PhotonBudget(signal_e_per_s=800_000.0, background_e_per_s=4_240.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.margins["sampling.wrong_direction"] < 1.0


def test_motion_blur_biased_at_full_duty_cycle():
    """10 ms exposure against a ~1.8 ms readout gives ~100% duty cycle --
    well past the 30% limit (docs/04 §5).

    ``achieved_fps`` is now required for this to grade at all: with no rate
    decided G8 reports a bound instead of failing (KH, 2026-09-09). 100 fps is
    the camera's own floor here, so the duty is the same ~100% the test always
    meant -- what changed is that somebody now has to say so.
    """
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=10.0, task_kind="tracking", achieved_fps=100.0)
    photons = PhotonBudget(signal_e_per_s=5000.0, background_e_per_s=200.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.status == "PASS_WITH_CHANGES"
    assert any(f.code == "motion_blur.biased" for f in v.findings)


def test_motion_blur_reports_a_bound_when_no_rate_is_decided():
    """The same configuration with the rate left open must not fail.

    It is the worst case for duty -- the camera's floor maximises it -- so the
    number is reported as an upper bound and excluded from the grade. A gate
    that failed here would be failing a decision nobody has made yet.
    """
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=10.0, task_kind="tracking")
    photons = PhotonBudget(signal_e_per_s=5000.0, background_e_per_s=200.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    codes = {f.code for f in v.findings}
    assert "motion_blur.biased" not in codes
    assert "motion_blur.rate_undecided" in codes
    assert acquisition.fps_source == "undecided"


def test_g8_and_g9_report_the_same_window_from_both_ends():
    """The frame-rate window is one thing seen from two sides (KH, 2026-09-09).

    G8's end is the duty limit (fps <= 0.3/t_exp); G9's is the readout
    ceiling. Both report `fps_at_duty_limit` and both report the camera
    maximum, so synthesis can take a min without re-deriving either -- and if
    the two ever disagree about the same number, that is the bug this catches.
    """
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=512, row_time_us=3.5312)
    acquisition = Acquisition(exposure_ms=0.542, task_kind="tracking")
    photons = PhotonBudget(signal_e_per_s=3_152_856.0, background_e_per_s=4_944.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))

    blur = v.metrics["motion_blur.rate_undecided"]
    rate = v.metrics["frame_rate.unconfirmed"]

    assert blur["fps_at_duty_limit"] == pytest.approx(rate["fps_at_duty_limit"])
    assert blur["fps_hardware_max"] == pytest.approx(rate["fps_hardware_max"])
    assert rate["fps_usable_max"] == pytest.approx(
        min(rate["fps_hardware_max"], rate["fps_at_duty_limit"])
    )
    # 0.3 / 0.542 ms = 553.5 fps, against a 512-row readout ceiling of 553.
    assert blur["fps_at_duty_limit"] == pytest.approx(0.3 / 0.542e-3, rel=1e-9)


def test_g8s_minimum_roi_actually_lands_on_the_duty_limit():
    """`roi_height_min_px` is the actionable form of the bound, so it has to
    be usable as given rather than approximately right.

    ROI height is the only lever that buys a longer period at a fixed
    exposure: the frame period is max(exposure, readout) with no interval
    control, so slowing the rate means lengthening the exposure and duty rises
    toward 100%. That is why this is a minimum ROI and not a minimum rate.
    """
    row_time_us = 3.5312
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=512, row_time_us=row_time_us)
    acquisition = Acquisition(exposure_ms=1.0, task_kind="tracking", achieved_fps=553.0)
    photons = PhotonBudget(signal_e_per_s=3_152_856.0, background_e_per_s=4_944.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))

    assert v.margins["motion_blur.biased"] < 1.0
    roi_min = v.metrics["motion_blur.biased"]["roi_height_min_px"]
    assert roi_min == 944

    # Re-run at that ROI: the duty limit must now be met, not merely approached.
    wider = Camera(detector=_detector(), mode="Slow", roi_height_px=roi_min, row_time_us=row_time_us)
    v2 = evaluate(_setup(camera=wider, acquisition=Acquisition(
        exposure_ms=1.0, task_kind="tracking", achieved_fps=1.0 / (roi_min * row_time_us * 1e-6),
    ), photons=photons))
    assert v2.margins["motion_blur"] >= 1.0


def test_g8s_maximum_exposure_is_the_other_form_of_the_same_bound():
    """`exposure_max_ms` is the dual of `roi_height_min_px` -- same limit, the
    other variable. At a 512-row readout (1.808 ms) it is 30% of that.
    """
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=512, row_time_us=3.5312)
    acquisition = Acquisition(exposure_ms=1.0, task_kind="tracking", achieved_fps=553.0)
    photons = PhotonBudget(signal_e_per_s=3_152_856.0, background_e_per_s=4_944.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.metrics["motion_blur.biased"]["exposure_max_ms"] == pytest.approx(0.542, abs=1e-3)


def test_detection_and_compute_share_the_fps_vocabulary():
    """lens 2 and lens 3 name the same distinction, so the tokens must match.

    G12b (compute) and G8/G9 (detection) are the same requested-vs-achieved
    question seen from the data-rate and the timing side. `undecided` is lens
    2's only addition -- lens 3 cannot compute a data rate without a rate.
    """
    from compute.setup import FPS_SOURCES as COMPUTE_SOURCES
    from detection.setup import FPS_SOURCES as DETECTION_SOURCES

    assert set(COMPUTE_SOURCES) <= set(DETECTION_SOURCES)
    assert set(DETECTION_SOURCES) - set(COMPUTE_SOURCES) == {"undecided"}


def test_fails_frame_rate_when_target_exceeds_the_realizable_rate():
    """Full-frame (1608 rows) readout tops out at ~60.5 fps (docs/04 §5);
    asking for 200 fps is not realizable as requested."""
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=1608, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=5.0, task_kind="imaging", target_fps=200.0)
    photons = PhotonBudget(signal_e_per_s=20_000.0, background_e_per_s=200.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.status == "FAIL"
    assert v.bottleneck == "frame_rate.unrealizable"
