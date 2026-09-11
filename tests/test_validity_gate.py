"""Tests for validity.gate.evaluate (lens 6).

This lens reviews other lenses' verdicts, so the tests build real verdicts from
the real lenses where that is cheap, and structural stand-ins where it is not.
"""

from __future__ import annotations

import pytest

from validity.gate import evaluate
from validity.setup import STANDING_LENSES, ValiditySetup


class _V:
    """Structural VerdictLike stand-in for an upstream lens."""

    def __init__(self, status="PASS", evidence="measured", findings=(), metrics=None):
        self.status = status
        self.evidence = evidence
        self.margins = {}
        self.findings = list(findings)
        self.metrics = metrics or {}


class _F:
    """Structural FindingLike stand-in."""

    def __init__(self, code, lens, kind="bias", severity="warn", margin=0.5):
        self.code = code
        self.lens = lens
        self.kind = kind
        self.severity = severity
        self.margin = margin
        self.message = f"{code} from {lens}"


def _all_present(**overrides):
    up = {name: _V() for name in STANDING_LENSES}
    up.update(overrides)
    return up


def _setup(**overrides) -> ValiditySetup:
    defaults = dict(
        intended_quantity="diffusion",
        upstream=_all_present(),
        pixel_size_measured=True,
        analysis_script="D:/codes/track_msd.m",
    )
    defaults.update(overrides)
    return ValiditySetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_any_upstream_verdict():
    """The lens has to run last; with nothing to review it refuses."""
    v = evaluate(_setup(upstream={}))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.upstream_verdicts" for f in v.findings)


def test_blocked_without_an_intended_quantity():
    v = evaluate(_setup(intended_quantity=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.intended_quantity" for f in v.findings)


def test_blocked_for_an_unknown_quantity():
    """Guessing which calibrations matter would mean certifying validity
    against the wrong criteria."""
    v = evaluate(_setup(intended_quantity="vibes"))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.quantity_requirements" for f in v.findings)


def test_phase_0_blocks_on_two_things_and_no_longer_on_four():
    """`missing.target_error` and `missing.sample_size` left with G11 on
    2026-09-11. They were half of this lens's Phase 0, and neither survived the
    gate they served -- refusing to review the committee because nobody stated
    a target relative error meant a session with every calibration in hand
    still came back BLOCKED. What blocks now is what this lens genuinely cannot
    work without: something to review, and a statement of what is measured."""
    from validity.gate import _missing_inputs

    assert [f.code for f in _missing_inputs(ValiditySetup())] == [
        "missing.upstream_verdicts",
        "missing.intended_quantity",
    ]


def test_the_setup_no_longer_accepts_the_g11_inputs():
    for field in ("target_relative_error", "n_particles", "n_frames"):
        with pytest.raises(TypeError):
            _setup(**{field: 1.0})


# ------------------------------------------- G27 committee coverage ------


def test_missing_standing_lens_fails():
    """Nothing else in the codebase notices that a lens never ran -- there is
    no orchestrator, so each lens is invoked separately."""
    up = _all_present()
    del up["sample"]
    v = evaluate(_setup(upstream=up))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["missing_standing"] == ["sample"]


def test_photo_is_no_longer_a_standing_lens():
    """It became a reporting section on 2026-09-10, so it has no verdict to
    return and G27 must not demand one -- doing so would BLOCK every review
    forever. Its absence is not a hole in the sense E4 means; it is not a
    lens."""
    from validity.setup import STANDING_LENSES

    assert "photo" not in STANDING_LENSES
    up = _all_present()
    up.pop("photo", None)
    v = evaluate(_setup(upstream=up))
    assert v.metrics["validity.committee_coverage"]["missing_standing"] == []


def test_blocked_upstream_lens_fails_coverage():
    """BLOCKED means 'no basis to decide'; validity cannot sit on top of that."""
    v = evaluate(_setup(upstream=_all_present(photo=_V(status="BLOCKED"))))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["blocked"] == ["photo"]


def test_failed_upstream_lens_fails_coverage():
    v = evaluate(_setup(upstream=_all_present(optics=_V(status="FAIL"))))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["failed"] == ["optics"]


def test_full_committee_passes_coverage():
    v = evaluate(_setup())
    assert v.margins["validity.committee_coverage"] == 10.0


def test_extra_conditional_lens_is_allowed():
    v = evaluate(_setup(upstream=_all_present(trapping=_V())))
    assert v.margins["validity.committee_coverage"] == 10.0


# ------------------------------------------------- G23 bias ledger ------


def test_no_upstream_bias_findings_passes():
    v = evaluate(_setup())
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


def test_uncorrected_upstream_bias_fails():
    up = _all_present(sample=_V(findings=[_F("geometry.ri_mismatch", "sample")]))
    v = evaluate(_setup(upstream=up))
    assert v.status == "FAIL"
    assert "geometry.ri_mismatch" in v.metrics["validity.bias_ledger"]["uncorrected_codes"]


def test_declaring_the_correction_clears_the_bias():
    """Only for a bias a correction actually exists for -- motion blur has
    Savin-Doyle, so declaring it is a claim that can be true."""
    up = _all_present(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(
        _setup(upstream=up, corrections_applied=frozenset({"motion_blur.biased"}))
    )
    assert v.metrics["validity.bias_ledger"]["uncorrected"] == 0
    assert v.status != "FAIL"


def test_bias_ledger_margin_is_the_worst_uncorrected_upstream_margin():
    """The committee's worst unhandled problem stays visible instead of being
    averaged away."""
    up = _all_present(
        sample=_V(findings=[_F("geometry.ri_mismatch", "sample", margin=0.33)]),
        photo=_V(findings=[_F("perturbation.photobleaching", "photo", margin=0.8)]),
    )
    v = evaluate(_setup(upstream=up))
    assert v.margins["validity.bias_ledger"] == pytest.approx(0.33)


def test_only_bias_kind_findings_enter_the_ledger():
    """A hard failure is the owning lens's business; this ledger is for biases."""
    up = _all_present(
        detection=_V(findings=[_F("timing.frame_rate", "detection", kind="hard", severity="fail")])
    )
    v = evaluate(_setup(upstream=up))
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


def test_ok_severity_bias_findings_are_not_counted():
    up = _all_present(
        sample=_V(findings=[_F("geometry.coverslip", "sample", severity="info")])
    )
    v = evaluate(_setup(upstream=up))
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


# --------------------------------------------- G24 pixel calibration ----


def test_geometric_quantity_without_measured_pixel_size_fails():
    """docs/06 A1: every distance would be wrong by an unknown constant, and
    the numbers would still look reasonable."""
    v = evaluate(_setup(pixel_size_measured=False))
    assert v.status == "FAIL"
    assert v.bottleneck == "validity.pixel_calibration"


def test_intensity_quantity_does_not_need_pixel_size():
    v = evaluate(
        _setup(
            intended_quantity="stoichiometry",
            pixel_size_measured=False,
            background_measured=True,
            dark_current_measured=True,
            flat_field_measured=True,
        )
    )
    assert v.margins["validity.pixel_calibration"] == 10.0


# --------------------------------------- G25 photometric calibration ----


def test_intensity_quantity_needs_photometric_calibration():
    v = evaluate(_setup(intended_quantity="concentration"))
    assert any(
        f.code == "validity.photometric_calibration" and f.severity == "warn"
        for f in v.findings
    )


def test_geometric_quantity_does_not_need_photometric_calibration():
    v = evaluate(_setup())
    assert v.margins["validity.photometric_calibration"] == 10.0


def test_photometric_margin_reflects_how_many_calibrations_are_missing():
    partial = evaluate(
        _setup(
            intended_quantity="concentration",
            background_measured=True,
            dark_current_measured=True,
        )
    )
    none = evaluate(_setup(intended_quantity="concentration"))
    assert (
        partial.margins["validity.photometric_calibration"]
        > none.margins["validity.photometric_calibration"]
    )


# ---------------- G26 removed 2026-09-11 -------------------------------------
#
# Four tests went with the check. It gated on the self-declared
# `despeckle_enabled` boolean -- which nobody verifies -- while
# `detection/recommend.py` already refuses a reference frame shot with
# despeckle on, and puts it more sharply: "despeckle on -> the ADU->electron
# conversion is invalid, full stop". That refusal lands at the point where
# despeckle destroys something computable, namely deriving a photon budget from
# the frame. A committee-level hard gate on an unverified boolean added no
# information and could not see the camera.
#
# docs/06 C1 is unchanged as a pitfall. What changed is which code owns it.
# kb/decisions/2026-09-11-g11-and-g26-removed.md


def test_nothing_in_this_lens_gates_post_processing_any_more():
    v = evaluate(_setup())
    assert "validity.post_processing" not in v.margins
    assert not any(f.code == "validity.post_processing" for f in v.findings)


def test_the_setup_no_longer_accepts_a_despeckle_flag():
    for field in ("despeckle_enabled", "nonlinear_filters"):
        with pytest.raises(TypeError):
            _setup(**{field: True})


def test_linearity_survives_in_the_quantity_table_with_no_reader():
    """Removing the check did not remove the requirement, on purpose:
    `BIAS_SCOPE` intersects against "linearity" to scope a photobleaching bias
    to the photometric quantities. It is no longer a check, and the table says
    so."""
    from validity.setup import BIAS_SCOPE, calibrations_for

    assert "linearity" in calibrations_for("intensity")
    assert "linearity" in BIAS_SCOPE["perturbation.photobleaching"]


# ---------------- G11 removed 2026-09-11 -------------------------------------
#
# Five tests went with the check, and so did this lens's only computation.
# `1/sqrt(N_p x N_f)` counts INDEPENDENT samples, which `validity/power.py`
# states in its own docstring, and a single trapped bead is the worse case
# because consecutive FRAMES are correlated: at 520 fps with
# tau = gamma/kappa = 12.1 ms there are 6.3 frames per relaxation time, so a
# 60 s movie of one bead is ~2,500 independent samples and not 31,200. The gate
# reported 0.566% where ~2.0% is defensible -- 3.5x optimistic, a margin of 78x
# where ~6x is real -- and the precision of a Stokes-drag calibration comes
# from the number of velocity steps, which is not N_p x N_f at all.
#
# The arithmetic is not wrong and survives in `validity/power.py` and
# `python -m validity.cli power`, which is where a floor belongs: something you
# consult, not something that certifies. tests/test_validity.py still covers it.
# kb/decisions/2026-09-11-g11-and-g26-removed.md


def test_nothing_in_this_lens_computes_a_sample_size_any_more():
    v = evaluate(_setup())
    assert "validity.statistical_power" not in v.margins
    assert not any("statistical_power" in f.code for f in v.findings)


def test_this_lens_computes_nothing_at_all():
    """Every remaining check reads another lens's verdict or a declaration.
    That is why `LIMITS` is empty -- there is no threshold of its own left."""
    import validity

    assert validity.LIMITS == {}
    assert {c.code for c in validity.CHECKS} == {
        "committee_coverage",
        "bias_ledger",
        "pixel_calibration",
        "photometric_calibration",
    }


def test_the_power_calculator_still_works_outside_the_gate():
    """Removing the gate did not remove the arithmetic, and the floor is worth
    consulting. It just does not certify anything."""
    from validity.power import relative_error, required_particles

    assert relative_error(1, 31200) == pytest.approx(0.00566, rel=1e-3)
    assert required_particles(0.05, 2000) == pytest.approx(0.2)


def test_lens_4s_particle_count_is_no_longer_consumed_here():
    """G19 fed G11, and that was the computational half of docs/01 §4's
    'ROI vs statistics' 3 <-> 6 constraint. With G11 gone **the constraint has
    no code left**: shrinking the ROI to buy frame rate still cuts the particle
    count by the same factor, and nothing in the committee now notices."""
    up = _all_present(
        sample=_V(
            metrics={
                "geometry.count_in_field": {"evaluated": True, "expected_count": 250.0}
            }
        )
    )
    v = evaluate(_setup(upstream=up))
    assert v.status != "BLOCKED"
    assert not any("particle count" in a for a in v.assumed_inputs)
    assert not hasattr(ValiditySetup(), "resolved_n_particles")


# ---------------------------------------------------------- evidence ------


def test_undeclared_analysis_script_downgrades_evidence():
    """docs/05: which script processes the data changes the setting
    requirements, and this lens does not read D:\\codes itself."""
    v = evaluate(_setup(analysis_script=None))
    assert v.evidence == "assumed"
    assert v.advances is False


def test_fully_specified_setup_advances():
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "PASS"
    assert v.advances is True


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "validity"
    assert d["feasibility_note"]


# ------------------------------------ interop with the real lens types ----


def test_reviews_a_real_sample_lens_verdict():
    """The structural protocol has to work on the actual Verdict classes, not
    just the stand-ins -- each lens defines its own copy."""
    from optics.components import find_objective
    from sample.gate import evaluate as sample_evaluate
    from sample.setup import SampleSetup

    # Retargeted 2026-09-10 onto G16c. This used G17's mismatch bias until
    # that check became INFO, and lens 4's remaining bias sources are the
    # near-wall drag bound and settled crowding. An untrapped 2.475 um-radius
    # particle 9 um from the coverslip is 15.5% suppressed -- past the 10%
    # screen, and with no trap nothing absorbs it.
    sample_verdict = sample_evaluate(
        SampleSetup(
            objective=find_objective("100x-Oil"),
            imaging_depth_um=9.0,
            particle_radius_um=2.475,
            n_sample=1.333,
            coverslip_actual_um=170.0,
        )
    )
    assert sample_verdict.status == "PASS_WITH_CHANGES"

    v = evaluate(_setup(upstream=_all_present(sample=sample_verdict)))
    assert "geometry.wall_drag" in v.metrics["validity.bias_ledger"]["uncorrected_codes"]


def test_reviews_a_real_trapping_verdict():
    """trapping.gate.Verdict was the only one without a `feasibility` field
    until 2026-08-12, when grading was added there so it could honour docs/05's
    advances rule. It now carries one like the rest."""
    from trapping.gate import Verdict as TrappingVerdict

    tv = TrappingVerdict(status="PASS", evidence="measured")
    assert tv.feasibility == "UNKNOWN"
    v = evaluate(_setup(upstream=_all_present(trapping=tv)))
    assert v.status == "PASS"


def test_tolerates_an_upstream_verdict_with_no_feasibility_field():
    """VerdictLike deliberately does not require `feasibility`, so lens 6 keeps
    working on a verdict that lacks it. This was a live asymmetry once and the
    protocol should not start depending on the field just because it is
    currently universal."""

    class _NoFeasibility:
        status = "PASS"
        evidence = "measured"
        margins: dict = {}
        findings: list = []
        metrics: dict = {}

    probe = _NoFeasibility()
    assert not hasattr(probe, "feasibility")
    v = evaluate(_setup(upstream=_all_present(trapping=probe)))
    assert v.status == "PASS"
