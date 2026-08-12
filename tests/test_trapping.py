"""Tests for the trapping lens (ray-optics trap-force verification).

Two different things, and the distinction matters (mirrors tests/test_optics.py):

* the **physics** is right -- symmetry, sign, power-linearity, order of magnitude
* the **refusals** are right -- geometry outside the model, sizes outside the
  ray-optics regime, and dial/calibration misuse must not silently produce a
  number
"""

from __future__ import annotations

import pytest

from trapping import Bead, Medium, ObjectiveBeam, ray_optics_regime, trap_force
from trapping.goa import radial_stiffness_n_per_m
from trapping.laser import LaserCalibration, power_per_trap

# The bead/medium/beam every GOA MATLAB script in D:\codes\Geometric_optics_approximation
# actually uses (2.5 um silica bead, water, 1064 nm, NA 1.33-1.45).
SILICA_BEAD = Bead(radius_m=2.5e-6, n=1.45)
WATER = Medium(n=1.33)
BEAM = ObjectiveBeam(na=1.33, wavelength_m=1064e-9)


# --------------------------------------------------------------- regime ---


def test_lab_bead_is_squarely_in_ray_optics_regime():
    """The exact bead size used across the MATLAB folder must not be refused."""
    regime, x = ray_optics_regime(SILICA_BEAD, BEAM, WATER)
    assert regime == "ray_optics"
    assert x > 10


def test_subwavelength_bead_is_rayleigh_not_ray_optics():
    tiny = Bead(radius_m=20e-9, n=1.45)  # 20 nm, far below 1064/1.33 nm
    regime, _ = ray_optics_regime(tiny, BEAM, WATER)
    assert regime == "rayleigh"


def test_ray_optics_refuses_outside_its_regime():
    tiny = Bead(radius_m=20e-9, n=1.45)
    with pytest.raises(ValueError, match="regime"):
        trap_force(1e-3, 0.0, tiny, WATER, BEAM)


def test_displacement_beyond_radius_is_refused():
    """The focus sitting outside the bead is outside this model's geometry."""
    with pytest.raises(ValueError, match="radius"):
        trap_force(30e-3, 3.0e-6, SILICA_BEAD, WATER, BEAM)


# -------------------------------------------------------------- physics ---


def test_centered_bead_has_zero_radial_force():
    """No preferred lateral direction when the bead sits exactly on-axis."""
    f_radial, _ = trap_force(30e-3, 0.0, SILICA_BEAD, WATER, BEAM)
    assert f_radial == pytest.approx(0.0, abs=1e-20)


def test_centered_bead_still_feels_forward_scattering_force():
    """Ashkin's classic result: even a centered bead is pushed down-beam,
    which is why the true axial equilibrium sits past the geometric focus."""
    _, f_axial = trap_force(30e-3, 0.0, SILICA_BEAD, WATER, BEAM)
    assert f_axial > 0


def test_radial_force_is_restoring():
    """A stable trap pulls a displaced bead back toward the focus."""
    f_pos, _ = trap_force(30e-3, 0.5e-6, SILICA_BEAD, WATER, BEAM)
    f_neg, _ = trap_force(30e-3, -0.5e-6, SILICA_BEAD, WATER, BEAM)
    assert f_pos < 0  # opposes +x displacement
    assert f_neg > 0  # opposes -x displacement
    assert f_pos == pytest.approx(-f_neg, rel=1e-9)  # odd in displacement


def test_force_scales_linearly_with_power():
    """Intensity is linear in P and the Q-factors don't depend on P."""
    f1, _ = trap_force(10e-3, 0.5e-6, SILICA_BEAD, WATER, BEAM)
    f2, _ = trap_force(20e-3, 0.5e-6, SILICA_BEAD, WATER, BEAM)
    assert f2 == pytest.approx(2 * f1, rel=1e-9)


def test_zero_power_gives_zero_force():
    f_radial, f_axial = trap_force(0.0, 0.5e-6, SILICA_BEAD, WATER, BEAM)
    assert f_radial == 0.0
    assert f_axial == 0.0


def test_radial_stiffness_is_positive_for_a_stable_trap():
    kappa = radial_stiffness_n_per_m(30e-3, SILICA_BEAD, WATER, BEAM)
    assert kappa > 0


def test_stiffness_scales_linearly_with_power():
    k1 = radial_stiffness_n_per_m(10e-3, SILICA_BEAD, WATER, BEAM)
    k2 = radial_stiffness_n_per_m(30e-3, SILICA_BEAD, WATER, BEAM)
    assert k2 == pytest.approx(3 * k1, rel=1e-6)


# -------------------------------------------------------- laser + split ---


def test_placeholder_calibration_is_not_measured():
    """Compute-never-infer: an uncalibrated dial must say so."""
    cal = LaserCalibration(placeholder_max_w=1.0)
    assert cal.measured is False
    assert cal.power_at(100) == pytest.approx(1.0)
    assert cal.power_at(0) == 0.0


def test_measured_calibration_interpolates_between_points():
    cal = LaserCalibration(points={0: 0.0, 50: 0.42, 100: 1.05})
    assert cal.measured is True
    assert cal.power_at(50) == pytest.approx(0.42)
    assert cal.power_at(25) == pytest.approx(0.21)  # midpoint, linear


def test_calibration_refuses_dial_outside_0_100():
    cal = LaserCalibration(placeholder_max_w=1.0)
    with pytest.raises(ValueError):
        cal.power_at(101)
    with pytest.raises(ValueError):
        cal.power_at(-1)


def test_calibration_refuses_to_extrapolate_past_measured_points():
    """A dial% above the highest calibrated point must not be guessed."""
    cal = LaserCalibration(points={0: 0.0, 50: 0.42, 80: 0.68})
    with pytest.raises(ValueError, match="extrapolat"):
        cal.power_at(95)


def test_splitting_into_n_traps_divides_power_equally_by_default():
    cal = LaserCalibration(placeholder_max_w=1.2)
    powers = power_per_trap(cal, dial_percent=100, n_traps=4)
    assert powers == pytest.approx([0.3, 0.3, 0.3, 0.3])
    assert sum(powers) == pytest.approx(1.2)


def test_single_trap_gets_full_dial_power():
    cal = LaserCalibration(placeholder_max_w=1.2)
    assert power_per_trap(cal, dial_percent=100, n_traps=1) == pytest.approx([1.2])


def test_split_efficiency_weights_need_not_be_uniform():
    cal = LaserCalibration(placeholder_max_w=1.0)
    powers = power_per_trap(cal, dial_percent=100, n_traps=3, weights=[0.5, 0.3, 0.1])
    assert powers == pytest.approx([0.5, 0.3, 0.1])


def test_more_traps_means_less_force_per_trap_at_the_same_dial_setting():
    """The point of the exercise: splitting into more traps is not free --
    each trap's restoring force (and stiffness) drops with its own power."""
    cal = LaserCalibration(placeholder_max_w=30e-3)
    p_one_trap = power_per_trap(cal, dial_percent=100, n_traps=1)[0]
    p_three_traps = power_per_trap(cal, dial_percent=100, n_traps=3)[0]

    f_one, _ = trap_force(p_one_trap, 0.5e-6, SILICA_BEAD, WATER, BEAM)
    f_three, _ = trap_force(p_three_traps, 0.5e-6, SILICA_BEAD, WATER, BEAM)

    assert p_three_traps == pytest.approx(p_one_trap / 3)
    assert abs(f_three) == pytest.approx(abs(f_one) / 3, rel=1e-9)
