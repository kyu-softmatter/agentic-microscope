"""Deterministic-period loop clock: sleep-then-spin, with a catch-up choice.

Extracted from the Takatori-lab bacteria stack, where the same twenty lines
are inlined into four separate worker loops (``lib/controller.py:139-233`` is
the one its own docstring calls canonical; ``lib/pi_test.py``,
``lib/pattern_test.py`` and ``lib/chamber_session.py`` each carry a copy).
Four copies of a timing loop is four places for the timing to differ, which
is the reason to have this as a function.

THE THREE IDEAS
---------------
**Sleep to nearly the deadline, then spin.** ``time.sleep`` on Windows is
accurate to about a millisecond at best and can overshoot by more, so a loop
that sleeps the whole interval arrives late by a random amount every tick.
Sleeping until ``deadline - spin_margin`` and busy-waiting the rest costs one
short burst of CPU per tick and lands on the deadline. The margin defaults to
``min(2 ms, dt/4)`` -- the bacteria rig's figure.

**Schedule from tick index, not from accumulation.** The scheduled time of
tick ``k`` is ``t0 + k*dt``, computed fresh each tick. Adding ``dt`` to a
running total instead makes every tick's error permanent, and the loop's idea
of elapsed time drifts away from the wall clock without ever reporting that
it did. :attr:`Tick.t_sched` is an exact multiple of ``dt``, always, and is
the value to write into a data file.

**Decide explicitly what a missed period means.** If a tick body overran, the
next deadline is already in the past. There are two defensible answers and
they are not interchangeable:

``catch_up=True`` (the default)
    Skip the missed ticks: jump ``k`` forward to the next deadline that is
    still in the future. The loop stays on the clock and the schedule stays
    honest about when things happened. This is what a control loop wants --
    a controller that overran should act on the present, not work through a
    backlog. It is also what a sampling loop wants: a skipped sample is
    visible in the record, a late one silently misdates the data.

``catch_up=False``
    Run every tick, late. Use this when the ticks are a *sequence that must
    not lose members* rather than samples of a clock -- the case here is
    ``config/tweezers/trap_from_tracking.py:stream_sine``, which sends a
    pre-computed position series to the trap. Which answer that loop actually
    wants is a physics question this module does not settle; see the note
    below.

WHICH ONE THE SINE DRIVE WANTS -- NOT SETTLED
---------------------------------------------
``stream_sine`` currently behaves as ``catch_up=False``: it iterates a
pre-computed schedule and sends every point, so a stall is followed by a
burst of positions sent back-to-back, and ``stream_report`` prints the
cumulative lateness that results. Switching it to ``catch_up=True`` would
instead move the trap to where the waveform says it should be *now* and drop
the backlog -- arguably the better drive, since a burst of stale positions
deforms the waveform in a way the fit cannot see, while a skipped point
merely thins it.

That is a change to a drive that has produced a measurement, so this module
offers both and changes nothing. Deciding it needs a run with the stage
tracked, comparing the fitted amplitude under each.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

__all__ = ["sleep_until", "Tick", "Ticker"]


def sleep_until(
    deadline: float,
    *,
    spin_margin: float = 0.002,
    now: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Block until ``now() >= deadline``. Returns the overshoot in seconds.

    Sleeps while there is more than ``spin_margin`` to go, then busy-waits.
    Returns ``now() - deadline`` at the moment it gives up control, which is
    >= 0 and is the honest measure of how well this worked -- a caller that
    wants to know whether the tick landed should record it rather than assume
    it was zero.

    Returns immediately (with a positive overshoot) if the deadline has
    already passed, so this is safe to call on a loop that is behind.

    ⚠ An injected ``now`` must advance on its own, because the spin is
    ``while now() < deadline: pass`` and nothing inside it moves the clock. A
    test clock that only advances when ``sleep`` is called will hang here
    unless it is used with ``spin_margin=0``, which removes the spin. This is
    a property of busy-waiting rather than a bug -- but it bit the first
    version of these tests, so it is written down.

    Parameters
    ----------
    deadline : float
        Target time on ``now()``'s clock.
    spin_margin : float, optional
        Switch from sleeping to spinning with this much time left. Zero
        disables the spin entirely, which trades deadline accuracy for not
        burning a core -- reasonable at ``dt`` of a second, not at 20 ms.
    now, sleep : callable, optional
        Injected for tests.
    """
    while True:
        remaining = deadline - now()
        if remaining <= 0:
            return -remaining
        if remaining > spin_margin:
            sleep(remaining - spin_margin)
        else:
            while now() < deadline:
                pass
            return now() - deadline


@dataclass(frozen=True)
class Tick:
    """One iteration of a :class:`Ticker`.

    Attributes
    ----------
    k : int
        Tick index since ``t0``, counting from 0. With ``catch_up=True`` this
        skips values, and the skipped ones are the periods that were missed.
    t_sched : float
        ``k * dt`` -- when this tick was *due*, relative to ``t0``. An exact
        multiple of ``dt``. This is the timestamp to record.
    t_actual : float
        When the tick body actually started, relative to ``t0``. Differs from
        ``t_sched`` by :attr:`lateness`.
    lateness : float
        ``t_actual - t_sched``, in seconds. Never negative.
    skipped : int
        Periods skipped between the previous tick and this one. Always 0 when
        ``catch_up=False``.
    warming : bool
        ``True`` while ``k < warmup_k``. The preroll: hardware is being held
        at its initial state and the experiment clock has not started.
    exp_t : float or None
        ``(k - warmup_k) * dt`` once past the preroll, and ``None`` during
        it. The experiment-relative clock, exact.
    """

    k: int
    t_sched: float
    t_actual: float
    lateness: float
    skipped: int
    warming: bool
    exp_t: Optional[float]


class Ticker:
    """Fixed-period loop clock. Iterate it; the tick body is the loop body.

    ::

        ticker = Ticker(dt=0.02, duration=10.0, warmup_k=5)
        for tick in ticker:
            frame = source.fresh(last_seq)
            ...
            ot.set_trap_position(name, *waveform(tick.exp_t))
        print(ticker.report())

    Blocking happens in ``__next__``, before the body runs, so the body always
    starts on (or as close as the OS allows to) ``t_sched``. ``t0`` is taken
    when the first tick is requested, not at construction, so building a
    Ticker ahead of time costs nothing.

    Parameters
    ----------
    dt : float
        Tick period, seconds. Must be > 0.
    duration : float, optional
        Stop once the *experiment* clock reaches this, i.e. after
        ``warmup_k * dt + duration`` seconds total. ``None`` runs until
        ``stop_event`` or the caller breaks.
    warmup_k : int, optional
        Preroll ticks before the experiment clock starts. During the preroll
        :attr:`Tick.warming` is True and :attr:`Tick.exp_t` is None. The
        bacteria stack uses this to hold an initial pattern while the sample
        settles, and to let a PI controller's error history fill without the
        derivative term seeing a step.
    catch_up : bool, optional
        What a missed period means. See the module docstring -- this is the
        one parameter worth reading about before setting.
    spin_margin : float, optional
        Passed to :func:`sleep_until`. Defaults to ``min(2 ms, dt/4)``.
    stop_event : threading.Event, optional
        Checked before each tick; when set, iteration ends. The cooperative
        stop, so a Ctrl-C handler or a worker supervisor can end the loop
        without the body having to poll.
    now, sleep : callable, optional
        Injected for tests.
    """

    def __init__(
        self,
        dt: float,
        *,
        duration: Optional[float] = None,
        warmup_k: int = 0,
        catch_up: bool = True,
        spin_margin: Optional[float] = None,
        stop_event: Optional["object"] = None,
        now: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if dt <= 0:
            raise ValueError(f"dt must be > 0, got {dt}")
        if warmup_k < 0:
            raise ValueError(f"warmup_k must be >= 0, got {warmup_k}")
        if duration is not None and duration <= 0:
            raise ValueError(f"duration must be > 0 or None, got {duration}")
        self.dt = float(dt)
        self.duration = None if duration is None else float(duration)
        self.warmup_k = int(warmup_k)
        self.catch_up = bool(catch_up)
        self.spin_margin = (
            min(0.002, 0.25 * self.dt) if spin_margin is None else float(spin_margin)
        )
        self._stop_event = stop_event
        self._now = now
        self._sleep = sleep

        self.t0: Optional[float] = None
        self._k = 0
        self._n = 0
        self._skipped = 0
        self._lateness: list[float] = []
        self._done = False

    # ------------------------------------------------------------------ #
    # iteration
    # ------------------------------------------------------------------ #

    def __iter__(self) -> Iterator[Tick]:
        return self

    def __next__(self) -> Tick:
        if self._done:
            raise StopIteration
        if self._stop_event is not None and self._stop_event.is_set():
            self._done = True
            raise StopIteration

        if self.t0 is None:
            # First tick runs immediately: its deadline is t0 itself, so there
            # is nothing to wait for and the loop does not pay a full period
            # before doing any work.
            self.t0 = self._now()
            overshoot = 0.0
        else:
            self._advance()
            if self._stop_event is not None and self._stop_event.is_set():
                self._done = True
                raise StopIteration
            overshoot = sleep_until(
                self.t0 + self._k * self.dt,
                spin_margin=self.spin_margin,
                now=self._now,
                sleep=self._sleep,
            )
            # Check again after the wait, not only before it. Most of a tick
            # is spent inside sleep_until, so a stop that arrives 10 ms into a
            # 1 s wait would otherwise still cost a whole tick body -- and for
            # a body that moves a stage or a trap, "one more tick" is the
            # difference between stopping and not.
            if self._stop_event is not None and self._stop_event.is_set():
                self._done = True
                raise StopIteration

        t_sched = self._k * self.dt
        exp_k = self._k - self.warmup_k
        warming = exp_k < 0
        exp_t = None if warming else exp_k * self.dt

        if self.duration is not None and exp_t is not None and exp_t >= self.duration:
            self._done = True
            raise StopIteration

        self._n += 1
        self._lateness.append(overshoot)
        return Tick(
            k=self._k,
            t_sched=t_sched,
            t_actual=self._now() - self.t0,
            lateness=overshoot,
            skipped=self._skipped,
            warming=warming,
            exp_t=exp_t,
        )

    def _advance(self) -> None:
        """Choose the next tick index. This is where catch_up lives.

        ``max(k+1, floor(elapsed/dt)+1)`` is the whole of the catch-up rule:
        normally the max picks ``k+1``, and only when the body overran by more
        than a period does the floor term win and skip the ones that were
        missed.
        """
        assert self.t0 is not None
        if not self.catch_up:
            self._k += 1
            self._skipped = 0
            return
        elapsed = self._now() - self.t0
        nxt = max(self._k + 1, int(elapsed // self.dt) + 1)
        self._skipped = nxt - self._k - 1
        self._k = nxt

    # ------------------------------------------------------------------ #
    # reporting
    # ------------------------------------------------------------------ #

    @property
    def n_ticks(self) -> int:
        """Ticks yielded so far."""
        return self._n

    @property
    def n_skipped(self) -> int:
        """Periods skipped so far. Always 0 when ``catch_up=False``."""
        return self._k + 1 - self._n if self._n else 0

    def report(self) -> str:
        """One line on how well the loop held its period.

        The lateness figures are :func:`sleep_until`'s overshoot, i.e. how far
        past the deadline control returned -- they measure the sleep/spin, not
        the tick body. Skips measure the body.
        """
        if not self._n:
            return "no ticks"
        late = self._lateness
        mean = sum(late) / len(late)
        worst = max(late)
        # Population std; a sample std on n=1 is undefined and this line is
        # diagnostic, not inferential.
        var = sum((x - mean) ** 2 for x in late) / len(late)
        out = (f"{self._n} ticks at dt={self.dt * 1e3:.1f} ms: "
               f"late {mean * 1e3:.2f} +- {var ** 0.5 * 1e3:.2f} ms "
               f"(max {worst * 1e3:.2f})")
        if self.catch_up:
            skipped = self.n_skipped
            out += f", {skipped} periods skipped"
            if skipped:
                out += (f" ({100.0 * skipped / (self._n + skipped):.0f}% of the "
                        f"schedule -- the body does not fit dt)")
        else:
            out += ", catch_up off (no periods skipped, ticks ran late instead)"
        return out
