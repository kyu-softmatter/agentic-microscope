"""Tests for sample.aberration -- the physics behind lens 4, independent of
the gate. Numbers here are cross-checked against
kb/expertise/sample-medium-refractive-index.md.
"""

from __future__ import annotations

import math

import pytest

from sample.aberration import (
    COVERSLIP_DESIGN_UM,
    collection_half_angle_deg,
    free_working_distance_um,
    max_na,
    mean_nearest_neighbour_um,
    paraxial_focal_shift_ratio,
    particles_in_field,
    ri_mismatch,
)

N_WATER = 1.333
N_OIL = 1.518


# ------------------------------------------------------------ mismatch -----


def test_oil_into_water_mismatch_is_the_recorded_value():
    assert ri_mismatch(N_WATER, N_OIL) == pytest.approx(0.185, abs=1e-9)


def test_water_immersion_into_aqueous_medium_is_matched():
    assert ri_mismatch(N_WATER, N_WATER) == 0.0


def test_mismatch_is_symmetric():
    assert ri_mismatch(N_WATER, N_OIL) == ri_mismatch(N_OIL, N_WATER)


# --------------------------------------------------------- focal shift -----


def test_paraxial_focal_shift_for_oil_into_water():
    """0.878: a nominal 10 um of z is ~8.78 um of real depth."""
    assert paraxial_focal_shift_ratio(N_WATER, N_OIL) == pytest.approx(0.8781, abs=1e-4)


def test_matched_media_have_no_focal_shift():
    assert paraxial_focal_shift_ratio(N_WATER, N_WATER) == pytest.approx(1.0)


def test_focal_shift_rejects_nonpositive_immersion_index():
    with pytest.raises(ValueError):
        paraxial_focal_shift_ratio(N_WATER, 0.0)


# ------------------------------------------------------ NA feasibility -----


def test_max_na_is_the_immersion_index():
    assert max_na(N_OIL) == N_OIL


def test_half_angle_is_none_when_na_exceeds_the_immersion_index():
    """The 40x WI's NA 1.25 is unreachable dry. None, not a clamped number --
    optics.components.Objective.collection_efficiency clamps instead."""
    assert collection_half_angle_deg(1.25, 1.0) is None


def test_half_angle_for_the_100x_oil():
    theta = collection_half_angle_deg(1.45, N_OIL)
    assert theta == pytest.approx(math.degrees(math.asin(1.45 / N_OIL)), abs=1e-9)
    assert 72.0 < theta < 73.5


def test_half_angle_is_90_deg_at_the_ceiling():
    assert collection_half_angle_deg(N_OIL, N_OIL) == pytest.approx(90.0)


# --------------------------------------------------- working distance ------


def test_design_thickness_coverslip_does_not_consume_working_distance():
    """Vendor WD is quoted past the design coverslip: the 100x Oil's 130 um WD
    against a 170 um coverslip only makes sense on that reading."""
    assert free_working_distance_um(130.0, COVERSLIP_DESIGN_UM) == 130.0


def test_only_coverslip_excess_over_design_is_subtracted():
    assert free_working_distance_um(130.0, 190.0, 170.0) == pytest.approx(110.0)


def test_thinner_than_design_coverslip_does_not_add_working_distance():
    assert free_working_distance_um(130.0, 150.0, 170.0) == 130.0


# ------------------------------------------------------ count in field -----


def test_particle_count_in_a_known_volume():
    """1e9 /mL in 100x100x10 um = 1e5 um^3 -> 100 particles."""
    assert particles_in_field(1e9, 100.0, 100.0, 10.0) == pytest.approx(100.0)


def test_particle_count_scales_with_concentration():
    a = particles_in_field(1e8, 100.0, 100.0, 10.0)
    b = particles_in_field(2e8, 100.0, 100.0, 10.0)
    assert b == pytest.approx(2 * a)


def test_nearest_neighbour_shrinks_as_concentration_rises():
    assert mean_nearest_neighbour_um(1e10) < mean_nearest_neighbour_um(1e8)


def test_nearest_neighbour_follows_the_inverse_cube_root():
    """0.554 n^(-1/3): an 8x denser suspension halves the spacing."""
    assert mean_nearest_neighbour_um(8e9) == pytest.approx(
        mean_nearest_neighbour_um(1e9) / 2.0, rel=1e-9
    )


def test_nearest_neighbour_is_none_for_an_empty_suspension():
    assert mean_nearest_neighbour_um(0.0) is None
