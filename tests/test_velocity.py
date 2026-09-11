"""Tests for `velocity/kinematics.py` -- lens 9's pure functions.

The theme of this file is that **nothing here is a chosen constant**. Each
bound is derived either from the caller's precision target or from a limit the
trap model states about itself, so the tests check the derivation rather than a
remembered number.
"""

from __future__ import annotations

import math

import pytest

from velocity.kinematics import (
    drag_coefficient_pn_s_per_um,
    equilibrium_offset_um,
    minimum_offset_um,
    reynolds_number,
    reynolds_unity_velocity_um_per_s,
    settling_time_constants,
    velocity_for_offset_um_per_s,
)


def test_stokes_drag_for_the_bead_this_bench_uses():
    """5 um polystyrene in water: 6*pi*eta*a with a = 2.5 um."""
    g = drag_coefficient_pn_s_per_um(2.5, 1.0e-3)
    assert g == pytest.approx(0.04712, rel=1e-3)


def test_drag_is_linear_in_radius_and_viscosity():
    base = drag_coefficient_pn_s_per_um(2.5, 1.0e-3)
    assert drag_coefficient_pn_s_per_um(5.0, 1.0e-3) == pytest.approx(2 * base)
    assert drag_coefficient_pn_s_per_um(2.5, 2.0e-3) == pytest.approx(2 * base)


def test_drag_rejects_nonpositive_inputs():
    for a, eta in ((0.0, 1e-3), (2.5, 0.0), (-1.0, 1e-3)):
        with pytest.raises(ValueError):
            drag_coefficient_pn_s_per_um(a, eta)


def test_offset_and_velocity_are_inverses():
    g, k = 0.04712, 3.87
    x = equilibrium_offset_um(20.0, g, k)
    assert velocity_for_offset_um_per_s(x, g, k) == pytest.approx(20.0)


def test_offset_per_unit_velocity_is_gamma_over_kappa():
    """12.18 nm per um/s for this bead at the measured kappa -- the number the
    whole velocity window turns on."""
    g, k = drag_coefficient_pn_s_per_um(2.5, 1.0e-3), 3.87
    assert equilibrium_offset_um(1.0, g, k) * 1000 == pytest.approx(12.18, rel=1e-3)


def test_the_offset_floor_is_derived_from_the_precision_target():
    """`dkappa/kappa = dx/x_eq`, so the offset has to beat the localization
    noise by exactly 1/target. **No multiple was chosen.**"""
    assert minimum_offset_um(10.0, 0.05) * 1000 == pytest.approx(200.0)
    assert minimum_offset_um(10.0, 0.02) * 1000 == pytest.approx(500.0)
    # Halving the target doubles the required offset, which is the whole claim.
    assert minimum_offset_um(10.0, 0.025) == pytest.approx(
        2 * minimum_offset_um(10.0, 0.05)
    )


def test_the_offset_floor_scales_with_the_localization_noise():
    assert minimum_offset_um(20.0, 0.05) == pytest.approx(
        2 * minimum_offset_um(10.0, 0.05)
    )


def test_the_offset_floor_rejects_an_impossible_target():
    for bad in (0.0, 1.0, 1.5, -0.1):
        with pytest.raises(ValueError):
            minimum_offset_um(10.0, bad)


def test_settling_time_is_derived_from_the_same_target():
    """The approach is exponential, so the residual after n tau is e^-n and
    `n = ln(1/target)`. **No "about five time constants" anywhere.**"""
    assert settling_time_constants(0.05) == pytest.approx(3.0, rel=1e-2)
    assert settling_time_constants(0.02) == pytest.approx(3.91, rel=1e-2)
    for target in (0.1, 0.05, 0.01):
        assert math.exp(-settling_time_constants(target)) == pytest.approx(target)


def test_reynolds_is_hopeless_to_violate_on_this_instrument():
    """The argument that makes L9.4 a report rather than a gate: Re = 1 needs
    about 4e5 um/s for a 2.5 um bead in water, four orders above anything the
    piezo or the AOD produces."""
    assert reynolds_number(20.0, 2.5, 1.0e-3) == pytest.approx(5.0e-5, rel=1e-2)
    v1 = reynolds_unity_velocity_um_per_s(2.5, 1.0e-3)
    assert v1 == pytest.approx(4.0e5, rel=1e-2)
    assert reynolds_number(v1, 2.5, 1.0e-3) == pytest.approx(1.0, rel=1e-6)


def test_reynolds_would_bind_for_a_larger_particle_in_a_thinner_medium():
    """Reported rather than assumed away, so a different sample shows up.

    Note the direction, which is easy to get backwards: `v(Re=1) = eta/(rho a)`,
    so a BIGGER particle lowers the threshold and a thinner medium lowers it
    too. A smaller bead raises it.
    """
    base = reynolds_unity_velocity_um_per_s(2.5, 1.0e-3)
    assert reynolds_unity_velocity_um_per_s(25.0, 1.0e-4) < base
    assert reynolds_unity_velocity_um_per_s(0.05, 1.0e-3) > base
