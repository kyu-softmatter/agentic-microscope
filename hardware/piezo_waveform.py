"""Waveform sample generation for the NPC-D piezo, in picometres.

The piezo's counterpart to hardware/tweezers_patterns.py, and for the same
reason: the controller has a **hardware waveform generator**, so a trajectory
whose timing matters gets uploaded and played by the instrument rather than
streamed from Python.

That the generator exists is settled -- the DLL carries a `function.*` command
family (upload data, set a point count, set an iteration count, start/stop/
pause/unpause, read state), and the vendor's own examples name it: `function_setup`
"demonstrates using function playback to construct simple **raster profiles**",
`function_waveform_demo` "demonstrates using the waveform generator to construct
a waveform" (library manual 11.1). Extracted list and provenance:
reference/npcd-command-set.md.

WHAT THIS MODULE DOES AND DOES NOT DO
-------------------------------------
It builds and validates sample arrays. ``piezo_stage.upload_waveform()`` loads
them, and as of 2026-08-27 that path is open: the signature was read off the
controller (``function.waveform.data.set channel index value``, see
``piezo_stage.WAVEFORM_PROTOCOL``) rather than guessed. Two things to know before
using it. The upload is one command per sample over a ~0.7 ms round trip, so the
sample count, not the sample period, is what costs time. And every
``function.*.set`` is invisible until the controller's security level is raised,
so an upload without ``piezo_stage.unlock()`` fails with "Invalid command name",
which does not sound like the permission problem it is.

UNITS
-----
Picometres throughout, because that is what `stage.position.measured.get`
returns for a linear stage. **Do not take that as given**: library manual 5.2
says a distance may be reported in picometres for linear stages or picoradians
for angular ones, and that applications "should always check the units used for
a parameter or return value". The verify script prints them.

THE TIMEBASE
------------
Settable, per channel: ``function.waveform.sample-period.set channel value`` in
seconds. It reads back 2.0e-5 out of the box, the same 20 us as
``controller.sampling-time.get``, so the generator advances on the servo clock
by default -- 50 kHz, which is roughly 1000x faster than the ~0.7 ms host round
trip a Python loop is stuck with.

A ``Waveform`` here still has a shape and a length but **no** duration:
``duration_s()`` takes the period as an argument and will not invent one, since
the period lives on the controller and can differ per channel.

Still unread on the real controller: the trigger plumbing that would start the
piezo and the camera off one edge -- ``function.trigger-inputs.*``,
``function.trigger-output.*``, and ``controller.synchronisation.master/slave``.
All present in the command set (2026-08-27), none exercised.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

PM_PER_UM = 1_000_000.0


@dataclass(frozen=True)
class StageTravel:
    """Usable travel and the smallest commandable step, both in picometres.

    Required rather than defaulted: a wrong travel bound is how a generated
    waveform ends up commanding the stage into its end stop. ``OBSERVED``
    below is a documented starting point, not a substitute for reading the real
    values off the controller.
    """

    min_pm: float
    max_pm: float
    resolution_pm: float

    def __post_init__(self) -> None:
        if self.max_pm <= self.min_pm:
            raise WaveformError("travel max must exceed min")
        if self.resolution_pm <= 0:
            raise WaveformError("resolution must be positive")

    @property
    def span_pm(self) -> float:
        return self.max_pm - self.min_pm

    @property
    def centre_pm(self) -> float:
        return 0.5 * (self.min_pm + self.max_pm)

    def contains(self, value_pm: float) -> bool:
        return self.min_pm <= value_pm <= self.max_pm

    def quantise(self, value_pm: float) -> float:
        """Snap to the controller's step. Reported, not hidden: a caller that
        asks for an amplitude near the step should see what it gets."""
        return self.min_pm + round((value_pm - self.min_pm) / self.resolution_pm) * self.resolution_pm


#: Travel and command step **read off the controller** on 2026-08-27 (COM4,
#: firmware 6.7.8, stage SP-XYZ-600), replacing figures borrowed from NIS.
#:
#: Travel: ``stage.position.calibrated-range.minimum/maximum.get`` answer 0 and
#: 6.0e8 on all three axes -- 0..600 um, identical for x, y and z. That the
#: number is 6.0e8 for a 600 um stage is also the cross-check that positions on
#: this interface are picometres, which no units query would confirm (the DLL
#: answers empty, when it does not access-violate -- piezo_stage.command_results).
#:
#: Step: measured, not looked up. Commanding channel 1 in 2 pm increments and
#: reading ``stage.position.command.get`` back shows the command grid stepping in
#: **32 pm**. That is the *command* quantisation only -- what the controller will
#: accept as distinct. It is nowhere near what the stage delivers: during a 1 Hz
#: 10 um sweep the readback sat 330 nm (median) from the commanded position, and
#: settling dominates everything at this scale.
#:
#: The old figures here -- 400 um travel, 0.0122 um step -- came from NIS's
#: analogue abstraction of this same controller (0-10 V mapped to 0-400 um,
#: kb/systems/current.md). Both were wrong for this path: the travel by 200 um,
#: the step by a factor of ~380. NIS's own scaling also disagrees with the
#: controller, which reports ``stage.command.analogue.scaling.get`` = 60,
#: consistent with 600 um over its 10 V input rather than 400.
CALIBRATED = StageTravel(
    min_pm=0.0, max_pm=600.0 * PM_PER_UM, resolution_pm=32.0
)

#: Kept as the name callers already use. It is the same object, so an
#: ``is CALIBRATED`` identity check holds.
OBSERVED = CALIBRATED


class WaveformError(ValueError):
    """Raised for a waveform the controller would clip, or refuse."""


@dataclass(frozen=True)
class Waveform:
    """An ordered sample array for one channel, in picometres.

    Order is the trajectory: the generator plays sample 0, 1, 2 ... and repeats
    for however many iterations are set. Length is known; duration is not, until
    someone supplies the sample period -- see the module docstring.
    """

    samples: tuple[float, ...]
    channel: int
    name: str = "waveform"

    def __post_init__(self) -> None:
        if not self.samples:
            raise WaveformError("a waveform needs at least one sample")
        if self.channel < 1:
            raise WaveformError("channels are 1-based")

    def __len__(self) -> int:
        return len(self.samples)

    # ---- range and resolution ----

    @property
    def span_pm(self) -> tuple[float, float]:
        return min(self.samples), max(self.samples)

    def fits_within(self, travel: StageTravel) -> bool:
        lo, hi = self.span_pm
        return travel.contains(lo) and travel.contains(hi)

    def check(self, travel: StageTravel) -> None:
        """Raise unless every sample is inside ``travel``.

        Refusing rather than clipping, deliberately: silently clipping a
        trajectory is the failure mode the tweezers' trapping range has (points
        outside are clipped with no error), and it produces data that looks
        fine and is wrong.
        """
        lo, hi = self.span_pm
        if not self.fits_within(travel):
            raise WaveformError(
                f"{self.name}: samples span {lo / PM_PER_UM:.4f}..{hi / PM_PER_UM:.4f} um, "
                f"outside travel {travel.min_pm / PM_PER_UM:.4f}.."
                f"{travel.max_pm / PM_PER_UM:.4f} um"
            )

    def quantised(self, travel: StageTravel) -> Waveform:
        return replace(self, samples=tuple(travel.quantise(s) for s in self.samples))

    def quantisation_error_pm(self, travel: StageTravel) -> float:
        """Largest single-sample error the controller's step will introduce.

        Worth checking before trusting a small-amplitude waveform: on a 12.2 nm
        step, a 20 nm amplitude triangle is three levels, not a ramp.
        """
        q = self.quantised(travel)
        return max(abs(a - b) for a, b in zip(self.samples, q.samples))

    # ---- timing, only with a period supplied ----

    def duration_s(self, sample_period_s: float, iterations: int = 1) -> float:
        if sample_period_s <= 0:
            raise WaveformError("sample period must be positive")
        if iterations < 1:
            raise WaveformError("iterations must be >= 1")
        return len(self.samples) * sample_period_s * iterations

    def peak_speed_um_s(self, sample_period_s: float) -> float:
        """Largest sample-to-sample step divided by the period -- the number to
        compare against what the stage can actually follow."""
        if sample_period_s <= 0:
            raise WaveformError("sample period must be positive")
        steps = [
            abs(b - a) for a, b in zip(self.samples, self.samples[1:] + self.samples[:1])
        ]
        return max(steps) / PM_PER_UM / sample_period_s


# ---- generators: samples in traversal order ---------------------------


def _centred(travel: StageTravel | None, centre_pm: float | None) -> float:
    if centre_pm is not None:
        return centre_pm
    if travel is not None:
        return travel.centre_pm
    raise WaveformError("give either centre_pm or travel to centre on")


def ramp(
    start_pm: float, stop_pm: float, n_samples: int, channel: int = 1
) -> Waveform:
    """One-way linear sweep, endpoints included. Not closed -- playing it on
    repeat jumps back to the start, which for a stage is a real retrace."""
    if n_samples < 2:
        raise WaveformError("a ramp needs at least 2 samples")
    step = (stop_pm - start_pm) / (n_samples - 1)
    return Waveform(
        tuple(start_pm + i * step for i in range(n_samples)),
        channel,
        name=f"ramp_{start_pm / PM_PER_UM:g}to{stop_pm / PM_PER_UM:g}um_n{n_samples}",
    )


def triangle(
    amplitude_pm: float,
    n_samples: int,
    channel: int = 1,
    centre_pm: float | None = None,
    travel: StageTravel | None = None,
) -> Waveform:
    """Closed there-and-back sweep, no repeated turning point.

    Same construction as the tweezers' ``oscillation``: a forward leg of k
    samples reuses the k-2 interior ones on the way back, so the cycle is
    2k-2 = n_samples long and neither extreme is commanded twice in a row.
    """
    if n_samples < 4 or n_samples % 2:
        raise WaveformError("n_samples must be even and >= 4 (two equal legs)")
    c = _centred(travel, centre_pm)
    per_leg = (n_samples + 2) // 2
    forward = [
        c - amplitude_pm + 2 * amplitude_pm * i / (per_leg - 1) for i in range(per_leg)
    ]
    samples = forward + list(reversed(forward))[1:-1]
    return Waveform(
        tuple(samples),
        channel,
        name=f"triangle_a{amplitude_pm / PM_PER_UM:g}um_n{len(samples)}",
    )


def sine(
    amplitude_pm: float,
    n_samples: int,
    channel: int = 1,
    centre_pm: float | None = None,
    travel: StageTravel | None = None,
) -> Waveform:
    """One full cycle, closed. ``n_samples`` points at 2*pi/n spacing, so the
    last sample does not duplicate the first."""
    if n_samples < 4:
        raise WaveformError("a sine needs at least 4 samples")
    c = _centred(travel, centre_pm)
    return Waveform(
        tuple(
            c + amplitude_pm * math.sin(2 * math.pi * i / n_samples)
            for i in range(n_samples)
        ),
        channel,
        name=f"sine_a{amplitude_pm / PM_PER_UM:g}um_n{n_samples}",
    )


def staircase(
    start_pm: float,
    step_pm: float,
    n_steps: int,
    dwell_samples: int,
    channel: int = 1,
) -> Waveform:
    """Discrete levels, each held for ``dwell_samples``.

    The shape for step-response and settling measurements: hold, step, hold.
    Pair it with ``snapshot.*`` capture to see how long the stage actually takes
    to arrive.
    """
    if n_steps < 1 or dwell_samples < 1:
        raise WaveformError("n_steps and dwell_samples must both be >= 1")
    samples = [
        start_pm + i * step_pm for i in range(n_steps) for _ in range(dwell_samples)
    ]
    return Waveform(
        tuple(samples),
        channel,
        name=f"staircase_{n_steps}x{step_pm / PM_PER_UM:g}um_dwell{dwell_samples}",
    )


def raster_pair(
    fast_amplitude_pm: float,
    slow_amplitude_pm: float,
    n_fast: int,
    n_lines: int,
    fast_channel: int = 1,
    slow_channel: int = 2,
    centre_fast_pm: float | None = None,
    centre_slow_pm: float | None = None,
    travel: StageTravel | None = None,
) -> tuple[Waveform, Waveform]:
    """Two equal-length waveforms that together raster an area.

    A hardware raster is two channels playing synchronised arrays, so both come
    back the same length and must be started together -- which is what
    ``controller.synchronisation.master``/``slave`` is presumably for, and one
    of the things to establish on the real controller.

    The fast axis sweeps and retraces (serpentine, so consecutive lines stay
    adjacent and there is no full-width flyback); the slow axis steps once per
    line and holds.
    """
    if n_fast < 2 or n_lines < 1:
        raise WaveformError("n_fast must be >= 2 and n_lines >= 1")
    cf = _centred(travel, centre_fast_pm)
    cs = _centred(travel, centre_slow_pm)

    line = [
        cf - fast_amplitude_pm + 2 * fast_amplitude_pm * i / (n_fast - 1)
        for i in range(n_fast)
    ]
    fast: list[float] = []
    slow: list[float] = []
    for j in range(n_lines):
        fast.extend(line if j % 2 == 0 else list(reversed(line)))
        y = (
            cs
            if n_lines == 1
            else cs - slow_amplitude_pm + 2 * slow_amplitude_pm * j / (n_lines - 1)
        )
        slow.extend([y] * n_fast)
    return (
        Waveform(tuple(fast), fast_channel, name=f"raster_fast_{n_fast}x{n_lines}"),
        Waveform(tuple(slow), slow_channel, name=f"raster_slow_{n_fast}x{n_lines}"),
    )
