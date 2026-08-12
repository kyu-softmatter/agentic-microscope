"""Tests for trapping.dynamics: water viscosity lookup, corner frequency,
and trap depth (U/kT)."""

from __future__ import annotations

import pytest

from trapping.dynamics import (
    TrapSetup,
    corner_frequency_hz,
    trap_depth_kt,
    water_viscosity_pa_s,
)
from trapping.goa import Bead, Medium, ObjectiveBeam
from trapping.laser import LaserCalibration

SILICA_BEAD = Bead(radius_m=2.5e-6, n=1.45)
BEAM = ObjectiveBeam(na=1.33, wavelength_m=1064e-9)


# ------------------------------------------------------------ viscosity ---


def test_water_viscosity_at_20c_matches_the_crc_table():
    assert water_viscosity_pa_s(20.0) == pytest.approx(1.0016e-3, rel=1e-6)


def test_water_viscosity_default_is_20c():
    assert water_viscosity_pa_s() == water_viscosity_pa_s(20.0)


def test_water_viscosity_decreases_with_temperature():
    assert water_viscosity_pa_s(30.0) < water_viscosity_pa_s(10.0)


def test_water_viscosity_refuses_to_extrapolate():
    with pytest.raises(ValueError, match="tabulated"):
        water_viscosity_pa_s(100.0)


# ------------------------------------------------------- corner frequency ---


def test_corner_frequency_matches_hand_worked_numbers():
    """kappa=2*pi N/m, eta=1/(6*pi) Pa*s, r=1 m -> gamma=1 -> f_c=1 Hz exactly."""
    import math

    f_c = corner_frequency_hz(2 * math.pi, 1 / (6 * math.pi), 1.0)
    assert f_c == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize("bad_kappa,bad_eta,bad_r", [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0)])
def test_corner_frequency_refuses_non_positive_inputs(bad_kappa, bad_eta, bad_r):
    with pytest.raises(ValueError):
        corner_frequency_hz(bad_kappa, bad_eta, bad_r)


# ------------------------------------------------------------ trap depth ---


def test_trap_depth_is_zero_at_zero_power():
    water = Medium(n=1.33)
    u_kt = trap_depth_kt(0.0, SILICA_BEAD, water, BEAM, temperature_k=293.15)
    assert u_kt == pytest.approx(0.0, abs=1e-9)


def test_trap_depth_is_positive_for_a_stable_trap():
    """The restoring force does positive work when moving the bead outward,
    i.e. this is a real potential well, not a downhill slope."""
    water = Medium(n=1.33)
    u_kt = trap_depth_kt(10e-3, SILICA_BEAD, water, BEAM, temperature_k=293.15)
    assert u_kt > 0


def test_trap_depth_scales_linearly_with_power():
    """Force is linear in power (see test_trapping.py); the potential -- an
    integral of force -- inherits that linearity."""
    water = Medium(n=1.33)
    u1 = trap_depth_kt(5e-3, SILICA_BEAD, water, BEAM, temperature_k=293.15)
    u2 = trap_depth_kt(15e-3, SILICA_BEAD, water, BEAM, temperature_k=293.15)
    assert u2 == pytest.approx(3 * u1, rel=1e-6)


def test_trap_depth_refuses_non_positive_temperature():
    water = Medium(n=1.33)
    with pytest.raises(ValueError, match="temperature"):
        trap_depth_kt(10e-3, SILICA_BEAD, water, BEAM, temperature_k=0.0)


# -------------------------------------------------------------- TrapSetup ---


def test_trap_setup_defaults_to_20c_and_unmeasured_temperature():
    setup = TrapSetup(
        bead=SILICA_BEAD,
        medium=Medium(n=1.33),
        beam=BEAM,
        calibration=LaserCalibration(placeholder_max_w=1.0),
        dial_percent=50,
    )
    assert setup.temperature_k == pytest.approx(293.15)
    assert setup.temperature_measured is False


def test_weakest_power_w_picks_the_smallest_weighted_trap():
    setup = TrapSetup(
        bead=SILICA_BEAD,
        medium=Medium(n=1.33),
        beam=BEAM,
        calibration=LaserCalibration(placeholder_max_w=1.0),
        dial_percent=100,
        n_traps=2,
        weights=[0.8, 0.2],
    )
    powers = setup.powers_w()
    assert setup.weakest_power_w() == pytest.approx(min(powers))
    assert setup.weakest_power_w() == pytest.approx(0.2)
