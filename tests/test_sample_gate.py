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


# ------------------------------------------------- G15 NA feasibility -----


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


# ------------------------------------------------ G16 working distance -----


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


# --------------------------------------------------- G17 RI mismatch -------


def test_water_objective_in_aqueous_medium_is_index_matched():
    v = evaluate(_setup(objective_kw=WATER_40X, imaging_depth_um=30.0))
    m = v.metrics["geometry.ri_mismatch"]
    assert m["ri_mismatch"] == 0.0
    assert v.margins["geometry.ri_mismatch"] >= 1.0


def test_oil_objective_in_aqueous_medium_warns_beyond_the_screening_depth():
    """0.185 mismatch tolerates ~10 um; 30 um does not."""
    v = evaluate(_setup(imaging_depth_um=30.0))
    assert any(f.code == "geometry.ri_mismatch" and f.severity == "warn" for f in v.findings)
    assert v.margins["geometry.ri_mismatch"] < 1.0


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
    assert (
        water.margins["geometry.ri_mismatch"] > oil.margins["geometry.ri_mismatch"]
    )


# --------------------------------------------- G16b depth in chamber -------


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
    40 um beats G16b's 0.50). That is the hard-gate rule: any HARD check under
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
    """With G17 out of the way, G16b is what decides the grade."""
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


# ------------------------------------------------ G16c near-wall drag -------


def test_wall_drag_bound_reproduces_the_pitfall_table():
    """docs/06 D8 tabulates the Faxen drag penalty for a 4 um bead (a = 2 um).
    G16c must land on the same numbers, or one of the two is wrong."""
    expected = {5.0: 0.290, 10.0: 0.127, 20.0: 0.060, 50.0: 0.023}
    for h, penalty in expected.items():
        v = evaluate(_setup(imaging_depth_um=h, particle_radius_um=2.0))
        m = v.metrics["geometry.wall_drag"]
        assert m["drag_penalty_upper_bound"] == pytest.approx(penalty, abs=5e-4)


def test_a_trap_absorbs_the_wall_drag_so_it_reports_as_info():
    """KH 2026-08-20: measurements are mainly trapped. D8's in-situ
    power-spectrum calibration at the working height returns kappa and the
    wall-corrected drag together, so the bound is reported, not charged."""
    v = evaluate(_setup(imaging_depth_um=5.0, particle_radius_um=2.0, trapped=True))
    assert v.margins["geometry.wall_drag"] == 10.0
    assert v.metrics["geometry.wall_drag"]["trapped"] is True
    assert not any(f.code == "geometry.wall_drag" for f in v.findings)


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


def test_wall_drag_is_skipped_without_a_particle_radius():
    v = evaluate(_setup())
    assert v.metrics["geometry.wall_drag"]["evaluated"] is False
    assert v.status != "BLOCKED"


# ----------------------------------------------------- G18 coverslip -------


def test_coverslip_within_tolerance_passes():
    v = evaluate(_setup(coverslip_actual_um=172.0))
    assert v.margins["geometry.coverslip"] >= 1.0


def test_unmeasured_coverslip_falls_back_to_the_lab_glass_not_the_design():
    """KH 2026-08-20: this lab mounts 170 um, which matches every objective's
    design thickness, so G18 passes on the fallback.

    The fallback still goes through LAB_DEFAULT_COVERSLIP_UM rather than the
    objective's design value. The two coincide today, so this asserts the
    provenance rather than a different number: an objective added later with a
    different design thickness must report a real deviation, not zero.
    """
    v = evaluate(_setup(coverslip_actual_um=None))
    m = v.metrics["geometry.coverslip"]
    assert m["coverslip_actual_um"] == 170.0
    assert m["coverslip_design_um"] == 170.0
    assert m["measured"] is False
    assert v.margins["geometry.coverslip"] == 10.0  # deviation 0


def test_the_nominal_coverslip_still_withholds_advance_on_evidence_alone():
    """G18 passes, but a nominal product thickness is not a micrometer reading,
    so evidence stays assumed and that alone blocks advancing. This is the
    whole remaining cost of an unmeasured coverslip -- the gate itself is
    content."""
    v = evaluate(_setup(coverslip_actual_um=None))
    # PASS, not PASS_WITH_CHANGES: evidence.assumed is an *info* finding, and
    # only fail/warn downgrade the status. This is the two-axis rule doing its
    # job -- status says the physics is sound, evidence says nobody measured it,
    # and advancing needs both.
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert v.advances is False
    assert not any(f.code == "geometry.coverslip" for f in v.findings)


def test_coverslip_beyond_tolerance_warns():
    v = evaluate(_setup(coverslip_actual_um=190.0))
    assert any(f.code == "geometry.coverslip" and f.severity == "warn" for f in v.findings)


def test_unadjusted_correction_collar_warns():
    v = evaluate(_setup(objective_kw={"correction_collar": True}, collar_adjusted=False))
    assert any(
        f.code == "geometry.coverslip" and "collar" in f.message.lower()
        for f in v.findings
    )


def test_adjusted_correction_collar_does_not_warn():
    v = evaluate(_setup(objective_kw={"correction_collar": True}, collar_adjusted=True))
    assert not any(
        f.code == "geometry.coverslip" and "no record" in f.message for f in v.findings
    )


# ------------------------------------------------- G19 count in field ------


def test_count_in_field_is_skipped_without_a_concentration():
    v = evaluate(_setup())
    assert v.metrics["geometry.count_in_field"]["evaluated"] is False


def test_count_in_field_reports_a_count_when_supplied():
    v = evaluate(
        _setup(concentration_per_ml=1e9, field_width_um=100.0, field_height_um=100.0)
    )
    m = v.metrics["geometry.count_in_field"]
    assert m["evaluated"] is True
    assert m["expected_count"] == 50.0  # 1e9/mL x 100x100x5 um
    # No emission wavelength to size a DOF, so the whole column is used and
    # the count is flagged as an upper bound.
    assert m["axial_extent_source"] == "imaging_depth"


def test_count_uses_the_depth_of_field_when_an_emission_line_is_known():
    """The count feeds lens 6's G11, so the axial extent must not be the
    imaging depth by default -- validity/setup.py::resolved_n_particles would
    inherit an overestimate of statistical power."""
    common = dict(concentration_per_ml=1e9, field_width_um=100.0, field_height_um=100.0)
    column = evaluate(_setup(**common)).metrics["geometry.count_in_field"]
    dof = evaluate(_setup(emission_nm=668.0, **common)).metrics["geometry.count_in_field"]

    assert dof["axial_extent_source"] == "depth_of_field"
    # 100x NA 1.45 oil at 668 nm is a ~0.48 um DOF against a 5 um imaging depth
    assert dof["axial_extent_um"] == pytest.approx(0.482, abs=0.01)
    assert dof["expected_count"] < column["expected_count"] / 10


def test_an_explicit_observed_slab_wins_over_both_fallbacks():
    v = evaluate(
        _setup(
            emission_nm=668.0,
            observed_slab_um=1.0,
            concentration_per_ml=1e9,
            field_width_um=100.0,
            field_height_um=100.0,
        )
    )
    m = v.metrics["geometry.count_in_field"]
    assert m["axial_extent_source"] == "explicit"
    assert m["expected_count"] == pytest.approx(10.0)  # 1e9/mL x 100x100x1 um


def test_dense_suspension_warns_about_overlap():
    v = evaluate(
        _setup(
            concentration_per_ml=1e13,
            field_width_um=100.0,
            field_height_um=100.0,
            emission_nm=520.0,
        )
    )
    assert any(f.code == "geometry.count_in_field" and f.severity == "warn" for f in v.findings)


def test_count_in_field_never_blocks_the_gate():
    """INFO kind: a missing concentration must not stop G15-G18."""
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
