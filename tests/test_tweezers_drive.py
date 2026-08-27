"""Tests for hardware.tweezers_drive -- spec -> plan -> command sequence.

Pure computation, no hardware and no socket. The repo's own drive spec is
exercised directly, so a change to it that breaks the plan fails here.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hardware.tweezers_drive import (
    build_pattern,
    command_sequence,
    load_spec,
    plan,
)
from hardware.tweezers_patterns import PatternError

REPO = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO / "config" / "tweezers" / "active-microrheology-drive.yaml"


@pytest.fixture
def spec():
    return load_spec(SPEC_PATH)


@pytest.fixture
def ready(spec):
    """The same spec with the microscope-PC facts filled in, so the downstream
    logic can be tested without waiting for them."""
    s = copy.deepcopy(spec)
    s["project"] = r"C:\tweez\projects\microrheology.twp"
    s["trapping_range"] = {"half_width_um": 50.0, "half_height_um": 50.0}
    s["field_calibration"] = {
        "objective": s["calibration"]["objective"],
        "taken": "2026-08-26",
    }
    return s


# ---- the repo's spec as it stands --------------------------------------


def test_the_repo_spec_loads_and_plans(spec):
    p = plan(spec)
    assert p.name == "active-microrheology-drive"
    assert p.trap == "Probe"
    assert len(p.pattern) == 2000


def test_an_unrecorded_calibration_objective_blocks(ready):
    """um coordinates only mean something against the objective the Tweez GUI
    was calibrated with, and neither Tweez calibration is readable over TCP."""
    ready["calibration"]["objective"] = None
    p = plan(ready)
    assert any("calibration.objective" in b for b in p.blockers)
    assert not p.advances


def test_the_calibration_block_reaches_the_report(ready):
    report = plan(ready).report()
    assert "4-Apo LmbdS 40x WI" in report
    assert "NOT verifiable from here" in report


def test_the_repo_spec_is_blocked_on_its_open_facts(spec):
    p = plan(spec)
    assert not p.advances
    assert p.range_status == "BLOCKED"
    assert any("range check" in b for b in p.blockers)
    assert any("wait states" in b for b in p.blockers)
    assert any("field_calibration.objective" in b for b in p.blockers)


# ---- the two calibrations are not interchangeable ----------------------


def test_a_field_calibration_from_another_objective_blocks(ready):
    """LOAD_PROJECT restores the GUI calibration but not the AOD field
    response -- that one is System Manager state (manual pp.28-32 vs p.65)."""
    ready["field_calibration"]["objective"] = "5-Plan Apo LmbdD0.15 60x Oil"
    p = plan(ready)
    assert not p.advances
    assert any("trapping-field calibration was taken with" in b for b in p.blockers)


def test_the_report_separates_the_two_calibrations(ready):
    report = plan(ready).report()
    assert "travels in the project" in report
    assert "field cal does NOT" in report


# ---- per-objective project templates ----------------------------------


def test_a_per_objective_project_mapping_selects_by_calibration_objective(ready):
    """"load the project for the magnification I want" -- one template per
    objective, each carrying that objective's GUI calibration."""
    ready["project"] = {
        "4-Apo LmbdS 40x WI": r"C:\tweez\40x.twp",
        "5-Plan Apo LmbdD0.15 60x Oil": r"C:\tweez\60x.twp",
    }
    p = plan(ready)
    assert p.project == r"C:\tweez\40x.twp"
    assert p.advances


def test_a_missing_template_for_the_calibrated_objective_blocks(ready):
    ready["project"] = {"5-Plan Apo LmbdD0.15 60x Oil": r"C:\tweez\60x.twp"}
    p = plan(ready)
    assert not p.advances
    assert any("no project template for objective" in b for b in p.blockers)


def test_a_scalar_project_path_still_works(ready):
    assert plan(ready).project == r"C:\tweez\projects\microrheology.twp"


def test_range_check_blocked_not_passed_when_unrecorded(spec):
    """An unverified extent must not read as OK -- silently clipped points are
    the exact failure mode."""
    assert plan(spec).range_status == "BLOCKED"


def test_range_check_fails_loudly_when_the_pattern_is_too_big(ready):
    ready["trapping_range"] = {"half_width_um": 2.0, "half_height_um": 2.0}
    p = plan(ready)
    assert p.range_status == "FAIL"
    assert "silently clipped" in p.range_note
    assert not p.advances


def test_plan_advances_once_the_template_and_range_are_supplied(ready):
    p = plan(ready)
    assert p.range_status == "OK"
    assert p.blockers == ()
    assert p.advances


# ---- slowdown routes ---------------------------------------------------


def test_every_route_reaches_the_target_speed(ready):
    for kind in ("wait_states", "dwell", "switching_rate"):
        ready["drive"]["slowdown"] = kind
        p = plan(ready)
        assert p.effective_speed_um_s() == pytest.approx(30.0, rel=2e-3), kind


def test_wait_states_route_leaves_the_file_and_the_clock_alone(ready):
    ready["drive"]["slowdown"] = "wait_states"
    p = plan(ready)
    assert len(p.emitted_pattern()) == len(p.pattern)
    assert p.switching_rate_hz() == 100_000
    assert p.wait_states == round(p.slowdown_factor) - 1


def test_dwell_route_grows_the_file_and_leaves_the_clock_alone(ready):
    ready["drive"]["slowdown"] = "dwell"
    p = plan(ready)
    assert len(p.emitted_pattern()) == len(p.pattern) * round(p.slowdown_factor)
    assert p.switching_rate_hz() == 100_000
    assert p.wait_states == 0


def test_switching_rate_route_drops_the_clock_and_leaves_the_file_alone(ready):
    ready["drive"]["slowdown"] = "switching_rate"
    p = plan(ready)
    assert len(p.emitted_pattern()) == len(p.pattern)
    assert p.switching_rate_hz() < 300  # ~236 Hz
    assert p.wait_states == 0


def test_switching_rate_route_reports_the_cost_to_other_traps(ready):
    ready["drive"]["slowdown"] = "switching_rate"
    p = plan(ready)
    cost = next(r for r in p.routes if r.kind == "switching_rate").cost
    assert "every other" in cost and "refresh" in cost


def test_only_wait_states_is_flagged_as_gui_only(ready):
    p = plan(ready)
    settable = {r.kind: r.python_settable for r in p.routes}
    assert settable == {"wait_states": False, "dwell": True, "switching_rate": True}


def test_an_unknown_slowdown_kind_is_refused(ready):
    ready["drive"]["slowdown"] = "magic"
    with pytest.raises(PatternError, match="drive.slowdown must be one of"):
        plan(ready)


def test_a_target_faster_than_the_hardware_is_refused(ready):
    ready["drive"]["target_speed_um_s"] = 1e9
    with pytest.raises(PatternError, match="already runs at"):
        plan(ready)


def test_a_nonpositive_target_is_refused(ready):
    ready["drive"]["target_speed_um_s"] = 0
    with pytest.raises(PatternError, match="must be positive"):
        plan(ready)


# ---- spec -> pattern ---------------------------------------------------


def test_build_pattern_dispatches_on_shape():
    patt = build_pattern({"pattern": {"shape": "circle", "radius_um": 5, "n_points": 12}})
    assert len(patt) == 12


def test_unknown_shape_is_refused():
    with pytest.raises(PatternError, match="unknown pattern shape"):
        build_pattern({"pattern": {"shape": "spiral"}})


def test_a_typo_in_a_parameter_name_is_refused_not_ignored():
    """Silently falling back to a generator default would change the trajectory
    without changing the spec, and the spec is the record."""
    with pytest.raises(PatternError, match="unknown parameter"):
        build_pattern(
            {"pattern": {"shape": "circle", "radius_um": 5, "n_points": 12, "rdius": 9}}
        )


def test_the_walk_seed_survives_the_spec_round_trip(spec):
    a = plan(spec).pattern
    b = plan(load_spec(SPEC_PATH)).pattern
    assert a.points == b.points


# ---- command sequence --------------------------------------------------


def test_command_sequence_is_in_dependency_order(ready):
    lines = command_sequence(plan(ready), r"C:\p\drive.tpf")
    kinds = [line.split()[0] for line in lines]
    assert kinds == [
        "LOAD_PROJECT",
        "BEAM_SET_PARAMS",
        "LOAD_PATTERN",
        "TRAP_ASSIGN_PATTERN",
        "TRAP_POSITION",
        "TRAP_STRENGTH",
        "TRAP_ON",
    ]


def test_command_sequence_never_arms_the_laser(ready):
    lines = command_sequence(plan(ready), r"C:\p\drive.tpf")
    assert not any("LASER_ON" in line for line in lines)


def test_load_project_is_omitted_when_no_template_is_given(spec):
    lines = command_sequence(plan(spec), r"C:\p\drive.tpf")
    assert not any(line.startswith("LOAD_PROJECT") for line in lines)


def test_file_first_flips_the_load_pattern_arguments(ready):
    p = plan(ready)
    normal = next(x for x in command_sequence(p, "C:/p/d.tpf") if x.startswith("LOAD_PATTERN"))
    flipped = next(
        x for x in command_sequence(p, "C:/p/d.tpf", file_first=True)
        if x.startswith("LOAD_PATTERN")
    )
    assert normal == "LOAD_PATTERN Drive C:/p/d.tpf"
    assert flipped == "LOAD_PATTERN C:/p/d.tpf Drive"


def test_names_with_spaces_are_quoted(ready):
    ready["trap"] = "Probe Trap"
    lines = command_sequence(plan(ready), r"C:\my patterns\drive.tpf")
    assert 'TRAP_ON "Probe Trap"' in lines
    assert any('"C:\\my patterns\\drive.tpf"' in line for line in lines)


def test_switching_rate_sent_matches_the_chosen_route(ready):
    ready["drive"]["slowdown"] = "switching_rate"
    p = plan(ready)
    line = next(x for x in command_sequence(p, "d.tpf") if x.startswith("BEAM_SET_PARAMS"))
    assert line.split()[1] == f"{p.switching_rate_hz():.0f}"
