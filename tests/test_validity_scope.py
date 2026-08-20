"""Tests for the two things lens 6 does beyond counting other lenses' verdicts:

- **the correction registry** -- a declared correction is checked against
  `CORRECTIONS`/`UNCORRECTABLE` rather than believed, so naming a bias that has
  no correction no longer clears it;
- **per-physical-quantity verdicts** -- `BIAS_SCOPE` decides which bias damages
  which quantity, so one session can report a biased MSD and a sound intensity
  profile instead of one collapsed status (docs/05 Lens 6).

`tests/test_validity_gate.py` covers the gate's own structure; this file covers
the scoping and the declaration audit.
"""

from __future__ import annotations

import pytest

from validity.gate import evaluate, evaluate_per_quantity
from validity.setup import (
    BIAS_SCOPE,
    CORRECTIONS,
    STANDING_LENSES,
    UNCORRECTABLE,
    ValiditySetup,
)


class _V:
    """Structural VerdictLike stand-in for an upstream lens."""

    def __init__(self, status="PASS", evidence="measured", findings=()):
        self.status = status
        self.evidence = evidence
        self.margins = {}
        self.findings = list(findings)
        self.metrics = {}


class _F:
    """Structural FindingLike stand-in."""

    def __init__(self, code, lens, kind="bias", severity="warn", margin=0.5):
        self.code = code
        self.lens = lens
        self.kind = kind
        self.severity = severity
        self.margin = margin
        self.message = f"{code} from {lens}"


def _upstream(**overrides):
    up = {name: _V() for name in STANDING_LENSES}
    up.update(overrides)
    return up


def _setup(**overrides) -> ValiditySetup:
    """A setup that passes cleanly, so a test only has to break one thing.

    The photometric calibrations are all in hand, which lets an intensity-based
    quantity be judged without G25 clouding the result.
    """
    defaults = dict(
        intended_quantity="diffusion",
        target_relative_error=0.05,
        upstream=_upstream(),
        n_particles=200.0,
        n_frames=2000,
        pixel_size_measured=True,
        background_measured=True,
        dark_current_measured=True,
        flat_field_measured=True,
        analysis_script="D:/codes/microrheology/track_msd.m",
    )
    defaults.update(overrides)
    return ValiditySetup(**defaults)


def _ledger(verdict, quantity=None):
    code = "validity.bias_ledger"
    return verdict.metrics[quantity][code] if quantity else verdict.metrics[code]


# ------------------------------------- G23 the correction registry ------


def test_the_two_registries_are_disjoint():
    """A bias cannot be both correctable and uncorrectable."""
    assert not set(CORRECTIONS) & set(UNCORRECTABLE)


def test_declaring_a_real_correction_clears_the_bias():
    """Motion blur has Savin-Doyle, so the declaration is a claim that can be
    true."""
    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(
        _setup(upstream=up, corrections_applied=frozenset({"motion_blur.biased"}))
    )
    assert _ledger(v)["uncorrected"] == 0
    assert v.status != "FAIL"


def test_declaring_a_correction_that_does_not_exist_does_not_clear_the_bias():
    """The hole this closes: `corrections_applied` was matched against nothing,
    so naming an uncorrectable bias cleared it and the ledger read clean."""
    up = _upstream(sample=_V(findings=[_F("geometry.ri_mismatch", "sample")]))
    v = evaluate(
        _setup(upstream=up, corrections_applied=frozenset({"geometry.ri_mismatch"}))
    )
    assert v.status == "FAIL"
    assert _ledger(v)["uncorrected"] == 1
    assert _ledger(v)["false_correction_codes"] == ["geometry.ri_mismatch"]


def test_a_false_declaration_is_named_and_told_to_withdraw():
    up = _upstream(photo=_V(findings=[_F("perturbation.light_driving", "photo")]))
    v = evaluate(
        _setup(
            upstream=up,
            corrections_applied=frozenset({"perturbation.light_driving"}),
        )
    )
    ledger = next(f for f in v.findings if f.code == "validity.bias_ledger")
    assert "perturbation.light_driving" in ledger.message
    assert "no correction" in ledger.message
    assert "withdraw" in ledger.action.lower()


def test_an_unregistered_correction_clears_the_bias_but_forfeits_measured():
    """A gate this table has not caught up with should not block work -- but an
    unaudited clearance must not advance either."""
    up = _upstream(optics=_V(findings=[_F("some.future_bias", "optics")]))
    v = evaluate(
        _setup(upstream=up, corrections_applied=frozenset({"some.future_bias"}))
    )
    assert _ledger(v)["uncorrected"] == 0
    assert _ledger(v)["unverified_correction_codes"] == ["some.future_bias"]
    assert v.evidence == "assumed"
    assert v.advances is False


def test_a_declaration_matching_no_upstream_finding_is_not_audited():
    """Only a declaration that actually cleared something gets flagged."""
    v = evaluate(_setup(corrections_applied=frozenset({"some.future_bias"})))
    assert _ledger(v)["unverified_correction_codes"] == []
    assert v.evidence == "measured"


def test_every_uncorrectable_entry_explains_what_to_do_instead():
    """A refusal without an instruction is a complaint (01 §3 Principle 5)."""
    for code, why in UNCORRECTABLE.items():
        assert why.strip(), code
        assert len(why) > 20, code


# ------------------------------------------------ G23 bias scoping ------


def test_a_photometric_bias_does_not_touch_a_geometric_quantity():
    """Bleaching is an intensity decay; it costs a tracking run statistics, not
    positional accuracy."""
    up = _upstream(photo=_V(findings=[_F("perturbation.photobleaching", "photo")]))
    v = evaluate(_setup(intended_quantity="diffusion", upstream=up))
    assert _ledger(v)["applicable"] == 0
    assert _ledger(v)["out_of_scope_codes"] == ["perturbation.photobleaching"]
    assert v.status != "FAIL"


def test_the_same_bias_fails_the_quantity_it_does_damage():
    up = _upstream(photo=_V(findings=[_F("perturbation.photobleaching", "photo")]))
    v = evaluate(_setup(intended_quantity="intensity", upstream=up))
    assert v.status == "FAIL"
    assert _ledger(v)["applicable"] == 1


def test_a_geometric_bias_fails_a_geometric_quantity():
    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(_setup(intended_quantity="msd", upstream=up))
    assert v.status == "FAIL"


def test_an_unscoped_bias_damages_every_quantity():
    """Light-driving moves the sample itself, so it is deliberately absent from
    BIAS_SCOPE and has to apply to both classes of quantity."""
    assert "perturbation.light_driving" not in BIAS_SCOPE
    up = _upstream(photo=_V(findings=[_F("perturbation.light_driving", "photo")]))
    for quantity in ("diffusion", "stoichiometry"):
        v = evaluate(_setup(intended_quantity=quantity, upstream=up))
        assert v.status == "FAIL", quantity


def test_out_of_scope_biases_are_named_rather_than_dropped():
    up = _upstream(photo=_V(findings=[_F("perturbation.photobleaching", "photo")]))
    v = evaluate(_setup(intended_quantity="diffusion", upstream=up))
    # The check passed, so it raises no finding -- but the bias is still on the
    # record, counted and named, rather than dropped.
    assert [f.code for f in v.findings if f.code == "validity.bias_ledger"] == []
    assert _ledger(v)["bias_findings"] == 1
    assert _ledger(v)["applicable"] == 0
    assert _ledger(v)["out_of_scope_codes"] == ["perturbation.photobleaching"]


def test_the_worst_margin_is_taken_among_applicable_biases_only():
    """An out-of-scope bias must not set the bottleneck for a quantity it does
    not touch."""
    up = _upstream(
        detection=_V(findings=[_F("motion_blur.biased", "detection", margin=0.8)]),
        photo=_V(findings=[_F("perturbation.photobleaching", "photo", margin=0.2)]),
    )
    v = evaluate(_setup(intended_quantity="diffusion", upstream=up))
    assert v.margins["validity.bias_ledger"] == pytest.approx(0.8)


def test_every_scoped_bias_names_calibrations_that_exist():
    """A scope tag that no quantity requires would silently disable the bias."""
    from validity.setup import QUANTITY_REQUIREMENTS

    known = {c for reqs in QUANTITY_REQUIREMENTS.values() for c in reqs}
    for code, scope in BIAS_SCOPE.items():
        assert scope <= known, code


# ------------------------------- per-physical-quantity verdicts ---------


def _both(**overrides):
    return _setup(intended_quantities=("diffusion", "intensity"), **overrides)


def test_one_session_can_have_a_biased_msd_and_a_sound_intensity_profile():
    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(_both(upstream=up))
    per = v.metrics["validity.per_quantity"]
    assert per["diffusion"]["status"] == "FAIL"
    assert per["intensity"]["status"] == "PASS"
    assert per["intensity"]["advances"] is True
    assert v.status == "FAIL"


def test_findings_carry_the_quantity_they_belong_to():
    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(_both(upstream=up))
    ledger = [f for f in v.findings if f.code == "validity.bias_ledger"]
    assert [f.physical_quantity for f in ledger] == ["diffusion"]


def test_a_quantity_independent_finding_is_emitted_once_untagged():
    """Statistical power does not depend on which quantity is wanted, so a
    two-quantity session must not report it twice."""
    v = evaluate(_both(n_particles=2.0, n_frames=10))
    power = [f for f in v.findings if f.code == "validity.statistical_power"]
    assert len(power) == 1
    assert power[0].physical_quantity is None


def test_margins_are_namespaced_by_quantity():
    v = evaluate(_both())
    assert "diffusion:validity.bias_ledger" in v.margins
    assert "intensity:validity.bias_ledger" in v.margins


def test_the_aggregate_advances_only_when_every_quantity_does():
    assert evaluate(_both()).advances is True

    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    mixed = evaluate(_both(upstream=up))
    assert mixed.metrics["validity.per_quantity"]["intensity"]["advances"] is True
    assert mixed.advances is False


def test_an_unknown_quantity_blocks_only_its_own_verdict():
    v = evaluate(_setup(intended_quantities=("diffusion", "banana")))
    per = v.metrics["validity.per_quantity"]
    assert per["banana"]["status"] == "BLOCKED"
    assert per["diffusion"]["status"] == "PASS"
    assert v.status == "BLOCKED"


def test_fail_outranks_blocked_in_the_aggregate():
    up = _upstream(detection=_V(findings=[_F("motion_blur.biased", "detection")]))
    v = evaluate(_setup(intended_quantities=("diffusion", "banana"), upstream=up))
    assert v.status == "FAIL"


def test_the_aggregate_feasibility_is_the_worst_quantitys():
    up = _upstream(
        detection=_V(findings=[_F("motion_blur.biased", "detection", margin=0.3)])
    )
    v = evaluate(_both(upstream=up))
    assert v.metrics["validity.per_quantity"]["intensity"]["feasibility"] == "ROUTINE"
    assert v.feasibility == "MARGINAL"


def test_a_single_quantity_list_behaves_like_the_singular_field():
    plural = evaluate(_setup(intended_quantities=("diffusion",)))
    singular = evaluate(_setup(intended_quantity="diffusion"))
    assert plural.to_dict() == singular.to_dict()


def test_a_one_entry_list_works_with_the_singular_field_unset():
    """The plural field alone must be enough -- the single-quantity path used to
    read `intended_quantity` and would have blocked on None."""
    v = evaluate(_setup(intended_quantity=None, intended_quantities=("diffusion",)))
    assert v.status == "PASS"
    assert v.advances is True
    assert "validity.pixel_calibration" in v.margins


def test_repeated_quantities_are_judged_once():
    assert ValiditySetup(intended_quantities=("msd", "msd")).quantities == ("msd",)
    assert list(evaluate_per_quantity(_setup(intended_quantities=("msd", "msd")))) == [
        "msd"
    ]


def test_the_plural_field_wins_over_the_singular_one():
    setup = _setup(intended_quantity="diffusion", intended_quantities=("intensity",))
    assert setup.quantities == ("intensity",)


def test_evaluate_per_quantity_keeps_the_stated_order():
    per = evaluate_per_quantity(_setup(intended_quantities=("intensity", "diffusion")))
    assert list(per) == ["intensity", "diffusion"]
