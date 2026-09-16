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


# --------------------------------------------------- the rate ceiling ------
#
# The handoff INTRA_TIER claimed and nothing carried (2026-09-15). Ordering
# lens 2 before lens 3 is not the same as handing lens 3 a number: L3.2 warned
# and graded nothing on every brief with a requested rate, which reads from
# outside like a bias nobody could bound rather than a wire never run.

REQUESTED = """
meta: {id: requested, date: 2026-09-15}
facts:
  lens_1_optics:
    detector: {value: Kinetix22, count: 1, source: "test", evidence: measured}
    objective: {value: "4-Apo LmbdS 40x WI", source: "test", evidence: measured}
  lens_2_detection:
    exposure_ms: {value: 10.0, source: "test"}
    task_kind: {value: tracking, source: "test"}
    camera_mode: {value: "Sensitivity", source: "test"}
    wavelength_em_nm: {value: 520.0, source: "test"}
    roi_width_px: {value: 512, source: "test"}
    roi_height_px: {value: 512, source: "test"}
    row_time_ns: {value: 3531.2, source: "test"}
    target_fps: {value: 100.0, source: "test"}
    photons:
      signal_e_per_s: {value: 50000.0, source: "test"}
      background_e_per_s: {value: 2000.0, source: "test"}
  lens_3_compute:
    disk_bandwidth_mb_s: {value: 206.8, source: "test"}
    free_disk_gb: {value: 500.0, source: "test"}
    circular_buffer_frames: {value: 10000, source: "test"}
  environment:
    acquisition_duration_s: {value: 60.0, source: "test"}
gaps: []
"""


def _requested(tmp_path):
    path = tmp_path / "requested.yaml"
    path.write_text(textwrap.dedent(REQUESTED), encoding="utf-8")
    return brief_mod.load(path)


def test_l3_2_grades_the_requested_rate_once_the_ceiling_is_carried(tmp_path):
    """Without `detection=` L3.2 can only warn; with it the shortfall gets a
    margin. Same arrangement as trapping.checks.check_sampling's detector_fps.
    """
    import compute.gate as compute_gate

    b = _requested(tmp_path)
    detection = build_detection(b)

    alone = compute_gate.evaluate(build_compute(b))
    assert any(f.code == "fps_provenance.requested" for f in alone.findings)
    assert "fps_provenance" not in alone.margins

    carried = compute_gate.evaluate(build_compute(b, detection=detection))
    assert not any(f.code == "fps_provenance.requested" for f in carried.findings)
    # 30 fps usable against a 100 fps request. Unrealizable, and now SAID so
    # with a margin instead of warned about without one.
    assert carried.margins["fps_provenance.unrealizable"] == pytest.approx(0.3)


def test_the_ceiling_is_the_duty_limit_not_the_hardware_maximum(tmp_path):
    """At a 10 ms exposure this camera reaches 100 fps and L2.4 allows 30.

    Passing the hardware figure would let L3.2 clear a 100 fps stream L2.4
    refuses -- the rename recorded in `compute/setup.py`'s own comment (KH,
    2026-09-10), held here by a number instead of by a comment.
    """
    detection = build_detection(_requested(tmp_path))
    window = detection.frame_rate_window()

    assert window.fps_hardware_max == pytest.approx(100.0)
    assert window.fps_at_duty_limit == pytest.approx(30.0)
    assert window.fps_usable_max == pytest.approx(30.0)
    assert window.binding == "blur (L2.4)"

    setup = build_compute(_requested(tmp_path), detection=detection)
    assert setup.usable_fps_ceiling == pytest.approx(30.0)


def test_lens_3_survives_lens_2_not_being_buildable(tmp_path):
    """Same rule as lens 4's: None is the honest argument, and it must make
    L3.2 fall back to warning rather than make the whole lens unbuildable."""
    setup = build_compute(_requested(tmp_path), detection=None)
    assert setup.usable_fps_ceiling is None
    assert len(setup.streams) == 1


def test_one_end_of_the_window_is_not_the_window(tmp_path):
    """With no ROI height there is no readout time, so there is no hardware
    ceiling -- and the duty limit alone must not be reported as the usable
    rate. A single bound reading as a cleared pair is §3 exactly."""
    b = _requested(tmp_path)
    b.facts["lens_2_detection"]["roi_height_px"] = {"value": None}
    window = build_detection(b).frame_rate_window()

    assert window.fps_at_duty_limit == pytest.approx(30.0)
    assert window.fps_hardware_max is None
    assert window.fps_usable_max is None
    assert window.binding is None


def test_l2_4_l2_5_and_lens_3_read_one_definition_of_the_window(tmp_path):
    """Three readers, one derivation.

    `fps_at_duty_limit` was derived separately in L2.4 and L2.5 before this,
    and lens 3's ceiling is the third reader. Two bounds that disagree about
    the usable rate is the failure one copy away.
    """
    import detection.gate as detection_gate

    detection = build_detection(_requested(tmp_path))
    window = detection.frame_rate_window()
    verdict = detection_gate.evaluate(detection)

    ends = [
        numbers["fps_at_duty_limit"]
        for numbers in verdict.metrics.values()
        if "fps_at_duty_limit" in numbers
    ]
    assert len(ends) >= 2
    assert all(v == pytest.approx(window.fps_at_duty_limit) for v in ends)

    usable = [
        numbers["fps_usable_max"]
        for numbers in verdict.metrics.values()
        if "fps_usable_max" in numbers
    ]
    assert usable and all(v == pytest.approx(window.fps_usable_max) for v in usable)


# ------------------------------------------------ lens 2 actually runs -----


def test_lens_2_reaches_phase_1(tmp_path):
    """It never did. `build_detection` passed no `PhotonBudget` and the brief
    had nowhere to carry one, so lens 2 BLOCKED with `missing.photon.signal`
    on every brief the designer ever ran -- and Phase 0 is all-or-nothing, so
    L2.1, L2.4, L2.5 and L2.6 never executed either, on inputs all present."""
    import detection.gate as detection_gate

    verdict = detection_gate.evaluate(build_detection(_requested(tmp_path)))
    assert verdict.status != "BLOCKED"
    assert {"sampling", "motion_blur", "frame_rate"} <= {
        code.split(".")[0] for code in verdict.metrics
    }


def test_a_brief_with_no_photometry_still_blocks_lens_2(tmp_path):
    """Signal and background must be MEASURED (kb/calibrations/frame-
    photometry.yaml). Wiring the field through is not permission to default
    it: a brief that is silent still BLOCKs, which is the correct answer."""
    import detection.gate as detection_gate

    b = _requested(tmp_path)
    del b.facts["lens_2_detection"]["photons"]
    findings = detection_gate.evaluate(build_detection(b)).findings
    assert any(f.code == "missing.photon.signal" for f in findings)


def test_no_emission_wavelength_refuses_by_name_instead_of_raising(tmp_path):
    """L2.1 divides by it, and `available_facts` did not list it -- so a setup
    with no wavelength cleared Phase 0 and `check_sampling` raised a
    TypeError. Invisible while the only caller was a CLI whose
    `--wavelength-em-nm` was required."""
    import detection.gate as detection_gate

    b = _requested(tmp_path)
    b.facts["lens_2_detection"]["wavelength_em_nm"] = {"value": None}
    verdict = detection_gate.evaluate(build_detection(b))

    assert verdict.status == "BLOCKED"
    assert any(f.code == "missing.wavelength" for f in verdict.findings)


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


# --------------------------------- carrying L6.5's numbers down -----------
#
# Lens 6 reads verdicts everywhere else; L6.5 reads NUMBERS, and it takes them
# as plain fields rather than reaching into another lens's `metrics` by string
# key. Carrying them is this module's job, so it is tested here.

FULL = """
meta: {id: full, date: 2026-09-14}
goal: {intended_quantity: msd}
facts:
  system:
    characteristic_time_s: {value: 0.5, source: "test"}
  lens_1_optics:
    detector: {value: Kinetix22, count: 1, source: "test", evidence: measured}
    objective: {value: "4-Apo LmbdS 40x WI", source: "test", evidence: measured}
  lens_2_detection:
    exposure_ms: {value: 10.0, source: "test"}
    task_kind: {value: tracking, source: "test"}
    camera_mode: {value: "Sensitivity", source: "test"}
    roi_width_px: {value: 512, source: "test"}
    roi_height_px: {value: 512, source: "test"}
    row_time_ns: {value: 3531.2, source: "test"}
    achieved_fps: {value: 100.0, source: "timestamps"}
  lens_4_sample:
    probe: {diameter_um: 0.5, source: "test"}
    imaging_depth_um: {value: 8.0, source: "test"}
    chamber_height_um: {value: 100.0, source: "test"}
    tracer_concentration_per_ml: {value: 10000000.0, source: "test"}
  lens_9_velocity:
    target_relative_error: {value: 0.05, source: "test"}
  environment:
    acquisition_duration_s: {value: 60.0, source: "test"}
gaps: []
"""


def _full(tmp_path, extra_lens_4="", extra_lens_9=""):
    text = textwrap.dedent(FULL)
    if extra_lens_4:
        text = text.replace("  lens_9_velocity:", extra_lens_4 + "  lens_9_velocity:")
    if extra_lens_9:
        text = text.replace("  environment:", extra_lens_9 + "  environment:")
    path = tmp_path / "full.yaml"
    path.write_text(text, encoding="utf-8")
    return brief_mod.load(path)


def _validity_for(brief):
    from designer.build import build_sample, build_validity

    detection = build_detection(brief)
    sample = build_sample(brief, detection=detection)
    return build_validity(brief, setups={"sample": sample, "detection": detection})


def test_l6_5_gets_the_particle_count_from_lens_4(tmp_path):
    """The same settled density L4.6 and L4.8 bound from either side, so the
    three readers cannot disagree about how many particles there are."""
    from designer.build import build_sample

    brief = _full(tmp_path)
    sample = build_sample(brief, detection=build_detection(brief))
    v = _validity_for(brief)
    assert v.n_particles == pytest.approx(sample.expected_count_in_field)
    assert v.n_particles == pytest.approx(6.92, rel=1e-2)


def test_l6_5_gets_the_frames_from_the_duration_and_the_decided_rate(tmp_path):
    v = _validity_for(_full(tmp_path))
    assert v.frame_rate_hz == 100.0
    assert v.n_frames == pytest.approx(6000.0)


def test_l6_5_has_no_particle_count_when_lens_2_did_not_run(tmp_path):
    """The field is lens 2's, so without it there is no count -- and L6.5 then
    reports rather than grading, which is the whole repair over G11."""
    from designer.build import build_sample, build_validity

    brief = _full(tmp_path)
    sample = build_sample(brief, detection=None)
    v = build_validity(brief, setups={"sample": sample})
    assert v.n_particles is None
    assert v.n_frames is None


def test_a_trapped_beads_own_tau_beats_the_stated_characteristic_time(tmp_path):
    """tau = gamma/kappa is what actually decorrelates consecutive frames.
    The brief's characteristic time is the fallback, for a free particle."""
    from designer.build import build_sample, build_validity
    from velocity.setup import VelocitySetup

    brief = _full(tmp_path)
    detection = build_detection(brief)
    sample = build_sample(brief, detection=detection)
    setups = {"sample": sample, "detection": detection}

    assert build_validity(brief, setups=setups).correlation_time_s == 0.5

    trapped = VelocitySetup(
        particle_radius_um=2.475, viscosity_pa_s=1.002e-3, stiffness_pn_per_um=3.87
    )
    with_trap = build_validity(brief, setups={**setups, "velocity": trapped})
    assert with_trap.correlation_time_s == pytest.approx(0.0121, rel=1e-2)


def test_the_carried_numbers_make_l6_5_grade(tmp_path):
    """End to end: 6.9 particles x 6000 frames is 41,533 naive samples, and 50
    frames per correlation time makes that 415 -- 4.9 % against a 5 % target
    where counting every frame would have claimed 0.49 %."""
    from validity.checks import check_independent_samples

    r = check_independent_samples(_validity_for(_full(tmp_path)))
    assert r.kind == "soft"
    assert r.numbers["independent_samples"] == pytest.approx(415, rel=1e-2)
    assert r.numbers["optimism_factor"] == pytest.approx(10.0, rel=1e-2)
    assert r.margin > 1.0


# ---------------------------------------- the two new brief fields --------


def test_target_particles_in_field_is_passed_only_when_stated(tmp_path):
    """Its dataclass default of 1.0 is definitional -- one particle or there is
    no measurement -- so passing None would break L4.8 rather than default it."""
    from designer.build import build_sample

    silent = build_sample(_full(tmp_path), detection=None)
    assert silent.target_particles_in_field == 1.0

    stated = build_sample(
        _full(
            tmp_path,
            extra_lens_4='    target_particles_in_field: {value: 5.0, source: "test"}\n',
        ),
        detection=None,
    )
    assert stated.target_particles_in_field == 5.0


def test_n_steps_reaches_lens_9(tmp_path):
    from designer.build import build_velocity

    assert build_velocity(_full(tmp_path)).n_steps is None
    stated = build_velocity(
        _full(tmp_path, extra_lens_9='    n_steps: {value: 40, source: "test"}\n')
    )
    assert stated.n_steps == 40
