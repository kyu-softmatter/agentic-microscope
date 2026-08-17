"""Tests for stability.gate.evaluate (lens 8) -- mirrors the other gate tests'
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

import pytest

from optics.components import find_objective
from stability.gate import evaluate
from stability.setup import CONVENE_DURATION_MIN, StabilitySetup


def _setup(**overrides) -> StabilitySetup:
    defaults = dict(
        duration_min=60.0,
        objective=find_objective("100x-Oil"),
        emission_nm=520.0,
        axial_drift_rate_nm_per_min=1.0,
        pfs_enabled=True,
        pfs_in_range=True,
        particle_radius_um=0.5,
        delta_density_kg_m3=0.0,  # density-matched by default, so G31 is quiet
        viscosity_pa_s=1.0e-3,
        chamber_sealed=True,
        lateral_drift_rate_nm_per_min=1.0,
        lateral_tolerance_um=1.0,
        vibration_measured=True,
    )
    defaults.update(overrides)
    return StabilitySetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_a_duration():
    v = evaluate(_setup(duration_min=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.duration" for f in v.findings)


def test_blocked_without_a_depth_of_field():
    v = evaluate(_setup(objective=None, emission_nm=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.depth_of_field" for f in v.findings)


def test_blocked_without_a_measured_drift_rate():
    """Nothing in kb/calibrations/ records one, and a guessed rate would decide
    the gate wrongly in whichever direction the guess leaned."""
    v = evaluate(_setup(axial_drift_rate_nm_per_min=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.axial_drift_rate" for f in v.findings)


def test_blocked_without_sedimentation_inputs():
    v = evaluate(_setup(delta_density_kg_m3=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.settling_inputs" for f in v.findings)


def test_depth_of_field_can_be_supplied_directly():
    v = evaluate(_setup(objective=None, emission_nm=None, depth_of_field_um=0.375))
    assert v.status != "BLOCKED"


def test_depth_of_field_comes_from_the_objective_registry():
    """100x oil, n=1.518, NA 1.45, 520 nm -> n lambda / NA^2 = 0.375 um."""
    s = _setup()
    assert s.resolved_dof_um == pytest.approx(0.375, rel=1e-2)


# ---------------------------------------------------- G28 PFS lock -------


def test_unrecorded_focus_maintenance_fails():
    v = evaluate(_setup(pfs_enabled=None))
    assert v.status == "FAIL"
    assert any(f.code == "stability.pfs_lock" for f in v.findings)


def test_pfs_on_but_range_unrecorded_fails():
    """docs/06 D7: the on state alone cannot tell a held focus from a wandered
    one, and the archive has sessions of exactly that shape."""
    v = evaluate(_setup(pfs_in_range=None))
    assert v.status == "FAIL"
    msg = next(f.message for f in v.findings if f.code == "stability.pfs_lock")
    assert "without being locked" in msg


def test_pfs_on_but_out_of_range_fails():
    v = evaluate(_setup(pfs_in_range=False))
    assert v.status == "FAIL"
    msg = next(f.message for f in v.findings if f.code == "stability.pfs_lock")
    assert "Out of Range" in msg


def test_pfs_off_on_a_long_acquisition_fails():
    v = evaluate(_setup(pfs_enabled=False, pfs_in_range=None, duration_min=120.0))
    assert v.status == "FAIL"


def test_pfs_off_on_a_short_acquisition_is_allowed():
    v = evaluate(
        _setup(pfs_enabled=False, pfs_in_range=None, duration_min=5.0)
    )
    assert v.margins["stability.pfs_lock"] == 10.0


def test_pfs_on_and_locked_passes():
    v = evaluate(_setup())
    assert v.margins["stability.pfs_lock"] == 10.0


# ------------------------------------------------- G29 axial drift -------


def test_small_drift_stays_inside_the_focus_budget():
    v = evaluate(_setup(axial_drift_rate_nm_per_min=1.0, duration_min=60.0))
    assert v.margins["stability.axial_drift"] >= 1.0


def test_drift_beyond_half_the_depth_of_field_fails():
    """5 nm/min for 60 min = 0.3 um against a 0.1875 um budget."""
    v = evaluate(_setup(axial_drift_rate_nm_per_min=5.0, duration_min=60.0))
    assert v.status == "FAIL"
    assert any(
        f.code == "stability.axial_drift" and f.severity == "fail" for f in v.findings
    )


def test_drift_scales_with_duration():
    short = evaluate(_setup(duration_min=30.0))
    long_ = evaluate(_setup(duration_min=120.0))
    assert (
        long_.metrics["stability.axial_drift"]["total_drift_um"]
        == pytest.approx(4 * short.metrics["stability.axial_drift"]["total_drift_um"])
    )


# ----------------------------------------------- G31 sedimentation -------


def test_density_matched_suspension_does_not_trigger_sedimentation():
    v = evaluate(_setup(delta_density_kg_m3=0.0))
    assert v.margins["stability.sedimentation"] == 10.0


def test_polystyrene_in_water_over_an_hour_warns():
    """98 um of settling against a 0.375 um depth of field -- 260x over, so the
    margin is ~0.004 rather than merely short."""
    v = evaluate(_setup(delta_density_kg_m3=50.0, duration_min=60.0))
    assert any(
        f.code == "stability.sedimentation" and f.severity == "warn"
        for f in v.findings
    )
    m = v.metrics["stability.sedimentation"]
    assert m["settling_distance_um"] == pytest.approx(98.07, rel=1e-3)
    assert v.margins["stability.sedimentation"] == pytest.approx(0.004, abs=5e-4)


def test_sedimentation_message_says_the_population_changed():
    v = evaluate(_setup(delta_density_kg_m3=50.0))
    msg = next(f.message for f in v.findings if f.code == "stability.sedimentation")
    assert "not the population that was there at the start" in msg


def test_creaming_is_reported_as_upward():
    v = evaluate(_setup(delta_density_kg_m3=-50.0))
    msg = next(f.message for f in v.findings if f.code == "stability.sedimentation")
    assert "creams upward" in msg


def test_settling_past_the_chamber_height_is_flagged():
    v = evaluate(_setup(delta_density_kg_m3=50.0, chamber_height_um=20.0))
    assert v.metrics["stability.sedimentation"]["leaves_chamber"] is True
    msg = next(f.message for f in v.findings if f.code == "stability.sedimentation")
    assert "reach the wall" in msg


# ------------------------------------------------- G32 evaporation ------


def test_sealed_chamber_does_not_evaporate():
    v = evaluate(_setup(chamber_sealed=True))
    assert v.margins["stability.evaporation"] == 10.0


def test_unsealed_long_acquisition_without_a_rate_warns():
    v = evaluate(_setup(chamber_sealed=False, duration_min=120.0))
    assert any(
        f.code == "stability.evaporation" and f.severity == "warn" for f in v.findings
    )


def test_unsealed_short_acquisition_is_tolerated():
    v = evaluate(_setup(chamber_sealed=False, duration_min=5.0))
    assert v.margins["stability.evaporation"] == 10.0


def test_measured_evaporation_within_the_limit_passes():
    v = evaluate(
        _setup(
            chamber_sealed=False,
            duration_min=30.0,
            evaporation_rate_ul_per_hour=1.0,
            sample_volume_ul=100.0,
        )
    )
    assert v.margins["stability.evaporation"] >= 1.0


def test_measured_evaporation_past_the_limit_warns():
    v = evaluate(
        _setup(
            chamber_sealed=False,
            duration_min=120.0,
            evaporation_rate_ul_per_hour=2.0,
            sample_volume_ul=20.0,
        )
    )
    m = v.metrics["stability.evaporation"]
    assert m["evaporated_fraction"] == pytest.approx(0.2)
    assert m["concentration_factor"] == pytest.approx(1.25)
    assert v.margins["stability.evaporation"] < 1.0


# --------------------------------------------- vibration / convening ----


def test_unmeasured_vibration_is_reported_not_passed_silently():
    v = evaluate(_setup(vibration_measured=False))
    f = next(f for f in v.findings if f.code == "stability.vibration")
    assert f.severity == "info"
    assert "absence of evidence" in f.message


def test_vibration_notice_does_not_change_the_grade():
    with_notice = evaluate(_setup(vibration_measured=False))
    without = evaluate(_setup(vibration_measured=True))
    assert with_notice.feasibility == without.feasibility


def test_convening_threshold_is_reported():
    long_ = evaluate(_setup(duration_min=CONVENE_DURATION_MIN + 1))
    short = evaluate(_setup(duration_min=CONVENE_DURATION_MIN - 1))
    assert long_.metrics["stability.convening"]["convenes"] is True
    assert short.metrics["stability.convening"]["convenes"] is False


def test_checks_still_run_below_the_convening_threshold():
    """The threshold is reported, not enforced: settling does not switch on at
    30 minutes."""
    v = evaluate(_setup(duration_min=10.0, delta_density_kg_m3=50.0))
    assert v.metrics["stability.convening"]["convenes"] is False
    assert v.margins["stability.sedimentation"] < 1.0


# ---------------------------------------------------------- evidence ------


def test_unmeasured_vibration_downgrades_evidence():
    v = evaluate(_setup(vibration_measured=False))
    assert v.evidence == "assumed"
    assert v.advances is False


def test_unmeasured_lateral_drift_downgrades_evidence():
    v = evaluate(_setup(lateral_drift_rate_nm_per_min=None))
    assert v.evidence == "assumed"
    assert any("lateral drift" in a for a in v.assumed_inputs)


def test_unsealed_chamber_without_a_rate_downgrades_evidence():
    v = evaluate(_setup(chamber_sealed=False))
    assert v.evidence == "assumed"
    assert any("evaporation rate" in a for a in v.assumed_inputs)


def test_fully_specified_setup_advances():
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "PASS"
    assert v.advances is True


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "stability"
    assert d["feasibility_note"]


# ------------------------------------------- interop with lens 6 ----------


def test_lens_6_can_review_this_lens_verdict():
    """Lens 8 is conditional, so lens 6 accepts it as an extra beyond the
    standing set rather than requiring it."""
    from validity.gate import evaluate as validity_evaluate
    from validity.setup import STANDING_LENSES, ValiditySetup

    class _V:
        def __init__(self):
            self.status = "PASS"
            self.evidence = "measured"
            self.margins = {}
            self.findings = []
            self.metrics = {}

    stability_verdict = evaluate(_setup(delta_density_kg_m3=50.0))
    assert stability_verdict.status == "PASS_WITH_CHANGES"

    upstream = {name: _V() for name in STANDING_LENSES}
    upstream["stability"] = stability_verdict
    v = validity_evaluate(
        ValiditySetup(
            intended_quantity="diffusion",
            target_relative_error=0.05,
            upstream=upstream,
            n_particles=200.0,
            n_frames=2000,
            pixel_size_measured=True,
            analysis_script="D:/codes/msd.m",
        )
    )
    # The sedimentation bias is a bias-kind finding, so it lands in the ledger.
    assert "stability.sedimentation" in v.metrics["validity.bias_ledger"]["uncorrected_codes"]
