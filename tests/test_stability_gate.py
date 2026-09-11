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
        particle_radius_um=0.5,
        delta_density_kg_m3=0.0,  # density-matched by default, so G31 is quiet
        viscosity_pa_s=1.0e-3,
        chamber_sealed=True,
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


def test_a_missing_drift_rate_no_longer_blocks_anything():
    """It was Phase 0's most common refusal and it is gone. G29 needed a
    measured rate, nothing in the repo had one, so every real acquisition
    BLOCKED -- and because Phase 0 is all-or-nothing, that one absent number
    took down G31 and G32, whose inputs were present. Removing the gate
    removed the refusal."""
    v = evaluate(_setup())
    assert v.status != "BLOCKED"
    assert not any("drift_rate" in f.code for f in v.findings)
    assert v.margins["stability.sedimentation"] > 0.0


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


# ---------------- G28 removed 2026-09-10 -------------------------------------
#
# The six tests that exercised `stability.pfs_lock` went with the gate. It
# moved to the hardware execution stage (KH), and not only as a relocation:
# the gate read `PFS in Range` as if it meant "the servo is holding", and
# `hardware/focus.py::FocusAxis.pfs_state` records that that property reports
# the COVERSLIP -- `In Range` is the normal reading for a focused sample. The
# hardware stage asks MMCore's autofocus API instead, which is the servo. So
# the gate was reading the wrong property, and a planning-time gate on a
# runtime state was the wrong shape for it regardless.
# kb/decisions/2026-09-10-g28-moves-to-the-hardware-stage.md


def test_nothing_in_this_lens_gates_pfs_any_more():
    v = evaluate(_setup())
    assert "stability.pfs_lock" not in v.margins
    assert not any(f.code.startswith("stability.pfs") for f in v.findings)


def test_the_setup_no_longer_accepts_the_pfs_flags():
    """They were planning-time stand-ins for a runtime state. Removing the
    fields is what stops a caller asserting a lock the lens cannot see."""
    with pytest.raises(TypeError):
        _setup(pfs_enabled=True)


# ---------------- G29 and G30 removed 2026-09-10 -----------------------------
#
# Axial drift and lateral drift went the way G28 had gone hours earlier, on the
# criterion KH gave when offered the choice of making G30 refuse like G29:
#
#     "실험 중 측정해야한다면 디자인 요소로는 적합하지 않은듯"
#
# Both rates ARE obtainable here -- `config/session/focus_monitor.py` samples
# ZDrive and both cameras several times a second, and most of the beads in
# data/particles.yaml are stuck to the coverslip and serve as lateral
# fiducials -- but obtainable from the ACQUISITION is the wrong timing for a
# gate that judges a PROPOSAL. `compute.drops` is the precedent for that work.
# kb/decisions/2026-09-10-drift-is-not-a-design-element.md
#
# What is tested instead: the two gates are absent, the fields are absent, and
# the half of the question that a plan CAN answer is reported.


def test_neither_drift_gate_exists_any_more():
    v = evaluate(_setup())
    assert "stability.axial_drift" not in v.margins
    assert "stability.lateral_drift" not in v.margins
    assert not any(
        f.code in {"stability.axial_drift", "stability.lateral_drift"}
        for f in v.findings
    )


def test_the_setup_no_longer_accepts_a_drift_rate():
    """The fields are what made a caller able to assert a rate at planning
    time. Removing them is the enforcement; the deleted checks were only the
    consequence."""
    for field in (
        "axial_drift_rate_nm_per_min",
        "lateral_drift_rate_nm_per_min",
        "lateral_tolerance_um",
    ):
        with pytest.raises(TypeError):
            _setup(**{field: 1.0})


def test_the_drift_budget_reports_the_rate_the_run_can_absorb():
    """Duration and depth of field are both planning inputs, so the tolerance
    IS a design quantity even though the rate is not. The 100x oil's 0.375 um
    DOF over 60 min is ~6.26 nm/min for one full DOF -- tighter than any drift
    figure anyone would casually claim, which is the point of reporting it."""
    s = _setup(duration_min=60.0)
    expected = s.resolved_dof_um * 1000.0 / 60.0
    n = evaluate(s).metrics["stability.drift_budget"]
    assert n["axial_rate_for_one_dof_nm_per_min"] == pytest.approx(expected, rel=1e-3)
    assert n["axial_rate_for_one_dof_nm_per_min"] == pytest.approx(6.26, rel=1e-2)
    assert n["axial_rate_for_half_dof_nm_per_min"] == pytest.approx(
        expected / 2, rel=1e-3
    )
    assert n["gated"] is False


def test_the_drift_budget_tightens_with_duration():
    short = evaluate(_setup(duration_min=30.0))
    long_ = evaluate(_setup(duration_min=120.0))
    assert (
        short.metrics["stability.drift_budget"]["axial_rate_for_one_dof_nm_per_min"]
        == pytest.approx(
            4
            * long_.metrics["stability.drift_budget"][
                "axial_rate_for_one_dof_nm_per_min"
            ],
            rel=1e-3,
        )
    )


def test_the_drift_budget_is_visible_rather_than_graded():
    """An INFO check whose severity is "ok" is dropped from findings by every
    gate in this repo. This one must be read, so it reports "info"."""
    v = evaluate(_setup())
    f = next(f for f in v.findings if f.code == "stability.drift_budget")
    assert f.severity == "info"
    assert f.kind == "info"
    assert v.margins["stability.drift_budget"] == 10.0


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


def test_drift_downgrades_evidence_unconditionally():
    """The entry cannot be retired by any planning input, so this lens never
    reports `measured`. Deliberate: drift is the dominant bias on a long
    acquisition and planning it well does not discharge it -- the run's own
    frames do."""
    v = evaluate(_setup())
    assert v.evidence == "assumed"
    assert any("drift" in a for a in v.assumed_inputs)


def test_unsealed_chamber_without_a_rate_downgrades_evidence():
    v = evaluate(_setup(chamber_sealed=False))
    assert v.evidence == "assumed"
    assert any("evaporation rate" in a for a in v.assumed_inputs)


def test_a_fully_specified_setup_passes_but_cannot_advance():
    """It used to advance. Since the drift entry became unconditional it
    cannot, and that is the intended reading: a long acquisition clears lens 8
    on physics and still waits on a measurement taken while it runs."""
    v = evaluate(_setup())
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert v.advances is False


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
    # Lens 6 reads `evidence` off the upstream verdicts, and lens 8's is now
    # permanently "assumed". The interop has to hold with that, not despite it.
    assert stability_verdict.evidence == "assumed"

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
