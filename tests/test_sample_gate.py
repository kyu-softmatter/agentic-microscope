"""Tests for sample.gate.evaluate (lens 4) -- mirrors
tests/test_compute_gate.py's split: Phase 0 refusals are right, Phase 1/2
aggregation is right.
"""

from __future__ import annotations

import pytest

from optics.components import Objective
from sample.gate import evaluate
from sample.setup import SampleSetup

# The two objectives that matter for the RI story, from
# kb/systems/current.md > objectives.
OIL_100X = dict(
    label="6-Plan Apo LmbdD0.13 100x Oil",
    magnification=100.0,
    na=1.45,
    immersion="oil",
    wd_um=130.0,
    verified_na=True,
)
WATER_40X = dict(
    label="4-Apo LmbdS 40x WI",
    magnification=40.0,
    na=1.25,
    immersion="water",
    wd_um=200.0,
    verified_na=True,
)


def _setup(objective_kw=None, **overrides) -> SampleSetup:
    obj_kw = dict(OIL_100X)
    obj_kw.update(objective_kw or {})
    defaults = dict(
        objective=Objective(**obj_kw),
        imaging_depth_um=5.0,
        n_sample=1.333,
        coverslip_actual_um=170.0,
    )
    defaults.update(overrides)
    return SampleSetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_an_imaging_depth():
    v = evaluate(_setup(imaging_depth_um=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.imaging_depth" for f in v.findings)


def test_blocked_without_a_working_distance():
    v = evaluate(_setup(objective_kw={"wd_um": None}))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.working_distance" for f in v.findings)


def test_blocked_without_an_na():
    v = evaluate(_setup(objective_kw={"na": 0.0}))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.na" for f in v.findings)


def test_atps_blocks_rather_than_using_the_water_default():
    """kb/expertise/sample-medium-refractive-index.md excludes ATPS from the
    default. The exclusion is enforced here, not remembered."""
    v = evaluate(_setup(multiphase=True, n_sample=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "unmodellable.multiphase" for f in v.findings)


def test_atps_with_per_phase_indices_is_judgeable():
    v = evaluate(_setup(multiphase=True, phase_n={"dextran_rich": 1.348, "peg_rich": 1.339}))
    assert v.status != "BLOCKED"


def test_birefringent_sample_blocks():
    """5CB: n_o ~1.53, n_e ~1.71. One isotropic index is meaningless."""
    v = evaluate(_setup(birefringent=True))
    assert v.status == "BLOCKED"
    assert any(f.code == "unmodellable.birefringent" for f in v.findings)


# ------------------------------------------------- L4.1 NA feasibility -----


def test_na_feasibility_fails_for_a_water_objective_used_dry():
    v = evaluate(_setup(objective_kw={**WATER_40X, "immersion": "air"}))
    assert v.status == "FAIL"
    assert v.bottleneck == "geometry.na_feasibility"
    assert any(f.code == "geometry.na_feasibility" and f.severity == "fail" for f in v.findings)


def test_na_feasibility_passes_for_the_100x_in_oil():
    v = evaluate(_setup())
    assert v.margins["geometry.na_feasibility"] > 1.0
    assert v.metrics["geometry.na_feasibility"]["na_ceiling_ratio"] == 1.047


def test_na_feasibility_does_not_drag_the_grade_for_a_correct_high_na_setup():
    """A high-NA immersion objective sits just under its medium's index by
    design (1.45/1.518 = 1.047). Grading on that ratio would make every
    correct setup TIGHT, so a pass returns MAX_MARGIN and the real
    bottleneck stays visible."""
    v = evaluate(_setup(objective_kw=WATER_40X, imaging_depth_um=30.0))
    assert v.margins["geometry.na_feasibility"] == 10.0
    assert v.bottleneck != "geometry.na_feasibility"
    assert v.feasibility == "ROUTINE"


# ------------------------------------------------ L4.2 working distance -----


def test_working_distance_fails_when_the_depth_exceeds_it():
    v = evaluate(_setup(imaging_depth_um=500.0))
    assert v.status == "FAIL"
    assert any(f.code == "geometry.working_distance" and f.severity == "fail" for f in v.findings)


def test_coverslip_excess_eats_into_the_working_distance():
    """Depth 30 um keeps both margins under MAX_MARGIN, so the clamp cannot
    hide the difference: 130/30 = 4.33 against (130-80)/30 = 1.67."""
    design = evaluate(_setup(imaging_depth_um=30.0, coverslip_actual_um=170.0))
    thick = evaluate(_setup(imaging_depth_um=30.0, coverslip_actual_um=250.0))
    assert design.margins["geometry.working_distance"] == pytest.approx(4.333, abs=1e-3)
    assert thick.margins["geometry.working_distance"] == pytest.approx(1.667, abs=1e-3)


# --------------------------------------------------- L4.5 RI mismatch -------


def test_water_objective_in_aqueous_medium_is_index_matched():
    v = evaluate(_setup(objective_kw=WATER_40X, imaging_depth_um=30.0))
    m = v.metrics["geometry.ri_mismatch"]
    assert m["ri_mismatch"] == 0.0
    assert v.margins["geometry.ri_mismatch"] >= 1.0


def test_g17_reports_and_no_longer_gates():
    """RETARGETED 2026-09-10. The screening product `depth x dn <= 1.85 um`
    was anchored circularly -- 1.85 IS 10 x 0.185, the checklist trigger
    evaluated at the oil-into-water case -- and the operator has imaged well
    past it. L4.5 is now the mechanical-z to optical-depth converter.
    kb/decisions/2026-09-10-g17-becomes-a-z-to-depth-converter.md
    """
    v = evaluate(_setup(imaging_depth_um=30.0))
    assert v.margins["geometry.ri_mismatch"] == 10.0
    assert not any(
        f.code == "geometry.ri_mismatch" and f.severity in {"warn", "fail"}
        for f in v.findings
    )
    # INFO, but it must still be SAID -- severity "info" reaches findings.
    assert any(
        f.code == "geometry.ri_mismatch" and f.severity == "info" for f in v.findings
    )


def test_g17_converts_z_travel_to_depth_both_ways():
    """A z reading is not a depth. The factor is the same whether the
    objective or the stage moves, because the refraction is at the interface."""
    v = evaluate(_setup(imaging_depth_um=9.0))
    m = v.metrics["geometry.ri_mismatch"]
    assert m["depth_at_this_z_travel_um"] == pytest.approx(7.90, abs=0.01)
    assert m["z_travel_for_this_depth_um"] == pytest.approx(10.25, abs=0.01)


def test_the_depth_window_no_longer_has_a_g17_ceiling():
    """The direct consequence, and the reason this was a conscious choice:
    the oil objective's window was EMPTY only because L4.5 capped it at 10 um
    against L4.4's 13.9 um floor. It is now bounded by reach and extent."""
    v = evaluate(
        _setup(imaging_depth_um=20.0, particle_radius_um=2.475, chamber_height_um=100.0)
    )
    m = v.metrics["geometry.depth_window"]
    assert "L4.5 index mismatch" not in m["upper_bounds_um"]
    assert m["depth_min_um"] == pytest.approx(13.92, abs=0.01)
    assert m["depth_max_um"] == pytest.approx(100.0)


def test_oil_objective_reports_the_axial_scaling_error():
    v = evaluate(_setup(imaging_depth_um=30.0))
    m = v.metrics["geometry.ri_mismatch"]
    assert m["paraxial_focal_shift_ratio"] == 0.8781
    assert m["axial_scaling_error_pct"] == 12.2


def test_shallow_imaging_survives_the_oil_water_mismatch():
    v = evaluate(_setup(imaging_depth_um=5.0))
    assert v.margins["geometry.ri_mismatch"] >= 1.0


def test_water_objective_beats_oil_on_mismatch_at_the_same_depth():
    """The lens 4 verdict that opposes lens 1's collection-efficiency
    preference -- the trade the committee exists to surface."""
    oil = evaluate(_setup(imaging_depth_um=30.0))
    water = evaluate(_setup(objective_kw=WATER_40X, imaging_depth_um=30.0))
    # Since L4.5 became INFO the trade shows in the conversion, not a margin.
    assert oil.metrics["geometry.ri_mismatch"]["axial_scaling_error_pct"] == 12.2
    assert water.metrics["geometry.ri_mismatch"]["axial_scaling_error_pct"] == 0.0


# --------------------------------------------- L4.3 depth in chamber -------


def test_depth_in_chamber_is_skipped_without_a_chamber_height():
    """HARD in character, but a missing chamber height must not BLOCK the gate
    -- the Check is registered with no `requires` precisely so that an absent
    answer skips instead of taking the whole lens down."""
    v = evaluate(_setup())
    assert v.status != "BLOCKED"
    assert v.metrics["geometry.depth_in_chamber"]["evaluated"] is False
    assert v.margins["geometry.depth_in_chamber"] == 10.0


def test_focusing_past_the_chamber_wall_fails_hard():
    """20 um of sample, 40 um focal depth: what comes into focus is the far
    wall. No other lens notices -- stability holds chamber_height_um but spends
    it only on the sedimentation flag.

    Note the status is FAIL even though `bottleneck` names ri_mismatch (0.25 at
    40 um beats L4.3's 0.50). That is the hard-gate rule: any HARD check under
    1.0 forces FAIL regardless of which margin is numerically worst.
    """
    v = evaluate(_setup(imaging_depth_um=40.0, chamber_height_um=20.0))
    assert v.status == "FAIL"
    assert v.margins["geometry.depth_in_chamber"] == pytest.approx(0.5)
    assert any(
        f.code == "geometry.depth_in_chamber" and f.severity == "fail"
        for f in v.findings
    )


def test_the_chamber_can_be_the_bottleneck_on_an_index_matched_objective():
    """With L4.5 out of the way, L4.3 is what decides the grade."""
    v = evaluate(
        _setup(objective_kw=WATER_40X, imaging_depth_um=40.0, chamber_height_um=20.0)
    )
    assert v.status == "FAIL"
    assert v.bottleneck == "geometry.depth_in_chamber"
    assert v.feasibility == "HARD"  # margin 0.5


def test_a_chamber_taller_than_the_focal_depth_passes():
    v = evaluate(_setup(imaging_depth_um=5.0, chamber_height_um=100.0))
    m = v.metrics["geometry.depth_in_chamber"]
    assert m["evaluated"] is True
    assert m["headroom_um"] == pytest.approx(95.0)
    assert v.margins["geometry.depth_in_chamber"] == 10.0  # 100/5, clamped


def test_an_unspaced_mount_says_so_instead_of_skipping_quietly():
    """KH 2026-08-20: this lab's samples usually have no spacer, so there is no
    designed thickness to ask for. That is a different statement from "nobody
    looked it up", and it belongs in findings."""
    v = evaluate(_setup(unspaced_mount=True))
    m = v.metrics["geometry.depth_in_chamber"]
    assert m["evaluated"] is False
    assert m["unspaced_mount"] is True
    f = next(x for x in v.findings if x.code == "geometry.depth_in_chamber")
    assert f.severity == "info"  # visible, but does not touch the grade
    assert "wedge" in f.message
    assert v.status == "PASS"  # info findings do not downgrade status


def test_an_unspaced_height_is_flagged_as_one_preparations_thickness():
    v = evaluate(_setup(imaging_depth_um=5.0, chamber_height_um=20.0, unspaced_mount=True))
    f_ok = v.metrics["geometry.depth_in_chamber"]
    assert f_ok["evaluated"] is True
    assert f_ok["unspaced_mount"] is True
    assert v.margins["geometry.depth_in_chamber"] == pytest.approx(4.0)


def test_focusing_exactly_at_the_far_wall_is_allowed():
    """Imaging the top interface is a real experiment; margin 1.0 says no
    headroom, not impossible."""
    v = evaluate(_setup(imaging_depth_um=20.0, chamber_height_um=20.0))
    assert v.margins["geometry.depth_in_chamber"] == pytest.approx(1.0)
    assert not any(f.code == "geometry.depth_in_chamber" for f in v.findings)


# ------------------------------------------------ L4.4 near-wall drag -------


def test_wall_drag_bound_reproduces_the_pitfall_table():
    """docs/06 D8 tabulates the Faxen drag penalty for a 4 um bead (a = 2 um).
    L4.4 must land on the same numbers, or one of the two is wrong."""
    expected = {5.0: 0.290, 10.0: 0.127, 20.0: 0.060, 50.0: 0.023}
    for h, penalty in expected.items():
        v = evaluate(_setup(imaging_depth_um=h, particle_radius_um=2.0))
        m = v.metrics["geometry.wall_drag"]
        assert m["drag_penalty_upper_bound"] == pytest.approx(penalty, abs=5e-4)


def test_a_trap_absorbs_the_wall_drag_so_it_is_not_charged():
    """KH 2026-08-20: measurements are mainly trapped. D8's in-situ
    power-spectrum calibration at the working height returns kappa and the
    wall-corrected drag together, so the bound is not charged.

    ⚠ "not charged" is not "not reported" -- the last assertion said
    `not any(...)` until 2026-09-10, which is exactly the behaviour that hid
    an 18.3% drag inflation from every verdict. Ungraded and invisible are
    different things, and only the first was intended.
    """
    v = evaluate(_setup(imaging_depth_um=5.0, particle_radius_um=2.0, trapped=True))
    assert v.margins["geometry.wall_drag.trapped"] == 10.0
    assert v.metrics["geometry.wall_drag.trapped"]["trapped"] is True
    assert any(
        f.code == "geometry.wall_drag.trapped" and f.severity == "info"
        for f in v.findings
    )


def test_untrapped_past_the_screening_limit_warns_with_the_bound():
    v = evaluate(_setup(imaging_depth_um=5.0, particle_radius_um=2.0, trapped=False))
    m = v.metrics["geometry.wall_drag"]
    assert m["d_suppression_upper_bound"] == pytest.approx(0.225)
    f = next(x for x in v.findings if x.code == "geometry.wall_drag")
    assert f.severity == "warn"
    assert f.kind == "bias"
    assert "at most" in f.message or "up to" in f.message


def test_untrapped_far_from_the_wall_passes_on_the_bound():
    """The bound falls as 1/h, so depth is the lever. 30 um -> 3.8%."""
    v = evaluate(_setup(imaging_depth_um=30.0, particle_radius_um=2.0, trapped=False))
    assert v.margins["geometry.wall_drag"] == pytest.approx(2.667, abs=1e-3)
    assert not any(f.code == "geometry.wall_drag" for f in v.findings)


def test_inside_the_expansion_domain_no_bound_is_offered():
    """h <= a is outside the Faxen expansion. Returning a big number there
    would be fiction; the check says 'unquantified' instead."""
    v = evaluate(_setup(imaging_depth_um=1.0, particle_radius_um=2.0, trapped=False))
    f = next(x for x in v.findings if x.code == "geometry.wall_drag")
    assert "no bound is available" in f.message
    assert "d_suppression_upper_bound" not in v.metrics["geometry.wall_drag"]


def test_a_trapped_wall_drag_bound_still_reaches_findings():
    """It used `_ok`, and sample/gate.py drops severity "ok" from findings --
    so an 18.3% drag inflation was computed and then discarded into metrics,
    on the strength of an absorption claim the reader never saw (KH,
    2026-09-10). Severity "info" now, so it is reported without being graded
    -- and since 2026-09-11 `kind: BIAS` under a distinct code, so it also
    reaches lens 6's ledger. Severity was only half the fix: the ledger filters
    on the result's KIND, so an INFO-kind result still reached a human reader
    and no gate, on the principal bias of a drag calibration.
    """
    v = evaluate(_setup(particle_radius_um=2.475, imaging_depth_um=9.0, trapped=True))
    f = next(f for f in v.findings if f.code == "geometry.wall_drag.trapped")
    assert f.severity == "info"      # still ungraded HERE
    assert f.kind == "bias"          # but graded by lens 6
    assert v.margins["geometry.wall_drag.trapped"] == 10.0
    # Both numbers have to be in the text, not just the suppression.
    assert "15.5%" in f.message and "18.3%" in f.message


def test_the_trapped_branch_uses_a_distinct_code_from_the_untrapped_one():
    """The registries are keyed by code and the two branches need different
    answers: trapped has an absorption route and belongs in
    `validity.setup.CORRECTIONS`, untrapped has none and belongs in
    `UNCORRECTABLE`. One code could only get one answer."""
    from validity.setup import CORRECTIONS, UNCORRECTABLE

    trapped = evaluate(
        _setup(particle_radius_um=2.0, imaging_depth_um=5.0, trapped=True)
    )
    free = evaluate(_setup(particle_radius_um=2.0, imaging_depth_um=5.0, trapped=False))
    assert "geometry.wall_drag.trapped" in trapped.margins
    assert "geometry.wall_drag" not in trapped.margins
    assert "geometry.wall_drag" in free.margins
    assert "geometry.wall_drag.trapped" not in free.margins

    assert "geometry.wall_drag.trapped" in CORRECTIONS
    assert "geometry.wall_drag.trapped" not in UNCORRECTABLE
    assert "geometry.wall_drag" in UNCORRECTABLE
    assert "geometry.wall_drag" not in CORRECTIONS


def test_the_trapped_bias_does_not_drag_lens_4s_grade_down():
    """MAX_MARGIN and severity "info", so BIAS-kind costs this lens nothing --
    10.0 is never the worst margin and "info" stays out of PASS_WITH_CHANGES.
    The grading moved to lens 6, not into lens 4."""
    v = evaluate(_setup(particle_radius_um=2.475, imaging_depth_um=9.0, trapped=True))
    assert v.bottleneck != "geometry.wall_drag.trapped"


def test_the_trapped_branch_says_the_absorption_can_be_false():
    """The premise holds when gamma comes OUT of a fit and fails when it goes
    IN as 6*pi*eta*a -- which is exactly what a Stokes-drag calibration does.
    A reader who takes `trapped=True` as a clearance is the failure this text
    exists to stop."""
    v = evaluate(_setup(particle_radius_um=2.475, imaging_depth_um=9.0, trapped=True))
    f = next(f for f in v.findings if f.code == "geometry.wall_drag.trapped")
    assert f.action is not None
    assert "PREMISE, NOT A FACT" in f.action
    assert "Stokes-drag" in f.action


def test_wall_drag_is_skipped_without_a_particle_radius():
    v = evaluate(_setup())
    assert v.metrics["geometry.wall_drag"]["evaluated"] is False
    assert v.status != "BLOCKED"


# ------------------------------ G18 removed 2026-09-10 ----------------------
#
# The four tests that graded `geometry.coverslip` went with the gate. What the
# coverslip still does in this lens is asserted below instead, because those
# two effects are the reason removing the margin was safe:
#   * L4.2 keeps subtracting coverslip excess from the working-distance budget
#   * an unmeasured coverslip is still an `assumed_input` and still withholds
#     `advances`
# and the collar condition moved to the evidence axis rather than vanishing.
# kb/decisions/2026-09-10-lens-4-depth-window-and-g18-removed.md


def test_no_check_grades_the_coverslip_any_more():
    v = evaluate(_setup(coverslip_actual_um=190.0))
    assert "geometry.coverslip" not in v.margins
    assert not any(f.code.startswith("geometry.coverslip") for f in v.findings)


def test_coverslip_excess_still_comes_off_the_working_distance():
    """L4.2's budget is the geometric half of what G18 used to cover, and it is
    why the removal loses no reach constraint. 190 um glass against a 170 um
    design costs 20 um of working distance."""
    thin = evaluate(_setup(coverslip_actual_um=170.0))
    thick = evaluate(_setup(coverslip_actual_um=190.0))
    assert (
        thin.metrics["geometry.working_distance"]["free_wd_um"]
        - thick.metrics["geometry.working_distance"]["free_wd_um"]
        == pytest.approx(20.0)
    )


def test_the_nominal_coverslip_still_withholds_advance_on_evidence_alone():
    """Unchanged by the removal: the `assumed_input` lives in sample/gate.py,
    not in the deleted check, so a nominal product thickness still costs
    `advances` while costing no margin."""
    v = evaluate(_setup(coverslip_actual_um=None))
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any("coverslip thickness" in i for i in v.assumed_inputs)


def test_unadjusted_correction_collar_still_withholds_advance():
    """The collar is a knob nothing else records, and the 40x WI is the only
    objective on the nosepiece that has one -- so the condition survives the
    gate's removal, on the evidence axis."""
    v = evaluate(_setup(objective_kw={"correction_collar": True}, collar_adjusted=False))
    assert v.advances is False
    assert any("correction collar" in i for i in v.assumed_inputs)


def test_adjusted_correction_collar_is_not_an_assumption():
    v = evaluate(_setup(objective_kw={"correction_collar": True}, collar_adjusted=True))
    assert not any("correction collar" in i for i in v.assumed_inputs)


# ------------------------------------------------- L4.6 count in field ------


def test_count_in_field_is_skipped_without_a_concentration():
    v = evaluate(_setup())
    assert v.metrics["geometry.count_in_field"]["evaluated"] is False


def test_settled_areal_density_replaces_the_volume_count():
    """REWRITTEN 2026-09-10. L4.6 used to count particles in an observed
    volume, whose default extent was the depth of field -- 377 nm against a
    4950 nm bead. Now it assumes total sedimentation, so there is no slab to
    guess: sigma = c * H.

    1 % w/v of 4.95 um polystyrene is 1.50e8 /mL (the figure
    data/particles.yaml derives independently), and a 100 um column puts all
    of it on the floor: 0.0150 particles/um^2.
    """
    v = evaluate(
        _setup(
            particle_radius_um=2.475,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=0.01,
            density_g_cm3=1.05,
        )
    )
    m = v.metrics["geometry.count_in_field.crowded"]
    assert m["evaluated"] is True
    assert m["concentration_source"] == "solids_w_v"
    assert m["concentration_per_ml"] == pytest.approx(1.50e8, rel=1e-3)
    assert m["settled_areal_density_per_um2"] == pytest.approx(0.0150, rel=1e-2)
    assert "axial_extent_source" not in m, "the slab guess is gone, not renamed"


def test_the_separability_bar_is_the_particle_not_the_optics_for_a_bead():
    """Two 5 um beads stop being resolvable when they touch, at 4.95 um
    centre-to-centre -- three orders above 3x the 219 nm Rayleigh limit. The
    old check compared against the resolution term alone, which is right only
    for a sub-diffraction tracer."""
    v = evaluate(
        _setup(
            particle_radius_um=2.475,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=0.01,
            density_g_cm3=1.05,
        )
    )
    m = v.metrics["geometry.count_in_field.crowded"]
    assert m["required_spacing_basis"] == "particle diameter (touching)"
    assert m["required_spacing_um"] == pytest.approx(4.95)


def test_a_subdiffraction_tracer_falls_back_to_the_resolution_bar():
    """The other side of the same branch: below the PSF, optics binds."""
    v = evaluate(
        _setup(
            particle_radius_um=0.02,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=1e-6,
            density_g_cm3=1.05,
        )
    )
    m = next(
        v.metrics[k] for k in v.metrics if k.startswith("geometry.count_in_field")
    )
    assert "Rayleigh" in m["required_spacing_basis"]


def test_the_minimum_dilution_is_a_floor_not_an_estimate():
    """The whole point of the total-sedimentation model: it is the worst case
    for crowding, so the dilution it demands is a floor and any real
    preparation is sparser. 8.2 particles in the ROI against a target of 1."""
    v = evaluate(
        _setup(
            particle_radius_um=2.475,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=0.01,
            density_g_cm3=1.05,
        )
    )
    m = v.metrics["geometry.count_in_field.crowded"]
    assert m["expected_count"] == pytest.approx(8.17, abs=0.05)
    assert m["min_dilution_factor"] == pytest.approx(8.2, abs=0.1)

    # Applying it lands on the target, and the gate then clears.
    diluted = evaluate(
        _setup(
            particle_radius_um=2.475,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=0.01,
            density_g_cm3=1.05,
            dilution_factor=m["min_dilution_factor"],
        )
    )
    assert diluted.metrics["geometry.count_in_field"]["expected_count"] == pytest.approx(
        1.0, abs=0.05
    )


def test_a_jammed_monolayer_says_the_spacing_is_meaningless():
    """Above ~50% areal coverage the Poisson spacing stops describing
    anything, so the finding says so rather than quoting it."""
    v = evaluate(
        _setup(
            particle_radius_um=2.475,
            chamber_height_um=100.0,
            field_width_um=16.5,
            field_height_um=33.0,
            emission_nm=520.0,
            solids_fraction_w_v=0.05,
            density_g_cm3=1.05,
        )
    )
    assert any(
        f.code == "geometry.count_in_field.jammed" and f.severity == "warn"
        for f in v.findings
    )


def test_count_in_field_never_blocks_the_gate():
    """INFO kind: a missing concentration must not stop L4.1-G18."""
    v = evaluate(_setup(concentration_per_ml=None))
    assert v.status != "BLOCKED"


# ---------------------------------------------------------- evidence ------


def test_defaulted_sample_index_no_longer_downgrades_evidence():
    """1.333 was confirmed 2026-08-19, so the fallback is not an assumption.

    Inverts the original test: leaving n_sample unset used to force
    evidence: assumed. The media the default does not cover still BLOCK in
    Phase 0 (see the multiphase/birefringent tests), which is what keeps this
    from being a silent substitution.
    """
    v = evaluate(_setup(n_sample=None))
    assert v.evidence == "measured"
    assert v.advances is True
    assert not any("refractive index" in a for a in v.assumed_inputs)


def test_unmeasured_coverslip_downgrades_evidence():
    v = evaluate(_setup(coverslip_actual_um=None))
    assert v.evidence == "assumed"
    assert any("coverslip" in a for a in v.assumed_inputs)


def test_unverified_na_downgrades_evidence():
    v = evaluate(_setup(objective_kw={"verified_na": False}))
    assert v.evidence == "assumed"
    assert any("NA" in a for a in v.assumed_inputs)


def test_fully_specified_setup_advances():
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "PASS"
    assert v.advances is True


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "sample"
    assert d["feasibility_note"]
