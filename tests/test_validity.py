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


# ------------------------------------ an empty ledger is not a clean one --


def _ledger(**kwargs):
    from validity.checks import check_bias_ledger
    from validity.setup import ValiditySetup

    return check_bias_ledger(ValiditySetup(**kwargs))


def test_an_empty_bias_ledger_says_it_is_empty():
    """Lens 6 reported this about its own gate on 2026-09-15: "bias_findings:
    0, applicable: 0, uncorrected_codes: [] -- because the four lenses that
    emit bias-kind findings BLOCKED before Phase 1 and produced none. Anyone
    reading `margins` without `metrics` on this verdict reads the opposite of
    the truth."

    On that run lens 4 had already identified an UNCORRECTABLE near-wall drag
    on the intended quantity, in prose, while this gate reported full headroom.
    """
    from optics.gate import Verdict as OpticsVerdict

    result = _ledger(
        intended_quantity="msd",
        upstream={
            "optics": OpticsVerdict(status="PASS"),
            "sample": OpticsVerdict(status="BLOCKED"),
            "photo": OpticsVerdict(status="BLOCKED"),
        },
    )

    #: `info`, NOT `ok` -- every gate drops `ok` from findings, which is how
    #: this vanished. The same correction the neighbouring `not applicable`
    #: branch received on 2026-09-11, for the same reason.
    assert result.severity == "info"
    assert "EMPTY rather than clean" in result.message
    assert "nothing was weighed" in result.message

    #: TWO reasons a lens reports no bias, and both belong here: it BLOCKED
    #: (sample, photo) or it is a standing lens that never reported at all
    #: (detection, compute -- absent from `upstream`). The second is the
    #: quieter of the two and is why `missing_standing_lenses` is included.
    because = result.numbers["ledger_empty_because"]
    assert {"sample", "photo"} <= set(because), "blocked"
    assert {"detection", "compute"} <= set(because), "never reported"
    assert "optics" not in because, "it returned a verdict and no bias"


def test_a_genuinely_clean_ledger_still_passes_quietly():
    """The distinction has to cut both ways or it is just a louder gate. Where
    every standing lens returned a verdict and none reported a bias, silence
    IS the finding about the proposal."""
    from optics.gate import Verdict as OpticsVerdict

    result = _ledger(
        intended_quantity="msd",
        upstream={
            name: OpticsVerdict(status="PASS")
            for name in ("optics", "detection", "compute", "sample", "validity")
        },
    )

    assert result.severity == "ok"
    assert result.numbers["ledger_empty_because"] == []
    assert "every standing lens returned a verdict" in result.message


def test_the_metrics_shape_does_not_depend_on_the_branch():
    """`ledger_empty_because` is present in every branch, as the comment above
    `numbers` requires -- a key that appears only on one path is a key a
    reader cannot rely on."""
    from optics.gate import Finding as OpticsFinding
    from optics.gate import Verdict as OpticsVerdict

    biased = {"sample": OpticsVerdict(
        status="PASS_WITH_CHANGES",
        findings=[OpticsFinding("warn", "geometry.ri_mismatch", "m", kind="bias")],
    )}
    for upstream in (biased, {}):
        numbers = _ledger(intended_quantity="msd", upstream=upstream).numbers
        assert "ledger_empty_because" in numbers
