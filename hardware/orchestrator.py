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

WHAT IS OPTIONAL, AND WHAT IS NOT
---------------------------------
The three surfaces are not always used together and a device is sometimes just
switched off, so a session declares a ``Roster`` of what is on. The microscope
is always on -- it need not be named and cannot be excluded, because its
per-frame ``ElapsedTime-ms`` series is what everything else is aligned to.

Three things follow, and they are the reason the roster is not merely
bookkeeping:

    the handoff     ``microscope_setup()`` waits for the camera to be released
                    only when the tweezers are enrolled. With them off, nothing
                    ever took the Kinetix and the session goes straight from
                    IDLE to MICROSCOPE_SETUP. Demanding the release
                    unconditionally -- which this module did until 2026-08-27 --
                    blocks the microscope on a release nobody will perform.
    the tracks      ``add_track`` for an absent subsystem is dropped and
                    recorded, so the program keeps its shape instead of growing
                    a presence check at every call site.
    the record      ``Roster.missing_from_record()`` names what the run cannot
                    measure, so an absent instrument does not read afterwards
                    like a null result.

TRACKS: ONE THREAD PER SUBSYSTEM, ONE BARRIER
---------------------------------------------
``add_track`` then ``run_tracks``. Every track is released from a single
``threading.Barrier``, so the spread between starts is OS scheduling and not
the sum of three connect times, and ``start_spread_s`` measures it rather than
assuming it. One track per subsystem is enforced -- that is what confines the
piezo's single DLL instance handle to one thread. A track that raises sets a
cooperative ``stop`` event and its exception comes back in its ``TrackResult``
instead of escaping the call, because with three instruments live the other two
still need winding down.

ALIGNING THE HARDWARE CLOCKS
----------------------------
``Clock`` makes host events comparable. It does not make *hardware* events
comparable, and hardware is where the real timing lives. ``Timeline.anchor()``
is the bridge: bracket the one command that starts a hardware-timed run, and it
records the host time of that start with an explicit uncertainty -- half the
command's round trip, since the hardware began somewhere inside it. After that,
sample and frame times come from the hardware's own rate
(``host_of_sample``), never from another host stamp.

Every anchor also records *which* clock carries the run -- ``HARDWARE`` or
``HOST_SCHED`` -- because the piezo is host-scheduled today and becomes
hardware-timed the day its generator's sample unit is settled, and the two must
not look the same in the record.

``alignment_error_s(a, b)`` is then the number that says what may be claimed
across two subsystems. With measured round trips of ~0.7-2.6 ms on the piezo
and ~2-6 ms on the tweezers, a claim like "the stage was at the peak on frame
412" holds at 1 Hz and does not hold at 500 fps. Tightening it needs a hardware
trigger (``function.trigger-inputs.*``, ``/Dev1/PFI0``), not better host code.

CAMERA ARBITER
--------------
The tweezers GUI takes one of the two Kinetix bodies and later releases it, and
PVCAM hands a camera to exactly one process at a time -- so the required order
is tweezers first, release, then Micro-Manager. ``CameraArbiter`` enforces that
instead of leaving it to be remembered. See the module comment on
``microscope.SHARED_DEVICES``.
"""

from __future__ import annotations

import csv
import statistics
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

#: The three control surfaces. These strings are the roster keys and the
#: ``subsystem`` column of every log line and every timeline row, so they are
#: the one vocabulary -- do not invent a second spelling for a subsystem.
MICROSCOPE = "microscope"
TWEEZERS = "tweezers"
PIEZO = "piezo"

SUBSYSTEMS = (MICROSCOPE, TWEEZERS, PIEZO)

#: The coordinator's own rows in the timeline. Not a subsystem and not on the
#: roster, but it has things to say: the roster, and the common start.
SESSION = "session"

#: What actually advances a run once it has started. Every anchor must say
#: which, because the difference is not cosmetic:
#:
#:   HARDWARE    a preloaded hardware clock carries it -- the AOD trap loop at
#:               50 kHz, the NPC-D's 20 us servo, the camera's own readout. The
#:               host stamps the start and then has no further influence, so the
#:               only error is in the anchor.
#:   HOST_SCHED  the host issues each step against absolute deadlines from one
#:               t0. Measured good to about a millisecond -- the piezo's 60 s
#:               1 Hz run showed slip median 1 us, max 1.07 ms and 0/6000
#:               overruns, and a 3.000 s tweezers breakpoint gap landed at
#:               +3 us -- but it is a schedule, not a clock, and a Windows
#:               hiccup lands in the data instead of being absorbed.
#:
#: Recorded per anchor because the piezo is HOST_SCHED *today* and becomes
#: HARDWARE the day ``function.waveform``'s sample unit is settled
#: (piezo_stage.WAVEFORM_DATA_UNITS, blocked on one constant-waveform run). A
#: record that did not distinguish them would make those two runs -- same
#: script, same trajectory, two different timing guarantees -- look identical.
HARDWARE = "hardware"
HOST_SCHED = "host schedule"

#: The microscope is not optional (user, 2026-08-27: "always the microscope
#: will be on"), and it could not be even if someone wanted it to: the camera's
#: per-frame ``ElapsedTime-ms`` series is the series every other subsystem gets
#: aligned onto, so a run without it has no shared time base to speak of.
REQUIRED = frozenset({MICROSCOPE})

#: Who may hold a shared camera. This names the *process* that contends for
#: PVCAM rather than the control surface: the other contender is the Tweez GUI,
#: a separate Windows program, so ownership is a question about processes.
#: ``MICROSCOPE`` is the subsystem; ``MICROMANAGER`` is the camera owner.
MICROMANAGER = "micromanager"

#: What a run stops being able to measure when a subsystem is off. Printed in
#: the report, because an absent subsystem leaves a gap in the record that
#: otherwise reads like a null result rather than like a missing instrument.
LOST_WITHOUT = {
    TWEEZERS: (
        "no trap position, so no trap force: F = kappa*(x_bead - x_trap) needs "
        "x_trap and nothing else in the rig produces it"
    ),
    PIEZO: (
        "no stage trajectory, so the sample frame is whatever the sample does "
        "on its own -- no imposed flow, shear or scan"
    ),
}


class OrchestratorError(RuntimeError):
    """Raised for an out-of-order phase, or a contended camera."""


class Phase(IntEnum):
    """Setup order, and it only moves forward.

    Not decoration: the tweezers GUI needs the camera for its own calibration
    and visual trap setup, and cannot get it once Micro-Manager has loaded a
    configuration that initialises the Kinetix.

    **Two of these phases exist only to hand the camera over, so they only
    happen when there is something to hand it to.** With the tweezers absent
    from the roster, nothing ever holds the Kinetix and the session goes
    straight from ``IDLE`` to ``MICROSCOPE_SETUP``; ``TWEEZERS_SETUP`` and
    ``CAMERA_RELEASED`` are skipped rather than faked. Requiring them anyway
    would block the microscope on a release that no one was ever going to
    perform -- which is what this module used to do (fixed 2026-08-27).
    """

    IDLE = 0
    TWEEZERS_SETUP = 1  # GUI has the camera: calibration, project, traps
    CAMERA_RELEASED = 2  # GUI has let go; the drive still runs over TCP
    MICROSCOPE_SETUP = 3  # MM may now load its configuration
    RUNNING = 4  # acquisition + drive together


class Roster:
    """Which control surfaces are present for this run.

    The three subsystems are not always used together, and a device is
    sometimes simply switched off. The program should not change shape for
    that: tracks for an absent subsystem are dropped instead of guarded at
    every call site, phases that only exist to hand it the camera are skipped,
    and the report states what the record is consequently missing.

    ``Roster()`` is a microscope-only run. The microscope is added whether or
    not it is named, because it is always on and everything else is timed
    against it -- see ``REQUIRED``.

        Roster()                  # microscope alone
        Roster(PIEZO)             # microscope + piezo, no tweezers
        Roster(TWEEZERS, PIEZO)   # all three

    Presence here means *enrolled*, not *proven alive*. Nothing in this module
    opens a device, so a roster is a declaration by the caller; whether the
    link actually answers is the driver's business, and on the tweezers it is
    what ``OpticalTweezers.wait_until_ready()`` is for.
    """

    def __init__(self, *subsystems: str) -> None:
        wanted = set(subsystems) | set(REQUIRED)
        unknown = sorted(wanted - set(SUBSYSTEMS))
        if unknown:
            raise OrchestratorError(
                f"unknown subsystem(s) {unknown}; known: {list(SUBSYSTEMS)}"
            )
        self.present = frozenset(wanted)

    def __contains__(self, subsystem: object) -> bool:
        return subsystem in self.present

    def __iter__(self) -> Iterator[str]:
        """In ``SUBSYSTEMS`` order, so reports are stable."""
        return iter(s for s in SUBSYSTEMS if s in self.present)

    def __len__(self) -> int:
        return len(self.present)

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(s for s in SUBSYSTEMS if s not in self.present)

    def missing_from_record(self) -> tuple[str, ...]:
        """One line per absent subsystem, naming what cannot be measured."""
        return tuple(
            f"{s}: {LOST_WITHOUT[s]}" for s in self.absent if s in LOST_WITHOUT
        )

    def __str__(self) -> str:
        off = f"; off: {', '.join(self.absent)}" if self.absent else ""
        return f"{', '.join(self)}{off}"

    def __repr__(self) -> str:
        return f"Roster({', '.join(repr(s) for s in self)})"


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


@dataclass(frozen=True)
class Mark:
    """One instant on the shared clock: something happened, and this is when."""

    subsystem: str
    event: str
    t_s: float
    detail: str = ""


@dataclass(frozen=True)
class HardwareAnchor:
    """Ties one subsystem's own hardware clock to the shared host base.

    This is the piece that makes "one common timestamp" mean something, because
    not one of the three subsystems is timed by the host:

        camera      MM's per-frame ``ElapsedTime-ms`` series
        tweezers    the AOD trap loop -- 50,000 points at 50 kHz is 1.000 s per
                    cycle and 0.250 s to a breakpoint at index 12,500, exact
                    rather than nominal
        piezo       the 20 us servo period; or the function generator's
                    ``sample-period``, once its sample unit is settled

    Each is its own precise clock with its own zero, and they can be compared
    only through the host. So the host stamp at the instant a hardware-timed
    run *starts* carries the entire alignment, and every later time comes from
    arithmetic on the hardware's own rate -- never from another host stamp.
    That is the opposite of stamping each event as it is noticed, and it is why
    this is worth a class: the host is allowed to be jittery exactly once per
    run, at the start, instead of once per event.

    THE UNCERTAINTY IS THE POINT
    ----------------------------
    That instant cannot be observed, only bracketed: the start command is a
    round trip and the hardware began somewhere inside it. So the anchor keeps
    both ends, and reports the midpoint with half the round trip as its
    uncertainty. The measured round trips make it concrete -- 0.69 ms median
    and 2.60 ms max for ``stage.position.command.set``, 1.9 ms for
    ``TRAP_POSITION``, ~4-6 ms for ``TRAP_PATT_RELEASE_BP`` -- so a
    piezo-to-tweezers alignment is good to a few milliseconds and no better.
    ``alignment_error_s`` states that as a number rather than leaving it to be
    assumed. At 1 Hz with 100 samples per cycle it is a fraction of one sample;
    at 500 fps it is several frames, and no amount of care here changes that.
    A hardware trigger would, which is what ``function.trigger-inputs.*`` and
    ``/Dev1/PFI0`` are for and why they are still on the open list.
    """

    subsystem: str
    label: str
    t_before_s: float
    t_after_s: float
    clock: str
    rate_hz: float | None = None

    @property
    def host_t0_s(self) -> float:
        """Best estimate of the host time at which the hardware clock started."""
        return 0.5 * (self.t_before_s + self.t_after_s)

    @property
    def uncertainty_s(self) -> float:
        """Half the start command's round trip. The hardware began inside it."""
        return 0.5 * (self.t_after_s - self.t_before_s)

    def host_of(self, hw_t_s: float) -> float:
        """Host-clock time of a moment ``hw_t_s`` into the hardware run."""
        return self.host_t0_s + hw_t_s

    def host_of_sample(self, index: int) -> float:
        """Host-clock time of hardware sample (or frame) ``index``.

        Uses the hardware rate, so it stays exact however long the run is --
        which is the point of asking the hardware for its own clock instead of
        stamping arrivals on the host.
        """
        if not self.rate_hz:
            raise OrchestratorError(
                f"no rate recorded for the {self.subsystem} anchor "
                f"({self.label!r}), so sample {index} has no time; pass "
                "rate_hz= when anchoring"
            )
        return self.host_t0_s + index / self.rate_hz


@dataclass(frozen=True)
class Entry:
    """One row of the merged record -- marks and timed operations together."""

    t_s: float
    subsystem: str
    kind: str  # "mark" or "op"
    event: str
    duration_ms: float
    ok: bool
    detail: str


class Timeline:
    """The shared record: what happened, when, on whose clock.

    Distinct from ``LatencyLog``, which measures how long host calls take.
    This answers the other question -- *when did it happen, and how well do I
    know* -- and holds the hardware anchors that let a subsystem's own clock be
    read in host time. Both share one ``Clock``, so ``merged()`` interleaves
    them into a single ordered record.
    """

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._marks: list[Mark] = []
        self._anchors: list[HardwareAnchor] = []
        self._lock = threading.Lock()

    def mark(self, subsystem: str, event: str, detail: str = "") -> Mark:
        """Stamp an instant. Safe to call from any track's thread."""
        m = Mark(subsystem, event, self.clock.now_s(), detail)
        with self._lock:
            self._marks.append(m)
        return m

    @contextmanager
    def anchor(
        self,
        subsystem: str,
        label: str,
        *,
        clock: str,
        rate_hz: float | None = None,
    ) -> Iterator[None]:
        """Bracket the one command that starts a timed run.

            with session.timeline.anchor(
                PIEZO, "sine 1 Hz", clock=HOST_SCHED, rate_hz=100.0
            ):
                t0 = time.perf_counter()   # the drive's own zero

        ``clock`` has no default on purpose: ``HARDWARE`` and ``HOST_SCHED``
        carry different guarantees and only the caller knows which one it just
        started.

        Put *only* the start command inside. Anything else in the body widens
        the bracket and the uncertainty then reports your setup code rather
        than the link. Read the result back with ``anchor_of``.

        A start command that raises records **no anchor**, only a failure mark.
        The hardware's zero is genuinely unknown in that case, and an anchor
        that looked usable would hand every later ``host_of_sample`` a
        plausible number with nothing behind it.
        """
        t_before = self.clock.now_s()
        try:
            yield
        except BaseException:
            self.mark(subsystem, "start failed", label)
            raise
        t_after = self.clock.now_s()
        with self._lock:
            self._anchors.append(
                HardwareAnchor(subsystem, label, t_before, t_after, clock, rate_hz)
            )
        self.mark(subsystem, f"{clock} started", label)

    @property
    def marks(self) -> tuple[Mark, ...]:
        with self._lock:
            return tuple(self._marks)

    @property
    def anchors(self) -> tuple[HardwareAnchor, ...]:
        with self._lock:
            return tuple(self._anchors)

    def anchor_of(self, subsystem: str) -> HardwareAnchor | None:
        """The most recent anchor for ``subsystem``, or None if never started.

        Most recent rather than first: restarting a waveform or re-assigning a
        pattern resets that subsystem's zero, and the live one is the one that
        maps its samples.
        """
        for a in reversed(self.anchors):
            if a.subsystem == subsystem:
                return a
        return None

    def host_of(self, subsystem: str, hw_t_s: float) -> float:
        a = self._require_anchor(subsystem)
        return a.host_of(hw_t_s)

    def host_of_sample(self, subsystem: str, index: int) -> float:
        a = self._require_anchor(subsystem)
        return a.host_of_sample(index)

    def alignment_error_s(self, first: str, second: str) -> float:
        """Worst-case host-time offset between two subsystems' zeros.

        The sum of the two anchor uncertainties -- the error in *where the runs
        started*. For two ``HARDWARE`` anchors that is the whole budget: each
        run is then carried exactly by its own clock, so nothing further
        accumulates.

        **For a ``HOST_SCHED`` anchor it is a lower bound.** The zero of a
        host-scheduled loop is known well (the start command is free, so the
        bracket is near zero), but every later step carries the schedule's own
        slip, which is a per-step quantity this class never sees. Add the
        loop's measured slip -- ``config/session/run_parallel.scheduled_loop``
        reports median and max per run -- to get the real budget.

        Either way this is the number that decides whether "the piezo was at
        the peak on frame 412" may be said: if the total exceeds the frame
        period, it may not.
        """
        return (
            self._require_anchor(first).uncertainty_s
            + self._require_anchor(second).uncertainty_s
        )

    def _require_anchor(self, subsystem: str) -> HardwareAnchor:
        a = self.anchor_of(subsystem)
        if a is None:
            raise OrchestratorError(
                f"{subsystem} has no hardware anchor: nothing recorded the host "
                "time at which its clock started, so its samples cannot be "
                "placed on the shared timeline. Wrap the start command in "
                "timeline.anchor()"
            )
        return a

    def merged(self, latency: LatencyLog | None = None) -> tuple[Entry, ...]:
        """Marks and (optionally) timed operations, in one time order."""
        rows = [
            Entry(m.t_s, m.subsystem, "mark", m.event, 0.0, True, m.detail)
            for m in self.marks
        ]
        if latency is not None:
            rows += [
                Entry(
                    op.t_start_s,
                    op.subsystem,
                    "op",
                    op.name,
                    op.duration_ms,
                    op.ok,
                    op.detail,
                )
                for op in latency.ops
            ]
        return tuple(sorted(rows, key=lambda e: e.t_s))

    def report(self, latency: LatencyLog | None = None) -> str:
        rows = self.merged(latency)
        lines = [f"{'t (s)':>9}  {'subsystem':12} {'ms':>8}  what"]
        for e in rows:
            dur = f"{e.duration_ms:8.3f}" if e.kind == "op" else " " * 8
            flag = "" if e.ok else "  !! "
            tail = f"   {e.detail}" if e.detail else ""
            lines.append(
                f"{e.t_s:9.4f}  {e.subsystem:12} {dur}  {flag}{e.event}{tail}"
            )
        if not rows:
            lines.append("  (nothing recorded)")
        for a in self.anchors:
            rate = f", {a.rate_hz:g} Hz" if a.rate_hz else ""
            lines.append(
                f"  anchor  {a.subsystem:12} t0 = {a.host_t0_s:.4f} s "
                f"+/- {1e3 * a.uncertainty_s:.3f} ms  [{a.clock}]  "
                f"({a.label}{rate})"
            )
        return "\n".join(lines)

    def to_csv(self, path: str | Path, latency: LatencyLog | None = None) -> Path:
        """Write the merged record, with wall time alongside the host clock.

        ``wall_s`` is what lines this file up against MM's own metadata after
        the fact -- a correlation through ``Clock.anchor``, not a
        synchronisation, and only as good as the anchors above.
        """
        out = Path(path)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(
                ["t_s", "wall_s", "subsystem", "kind", "event", "duration_ms",
                 "ok", "detail"]
            )
            for e in self.merged(latency):
                w.writerow(
                    [f"{e.t_s:.6f}", f"{self.clock.wall_of(e.t_s):.6f}",
                     e.subsystem, e.kind, e.event, f"{e.duration_ms:.6f}",
                     int(e.ok), e.detail]
                )
        return out


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


@dataclass(frozen=True)
class Track:
    """One subsystem's share of the run, as the one thread that drives it.

    ``body`` is called as ``body(session, stop)`` on its own thread and may do
    whatever that subsystem needs -- it is handed the session, so it stamps
    against the shared clock and logs to the shared latency log without any of
    the three drivers knowing about each other.

    ``stop`` is a cooperative ``threading.Event``, set when any track fails.
    A body that runs for a while should check it between steps. It cannot
    interrupt anything: a driver blocked in a socket ``recv`` or inside a DLL
    call will not see it until it returns.
    """

    subsystem: str
    body: Callable[[Session, threading.Event], object]
    name: str


@dataclass(frozen=True)
class TrackResult:
    """What a track returned, or how it failed, and when it ran."""

    subsystem: str
    name: str
    started: bool
    value: object = None
    error: BaseException | None = None
    t_start_s: float = float("nan")
    t_end_s: float = float("nan")

    @property
    def ok(self) -> bool:
        return self.started and self.error is None

    @property
    def duration_s(self) -> float:
        return self.t_end_s - self.t_start_s


def start_spread_s(results: dict[str, TrackResult]) -> float:
    """How far apart the tracks actually got going, in seconds.

    Measured rather than assumed. The barrier releases every thread at once but
    the OS schedules them when it likes, so this is the real answer to "did
    they start together" -- and it is a floor on how well host-side start
    stamps alone could align two subsystems. It is not the alignment of the
    *hardware* clocks; that is ``Timeline.alignment_error_s``, and it is the
    number that matters, because a hardware-timed run does not care when its
    Python thread woke up.
    """
    started = [r.t_start_s for r in results.values() if r.started]
    return max(started) - min(started) if len(started) > 1 else 0.0


def track_report(results: dict[str, TrackResult]) -> str:
    lines = [f"{'subsystem':12} {'ran (s)':>9}  outcome"]
    for subsystem in SUBSYSTEMS:
        r = results.get(subsystem)
        if r is None:
            continue
        if not r.started:
            outcome = f"NEVER STARTED -- {r.error}"
        elif r.error is not None:
            outcome = f"FAILED -- {type(r.error).__name__}: {r.error}"
        else:
            outcome = "ok" + (f" -> {r.value!r}" if r.value is not None else "")
        ran = f"{r.duration_s:9.4f}" if r.started else " " * 9
        lines.append(f"{r.subsystem:12} {ran}  {outcome}")
    if len(results) > 1:
        spread_ms = 1e3 * start_spread_s(results)
        lines.append(f"\n   tracks started within {spread_ms:.3f} ms of each other")
    return "\n".join(lines)


class Session:
    """Holds the shared pieces and the setup order for one experiment.

    Deliberately does not wrap the drivers. Each subsystem keeps its own
    module and its own API; a caller times its calls through ``instrument``,
    which is enough to get one clock and one latency log across all three
    without a facade that has to be kept in step with three vendor protocols.

    Name the subsystems that are switched on. The microscope is always on and
    need not be named:

        Session()                  # microscope alone
        Session(PIEZO)             # microscope + piezo
        Session(TWEEZERS, PIEZO)   # all three

    What follows from the roster: an absent subsystem's track is dropped
    instead of guarded, calling it raises instead of hanging on a dead link,
    and the camera handoff only happens if there is a second program to hand
    the camera to.
    """

    def __init__(self, *present: str, camera: str = "Kinetix_red") -> None:
        self.roster = Roster(*present)
        self.clock = Clock()
        self.latency = LatencyLog(self.clock)
        self.timeline = Timeline(self.clock)
        self.camera = CameraArbiter(camera)
        self.state = SharedState(self.clock)
        #: Cooperative. Set when a track fails, so the others can wind down;
        #: a caller may also set it to stop a run early.
        self.stop = threading.Event()
        self._phase = Phase.IDLE
        self._tracks: dict[str, Track] = {}
        self._lock = threading.Lock()
        self.timeline.mark(SESSION, "roster", str(self.roster))

    # -- what is switched on --------------------------------------------

    def has(self, subsystem: str) -> bool:
        return subsystem in self.roster

    @property
    def absent(self) -> tuple[str, ...]:
        return self.roster.absent

    def require_present(self, subsystem: str) -> None:
        """Refuse a call aimed at a subsystem that is not on the roster.

        Loud rather than lenient. The alternative is a command sent at a
        switched-off instrument, which on the tweezers means a socket connect
        that hangs for the full timeout and on the piezo means a vendor error
        whose text says nothing about the cause.
        """
        if subsystem not in self.roster:
            raise OrchestratorError(
                f"{subsystem!r} is not on this session's roster ({self.roster}). "
                f"Enrol it with Session({subsystem.upper()}, ...), or guard the "
                f"call with session.has({subsystem!r})"
            )

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
        """Time and log one operation. The only thing a driver call needs.

        Refuses a subsystem that is off, so a program that forgot to guard a
        call fails at the call rather than at the instrument.
        """
        self.require_present(subsystem)
        with self.latency.timed(subsystem, name):
            yield

    # -- parallel tracks -------------------------------------------------

    def add_track(
        self,
        subsystem: str,
        body: Callable[[Session, threading.Event], object],
        name: str = "",
    ) -> bool:
        """Register the one thread that will drive ``subsystem``.

        Returns True if it was registered and False if the subsystem is off --
        so a program keeps its shape when a device is switched off, instead of
        growing a presence check at every call site.

        **One track per subsystem, enforced.** That is what confines the
        piezo's single DLL instance handle to one thread, which the vendor
        library requires and which nothing else in this process would notice
        being violated.
        """
        if subsystem not in self.roster:
            self.timeline.mark(subsystem, "track skipped", "subsystem is off")
            return False
        track = Track(subsystem, body, name or subsystem)
        with self._lock:
            if subsystem in self._tracks:
                raise OrchestratorError(
                    f"{subsystem} already has a track "
                    f"({self._tracks[subsystem].name!r}): one thread per "
                    "subsystem. The piezo's DLL handle is not safe to call "
                    "from two, and the tweezers GUI rejects overlapping "
                    "commands with -14"
                )
            self._tracks[subsystem] = track
        return True

    @property
    def tracks(self) -> tuple[Track, ...]:
        """Registered tracks, in ``SUBSYSTEMS`` order."""
        with self._lock:
            return tuple(self._tracks[s] for s in SUBSYSTEMS if s in self._tracks)

    def run_tracks(
        self, *, start_timeout_s: float = 30.0, join_timeout_s: float | None = None
    ) -> dict[str, TrackResult]:
        """Run every registered track at once, released from one barrier.

        The barrier is what makes the start common: no thread enters its body
        until all of them are ready, so the spread between starts is OS
        scheduling only (``start_spread_s`` measures it) rather than the sum of
        three driver connect times.

        A track that raises sets ``stop`` and its exception is returned in its
        ``TrackResult`` rather than raised here -- with three instruments live,
        the other two still need winding down, and one traceback escaping this
        call would skip that.

        ``join_timeout_s=None`` waits indefinitely, which is what a real drive
        wants. Give it a number and a track still running past it raises: a
        stuck driver thread with a class-4 laser armed is not something to
        return a partial result about.
        """
        tracks = self.tracks
        if not tracks:
            self.timeline.mark(SESSION, "no tracks to run", str(self.roster))
            return {}

        self.stop.clear()
        barrier = threading.Barrier(len(tracks))
        results: dict[str, TrackResult] = {}
        results_lock = threading.Lock()
        threads = [
            threading.Thread(
                target=self._drive_track,
                args=(t, barrier, results, results_lock, start_timeout_s),
                name=f"track-{t.subsystem}",
            )
            for t in tracks
        ]
        self.timeline.mark(
            SESSION, "common start", ", ".join(t.subsystem for t in tracks)
        )
        for th in threads:
            th.start()
        for th in threads:
            th.join(join_timeout_s)

        stuck = [t.subsystem for t, th in zip(tracks, threads) if th.is_alive()]
        if stuck:
            self.stop.set()
            raise OrchestratorError(
                f"still running after {join_timeout_s} s: {', '.join(stuck)}. "
                "stop is set, but a driver blocked in a socket recv or inside a "
                "DLL call will not see it -- go and deal with the instrument"
            )
        self.timeline.mark(
            SESSION,
            "tracks done",
            ", ".join(
                f"{s}={'ok' if results[s].ok else 'failed'}" for s in results
            ),
        )
        return results

    def _drive_track(
        self,
        track: Track,
        barrier: threading.Barrier,
        results: dict[str, TrackResult],
        results_lock: threading.Lock,
        start_timeout_s: float,
    ) -> None:
        def put(result: TrackResult) -> None:
            with results_lock:
                results[track.subsystem] = result

        try:
            barrier.wait(timeout=start_timeout_s)
        except threading.BrokenBarrierError:
            self.stop.set()
            self.timeline.mark(track.subsystem, "track never started", track.name)
            put(
                TrackResult(
                    track.subsystem,
                    track.name,
                    started=False,
                    error=OrchestratorError(
                        "not every track reached the common start within "
                        f"{start_timeout_s} s, so none of them ran"
                    ),
                )
            )
            return

        t_start = self.clock.now_s()
        self.timeline.mark(track.subsystem, "track start", track.name)
        value: object = None
        error: BaseException | None = None
        try:
            value = track.body(self, self.stop)
        except BaseException as exc:  # noqa: BLE001 -- recorded, not swallowed
            error = exc
            self.stop.set()
        t_end = self.clock.now_s()
        self.timeline.mark(
            track.subsystem,
            "track end" if error is None else "track failed",
            "" if error is None else f"{type(error).__name__}: {error}",
        )
        put(
            TrackResult(
                track.subsystem, track.name, True, value, error, t_start, t_end
            )
        )

    # -- the ordered handoff --------------------------------------------

    @contextmanager
    def tweezers_setup(self) -> Iterator[Session]:
        """Phase 1: the tweezers GUI holds the camera.

        Do everything here that needs a live image -- the GUI calibration
        (Magnification and Beam Position both need to see the sample) and
        visual trap setup. On exit the camera is released and the session
        advances, so Micro-Manager may take it.

        Refuses outright if the tweezers are not on the roster: taking the
        camera on behalf of a program that is not running would then block the
        microscope for the rest of the session.
        """
        self.require_present(TWEEZERS)
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

        **The release is only required if there is something holding the
        camera.** With the tweezers on the roster this refuses until they have
        let go, which is the whole point of the phase machine. With the
        tweezers switched off nothing ever took the Kinetix, so there is
        nothing to wait for and this runs straight from ``IDLE`` -- a
        tweezers-free run has no handoff in it at all.

        This module used to demand ``CAMERA_RELEASED`` unconditionally, which
        made a piezo-only or microscope-only session refuse to bring the
        microscope up: it was blocked on a release that nobody was ever going
        to perform (user, 2026-08-27).
        """
        if self.has(TWEEZERS):
            self.require(Phase.CAMERA_RELEASED)
        self.camera.require_free(MICROMANAGER)
        self.camera.acquire(MICROMANAGER)
        self.advance_to(Phase.MICROSCOPE_SETUP)

    def start_running(self) -> None:
        self.require(Phase.MICROSCOPE_SETUP)
        self.advance_to(Phase.RUNNING)
