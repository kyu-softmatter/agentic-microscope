"""Tests for calibration.ram_capture against pymmcore-plus's bundled demo camera.

Skipped entirely if pymmcore-plus isn't installed, or no working Micro-
Manager device-adapter bundle is found -- same reasoning as
test_calibration_mm_live.py. Validates the capture/flush plumbing, not the
lab's real PVCAM/Kinetix adapter or true concurrent dual-camera capture --
see calibration.ram_capture's module docstring for what that leaves
unconfirmed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pymmcore_plus")

from calibration import mm_live, ram_capture  # noqa: E402


@pytest.fixture(scope="module")
def demo_core():
    try:
        return mm_live.connect(None)
    except Exception as exc:
        pytest.skip(f"no usable Micro-Manager device-adapter install: {exc}")


def test_capture_burst_to_ram_gets_every_requested_frame(demo_core):
    result = ram_capture.capture_burst_to_ram(demo_core, "Camera", 10)
    assert result.n_requested == 10
    assert result.n_captured == 10
    assert result.dropped == 0
    assert result.frames.shape == (10, 512, 512)
    assert result.achieved_fps > 0


def test_capture_burst_to_ram_rejects_non_positive_count(demo_core):
    with pytest.raises(ValueError):
        ram_capture.capture_burst_to_ram(demo_core, "Camera", 0)


def test_flush_to_disk_round_trips_the_captured_frames(demo_core, tmp_path):
    import numpy as np

    result = ram_capture.capture_burst_to_ram(demo_core, "Camera", 5)
    out = tmp_path / "burst.npy"
    flushed = ram_capture.flush_to_disk(result.frames, out)

    assert flushed.bytes_written == result.frames.nbytes
    assert flushed.mb_per_s > 0
    reloaded = np.load(out)
    np.testing.assert_array_equal(reloaded, result.frames)
