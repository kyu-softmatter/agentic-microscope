"""Tests for the compute lens's post-hoc half -- compute.mm_metadata's
reader and compute.drops' detection.

The two failures being reproduced are real ones from docs/06-pitfalls.md:
§C4 (requested and delivered frame rate differed by 3x) and §C5 (frames are
discarded with no error, leaving only an irregular ElapsedTime series).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compute.drops import (
    GAP_RATIO,
    NotEnoughFrames,
    analyse,
    analyse_file,
    scan_tree,
)
from compute.mm_metadata import FrameTime, read_frame_times, read_summary_hints


def write_metadata(
    path,
    entries,
    *,
    interval_ms=None,
    quote_elapsed=False,
    one_line=False,
    omit_timestamp_for=(),
):
    """Write a Micro-Manager-shaped metadata file.

    ``entries`` is ``(t, c, z, elapsed_ms)`` tuples. The flags cover the
    variants docs/06 §A2 warns about: MM 1.4 quotes numbers, and nothing
    guarantees the file is pretty-printed.
    """
    summary = {"Frames": len(entries), "Width": 1608, "Height": 1608, "BitDepth": 16}
    if interval_ms is not None:
        summary["Interval_ms"] = interval_ms

    doc = {"Summary": summary}
    for t, c, z, ms in entries:
        frame = {"Channel": "Default", "PositionIndex": 0}
        if (t, c, z) not in omit_timestamp_for:
            frame["ElapsedTime-ms"] = str(ms) if quote_elapsed else ms
        doc[f"FrameKey-{t}-{c}-{z}"] = frame

    path.write_text(
        json.dumps(doc) if one_line else json.dumps(doc, indent=2), encoding="utf-8"
    )
    return path


def _series(intervals_ms, *, channel=0, start=0.0):
    """Frames laid out at the given successive intervals."""
    frames = [FrameTime(0, channel, 0, start)]
    t = start
    for i, dt in enumerate(intervals_ms, start=1):
        t += dt
        frames.append(FrameTime(i, channel, 0, t))
    return frames


# ------------------------------------------------------------- reading ---


def test_reads_frame_key_and_elapsed_time(tmp_path):
    path = write_metadata(
        tmp_path / "run_metadata.txt",
        [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 100.0)],
    )
    scan = read_frame_times(path)
    assert [f.frame for f in scan.frames] == [0, 1, 2]
    assert [f.elapsed_ms for f in scan.frames] == [0.0, 50.0, 100.0]
    assert scan.frames_without_timestamp == 0


def test_reads_a_single_line_file(tmp_path):
    """Nothing guarantees MM pretty-prints, so the scan matches tokens
    within a line rather than assuming one per line."""
    path = write_metadata(
        tmp_path / "run_metadata.txt",
        [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 100.0)],
        one_line=True,
    )
    assert len(read_frame_times(path).frames) == 3


def test_reads_quoted_elapsed_time(tmp_path):
    """MM 1.4 sometimes writes the number as a string (docs/06 §A2)."""
    path = write_metadata(
        tmp_path / "run_metadata.txt",
        [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 100.0)],
        quote_elapsed=True,
    )
    assert [f.elapsed_ms for f in read_frame_times(path).frames] == [0.0, 50.0, 100.0]


def test_counts_frame_keys_that_carry_no_timestamp(tmp_path):
    path = write_metadata(
        tmp_path / "run_metadata.txt",
        [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 100.0), (3, 0, 0, 150.0)],
        omit_timestamp_for=[(2, 0, 0)],
    )
    scan = read_frame_times(path)
    assert scan.frame_keys_seen == 4
    assert len(scan.frames) == 3
    assert scan.frames_without_timestamp == 1


def test_summary_hints_read_what_was_requested(tmp_path):
    path = write_metadata(
        tmp_path / "run_metadata.txt",
        [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 100.0)],
        interval_ms=11.76,
    )
    hints = read_summary_hints(path)
    assert hints.interval_ms == pytest.approx(11.76)
    assert hints.frames == 3
    assert (hints.width, hints.height, hints.bit_depth) == (1608, 1608, 16)


# ----------------------------------------------------------- detection ---


def test_a_steady_series_is_clean():
    r = analyse(_series([50.0] * 9))
    assert r.dropped_frames == 0
    assert r.n_gaps == 0
    assert r.jitter_fraction == 0.0
    assert r.contaminated is False
    assert r.cadence_fps == pytest.approx(20.0)


def test_one_missing_frame_shows_up_as_one_gap():
    """docs/06 §C5: the drop raises no error, so this doubled interval is
    the entire evidence that it happened."""
    r = analyse(_series([50.0, 50.0, 100.0, 50.0]))
    assert r.n_gaps == 1
    assert r.dropped_frames == 1
    assert r.largest_gap_frames == 1
    assert r.gaps[0].after_frame == 2
    assert r.contaminated is True
    assert r.dropped_fraction == pytest.approx(1 / 6)


def test_a_long_stall_is_counted_in_frames():
    r = analyse(_series([50.0, 50.0, 500.0, 50.0, 50.0]))
    assert r.dropped_frames == 9
    assert r.largest_gap_frames == 9


def test_cadence_survives_a_drop_but_throughput_does_not():
    """The median is used precisely because a drop can only lengthen an
    interval -- the cadence stays honest while throughput falls."""
    r = analyse(_series([50.0, 50.0, 100.0, 50.0, 50.0, 50.0]))
    assert r.cadence_fps == pytest.approx(20.0)
    assert r.throughput_fps < r.cadence_fps


def test_gap_threshold_is_not_tripped_by_jitter_below_the_ratio():
    just_under = 50.0 * (GAP_RATIO - 0.1)
    r = analyse(_series([50.0, 50.0, just_under, 50.0, 50.0]))
    assert r.dropped_frames == 0
    assert r.n_gaps == 0


def test_interleaved_channels_are_analysed_per_series():
    """A two-channel acquisition has a bimodal interval distribution -- a
    pooled median would land between the two modes and call every timepoint
    boundary a drop."""
    frames = []
    for t in range(4):
        frames.append(FrameTime(t, 0, 0, t * 100.0))
        frames.append(FrameTime(t, 1, 0, t * 100.0 + 10.0))
    r = analyse(frames)
    assert r.n_series == 2
    assert r.median_interval_ms == pytest.approx(100.0)
    assert r.dropped_frames == 0
    assert r.cadence_fps == pytest.approx(20.0)  # 10 fps per series, two series


def test_reproduces_the_c4_requested_versus_delivered_gap():
    """docs/06 §C4: a 176-row ROI at 10 ms exposure has a ~85 Hz ceiling
    (11.76 ms) and delivered ActualInterval-ms 35.67 -- 3x slower."""
    r = analyse(_series([35.67] * 8), requested_interval_ms=11.76)
    assert r.requested_vs_achieved == pytest.approx(3.03, abs=0.02)
    assert r.cadence_fps == pytest.approx(28.0, abs=0.1)


def test_fast_acquisitions_are_marked_quantization_limited():
    """At 500 fps the interval is 2 ms and MM's 1 ms timestamps cannot
    resolve jitter -- one tick of rounding is already a 1.5x interval, so
    without the quantization floor every tick would read as a dropped
    frame and the fastest sessions would look like the dirtiest."""
    r = analyse(_series([2.0, 3.0, 2.0, 2.0, 3.0, 2.0]))
    assert r.timestamps_quantized is True
    assert r.dropped_frames == 0
    assert r.irregular is False
    assert r.contaminated is False


def test_a_real_drop_still_registers_at_a_quantized_cadence():
    """The floor suppresses one tick of rounding, not a genuinely missing
    frame: at a 2 ms cadence that is a 4 ms interval."""
    r = analyse(_series([2.0, 2.0, 4.0, 2.0, 2.0]))
    assert r.dropped_frames == 1


def test_irregular_cadence_without_a_full_drop_still_counts_as_contaminated():
    r = analyse(_series([50.0, 60.0, 45.0, 62.0, 44.0, 58.0, 50.0]))
    assert r.dropped_frames == 0
    assert r.jitter_fraction > 0.10
    assert r.irregular is True
    assert r.contaminated is True


def test_a_true_interval_between_two_ticks_is_flagged_not_reported_as_steady():
    """Taken from a real 2.0.3 acquisition on this archive: 3000 frames whose
    intervals alternate 15 and 16 ms around a true cadence of 15.63. The
    median lands on 16, MAD comes out 0.00 ms, and delivered throughput
    exceeds the cadence -- which only makes sense once quantization is
    named."""
    intervals = [16.0, 15.0] * 8 + [16.0]
    r = analyse(_series(intervals))
    assert r.median_interval_ms == 16.0
    assert r.mean_interval_ms < r.median_interval_ms
    assert r.mad_interval_ms == 0.0
    assert r.timestamps_quantized is True
    assert r.irregular is False
    assert r.throughput_fps > r.cadence_fps


def test_a_short_run_is_reported_as_truncated_not_clean():
    """MM's Summary keeps advertising the planned frame count. An
    acquisition stopped at 58 of 1000 has perfectly uniform lag times and is
    still not the experiment anyone designed -- a real case on this
    archive."""
    r = analyse(_series([500.0] * 57), planned_frames=1000)
    assert r.contaminated is False
    assert r.truncated is True
    assert r.completion_fraction == pytest.approx(0.058)
    assert "truncated 58/1000" in r.summary_line()


def test_a_complete_run_is_not_truncated():
    r = analyse(_series([500.0] * 9), planned_frames=10)
    assert r.truncated is False
    assert r.completion_fraction == pytest.approx(1.0)


def test_truncation_is_unknown_without_a_summary():
    r = analyse(_series([500.0] * 9))
    assert r.completion_fraction is None
    assert r.truncated is False


def test_to_dict_carries_the_derived_verdicts():
    """A JSON consumer (the Phase 2 indexer) must not have to re-derive
    contaminated/truncated -- computing them here is the point."""
    d = analyse(_series([50.0, 50.0, 100.0, 50.0]), planned_frames=10).to_dict()
    assert d["contaminated"] is True
    assert d["truncated"] is True
    assert d["irregular"] is False
    assert d["completion_fraction"] == pytest.approx(0.5)
    assert d["dropped_frames"] == 1


def test_too_few_frames_refuses_rather_than_guessing():
    with pytest.raises(NotEnoughFrames):
        analyse([FrameTime(0, 0, 0, 0.0), FrameTime(1, 0, 0, 50.0)])


def test_series_shorter_than_the_minimum_are_skipped_not_averaged_in():
    frames = _series([50.0] * 5) + [FrameTime(0, 9, 0, 0.0)]
    r = analyse(frames)
    assert r.n_series == 1
    assert r.short_series == 1


# ---------------------------------------------------------------- sweep ---


def test_analyse_file_end_to_end(tmp_path):
    entries = [(0, 0, 0, 0.0), (1, 0, 0, 50.0), (2, 0, 0, 150.0), (3, 0, 0, 200.0)]
    path = write_metadata(tmp_path / "run_metadata.txt", entries, interval_ms=50.0)
    r = analyse_file(path)
    assert r.dropped_frames == 1
    assert r.source == str(path)
    assert r.requested_interval_ms == pytest.approx(50.0)
    # The containing folder has to be in the line: this archive reuses the
    # same MM prefix across dated folders, so a bare filename identifies
    # nothing.
    expected = str(Path(tmp_path.name) / "run_metadata.txt")
    assert r.summary_line().startswith(expected)
    assert r.summary_line(tmp_path).startswith("run_metadata.txt")


def test_scan_tree_separates_readable_from_skipped(tmp_path):
    write_metadata(
        tmp_path / "good_metadata.txt",
        [(t, 0, 0, t * 50.0) for t in range(6)],
    )
    write_metadata(tmp_path / "short_metadata.txt", [(0, 0, 0, 0.0)])

    results = {p.name: (r, e) for p, r, e in scan_tree(tmp_path)}
    assert results["good_metadata.txt"][0].contaminated is False
    assert results["short_metadata.txt"][0] is None
    assert "at least" in results["short_metadata.txt"][1]
