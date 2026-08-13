"""Tests for photo.dose -- the physics behind lens 5, independent of the gate.
docs/04-decision-engine.md §5-§6.
"""

from __future__ import annotations

import math

import pytest

from photo.dose import (
    bleached_fraction,
    duty_cycle,
    emitted_photons_per_molecule,
    excited_state_fraction,
    irradiance_w_cm2,
    photon_flux_per_cm2_s,
    saturation_irradiance_w_cm2,
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


# -------------------------------------------------------- bleaching --------


def test_emitted_photons_is_rate_times_illuminated_time():
    assert emitted_photons_per_molecule(1e3, 50.0, 1000) == pytest.approx(5e4)


def test_bleached_fraction_follows_the_exponential():
    """N_emitted == N_bleach leaves 1/e unbleached."""
    assert bleached_fraction(1e4, 1e4) == pytest.approx(1 - math.exp(-1))


def test_bleaching_is_negligible_far_below_the_budget():
    assert bleached_fraction(1e2, 1e6) < 0.001


def test_bleaching_saturates_toward_one():
    assert bleached_fraction(1e8, 1e4) == pytest.approx(1.0)


def test_bleached_fraction_rejects_nonpositive_budget():
    with pytest.raises(ValueError):
        bleached_fraction(1e4, 0.0)


# ------------------------------------------------------- saturation --------


def test_excited_state_fraction_is_half_when_k_tau_is_one():
    """k_ex = 1/tau parks half the population in the excited state."""
    tau_ns = 4.1
    k_ex = 1.0 / (tau_ns * 1e-9)
    assert excited_state_fraction(k_ex, tau_ns) == pytest.approx(0.5)


def test_excited_state_fraction_is_small_at_low_power():
    assert excited_state_fraction(1e6, 4.1) < 0.01


def test_excited_state_fraction_approaches_one_at_high_power():
    assert excited_state_fraction(1e12, 4.1) > 0.99


def test_excited_state_fraction_rejects_nonpositive_lifetime():
    with pytest.raises(ValueError):
        excited_state_fraction(1e6, 0.0)


def test_saturation_irradiance_reproduces_k_tau_equals_one():
    """Feeding the returned irradiance back through the chain must give an
    excited-state fraction of 0.5."""
    eps, tau_ns, lam = 75000.0, 4.1, 488.0
    i_sat = saturation_irradiance_w_cm2(eps, tau_ns, lam)
    k_ex = 3.82e-21 * eps * photon_flux_per_cm2_s(i_sat, lam)
    assert excited_state_fraction(k_ex, tau_ns) == pytest.approx(0.5, rel=1e-6)


def test_brighter_dyes_saturate_at_lower_irradiance():
    assert saturation_irradiance_w_cm2(150000.0, 4.1, 488.0) < saturation_irradiance_w_cm2(
        75000.0, 4.1, 488.0
    )


# ------------------------------------------------------- total dose --------


def test_total_dose_is_irradiance_times_illuminated_time():
    assert total_dose_j_cm2(10.0, 50.0, 1000) == pytest.approx(500.0)


def test_total_dose_scales_with_frame_count():
    assert total_dose_j_cm2(10.0, 50.0, 2000) == pytest.approx(
        2 * total_dose_j_cm2(10.0, 50.0, 1000)
    )
