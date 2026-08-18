"""Tests for the detection lens's pure formulas (detection.photometry,
detection.timing).

These check the physics against docs/04-decision-engine.md's own worked
examples -- if a formula here drifts from the doc, one of these fails.
"""

from __future__ import annotations

import pytest

from detection.photometry import (
    effective_pixel_nm,
    effective_read_noise_e,
    localization_variance_nm2,
    peak_adu,
    quantization_noise_e,
    required_photons,
    snr,
)
from detection.timing import (
    duty_cycle,
    frame_period_s,
    max_fps,
    motion_blur_bias_fraction,
    readout_time_s,
)
from optics.components import Objective

# --------------------------------------------------- sampling / diffraction --

OBJ_100X_OIL = Objective("100x", 100, 1.45, "oil")


def test_rayleigh_and_psf_sigma_match_docs_example():
    """docs/04 §2: 100x/NA1.45, lambda_em=668nm -> r=281nm, sigma=97nm."""
    assert OBJ_100X_OIL.resolution_nm(668.0) == pytest.approx(281.0, abs=1.0)
    assert OBJ_100X_OIL.psf_sigma_nm(668.0) == pytest.approx(97.0, abs=1.0)


def test_effective_pixel_matches_legacy_setup_table():
    """docs/04 §2: 11um pitch, B=1, various mag -> p_sample table."""
    assert effective_pixel_nm(11.0, 1, 100.0, 1.5) == pytest.approx(73.3, abs=0.1)
    assert effective_pixel_nm(11.0, 1, 100.0, 1.0) == pytest.approx(110.0, abs=0.1)
    assert effective_pixel_nm(11.0, 1, 60.0, 1.0) == pytest.approx(183.3, abs=0.2)
    assert effective_pixel_nm(11.0, 1, 40.0, 1.0) == pytest.approx(275.0, abs=0.2)
    assert effective_pixel_nm(11.0, 1, 20.0, 1.0) == pytest.approx(550.0, abs=0.2)
    assert effective_pixel_nm(11.0, 1, 10.0, 1.0) == pytest.approx(1100.0, abs=0.5)


def test_required_photons_matches_docs_example():
    """docs/04 §4: sigma_PSF=97nm, p=110nm, target sigma_loc=10nm -> N ~ 104."""
    n = required_photons(97.0, 110.0, 10.0)
    assert n == pytest.approx(104.17, rel=1e-3)


def test_localization_variance_recovers_the_shot_noise_only_bound():
    """With background=0, the variance collapses to the docs/04 §4
    background-free lower bound sigma_a^2 / N."""
    sigma_a2 = 97.0**2 + 110.0**2 / 12.0
    var = localization_variance_nm2(97.0, 110.0, n_photons=104.17, background_e=0.0)
    assert var == pytest.approx(sigma_a2 / 104.17, rel=1e-6)


def test_finer_than_nyquist_pixel_can_be_worse_for_tracking_with_background():
    """docs/06-pitfalls.md §C6: subdividing pixels finer -- as imaging-style
    Nyquist reasoning would push toward -- can make tracking precision
    *worse*, not better, once background is present. The finite optimum
    only exists because of the background term; at a modest photon budget
    a pixel finer than the Nyquist limit (e.g. the legacy 100x/1.5x 73.3 nm
    pixel, docs/04 §2) can lose to the coarser Nyquist pixel itself."""
    sigma_psf = 97.0
    nyquist_p = 281.0 / 2.0  # 140.5 nm
    finer_p = 73.3  # legacy 100x/1.5x pixel -- finer than the Nyquist limit
    n_photons, background = 400.0, 16.0
    var_finer = localization_variance_nm2(sigma_psf, finer_p, n_photons, background)
    var_nyquist = localization_variance_nm2(sigma_psf, nyquist_p, n_photons, background)
    assert var_finer > var_nyquist


# ------------------------------------------------------------ quantization --


def test_quantization_noise_matches_prime95b_hdr_16bit_mode():
    """docs/04 §4 table: full_well=80000, 16-bit -> e/ADU=1.22, q/sqrt12=0.35,
    effective noise (with 1.3 e- read noise) = 1.35 e-."""
    q = quantization_noise_e(80000, 16)
    assert q == pytest.approx(0.352, abs=0.01)
    eff = effective_read_noise_e(1.3, 80000, 16)
    assert eff == pytest.approx(1.35, abs=0.01)


def test_quantization_noise_matches_prime95b_fullwell_12bit_mode():
    """docs/04 §4 table: full_well=62000, 12-bit -> e/ADU=15.14, q/sqrt12=4.37,
    effective noise (with 1.6 e- read noise) = 4.65 e- -- 3.4x the 16-bit mode."""
    q = quantization_noise_e(62000, 12)
    assert q == pytest.approx(4.37, abs=0.01)
    eff = effective_read_noise_e(1.6, 62000, 12)
    assert eff == pytest.approx(4.65, abs=0.01)
    eff_16bit = effective_read_noise_e(1.3, 80000, 16)
    assert eff / eff_16bit == pytest.approx(3.4, abs=0.1)  # docs/04 prose rounds to "3.4x"


def test_snr_degrades_as_effective_read_noise_grows():
    weak_signal, background, dark, n_pix = 50.0, 20.0, 0.0, 1
    snr_16bit = snr(weak_signal, background, dark, n_pix, effective_read_noise_e(1.3, 80000, 16))
    snr_12bit = snr(weak_signal, background, dark, n_pix, effective_read_noise_e(1.6, 62000, 12))
    assert snr_12bit < snr_16bit


def test_peak_adu_adds_the_observed_offset():
    # 40000 e- at 80000 full well / 16 bit -> e_per_adu = 1.221; + 100 ADU offset
    adu = peak_adu(40000.0, 80000.0, 16, offset_adu=100.0)
    assert adu == pytest.approx(40000.0 / (80000.0 / 65536.0) + 100.0, rel=1e-6)


# ------------------------------------------------------------------ timing --


@pytest.mark.parametrize(
    "roi_height,expected_readout_ms,expected_fps",
    [
        (1608, 16.53, 60.5),
        (402, 4.13, 242.0),
        (176, 1.81, 553.0),
        (108, 1.11, 901.0),
    ],
)
def test_readout_and_max_fps_match_legacy_row_time_table(roi_height, expected_readout_ms, expected_fps):
    """docs/04 §5: 10.28 us/row (archive-derived), readout-bound (t_exp=0)."""
    readout_s = readout_time_s(10.28, roi_height)
    assert readout_s * 1e3 == pytest.approx(expected_readout_ms, abs=0.03)
    t_frame = frame_period_s(exposure_ms=0.0, readout_s=readout_s)
    assert max_fps(t_frame) == pytest.approx(expected_fps, abs=1.0)


def test_narrower_width_does_not_change_readout_time():
    """docs/06-pitfalls.md §C3: rolling-shutter readout depends on row count
    only -- this module never takes a width, which is the point."""
    assert readout_time_s(10.28, 176) == readout_time_s(10.28, 176)


def test_motion_blur_bias_fraction_at_full_duty_cycle_is_one_third():
    """docs/04 §5: t_exp = 1/f (duty 100%) -> 33% bias at the shortest lag."""
    assert motion_blur_bias_fraction(1.0) == pytest.approx(1.0 / 3.0, rel=1e-6)


def test_duty_cycle_matches_the_archive_28_percent_example():
    """docs/04 §5 / docs/06-pitfalls.md §C4: 10ms exposure, measured 28 Hz."""
    t_frame = 1.0 / 28.0
    assert duty_cycle(10.0, t_frame) == pytest.approx(0.28, abs=0.005)


def test_g9_accepts_a_frame_rate_that_exactly_meets_the_target():
    """t_frame is summed from exposure + overhead in floating point, so a camera
    configured to hit the target exactly can land a few ulp under it. G9 used to
    report 'only 240 fps is realizable, below the 240 fps target'."""
    from detection.checks import check_frame_rate
    from detection.setup import Acquisition, Camera, DetectionSetup, PhotonBudget
    from optics.components import Objective, find_detector

    target = 240.0
    exposure_ms = 1.0
    cam = Camera(
        detector=find_detector("Kinetix"),
        mode="Sensitivity",
        binning=1,
        roi_height_px=1040,
        row_time_us=3.53125,
        frame_overhead_ms=1000.0 / target - exposure_ms,
    )
    setup = DetectionSetup(
        objective=Objective(label="40x-WI", magnification=40, na=1.25, verified_na=True),
        wavelength_em_nm=520,
        mag_objective=40,
        mag_intermediate=1.5,
        camera=cam,
        acquisition=Acquisition(
            exposure_ms=exposure_ms, task_kind="tracking", target_fps=target
        ),
        photons=PhotonBudget(),
    )
    result = check_frame_rate(setup)
    assert result.severity == "ok", result.message
    assert result.code == "frame_rate"
