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
    )
    defaults.update(overrides)
    return StabilitySetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_a_duration():
    v = evaluate(_setup(duration_min=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.duration" for f in v.findings)


def test_a_missing_depth_of_field_reports_rather_than_blocks():
    """It was a Phase 0 refusal until 2026-09-10. Only `drift_budget` needs the
    DOF now, and it says so itself -- blocking the settling and evaporation
    reports for it was the all-or-nothing pattern this review removed."""
    v = evaluate(_setup(objective=None, emission_nm=None, delta_density_kg_m3=50.0))
    assert v.status == "REPORT"
    f = next(f for f in v.findings if f.code == "stability.drift_budget")
    assert "without both a depth of field and a duration" in f.message
    assert v.metrics["stability.sedimentation"]["settling_velocity_um_per_s"] > 0


def test_a_missing_drift_rate_no_longer_blocks_anything():
    """It was Phase 0's most common refusal and it is gone. G29 needed a
    measured rate, nothing in the repo had one, so every real acquisition
    BLOCKED -- and because Phase 0 is all-or-nothing, that one absent number
    took down G31 and G32, whose inputs were present. Removing the gate
    removed the refusal."""
    v = evaluate(_setup())
    assert v.status == "REPORT"
    assert not any("drift_rate" in f.code for f in v.findings)
    assert "stability.sedimentation" in v.metrics


def test_duration_is_the_only_blocking_input_left():
    """Everything a plan can be missing is now reported by the check that
    needed it. Duration survives because every quantity here is a rate against
    it, and the convening comparison is to it."""
    from stability.gate import _missing_inputs

    assert [f.code for f in _missing_inputs(StabilitySetup())] == [
        "missing.duration"
    ]


def test_depth_of_field_can_be_supplied_directly():
    v = evaluate(_setup(objective=None, emission_nm=None, depth_of_field_um=0.375))
    assert v.status == "REPORT"
    assert v.metrics["stability.drift_budget"]["depth_of_field_um"] == 0.375


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
#
# REPORTS, DOES NOT GATE, since 2026-09-10 (KH): "침강 상승 속도와 평형에
# 도달하는 시간 정도만 계산하고 인포로 남겨두자." The old gate compared a whole
# run's free settling against the depth of field and so called every real bead
# INFEASIBLE -- 5 um polystyrene in water moves 41 um/min against 0.375 um --
# including the experiments that work, because a TRAPPED bead does not settle
# (gravity is 0.032 pN against the trap's own 9.56 pN axial force at 100 mW, so
# 0.34% of the axial budget -- a ratio that needs no kappa_z, since both
# displacements divide by it) and the lens has
# no `trapped` field to tell the two apart. The free-settling case is lens 4's
# G19, which assumes the settled state; this reports when it arrives.


def test_sedimentation_is_a_report_not_a_gate():
    v = evaluate(_setup(delta_density_kg_m3=50.0, duration_min=60.0))
    f = next(f for f in v.findings if f.code == "stability.sedimentation")
    assert f.severity == "info"
    assert f.kind == "info"
    assert v.margins["stability.sedimentation"] == 10.0


def test_sedimentation_reports_the_stokes_velocity():
    """5 um polystyrene, a = 2.5 um, drho 50, water: 0.681 um/s."""
    v = evaluate(_setup(particle_radius_um=2.5, delta_density_kg_m3=50.0))
    m = v.metrics["stability.sedimentation"]
    assert m["settling_velocity_um_per_s"] == pytest.approx(0.681, rel=1e-2)
    assert m["settling_velocity_um_per_min"] == pytest.approx(40.86, rel=1e-2)
    assert m["direction"] == "settles"


def test_sedimentation_reports_the_time_to_equilibrium():
    """The equilibrium of a settling suspension is the floor, and the chamber
    height sets the clock: 100 um at 0.681 um/s is 2.4 min."""
    v = evaluate(
        _setup(
            particle_radius_um=2.5,
            delta_density_kg_m3=50.0,
            chamber_height_um=100.0,
            duration_min=60.0,
        )
    )
    m = v.metrics["stability.sedimentation"]
    assert m["time_to_equilibrium_min"] == pytest.approx(2.45, rel=1e-2)
    assert m["equilibrium_before_end"] is True
    assert m["duration_over_equilibrium_time"] == pytest.approx(24.5, rel=1e-2)


def test_the_time_to_equilibrium_needs_a_chamber_height():
    """Without one there is no distance to fall, so the clock is absent rather
    than guessed -- and the velocity is still reported."""
    v = evaluate(_setup(delta_density_kg_m3=50.0, chamber_height_um=None))
    m = v.metrics["stability.sedimentation"]
    assert "time_to_equilibrium_min" not in m
    assert m["settling_velocity_um_per_s"] > 0
    assert "no clock" in next(
        f.message for f in v.findings if f.code == "stability.sedimentation"
    )


def test_a_run_shorter_than_the_equilibration_time_says_so():
    """Then G19's settled-state premise does not hold yet, which is the one
    thing this report exists to tell lens 4."""
    v = evaluate(
        _setup(
            particle_radius_um=0.5,
            delta_density_kg_m3=50.0,
            chamber_height_um=100.0,
            duration_min=10.0,
        )
    )
    m = v.metrics["stability.sedimentation"]
    assert m["equilibrium_before_end"] is False
    assert "still in transit" in next(
        f.message for f in v.findings if f.code == "stability.sedimentation"
    )


def test_creaming_is_reported_as_upward():
    v = evaluate(_setup(delta_density_kg_m3=-50.0, chamber_height_um=100.0))
    msg = next(f.message for f in v.findings if f.code == "stability.sedimentation")
    assert "creams upward" in msg
    assert "reaches the top" in msg


def test_density_matched_suspension_reports_exactly_zero():
    v = evaluate(_setup(delta_density_kg_m3=0.0))
    m = v.metrics["stability.sedimentation"]
    assert m["settling_velocity_um_per_s"] == 0.0
    assert m["direction"] == "neither"


def test_missing_settling_inputs_report_rather_than_block():
    """They used to be a Phase 0 refusal, which took the evaporation report
    down with them. Each check now owns its own absent input."""
    v = evaluate(_setup(delta_density_kg_m3=None))
    assert v.status == "REPORT"
    f = next(f for f in v.findings if f.code == "stability.sedimentation")
    assert f.severity == "info"
    assert "particle radius" in f.message
    assert "stability.evaporation" in v.metrics


# ------------------------------------------------- G32 evaporation ------
#
# REPORTS, DOES NOT GATE, since 2026-09-10 (KH). Sealing is declarable; an
# evaporation rate is not. The old gate returned a stand-in margin of 0.5 when
# it had no rate -- a number invented to mean "not quantified", which graded
# HARD and blocked `advances` on an acquisition nobody had measured.


def test_evaporation_is_a_report_not_a_gate():
    v = evaluate(_setup(chamber_sealed=False, duration_min=120.0))
    f = next(f for f in v.findings if f.code == "stability.evaporation")
    assert f.severity == "info"
    assert f.kind == "info"
    assert v.margins["stability.evaporation"] == 10.0


def test_no_stand_in_margin_survives_anywhere_in_this_lens():
    """The 0.5 was the last invented number here. Every margin is now the
    INFO maximum, because nothing is graded."""
    v = evaluate(_setup(chamber_sealed=False, duration_min=120.0))
    assert set(v.margins.values()) == {10.0}


def test_a_sealed_chamber_is_reported_as_answered():
    v = evaluate(_setup(chamber_sealed=True))
    f = next(f for f in v.findings if f.code == "stability.evaporation")
    assert "declared sealed" in f.message
    assert v.metrics["stability.evaporation"]["chamber_sealed"] is True


def test_an_unquantified_rate_is_said_to_be_unquantified_not_small():
    v = evaluate(_setup(chamber_sealed=False, duration_min=120.0))
    msg = next(f.message for f in v.findings if f.code == "stability.evaporation")
    assert "UNQUANTIFIED -- not small" in msg


def test_a_measured_rate_is_reported_as_arithmetic():
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


# --------------------------------------------------------- convening ----
#
# ---------------- vibration removed 2026-09-10 -------------------------------
#
# Two tests went with the check. It reported that vibration had no measurement
# channel, and the argument for keeping it was that the drag calibration IS a
# channel -- a coverslip-stuck bead's PSD in the same 520 fps stream. KH:
# "현미경의 모든 부속이 진동 테이블 위에 있어서 카메라와 샘플이 함께 흔들림.
# 구분 할 방법이 없음." Every part of the microscope sits on the same isolation
# table, so camera and sample move together; an image shows only their RELATIVE
# motion, and common-mode motion of a rigid assembly cancels out of it. There is
# no channel to build, and the physics -- not the timing -- is why.
#
# The contrast with drift is the part worth keeping: drift is differential
# expansion in the path between objective and holder, so it does NOT cancel,
# which is why `drift_budget` survives. See check_drift_budget's action text.


def test_nothing_in_this_lens_mentions_vibration_any_more():
    v = evaluate(_setup())
    assert not any("vibration" in f.code for f in v.findings)
    assert not any("vibration" in a for a in v.assumed_inputs)
    assert "stability.vibration" not in v.margins


def test_the_setup_no_longer_accepts_a_vibration_flag():
    with pytest.raises(TypeError):
        _setup(vibration_measured=True)


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
    assert v.metrics["stability.sedimentation"]["settling_velocity_um_per_s"] > 0


# ---------------------------------------------------------- evidence ------


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


def test_this_lens_neither_advances_nor_refuses():
    """A reporting section does neither, so `advances` is None and not False --
    False would read as a refusal it has no gate to base on. Same shape lens 5
    took the same day.

    ⚠ Note what that cost: while this lens still graded, the unconditional
    drift entry pinned `evidence` to assumed and so pinned `advances` to False,
    which is how drift blocked a long acquisition. It cannot block anything
    now. The entry stays so the bias is visible; lens 6 is the only place left
    that can stop on it."""
    v = evaluate(_setup())
    assert v.status == "REPORT"
    assert v.feasibility == "N/A"
    assert v.evidence == "assumed"
    assert v.advances is None
    assert v.passed is True
    assert v.to_dict()["reporting_only"] is True


def test_nothing_in_this_lens_is_gradeable():
    """The invariant `evaluate` asserts. If a gradeable check comes back, that
    is a decision to re-litigate, not a refactor."""
    from stability.checks import BIAS, CHECKS, HARD, SOFT

    assert not [c for c in CHECKS if c.kind in (HARD, SOFT, BIAS)]


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "stability"
    assert d["feasibility"] == "N/A"
    # Not empty: GRADE_NOTES carries an explicit N/A entry, so a consumer
    # cannot mistake "not graded" for a failed lookup.
    assert "reporting section" in d["feasibility_note"]


# ------------------------------------------- interop with lens 6 ----------


def test_lens_6_can_review_this_lens_verdict():
    """Lens 8 is conditional, so lens 6 accepts it as an extra beyond the
    standing set rather than requiring it.

    ⚠ AND AS OF 2026-09-10 NOTHING FROM LENS 8 REACHES LENS 6 AT ALL. G23's
    ledger collects `bias`-kind findings, and this lens has none left -- both
    of its bias gates became reports. Its drift and evaporation notes live in
    `assumed_inputs`, and `_evaluate_one` does not read upstream
    `assumed_inputs`: only the multi-quantity aggregation at
    `validity/gate.py:307` unions them, and that is across lens 6's OWN
    per-quantity verdicts, not from upstream.

    This test pins the gap rather than hiding it. **It is lens 6's to close,
    not this lens's** -- lens 6 is reviewed last by E2, and reaching into it
    from here would be the coupling that review exists to check. Recorded in
    kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md."""
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
    assert stability_verdict.status == "REPORT"
    # Lens 6 reads `evidence` off the upstream verdicts, and lens 8's is now
    # permanently "assumed". The interop has to hold with that, not despite it.
    assert stability_verdict.evidence == "assumed"

    upstream = {name: _V() for name in STANDING_LENSES}
    upstream["stability"] = stability_verdict
    v = validity_evaluate(
        ValiditySetup(
            intended_quantity="diffusion",
            upstream=upstream,
            pixel_size_measured=True,
            analysis_script="D:/codes/msd.m",
        )
    )
    # Nothing from lens 8 reaches the ledger any more -- no bias-kind findings.
    assert not [
        c
        for c in v.metrics["validity.bias_ledger"]["uncorrected_codes"]
        if c.startswith("stability.")
    ]
    # And the drift note does NOT travel either: lens 6's single-quantity path
    # does not read upstream assumed_inputs. Pinned as the open gap it is.
    assert not any("drift" in a for a in v.assumed_inputs)
