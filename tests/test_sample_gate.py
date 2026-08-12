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


# ----------------------------------------------------- G18 coverslip -------


def test_coverslip_within_tolerance_passes():
    v = evaluate(_setup(coverslip_actual_um=172.0))
    assert v.margins["geometry.coverslip"] >= 1.0


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


def test_defaulted_sample_index_downgrades_evidence():
    v = evaluate(_setup(n_sample=None))
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any("refractive index" in a for a in v.assumed_inputs)


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
