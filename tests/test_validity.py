"""Tests for validity.power -- statistical power, the one quantity lens 6
computes itself. docs/04-decision-engine.md §7.
"""

from __future__ import annotations

import math

import pytest

from validity.power import (
    relative_error,
    required_frames,
    required_particles,
    required_sample_product,
    roi_speed_tradeoff,
)


def test_relative_error_is_the_inverse_root_of_the_sample_product():
    """100 particles x 100 frames = 1e4 samples -> 1% error."""
    assert relative_error(100, 100) == pytest.approx(0.01)


def test_relative_error_halves_when_the_product_quadruples():
    assert relative_error(400, 100) == pytest.approx(relative_error(100, 100) / 2)


def test_particles_and_frames_enter_symmetrically():
    assert relative_error(50, 200) == pytest.approx(relative_error(200, 50))


def test_relative_error_is_infinite_for_an_empty_sample():
    assert math.isinf(relative_error(0, 1000))


def test_required_product_inverts_the_error():
    assert required_sample_product(0.01) == pytest.approx(1e4)


def test_required_product_rejects_nonpositive_target():
    with pytest.raises(ValueError):
        required_sample_product(0.0)


def test_required_particles_and_frames_are_consistent():
    target, n_f = 0.05, 2000.0
    n_p = required_particles(target, n_f)
    assert relative_error(n_p, n_f) == pytest.approx(target)
    assert required_frames(target, n_p) == pytest.approx(n_f)


def test_required_particles_rejects_zero_frames():
    with pytest.raises(ValueError):
        required_particles(0.05, 0.0)


# ---------------------------------------------------- the ROI trap ---------


def test_quartering_the_area_for_four_times_the_frame_rate_is_a_wash():
    """docs/04 §7's warning, as an equality: the net gain is exactly 1."""
    assert roi_speed_tradeoff(0.25, 4.0) == pytest.approx(1.0)


def test_roi_shrink_is_a_real_gain_only_if_frame_rate_beats_the_area_loss():
    assert roi_speed_tradeoff(0.25, 8.0) > 1.0
    assert roi_speed_tradeoff(0.25, 2.0) < 1.0


def test_a_wash_leaves_the_relative_error_unchanged():
    """Cross-check the tradeoff against the error formula itself."""
    base = relative_error(400, 1000)
    quartered_area_four_x_frames = relative_error(100, 4000)
    assert quartered_area_four_x_frames == pytest.approx(base)
