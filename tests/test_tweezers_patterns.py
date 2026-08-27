"""Tests for hardware.tweezers_patterns -- pure computation, no hardware.

The timing tests reproduce the Tweez300UserManual's own worked examples
(pp. 10-12) number for number. That is the strongest check available offline:
it does not prove the GUI accepts the files this module writes, but it does
prove the trap-loop arithmetic matches the vendor's.
"""

from __future__ import annotations

import math

import pytest

from hardware.tweezers_patterns import (
    PATTERN_SUFFIXES,
    Pattern,
    PatternError,
    PatternPoint,
    TrapLoop,
    bounded_random_walk,
    circle,
    oscillation,
    raster,
)


# ---- the manual's worked examples -------------------------------------


def test_manual_example_semi_continuous_illumination():
    """Manual p. 11: 200-point pattern, 3 traps in the loop, 100 kHz ->
    30 us per pass, 6 ms per traversal, illuminated ~167 times/s."""
    loop = TrapLoop(switching_rate_hz=100_000, n_traps=3)
    assert loop.pass_time_s == pytest.approx(30e-6)

    patt = circle(radius_um=10, n_points=200)
    assert patt.traversal_time_s(loop) == pytest.approx(6e-3)
    assert 1 / patt.traversal_time_s(loop) == pytest.approx(167, rel=1e-2)


def test_manual_example_slow_paths_via_switching_rate():
    """Manual p. 11-12: at 150 Hz with 3 traps the loop runs 50x/s, so a
    200-point pattern traverses in 4 s -- giving 12.5 um/s on a 50 um
    circumference and 37.5 um/s on a 150 um one."""
    loop = TrapLoop(switching_rate_hz=150, n_traps=3)
    assert 1 / loop.pass_time_s == pytest.approx(50)

    small = circle(radius_um=50 / (2 * math.pi), n_points=200)
    large = circle(radius_um=150 / (2 * math.pi), n_points=200)
    assert small.traversal_time_s(loop) == pytest.approx(4.0)
    assert small.mean_speed_um_s(loop) == pytest.approx(12.5, rel=1e-3)
    assert large.mean_speed_um_s(loop) == pytest.approx(37.5, rel=1e-3)


def test_manual_example_wait_states_as_point_duplication():
    """Manual p. 12: to get 5 um/s on the 150 um circumference while keeping
    100 kHz, the pattern must be slowed by 5000x (wait states 4999). dwell()
    reaches the same 30 s traversal by repeating each point."""
    loop = TrapLoop(switching_rate_hz=100_000, n_traps=3)
    patt = circle(radius_um=150 / (2 * math.pi), n_points=200)
    assert patt.traversal_time_s(loop) == pytest.approx(6e-3)

    slowed = patt.dwell(5000)
    assert len(slowed) == 200 * 5000
    assert slowed.traversal_time_s(loop) == pytest.approx(30.0)
    assert slowed.mean_speed_um_s(loop) == pytest.approx(5.0, rel=1e-3)


def test_switching_rate_for_speed_inverts_mean_speed():
    patt = circle(radius_um=8, n_points=120)
    rate = patt.switching_rate_for_speed(20.0, n_traps=2)
    assert patt.mean_speed_um_s(TrapLoop(rate, n_traps=2)) == pytest.approx(20.0)


def test_switching_rate_above_the_hardware_maximum_is_refused():
    with pytest.raises(PatternError, match="exceeds the quoted maximum"):
        TrapLoop(switching_rate_hz=200_000)


# ---- file format (manual pp. 55-56) -----------------------------------


def test_tpf_header_names_the_mandatory_columns():
    text = circle(5, 8).to_tpf()
    assert text.splitlines()[0] == "colX\tcolY\tcolStr"


def test_tpf_omits_colbp_unless_a_breakpoint_is_set():
    assert "colBP" not in circle(5, 8).to_tpf()
    marked = circle(5, 8).with_breakpoint_at(0, bits=1)
    lines = marked.to_tpf().splitlines()
    assert lines[0] == "colX\tcolY\tcolStr\tcolBP"
    assert lines[1].endswith("\t1")
    assert lines[2].endswith("\t0")


def test_tpf_body_has_one_line_per_point():
    patt = circle(5, 8)
    assert len(patt.to_tpf().splitlines()) == 1 + len(patt)


def test_tpf_can_use_a_decimal_comma_for_a_comma_locale():
    """Manual: floats follow the Windows locale, which may be a comma."""
    text = Pattern((PatternPoint(1.5, -2.25, 0.5),)).to_tpf(decimal=",")
    assert "1,5000\t-2,2500\t0,5000" in text


def test_tpf_rejects_an_unsupported_decimal_separator():
    with pytest.raises(PatternError, match="decimal separator"):
        circle(5, 8).to_tpf(decimal=";")


def test_write_rejects_an_extension_that_is_neither_candidate(tmp_path):
    with pytest.raises(PatternError, match=r"should end in one of"):
        circle(5, 8).write(tmp_path / "p.txt")


def test_write_accepts_both_candidate_extensions(tmp_path):
    """The manual claims .tpf for both the ASCII pattern file and the XML
    project file, and its one LOAD_PATTERN example says .tsf -- unresolvable
    from the document, so refusing either would be guessing. See
    PATTERN_SUFFIXES."""
    assert circle(5, 8).write(tmp_path / "a.tpf").exists()
    assert circle(5, 8).write(tmp_path / "b.tsf").exists()
    assert {".tpf", ".tsf"} == set(PATTERN_SUFFIXES)


def test_write_produces_ascii_with_windows_line_endings(tmp_path):
    out = circle(5, 8).write(tmp_path / "p.tpf")
    raw = out.read_bytes()
    assert raw.count(b"\r\n") == 1 + 8
    raw.decode("ascii")  # raises if anything non-ASCII slipped in


# ---- validation -------------------------------------------------------


def test_strength_outside_zero_to_one_is_refused():
    with pytest.raises(PatternError, match=r"strength must be in \[0, 1\]"):
        PatternPoint(0, 0, strength=1.5)


def test_empty_pattern_is_refused():
    with pytest.raises(PatternError, match="at least one point"):
        Pattern(())


def test_fits_within_is_a_necessary_check_on_the_half_extent():
    patt = circle(radius_um=12, n_points=64)
    assert patt.half_extent_um[0] == pytest.approx(12)
    assert patt.fits_within(50)  # 100x100 um max range
    assert not patt.fits_within(10)


def test_dwell_below_one_is_refused():
    with pytest.raises(PatternError, match="dwell factor"):
        circle(5, 8).dwell(0)


# ---- generators -------------------------------------------------------


def test_circle_closes_and_has_the_right_circumference():
    patt = circle(radius_um=10, n_points=360)
    assert patt.path_length_um == pytest.approx(2 * math.pi * 10, rel=1e-4)


def test_circle_needs_three_points():
    with pytest.raises(PatternError, match="at least 3 points"):
        circle(10, 2)


def test_oscillation_has_the_requested_point_count_and_no_repeated_turn():
    patt = oscillation(amplitude_um=5, n_points=10)
    assert len(patt) == 10
    xs = [p.x_um for p in patt.points]
    assert xs.count(min(xs)) == 1  # each turning point illuminated once
    assert xs.count(max(xs)) == 1


def test_oscillation_path_is_twice_the_peak_to_peak():
    patt = oscillation(amplitude_um=5, n_points=20)
    assert patt.path_length_um == pytest.approx(4 * 5, rel=1e-9)


def test_oscillation_respects_its_angle():
    patt = oscillation(amplitude_um=5, n_points=8, angle_deg=90)
    assert all(abs(p.x_um) < 1e-9 for p in patt.points)


def test_oscillation_refuses_an_odd_count_that_would_skew_the_legs():
    with pytest.raises(PatternError, match="even"):
        oscillation(5, 9)


def test_raster_covers_the_grid_and_serpentines():
    patt = raster(width_um=4, height_um=2, nx=3, ny=2)
    assert len(patt) == 6
    xs = [p.x_um for p in patt.points]
    assert xs[:3] == [-2, 0, 2]
    assert xs[3:] == [2, 0, -2]  # second row reversed


def test_raster_without_serpentine_keeps_every_row_in_the_same_direction():
    patt = raster(4, 2, 3, 2, serpentine=False)
    xs = [p.x_um for p in patt.points]
    assert xs[:3] == xs[3:]


# ---- bounded random walk ----------------------------------------------


def test_walk_is_reproducible_from_its_seed():
    """The seed is the record of the drive trajectory -- see the module
    docstring on F = kappa * (x_bead - x_trap)."""
    a = bounded_random_walk(200, step_um=0.5, half_width_um=8, seed=7)
    b = bounded_random_walk(200, step_um=0.5, half_width_um=8, seed=7)
    c = bounded_random_walk(200, step_um=0.5, half_width_um=8, seed=8)
    assert a.points == b.points
    assert a.points != c.points


def test_walk_stays_inside_its_boundary():
    patt = bounded_random_walk(5000, step_um=1.0, half_width_um=6, seed=3)
    assert all(abs(p.x_um) <= 6 + 1e-9 and abs(p.y_um) <= 6 + 1e-9 for p in patt.points)


def test_walk_point_count_is_exact_so_the_timing_is_exact():
    """Reflection, not rejection: a rejected step would make the traversal time
    depend on how often the walk hit the wall."""
    patt = bounded_random_walk(1234, step_um=2.0, half_width_um=4, seed=1)
    assert len(patt) == 1234


def test_walk_needs_room_to_step():
    with pytest.raises(PatternError, match="wider than one step"):
        bounded_random_walk(100, step_um=5.0, half_width_um=5.0, seed=1)


def test_walk_seeded_drive_lands_in_the_channels_speed_range():
    """active-microrheology-probe-tracer.yaml drives at 0-30 um/s. Check a
    plausible parameter set reaches it inside the switching-rate ceiling."""
    patt = bounded_random_walk(2000, step_um=0.25, half_width_um=8, seed=11)
    rate = patt.switching_rate_for_speed(30.0, n_traps=2)
    assert rate <= 100_000
    assert patt.mean_speed_um_s(TrapLoop(rate, n_traps=2)) == pytest.approx(30.0)
