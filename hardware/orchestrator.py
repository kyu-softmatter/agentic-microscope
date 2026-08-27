"""DRAFT -- run the three control surfaces concurrently on one shared clock.

The three drivers stay in their own files and know nothing about each other:

    hardware/microscope.py        Micro-Manager devices, via pymmcore-plus
    hardware/optical_tweezers.py  Aresis Tweez 300, via TCP 2070
    hardware/piezo_stage.py       Prior/Queensgate NPC-D, via vendor DLL

This module is only the coordinator: one time base they all stamp against, a
latency log, a camera arbiter, and a small shared-variable store. It opens no
device itself, so it is testable offline (tests/test_orchestrator.py) and adds
nothing to what a single subsystem can do alone.

THREADS, NOT PROCESSES
----------------------
All three drivers block inside C or I/O -- a socket recv, PVCAM, a ctypes DLL
call -- and every one of those releases the GIL, so threads genuinely overlap
and the GIL is not the bottleneck. Threads also give shared variables for free,
which is the point: with processes, every shared value needs IPC *and* a
clock-alignment handshake, and the handshake is exactly what you were trying to
avoid. Use processes only if a driver turns out to be thread-hostile (the
vendor DLL is the candidate -- ``PiezoStage`` holds one DLL instance handle, so
confine it to a single thread and never call it from two).

THE HOST CLOCK IS NOT THE EXPERIMENT CLOCK
------------------------------------------
``Clock`` gives one monotonic base so host-side events from all three
subsystems are comparable to each other. It is **not** what times the
experiment, and must never be used as if it were. The authoritative clock is
per-subsystem and lives in hardware:

    camera / MM     the per-frame ``ElapsedTime-ms`` series in MM's metadata
                    (compute/mm_metadata.py), plus hardware sequencing on the
                    NIDAQ hub (MaxSequenceLength 1024, triggered from
                    /Dev1/PFI0 -- config/micromanager/DMD_dualcam_LUNF.cfg)
    tweezers        the AOD trap loop, one pattern point per pass at up to
                    100 kHz (hardware/tweezers_patterns.py)
    piezo           whatever trajectory/waveform the NPC-D command set offers --
                    not yet established, see hardware/piezo_stage.py

So the pattern to build toward is: **preload the hardware-timed behaviour on
each subsystem, start them from a common trigger, and use the host only to
orchestrate and to log.** ``Clock.anchor`` records a wall-clock and monotonic
pair at construction so host stamps can be mapped onto MM's own series
afterwards; that mapping is a correlation, not a synchronisation.

WHAT THE LATENCY LOG IS FOR
---------------------------
It measures the host-to-instrument round trip -- the thing that decides what
you cannot do from Python. The tweezers interface is the case that matters:
every ``TRAP_POSITION`` is a socket round trip through the GUI, with no readback
to check it landed, so the measured distribution is the only evidence about
whether host-driven motion is usable at all. Numbers already in hand for
comparison: ``core.setProperty`` on a NIDAQ line measured 5.4 us
(config/micromanager/verify_lunf_daq.py); the tweezers round trip has never
been measured.

CAMERA ARBITER
--------------
The tweezers GUI takes one of the two Kinetix bodies and later releases it, and
PVCAM hands a camera to exactly one process at a time -- so the required order
is tweezers first, release, then Micro-Manager. ``CameraArbiter`` enforces that
instead of leaving it to be remembered. See the module comment on
``microscope.SHARED_DEVICES``.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum

#: Who may hold a shared camera.
TWEEZERS = "tweezers"
MICROMANAGER = "micromanager"


class OrchestratorError(RuntimeError):
    """Raised for an out-of-order phase, or a contended camera."""


class Phase(IntEnum):
    """Setup order, and it only moves forward.

    Not decoration: the tweezers GUI needs the camera for its own calibration
    and visual trap setup, and cannot get it once Micro-Manager has loaded a
    configuration that initialises the Kinetix.
    """

    IDLE = 0
    TWEEZERS_SETUP = 1  # GUI has the camera: calibration, project, traps
    CAMERA_RELEASED = 2  # GUI has let go; the drive still runs over TCP
    MICROSCOPE_SETUP = 3  # MM may now load its configuration
    RUNNING = 4  # acquisition + drive together


@dataclass(frozen=True)
class Op:
    """One timed host-to-instrument operation."""

    subsystem: str
    name: str
    t_start_s: float
    duration_s: float
    ok: bool
    detail: str = ""

    @property
    def duration_ms(self) -> float:
        return self.duration_s * 1e3


class Clock:
    """One monotonic base shared by every subsystem.

    ``perf_counter`` rather than ``time.time``: monotonic and high resolution,
    which is what a latency measurement needs. ``anchor`` pairs it once with a
    wall clock so host stamps can be lined up against MM metadata afterwards.
    """

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self.anchor = (time.time(), self._t0)

    def now_s(self) -> float:
        """Seconds since this clock was created."""
        return time.perf_counter() - self._t0

    def wall_of(self, t_s: float) -> float:
        """Map a clock reading back onto wall time, for correlating with MM's
        ``ElapsedTime-ms`` series. A correlation, not a synchronisation."""
        wall0, mono0 = self.anchor
        return wall0 + (t_s - (mono0 - self._t0))


class LatencyLog:
    """Thread-safe record of timed operations, with per-operation statistics."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._ops: list[Op] = []
        self._lock = threading.Lock()

    def record(self, op: Op) -> None:
        with self._lock:
            self._ops.append(op)

    @property
    def ops(self) -> tuple[Op, ...]:
        with self._lock:
            return tuple(self._ops)

    @contextmanager
    def timed(self, subsystem: str, name: str) -> Iterator[None]:
        """Time a call and log it, whether it succeeds or raises.

        A failed call's latency is kept, not dropped -- a command that errors
        after 2 s of waiting is exactly the kind of thing that ruins a
        host-timed drive, and discarding it would hide that.
        """
        start = self.clock.now_s()
        ok, detail = True, ""
        try:
            yield
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.record(
                Op(subsystem, name, start, self.clock.now_s() - start, ok, detail)
            )

    def stats(self) -> dict[tuple[str, str], dict[str, float]]:
        """Per ``(subsystem, name)``: count, failures, and the latency spread.

        Percentiles are reported as the nearest-rank order statistic rather
        than interpolated, because a latency budget cares about a value the
        instrument actually produced.
        """
        grouped: dict[tuple[str, str], list[Op]] = {}
        for op in self.ops:
            grouped.setdefault((op.subsystem, op.name), []).append(op)
        out = {}
        for key, ops in grouped.items():
            ms = sorted(op.duration_ms for op in ops)
            out[key] = {
                "count": len(ms),
                "failures": sum(1 for op in ops if not op.ok),
                "min_ms": ms[0],
                "median_ms": statistics.median(ms),
                "p95_ms": ms[min(len(ms) - 1, int(0.95 * (len(ms) - 1) + 0.5))],
                "max_ms": ms[-1],
            }
        return out

    def report(self) -> str:
        rows = self.stats()
        if not rows:
            return "no operations recorded"
        lines = [
            f"{'subsystem':12} {'op':26} {'n':>5} {'fail':>5} "
            f"{'min':>9} {'med':>9} {'p95':>9} {'max':>9}   (ms)"
        ]
        for (subsystem, name), s in sorted(rows.items()):
            lines.append(
                f"{subsystem:12} {name:26} {s['count']:>5} {s['failures']:>5} "
                f"{s['min_ms']:>9.3f} {s['median_ms']:>9.3f} "
                f"{s['p95_ms']:>9.3f} {s['max_ms']:>9.3f}"
            )
        return "\n".join(lines)


class CameraArbiter:
    """Single-owner lock over a camera two programs both want.

    Advisory, not enforced by the driver: this cannot stop the Tweez GUI, a
    separate Windows process, from grabbing a Kinetix. What it does stop is
    *this* code initialising the camera while the arbiter says the tweezers
    still hold it -- which is the mistake that produces an opaque PVCAM error
    with no hint about the cause.
    """

    def __init__(self, camera: str) -> None:
        self.camera = camera
        self._owner: str | None = None
        self._lock = threading.Lock()

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def acquire(self, owner: str) -> None:
        with self._lock:
            if self._owner is not None and self._owner != owner:
                raise OrchestratorError(
                    f"{self.camera} is held by {self._owner!r}; {owner!r} cannot "
                    "take it. PVCAM gives a camera to one process at a time -- "
                    "release it first"
                )
            self._owner = owner

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner not in (None, owner):
                raise OrchestratorError(
                    f"{owner!r} cannot release {self.camera}: held by {self._owner!r}"
                )
            self._owner = None

    def require_free(self, would_be_owner: str) -> None:
        if self.owner not in (None, would_be_owner):
            raise OrchestratorError(
                f"{self.camera} is still held by {self.owner!r} -- "
                f"{would_be_owner!r} needs it released"
            )

    @contextmanager
    def held_by(self, owner: str) -> Iterator[CameraArbiter]:
        self.acquire(owner)
        try:
            yield self
        finally:
            self.release(owner)


@dataclass
class SharedState:
    """Stamped key/value store for the handful of variables that cross
    subsystems -- current objective, commanded trap position, piezo setpoint.

    Every write carries the clock reading that produced it, so a reader can ask
    how stale a value is instead of assuming it is current. Nothing here is read
    back from hardware; these are *commanded* values, and on the tweezers side
    commanded is all there is.
    """

    clock: Clock
    _values: dict[str, tuple[float, object]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, key: str, value: object) -> None:
        with self._lock:
            self._values[key] = (self.clock.now_s(), value)

    def get(self, key: str, default: object = None) -> object:
        with self._lock:
            entry = self._values.get(key)
        return default if entry is None else entry[1]

    def age_s(self, key: str) -> float | None:
        """Seconds since ``key`` was last written, or None if never."""
        with self._lock:
            entry = self._values.get(key)
        return None if entry is None else self.clock.now_s() - entry[0]

    def snapshot(self) -> dict[str, tuple[float, object]]:
        with self._lock:
            return dict(self._values)


class Session:
    """Holds the shared pieces and the setup order for one experiment.

    Deliberately does not wrap the drivers. Each subsystem keeps its own
    module and its own API; a caller times its calls through ``instrument``,
    which is enough to get one clock and one latency log across all three
    without a facade that has to be kept in step with three vendor protocols.
    """

    def __init__(self, camera: str = "Kinetix_red") -> None:
        self.clock = Clock()
        self.latency = LatencyLog(self.clock)
        self.camera = CameraArbiter(camera)
        self.state = SharedState(self.clock)
        self._phase = Phase.IDLE
        self._lock = threading.Lock()

    @property
    def phase(self) -> Phase:
        with self._lock:
            return self._phase

    def advance_to(self, phase: Phase) -> None:
        """Move the session forward. Backwards is refused -- going back would
        mean the camera changed hands again, which needs a new session rather
        than a rewound flag."""
        with self._lock:
            if phase < self._phase:
                raise OrchestratorError(
                    f"cannot go back from {self._phase.name} to {phase.name}"
                )
            self._phase = phase

    def require(self, phase: Phase) -> None:
        if self.phase < phase:
            raise OrchestratorError(
                f"this needs phase {phase.name} or later; session is at "
                f"{self.phase.name}"
            )

    @contextmanager
    def instrument(self, subsystem: str, name: str) -> Iterator[None]:
        """Time and log one operation. The only thing a driver call needs."""
        with self.latency.timed(subsystem, name):
            yield

    # -- the ordered handoff --------------------------------------------

    @contextmanager
    def tweezers_setup(self) -> Iterator[Session]:
        """Phase 1: the tweezers GUI holds the camera.

        Do everything here that needs a live image -- the GUI calibration
        (Magnification and Beam Position both need to see the sample) and
        visual trap setup. On exit the camera is released and the session
        advances, so Micro-Manager may take it.
        """
        self.advance_to(Phase.TWEEZERS_SETUP)
        self.camera.acquire(TWEEZERS)
        try:
            yield self
        finally:
            self.camera.release(TWEEZERS)
            self.advance_to(Phase.CAMERA_RELEASED)

    def microscope_setup(self) -> None:
        """Phase 3: assert the camera is free, then let MM load its config.

        Call before ``Microscope.connect``. Raises rather than letting the
        PVCAM adapter fail with an error that does not name the cause.
        """
        self.require(Phase.CAMERA_RELEASED)
        self.camera.require_free(MICROMANAGER)
        self.camera.acquire(MICROMANAGER)
        self.advance_to(Phase.MICROSCOPE_SETUP)

    def start_running(self) -> None:
        self.require(Phase.MICROSCOPE_SETUP)
        self.advance_to(Phase.RUNNING)
