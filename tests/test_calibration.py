"""Tests for calibration.disk_bandwidth -- no hardware, no pymmcore-plus needed."""

from __future__ import annotations

import pytest

from calibration.disk_bandwidth import measure_write_bandwidth


def test_measures_a_positive_bandwidth(tmp_path):
    result = measure_write_bandwidth(
        tmp_path, total_bytes=8 * 1024 * 1024, chunk_bytes=1024 * 1024
    )
    assert result.bytes_written == 8 * 1024 * 1024
    assert result.seconds > 0
    assert result.mb_per_s > 0


def test_cleans_up_the_probe_file(tmp_path):
    measure_write_bandwidth(tmp_path, total_bytes=1024 * 1024)
    assert list(tmp_path.iterdir()) == []


def test_rejects_a_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        measure_write_bandwidth(tmp_path / "does-not-exist", total_bytes=1024)


def test_rejects_non_positive_size(tmp_path):
    with pytest.raises(ValueError):
        measure_write_bandwidth(tmp_path, total_bytes=0)
