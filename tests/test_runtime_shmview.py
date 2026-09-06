"""Tests for runtime/shmview.py -- the cross-process display channel.

Most tests run both ends in this process, which is enough for the header, the
decimation, the rate cap and the seqlock. Two at the end spawn a real second
interpreter with ``subprocess``, because "does a separate process actually
see the pixels" is the entire point of the module and cannot be checked any
other way. Those two have their own timeouts and kill the child in a
``finally``, so a hung reader fails the test rather than the run.

Segment names are unique per test (pid + a counter): a leftover name from a
crashed run would otherwise make an unrelated test fail with FileExistsError,
and on POSIX segments do outlive the process that made them.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from itertools import count
from pathlib import Path

import numpy as np
import pytest

from runtime.shmview import HEADER_SIZE, ShmPublisher, ShmSubscriber, decimate

_counter = count()
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def name() -> str:
    """A segment name no other test or run can collide with."""
    return f"amtest_{os.getpid()}_{next(_counter)}"


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def frame(h: int = 8, w: int = 8, fill: int = 0x1234) -> np.ndarray:
    return np.full((h, w), fill, dtype=np.uint16)


# --------------------------------------------------------------------------
# decimate
# --------------------------------------------------------------------------


def test_decimate_leaves_a_small_frame_alone():
    view, step = decimate(frame(8, 8), 640)
    assert step == 1
    assert view.shape == (8, 8)


def test_decimate_strides_a_large_frame_under_the_cap():
    view, step = decimate(np.zeros((2400, 2400), np.uint16), 640)
    assert step == 4, "ceil(2400/640) = 4"
    assert view.shape == (600, 600)
    assert max(view.shape) <= 640


def test_decimate_returns_a_view_not_a_copy():
    """The stride has to be free until someone copies it -- that is what keeps
    the publish cost off the producer's clock."""
    src = np.zeros((100, 100), np.uint16)
    view, _ = decimate(src, 10)
    assert view.base is src


def test_decimate_caps_the_longest_edge_of_a_landscape_frame():
    view, step = decimate(np.zeros((100, 1000), np.uint16), 100)
    assert step == 10
    assert view.shape == (10, 100)


def test_decimate_caps_the_longest_edge_of_a_portrait_frame():
    """Capping the width alone would leave this 1000 px tall, and the payload
    would then not fit a segment sized max_w**2."""
    view, step = decimate(np.zeros((1000, 100), np.uint16), 100)
    assert step == 10
    assert view.shape == (100, 10)
    assert max(view.shape) <= 100


# --------------------------------------------------------------------------
# publish / subscribe round trip
# --------------------------------------------------------------------------


def test_round_trip_carries_pixels_and_timestamp(name):
    with ShmPublisher(name) as pub:
        assert pub.try_publish(frame(fill=0xAB00), ts=1.25)
        with ShmSubscriber(name, wait=False) as sub:
            got = sub.poll()
    assert got is not None
    img, ts, meta = got
    assert ts == pytest.approx(1.25)
    assert img.dtype == np.uint8
    assert np.all(img == 0xAB), "uint16 >> 8 keeps the high byte"
    assert meta["version"] == 1


def test_meta_carries_the_full_sensor_shape_and_the_stride(name):
    """An overlay needs to get back to sensor pixels, and from there to
    microns. The bacteria original's header could not say."""
    with ShmPublisher(name, max_w=64) as pub:
        pub.try_publish(frame(256, 256), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, meta = sub.poll()
    assert meta["full_h"] == 256
    assert meta["full_w"] == 256
    assert meta["step"] == 4
    assert img.shape == (64, 64)


def test_poll_returns_none_until_something_new_is_published(name):
    with ShmPublisher(name) as pub:
        pub.try_publish(frame(), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            assert sub.poll() is not None
            assert sub.poll() is None, "same frame must not come back"
            pub.try_publish(frame(fill=0x5600), ts=1.0, force=True)
            got = sub.poll()
    assert got is not None
    assert np.all(got[0] == 0x56)


def test_version_increments_per_publish(name):
    with ShmPublisher(name) as pub:
        # The segment does not exist until the first publish -- the publisher
        # has no shape before then -- so the subscriber is built after it.
        # Building both in one `with` deadlocks the waiting subscriber.
        pub.try_publish(frame(fill=0), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            versions = [sub.poll()[2]["version"]]
            for i in range(1, 4):
                pub.try_publish(frame(fill=i << 8), ts=float(i), force=True)
                versions.append(sub.poll()[2]["version"])
    assert versions == [1, 2, 3, 4]


def test_a_subscriber_built_alongside_a_publisher_must_wait_for_the_first_frame(name):
    """Pins the ordering the test above works around: the segment appears on
    the first publish, not at construction."""
    with ShmPublisher(name) as pub:
        with pytest.raises(FileNotFoundError):
            ShmSubscriber(name, wait=False)
        pub.try_publish(frame(), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            assert sub.poll() is not None


def test_uint8_input_is_passed_through_without_shifting(name):
    with ShmPublisher(name) as pub:
        pub.try_publish(np.full((8, 8), 200, np.uint8), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, _meta = sub.poll()
    assert np.all(img == 200), "an 8-bit frame must not be shifted"


def test_shift_right_is_settable_for_a_12_bit_sensor(name):
    """A Kinetix in 12-bit mode leaves the top 4 bits empty, so >>8 would
    show a dark field. 0x0F00 >> 4 is 0xF0."""
    with ShmPublisher(name, shift_right=4) as pub:
        pub.try_publish(frame(fill=0x0F00), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, _meta = sub.poll()
    assert np.all(img == 0xF0)


def test_segment_holds_header_plus_payload(name):
    """``>=``, not ``==``: Windows rounds an allocation up to a page, so a
    288-byte request comes back reporting 4096. Asserting equality here is
    the same mistake that made the publisher recreate its segment every
    frame."""
    with ShmPublisher(name, max_w=16) as pub:
        pub.try_publish(frame(16, 16), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            assert sub._shm.size >= HEADER_SIZE + 16 * 16


def test_republishing_the_same_shape_does_not_recreate_the_segment(name):
    """The regression that page rounding caused: recreating per frame reset
    the version counter, so a subscriber saw exactly one frame and then
    nothing."""
    with ShmPublisher(name, max_w=16) as pub:
        pub.try_publish(frame(16, 16), ts=0.0)
        first = pub._shm
        for i in range(5):
            pub.try_publish(frame(16, 16), ts=float(i), force=True)
        assert pub._shm is first, "segment was recreated for an unchanged shape"
        assert pub._version == 6, f"version must keep counting, got {pub._version}"


# --------------------------------------------------------------------------
# the rate cap
# --------------------------------------------------------------------------


def test_rate_cap_drops_offers_rather_than_queueing_them(name):
    clock = FakeClock()
    with ShmPublisher(name, max_fps=10.0, now=clock.now) as pub:
        assert pub.try_publish(frame(), ts=0.0) is True, "first offer goes out"
        assert pub.try_publish(frame(), ts=0.0) is False
        clock.advance(0.05)
        assert pub.try_publish(frame(), ts=0.0) is False, "still inside 1/10 s"
        clock.advance(0.06)
        assert pub.try_publish(frame(), ts=0.0) is True


def test_a_200_hz_loop_pays_the_write_on_one_tick_in_twenty(name):
    """The property a control loop budgets against."""
    clock = FakeClock()
    with ShmPublisher(name, max_fps=10.0, now=clock.now) as pub:
        published = 0
        for _ in range(200):          # 200 ticks of 5 ms = 1 s
            if pub.try_publish(frame(), ts=0.0):
                published += 1
            clock.advance(0.005)
    assert published == 10, f"expected the 10 fps cap, got {published}"


def test_force_bypasses_the_cap(name):
    """For the last frame before shutdown, so a viewer's final image is the
    state things were actually left in."""
    clock = FakeClock()
    with ShmPublisher(name, max_fps=1.0, now=clock.now) as pub:
        assert pub.try_publish(frame(), ts=0.0) is True
        assert pub.try_publish(frame(), ts=0.0) is False
        assert pub.try_publish(frame(), ts=0.0, force=True) is True


def test_report_counts_what_the_cap_dropped(name):
    clock = FakeClock()
    with ShmPublisher(name, max_fps=10.0, now=clock.now) as pub:
        for _ in range(20):
            pub.try_publish(frame(), ts=0.0)
            clock.advance(0.005)
        line = pub.report()
    assert "1 published" in line
    assert "19 dropped" in line
    assert "10 fps cap" in line


def test_report_before_anything_was_offered(name):
    with ShmPublisher(name) as pub:
        assert "nothing published" in pub.report()


# --------------------------------------------------------------------------
# shape changes, staleness, lifecycle
# --------------------------------------------------------------------------


def test_the_segment_is_sized_for_the_worst_case_frame(name):
    """Not fitted to the frame: max_w**2 plus the header, allocated once."""
    with ShmPublisher(name, max_w=64) as pub:
        pub.try_publish(frame(8, 8), ts=0.0)
        assert pub._size == HEADER_SIZE + 64 * 64
        assert pub._shm.size >= HEADER_SIZE + 64 * 64


def test_a_shape_change_needs_no_resize(name):
    """An ROI change mid-session. The segment is already sized for the worst
    case, so the new shape just travels in the header."""
    with ShmPublisher(name, max_w=64) as pub:
        pub.try_publish(frame(32, 32), ts=0.0)
        first = pub._shm
        pub.try_publish(frame(64, 64), ts=1.0, force=True)
        assert pub._shm is first, "segment must not be recreated for a new shape"
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, meta = sub.poll()
    assert img.shape == (64, 64)
    assert meta["full_h"] == 64


def test_an_attached_subscriber_survives_a_shape_change(name):
    """The failure the fixed allocation removes. On Windows a subscriber's
    handle keeps the name alive, so a publisher that refitted its segment
    could not recreate it -- an ROI change took the run down with
    FileExistsError whenever a viewer happened to be watching."""
    with ShmPublisher(name, max_w=64) as pub:
        pub.try_publish(frame(16, 16), ts=0.0)
        with ShmSubscriber(name, wait=False) as sub:
            assert sub.poll()[0].shape == (16, 16)
            pub.try_publish(frame(64, 64, fill=0x2200), ts=1.0, force=True)
            img, _ts, meta = sub.poll()
    assert img.shape == (64, 64), "the same subscriber follows the new shape"
    assert np.all(img == 0x22)
    assert meta["full_w"] == 64


def test_a_frame_smaller_than_the_segment_leaves_the_tail_unread(name):
    """The payload is only the first vh*vw bytes; the rest is whatever was
    there before, and the header is what stops a reader touching it."""
    with ShmPublisher(name, max_w=64) as pub:
        pub.try_publish(frame(64, 64, fill=0xFF00), ts=0.0)
        pub.try_publish(frame(8, 8, fill=0x1100), ts=1.0, force=True)
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, _meta = sub.poll()
    assert img.shape == (8, 8)
    assert np.all(img == 0x11), "no stale pixels from the larger frame"


def test_age_grows_while_nothing_is_published(name):
    """The only way to tell an idle publisher from a dead one on Windows."""
    clock = FakeClock()
    with ShmPublisher(name) as pub:
        pub.try_publish(frame(), ts=0.0)
        with ShmSubscriber(name, wait=False, now=clock.now) as sub:
            sub.poll()
            assert sub.age == pytest.approx(0.0)
            clock.advance(5.0)
            assert sub.age == pytest.approx(5.0)


def test_subscriber_without_a_publisher_raises_when_not_waiting(name):
    with pytest.raises(FileNotFoundError):
        ShmSubscriber(name, wait=False)


def test_subscriber_times_out_with_a_diagnostic(name):
    with pytest.raises(TimeoutError, match="publisher"):
        ShmSubscriber(name, wait=True, timeout=0.2, poll_interval=0.05)


def test_publisher_close_is_idempotent(name):
    pub = ShmPublisher(name)
    pub.try_publish(frame(), ts=0.0)
    pub.close()
    pub.close()


def test_subscriber_close_is_idempotent(name):
    with ShmPublisher(name) as pub:
        pub.try_publish(frame(), ts=0.0)
        sub = ShmSubscriber(name, wait=False)
        sub.close()
        sub.close()
        assert sub.poll() is None, "a closed subscriber polls to None, not a crash"


@pytest.mark.skipif(os.name != "nt", reason="Windows segment-lifetime behaviour")
def test_a_second_live_publisher_on_one_name_is_refused_with_a_diagnostic(name):
    """Two publishers on one name cannot be merged, and on Windows cannot
    even be taken over: a segment lives while any handle does. The raw
    failure is ``WinError 183: File exists``, which names no cause, so the
    module replaces it."""
    first = ShmPublisher(name, max_w=32)
    try:
        first.try_publish(frame(32, 32), ts=0.0)
        second = ShmPublisher(name, max_w=8)
        with pytest.raises(RuntimeError, match="own name"):
            second.try_publish(frame(8, 8), ts=1.0)
    finally:
        first.close()


def test_a_publisher_can_reuse_a_name_after_the_first_one_closed(name):
    """The ordinary case that must keep working: one run ends, the next
    starts, same name."""
    first = ShmPublisher(name, max_w=32)
    first.try_publish(frame(32, 32), ts=0.0)
    first.close()

    with ShmPublisher(name, max_w=8) as second:
        second.try_publish(frame(8, 8, fill=0x7700), ts=1.0)
        with ShmSubscriber(name, wait=False) as sub:
            img, _ts, _meta = sub.poll()
    assert img.shape == (8, 8)
    assert np.all(img == 0x77)


def test_a_non_2d_frame_is_refused(name):
    with ShmPublisher(name) as pub:
        with pytest.raises(ValueError, match="2-D"):
            pub.try_publish(np.zeros((4, 4, 3), np.uint8), ts=0.0)


@pytest.mark.parametrize(
    "kwargs, match",
    [({"max_w": 0}, "max_w"), ({"max_fps": 0.0}, "max_fps"),
     ({"max_fps": -1.0}, "max_fps")],
)
def test_bad_publisher_arguments_are_refused(kwargs, match, name):
    with pytest.raises(ValueError, match=match):
        ShmPublisher(name, **kwargs)


# --------------------------------------------------------------------------
# the actual point: a second process
# --------------------------------------------------------------------------


_READER = textwrap.dedent(
    """
    import sys, time
    import numpy as np
    sys.path.insert(0, sys.argv[2])
    from runtime.shmview import ShmSubscriber

    with ShmSubscriber(sys.argv[1], wait=True, timeout=20.0) as sub:
        deadline = time.time() + 20.0
        while time.time() < deadline:
            got = sub.poll()
            if got is not None:
                img, ts, meta = got
                print(f"{int(img[0, 0])} {ts} {img.shape[0]} {img.shape[1]} "
                      f"{meta['full_h']} {meta['step']}")
                sys.exit(0)
            time.sleep(0.01)
    sys.exit(3)
    """
)


def _spawn_reader(segment: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", _READER, segment, str(REPO_ROOT)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def test_a_separate_process_reads_the_frame(name):
    """The module's reason to exist: pixels crossing a process boundary with
    no second claim on the camera.

    The reader is started first and waits, which is the real ordering -- a
    viewer opened before the run begins.
    """
    reader = _spawn_reader(name)
    try:
        with ShmPublisher(name, max_w=32) as pub:
            deadline = __import__("time").monotonic() + 15.0
            while reader.poll() is None and __import__("time").monotonic() < deadline:
                pub.try_publish(frame(128, 128, fill=0x3C00), ts=2.5, force=True)
                __import__("time").sleep(0.02)
            out, err = reader.communicate(timeout=10)
    finally:
        if reader.poll() is None:
            reader.kill()
            reader.communicate()

    assert reader.returncode == 0, f"reader failed: {err}"
    fields = out.strip().split()
    assert fields[0] == "60", f"0x3C00 >> 8 = 0x3C = 60; got {fields[0]}"
    assert float(fields[1]) == pytest.approx(2.5)
    assert (int(fields[2]), int(fields[3])) == (32, 32), "decimated to max_w"
    assert int(fields[4]) == 128, "full sensor height travelled with it"
    assert int(fields[5]) == 4, "and the stride"


def test_a_separate_process_gets_nothing_when_no_publisher_appears(name):
    """A viewer pointed at a name nobody publishes must fail loudly, not hang
    forever showing a blank window."""
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(
            """
            import sys
            sys.path.insert(0, sys.argv[2])
            from runtime.shmview import ShmSubscriber
            try:
                ShmSubscriber(sys.argv[1], wait=True, timeout=0.5)
            except TimeoutError as exc:
                print(exc)
                sys.exit(7)
            sys.exit(0)
            """
        ), name, str(REPO_ROOT)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 7, f"expected a timeout; out={out!r} err={err!r}"
    assert "publisher" in out
