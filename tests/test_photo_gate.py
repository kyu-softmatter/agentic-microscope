"""Tests for photo.gate.evaluate (lens 5) -- mirrors tests/test_sample_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

import pytest

from photo.gate import evaluate
from photo.setup import IlluminationSetup

# FITC's real registry values (data/fluorophores.yaml). Sample-plane power and
# illuminated area are measured as of 2026-09-09 but are supplied per evaluation
# rather than looked up, so the defaults below still carry them.
FITC = dict(
    ext_coeff_m1cm1=75000,
    quantum_yield=0.92,
    lifetime_ns=4.1,
)


def _setup(**overrides) -> IlluminationSetup:
    defaults = dict(
        power_mw_at_sample=0.05,
        illuminated_area_um2=1e4,
        wavelength_nm=488.0,
        exposure_ms=20.0,
        n_frames=100,
        frame_interval_ms=100.0,
        #: Stated on purpose. Left out it is the "nobody asked" state, which
        #: is what the tri-state tests below cover; every other test wants a
        #: fully answered setup.
        photoresponsive=False,
        **FITC,
    )
    defaults.update(overrides)
    return IlluminationSetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_measured_sample_power():
    """The project's top blocker. A percent setting is not a physical
    quantity, so this lens refuses rather than guessing."""
    v = evaluate(_setup(power_mw_at_sample=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.power_at_sample" for f in v.findings)


def test_blocked_without_an_illuminated_area():
    v = evaluate(_setup(illuminated_area_um2=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.power_at_sample" for f in v.findings)


def test_blocked_without_an_exposure_plan():
    v = evaluate(_setup(exposure_ms=None, n_frames=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.exposure_plan" for f in v.findings)


def test_photoresponsive_sample_without_a_threshold_blocks():
    """docs/06 D2. A guessed threshold would be worse than none."""
    v = evaluate(_setup(photoresponsive=True))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.light_driving_threshold" for f in v.findings)


def test_photoresponsive_sample_with_a_threshold_is_judgeable():
    v = evaluate(_setup(photoresponsive=True, light_driving_threshold_w_cm2=100.0))
    assert v.status != "BLOCKED"


def test_non_photoresponsive_sample_never_warns_about_light_driving():
    v = evaluate(_setup(power_mw_at_sample=50.0))
    assert v.margins["perturbation.light_driving"] == 10.0
    assert v.metrics["perturbation.light_driving"]["photoresponsive"] is False
    assert v.metrics["perturbation.light_driving"]["evaluated"] is True


def test_unasked_photoresponsiveness_warns_instead_of_clearing():
    """docs/06 D2's accident is the unasked question. A default of "no" would
    make this gate silent in exactly the case it exists for."""
    v = evaluate(_setup(photoresponsive=None))
    f = next(f for f in v.findings if f.code == "perturbation.light_driving")
    assert f.severity == "warn"
    assert v.metrics["perturbation.light_driving"]["evaluated"] is False


def test_unasked_photoresponsiveness_costs_the_verdict_advances():
    v = evaluate(_setup(photoresponsive=None))
    assert v.evidence == "assumed"
    # `advances` is None, not False -- a reporting section neither advances
    # nor refuses (2026-09-10). What an unasked question still costs is the
    # evidence tier and its place in assumed_inputs.
    assert v.advances is None
    assert any("photoresponsiveness" in a for a in v.assumed_inputs)


def test_unasked_photoresponsiveness_does_not_block_the_whole_lens():
    """It is a missing answer, not a missing number: the dose is still
    reported, so the section reports rather than refusing.

    Went through G20's margin, then G22's, and now through neither -- since
    2026-09-10 nothing here is graded, so the assertion is that the report was
    still written and the dose still reached `findings`."""
    v = evaluate(_setup(photoresponsive=None))
    assert v.status == "REPORT"
    assert any(f.code == "perturbation.total_dose" for f in v.findings)


def test_unasked_photoresponsiveness_does_not_fake_a_margin():
    """MAX_MARGIN here means "not evaluated", not "lots of headroom" -- so it
    must not drag the feasibility grade around either."""
    unasked = evaluate(_setup(photoresponsive=None))
    answered = evaluate(_setup(photoresponsive=False))
    assert unasked.feasibility == answered.feasibility
    assert unasked.bottleneck == answered.bottleneck


def test_photoresponsive_sample_below_threshold_passes():
    v = evaluate(
        _setup(photoresponsive=True, light_driving_threshold_w_cm2=100.0)
    )
    assert v.margins["perturbation.light_driving"] >= 1.0


def test_photoresponsive_sample_above_threshold_warns():
    """Lens 5's reason to exist: lens 1 says raise the light for SNR, and this
    is the only lens that can say that ruins the experiment."""
    v = evaluate(
        _setup(
            power_mw_at_sample=20.0,  # 200 W/cm^2 over a 1e4 um^2 field
            photoresponsive=True,
            light_driving_threshold_w_cm2=100.0,
        )
    )
    assert any(
        f.code == "perturbation.light_driving" and f.severity == "warn"
        for f in v.findings
    )
    msg = next(f.message for f in v.findings if f.code == "perturbation.light_driving")
    assert "not a measurement tool" in msg


# ----------------------------------------------------- G22 total dose ----


def test_total_dose_is_reported_without_a_ceiling():
    v = evaluate(_setup())
    m = v.metrics["perturbation.total_dose"]
    assert m["evaluated"] is True
    assert m["total_dose_j_cm2"] == pytest.approx(0.5 * 2.0, abs=1e-6)  # 0.5 W/cm^2 x 2 s


def test_duty_cycle_is_reported_when_the_interval_is_known():
    v = evaluate(_setup(exposure_ms=20.0, frame_interval_ms=100.0))
    assert v.metrics["perturbation.total_dose"]["duty_cycle"] == pytest.approx(0.2)


def test_dose_over_a_stated_ceiling_warns():
    v = evaluate(_setup(dose_limit_j_cm2=0.1))
    assert any(
        f.code == "perturbation.total_dose" and f.severity == "warn" for f in v.findings
    )


def test_total_dose_is_info_and_never_blocks():
    v = evaluate(_setup(dose_limit_j_cm2=1e-9))
    assert v.status != "BLOCKED"


# ------------------------------------------ 5 -> 7 trap heating handoff --


def test_trap_heating_is_silent_when_the_trap_is_off():
    v = evaluate(_setup())
    f = next(f for f in v.findings if f.code == "perturbation.trap_heating_unowned")
    # Visible, but saying the opposite thing: "does not apply". Since
    # 2026-09-10 every check in this section reaches `findings`, so silence is
    # no longer how "not applicable" is expressed -- words are.
    assert "not in use" in f.message


def test_trap_on_raises_the_unowned_heating_finding():
    """docs/06 D6 assigns trap heating to lens 7, which has no heating check and
    is not getting one (ungated by decision, 2026-08-19). A named risk still
    has to reach the reader, so lens 5 says it rather than assuming someone
    else did."""
    v = evaluate(_setup(trap_on=True))
    f = next(f for f in v.findings if f.code == "perturbation.trap_heating_unowned")
    assert f.severity == "info"
    assert "ungated by decision" in f.message


def test_temperature_sensitive_sample_gets_a_stronger_heating_notice():
    """KH 2026-09-10: keep trap heating as INFO, but a temperature-sensitive
    sample -- a liquid crystal, an ATPS, a gel -- has to be told loudly. For
    those the trap does not bias a number, it can move the sample across a
    transition at the focus, and nothing in the committee sees that: G21
    covers light-DRIVING through the visible line, a different wavelength and
    a different mechanism.
    """
    v = evaluate(_setup(trap_on=True, temperature_sensitive=True))
    f = next(f for f in v.findings if f.code == "perturbation.trap_heating_unowned")
    assert f.severity == "info"
    assert "TEMPERATURE-SENSITIVE" in f.message
    assert "liquid crystal" in f.message
    assert f.action is not None and "first-order design constraint" in f.action


def test_an_unasked_temperature_sensitivity_is_reported_as_unasked():
    """Same tri-state discipline as `photoresponsive`: silence is not a no."""
    v = evaluate(_setup(trap_on=True))
    f = next(f for f in v.findings if f.code == "perturbation.trap_heating_unowned")
    assert "Unasked, not cleared" in f.message
    assert f.numbers["temperature_sensitive"] is None


def test_declaring_temperature_sensitivity_never_changes_the_grade():
    """"인포로만 남겨두자" -- it stays INFO in every state, so the feasibility
    and the bottleneck must be identical across all three."""
    unasked = evaluate(_setup(trap_on=True))
    no = evaluate(_setup(trap_on=True, temperature_sensitive=False))
    yes = evaluate(_setup(trap_on=True, temperature_sensitive=True))
    assert unasked.feasibility == no.feasibility == yes.feasibility
    assert unasked.bottleneck == no.bottleneck == yes.bottleneck
    assert unasked.status == no.status == yes.status
    for v in (unasked, no, yes):
        assert v.margins["perturbation.trap_heating_unowned"] == 10.0


def test_trap_heating_notice_does_not_change_the_grade():
    with_trap = evaluate(_setup(trap_on=True))
    without = evaluate(_setup())
    assert with_trap.feasibility == without.feasibility


# ---------------------------------------------------------- evidence ------


def test_missing_frame_interval_downgrades_evidence():
    v = evaluate(_setup(frame_interval_ms=None))
    assert v.evidence == "assumed"
    assert v.advances is None  # reporting section; see test_advances_rule.py


def test_fully_specified_setup_reports():
    """RENAMED 2026-09-10: there is nothing here to advance. A fully specified
    setup produces a report, with every check in it."""
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "REPORT"
    assert v.feasibility == "N/A"
    assert v.advances is None
    assert {f.code for f in v.findings} >= {
        "perturbation.light_driving",
        "perturbation.total_dose",
        "perturbation.trap_heating_unowned",
    }


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "photo"
    assert d["reporting_only"] is True
    assert d["advances"] is None
