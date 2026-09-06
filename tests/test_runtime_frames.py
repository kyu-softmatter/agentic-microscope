"""Tests for runtime/frames.py -- the one-slot ring and the drain thread.

The drain thread is real (there is no way to test a thread's behaviour
without running it), but the core it talks to is a fake whose buffer the test
controls, so the assertions are about counts and ordering rather than about
timing. The one place a wall-clock wait appears, `_settle`, waits for a
condition with a generous ceiling instead of sleeping a fixed time.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from runtime.frames import Frame, FrameSource, FrameStats, Latest


# --------------------------------------------------------------------------
# fake core
# --------------------------------------------------------------------------


class FakeCore:
    """Minimum surface FrameSource needs, with a buffer the test drives.

    ``push`` puts frames in; the source pops them. Flat buffers by default,
    the way plain pymmcore hands them over, so the reshape path is exercised.
    """

    def __init__(self, h: int = 4, w: int = 6, *, flat: bool = True):
        self.h = h
        self.w = w
        self.flat = flat
        self._buf: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.pops = 0
        self.raise_on_pop = 0  # pop this many times with an error first

    def push(self, fill: int) -> None:
        frame = np.full((self.h, self.w), fill, dtype=np.uint16)
        with self._lock:
            self._buf.append(frame.ravel() if self.flat else frame)

    def getRemainingImageCount(self) -> int:  # noqa: N802 - MMCore spelling
        with self._lock:
            return len(self._buf)

    def popNextImage(self):  # noqa: N802 - MMCore spelling
        if self.raise_on_pop > 0:
            self.raise_on_pop -= 1
            raise RuntimeError("camera said no")
        with self._lock:
            self.pops += 1
            return self._buf.pop(0)

    def getImageHeight(self) -> int:  # noqa: N802 - MMCore spelling
        return self.h

    def getImageWidth(self) -> int:  # noqa: N802 - MMCore spelling
        return self.w


def _settle(predicate, timeout: float = 2.0) -> bool:
    """Poll until ``predicate()`` or the timeout. Returns whether it held."""
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if predicate():
            return True
        time.sleep(0.002)
    return predicate()


# --------------------------------------------------------------------------
# Latest
# --------------------------------------------------------------------------


def test_latest_starts_empty():
    assert Latest().get() is None


def test_latest_keeps_only_the_last_put():
    ring = Latest()
    ring.put(0, "a")
    ring.put(1, "b")
    assert ring.get() == (1, "b")


def test_latest_seq_comes_from_the_producer_not_a_call_count():
    """The whole point of taking seq as an argument -- it has to be able to
    mean "images out of the camera", which skips when frames are dropped."""
    ring = Latest()
    ring.put(0, "first")
    ring.put(7, "eighth")  # six frames were dropped in between
    assert ring.get()[0] == 7


def test_latest_clear():
    ring = Latest()
    ring.put(3, "x")
    ring.clear()
    assert ring.get() is None


def test_latest_get_is_stable_under_concurrent_put():
    """A reader must never see a half-written slot: it gets either the old
    tuple or the new one, never a mix."""
    ring = Latest()
    ring.put(0, (0, 0))
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            i += 1
            ring.put(i, (i, i))

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        for _ in range(2000):
            seq, payload = ring.get()
            assert payload == (seq, seq)
    finally:
        stop.set()
        t.join(timeout=1.0)


# --------------------------------------------------------------------------
# FrameSource: shape and basic delivery
# --------------------------------------------------------------------------


def test_flat_buffer_is_reshaped():
    core = FakeCore(h=4, w=6, flat=True)
    core.push(11)
    with FrameSource(core) as source:
        frame = source.wait(timeout=2.0)
    assert frame.data.shape == (4, 6)
    assert frame.data[0, 0] == 11


def test_already_shaped_buffer_passes_through():
    """pymmcore-plus reshapes for you; reshaping to the same shape is free."""
    core = FakeCore(h=4, w=6, flat=False)
    core.push(12)
    with FrameSource(core) as source:
        frame = source.wait(timeout=2.0)
    assert frame.data.shape == (4, 6)


def test_reshape_recovers_when_the_roi_changed_under_it():
    """The cached shape is re-read once on a size mismatch rather than
    failing the pass, because an ROI change mid-run is a real thing."""
    core = FakeCore(h=4, w=6)
    core.push(1)
    with FrameSource(core) as source:
        assert source.wait(timeout=2.0).data.shape == (4, 6)
        core.h, core.w = 2, 3  # ROI shrank; next frames are a new size
        core.push(2)
        assert _settle(lambda: (source.latest().data.shape == (2, 3)))


def test_wait_raises_with_a_diagnostic_when_no_frame_arrives():
    core = FakeCore()  # nothing pushed
    with FrameSource(core) as source:
        with pytest.raises(TimeoutError, match="startContinuousSequenceAcquisition"):
            source.wait(timeout=0.15)


def test_latest_is_none_before_anything_arrives():
    with FrameSource(FakeCore()) as source:
        assert source.latest() is None


# --------------------------------------------------------------------------
# FrameSource: seq, drops, and the getLastImage replacement
# --------------------------------------------------------------------------


def test_seq_counts_images_popped_not_publishes():
    """The property the three-pixel dupe check cannot provide: seq gaps are
    exactly the frames the consumer did not see."""
    core = FakeCore()
    for fill in range(10):
        core.push(fill)
    with FrameSource(core, max_drain=4) as source:
        assert _settle(lambda: source.stats().popped == 10)
        frame = source.latest()
    # Ten frames went past; the last one popped is index 9.
    assert frame.seq == 9
    assert frame.data[0, 0] == 9


def test_drain_keeps_the_newest_and_counts_the_rest_as_dropped():
    core = FakeCore()
    for fill in range(4):
        core.push(fill)
    with FrameSource(core, max_drain=4) as source:
        assert _settle(lambda: source.stats().popped == 4)
        frame = source.latest()
        stats = source.stats()
    assert frame.data[0, 0] == 3, "kept frame must be the newest of the drain"
    assert stats.dropped == 3
    assert frame.n_dropped == 3


def test_max_drain_bounds_one_pass_and_the_backlog_clears_over_several():
    core = FakeCore()
    for fill in range(9):
        core.push(fill)
    with FrameSource(core, max_drain=2) as source:
        assert _settle(lambda: source.stats().popped == 9)
    # Nine frames at two per pass is five passes; nothing is lost, it just
    # takes more of them.
    assert core.pops == 9


def test_fresh_returns_nothing_until_a_new_frame_lands():
    """This is the call that replaces the pixel-signature duplicate check."""
    core = FakeCore()
    core.push(1)
    with FrameSource(core) as source:
        first = source.wait(timeout=2.0)
        assert source.fresh(first.seq) is None, "same frame must not come back"
        core.push(2)
        assert _settle(lambda: source.fresh(first.seq) is not None)
        second = source.fresh(first.seq)
        assert second.seq > first.seq
        assert second.data[0, 0] == 2


def test_fresh_after_a_gap_reports_the_frames_that_were_missed():
    core = FakeCore()
    core.push(0)
    with FrameSource(core, max_drain=8) as source:
        first = source.wait(timeout=2.0)
        for fill in range(1, 6):
            core.push(fill)
        assert _settle(lambda: source.stats().popped == 6)
        newest = source.fresh(first.seq)
    # A consumer comparing seq learns it missed four frames, without ever
    # comparing an image to another image.
    assert newest.seq - first.seq == 5
    assert newest.seq - first.seq - 1 == 4


# --------------------------------------------------------------------------
# FrameSource: rate limiting
# --------------------------------------------------------------------------


def test_period_rate_limits_publishes_but_not_the_drain():
    """The consumer's view is throttled; the camera buffer is still emptied,
    which is the point -- a slow consumer must not back the buffer up."""
    core = FakeCore()
    for fill in range(6):
        core.push(fill)
    # A period longer than the test means at most the one immediate publish.
    with FrameSource(core, period_s=30.0, max_drain=8) as source:
        assert _settle(lambda: source.stats().popped == 6)
        stats = source.stats()
    assert stats.popped == 6, "drain must not be throttled"
    assert stats.published <= 2, f"publishes must be throttled, got {stats.published}"


def test_dropped_count_survives_a_run_that_ends_between_pop_and_publish():
    """Frames are counted as dropped when displaced, not when a publish
    happens -- otherwise a run that stops while a frame is pending loses the
    count."""
    core = FakeCore()
    for fill in range(5):
        core.push(fill)
    source = FrameSource(core, period_s=30.0, max_drain=8).start()
    assert _settle(lambda: source.stats().popped == 5)
    stats = source.stop()
    # One published immediately, four more popped behind it; whatever was
    # displaced is accounted for.
    assert stats.popped == 5
    assert stats.dropped == stats.popped - stats.published


# --------------------------------------------------------------------------
# FrameSource: lifecycle and failure
# --------------------------------------------------------------------------


def test_lock_is_taken_around_the_drain():
    """On a rig where the camera and DMD share a bus, the drain has to hold
    the same mutex a pattern write does."""
    core = FakeCore()
    core.push(1)
    held: list[bool] = []
    real = threading.Lock()

    class WatchedLock:
        def acquire(self, *a, **k):
            held.append(True)
            return real.acquire(*a, **k)

        def release(self):
            return real.release()

    with FrameSource(core, lock=WatchedLock()) as source:
        source.wait(timeout=2.0)
    assert held, "drain ran without taking the lock"
    assert not real.locked(), "lock was not released"


def test_a_raising_pop_is_counted_and_the_thread_keeps_going():
    core = FakeCore()
    core.raise_on_pop = 2
    core.push(1)
    core.push(2)
    with FrameSource(core) as source:
        assert _settle(lambda: source.stats().errors >= 2)
        core.push(3)
        frame = source.wait(timeout=2.0)
        stats = source.stats()
    assert frame is not None, "thread died on an error instead of continuing"
    assert stats.errors >= 2
    assert "camera said no" in stats.last_error


def test_start_twice_is_refused():
    source = FrameSource(FakeCore()).start()
    try:
        with pytest.raises(RuntimeError, match="twice"):
            source.start()
    finally:
        source.stop()


def test_stop_is_idempotent_and_safe_without_start():
    source = FrameSource(FakeCore())
    assert isinstance(source.stop(), FrameStats)  # never started
    source.start()
    source.stop()
    source.stop()
    assert not source.running


def test_running_reflects_the_thread():
    source = FrameSource(FakeCore())
    assert not source.running
    source.start()
    assert source.running
    source.stop()
    assert not source.running


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"max_drain": 0}, "max_drain"),
        ({"period_s": -1.0}, "period_s"),
    ],
)
def test_bad_arguments_are_refused_at_construction(kwargs, match):
    with pytest.raises(ValueError, match=match):
        FrameSource(FakeCore(), **kwargs)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def test_stats_report_says_so_when_nothing_arrived():
    assert FrameStats().report() == "no frames popped"


def test_stats_report_includes_errors_even_with_no_frames():
    stats = FrameStats(errors=3, last_error="RuntimeError: nope")
    assert "3 errors" in stats.report()


def test_stats_report_has_rate_and_drop_fraction():
    stats = FrameStats(popped=100, published=50, dropped=50,
                       t_first=1.0, t_last=3.0)
    line = stats.report()
    assert "100 frames popped" in line
    assert "50.0 Hz" in line
    assert "50%" in line


def test_stats_report_omits_the_rate_when_the_span_is_zero():
    """A single frame has no rate; inventing one would be a made-up number."""
    stats = FrameStats(popped=1, published=1, t_first=2.0, t_last=2.0)
    assert "Hz" not in stats.report()


def test_stats_is_a_copy_not_a_live_reference():
    core = FakeCore()
    core.push(1)
    with FrameSource(core) as source:
        source.wait(timeout=2.0)
        snapshot = source.stats()
        before = snapshot.popped
        core.push(2)
        _settle(lambda: source.stats().popped > before)
    assert snapshot.popped == before


def test_frame_is_immutable_bookkeeping():
    frame = Frame(seq=1, data=np.zeros((2, 2), np.uint16), t=0.5, n_dropped=0)
    with pytest.raises(Exception):
        frame.seq = 2  # frozen dataclass
