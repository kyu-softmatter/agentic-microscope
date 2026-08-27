"""Tests for hardware.piezo_waveform and the piezo command-set reference.

Pure computation. The vendor DLL is a Windows PE binary, so nothing here loads
it -- the parts that need the real controller are covered by
config/piezo/verify_piezo_commands.py instead, which is why the reference-list
tests below exist: they are the only offline check that the command names the
code uses are names the DLL actually contains.
"""

from __future__ import annotations

import pytest

from hardware.piezo_waveform import (
    OBSERVED,
    PM_PER_UM,
    StageTravel,
    Waveform,
    WaveformError,
    ramp,
    raster_pair,
    sine,
    staircase,
    triangle,
)

UM = PM_PER_UM


# ---- travel ------------------------------------------------------------


def test_calibrated_travel_matches_what_the_controller_reports():
    """Read off COM4 on 2026-08-27: 0-600 um per axis, 32 pm command step.

    Was 0-400 um / 0.0122 um, which came from NIS's analogue abstraction of the
    same controller and was wrong for this path on both numbers.
    """
    assert OBSERVED.min_pm == 0.0
    assert OBSERVED.max_pm == pytest.approx(600 * UM)
    assert OBSERVED.resolution_pm == pytest.approx(32.0)
    assert OBSERVED.centre_pm == pytest.approx(300 * UM)


def test_inverted_travel_is_refused():
    with pytest.raises(WaveformError, match="max must exceed min"):
        StageTravel(min_pm=10.0, max_pm=1.0, resolution_pm=1.0)


def test_nonpositive_resolution_is_refused():
    with pytest.raises(WaveformError, match="resolution must be positive"):
        StageTravel(min_pm=0.0, max_pm=10.0, resolution_pm=0.0)


def test_quantise_snaps_to_the_controller_step():
    travel = StageTravel(0.0, 400 * UM, 0.0122 * UM)
    assert travel.quantise(0.0) == pytest.approx(0.0)
    # 0.02 um is between the 1st (0.0122) and 2nd (0.0244) step; nearer the 2nd
    assert travel.quantise(0.02 * UM) == pytest.approx(0.0244 * UM)


# ---- waveform basics ---------------------------------------------------


def test_empty_waveform_is_refused():
    with pytest.raises(WaveformError, match="at least one sample"):
        Waveform((), channel=1)


def test_channels_are_one_based():
    with pytest.raises(WaveformError, match="1-based"):
        Waveform((0.0,), channel=0)


def test_out_of_travel_is_refused_not_clipped():
    """Silent clipping is the tweezers' trapping-range failure mode: data that
    looks fine and is wrong. Here it raises."""
    wf = ramp(0.0, 700 * UM, 10)          # travel is 0..600 um
    assert not wf.fits_within(OBSERVED)
    with pytest.raises(WaveformError, match="outside travel"):
        wf.check(OBSERVED)


def test_a_waveform_inside_travel_passes_the_check():
    wf = triangle(amplitude_pm=10 * UM, n_samples=20, travel=OBSERVED)
    wf.check(OBSERVED)
    assert wf.fits_within(OBSERVED)


def test_quantisation_error_is_reported_not_hidden():
    """On the measured 32 pm command step, a 50 pm amplitude is a few levels.

    The amplitude has to be this small to show it: the step is 32 pm, not the
    12.2 nm this test used to assume from NIS's analogue scaling.
    """
    wf = triangle(amplitude_pm=50.0, n_samples=20, travel=OBSERVED)
    assert wf.quantisation_error_pm(OBSERVED) > 0
    coarse = wf.quantised(OBSERVED)
    assert len(set(coarse.samples)) <= 8


# ---- timing needs a period supplied -----------------------------------


def test_duration_requires_a_sample_period():
    """A Waveform has a length but no duration: the generator's timebase is in
    a manual this repo does not have."""
    wf = ramp(0.0, 10 * UM, 100)
    assert not hasattr(wf, "duration")
    assert wf.duration_s(1e-3) == pytest.approx(0.1)
    assert wf.duration_s(1e-3, iterations=5) == pytest.approx(0.5)


def test_nonpositive_period_and_iterations_are_refused():
    wf = ramp(0.0, 10 * UM, 10)
    with pytest.raises(WaveformError, match="sample period must be positive"):
        wf.duration_s(0)
    with pytest.raises(WaveformError, match="iterations must be >= 1"):
        wf.duration_s(1e-3, iterations=0)


def test_peak_speed_uses_the_largest_step():
    """A +/-10 um triangle over 20 samples has an 11-point forward leg, so it
    steps 20/10 = 2 um per sample; at a 1 ms period that is 2000 um/s."""
    wf = triangle(amplitude_pm=10 * UM, n_samples=20, centre_pm=200 * UM)
    steps = {round(abs(b - a) / UM, 9) for a, b in zip(wf.samples, wf.samples[1:])}
    assert steps == {2.0}
    assert wf.peak_speed_um_s(1e-3) == pytest.approx(2000.0)


def test_peak_speed_rejects_a_nonpositive_period():
    with pytest.raises(WaveformError, match="sample period must be positive"):
        ramp(0.0, 10 * UM, 10).peak_speed_um_s(0)


# ---- generators --------------------------------------------------------


def test_ramp_hits_both_endpoints():
    wf = ramp(10 * UM, 30 * UM, 5)
    assert wf.samples[0] == pytest.approx(10 * UM)
    assert wf.samples[-1] == pytest.approx(30 * UM)
    assert len(wf) == 5


def test_ramp_needs_two_samples():
    with pytest.raises(WaveformError, match="at least 2 samples"):
        ramp(0.0, 1.0, 1)


def test_triangle_is_closed_with_no_repeated_turning_point():
    wf = triangle(amplitude_pm=5 * UM, n_samples=10, centre_pm=200 * UM)
    assert len(wf) == 10
    s = list(wf.samples)
    assert s.count(min(s)) == 1
    assert s.count(max(s)) == 1


def test_triangle_refuses_an_odd_count():
    with pytest.raises(WaveformError, match="even"):
        triangle(amplitude_pm=5 * UM, n_samples=9, centre_pm=0.0)


def test_triangle_centres_on_the_travel_when_asked():
    wf = triangle(amplitude_pm=5 * UM, n_samples=8, travel=OBSERVED)
    lo, hi = wf.span_pm
    assert (lo + hi) / 2 == pytest.approx(OBSERVED.centre_pm)


def test_a_generator_needs_a_centre_or_a_travel():
    with pytest.raises(WaveformError, match="centre_pm or travel"):
        triangle(amplitude_pm=5 * UM, n_samples=8)


def test_sine_spans_the_amplitude_and_closes():
    wf = sine(amplitude_pm=5 * UM, n_samples=360, centre_pm=200 * UM)
    lo, hi = wf.span_pm
    assert hi - 200 * UM == pytest.approx(5 * UM, rel=1e-3)
    assert 200 * UM - lo == pytest.approx(5 * UM, rel=1e-3)
    assert wf.samples[0] == pytest.approx(200 * UM)  # starts at the centre


def test_sine_needs_four_samples():
    with pytest.raises(WaveformError, match="at least 4 samples"):
        sine(amplitude_pm=1.0, n_samples=3, centre_pm=0.0)


def test_staircase_holds_each_level():
    wf = staircase(start_pm=0.0, step_pm=1 * UM, n_steps=3, dwell_samples=4)
    assert len(wf) == 12
    assert wf.samples[:4] == (0.0,) * 4
    assert wf.samples[4:8] == (1 * UM,) * 4


def test_staircase_refuses_a_zero_dwell():
    with pytest.raises(WaveformError, match=">= 1"):
        staircase(0.0, 1.0, 3, 0)


# ---- raster: two channels, one length ---------------------------------


def test_raster_pair_returns_equal_length_waveforms_on_two_channels():
    """A hardware raster is two channels playing synchronised arrays, so the
    lengths have to match and the pair has to be started together."""
    fast, slow = raster_pair(
        fast_amplitude_pm=5 * UM, slow_amplitude_pm=5 * UM,
        n_fast=4, n_lines=3, travel=OBSERVED,
    )
    assert len(fast) == len(slow) == 12
    assert fast.channel == 1 and slow.channel == 2


def test_raster_fast_axis_serpentines():
    fast, _ = raster_pair(5 * UM, 5 * UM, n_fast=3, n_lines=2, travel=OBSERVED)
    first, second = fast.samples[:3], fast.samples[3:]
    assert second == tuple(reversed(first))


def test_raster_slow_axis_holds_one_value_per_line():
    _, slow = raster_pair(5 * UM, 5 * UM, n_fast=4, n_lines=3, travel=OBSERVED)
    lines = [slow.samples[i * 4:(i + 1) * 4] for i in range(3)]
    assert all(len(set(line)) == 1 for line in lines)
    assert len({line[0] for line in lines}) == 3


def test_a_single_line_raster_holds_the_slow_axis_at_centre():
    _, slow = raster_pair(5 * UM, 5 * UM, n_fast=4, n_lines=1, travel=OBSERVED)
    assert set(slow.samples) == {OBSERVED.centre_pm}


def test_raster_refuses_degenerate_sizes():
    with pytest.raises(WaveformError, match="n_fast must be >= 2"):
        raster_pair(1.0, 1.0, n_fast=1, n_lines=2, centre_fast_pm=0.0, centre_slow_pm=0.0)


# ---- the command-set reference ----------------------------------------


def test_reference_lists_the_waveform_generator():
    """The finding this whole piece rests on: the controller DLL carries a
    function.* family, so the piezo can play a trajectory in hardware."""
    from hardware.piezo_stage import reference_commands

    commands = reference_commands()
    assert "function.waveform.data.set" in commands
    assert "function.waveform.count.set" in commands
    assert "function.waveform.iterations.set" in commands
    assert {"function.command.start", "function.command.stop"} <= commands


def test_reference_lists_the_readbacks_the_tweezers_lack():
    from hardware.piezo_stage import reference_commands

    commands = reference_commands()
    assert "function.state.get" in commands
    assert "stage.position.measured.get" in commands
    assert "snapshot.response.data.get" in commands


def test_reference_lists_the_mode_query_the_kb_asks_for():
    """The analogue-input question outstanding since 2026-08-19 -- and note
    there is no stage.mode.set, so it is readable, not settable."""
    from hardware.piezo_stage import reference_commands

    commands = reference_commands()
    assert "stage.mode.get" in commands
    assert "stage.mode.set" not in commands


def test_reference_parses_to_a_plausible_command_count():
    from hardware.piezo_stage import reference_commands

    commands = reference_commands()
    # what the controller answered at User level on 2026-08-27, over COM4
    assert len(commands) == 414
    assert not any(c.endswith(".") for c in commands)
    # the hyphenated half the strings-extraction could not see
    assert "stage.mode.digital-command.get" in commands
    assert "function.waveform.sample-period.set" in commands
    assert any(c.startswith("resonance-detect.") for c in commands)


def test_every_command_the_module_sends_is_in_the_reference():
    """Guards against a typo'd command name shipping: DoCommand answers -11
    ("Invalid command name") at runtime, on the microscope PC, which is a slow
    way to find out."""
    import re
    from pathlib import Path

    from hardware.piezo_stage import reference_commands

    source = Path(__file__).resolve().parent.parent / "hardware" / "piezo_stage.py"
    # hyphens included: half the real command names carry one
    used = set(re.findall(
        r'"((?:[a-z][a-z0-9-]*\.)+[a-z0-9-]+)(?: \{[^"]*\})?"',
        source.read_text(encoding="utf-8"),
    ))
    # the same widening also catches file names quoted in the module
    not_commands = (".py", ".md", ".dll", ".ini", ".cfg", ".json", ".txt")
    sent = {c for c in used if c.count(".") >= 1 and not c.endswith(not_commands)}
    missing = sorted(sent - reference_commands())
    assert not missing, f"command names not in the extracted reference: {missing}"


def test_waveform_protocol_records_what_the_controller_reported():
    """The arities upload_waveform() encodes, read off the controller on
    2026-08-27 with GetCommandParameters/GetCommandParameterName rather than
    guessed. A wrong entry here is a wrong command at a stage that can drive
    glass into a coverslip, which is why it is pinned by a test.
    """
    from hardware import piezo_stage

    protocol = piezo_stage.WAVEFORM_PROTOCOL
    assert protocol["function.waveform.data.set"] == ("channel", "index", "value")
    assert protocol["function.waveform.count.set"] == ("channel", "value")
    assert protocol["function.waveform.sample-period.set"] == ("channel", "value")
    assert protocol["stage.position.command.set"] == ("channel", "value")
    # start/stop carry a snapshot flag, pause/unpause do not
    assert len(protocol["function.command.start"]) == 5
    assert len(protocol["function.command.stop"]) == 5
    assert len(protocol["function.command.pause"]) == 4
    assert len(protocol["function.command.unpause"]) == 4


def test_function_command_flags_are_positional_not_omitted():
    """function.command.* takes one flag per target. Sending it bare -- which
    this module used to do -- answers "Invalid command name" while locked and
    is wrong unlocked."""
    from hardware.piezo_stage import PiezoStage, PiezoStageError

    # _function_flags is pure string work, so it needs no DLL and no controller
    stage = PiezoStage.__new__(PiezoStage)
    assert stage._function_flags((1,), snapshot=False) == "0 0 1 0 0"
    assert stage._function_flags((2, 3), snapshot=True) == "1 0 0 1 1"
    assert stage._function_flags((1, 3), internal=True) == "1 1 0 1"
    with pytest.raises(PiezoStageError, match="1..3"):
        stage._function_flags((4,))
