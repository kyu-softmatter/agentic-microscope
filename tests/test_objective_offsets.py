"""Tests for the objective-offset measurement (config/session/...).

The instrument half cannot run from here. The parts that CAN be wrong without
anyone noticing are the two that these cover:

    * **fiducial localisation** -- a sub-pixel centroid and a phase correlation.
      A whole-pixel answer at 4x is a 1.6 um quantisation on an offset that may
      itself be a few um, so "close enough" is not.
    * **the offset arithmetic and the loop closure** -- which offset is relative
      to what, and whether an offset smaller than the measurement's own
      repeatability gets reported as a number anyway. That last one is the whole
      reason the closure repeat exists.

The `config/` scripts are not a package, so they are loaded by path the way
tests/test_session_scripts.py does it.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
# `measure_objective_offsets` imports its light/camera helpers from `autofocus`,
# a sibling script rather than a module, so the directory has to be importable.
sys.path.insert(0, str(REPO / "config" / "session"))


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


OFF = _load("config/session/measure_objective_offsets.py", "_measure_objective_offsets")


# ---- the registry the sequence drives from --------------------------------

def test_every_objective_has_a_nosepiece_state():
    """The rotation is commanded by state index, and the label's leading digit is
    NOT it -- "6-Plan Apo ... 100x Oil" sits at state 5."""
    pos = OFF.nosepiece_positions()
    assert pos == {"4x": 0, "10x": 1, "20x": 2, "40x-WI": 3, "60x-Oil": 4, "100x-Oil": 5}


def test_immersion_classes_are_the_three_the_hazard_is_about():
    got = {k: OFF.immersion_of(k) for k in OFF.nosepiece_positions()}
    assert got["4x"] == got["10x"] == got["20x"] == "air"
    assert got["40x-WI"] == "water"
    assert got["60x-Oil"] == got["100x-Oil"] == "oil"


# ---- localisation ---------------------------------------------------------

def _bead_field(u, v, size=256, sigma=3.0, amp=3000.0, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    img = 120.0 + 8.0 * rng.standard_normal((size, size))
    img += amp * np.exp(-(((xx - u) ** 2 + (yy - v) ** 2) / (2 * sigma ** 2)))
    return img.astype(np.uint16)


@pytest.mark.parametrize("u,v", [(100.37, 150.62), (64.0, 64.0), (200.9, 33.1)])
def test_centroid_is_sub_pixel(u, v):
    got_u, got_v, diag = OFF.locate_centroid(_bead_field(u, v))
    assert diag["mode"] == "centroid"
    assert got_u == pytest.approx(u, abs=0.05)
    assert got_v == pytest.approx(v, abs=0.05)


def test_centroid_refuses_an_empty_field_instead_of_returning_the_centre():
    """A field with nothing in it must REFUSE. Returning the frame centre would
    read as 'the fiducial is perfectly centred' -- a zero offset that is really
    a missing measurement."""
    from hardware.focus import FocusError

    rng = np.random.default_rng(1)
    flat = (120 + 8 * rng.standard_normal((128, 128))).astype(np.uint16)
    with pytest.raises(FocusError, match="no feature above"):
        OFF.locate_centroid(flat)


def _texture_field(shift_u=0.0, shift_v=0.0, size=256, seed=7):
    """An EXTENDED target -- the regime `correlate` is actually for.

    Band-limited noise standing in for a graticule, an edge or a scratch:
    structure across the whole field rather than one small blob.
    """
    import cv2

    rng = np.random.default_rng(seed)
    base = cv2.GaussianBlur(rng.standard_normal((size, size)).astype(np.float32),
                            (0, 0), 2.0)
    m = np.float32([[1, 0, shift_u], [0, 1, shift_v]])
    shifted = cv2.warpAffine(base, m, (size, size), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REFLECT)
    return (1000.0 + 300.0 * shifted).astype(np.float32)


def test_correlation_recovers_a_known_shift_on_an_extended_target():
    """0.1 px on a field-filling target. This is what `--locate correlate` is
    for: an edge or a graticule, where there is structure everywhere."""
    ref = _texture_field()
    cur = _texture_field(shift_u=7.0, shift_v=-4.0)
    u, v, diag = OFF.locate_by_correlation(cur, ref, 1.0)
    h, w = cur.shape
    assert diag["mode"] == "correlate"
    assert u - w / 2 == pytest.approx(7.0, abs=0.1)
    assert v - h / 2 == pytest.approx(-4.0, abs=0.1)


def test_correlation_on_a_single_small_bead_is_much_worse_than_a_centroid():
    """Measured here, and it decides which `--locate` mode to use.

    `cv2.phaseCorrelate` applies a Hanning window, which attenuates an
    off-centre point feature -- so on a lone bead the correlation lands within
    about half a pixel while `locate_centroid` gets to 0.05 px on the same
    field. At 4x that half-pixel is 0.8 um of parcentric offset, which is not
    negligible against the offsets being measured.

    So: centroid for a bead, correlate for an extended target. The test asserts
    the ORDERING rather than an absolute number, because the exact figure is a
    noise realisation and would make this brittle.
    """
    ref = _bead_field(100.0, 150.0).astype(np.float32)
    cur = _bead_field(107.0, 146.0, seed=2).astype(np.float32)
    h, w = cur.shape

    cu, cv_, _ = OFF.locate_by_correlation(cur, ref, 1.0)
    corr_err = abs((cu - w / 2) - 7.0)
    assert corr_err < 1.0  # still usable, just not precise

    ru, rv, _ = OFF.locate_centroid(_bead_field(100.0, 150.0))
    tu, tv, _ = OFF.locate_centroid(_bead_field(107.0, 146.0, seed=2))
    centroid_err = abs((tu - ru) - 7.0)
    assert centroid_err < corr_err
    assert centroid_err < 0.05


def test_correlation_handles_a_magnification_ratio():
    """The reference is rescaled before correlating, which is what lets a 20x
    frame be matched against a 100x one at all."""
    ref = _bead_field(128.0, 128.0, sigma=3.0).astype(np.float32)
    cur = _bead_field(128.0, 128.0, sigma=6.0, seed=3).astype(np.float32)
    _u, _v, diag = OFF.locate_by_correlation(cur, ref, 2.0)
    assert diag["mag_ratio"] == 2.0


# ---- the offset table ----------------------------------------------------

def _args(**kw):
    base = dict(cfg="x.cfg", locate="centroid", line="GREEN", level=80,
                exposure_ms=20.0, calibrate_xy=None, out=None)
    base.update(kw)
    return argparse.Namespace(**base)


def _rec(key, visit, z, off, pixel_um=0.325, closure=False):
    return {"objective_key": key, "visit_index": visit, "z_focus_um": z,
            "fiducial_offset_um": list(off), "pixel_um": pixel_um,
            "is_loop_closure": closure}


def test_offsets_are_relative_to_the_first_objective(capsys):
    records = [
        _rec("20x", 0, 3000.000, (0.0, 0.0)),
        _rec("100x-Oil", 1, 3012.500, (2.0, -3.0)),
        _rec("20x", 2, 3000.100, (0.1, -0.05), closure=True),
    ]
    rc = OFF.report(records, _args(), ["20x", "100x-Oil"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OFFSETS relative to 20x" in out
    # 3012.5 - 3000.0
    assert "12.500" in out
    # The closure repeat is excluded from the offset table, not offset against.
    assert out.count("100x-Oil") >= 1
    assert "loop closure" in out


def test_loop_closure_is_reported_as_the_uncertainty(capsys):
    records = [
        _rec("20x", 0, 3000.000, (0.0, 0.0)),
        _rec("100x-Oil", 1, 3012.500, (2.0, -3.0)),
        _rec("20x", 2, 3000.400, (0.0, 0.0), closure=True),
    ]
    OFF.report(records, _args(), ["20x", "100x-Oil"])
    out = capsys.readouterr().out
    assert "LOOP CLOSURE" in out
    assert "+0.400" in out
    assert "not a measurement" in out


def test_an_offset_inside_the_closure_is_flagged_not_reported_as_a_number(capsys):
    """The case this check exists for: two lenses that are parfocal to the
    resolution of the measurement. 0.2 um of dz against 0.4 um of closure is
    not a 0.2 um offset."""
    records = [
        _rec("60x-Oil", 0, 3000.000, (0.0, 0.0)),
        _rec("100x-Oil", 1, 3000.200, (0.0, 0.0)),
        _rec("60x-Oil", 2, 3000.400, (0.0, 0.0), closure=True),
    ]
    OFF.report(records, _args(), ["60x-Oil", "100x-Oil"])
    out = capsys.readouterr().out
    assert "within the loop closure" in out
    assert "100x-Oil" in out.split("within the loop closure")[0].split("!!")[-1]


def test_no_closure_repeat_says_there_is_no_error_bar(capsys):
    records = [
        _rec("20x", 0, 3000.000, (0.0, 0.0)),
        _rec("100x-Oil", 1, 3012.500, (2.0, -3.0)),
    ]
    OFF.report(records, _args(), ["20x", "100x-Oil"])
    out = capsys.readouterr().out
    assert "NOT MEASURED" in out
    assert "repeatability has never been measured" in out


def test_a_pass_where_nothing_focused_returns_failure(capsys):
    records = [{"objective_key": "20x", "visit_index": 0, "z_focus_um": None,
                "pixel_um": 0.325}]
    assert OFF.report(records, _args(), ["20x"]) == 1
    assert "no objective yielded a focus" in capsys.readouterr().out


def test_stage_um_appears_only_when_the_xy_transform_was_measured(capsys):
    """Camera um are not stage um -- image y runs down and the rotation has never
    been measured for this path. So a stage number must not appear unless
    --calibrate-xy produced one."""
    plain = [
        _rec("20x", 0, 3000.0, (0.0, 0.0)),
        _rec("100x-Oil", 1, 3010.0, (2.0, -3.0)),
    ]
    OFF.report(plain, _args(), ["20x", "100x-Oil"])
    assert "stage (" not in capsys.readouterr().out

    calibrated = [dict(r) for r in plain]
    # A pure 90-degree rotation with 1 px = 1 um, so the inverse is unambiguous.
    calibrated[1]["xy_calibration"] = {
        "camera_px_to_stage_um": [[0.0, 1.0], [-1.0, 0.0]],
        "stage_to_camera_px_per_um": [[0.0, -1.0], [1.0, 0.0]],
        "step_um": 10.0, "det": 1.0,
    }
    OFF.report(calibrated, _args(calibrate_xy=10.0), ["20x", "100x-Oil"])
    out = capsys.readouterr().out
    assert "stage (" in out
