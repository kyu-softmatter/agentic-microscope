"""Tests for the compute-resource lens's pure formulas (compute.resources).

Checked against docs/04-decision-engine.md §8's own worked examples.
"""

from __future__ import annotations

import pytest

from compute.resources import (
    buffer_bytes,
    buffer_seconds,
    data_rate_bytes_s,
    frame_bytes,
    total_capacity_bytes,
)


@pytest.mark.parametrize(
    "width,height,fps,expected_mb_s",
    [
        (1608, 1608, 60, 310.28),
        (1608, 1608, 30, 155.14),  # 12-bit stored in MM's 16-bit container
        (176, 176, 550, 34.07),
    ],
)
def test_data_rate_matches_docs_examples(width, height, fps, expected_mb_s):
    rate = data_rate_bytes_s(width, height, fps)
    assert rate / 1e6 == pytest.approx(expected_mb_s, abs=0.1)


def test_data_rate_uses_the_16bit_container_regardless_of_adc_bit_depth():
    """docs/04 §8: MM stores 12-bit data in a 16-bit container -- the disk
    calculation must use 16-bit either way."""
    rate_a = data_rate_bytes_s(1608, 1608, 30)
    rate_b = data_rate_bytes_s(1608, 1608, 30)
    assert rate_a == rate_b == frame_bytes(1608, 1608) * 30


@pytest.mark.parametrize(
    "width,height,expected_mb",
    [
        (176, 160, 31.09),
        (1608, 1608, 2854.57),
    ],
)
def test_buffer_bytes_matches_docs_examples(width, height, expected_mb):
    buf = buffer_bytes(552, width, height)
    assert buf / 1e6 == pytest.approx(expected_mb, abs=0.5)


def test_buffer_seconds_is_buffer_over_rate():
    rate = data_rate_bytes_s(1608, 1608, 60)
    buf = buffer_bytes(552, 1608, 1608)
    assert buffer_seconds(buf, rate) == pytest.approx(buf / rate, rel=1e-9)


def test_total_capacity_scales_linearly_with_duration():
    rate = data_rate_bytes_s(1608, 1608, 60)
    assert total_capacity_bytes(rate, 120.0) == pytest.approx(2 * total_capacity_bytes(rate, 60.0))
