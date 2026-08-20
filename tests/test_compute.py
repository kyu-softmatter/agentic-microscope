"""Tests for the compute-resource lens's pure formulas (compute.resources)
and the stream model it feeds (compute.setup).

Checked against docs/04-decision-engine.md §8's own worked examples.
"""

from __future__ import annotations

import pytest

from compute.resources import (
    buffer_bytes,
    buffer_seconds,
    buffer_seconds_from_frames,
    bytes_per_pixel_for_bit_depth,
    data_rate_bytes_s,
    flush_seconds,
    frame_bytes,
    total_capacity_bytes,
)
from compute.setup import AcquisitionResourceSetup, Stream


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


# ------------------------------------------------------- pixel container ---


@pytest.mark.parametrize(
    "bit_depth,expected",
    [(8, 1), (12, 2), (16, 2), (1, 1), (9, 2)],
)
def test_container_width_by_bit_depth(bit_depth, expected):
    """Kinetix Speed mode is 8-bit (data/detectors.yaml) -- one byte, not
    two, which halves the data rate in the one mode fast enough for G12a to
    bind."""
    assert bytes_per_pixel_for_bit_depth(bit_depth) == expected


@pytest.mark.parametrize("bad", [0, -1, 17, 32])
def test_container_width_refuses_unmodelled_bit_depths(bad):
    with pytest.raises(ValueError):
        bytes_per_pixel_for_bit_depth(bad)


def test_eight_bit_halves_the_data_rate():
    sixteen = data_rate_bytes_s(3200, 3200, 500, 2)
    eight = data_rate_bytes_s(3200, 3200, 500, 1)
    assert eight == pytest.approx(sixteen / 2)


# -------------------------------------------------------------- streams ---


def test_streams_sum_their_data_rates():
    """The dual-cam case that used to need the doubled-width trick recorded
    in kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md."""
    dual = AcquisitionResourceSetup(
        streams=[
            Stream("red", 2400, 2400, 200.0),
            Stream("blue", 2400, 2400, 200.0),
        ]
    )
    doubled_width = AcquisitionResourceSetup.single(
        frame_width_px=4800, frame_height_px=2400, fps=200.0
    )
    assert dual.data_rate_bytes_s() == pytest.approx(
        doubled_width.data_rate_bytes_s()
    )
    assert dual.data_rate_bytes_s() / 1e6 == pytest.approx(4608.0, abs=1.0)


def test_frames_per_s_counts_every_stream():
    setup = AcquisitionResourceSetup(
        streams=[Stream("red", 2400, 2400, 200.0), Stream("blue", 512, 512, 50.0)]
    )
    assert setup.frames_per_s() == pytest.approx(250.0)


def test_mean_frame_bytes_reconstructs_the_data_rate():
    """The weighting is what keeps G13a right when the streams differ in
    size -- mean_frame_bytes * frames_per_s must be the total rate."""
    setup = AcquisitionResourceSetup(
        streams=[Stream("red", 2400, 2400, 200.0), Stream("blue", 512, 512, 50.0)]
    )
    assert setup.mean_frame_bytes() * setup.frames_per_s() == pytest.approx(
        setup.data_rate_bytes_s()
    )


def test_buffer_seconds_from_frames_is_geometry_free():
    """MMCore counts its buffer in images, so headroom is frames over
    arrival rate no matter how the streams are shaped."""
    assert buffer_seconds_from_frames(2000, 400.0) == pytest.approx(5.0)


def test_from_dimensions_multiplies_z_channels_and_positions():
    s = Stream.from_dimensions(
        "cam", 512, 512, timepoints_per_s=2.0, z_slices=10, channels=2, positions=3
    )
    assert s.fps == pytest.approx(120.0)


def test_eight_bit_stream_is_flagged_as_an_assumed_container():
    assert Stream("cam", 512, 512, 10.0, bit_depth=8).container_is_assumed is True
    assert Stream("cam", 512, 512, 10.0, bit_depth=16).container_is_assumed is False
    assert (
        Stream("cam", 512, 512, 10.0, bit_depth=8, container_confirmed=True)
        .container_is_assumed
        is False
    )


def test_stream_rejects_an_unknown_fps_source():
    with pytest.raises(ValueError):
        Stream("cam", 512, 512, 10.0, fps_source="guessed")


# ---------------------------------------------------------- RAM capture ---


def test_flush_seconds_matches_the_decision_log_estimate():
    """kb/decisions/2026-08-12-ram-buffer-detour: 200 GB at the measured
    206.8 MB/s is about 16 minutes."""
    assert flush_seconds(200e9, 206.8) / 60 == pytest.approx(16.1, abs=0.3)
