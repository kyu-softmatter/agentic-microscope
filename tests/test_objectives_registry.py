"""Tests for the objective registry (data/objectives.yaml) and the plumbing
that lets lens 4 consume it.

Values are the nosepiece recorded in kb/systems/current.md > objectives,
verified 2026-08-10 against the Nikon catalogue and 2026-08-11 against the
barrel engravings.
"""

from __future__ import annotations

import pytest

from optics.components import find_objective, objective_keys, objectives
from sample.gate import evaluate
from sample.setup import SampleSetup


def test_all_six_nosepiece_objectives_are_registered():
    assert objective_keys() == ("4x", "10x", "20x", "40x-WI", "60x-Oil", "100x-Oil")


def test_keys_are_in_magnification_order():
    mags = [objectives()[k.lower()].magnification for k in objective_keys()]
    assert mags == sorted(mags)


@pytest.mark.parametrize(
    "key,na,immersion,wd_um",
    [
        ("4x", 0.20, "air", 20000),
        ("10x", 0.45, "air", 4000),
        ("20x", 0.80, "air", 800),
        ("40x-WI", 1.25, "water", 160),
        ("60x-Oil", 1.42, "oil", 150),
        ("100x-Oil", 1.45, "oil", 130),
    ],
)
def test_recorded_specs(key, na, immersion, wd_um):
    obj = find_objective(key)
    assert obj is not None
    assert obj.na == pytest.approx(na)
    assert obj.immersion == immersion
    assert obj.wd_um == pytest.approx(wd_um)


def test_lookup_is_case_insensitive():
    assert find_objective("100X-OIL") is find_objective("100x-oil")


def test_lookup_by_label_also_works():
    """objectives() is keyed by label too, so a dossier label resolves."""
    assert find_objective("6-Plan Apo LmbdD0.13 100x Oil") is find_objective("100x-Oil")


def test_unknown_objective_is_none():
    assert find_objective("200x-Oil") is None


def test_every_na_is_marked_verified():
    """All six were cross-checked twice; an unverified NA would downgrade
    every lens 4 verdict to evidence: assumed."""
    for key in objective_keys():
        assert find_objective(key).verified_na is True


def test_only_the_40x_wi_has_a_correction_collar():
    with_collar = [k for k in objective_keys() if find_objective(k).correction_collar]
    assert with_collar == ["40x-WI"]


def test_the_40x_wi_working_distance_is_the_conservative_end():
    """The catalogue gives 0.2-0.16 mm, collar dependent. G16 is a hard gate,
    so the registry records the shorter end -- budgeting against 200 um would
    pass configurations that fail in practice."""
    assert find_objective("40x-WI").wd_um == 160


# ------------------------------------------------- the plumbing itself -----


def test_registry_objective_drives_the_lens_4_gate():
    v = evaluate(
        SampleSetup(
            objective=find_objective("100x-Oil"),
            imaging_depth_um=5.0,
            n_sample=1.333,
            coverslip_actual_um=170.0,
        )
    )
    assert v.status == "PASS"
    assert v.evidence == "measured"
    assert v.metrics["geometry.working_distance"]["wd_um"] == 130


def test_oil_and_water_objectives_disagree_straight_from_the_registry():
    """The lens 1 / lens 4 conflict, with no hand-entered numbers."""
    common = dict(imaging_depth_um=30.0, n_sample=1.333, coverslip_actual_um=170.0)
    oil = evaluate(SampleSetup(objective=find_objective("100x-Oil"), **common))
    water = evaluate(
        SampleSetup(objective=find_objective("40x-WI"), collar_adjusted=True, **common)
    )
    assert oil.metrics["geometry.ri_mismatch"]["ri_mismatch"] == pytest.approx(0.185)
    assert water.metrics["geometry.ri_mismatch"]["ri_mismatch"] == 0.0
    assert water.margins["geometry.ri_mismatch"] > oil.margins["geometry.ri_mismatch"]


def test_air_objectives_are_badly_mismatched_against_aqueous_media():
    """n=1.0 vs 1.333 is a 0.333 mismatch, worse than oil's 0.185 -- the dry
    objectives are the wrong tool for looking into water, not the safe one."""
    v = evaluate(
        SampleSetup(
            objective=find_objective("20x"),
            imaging_depth_um=30.0,
            n_sample=1.333,
            coverslip_actual_um=170.0,
        )
    )
    assert v.metrics["geometry.ri_mismatch"]["ri_mismatch"] == pytest.approx(0.333)
    assert v.margins["geometry.ri_mismatch"] < 1.0


def test_low_mag_objectives_have_ample_working_distance():
    v = evaluate(
        SampleSetup(
            objective=find_objective("4x"),
            imaging_depth_um=100.0,
            n_sample=1.333,
            coverslip_actual_um=170.0,
        )
    )
    assert v.margins["geometry.working_distance"] == 10.0  # 20000/100, clamped
