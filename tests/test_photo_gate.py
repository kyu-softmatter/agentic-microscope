"""Tests for photo.gate.evaluate (lens 5) -- mirrors tests/test_sample_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

import pytest

from photo.gate import evaluate
from photo.setup import IlluminationSetup

# FITC's real registry values (data/fluorophores.yaml), with a bleach_photons
# and a sample-plane power supplied -- neither exists on the instrument yet.
FITC = dict(
    ext_coeff_m1cm1=75000,
    quantum_yield=0.92,
    lifetime_ns=4.1,
    bleach_photons=3.0e4,
)


def _setup(**overrides) -> IlluminationSetup:
    defaults = dict(
        power_mw_at_sample=0.05,
        illuminated_area_um2=1e4,
        wavelength_nm=488.0,
        exposure_ms=20.0,
        n_frames=100,
        frame_interval_ms=100.0,
        #: Both stated on purpose. Left out they are the two "nobody asked"
        #: states, which is what the tri-state and coupling tests below cover;
        #: every other test wants a fully answered setup.
        photoresponsive=False,
        excitation_coupling=1.0,
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


def test_blocked_without_bleach_photons():
    """docs/04 §6: the qualitative photostability grade is not a substitute."""
    v = evaluate(_setup(bleach_photons=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.bleach_photons" for f in v.findings)


def test_blocked_without_a_lifetime():
    v = evaluate(_setup(lifetime_ns=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.lifetime" for f in v.findings)


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


# ------------------------------------------------- G10 photobleaching -----


def test_gentle_illumination_keeps_bleaching_under_the_limit():
    v = evaluate(_setup())
    assert v.margins["perturbation.photobleaching"] >= 1.0


def test_long_movie_bleaches_past_the_limit():
    v = evaluate(_setup(n_frames=100000))
    assert any(
        f.code == "perturbation.photobleaching" and f.severity == "warn"
        for f in v.findings
    )
    assert v.margins["perturbation.photobleaching"] < 1.0


def test_bleaching_scales_with_frame_count():
    few = evaluate(_setup(n_frames=100))
    many = evaluate(_setup(n_frames=1000))
    assert (
        many.metrics["perturbation.photobleaching"]["bleached_fraction"]
        > few.metrics["perturbation.photobleaching"]["bleached_fraction"]
    )


def test_bleaching_message_states_it_is_a_lower_bound():
    """docs/04 §6: superlinear triplet pathways are not modelled."""
    v = evaluate(_setup(n_frames=100000))
    msg = next(
        f.message for f in v.findings if f.code == "perturbation.photobleaching"
    )
    assert "lower bound" in msg


# --------------------------------------------------- G20 saturation -------


def test_low_power_stays_in_the_linear_regime():
    v = evaluate(_setup())
    assert v.margins["perturbation.saturation"] >= 1.0


def test_high_power_drives_the_dye_into_saturation():
    """FITC saturates near 3.5e5 W/cm^2, which a widefield field-of-view never
    reaches -- but 5 mW focused into a 10 um^2 spot is 5e4 W/cm^2 and does
    (excited-state fraction 0.126 against the 0.1 limit). That is confocal /
    spinning-disk territory, not widefield."""
    v = evaluate(_setup(power_mw_at_sample=5.0, illuminated_area_um2=10.0))
    assert any(
        f.code == "perturbation.saturation" and f.severity == "warn" for f in v.findings
    )


def test_widefield_power_does_not_saturate():
    """50 mW over a 1e4 um^2 field is 500 W/cm^2 -- three orders below FITC's
    saturation irradiance. G20 should stay quiet rather than cry wolf."""
    v = evaluate(_setup(power_mw_at_sample=50.0))
    assert v.margins["perturbation.saturation"] >= 1.0


def test_saturation_warning_says_the_photon_budget_overestimates():
    """The point of G20: it invalidates lens 1 and 2's numbers, which assume
    emission is linear in power."""
    v = evaluate(_setup(power_mw_at_sample=5.0, illuminated_area_um2=10.0))
    msg = next(f.message for f in v.findings if f.code == "perturbation.saturation")
    assert "overestimates" in msg


def test_saturation_irradiance_is_reported():
    v = evaluate(_setup())
    assert v.metrics["perturbation.saturation"]["saturation_irradiance_w_cm2"] > 0


# ------------------------------------------------- G21 light-driving ------


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
    assert v.advances is False
    assert any("photoresponsiveness" in a for a in v.assumed_inputs)


def test_unasked_photoresponsiveness_does_not_block_the_whole_lens():
    """It is a missing answer, not a missing number: bleaching and saturation
    can still be judged, so the lens reports rather than refusing."""
    v = evaluate(_setup(photoresponsive=None))
    assert v.status == "PASS_WITH_CHANGES"
    assert "perturbation.photobleaching" in v.margins
    assert "perturbation.saturation" in v.margins


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
    assert not any(
        f.code == "perturbation.trap_heating_unowned" for f in v.findings
    )


def test_trap_on_raises_the_unowned_heating_finding():
    """docs/06 D6 assigns trap heating to lens 7, which has no heating check and
    is not getting one (ungated by decision, 2026-08-19). A named risk still
    has to reach the reader, so lens 5 says it rather than assuming someone
    else did."""
    v = evaluate(_setup(trap_on=True))
    f = next(f for f in v.findings if f.code == "perturbation.trap_heating_unowned")
    assert f.severity == "info"
    assert "ungated by decision" in f.message


def test_trap_heating_notice_does_not_change_the_grade():
    with_trap = evaluate(_setup(trap_on=True))
    without = evaluate(_setup())
    assert with_trap.feasibility == without.feasibility


# ------------------------------------------- spectral overlap coupling ----


def test_local_chain_without_a_coupling_is_reported_as_assumed():
    """The bare-field chain has no spectra, so it sets the overlap to 1 -- the
    line treated as if it sat on the absorption peak. Honest about it."""
    v = evaluate(_setup(excitation_coupling=None))
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any("overlap" in a for a in v.assumed_inputs)


def test_supplying_the_coupling_restores_advances():
    v = evaluate(_setup(excitation_coupling=0.5))
    assert v.evidence == "measured"
    assert v.advances is True


def test_coupling_scales_k_ex_and_so_relaxes_the_bleaching_margin():
    """Assuming perfect overlap overstates k_ex, which overstates bleaching:
    the gate comes out stricter than the instrument warrants, not laxer."""
    assumed_perfect = evaluate(_setup(excitation_coupling=1.0))
    real = evaluate(_setup(excitation_coupling=0.5))
    assert (
        real.margins["perturbation.photobleaching"]
        > assumed_perfect.margins["perturbation.photobleaching"]
    )


def test_rates_from_lens_one_need_no_coupling():
    """optics.path.Channel.excitation_rate_per_s already carries the overlap
    weighting, so consuming it is not an assumption."""
    v = evaluate(
        _setup(
            excitation_coupling=None,
            excitation_rate_per_s=350.0,
            emitted_photons_per_s=320.0,
        )
    )
    assert not any("overlap" in a for a in v.assumed_inputs)
    assert v.evidence == "measured"
    assert v.advances is True


# ---------------------------------------------------------- evidence ------


def test_missing_frame_interval_downgrades_evidence():
    v = evaluate(_setup(frame_interval_ms=None))
    assert v.evidence == "assumed"
    assert v.advances is False


def test_fully_specified_setup_advances():
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "PASS"
    assert v.advances is True


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "photo"
    assert d["feasibility_note"]
