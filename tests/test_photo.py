"""Tests for photo.dose -- the physics behind lens 5, independent of the gate.
docs/04-decision-engine.md §5-§6.
"""

from __future__ import annotations


import pytest

from photo.dose import (
    duty_cycle,
    irradiance_w_cm2,
    photon_flux_per_cm2_s,
    total_dose_j_cm2,
    total_illuminated_time_s,
)


# ---------------------------------------------------------- irradiance -----


def test_irradiance_is_power_over_area():
    """1 mW over 1e4 um^2 = 1e-3 W / 1e-4 cm^2 = 10 W/cm^2."""
    assert irradiance_w_cm2(1.0, 1e4) == pytest.approx(10.0)


def test_irradiance_scales_inversely_with_area():
    assert irradiance_w_cm2(1.0, 2e4) == pytest.approx(irradiance_w_cm2(1.0, 1e4) / 2)


def test_irradiance_rejects_zero_area():
    with pytest.raises(ValueError):
        irradiance_w_cm2(1.0, 0.0)


# --------------------------------------------------------- photon flux -----


def test_photon_flux_matches_the_photon_energy():
    """phi = I / (hc/lambda). At 488 nm a photon is ~4.07e-19 J."""
    e_photon = 6.62607015e-34 * 2.99792458e8 / 488e-9
    assert photon_flux_per_cm2_s(10.0, 488.0) == pytest.approx(10.0 / e_photon)


def test_longer_wavelength_gives_more_photons_at_equal_power():
    assert photon_flux_per_cm2_s(10.0, 647.0) > photon_flux_per_cm2_s(10.0, 405.0)


def test_photon_flux_rejects_zero_wavelength():
    with pytest.raises(ValueError):
        photon_flux_per_cm2_s(10.0, 0.0)


# ------------------------------------------------------ exposure plan ------


def test_only_exposure_counts_toward_illuminated_time():
    """50 ms x 1000 frames = 50 s under light, regardless of frame spacing."""
    assert total_illuminated_time_s(50.0, 1000) == pytest.approx(50.0)


def test_duty_cycle_is_exposure_over_interval():
    assert duty_cycle(50.0, 200.0) == pytest.approx(0.25)


def test_duty_cycle_cannot_exceed_one():
    assert duty_cycle(300.0, 200.0) == 1.0


def test_duty_cycle_is_none_without_an_interval():
    assert duty_cycle(50.0, None) is None


def test_total_dose_is_irradiance_times_illuminated_time():
    assert total_dose_j_cm2(10.0, 50.0, 1000) == pytest.approx(500.0)


def test_total_dose_scales_with_frame_count():
    assert total_dose_j_cm2(10.0, 50.0, 2000) == pytest.approx(
        2 * total_dose_j_cm2(10.0, 50.0, 1000)
    )
