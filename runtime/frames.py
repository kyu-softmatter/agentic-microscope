"""Single-slot frame ring and a drain-and-keep-newest acquisition thread.

Adapted from the Takatori-lab bacteria stack (``lib/ring.py`` and
``lib/devices_mm.py:MMCamera.start`` in ``bacteria3``), which has run this
pattern on the DMD rig. Two ideas, and they only work together:

**One slot, not a queue.** :class:`Latest` holds exactly one
``(seq, payload)``. A producer overwrites it; a consumer reads whatever is
there. A queue would grow without bound the moment the consumer is slower
than the camera, and a bounded queue would hand the consumer *stale* frames
under load -- which for closed-loop trapping is worse than handing it none.

**Drain the buffer, publish only the newest.** :class:`FrameSource` pops up
to ``max_drain`` images per pass out of Micro-Manager's circular buffer and
keeps only the last one. That trades frames away on purpose, so the control
loop can never fall behind the camera.

WHY THIS REPLACES ``getLastImage()`` POLLING
--------------------------------------------
``config/tweezers/trap_from_tracking.py:track_bead_during`` reads
``core.getLastImage()`` inside the drive loop and de-duplicates the result by
comparing three pixels -- ``raw[0,0]``, ``raw[-1,-1]`` and the centre. It
works, and its own docstring says why it has to exist: at a 50 Hz tick
against a 30 fps camera roughly a third of the ticks see the same frame
twice. But the three-pixel signature answers "is this the same frame?" by
guessing, and it cannot answer the question that matters for a measurement --
*how many frames went past that I never saw*. ``getLastImage`` peeks the
newest image without removing it, so nothing in that path counts.

Popping does count. :attr:`Frame.seq` increments once per image taken out of
the camera buffer, so a consumer that compares consecutive ``seq`` values
learns exactly how many camera frames it missed, whether this class discarded
them in a drain or the consumer simply never looked. That is a measured
number rather than an inferred one, and a stalled camera shows up as a
``seq`` that stops moving instead of as a rising dupe count that looks the
same as a slow tick.

DO NOT MIX THE TWO ON ONE CORE
------------------------------
``popNextImage`` removes images; ``getLastImage`` does not. Running a
:class:`FrameSource` while other code in the same process still polls
``getLastImage()`` on the same core leaves both reading a buffer the other is
mutating, and which frame either one sees becomes a race. Pick one per core.

WHAT IS NOT VERIFIED HERE
-------------------------
Nothing in this module has run against a Kinetix yet -- the tests drive a
fake core. Three things to check on the rig, because they are properties of
the PVCAM adapter rather than of this code: that ``getRemainingImageCount``
and ``popNextImage`` are the right pair for
``startContinuousSequenceAcquisition`` (the bacteria rig's Kinetix uses
exactly this); whether ``max_drain=4`` is enough headroom at the frame rate
you run (a rising :attr:`FrameStats.dropped` with a flat
:attr:`FrameStats.published` means it is not); and whether popping changes
what a concurrent ``getLastImage()`` elsewhere in the process returns, which
is the reason for the warning above.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np


class Latest:
    """Single-slot ``(seq, payload)`` cache with atomic put/get.

    The "ring" has one slot: :meth:`put` overwrites whatever was there. The
    sequence number is supplied by the producer rather than counted here, so
    it can mean "images out of the camera" rather than "calls to put" -- see
    the module docstring on why that distinction is the whole point.

    The lock is a plain :class:`threading.Lock`. Both critical sections are a
    tuple assignment, so contention is not a consideration at any frame rate
    a camera can produce.
    """

    __slots__ = ("_lock", "_item")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._item: Optional[tuple[int, Any]] = None

    def put(self, seq: int, payload: Any) -> None:
        """Replace the stored ``(seq, payload)``."""
        with self._lock:
            self._item = (int(seq), payload)

    def get(self) -> Optional[tuple[int, Any]]:
        """Return the stored ``(seq, payload)``, or ``None`` if empty."""
        with self._lock:
            return self._item

    def clear(self) -> None:
        """Forget the stored item. Used when a consumer must not see a frame
        from before some event -- an objective change, a re-ROI."""
        with self._lock:
            self._item = None


@dataclass(frozen=True)
class Frame:
    """One camera frame, with enough bookkeeping to audit the stream.

    Attributes
    ----------
    seq : int
        Index of this image among all images popped from the camera buffer,
        counting from 0. Gaps between the ``seq`` values a consumer observes
        are frames it did not see.
    data : numpy.ndarray
        The frame, shaped ``(h, w)``. Not copied -- treat it as read-only, or
        copy it before writing into it.
    t : float
        ``time.perf_counter()`` at the moment the image came out of the
        buffer. This is *arrival*, not exposure start: it trails the real
        exposure by the camera's own latency plus however long this pass
        waited on the lock. Do not use it as an exposure timestamp; for that
        the frame needs the adapter's own metadata, which this class does not
        read.
    n_dropped : int
        How many frames were popped and discarded since the previously
        published one. Non-zero means the consumer is slower than the camera,
        which is the design working, not a fault.
    """

    seq: int
    data: np.ndarray
    t: float
    n_dropped: int


@dataclass
class FrameStats:
    """Counters for one :class:`FrameSource` run. Read with :meth:`FrameSource.stats`."""

    popped: int = 0
    published: int = 0
    dropped: int = 0
    errors: int = 0
    last_error: str = ""
    #: ``perf_counter`` of the first and most recent image *popped* -- so
    #: ``popped / (t_last - t_first)`` is the rate frames left the camera at,
    #: which is not the publish rate when ``period_s > 0``.
    t_first: float = 0.0
    t_last: float = 0.0

    def report(self) -> str:
        """One line, honest about the case where nothing arrived."""
        if self.popped == 0:
            err = f", {self.errors} errors ({self.last_error})" if self.errors else ""
            return f"no frames popped{err}"
        span = self.t_last - self.t_first
        rate = f", {self.popped / span:.1f} Hz" if span > 0 else ""
        out = (f"{self.popped} frames popped{rate}, "
               f"{self.published} published, {self.dropped} dropped in drain "
               f"({100.0 * self.dropped / self.popped:.0f}%)")
        if self.errors:
            out += f", {self.errors} errors (last: {self.last_error})"
        return out


class FrameSource:
    """Daemon thread that drains a Micro-Manager circular buffer.

    The core object needs four methods -- ``getRemainingImageCount()``,
    ``popNextImage()``, ``getImageHeight()`` and ``getImageWidth()``. Both
    ``pymmcore.CMMCore`` and ``pymmcore_plus.CMMCorePlus`` satisfy that. The
    caller is responsible for having started acquisition
    (``core.startContinuousSequenceAcquisition(0)``) before :meth:`start`,
    and for stopping it afterwards; this class does not own the camera.

    Parameters
    ----------
    core : object
        The Micro-Manager core, already acquiring.
    period_s : float, optional
        Minimum interval between published frames. ``0.0`` (the default)
        publishes every frame it drains, which is what a tracker wants. A
        non-zero value rate-limits the *consumer's* view without slowing the
        drain, so the buffer still gets emptied.
    max_drain : int, optional
        Ceiling on images popped per pass. Bounded so a backlog cannot hold
        the lock for an unbounded time; the backlog is drained over several
        passes instead. Default 4, which is what the bacteria rig runs.
    lock : threading.Lock, optional
        Serializes bus traffic. On a rig where the camera and the DMD share a
        USB bus, pass the same lock every pattern submission uses -- that is
        the ``usb_mutex`` invariant from the bacteria stack. ``None`` (the
        default) means no serialization, which is correct when nothing else
        talks to the bus.
    idle_sleep_s : float, optional
        How long to sleep when a pass finds the buffer empty. Keeps the
        thread off the CPU without adding latency worth measuring. Default
        1 ms.
    now : callable, optional
        Clock, for tests. Defaults to :func:`time.perf_counter`.
    """

    def __init__(
        self,
        core: Any,
        *,
        period_s: float = 0.0,
        max_drain: int = 4,
        lock: Optional[threading.Lock] = None,
        idle_sleep_s: float = 0.001,
        now: Callable[[], float] = time.perf_counter,
    ) -> None:
        if max_drain < 1:
            raise ValueError(f"max_drain must be >= 1, got {max_drain}")
        if period_s < 0:
            raise ValueError(f"period_s must be >= 0, got {period_s}")
        self._core = core
        self._period_s = float(period_s)
        self._max_drain = int(max_drain)
        self._lock = lock
        self._idle_sleep_s = float(idle_sleep_s)
        self._now = now

        self._latest = Latest()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stats = FrameStats()
        self._stats_lock = threading.Lock()
        self._shape: Optional[tuple[int, int]] = None
        self._arrived = threading.Event()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> "FrameSource":
        """Spawn the acquisition thread. Returns self, so it can be chained."""
        if self._thread is not None:
            raise RuntimeError("FrameSource.start() called twice")
        self._thread = threading.Thread(
            target=self._loop, name="FrameSource", daemon=True
        )
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> FrameStats:
        """Signal the thread and join it. Returns the final stats.

        Safe to call more than once, and safe to call without :meth:`start`
        -- an exit path should not have to know whether it got that far.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        return self.stats()

    def __enter__(self) -> "FrameSource":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # consumer side
    # ------------------------------------------------------------------ #

    def latest(self) -> Optional[Frame]:
        """The newest published frame, or ``None`` if none has arrived.

        Never blocks for longer than a tuple read. Returns the *same*
        :class:`Frame` on repeated calls until a new one lands, so a consumer
        that wants only new frames compares :attr:`Frame.seq` against the one
        it last handled -- or calls :meth:`fresh`, which does that for it.
        """
        item = self._latest.get()
        return None if item is None else item[1]

    def fresh(self, after_seq: int) -> Optional[Frame]:
        """The newest frame if it is newer than ``after_seq``, else ``None``.

        This is the call that replaces the three-pixel duplicate check: pass
        the ``seq`` of the frame you last processed and you get either a frame
        you have not seen or nothing, with no image comparison at all.
        """
        frame = self.latest()
        if frame is None or frame.seq <= after_seq:
            return None
        return frame

    def wait(self, timeout: float = 2.0) -> Frame:
        """Block until a frame has been published. Raises on timeout.

        For the one place a blocking read is the right thing: getting the
        first frame after starting acquisition, where the alternative is the
        ``time.sleep(0.5)`` that ``trap_from_tracking.py`` currently uses to
        "let the first frames arrive". A timeout here is a camera that is not
        delivering, which is worth an exception rather than a dark frame.
        """
        if not self._arrived.wait(timeout=timeout):
            raise TimeoutError(
                f"no frame within {timeout:.2f} s. {self.stats().report()}. "
                f"Is the camera acquiring (startContinuousSequenceAcquisition) "
                f"and is this the core that owns it?"
            )
        frame = self.latest()
        assert frame is not None  # _arrived is only set after a put
        return frame

    def stats(self) -> FrameStats:
        """A snapshot copy of the counters. Safe to call while running."""
        with self._stats_lock:
            return FrameStats(**vars(self._stats))

    # ------------------------------------------------------------------ #
    # producer side
    # ------------------------------------------------------------------ #

    def _reshape(self, raw: Any) -> np.ndarray:
        """Coerce whatever the adapter returned into ``(h, w)``.

        Plain ``pymmcore`` hands back a flat buffer; ``pymmcore-plus``
        reshapes for you. Reshaping an already-shaped array to the same shape
        is free, so doing it unconditionally covers both. A size mismatch
        means the ROI moved under us, so the dimensions get re-read once
        before giving up.
        """
        arr = np.asarray(raw)
        if self._shape is None:
            self._shape = (int(self._core.getImageHeight()),
                           int(self._core.getImageWidth()))
        try:
            return arr.reshape(self._shape)
        except ValueError:
            self._shape = (int(self._core.getImageHeight()),
                           int(self._core.getImageWidth()))
            return arr.reshape(self._shape)

    def _drain(self) -> tuple[Optional[np.ndarray], int, float, int]:
        """Pop up to ``max_drain`` images. Returns (newest, seq, t, discarded).

        One lock acquisition for the whole drain, not one per image: the point
        of the mutex is to serialize bus traffic, and releasing between pops
        would let a DMD write interleave into the middle of a drain for no
        benefit.
        """
        newest: Optional[np.ndarray] = None
        seq = -1
        t = 0.0
        discarded = 0
        if self._lock is not None:
            self._lock.acquire()
        try:
            count = int(self._core.getRemainingImageCount())
            for _ in range(min(count, self._max_drain)):
                raw = self._core.popNextImage()
                if newest is not None:
                    discarded += 1
                newest = self._reshape(raw)
                t = self._now()
                with self._stats_lock:
                    seq = self._stats.popped
                    self._stats.popped += 1
                    # Timestamped on the pop, not on the publish: the rate in
                    # `report()` is frames out of the *camera* per second, and
                    # with period_s > 0 the publish span is a different (and
                    # longer) interval.
                    if self._stats.t_first == 0.0:
                        self._stats.t_first = t
                    self._stats.t_last = t
        finally:
            if self._lock is not None:
                self._lock.release()
        return newest, seq, t, discarded

    def _loop(self) -> None:
        # `pending` is a frame that has been popped but not published yet,
        # which only happens when period_s > 0. Anything it displaces was
        # popped and never seen, so it counts as dropped at the moment it is
        # displaced -- not at publish time, which would lose the count of a
        # run that ends between a pop and a publish.
        pending: Optional[Frame] = None
        next_deadline = self._now()

        while not self._stop.is_set():
            try:
                newest, seq, t, discarded = self._drain()
            except Exception as exc:  # noqa: BLE001 - a bad pass must not kill the thread
                with self._stats_lock:
                    self._stats.errors += 1
                    self._stats.last_error = f"{type(exc).__name__}: {exc}"
                self._stop.wait(self._idle_sleep_s)
                continue

            if newest is not None:
                displaced = 1 if pending is not None else 0
                if discarded or displaced:
                    with self._stats_lock:
                        self._stats.dropped += discarded + displaced
                carried = discarded + displaced + (
                    pending.n_dropped if pending is not None else 0
                )
                pending = Frame(seq=seq, data=newest, t=t, n_dropped=carried)

            now = self._now()
            if pending is not None and now >= next_deadline:
                self._latest.put(pending.seq, pending)
                with self._stats_lock:
                    self._stats.published += 1
                self._arrived.set()
                pending = None
                if self._period_s > 0:
                    # Catch up rather than queue: a publish that ran late does
                    # not push every later deadline back by the same amount.
                    while next_deadline <= now:
                        next_deadline += self._period_s
                else:
                    next_deadline = now

            if newest is None:
                # Buffer was empty. Sleeping on the stop event rather than
                # time.sleep means stop() is not held up by an idle sleep.
                self._stop.wait(self._idle_sleep_s)
            elif self._period_s > 0:
                remaining = next_deadline - self._now()
                if remaining > 0:
                    self._stop.wait(min(remaining, self._period_s))
