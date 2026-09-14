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


# ------------------------------------------------- the lens 2 -> 4 handoff --


def test_lens_2_computes_the_field_and_lens_4_receives_it(tmp_path):
    """`sample/setup.py` says the field is "owned by lenses 1/2 ... lens 4 only
    consumes it", and until 2026-09-14 nothing carried it. L4.6's particle
    count only ever ran from `sample/cli.py`'s arguments."""
    from designer.build import build_sample

    brief = _brief(tmp_path)
    detection = build_detection(brief)
    width_um, height_um = detection.field_of_view_um()

    pixel_nm, _ = detection.pixel_size_nm()
    assert width_um == pytest.approx(512 * pixel_nm / 1000.0)
    assert height_um == pytest.approx(512 * pixel_nm / 1000.0)

    sample = build_sample(brief, detection=detection)
    assert sample.field_width_um == pytest.approx(width_um)
    assert sample.field_height_um == pytest.approx(height_um)


def test_lens_4_survives_lens_2_not_being_buildable(tmp_path):
    """Lens 2 unbuildable must not make lens 4 unbuildable too -- it must make
    lens 4's field-dependent half say it did not evaluate."""
    from designer.build import build_sample

    sample = build_sample(_brief(tmp_path), detection=None)
    assert sample.field_width_um is None
    assert sample.field_height_um is None


def test_the_field_is_none_for_a_dimension_the_roi_does_not_give(tmp_path):
    detection = build_detection(_brief(tmp_path, w="null"))
    assert detection.field_of_view_um()[0] is None
    assert detection.field_of_view_um()[1] is not None


# ----------------------------------------------- one definition, one file --


def test_the_convening_threshold_has_exactly_one_definition():
    """It was a second `30.0` in roster.py until 2026-09-14, and the copies had
    already drifted in the comparison around them: `>= 30` here, `> 30` in
    `StabilitySetup.convenes`, so a 30-minute run convened lens 8 in one place
    and not the other."""
    from stability.setup import CONVENE_DURATION_MIN, StabilitySetup

    from designer.roster import STABILITY_THRESHOLD_MIN

    assert STABILITY_THRESHOLD_MIN is CONVENE_DURATION_MIN
    assert StabilitySetup(duration_min=CONVENE_DURATION_MIN).convenes is False


def test_exactly_thirty_minutes_convenes_nobody(tmp_path):
    """The boundary the two copies disagreed on. Whichever way it goes, both
    places have to go the same way."""
    from stability.setup import StabilitySetup

    from designer.roster import convene

    path = tmp_path / "thirty.yaml"
    path.write_text(
        textwrap.dedent(BASE).format(
            count=1, mode='"Sensitivity"', w=512, h=512,
            rate='target_fps: {value: 100.0, source: "test"}',
        ).replace(
            "gaps: []",
            '  environment:\n'
            '    acquisition_duration_s: {value: 1800.0, source: "test"}\n'
            "gaps: []",
        ),
        encoding="utf-8",
    )
    seat = convene(brief_mod.load(path))["stability"]
    assert seat.state == "absent"
    assert StabilitySetup(duration_min=30.0).convenes is False


# ------------------------------------------- the brief names, the KB is ----


def test_a_known_objective_comes_from_the_registry_with_its_working_distance(tmp_path):
    """The brief NAMES the objective; `data/objectives.yaml` IS the objective.

    Hand-building one from the brief's three fields threw away `wd_um`, so
    lens 4 BLOCKED with `missing.working_distance` on every brief the designer
    ever ran -- the whole lens, silently, on a fact recorded 2026-08-10.
    """
    from optics.components import find_objective

    from designer.build import _objective

    obj = _objective(_brief(tmp_path))
    assert obj is find_objective("4-Apo LmbdS 40x WI")
    assert obj.wd_um == 160


def test_an_objective_the_registry_does_not_know_still_builds_from_the_brief(tmp_path):
    """On the nosepiece and not in the file is a real situation; refusing it
    would be worse than proceeding with less."""
    from designer.build import _objective

    path = tmp_path / "unknown.yaml"
    path.write_text(
        textwrap.dedent(BASE)
        .format(count=1, mode='"Sensitivity"', w=512, h=512, rate="")
        .replace('"4-Apo LmbdS 40x WI"', '"60x Someone Else"'),
        encoding="utf-8",
    )
    obj = _objective(brief_mod.load(path))
    assert obj.label == "60x Someone Else"
    assert obj.magnification == 60.0
    assert obj.wd_um is None


def test_lens_4_reaches_phase_1_now_that_it_has_a_working_distance(tmp_path):
    """The end of the chain: with the objective looked up and the field handed
    down, L4.4 through L4.7 execute instead of the lens refusing at Phase 0."""
    from designer import run as run_mod

    path = tmp_path / "full.yaml"
    path.write_text(
        textwrap.dedent(BASE)
        .format(count=1, mode='"Sensitivity"', w=512, h=512,
                rate='task_kind: {value: tracking, source: "test"}')
        .replace(
            "gaps: []",
            "  lens_4_sample:\n"
            "    probe: {diameter_um: 5.0, source: \"test\"}\n"
            "    imaging_depth_um: {value: 8.0, source: \"test\"}\n"
            "    chamber_height_um: {value: 100.0, source: \"test\"}\n"
            "    tracer_concentration_per_ml: {value: 10000000.0, source: \"test\"}\n"
            "gaps: []",
        ),
        encoding="utf-8",
    )
    verdict = run_mod.run(brief_mod.load(path)).runs["sample"].verdict
    assert verdict.status != "BLOCKED"
    count = next(f for f in verdict.findings if "count_in_field" in f.code)
    assert count.numbers["evaluated"] is True
    assert count.numbers["expected_count"] > 0
