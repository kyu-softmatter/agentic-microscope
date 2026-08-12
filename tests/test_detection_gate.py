"""Tests for detection.gate.evaluate -- mirrors tests/test_trapping_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

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


def test_sampling_wrong_direction_downgrades_to_pass_with_changes_for_tracking():
    """docs/06-pitfalls.md §C6: the legacy 100x/1.5x pixel (73.3 nm) is
    finer than the imaging-Nyquist limit (140.5 nm); at a modest photon
    budget that makes tracking precision *worse*, not better."""
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=0.5, task_kind="tracking")
    photons = PhotonBudget(signal_e_per_s=800_000.0, background_e_per_s=32_000.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.status == "PASS_WITH_CHANGES"
    assert v.bottleneck == "sampling.wrong_direction"


def test_motion_blur_biased_at_full_duty_cycle():
    """10 ms exposure against a ~1.8 ms readout gives ~100% duty cycle --
    well past the 30% limit (docs/04 §5)."""
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=176, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=10.0, task_kind="tracking")
    photons = PhotonBudget(signal_e_per_s=5000.0, background_e_per_s=200.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.status == "PASS_WITH_CHANGES"
    assert any(f.code == "motion_blur.biased" for f in v.findings)


def test_fails_frame_rate_when_target_exceeds_the_realizable_rate():
    """Full-frame (1608 rows) readout tops out at ~60.5 fps (docs/04 §5);
    asking for 200 fps is not realizable as requested."""
    camera = Camera(detector=_detector(), mode="Slow", roi_height_px=1608, row_time_us=10.28)
    acquisition = Acquisition(exposure_ms=5.0, task_kind="imaging", target_fps=200.0)
    photons = PhotonBudget(signal_e_per_s=20_000.0, background_e_per_s=200.0)
    v = evaluate(_setup(camera=camera, acquisition=acquisition, photons=photons))
    assert v.status == "FAIL"
    assert v.bottleneck == "frame_rate.unrealizable"
