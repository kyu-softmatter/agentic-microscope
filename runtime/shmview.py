"""Rate-capped shared-memory frame channel, for a live view in another process.

Adapted from ``lib/viz.py`` in the Takatori-lab bacteria stack, where the
matplotlib visualizer (``run_viz.py``) is a separate process that attaches to
two segments the experiment loop publishes.

WHY ANOTHER PROCESS AND NOT ANOTHER THREAD
------------------------------------------
This is the question worth getting right, and the answer is the GIL. Split by
whether the work releases it:

**Thread** when the work is a C extension that drops the GIL and needs to
share the frame buffer for free. ``popNextImage`` blocks in C++;
numpy/OpenCV/CuPy kernels release the GIL for their duration. A camera drain
thread (:class:`runtime.frames.FrameSource`) costs the control loop almost
nothing, and it hands over the array by reference.

**Process** when the work is Python bytecode or a GUI event loop, because
that holds the GIL and the control loop cannot get it back. This is the case
here: ``cv2_loop`` in ``config/micromanager/live_view.py`` measures its own
tick at ~38 ms full-frame -- draw, ``cv2.imshow`` and ``waitKey`` are Python
frames plus highgui event pumping. Run that in a thread beside a 20 ms
control loop and the control loop misses periods it will then report as
skipped; run it in a process and it competes for a core instead of for the
interpreter. Tk is worse: ``PhotoImage`` costs a measured 43.1 ms of
zlib+base64 per 800x800 frame, all of it in the GIL.

The two processes then need the pixels in each other's address space, and
that is the only thing this module does.

WHY IT MATTERS ON *THIS* RIG SPECIFICALLY
-----------------------------------------
PVCAM hands a Kinetix to one process at a time
(``hardware/microscope.SHARED_DEVICES``), which is the reason
``live_view.py`` exists at all rather than deferring to MM Studio. So the
process that owns the camera during a trapping run is the *only* process that
can see it, and today watching a run means not running one. A publisher on
the acquisition side plus a subscriber in a second process gives a live view
without a second claim on the camera -- and without ever having to release
the trap to get one, which on this instrument is the expensive move.

WHAT KEEPS IT OFF THE HOT PATH
------------------------------
Three constants, all of them caps rather than best-effort:

``max_fps``     Publishes are dropped, not queued, once the cap is hit.
                Default 10 Hz, so a 200 Hz control loop pays the write on
                one tick in twenty.
``max_w``       Frames are decimated by an integer stride until their
                longest edge is at most this, before the copy. A 2400x2400
                uint16 frame is 11.5 MB; at ``max_w=640`` the payload is
                600x600 uint8, a 32x smaller memcpy. It also fixes the
                segment size at ``max_w**2``, so the segment is allocated
                once -- see the Windows notes.
``shift_right`` uint16 is right-shifted to uint8 in the same pass (default 8,
                the high byte). No autoscaling, no percentile pass -- both
                would be per-frame work on the producer's clock. A subscriber
                that wants contrast can stretch its own copy.

Together those make the publish cost a constant the producer can budget for,
which is the property a control loop needs; a viewer that got slower would
otherwise slow the loop down with it.

Measured on this workstation, 2400x2400 uint16 frames, 60 publishes:

===============================  =========================
``try_publish`` that publishes   **1.14 ms** median (1.74 max) at max_w=640
                                 3.98 ms median at max_w=1200
``try_publish`` the cap rejects  **0.30 us** median
===============================  =========================

So a 50 Hz (20 ms) loop publishing at the 10 fps default pays 1.14 ms on one
tick in five and 0.3 us on the rest -- about 0.3% of the budget. Raising
``max_w`` is the expensive knob, not ``max_fps``: the payload is quadratic in
it, and 1200 already costs a fifth of a 20 ms tick.

TORN READS, AND WHAT IS DONE ABOUT THEM
---------------------------------------
There is no lock across the segment -- a lock shared with a process that
might be paused under a debugger is worse than the problem. Instead the
version counter is written *after* the pixels, and :meth:`ShmSubscriber.poll`
re-reads it after copying: if it moved, the copy straddled a write and is
retried. That is a seqlock, and it makes a torn frame a retry rather than a
displayed artifact. It does not make the channel lossless, and it is not
meant to be -- see the warning below.

⚠ THIS IS A DISPLAY CHANNEL, NOT A DATA CHANNEL
-----------------------------------------------
It decimates, it drops to 8 bits, and it drops whole frames on the ``max_fps``
cap. Nothing that comes out of a subscriber can be measured -- no MSD, no
photometry, no calibration. This is the same restriction ``live_view.py``
already states for its own display path, for the same reasons, and it applies
to anything reading this segment. Frames worth measuring go to disk from the
acquiring process.

WINDOWS BEHAVIOUR, WHICH DIFFERS
--------------------------------
``multiprocessing.shared_memory`` works on both platforms, but not the same
way, and this rig is Windows:

* ``unlink()`` is a no-op on Windows. A segment is freed when the last handle
  to it closes, so a publisher that exits takes the segment with it once the
  subscriber also closes -- there are no stale segments to clean up after a
  crash, which is the failure the POSIX ``resource_tracker`` dance below
  exists to handle.
* A subscriber that already holds a handle keeps a *valid mapping* after the
  publisher exits; the pixels simply stop changing. So "publisher gone" looks
  exactly like "publisher idle" from inside :meth:`poll`, which returns
  ``None`` for both. :attr:`ShmSubscriber.age` is how a viewer tells them
  apart -- a version that has not moved for seconds is a dead publisher.
* A subscriber that attaches *before* any publisher gets ``FileNotFoundError``
  rather than a wait, hence the ``wait``/``timeout`` arguments. Note the
  publisher does not create its segment until its first ``try_publish`` --
  it has no shape before then -- so a subscriber built in the same breath as
  the publisher must be the one that waits.
* **A segment cannot be resized while a subscriber holds a handle**, because
  the handle keeps the name alive and recreating it raises
  ``FileExistsError``. So the segment is allocated once at ``max_w**2`` and
  never resized; a frame smaller than that leaves the tail of the buffer
  unread. Fitting the segment to each frame instead made an ROI change
  mid-run fail whenever a viewer was attached.
* Two live publishers on one name is refused with a diagnostic rather than a
  bare ``WinError 183``. There is no taking over a name someone else is
  publishing to; give the second one its own.

The tests cover the header, the seqlock, the rate cap and the decimation with
both ends in one process, and spawn a real second interpreter for the part
that only a second process can answer. What they cannot cover is a real
camera on the producing end.
"""

from __future__ import annotations

import os
import struct
import time
from multiprocessing import shared_memory
from typing import Optional

import numpy as np

__all__ = ["ShmPublisher", "ShmSubscriber", "HEADER_SIZE"]

# version:u64, ts:f64, vh:i32, vw:i32, full_h:i32, full_w:i32
#
# The full sensor shape travels with every frame because a subscriber drawing
# an overlay needs to map its own pixels back to sensor coordinates, and
# therefore to microns. The bacteria stack's header carries only the
# published shape, which left `run_viz.py` reconstructing the decimation from
# a hardcoded native size -- a constant that is wrong the first time anyone
# sets an ROI.
_HDR_FMT = "<Qdiiii"
HEADER_SIZE = struct.calcsize(_HDR_FMT)

_MAX_SEQLOCK_RETRIES = 4


def _quiet_resource_tracker() -> None:
    """Stop the POSIX resource tracker warning about segments it does not own.

    On POSIX, ``shared_memory`` registers every segment with a tracker process
    that unlinks leftovers at exit and prints a ``UserWarning`` for each. A
    subscriber that attaches to someone else's segment gets registered too and
    then gets blamed for leaking it. Both ends here manage their own lifetime,
    so the tracker has nothing useful to add.

    A no-op on Windows, where there is no tracker and no ``unlink`` -- guarded
    rather than patched blindly, because the bacteria original patches
    unconditionally and the patch is dead code on the platform this rig runs.
    """
    if os.name == "nt":
        return
    try:
        from multiprocessing import resource_tracker

        original_register = resource_tracker.register
        original_unregister = resource_tracker.unregister

        def register(name, rtype):  # noqa: ANN001
            if rtype == "shared_memory":
                return
            return original_register(name, rtype)

        def unregister(name, rtype):  # noqa: ANN001
            if rtype == "shared_memory":
                return
            return original_unregister(name, rtype)

        resource_tracker.register = register
        resource_tracker.unregister = unregister
        resource_tracker._CLEANUP_FUNCS.pop("shared_memory", None)
    except Exception:  # noqa: BLE001 - a tracker we cannot patch is not fatal
        pass


def decimate(frame: np.ndarray, max_edge: int) -> tuple[np.ndarray, int]:
    """Stride-decimate ``frame`` so its longest edge is <= ``max_edge``.

    Returns ``(view, step)``. An integer stride and a plain slice, so the
    "resize" is a view and costs nothing until it is copied. No interpolation:
    averaging would be a per-frame pass over 11.5 MB on the producer's clock,
    and the result is going to an 8-bit display either way.

    The **longest** edge, not the width. Two reasons: it matches
    ``--display`` in ``config/micromanager/live_view.py``, whose help calls it
    "longest on-screen edge"; and it bounds the payload at ``max_edge**2``,
    which is what lets :class:`ShmPublisher` allocate once and never resize.
    Capping the width alone leaves a portrait frame taller than the cap.

    ``live_view.py`` has its own ``decimate``. This one is here so the
    publisher does not have to import a 47 kB module that pulls in cv2.
    """
    h, w = frame.shape[:2]
    longest = max(h, w)
    step = 1 if longest <= max_edge else int(np.ceil(longest / max_edge))
    return frame[::step, ::step], step


class ShmPublisher:
    """Producer side. Owned by whichever process owns the camera.

    ``try_publish`` is safe to call every tick; the ``max_fps`` cap decides
    whether the call does anything, so the caller does not have to keep its
    own timer.

    Parameters
    ----------
    name : str
        Segment name. Subscribers attach to the same string. Keep it specific
        to the camera -- ``kinetix_red`` rather than ``live`` -- because two
        publishers on one name is a size fight, not a merge.
    max_w : int, optional
        Decimate until the frame's longest edge is at most this, before
        publishing. Default 640. Also fixes the segment at ``max_w**2``
        bytes (410 kB by default), allocated once on the first publish.
    max_fps : float, optional
        Publish-rate ceiling. Default 10.
    shift_right : int, optional
        Right-shift for uint16 input, to reach uint8. Default 8 (the high
        byte). Pass 4 for a sensor that never fills the top bits -- a Kinetix
        in 12-bit mode leaves the top 4 empty, so ``>>8`` throws away half the
        signal's range and the view looks dark. Ignored for uint8 input.
    now : callable, optional
        Clock, for tests.
    """

    def __init__(
        self,
        name: str,
        *,
        max_w: int = 640,
        max_fps: float = 10.0,
        shift_right: int = 8,
        now=time.perf_counter,
    ) -> None:
        if max_w < 1:
            raise ValueError(f"max_w must be >= 1, got {max_w}")
        if max_fps <= 0:
            raise ValueError(f"max_fps must be > 0, got {max_fps}")
        _quiet_resource_tracker()
        self.name = str(name)
        self.max_w = int(max_w)
        self.max_fps = float(max_fps)
        self.shift_right = int(shift_right)
        self._now = now

        self._shm: Optional[shared_memory.SharedMemory] = None
        self._shape: Optional[tuple[int, int]] = None
        self._size = 0
        self._version = 0
        self._last_publish = float("-inf")
        self._published = 0
        self._skipped = 0

    def __enter__(self) -> "ShmPublisher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #

    def _ensure(self) -> None:
        """Create the segment, once, at the worst-case size. Never resizes.

        The segment is ``HEADER_SIZE + max_w**2`` bytes -- big enough for any
        frame :func:`decimate` can produce, since that caps the longest edge
        at ``max_w``. The actual ``(vh, vw)`` of each frame travels in the
        header, so a smaller payload just leaves the tail of the buffer
        unread.

        It is allocated for the worst case rather than fitted to the frame
        because **a Windows segment cannot be resized while a subscriber holds
        a handle to it**. A handle keeps the name alive, so freeing and
        recreating raises ``FileExistsError`` -- which meant an ROI change
        mid-run took the publisher down whenever a viewer was attached. One
        allocation removes the failure rather than reporting it. At the
        default ``max_w=640`` that is 410 kB, allocated once.

        (An earlier version fitted the segment to each frame and compared
        ``SharedMemory.size`` to decide whether to reuse it. Windows rounds an
        allocation up to a page, so a 288-byte request reports back as 4096,
        the comparison never matched, and the segment was destroyed and
        recreated on *every frame* -- resetting the version counter each time,
        so a subscriber saw one frame and then nothing.)
        """
        if self._shm is not None:
            return

        size = HEADER_SIZE + self.max_w * self.max_w
        try:
            self._shm = shared_memory.SharedMemory(
                name=self.name, create=True, size=size
            )
        except FileExistsError:
            # POSIX: a leftover from a publisher that crashed without closing.
            # Take it over, since a subscriber sizes its read from the header
            # and a stale segment of the wrong size would be misread.
            #
            # Windows: `unlink` does not exist there, and a segment lives as
            # long as any handle to it -- so this branch means a *live* second
            # publisher, and there is no taking it over. Say that, rather than
            # re-raising a WinError 183 that names no cause.
            if os.name == "nt":
                raise RuntimeError(
                    f"a shared-memory segment named {self.name!r} already "
                    f"exists. On Windows that means another process is "
                    f"publishing to it right now (segments are freed when the "
                    f"last handle closes, so there are no stale ones). Two "
                    f"publishers on one name cannot be merged -- give this one "
                    f"its own name."
                ) from None
            existing = shared_memory.SharedMemory(name=self.name, create=False)
            existing.close()
            try:
                existing.unlink()
            except (FileNotFoundError, OSError):
                pass
            self._shm = shared_memory.SharedMemory(
                name=self.name, create=True, size=size
            )
        self._size = size
        self._version = 0

    def _destroy(self) -> None:
        if self._shm is None:
            return
        try:
            self._shm.close()
        finally:
            try:
                self._shm.unlink()  # no-op on Windows
            except (FileNotFoundError, OSError):
                pass
        self._shm = None
        self._shape = None
        self._size = 0

    def close(self) -> None:
        """Release the segment. Idempotent; call it from a ``finally``."""
        self._destroy()

    # ------------------------------------------------------------------ #

    def try_publish(
        self, frame: np.ndarray, ts: float, *, force: bool = False
    ) -> bool:
        """Publish ``frame`` if the rate cap allows. Returns whether it did.

        Parameters
        ----------
        frame : numpy.ndarray
            ``(h, w)``, uint16 or uint8.
        ts : float
            Timestamp to carry with the frame, on whatever clock the producer
            is using. Passed through untouched -- a subscriber cannot compare
            it to its own ``perf_counter``, which has a different origin per
            process, so it is for relating frames to each other.
        force : bool, optional
            Bypass the rate cap. For the last frame before shutdown, so a
            viewer's final image is the state things were left in.
        """
        t = self._now()
        if not force and (t - self._last_publish) < (1.0 / self.max_fps):
            self._skipped += 1
            return False

        arr = np.asarray(frame)
        if arr.ndim != 2:
            raise ValueError(f"frame must be 2-D (h, w); got shape {arr.shape}")
        full_h, full_w = arr.shape
        view, _step = decimate(arr, self.max_w)
        vh, vw = view.shape

        self._ensure()
        assert self._shm is not None
        self._shape = (vh, vw)

        if arr.dtype == np.uint8:
            payload = view
        else:
            payload = (view.astype(np.uint16, copy=False) >> self.shift_right).astype(
                np.uint8, copy=False
            )

        # Pixels first, version last: a subscriber that reads the version
        # before and after its copy can tell that the copy was clean. Writing
        # the version first would make a torn read undetectable.
        self._shm.buf[HEADER_SIZE:HEADER_SIZE + payload.size] = payload.tobytes()
        self._version += 1
        self._shm.buf[:HEADER_SIZE] = struct.pack(
            _HDR_FMT, self._version, float(ts), vh, vw, full_h, full_w
        )
        self._last_publish = t
        self._published += 1
        return True

    def report(self) -> str:
        """One line: how many frames went out and how many the cap dropped."""
        total = self._published + self._skipped
        if not total:
            return f"{self.name}: nothing published"
        return (f"{self.name}: {self._published} published, {self._skipped} "
                f"dropped by the {self.max_fps:g} fps cap "
                f"({100.0 * self._published / total:.0f}% of offers), "
                f"{'x'.join(str(v) for v in (self._shape or ()))} uint8")


class ShmSubscriber:
    """Consumer side. Attaches by name; never unlinks.

    Parameters
    ----------
    name : str
        Must match the publisher's.
    wait : bool, optional
        Block until the segment exists. A viewer started before the run is
        the normal case, so this defaults to True.
    timeout : float, optional
        Seconds to wait when ``wait=True``. ``None`` waits forever.
    poll_interval : float, optional
        How often to look while waiting.
    now : callable, optional
        Clock, for tests.
    """

    def __init__(
        self,
        name: str,
        *,
        wait: bool = True,
        timeout: Optional[float] = 30.0,
        poll_interval: float = 0.1,
        now=time.perf_counter,
    ) -> None:
        _quiet_resource_tracker()
        self.name = str(name)
        self._now = now
        self._shm: Optional[shared_memory.SharedMemory] = None
        self._last_version = 0
        self._t_last_change = now()
        self._attach(wait=wait, timeout=timeout, poll_interval=poll_interval)

    def __enter__(self) -> "ShmSubscriber":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _attach(
        self, *, wait: bool, timeout: Optional[float], poll_interval: float
    ) -> None:
        deadline = None if timeout is None else self._now() + timeout
        while True:
            try:
                self._shm = shared_memory.SharedMemory(name=self.name, create=False)
                return
            except FileNotFoundError:
                if not wait:
                    raise
                if deadline is not None and self._now() > deadline:
                    raise TimeoutError(
                        f"no shared-memory segment named {self.name!r} after "
                        f"{timeout:.1f} s. Is the acquiring process running "
                        f"with a publisher on that name?"
                    ) from None
                time.sleep(poll_interval)

    def close(self) -> None:
        """Detach. Never unlinks -- the publisher owns the segment's lifetime."""
        if self._shm is not None:
            self._shm.close()
            self._shm = None

    # ------------------------------------------------------------------ #

    def _header(self) -> tuple[int, float, int, int, int, int]:
        assert self._shm is not None
        return struct.unpack(_HDR_FMT, bytes(self._shm.buf[:HEADER_SIZE]))

    @property
    def age(self) -> float:
        """Seconds since the version last changed.

        The only way to tell an idle publisher from a dead one on Windows,
        where a subscriber's mapping stays valid after the publisher exits and
        the pixels simply stop moving. A viewer should say so on screen rather
        than keep showing a frozen frame as if it were live.
        """
        return self._now() - self._t_last_change

    def poll(self) -> Optional[tuple[np.ndarray, float, dict]]:
        """Return ``(frame, ts, meta)`` if a new frame has been published.

        ``None`` means nothing new -- either the publisher has not published
        since the last call, or (on Windows) it has exited. Check :attr:`age`
        to distinguish those.

        ``meta`` carries ``full_h``/``full_w`` (the undecimated sensor shape)
        and ``step`` (the decimation stride), which is what an overlay needs
        to convert its own pixel coordinates back to sensor pixels and then to
        microns.

        The returned array is always a copy: the segment underneath it is
        being overwritten by another process, so a view would change while it
        was being drawn.
        """
        if self._shm is None:
            return None
        for _ in range(_MAX_SEQLOCK_RETRIES):
            version, ts, vh, vw, full_h, full_w = self._header()
            if version == self._last_version:
                return None
            if vh <= 0 or vw <= 0:
                return None  # header not written yet
            end = HEADER_SIZE + vh * vw
            if end > self._shm.size:
                # The publisher resized (an ROI change) and this handle still
                # maps the old, smaller segment. Reattaching is the caller's
                # move; say nothing rather than read past the end.
                return None
            frame = np.frombuffer(
                bytes(self._shm.buf[HEADER_SIZE:end]), dtype=np.uint8
            ).reshape(vh, vw)
            # Seqlock check: if the version moved while we copied, the copy may
            # straddle two frames. Retry rather than display a torn one.
            if self._header()[0] != version:
                continue
            self._last_version = version
            self._t_last_change = self._now()
            step = max(1, full_w // vw) if vw else 1
            return frame, ts, {
                "version": version,
                "full_h": full_h,
                "full_w": full_w,
                "step": step,
            }
        return None
