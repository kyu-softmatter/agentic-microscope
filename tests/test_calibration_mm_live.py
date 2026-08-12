"""Tests for calibration.mm_live against pymmcore-plus's bundled demo camera.

Skipped entirely if pymmcore-plus isn't installed, or if no working
Micro-Manager device-adapter bundle is found (``mmcore install``) -- the
project's other tests deliberately don't require either, since this repo
targets an offline work PC (see README) and only calibration/ needs live MM.

This validates the pymmcore-plus plumbing (connect / list cameras / ROI /
property lookup / snap), not the lab's real PVCAM/Kinetix adapter -- see
calibration/mm_live.py's module docstring for what that leaves unconfirmed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pymmcore_plus")

from calibration import mm_live  # noqa: E402


@pytest.fixture(scope="module")
def demo_core():
    try:
        return mm_live.connect(None)
    except Exception as exc:
        pytest.skip(f"no usable Micro-Manager device-adapter install: {exc}")


def test_list_cameras_finds_the_demo_camera(demo_core):
    assert "Camera" in mm_live.list_cameras(demo_core)


def test_roi_height_matches_the_demo_cameras_default(demo_core):
    assert mm_live.roi_height(demo_core, "Camera") == 512


def test_readout_time_candidates_finds_the_demo_cameras_property(demo_core):
    hits = mm_live.readout_time_candidates(demo_core, "Camera")
    assert any(c.name == "ReadoutTime" for c in hits)


def test_snap_mean_intensity_returns_a_plausible_pixel_value(demo_core):
    mean = mm_live.snap_mean_intensity(demo_core, "Camera")
    assert 0 <= mean <= 65535
