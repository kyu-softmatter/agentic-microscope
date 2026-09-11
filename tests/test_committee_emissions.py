"""Tests for `committee/` -- the emission collection layer.

Two kinds of test here, and the first kind matters more. The layer PARSES the
lenses rather than trusting a declaration, so its failure mode is not "reports
the wrong number" but "confidently reports that a code cannot be emitted when
it can". So the parser's coverage and its treatment of conditionals are pinned
first, and the reconciliation second.
"""

from __future__ import annotations

import pytest

from committee import (
    LENSES,
    collect,
    collect_all,
    invisible_computations,
    ledger_reachable_codes,
    reconcile_bias_registry,
    unparsed_sites,
)

# ------------------------------------------------- the parser must not be blind


@pytest.mark.parametrize("lens", LENSES)
def test_every_construction_site_parses(lens: str) -> None:
    """⚠ THE LOAD-BEARING TEST. A miss here is not a gap in a report -- it is
    this layer claiming a code cannot reach the bias ledger when it can, which
    is worse than having no layer.

    If it fails, extend `committee.emissions` to understand the new shape.
    **Do not** widen the constructor pattern to skip it.
    """
    assert unparsed_sites(lens) == ()


def test_the_ok_helper_is_not_counted_as_an_emission() -> None:
    """`_ok` builds a CheckResult from its own arguments, so its body is the
    mechanism and not a site. Every call to it is counted at the call site,
    where the code and kind are literals."""
    for site in collect_all():
        assert site.emitted_code not in {"code", "message"}


def test_the_ok_severity_is_read_per_lens_and_is_not_uniform() -> None:
    """The difference is load-bearing: every `gate.py` drops severity "ok" from
    `findings`, so a lens whose `_ok` says "ok" hides its passing computations
    and one whose `_ok` says "info" shows them. Lenses 5, 7 and 8 were changed
    to "info" during the 2026-09 review."""
    from committee.emissions import _OK_SEVERITY

    assert _OK_SEVERITY["optics"] == "ok"
    assert _OK_SEVERITY["photo"] == "info"
    assert _OK_SEVERITY["trapping"] == "info"
    assert _OK_SEVERITY["stability"] == "info"
    # Nothing from a lens whose `_ok` is "info" can be invisible.
    invisible = {s.lens for s in invisible_computations()}
    assert not invisible & {"photo", "trapping", "stability"}


# ------------------------------------------------ correlated conditionals ------


def test_a_conditional_code_emits_both_branches() -> None:
    """`detection.check_sampling` writes
    `"sampling" if ok else "sampling.undersampled"`, and a regex written for
    this missed both -- which is how `sampling.undersampled` came to be absent
    from a hand-written audit."""
    codes = {s.emitted_code for s in collect("detection")}
    assert {"sampling", "sampling.undersampled", "sampling.wrong_direction"} <= codes


def test_a_shared_condition_is_zipped_and_not_multiplied() -> None:
    """The bug this caught in its own first run. Code and severity are the same
    conditional, so only two of four combinations exist; the cross product
    invents `("sampling", "fail")` -- BIAS-kind, findings-visible, and
    impossible -- which duly appeared as an unregistered ledger code somebody
    would have been sent to register."""
    pairs = {
        (s.emitted_code, s.severity)
        for s in collect("detection")
        if s.check == "sampling" and s.kind == "bias"
    }
    assert pairs == {("sampling", "ok"), ("sampling.wrong_direction", "fail")}


def test_a_severity_assigned_to_a_local_is_still_resolved() -> None:
    """`optics` assigns first and passes the name:
    `severity = "warn" if ratio < 0.5 else "ok"`. Two sites depend on following
    that one binding."""
    pairs = {
        (s.emitted_code, s.severity)
        for s in collect("optics")
        if s.emitted_code in {"excitation.coupling", "emission.centering"}
    }
    assert pairs == {
        ("excitation.coupling", "warn"),
        ("excitation.coupling", "ok"),
        ("emission.centering", "warn"),
        ("emission.centering", "ok"),
    }


# ---------------------------------------------------- what reaches the ledger ---


def test_reaching_the_ledger_is_decided_by_the_results_kind() -> None:
    """Not by the owning `Check`'s registration -- the subtlety that made a
    hand count wrong by two. Three BIAS-kind results come out of
    INFO-registered checks in lens 4 and do reach the ledger."""
    import sample

    registered_kind = {c.code: c.kind for c in sample.CHECKS}
    assert registered_kind["depth_window"] == "info"
    assert registered_kind["count_in_field"] == "info"

    reachable = ledger_reachable_codes()
    assert "geometry.depth_window.empty" in reachable
    assert "geometry.count_in_field.crowded" in reachable
    assert "geometry.count_in_field.jammed" in reachable


def test_an_ok_severity_bias_code_does_not_reach_the_ledger() -> None:
    """Every `gate.py` drops severity "ok", so a BIAS result on the pass path
    is unreachable whatever the registries say."""
    reachable = ledger_reachable_codes()
    ok_bias = {
        s.emitted_code
        for s in collect_all()
        if s.kind == "bias" and s.severity == "ok"
    }
    assert "motion_blur" in ok_bias
    assert "motion_blur" not in reachable


def test_validity_does_not_feed_its_own_ledger() -> None:
    """`bias_findings` reads `upstream` only, so lens 6's own BIAS result is
    not a candidate."""
    assert any(s.kind == "bias" for s in collect("validity"))
    assert not any(s.reaches_bias_ledger for s in collect("validity"))


# ------------------------------------------------------------ reconciliation ----


def test_the_reconciliation_is_derived_and_still_dirty() -> None:
    """The drift is real, known and deliberate: KH is reconciling it through
    this layer rather than by hand, because a table edited to match today's
    emitters drifts again on the next gate change and had already done so
    twice. **So this asserts the shape, not that it is clean.**
    """
    r = reconcile_bias_registry()
    assert not r.clean
    assert r.agreed == (
        "crosstalk",
        "geometry.wall_drag",
        "geometry.wall_drag.trapped",
        "motion_blur.biased",
    )
    assert r.registered_without_emitter == (
        "geometry.coverslip",
        "geometry.ri_mismatch",
        "perturbation.light_driving",
        "perturbation.photobleaching",
        "perturbation.saturation",
        "stability.evaporation",
        "stability.lateral_drift",
    )
    assert r.emitted_without_registry == (
        "fps_provenance.requested",
        "fps_provenance.unmeasured",
        "fps_provenance.unrealizable",
        "geometry.count_in_field.crowded",
        "geometry.count_in_field.jammed",
        "geometry.depth_window.empty",
        "pixel_container.unconfirmed",
        "sampling.wrong_direction",
    )


def test_the_layer_found_one_the_hand_count_had_wrong() -> None:
    """`sampling.wrong_direction` is BIAS at severity "fail", so it reaches the
    ledger -- and `tests/test_gate_registry.py` asserted the opposite until
    2026-09-11, because the `ok` branch of its conditional was read and the
    `fail` branch was not. Eight unregistered emitters, not seven.
    """
    site = next(
        s for s in collect("detection") if s.emitted_code == "sampling.wrong_direction"
    )
    assert (site.kind, site.severity) == ("bias", "fail")
    assert site.reaches_bias_ledger
    assert "sampling.wrong_direction" in reconcile_bias_registry().emitted_without_registry


def test_every_site_carries_its_address() -> None:
    """An emission with no address would be a code from a helper rather than a
    registered check, which is the thing that hides."""
    for site in collect_all():
        assert site.address is not None, f"{site.lens}:{site.line} {site.emitted_code}"
        assert site.check is not None


def test_the_site_count_is_pinned() -> None:
    """Not an interesting number in itself -- it is here so that adding or
    removing a branch shows up as a decision rather than as noise."""
    assert len(collect_all()) == 104
