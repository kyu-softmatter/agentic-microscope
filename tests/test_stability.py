"""Tests for stability.drift -- the physics behind lens 8, independent of the
gate. docs/05-consensus-gate.md "Lens 8".
"""

from __future__ import annotations

import math

import pytest

from stability.drift import (
    concentration_factor,
    evaporated_fraction,
    settling_distance_um,
    stokes_settling_velocity_um_per_s,
    total_drift_nm,
)


# --------------------------------------------------------------- drift -----


def test_drift_is_rate_times_time():
    assert total_drift_nm(5.0, 60.0) == pytest.approx(300.0)


def test_zero_rate_gives_no_drift():
    assert total_drift_nm(0.0, 600.0) == 0.0


# -------------------------------------------------------- sedimentation ----


def test_polystyrene_in_water_settling_velocity():
    """a = 0.5 um, dRho = 50 kg/m^3, water: (2/9) dRho g a^2/eta."""
    v = stokes_settling_velocity_um_per_s(0.5, 50.0, 1.0e-3)
    assert v == pytest.approx(0.027241, rel=1e-4)


def test_settling_goes_as_radius_squared():
    """Doubling the radius quadruples the velocity -- the reason 'use smaller
    particles' is the strongest lever in the action text."""
    small = stokes_settling_velocity_um_per_s(0.5, 50.0, 1.0e-3)
    big = stokes_settling_velocity_um_per_s(1.0, 50.0, 1.0e-3)
    assert big == pytest.approx(4 * small)


def test_settling_is_linear_in_density_contrast():
    a = stokes_settling_velocity_um_per_s(0.5, 50.0, 1.0e-3)
    b = stokes_settling_velocity_um_per_s(0.5, 100.0, 1.0e-3)
    assert b == pytest.approx(2 * a)


def test_density_matched_suspension_does_not_settle():
    assert stokes_settling_velocity_um_per_s(0.5, 0.0, 1.0e-3) == 0.0


def test_lighter_than_medium_particles_cream_upward():
    assert stokes_settling_velocity_um_per_s(0.5, -50.0, 1.0e-3) < 0


def test_settling_is_inversely_proportional_to_viscosity():
    thin = stokes_settling_velocity_um_per_s(0.5, 50.0, 1.0e-3)
    thick = stokes_settling_velocity_um_per_s(0.5, 50.0, 2.0e-3)
    assert thick == pytest.approx(thin / 2)


def test_settling_rejects_nonpositive_viscosity():
    with pytest.raises(ValueError):
        stokes_settling_velocity_um_per_s(0.5, 50.0, 0.0)


def test_thirty_minutes_of_settling_dwarfs_any_depth_of_field():
    """49 um against a 0.375 um DOF on the 100x oil -- the number that makes
    this gate worth having."""
    v = stokes_settling_velocity_um_per_s(0.5, 50.0, 1.0e-3)
    assert settling_distance_um(v, 30.0) == pytest.approx(49.03, rel=1e-3)


# --------------------------------------------------------- evaporation -----


def test_evaporated_fraction_is_lost_volume_over_total():
    """2 uL/hour for 30 min out of 20 uL = 1 uL = 5%."""
    assert evaporated_fraction(2.0, 20.0, 30.0) == pytest.approx(0.05)


def test_evaporated_fraction_is_clamped_at_complete_loss():
    assert evaporated_fraction(100.0, 1.0, 600.0) == 1.0


def test_evaporated_fraction_rejects_zero_volume():
    with pytest.raises(ValueError):
        evaporated_fraction(2.0, 0.0, 30.0)


def test_concentration_factor_for_five_percent_loss():
    """5% of the solvent gone concentrates the solute 1.053x."""
    assert concentration_factor(0.05) == pytest.approx(1.0 / 0.95)


def test_no_evaporation_leaves_concentration_unchanged():
    assert concentration_factor(0.0) == 1.0


def test_complete_evaporation_is_unbounded():
    assert math.isinf(concentration_factor(1.0))


def test_concentration_factor_rejects_negative_fraction():
    with pytest.raises(ValueError):
        concentration_factor(-0.1)
