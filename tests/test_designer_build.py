"""Tests for `designer/build.py` -- the brief -> Setup boundary.

The designer's only contact with physical values, and therefore the one place
rule 2 is easiest to break. These tests are almost all of the form "the brief
does not say, so the builder does not either": a fallback here would be
invisible, because the lens downstream would compute happily on it.

Written 2026-09-14 with the stream wiring. Before it, `build_compute` passed
no streams at all and lens 3 refused with `missing.streams` on every brief
ever written -- which nothing noticed, because nothing tested this module.
"""

from __future__ import annotations

import textwrap

import pytest

from designer import brief as brief_mod
from designer.build import build_compute, build_detection, _streams

BASE = """
meta:
  id: t
  date: 2026-09-14
facts:
  lens_1_optics:
    detector:
      value: Kinetix22
      count: {count}
      source: "test"
      evidence: measured
    objective:
      value: "4-Apo LmbdS 40x WI"
      na: 1.25
      source: "test"
  lens_2_detection:
    exposure_ms: {{value: 10.0, source: "test"}}
    camera_mode: {{value: {mode}, source: "test"}}
    roi_width_px: {{value: {w}, source: "test"}}
    roi_height_px: {{value: {h}, source: "test"}}
    {rate}
gaps: []
"""


def _brief(tmp_path, *, count=1, mode='"Sensitivity"', w=512, h=512, rate="target_fps: {value: 100.0, source: \"test\"}"):
    path = tmp_path / "b.yaml"
    path.write_text(
        textwrap.dedent(BASE).format(count=count, mode=mode, w=w, h=h, rate=rate),
        encoding="utf-8",
    )
    return brief_mod.load(path)


# ------------------------------------------------------------- streams -----


@pytest.mark.parametrize(
    "kwargs",
    [
        {"w": "null"},
        {"h": "null"},
        {"rate": ""},
        {"mode": "null"},
    ],
    ids=["no-width", "no-height", "no-rate", "no-mode"],
)
def test_no_stream_when_any_of_the_four_facts_is_absent(tmp_path, kwargs):
    assert _streams(_brief(tmp_path, **kwargs)) == []


def test_the_stream_carries_the_modes_bit_depth_not_a_default(tmp_path):
    """16 would be the dataclass default and 12 is what Sensitivity actually
    writes. A 16 here makes L3.1's data rate 33% high, in the direction that
    looks safe."""
    from optics.components import find_detector

    expected = find_detector("Kinetix22").modes["Sensitivity"].bit_depth
    (stream,) = _streams(_brief(tmp_path))
    assert stream.bit_depth == expected
    assert stream.width_px == 512 and stream.height_px == 512


def test_two_camera_bodies_are_two_streams(tmp_path):
    """One disk, twice the data rate -- the reason L3.1 is a `hard` gate."""
    streams = _streams(_brief(tmp_path, count=2))
    assert len(streams) == 2
    assert len({s.label for s in streams}) == 2


def test_a_requested_rate_is_marked_requested(tmp_path):
    """L3.2's whole subject: a requested rate is not evidence (CLAUDE.md E5)."""
    (requested,) = _streams(_brief(tmp_path))
    assert requested.fps_source == "requested"

    (achieved,) = _streams(
        _brief(tmp_path, rate='achieved_fps: {value: 62.0, source: "timestamps"}')
    )
    assert achieved.fps_source == "measured"
    assert achieved.fps == 62.0


def test_compute_setup_gets_the_streams(tmp_path):
    setup = build_compute(_brief(tmp_path))
    assert len(setup.streams) == 1


# ----------------------------------------------------- characteristic ------


def test_the_system_scales_reach_lens_2_or_stay_none(tmp_path):
    """L2.6 asks for them; the builder passes them through and invents
    neither. A brief that is silent leaves them None, and the check reports
    the silence rather than the builder papering over it."""
    silent = build_detection(_brief(tmp_path))
    assert silent.characteristic_length_um is None
    assert silent.characteristic_time_s is None

    path = tmp_path / "with-scales.yaml"
    path.write_text(
        textwrap.dedent(BASE).format(
            count=1, mode='"Sensitivity"', w=512, h=512,
            rate='target_fps: {value: 100.0, source: "test"}',
        ).replace(
            "  lens_1_optics:",
            "  system:\n"
            "    characteristic_length_um: {value: 2.0, source: \"KH\"}\n"
            "    characteristic_time_s: {value: 0.05, source: \"KH\"}\n"
            "  lens_1_optics:",
        ),
        encoding="utf-8",
    )
    supplied = build_detection(brief_mod.load(path))
    assert supplied.characteristic_length_um == 2.0
    assert supplied.characteristic_time_s == 0.05
