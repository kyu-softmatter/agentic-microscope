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
    removing a branch shows up as a decision rather than as noise. 104 before
    lens 9 was added on 2026-09-11, 112 after, 116 once L2.6 added its four
    branches on 2026-09-14 -- three of them `missing.*`, which is the point of
    that check -- and 127 when L4.8, L6.5 and L9.6 landed the same day with
    eleven between them."""
    assert len(collect_all()) == 127


def test_the_layer_covers_every_lens_package() -> None:
    """A lens this layer does not know about is a lens whose emissions nobody
    reconciles -- the exact blindness it exists to remove. So registering a new
    lens in `committee.emissions.LENSES` is part of adding one, and this is
    what says so.

    Derived from the filesystem rather than from a list, because a list is the
    thing that would go stale. A lens is a package with both `checks.py` and
    `gate.py`; `setup.py` is NOT part of the test, because `optics` and
    `trapping` do not have one -- optics reads a `Channel` and trapping a
    `TrapSetup` from its own `dynamics.py`.
    """
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    packages = {
        p.parent.name
        for p in repo.glob("*/checks.py")
        if (p.parent / "gate.py").exists()
    }
    assert packages == set(LENSES), (
        f"lens packages and committee.emissions.LENSES disagree: "
        f"{packages ^ set(LENSES)}"
    )


def test_the_new_lens_has_no_invisible_computations() -> None:
    """Lens 9 was built after the `_ok`-hides-it defect had appeared five
    times, so its `_ok` writes severity "info" from the start."""
    assert not [s for s in invisible_computations() if s.lens == "velocity"]


# ------------------------------------ the nine cross-lens constraints, parsed --
#
# Found missing from the stage-2 packets on 2026-09-15 by convening the agents
# for real: `sample-optics`'s own description says it "must be invoked together
# with optics (Lens 1)" and the packet carried no lens 1 at all. E6, and no
# code could see 01 §4's table.


def test_the_nine_are_parsed_and_not_copied():
    """A table transcribed into a dict here would be a second definition of
    the nine and would drift from the prose -- the failure this package exists
    to stop, and which its two bias registries had already committed twice."""
    from committee import constraints

    nine = constraints.all_constraints()
    assert len(nine) == 9
    assert all(len(c.lenses) >= 2 for c in nine)
    assert all(1 <= n <= 9 for c in nine for n in c.lenses)
    assert all(c.content for c in nine), "each row carries its own prose"


def test_a_struck_through_half_is_not_resurrected():
    """01 §4's `Particle count` row reads `~~4 → 6~~, 8 → 4`: the 4 -> 6 half
    died with G11 on 2026-09-11 and the strikethrough is the document saying
    so. A parser ignoring the markup would hand lens 6 a constraint nothing
    implements."""
    from committee import constraints

    row = next(c for c in constraints.all_constraints() if c.name == "Particle count")
    assert row.partly_retired
    assert row.lenses == (8, 4)
    assert 6 not in row.lenses


def test_the_pairs_are_the_ones_e6_names():
    """CLAUDE.md E6: "convene lenses 1 and 5 together, and 1 and 4 likewise".
    Derived from the table rather than from E6's prose, so a constraint added
    to 01 §4 reaches the packets with no edit and one removed stops."""
    from committee import constraints

    assert constraints.partners_of(4) == (1, 8)
    assert constraints.partners_of(5) == (1,)
    assert constraints.partners_of(1) == (4, 5)


def test_lens_9_is_in_no_constraint_and_that_is_the_document_not_a_bug():
    """Lens 9 was added 2026-09-11 and 01 §4's table predates it. Asserted so
    the gap is a recorded fact rather than a parser suspicion: lens 9 DOES
    hand lens 6 a correlation time, but that is a handoff in
    `designer.run.CROSS_TIER`, not a constraint neither lens owns."""
    from committee import constraints

    from designer.run import CROSS_TIER

    assert constraints.partners_of(9) == ()
    assert ("velocity", "validity") in CROSS_TIER


def test_a_renamed_heading_fails_loudly():
    """Returning no constraints would read as "no lens is paired with any
    other", which is the silence-as-agreement failure in its purest form."""
    from committee import constraints

    with pytest.raises(ValueError, match="cross-lens"):
        constraints._rows("# a document with no such heading\n")


# ------------------------- the tolerance band, and the key it is keyed on --


def test_every_tolerance_key_is_a_code_its_lens_actually_emits():
    """The failure this catches was committed on the way in, 2026-09-16.

    `TOLERANCE` was first keyed on the REGISTERED check code (`buffer`) while
    results carry the EMITTED one (`buffer.too_small`), so the dict matched
    nothing and every band was silently inert -- "a registry naming a code
    nobody emits", the second of the two failure modes this package exists to
    catch, arriving in a new table.

    The relation cannot be recovered by string surgery: `buffer` -> 
    `buffer.too_small` adds a suffix, `na_feasibility` ->
    `geometry.na_feasibility` adds a prefix. So the check is against the
    parsed emission sites, not against a rule.
    """
    import importlib

    for lens in LENSES:
        tolerance = getattr(importlib.import_module(f"{lens}.checks"), "TOLERANCE", {})
        if not tolerance:
            continue
        emitted = {s.emitted_code for s in collect(lens)}
        unknown = sorted(set(tolerance) - emitted)
        assert not unknown, f"{lens}: TOLERANCE names {unknown}, which nothing emits"


def test_a_band_is_only_on_a_failure_code():
    """A band on an `ok` or `info` code would be inert in a different way --
    those severities never reach `hard_failed`, so the entry would read as a
    granted concession that can never be granted."""
    import importlib

    for lens in LENSES:
        tolerance = getattr(importlib.import_module(f"{lens}.checks"), "TOLERANCE", {})
        by_code: dict[str, set[str]] = {}
        for site in collect(lens):
            by_code.setdefault(site.emitted_code, set()).add(site.severity)
        for code in tolerance:
            assert "fail" in by_code.get(code, set()), f"{lens}: {code} never fails"


def test_a_band_stays_within_its_own_bounds():
    """Every band is a concession on a threshold this repository chose, so
    none of them may reach a value where the failure stops being a
    degradation. 0.5 is "2x past the threshold" -- KH, 2026-09-16 -- and
    nothing is allowed below it without its own recorded reason."""
    import importlib

    for lens in LENSES:
        tolerance = getattr(importlib.import_module(f"{lens}.checks"), "TOLERANCE", {})
        for code, band in tolerance.items():
            assert 0.0 < band < 1.0, f"{lens}: {code} band {band} is not a band"
            assert band >= 0.5, (
                f"{lens}: {code} band {band} is looser than 2x, which is the "
                "operator's stated limit"
            )
