"""Tests for runtime/ticker.py.

TWO FAKE CLOCKS, AND WHY
------------------------
:class:`ManualClock` advances only when the code under test sleeps, or when
the test jumps it by hand. That makes the scheduling arithmetic -- which tick
index comes next, what ``t_sched`` is, when StopIteration lands -- exact and
instant. But a busy-spin (``while now() < deadline: pass``) never terminates
under it, so every test using it passes ``spin_margin=0`` to remove the spin.
That is the documented requirement on :func:`sleep_until`, and the first
version of this file hung because it did not honour it.

:class:`TickingClock` advances a fixed step on every ``now()`` call, so a
spin does terminate. It is what the spin-branch tests use.

Two tests at the end use the real clock, to check that ``sleep_until``
genuinely blocks and that a Ticker's schedule does not drift. Their
tolerances are loose enough for a loaded Windows box.
"""

from __future__ import annotations

import threading
import time
from itertools import islice

import pytest

from runtime.ticker import Tick, Ticker, sleep_until


class ManualClock:
    """A clock the test advances by hand. Use with ``spin_margin=0``."""

    def __init__(self, t: float = 0.0):
        self.t = float(t)
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.slept.append(dt)
        self.t += dt

    def jump(self, dt: float) -> None:
        """Simulate a tick body that overran, without any sleeping."""
        self.t += dt


class TickingClock:
    """``now()`` advances by ``step`` per call, so a busy-spin terminates."""

    def __init__(self, t: float = 0.0, step: float = 1e-4):
        self.t = float(t)
        self.step = float(step)
        self.slept: list[float] = []
        self.calls = 0

    def now(self) -> float:
        self.calls += 1
        out = self.t
        self.t += self.step
        return out

    def sleep(self, dt: float) -> None:
        self.slept.append(dt)
        self.t += dt


def take(ticker, n):
    """First ``n`` ticks as a list.

    Not ``zip(ticker, range(n))``: zip pulls from its first iterable before
    discovering the second is exhausted, so it takes n+1 ticks and pays n
    sleeps -- which made a sleep-counting assertion here off by one.
    """
    return list(islice(ticker, n))


def manual(**kwargs):
    """A Ticker on a ManualClock with the spin removed. Returns (ticker, clock)."""
    clock = ManualClock()
    kwargs.setdefault("spin_margin", 0.0)
    return Ticker(now=clock.now, sleep=clock.sleep, **kwargs), clock


# --------------------------------------------------------------------------
# sleep_until
# --------------------------------------------------------------------------


def test_sleep_until_returns_immediately_when_the_deadline_has_passed():
    clock = ManualClock(t=5.0)
    overshoot = sleep_until(3.0, spin_margin=0.0, now=clock.now, sleep=clock.sleep)
    assert overshoot == pytest.approx(2.0)
    assert clock.slept == [], "must not sleep when already late"


def test_sleep_until_with_zero_margin_sleeps_the_whole_interval():
    clock = ManualClock(t=0.0)
    sleep_until(1.0, spin_margin=0.0, now=clock.now, sleep=clock.sleep)
    assert clock.slept == [pytest.approx(1.0)]


def test_sleep_until_sleeps_all_but_the_spin_margin_then_spins():
    clock = TickingClock(t=0.0, step=1e-5)
    sleep_until(1.0, spin_margin=0.002, now=clock.now, sleep=clock.sleep)
    assert clock.slept == [pytest.approx(0.998, abs=1e-3)], \
        "one sleep, of the interval minus the margin"
    assert clock.t >= 1.0, "the spin covered the margin"


def test_sleep_until_inside_the_margin_spins_without_sleeping():
    clock = TickingClock(t=0.9995, step=1e-5)
    sleep_until(1.0, spin_margin=0.002, now=clock.now, sleep=clock.sleep)
    assert clock.slept == [], "inside the margin it spins, it does not sleep"
    assert clock.t >= 1.0


def test_sleep_until_overshoot_is_never_negative():
    clock = ManualClock(t=0.0)
    assert sleep_until(1.0, spin_margin=0.0,
                       now=clock.now, sleep=clock.sleep) >= 0.0


def test_sleep_until_really_blocks_on_the_real_clock():
    """What is guaranteed is asserted every time; the timing quality is
    best-of-N.

    ``sleep_until`` cannot promise a deadline on a machine it does not own. A
    shared macOS CI runner descheduled this by 107.8 ms against the 20 ms
    bound this test used to assert unconditionally. What the sleep-then-spin
    mechanism *can* be held to is that it lands on the deadline when the OS
    lets it run at all -- so the tight bound is best of five. A runner that
    cannot manage it once in five tries is genuinely not usable for timing.
    """
    best = None
    for _ in range(5):
        t0 = time.perf_counter()
        overshoot = sleep_until(t0 + 0.05)
        elapsed = time.perf_counter() - t0
        # true on any machine, however contended
        assert elapsed >= 0.05
        assert overshoot >= 0.0
        best = overshoot if best is None else min(best, overshoot)
    assert best < 0.02, f"best of 5 landed {best * 1e3:.1f} ms past the deadline"


# --------------------------------------------------------------------------
# Ticker: the schedule
# --------------------------------------------------------------------------


def test_first_tick_runs_immediately_and_does_not_wait_a_period():
    ticker, clock = manual(dt=1.0)
    tick = next(iter(ticker))
    assert tick.k == 0
    assert tick.t_sched == 0.0
    assert clock.slept == [], "the first tick must not pay a period first"


def test_t0_is_taken_at_the_first_tick_not_at_construction():
    clock = ManualClock(t=100.0)
    ticker = Ticker(dt=1.0, spin_margin=0.0, now=clock.now, sleep=clock.sleep)
    assert ticker.t0 is None
    clock.jump(50.0)
    next(iter(ticker))
    assert ticker.t0 == pytest.approx(150.0)


def test_t_sched_is_exact_multiples_of_dt():
    """The reason to schedule from the tick index: 0.1 added to itself ten
    times is not 1.0, and a timestamp written to a data file has to be."""
    ticker, _ = manual(dt=0.1)
    ticks = take(ticker, 11)
    assert ticks[10].t_sched == 10 * 0.1 == 1.0

    # What the loop would have carried if it had added dt each tick. (Not
    # `sum([0.1]*10)`: CPython 3.12's sum() compensates and returns exactly
    # 1.0, which hides the very drift this is about.)
    accumulated = 0.0
    for _ in range(10):
        accumulated += 0.1
    assert accumulated != 1.0
    assert ticks[10].t_sched != accumulated


def test_ticks_are_consecutive_when_the_body_is_fast():
    ticker, _ = manual(dt=1.0)
    ks = [t.k for t in take(ticker, 5)]
    assert ks == [0, 1, 2, 3, 4]
    assert ticker.n_skipped == 0


def test_duration_stops_the_loop():
    ticker, _ = manual(dt=0.25, duration=1.0)
    ticks = list(ticker)
    # t_sched 0, .25, .5, .75 run; 1.0 is >= duration and stops it.
    assert [t.t_sched for t in ticks] == pytest.approx([0.0, 0.25, 0.5, 0.75])


def test_duration_is_measured_on_the_experiment_clock_not_the_total():
    """warmup_k * dt of preroll comes before the duration starts."""
    ticker, _ = manual(dt=1.0, duration=2.0, warmup_k=3)
    ticks = list(ticker)
    assert len(ticks) == 5, "3 preroll + 2 experiment"
    assert [t.warming for t in ticks] == [True, True, True, False, False]
    assert [t.exp_t for t in ticks] == [None, None, None, 0.0, 1.0]


def test_warmup_exp_t_is_none_during_preroll_and_exact_after():
    ticker, _ = manual(dt=0.5, warmup_k=2)
    ticks = take(ticker, 4)
    assert [t.exp_t for t in ticks] == [None, None, 0.0, 0.5]


def test_no_warmup_means_the_experiment_clock_starts_at_tick_zero():
    ticker, _ = manual(dt=1.0)
    tick = next(iter(ticker))
    assert tick.warming is False
    assert tick.exp_t == 0.0


def test_ticker_spins_to_its_deadline_by_default():
    """The default margin is not zero, so the real loop does spin."""
    clock = TickingClock(step=1e-5)
    ticker = Ticker(dt=1.0, now=clock.now, sleep=clock.sleep)
    ticks = take(ticker, 3)
    assert [t.k for t in ticks] == [0, 1, 2]
    assert len(clock.slept) == 2, "two waits for two non-first ticks"
    assert clock.slept[0] == pytest.approx(0.998, abs=1e-3)


# --------------------------------------------------------------------------
# Ticker: catch_up, the parameter that matters
# --------------------------------------------------------------------------


def test_catch_up_skips_the_periods_a_slow_body_missed():
    ticker, clock = manual(dt=1.0, catch_up=True)
    it = iter(ticker)
    assert next(it).k == 0
    clock.jump(3.4)          # the body took 3.4 periods
    second = next(it)
    assert second.k == 4, "jumps to the next deadline still in the future"
    assert second.skipped == 3
    assert second.t_sched == pytest.approx(4.0)


def test_catch_up_off_runs_every_tick_late():
    ticker, clock = manual(dt=1.0, catch_up=False)
    it = iter(ticker)
    next(it)
    clock.jump(3.4)
    second = next(it)
    assert second.k == 1, "every tick runs, however late"
    assert second.skipped == 0
    assert second.lateness == pytest.approx(2.4), "and it reports the lateness"


def test_catch_up_off_never_skips_over_a_long_stall():
    """The property the sine drive relies on today: no commanded position is
    dropped, whatever happens to the clock."""
    ticker, clock = manual(dt=0.1, catch_up=False)
    it = iter(ticker)
    ks = [next(it).k]
    for _ in range(4):
        clock.jump(5.0)      # a 50-period stall, every time
        ks.append(next(it).k)
    assert ks == [0, 1, 2, 3, 4]
    assert ticker.n_skipped == 0


def test_lateness_is_zero_when_the_loop_keeps_up():
    ticker, _ = manual(dt=1.0)
    ticks = take(ticker, 4)
    assert [t.lateness for t in ticks] == pytest.approx([0, 0, 0, 0])


def test_t_actual_reports_when_the_body_really_started():
    ticker, clock = manual(dt=1.0, catch_up=False)
    it = iter(ticker)
    next(it)
    clock.jump(2.5)
    tick = next(it)
    assert tick.t_sched == pytest.approx(1.0)
    assert tick.t_actual == pytest.approx(2.5)


# --------------------------------------------------------------------------
# Ticker: stopping
# --------------------------------------------------------------------------


def test_stop_event_ends_iteration():
    clock = ManualClock()
    stop = threading.Event()
    ticker = Ticker(dt=1.0, stop_event=stop, spin_margin=0.0,
                    now=clock.now, sleep=clock.sleep)
    it = iter(ticker)
    next(it)
    next(it)
    stop.set()
    with pytest.raises(StopIteration):
        next(it)


def test_stop_event_set_before_the_first_tick_yields_nothing():
    stop = threading.Event()
    stop.set()
    clock = ManualClock()
    assert list(Ticker(dt=1.0, stop_event=stop, duration=10.0, spin_margin=0.0,
                       now=clock.now, sleep=clock.sleep)) == []


def test_stop_event_is_checked_after_the_wait_not_only_before():
    """A stop that arrives while the loop is asleep must not cost a whole
    extra tick body -- for a long dt that is the difference between a prompt
    stop and a hung one."""
    clock = ManualClock()
    stop = threading.Event()

    def sleep(dt):
        clock.sleep(dt)
        stop.set()          # the stop lands during the wait

    ticker = Ticker(dt=1.0, stop_event=stop, spin_margin=0.0,
                    now=clock.now, sleep=sleep)
    assert len(take(ticker, 5)) == 1


def test_iteration_stays_stopped():
    ticker, _ = manual(dt=1.0, duration=1.0)
    list(ticker)
    with pytest.raises(StopIteration):
        next(iter(ticker))


# --------------------------------------------------------------------------
# Ticker: validation and reporting
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"dt": 0.0}, "dt"),
        ({"dt": -1.0}, "dt"),
        ({"dt": 1.0, "warmup_k": -1}, "warmup_k"),
        ({"dt": 1.0, "duration": 0.0}, "duration"),
        ({"dt": 1.0, "duration": -5.0}, "duration"),
    ],
)
def test_bad_arguments_are_refused(kwargs, match):
    with pytest.raises(ValueError, match=match):
        Ticker(**kwargs)


def test_default_spin_margin_follows_dt():
    assert Ticker(dt=1.0).spin_margin == pytest.approx(0.002)
    assert Ticker(dt=0.004).spin_margin == pytest.approx(0.001), "dt/4 below 8 ms"


def test_report_says_no_ticks_before_anything_ran():
    assert Ticker(dt=1.0).report() == "no ticks"


def test_report_counts_skipped_periods_and_names_the_cause():
    ticker, clock = manual(dt=1.0)
    it = iter(ticker)
    next(it)
    clock.jump(5.5)
    next(it)
    line = ticker.report()
    assert "2 ticks" in line
    assert "5 periods skipped" in line
    assert "does not fit dt" in line


def test_report_on_a_healthy_loop_says_nothing_was_skipped():
    ticker, _ = manual(dt=1.0)
    take(ticker, 4)
    line = ticker.report()
    assert "0 periods skipped" in line
    assert "does not fit" not in line


def test_report_states_when_catch_up_is_off():
    ticker, _ = manual(dt=1.0, catch_up=False)
    take(ticker, 3)
    assert "catch_up off" in ticker.report()


def test_n_ticks_and_n_skipped_track_the_loop():
    ticker, clock = manual(dt=1.0)
    it = iter(ticker)
    next(it)
    clock.jump(2.2)
    next(it)
    assert ticker.n_ticks == 2
    assert ticker.n_skipped == 2


def test_tick_is_immutable():
    tick = Tick(k=0, t_sched=0.0, t_actual=0.0, lateness=0.0,
                skipped=0, warming=False, exp_t=0.0)
    with pytest.raises(Exception):
        tick.k = 1


def test_real_clock_schedule_does_not_drift():
    """20 ticks of 5 ms on the real clock. The exact assertion is the point:
    ``t_sched`` is arithmetic on the tick index, exact to the last bit however
    badly the loop ran.

    It is NOT ``19 * dt``, and asserting that was this test's own bug.
    ``catch_up=True`` is the default and it *skips* indices -- ``Tick.k``:
    "With catch_up=True this skips values, and the skipped ones are the
    periods that were missed". So on a loaded machine the twentieth tick
    yielded carries an index above 19, and the old assertion passed only on
    hardware fast enough never to miss a 5 ms period. A shared macOS CI
    runner reached k=61 (t_sched 0.305) and failed it. The invariants below
    are the ones the docstring was reaching for, and they hold anywhere.
    """
    dt = 0.005
    ticker = Ticker(dt=dt)
    t_wall = time.perf_counter()
    ticks = take(ticker, 20)
    elapsed = time.perf_counter() - t_wall

    # the real invariant: exact arithmetic on the index, to the last bit
    for tick in ticks:
        assert tick.t_sched == tick.k * dt

    # the schedule only ever advances, and never repeats an index
    assert [t.k for t in ticks] == sorted({t.k for t in ticks})
    assert ticks[0].k == 0
    # equality only when nothing was skipped; a slow machine skips
    assert ticks[-1].k >= len(ticks) - 1
    assert ticks[-1].t_sched >= (len(ticks) - 1) * dt

    # whatever was skipped is accounted for rather than silently dropped
    assert ticker.n_skipped == ticks[-1].k + 1 - len(ticks)

    # the loop cannot have finished before the schedule it actually kept
    assert elapsed >= ticks[-1].t_sched, ticker.report()
