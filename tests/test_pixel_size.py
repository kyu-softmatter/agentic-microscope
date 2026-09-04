"""Tests for the recorded pixel-size table (data/pixel_size.yaml).

The table exists because the lab's Micro-Manager ``.cfg`` carries an empty
``PixelSize settings`` block, so ``getPixelSizeUm()`` answers 0.0 and the value
measured in 2025-04 was unreachable from code. These tests hold two things: the
numbers match ``kb/systems/current.md > pixel_size_calibration``, and the
provenance stays honest -- eleven of the twelve cells are the nominal quotient
and are labelled as such, so nothing downstream can mistake arithmetic for a
measurement.
"""

from __future__ import annotations

import pytest

from detection.photometry import effective_pixel_nm
from hardware.microscope import (
    _intermediate_mag_from_label,
    _objective_mag_from_label,
)
from optics.components import pixel_size_table, recorded_pixel_um

#: kb/systems/current.md > pixel_size_calibration, transcribed independently of
#: the YAML so a typo in one does not silently agree with the other.
KB_TABLE = {
    4: {"1x": 1.625, "1.5x": 1.0833},
    10: {"1x": 0.65, "1.5x": 0.43333},
    20: {"1x": 0.32373, "1.5x": 0.21582},
    40: {"1x": 0.1625, "1.5x": 0.10833},
    60: {"1x": 0.10833, "1.5x": 0.07222},
    100: {"1x": 0.065, "1.5x": 0.04333},
}

SENSOR_UM = 6.5  # Kinetix, data/detectors.yaml


@pytest.mark.parametrize("mag", sorted(KB_TABLE))
@pytest.mark.parametrize("inter", [1.0, 1.5])
def test_matches_the_kb_dossier(mag, inter):
    hit = recorded_pixel_um(mag, inter)
    assert hit is not None
    assert hit[0] == pytest.approx(KB_TABLE[mag][f"{inter:g}x"])


def test_sensor_pixel_agrees_with_the_detector_registry():
    from optics.components import detectors

    assert pixel_size_table()["sensor_pixel_um"] == pytest.approx(SENSOR_UM)
    camera = pixel_size_table()["camera"]
    assert detectors()[camera.lower()].pixel_um == pytest.approx(SENSOR_UM)


@pytest.mark.parametrize("mag", [4, 10, 40, 60, 100])
@pytest.mark.parametrize("inter", [1.0, 1.5])
def test_nominal_rows_are_the_quotient_and_say_so(mag, inter):
    """The eleven cells that carry no information, and must not claim to."""
    um, evidence = recorded_pixel_um(mag, inter)
    assert evidence == "nominal"
    assert um * 1000.0 == pytest.approx(
        effective_pixel_nm(SENSOR_UM, 1, mag, inter), rel=1e-4
    )


@pytest.mark.parametrize("inter,nominal_um", [(1.0, 0.325), (1.5, 0.2166667)])
def test_the_20x_is_the_one_row_that_departs(inter, nominal_um):
    """0.39 % low at both intermediate settings -- a real 20.078x objective."""
    um, evidence = recorded_pixel_um(20, inter)
    assert evidence == "measured"
    assert um != pytest.approx(nominal_um, rel=1e-4)
    assert um / nominal_um == pytest.approx(0.9961, abs=5e-4)


def test_exactly_one_row_is_measured():
    """A regression guard on provenance, not on physics.

    If a later edit promotes the nominal rows to ``measured``, an
    ``advances: YES`` appears under numbers nobody measured -- which is the
    failure mode lens 6 (G23-G27) exists to catch.
    """
    table = pixel_size_table()["table"]
    measured = [k for k, row in table.items() if row.get("evidence") == "measured"]
    assert measured == ["20"]


def test_binning_scales_linearly():
    assert recorded_pixel_um(100, 1.0, 2)[0] == pytest.approx(0.13)


def test_absent_combinations_return_none_rather_than_guessing():
    assert recorded_pixel_um(25, 1.0) is None  # no such objective
    assert recorded_pixel_um(20, 2.0) is None  # no such intermediate
    assert recorded_pixel_um(20.5, 1.0) is None  # non-integer magnification


# ---- label parsing: the lab's own strings -----------------------------


@pytest.mark.parametrize(
    "label,mag",
    [
        ("1-Plan Apo LmbdD20 4x", 4.0),
        ("2-Plan Apo LmbdD4 10x", 10.0),
        ("3-Plan Apo LmbdD0.8 20x", 20.0),
        ("4-Apo LmbdS 40x WI", 40.0),
        ("5-Plan Apo LmbdD0.15 60x Oil", 60.0),
        ("6-Plan Apo LmbdD0.13 100x Oil", 100.0),
    ],
)
def test_objective_label_parses_past_the_design_code(label, mag):
    """``LmbdD20`` and ``LmbdD0.13`` carry digits that are not magnifications."""
    assert _objective_mag_from_label(label) == mag


@pytest.mark.parametrize("label", ["1x", "1.0x", "1.5x"])
def test_intermediate_label_parses(label):
    assert _intermediate_mag_from_label(label) is not None


@pytest.mark.parametrize("label", [None, "state 0", "state 1", "unreadable", ""])
def test_unlabelled_intermediate_is_not_parsed_as_a_factor(label):
    """A turret position is not a magnification.

    ``Microscope.pixel_size_um`` then falls back to
    :data:`~hardware.microscope.DEFAULT_INTERMEDIATE_MAG` and says so in its
    provenance; the parser's job is only to refuse to invent a factor from a
    position index.
    """
    assert _intermediate_mag_from_label(label) is None


def test_the_cfg_presets_match_the_recorded_table():
    """The .cfg's 1x block and data/pixel_size.yaml cannot drift apart.

    Two copies of the same number in two files is how a calibration goes stale
    silently, so this reads the .cfg back and compares every preset.
    """
    from pathlib import Path

    from hardware.microscope import _objective_mag_from_label

    cfg = (
        Path(__file__).resolve().parent.parent
        / "config"
        / "micromanager"
        / "single_cam_red_noDMD.cfg"
    )
    lines = cfg.read_text(encoding="utf-8").splitlines()

    objective_of: dict[str, str] = {}
    for line in lines:
        if line.startswith("ConfigPixelSize,") and ",Nosepiece,Label," in line:
            preset = line.split(",")[1]
            objective_of[preset] = line.split(",Label,", 1)[1]

    sizes = {
        line.split(",")[1]: float(line.split(",")[2].split("#")[0])
        for line in lines
        if line.startswith("PixelSize_um,")
    }

    assert sizes, "the .cfg lost its PixelSize block"
    assert set(sizes) == set(objective_of), "a preset is missing one of its two lines"

    for preset, um in sizes.items():
        mag = _objective_mag_from_label(objective_of[preset])
        assert mag is not None, preset
        assert recorded_pixel_um(mag, 1.0)[0] == pytest.approx(um), preset

    # Every objective on the nosepiece is covered, so no position silently
    # falls back to MM's 0.0.
    nosepiece_labels = {
        line.split(",", 3)[3]
        for line in lines
        if line.startswith("Label,Nosepiece,")
    }
    assert set(objective_of.values()) == nosepiece_labels
