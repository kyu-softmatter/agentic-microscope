"""Tests for the two offline-checkable parts of the microscope-PC scripts.

Neither script can be run against hardware from here, but the parts that decide
whether a command is *safe to issue* are pure arithmetic, and those are exactly
the parts that must not be wrong:

    config/piezo/settle_waveform_units.py    predicts where the stage will go
                                             under each reading of the sample
                                             unit, and refuses a probe whose
                                             destination is unbounded
    config/micromanager/make_single_cam_cfg.py  derives a one-camera config that
                                             gets loaded against real hardware

The `config/` scripts are not a package, so they are loaded by path the way
tests/test_advances_rule.py loads its modules.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SETTLE = _load("config/piezo/settle_waveform_units.py", "_settle_waveform_units")
SINGLECAM = _load("config/micromanager/make_single_cam_cfg.py", "_make_single_cam")


# ---- the sample-unit hypotheses ----------------------------------------


def _by_key(key: str):
    return next(h for h in SETTLE.hypotheses() if h.key == key)


def test_absolute_picometres_reads_the_value_as_a_position():
    assert _by_key("absolute-pm").predict_um(5.0e6, 300.0) == pytest.approx(5.0)


def test_an_offset_is_relative_to_where_the_axis_already_is():
    h = _by_key("offset-pm")
    assert h.predict_um(5.0e6, 300.0) == pytest.approx(305.0)
    assert h.predict_um(0.0, 300.0) == pytest.approx(300.0)


def test_a_dac_code_scales_the_value_across_the_whole_travel():
    h = _by_key("code-2^24")
    assert h.predict_um(0.0, 300.0) == pytest.approx(0.0)
    assert h.predict_um(2**23, 300.0) == pytest.approx(300.0)
    assert h.predict_um(2**24, 300.0) == pytest.approx(0.0)  # wraps


def test_a_code_wraps_which_is_what_explains_the_314_um_excursion():
    """3.0e8 -- "300 um of picometres" -- overflows a 24-bit code, and wrapping
    puts consecutive samples anywhere in the travel. That is the shape that was
    actually observed on 2026-08-27."""
    h = _by_key("code-2^24")
    predicted = h.predict_um(3.0e8, 300.0)
    assert 0.0 < predicted < 600.0
    assert predicted == pytest.approx(600.0 * ((3.0e8 % 2**24) / 2**24))
    assert abs(predicted - 300.0) > 100.0  # nowhere near the requested position


def test_every_reading_is_a_distinct_prediction_for_the_first_probe():
    """The first probe has to separate all six readings on its own, or the
    ladder cannot converge in one move."""
    first = SETTLE.LADDER[0]
    predictions = sorted(
        h.predict_um(first, 300.0) for h in SETTLE.hypotheses()
    )
    gaps = [b - a for a, b in zip(predictions, predictions[1:])]
    assert all(gap > SETTLE.TOLERANCE_UM for gap in gaps), predictions


# ---- the safety screen -------------------------------------------------


def test_a_probe_whose_destination_leaves_the_travel_is_refused():
    hs = SETTLE.hypotheses()
    # An offset of 400 um from 300 um is 700 um, past the 600 um travel.
    ok, why = SETTLE.screen(hs, 4.0e8, 300.0)
    assert not ok
    assert "offset-pm" in why and "outside travel" in why


def test_eliminating_the_offending_reading_makes_the_probe_issuable():
    """This is what makes the ladder adaptive: a probe refused now becomes safe
    once an earlier probe has ruled the overshooting reading out."""
    hs = SETTLE.hypotheses()
    assert not SETTLE.screen(hs, 4.0e8, 300.0)[0]
    _by_key_in(hs, "offset-pm").alive = False
    assert SETTLE.screen(hs, 4.0e8, 300.0)[0]


def _by_key_in(hs, key):
    return next(h for h in hs if h.key == key)


def test_the_whole_ladder_is_issuable_with_every_reading_still_in_play():
    """If a probe needed a prior elimination the plan would say so; today none
    of them does, and a change to the ladder that breaks this should be seen."""
    hs = SETTLE.hypotheses()
    for value in SETTLE.LADDER:
        ok, why = SETTLE.screen(hs, value, 300.0)
        assert ok, f"{value}: {why}"


def test_a_dead_reading_does_not_veto_a_probe():
    hs = SETTLE.hypotheses()
    for h in hs:
        h.alive = False
    assert SETTLE.screen(hs, 9.9e9, 300.0)[0]


def test_predictions_sitting_on_an_end_of_travel_are_flagged():
    assert "BOTTOM" in SETTLE.limit_note(0.0)
    assert "TOP" in SETTLE.limit_note(600.0)
    assert SETTLE.limit_note(300.0) == ""
    assert "BOTTOM" in SETTLE.limit_note(SETTLE.MARGIN_UM - 0.1)


def test_the_limits_themselves_are_allowed_only_flagged():
    """0 and 600 um are the controller's own calibrated range, and "absolute
    picometres" necessarily maps small values to the bottom -- so refusing the
    limits would refuse the sharpest probe in the ladder."""
    hs = SETTLE.hypotheses()
    ok, _ = SETTLE.screen(hs, 0.0, 300.0)
    assert ok
    assert SETTLE.limit_note(_by_key("absolute-pm").predict_um(0.0, 300.0))


# ---- the script's own gates --------------------------------------------


def test_z_is_refused_outright(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["settle", "--channel", "3"])
    assert SETTLE.main() == 2
    assert "channel 3 is Z" in capsys.readouterr().err


def test_moving_without_the_unlock_code_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["settle", "--move"])
    assert SETTLE.main() == 2
    assert "needs --unlock" in capsys.readouterr().err


def test_plan_only_opens_no_device_so_it_runs_anywhere(monkeypatch, capsys):
    """The vendor DLL cannot load on this machine at all, so a plan that needed
    it would be uncheckable until someone was standing at the instrument."""
    monkeypatch.setattr(sys, "argv", ["settle", "--channel", "1"])
    assert SETTLE.main() == 0
    out = capsys.readouterr().out
    assert "PLAN ONLY" in out and "no device is opened" in out


# ---- the one-camera config ---------------------------------------------


PARENT_LINES = [
    "# Generated by Configurator",
    "Property,Core,Initialize,0",
    "Device,Kinetix_blue,PVCAM,Camera-1",
    "Device,Kinetix_red,PVCAM,Camera-2",
    "Device,XYStage,NikonTi2,XYStage",
    "Property,Core,Camera,Kinetix_red",
    "Property,Core,AutoShutter,1",
]


def _parent(tmp_path: Path, eol: str = "\n") -> Path:
    path = tmp_path / "parent.cfg"
    path.write_bytes(eol.join(PARENT_LINES).encode())
    return path


def _settings(data: bytes, eol: bytes = b"\n") -> list[str]:
    return [
        line.strip().decode()
        for line in data.split(eol)
        if line.strip() and not line.strip().startswith(b"#")
    ]


def test_keeping_blue_drops_red_and_hands_it_the_core_camera(tmp_path):
    derived, edits = SINGLECAM.derive(_parent(tmp_path), "Kinetix_blue")
    settings = _settings(derived)
    assert "Device,Kinetix_blue,PVCAM,Camera-1" in settings
    assert not any("Kinetix_red" in line for line in settings)
    assert "Property,Core,Camera,Kinetix_blue" in settings
    assert any(e.startswith("removed") for e in edits)


def test_keeping_red_is_a_one_line_derivation_because_it_already_owns_core(tmp_path):
    """The parent already names Kinetix_red, so nothing about Core,Camera
    changes. Reporting that as an edit is what made --check call a correct file
    UNEXPECTED."""
    derived, edits = SINGLECAM.derive(_parent(tmp_path), "Kinetix_red")
    settings = _settings(derived)
    assert not any("Kinetix_blue" in line for line in settings)
    assert "Property,Core,Camera,Kinetix_red" in settings
    assert sum(1 for e in edits if e.startswith("changed")) == 0
    assert any("unchanged" in e for e in edits)


def test_nothing_but_the_camera_lines_is_touched(tmp_path):
    parent = _parent(tmp_path)
    derived, _ = SINGLECAM.derive(parent, "Kinetix_blue")
    before, after = _settings(parent.read_bytes()), _settings(derived)
    for line in before:
        if "Kinetix" not in line:
            assert line in after


def test_line_endings_are_preserved_because_this_repo_syncs_through_box(tmp_path):
    derived, _ = SINGLECAM.derive(_parent(tmp_path, eol="\r\n"), "Kinetix_blue")
    assert b"\r\n" in derived
    assert b"\n" not in derived.replace(b"\r\n", b"")


def test_an_unknown_camera_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        SINGLECAM.derive(_parent(tmp_path), "Kinetix_green")


def test_the_check_passes_on_the_real_dual_camera_config():
    """The artifact that actually gets loaded against hardware."""
    parent = REPO / "config/micromanager/DMD_dualcam_LUNF.cfg"
    for keep in ("Kinetix_blue", "Kinetix_red"):
        derived, _ = SINGLECAM.derive(parent, keep)
        assert SINGLECAM.check(parent, derived, keep) == 0, keep
