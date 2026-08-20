"""Individual compute-resource checks -- G12 (data rate) and G13 (buffer /
capacity / real-time CPU / RAM capture). docs/04-decision-engine.md §8;
docs/05-consensus-gate.md §5.

Mirrors optics.checks / trapping.checks: independent margins
(achieved / required), never booleans -- see optics/checks.py's module
docstring.

Sub-check numbering, as used in the messages below:

    G12a  data_rate       R < 0.7 x measured disk bandwidth
    G12b  fps_provenance  the f in R is an achieved rate, not a requested one
    G12c  pixel_container the bytes/pixel in R is the one MM actually writes
    G13a  buffer          circular buffer holds >= 5 s
    G13b  capacity        total volume fits in free disk
    G13c  realtime_cpu    per-frame processing < 1/f
    G13d  ram_capacity    RAM-capture path: whole burst fits in the RAM budget
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .resources import (
    buffer_seconds_from_frames,
    flush_seconds,
    total_capacity_bytes,
)

if TYPE_CHECKING:
    from .setup import AcquisitionResourceSetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    #: G12a: never plan to sustain more than 70% of measured disk bandwidth.
    "disk_bandwidth_fraction": 0.7,
    #: G13a: buffer must absorb at least this many seconds of transient
    #: disk latency before frames start dropping.
    "buffer_seconds_min": 5.0,
    #: G13d: RAM the capture path may claim, in MB. The machine has 255.65 GB
    #: total (kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md)
    #: but how much of it the OS, MM, and the DMD/piezo/tweezers control
    #: processes actually hold during an acquisition has never been measured
    #: -- that is still an open checkbox in that decision log. 32 GB is the
    #: ceiling authorized in the meantime (user, 2026-08-19), not a
    #: measurement of what is free. Raise it only against a measurement.
    "ram_capture_budget_mb": 32_000.0,
}


@dataclass
class CheckResult:
    code: str
    kind: str
    margin: float
    severity: str  # ok | info | warn | fail
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.margin):
            self.margin = MAX_MARGIN
        self.margin = max(0.0, min(float(self.margin), MAX_MARGIN))

    @property
    def passed(self) -> bool:
        return self.margin >= 1.0


@dataclass
class Check:
    code: str
    kind: str
    requires: tuple[str, ...]
    run: Callable[["AcquisitionResourceSetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


def _stream_summary(setup: "AcquisitionResourceSetup") -> str:
    """``red 2400x2400@200 (16bit) + blue 2400x2400@200 (16bit)``."""
    return " + ".join(
        f"{s.label} {s.width_px}x{s.height_px}@{s.fps:g} ({s.bit_depth}bit)"
        for s in setup.streams
    )


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "AcquisitionResourceSetup") -> set[str]:
    facts: set[str] = set()
    if setup.streams:
        facts.add("streams")
    if setup.disk_bandwidth_mb_s is not None:
        facts.add("disk_bandwidth")
    if setup.resolved_buffer_frames() is not None:
        facts.add("buffer_frames")
    if setup.acquisition_duration_s is not None:
        facts.add("acquisition_duration")
    if setup.free_disk_gb is not None:
        facts.add("free_disk")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_data_rate(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G12a: R < 0.7 * measured disk bandwidth. Exceeding it is a silent
    frame drop, not an error (docs/06-pitfalls.md §C5).

    On the RAM-capture path nothing is written while the camera runs, so
    this stops being a gate and G13d takes over.
    """
    rate = setup.data_rate_bytes_s()
    budget = LIMITS["disk_bandwidth_fraction"] * setup.disk_bandwidth_mb_s * 1e6

    if setup.ram_capture:
        return _ok(
            "data_rate",
            INFO,
            MAX_MARGIN,
            f"Data rate {rate / 1e6:.0f} MB/s ({_stream_summary(setup)}), but "
            "the RAM-capture path writes nothing during acquisition -- the "
            f"{budget / 1e6:.0f} MB/s disk budget does not gate here. G13d "
            "(ram_capacity) is the binding constraint instead.",
            data_rate_mb_s=rate / 1e6,
            disk_budget_mb_s=budget / 1e6,
        )

    margin = budget / rate if rate > 0 else MAX_MARGIN

    if margin >= 1.0:
        return _ok(
            "data_rate",
            HARD,
            margin,
            f"Data rate {rate / 1e6:.0f} MB/s ({_stream_summary(setup)}) is "
            f"within {LIMITS['disk_bandwidth_fraction'] * 100:.0f}% of measured "
            f"disk bandwidth ({budget / 1e6:.0f} MB/s budget).",
            data_rate_mb_s=rate / 1e6,
            disk_budget_mb_s=budget / 1e6,
        )
    return CheckResult(
        "data_rate.exceeds_disk",
        HARD,
        margin,
        "fail",
        f"Data rate {rate / 1e6:.0f} MB/s ({_stream_summary(setup)}) exceeds "
        f"the {LIMITS['disk_bandwidth_fraction'] * 100:.0f}% disk-bandwidth "
        f"budget ({budget / 1e6:.0f} MB/s). Frames will drop silently, not "
        "error (docs/06-pitfalls.md §C5).",
        action="Reduce ROI, frame rate, or stream count; write to faster "
        "storage; or switch to the RAM-capture path (ram_capture=True, "
        "calibration/ram_capture.py), which trades this gate for G13d.",
        numbers={"data_rate_mb_s": rate / 1e6, "disk_budget_mb_s": budget / 1e6},
    )


def check_fps_provenance(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G12b: the ``f`` in ``R = W*H*bytes*f`` has to be an **achieved** rate.

    docs/06-pitfalls.md §C4: a 176-row ROI at 10 ms exposure has a ~85 Hz
    camera ceiling and delivered 28 Hz -- a 3x gap, and the camera was not
    the bottleneck. Every number this lens produces scales linearly with f,
    so a requested rate makes the whole verdict a rehearsal.

    This lens does not own frame rate (that is lens 2, G9), so without lens
    2's ``detector_max_fps`` it can only warn. With it, the shortfall gets a
    margin -- the same arrangement as trapping.checks.check_sampling.
    """
    unverified = setup.unverified_fps_streams()
    if not unverified:
        return _ok(
            "fps_provenance",
            INFO,
            MAX_MARGIN,
            "Every stream's frame rate is an achieved rate, so the data-rate "
            "and capacity numbers describe what the disk will actually see.",
            fps_source="measured",
        )

    worst = max(unverified, key=lambda s: s.fps)
    labels = ", ".join(s.label for s in unverified)

    if setup.detector_max_fps is None:
        return CheckResult(
            "fps_provenance.requested",
            BIAS,
            MAX_MARGIN,
            "warn",
            f"Frame rate for {labels} is a requested rate, not an achieved "
            f"one. docs/06 §C4 measured a 3x gap between the two on this "
            "archive (85 Hz camera ceiling, 28 Hz delivered) with MM "
            "overhead or the disk -- not the camera -- as the bottleneck. "
            "Every number below scales linearly with it.",
            action="Supply detector_max_fps from lens 2 to gate realizability, "
            "and get an achieved rate from a comparable past acquisition with "
            "`python -m compute.cli drops <metadata.txt>` (its cadence_fps), "
            "then set fps_source='measured'.",
            numbers={"requested_fps": worst.fps},
        )

    margin = setup.detector_max_fps / worst.fps if worst.fps > 0 else MAX_MARGIN
    if margin >= 1.0:
        return CheckResult(
            "fps_provenance.unmeasured",
            BIAS,
            margin,
            "warn",
            f"Lens 2 puts the realizable ceiling at {setup.detector_max_fps:.0f} "
            f"fps, so the camera can deliver the {worst.fps:g} fps requested "
            f"for {labels}. That clears G9, but not §C4: there the camera was "
            "not the bottleneck either, and the delivered rate still came in "
            "3x low.",
            action="Confirm with an achieved rate before treating this verdict "
            "as measured (`python -m compute.cli drops <metadata.txt>`).",
            numbers={
                "requested_fps": worst.fps,
                "detector_max_fps": setup.detector_max_fps,
            },
        )
    return CheckResult(
        "fps_provenance.unrealizable",
        BIAS,
        margin,
        "fail",
        f"{worst.fps:g} fps is requested for {labels}, but lens 2 caps the "
        f"realizable rate at {setup.detector_max_fps:.0f} fps (G9). The "
        "acquisition will not fail -- it will quietly run slower, which makes "
        "every data-rate and capacity number below an overestimate and every "
        "lag time in the analysis wrong (§C5).",
        action="Budget for the realizable rate, or take lens 2's bottleneck "
        "out first (shorter exposure, fewer rows). Frame-rate realizability is "
        "lens 2's verdict, not this lens's.",
        numbers={
            "requested_fps": worst.fps,
            "detector_max_fps": setup.detector_max_fps,
        },
    )


def check_pixel_container(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G12c: the bytes/pixel in R must be what MM actually writes.

    MM puts 9..16-bit data in a 16-bit container, so a 12-bit mode still
    costs 2 bytes/pixel (docs/04 §8). At 8 bit MMCore reports 1 byte -- but
    whether this lab's PVCAM/Kinetix adapter hands MMCore 8-bit pixels or
    upconverts has never been checked, and the Kinetix's 8-bit Speed mode
    (500 fps full frame, data/detectors.yaml) is exactly where G12a binds.
    """
    assumed = setup.assumed_container_streams()
    if not assumed:
        return _ok(
            "pixel_container",
            INFO,
            MAX_MARGIN,
            "Every stream is 9-16 bit, which MM stores in a 16-bit container "
            "(docs/04 §8) -- 2 bytes/pixel, no assumption needed.",
        )

    labels = ", ".join(f"{s.label} ({s.bit_depth}bit)" for s in assumed)
    rate = setup.data_rate_bytes_s()
    if_upconverted = rate + sum(s.frame_bytes() * s.fps for s in assumed)
    return CheckResult(
        "pixel_container.unconfirmed",
        BIAS,
        MAX_MARGIN,
        "warn",
        f"{labels} are billed at 1 byte/pixel, giving {rate / 1e6:.0f} MB/s. "
        "MMCore reports 1 byte for an 8-bit pixel type, but that has not been "
        "confirmed against this lab's PVCAM/Kinetix adapter. If the adapter "
        f"upconverts to the 16-bit container the real rate is "
        f"{if_upconverted / 1e6:.0f} MB/s -- 2x, in the one mode fast enough "
        "for G12a to bind.",
        action="On the microscope PC, load the config and read "
        "`core.getBytesPerPixel()` in that mode (or divide a written frame's "
        "file size by its pixel count); then set container_confirmed=True.",
        numbers={
            "data_rate_mb_s": rate / 1e6,
            "data_rate_if_upconverted_mb_s": if_upconverted / 1e6,
        },
    )


def check_buffer(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13a: circular buffer must absorb >= 5 s of data at the achieved rate.

    MMCore's buffer is counted in images and shared across cameras, so the
    headroom is ``N_buffered / N_arriving_per_second`` and the frame geometry
    cancels -- which is what keeps this correct for two cameras of different
    ROI. Still a hard gate on the RAM-capture path: the pop loop that drains
    the buffer into the capture array can stall too, it just stalls on the
    CPU rather than the disk.
    """
    frames = setup.resolved_buffer_frames()
    frames_per_s = setup.frames_per_s()
    buf_bytes = frames * setup.mean_frame_bytes()
    seconds = buffer_seconds_from_frames(frames, frames_per_s)
    margin = seconds / LIMITS["buffer_seconds_min"]

    if margin >= 1.0:
        return _ok(
            "buffer",
            HARD,
            margin,
            f"{frames} frames ({buf_bytes / 1e6:.0f} MB) buffers "
            f"{seconds:.1f} s at {frames_per_s:g} frames/s "
            f"({setup.data_rate_bytes_s() / 1e6:.0f} MB/s).",
            buffer_frames=frames,
            buffer_seconds=seconds,
            buffer_mb=buf_bytes / 1e6,
        )
    return CheckResult(
        "buffer.too_small",
        HARD,
        margin,
        "fail",
        f"{frames} frames ({buf_bytes / 1e6:.0f} MB) only buffers "
        f"{seconds:.1f} s at {frames_per_s:g} frames/s (need "
        f"{LIMITS['buffer_seconds_min']:.0f} s to absorb transient stalls) "
        "-- a stall drops frames silently.",
        action="Increase CircularBufferFrameCount / available RAM, or lower "
        "the frame rate into the buffer (smaller ROI, lower fps, fewer "
        "streams, or fewer bits/pixel).",
        numbers={
            "buffer_frames": frames,
            "buffer_seconds": seconds,
            "buffer_mb": buf_bytes / 1e6,
        },
    )


def check_capacity(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13b: total acquisition size must fit in free disk space.

    Applies on the RAM-capture path too -- the burst still lands on disk,
    just later.
    """
    rate = setup.data_rate_bytes_s()
    total = total_capacity_bytes(rate, setup.acquisition_duration_s)
    free = setup.free_disk_gb * 1e9
    margin = free / total if total > 0 else MAX_MARGIN

    if margin >= 1.0:
        return _ok(
            "capacity",
            HARD,
            margin,
            f"{total / 1e9:.1f} GB acquisition fits in {free / 1e9:.0f} GB free.",
            total_gb=total / 1e9,
            free_gb=free / 1e9,
        )
    return CheckResult(
        "capacity.insufficient",
        HARD,
        margin,
        "fail",
        f"{total / 1e9:.1f} GB acquisition exceeds {free / 1e9:.0f} GB free disk.",
        action="Free up disk space, shorten the acquisition, or lower the "
        "data rate.",
        numbers={"total_gb": total / 1e9, "free_gb": free / 1e9},
    )


def check_realtime_cpu(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13c: per-frame processing time < 1/f, only when real-time
    processing is actually attached (docs/04 §8's fourth condition).

    The budget is set by the **total** frame arrival rate across streams:
    two cameras at 200 fps each leave 2.5 ms per frame, not 5 ms.
    """
    if not setup.realtime_processing:
        return _ok(
            "realtime_cpu",
            INFO,
            MAX_MARGIN,
            "No real-time processing attached; per-frame CPU budget does not apply.",
        )
    if setup.cpu_per_frame_ms is None:
        return CheckResult(
            "realtime_cpu.unconfirmed",
            INFO,
            MAX_MARGIN,
            "info",
            "Real-time processing is attached but no measured per-frame CPU "
            "time has been supplied.",
            action="Measure per-frame processing time and supply "
            "cpu_per_frame_ms to grade this.",
        )
    frames_per_s = setup.frames_per_s()
    budget_ms = 1000.0 / frames_per_s if frames_per_s > 0 else float("inf")
    margin = budget_ms / setup.cpu_per_frame_ms if setup.cpu_per_frame_ms > 0 else MAX_MARGIN

    if margin >= 1.0:
        return _ok(
            "realtime_cpu",
            HARD,
            margin,
            f"Per-frame budget {budget_ms:.2f} ms at {frames_per_s:g} frames/s; "
            f"processing takes {setup.cpu_per_frame_ms:.2f} ms.",
            budget_ms=budget_ms,
            cpu_per_frame_ms=setup.cpu_per_frame_ms,
        )
    return CheckResult(
        "realtime_cpu.overrun",
        HARD,
        margin,
        "fail",
        f"Per-frame budget {budget_ms:.2f} ms at {frames_per_s:g} frames/s; "
        f"processing takes {setup.cpu_per_frame_ms:.2f} ms -- falls behind "
        "and eventually drops frames.",
        action="Speed up the real-time processing step or lower the frame rate.",
        numbers={"budget_ms": budget_ms, "cpu_per_frame_ms": setup.cpu_per_frame_ms},
    )


def check_ram_capacity(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13d: on the RAM-capture path, the whole burst must fit in RAM.

    kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md: holding
    the acquisition in memory and flushing afterwards removes the real-time
    disk constraint (G12a) and replaces it with a hard capacity ceiling. That
    decision log ends with "decide whether to encode this approach in
    compute.checks as a new check (e.g. G13d RAM capacity)" -- this is it.
    """
    if not setup.ram_capture:
        return _ok(
            "ram_capacity",
            INFO,
            MAX_MARGIN,
            "Streaming to disk during acquisition; the RAM-capture path (G13d) "
            "does not apply.",
        )

    ceiling = LIMITS["ram_capture_budget_mb"]
    budget_mb = setup.ram_capture_budget_mb
    if budget_mb is None:
        budget_mb = ceiling
    total = total_capacity_bytes(
        setup.data_rate_bytes_s(), setup.acquisition_duration_s
    )
    margin = (budget_mb * 1e6) / total if total > 0 else MAX_MARGIN
    flush_s = flush_seconds(total, setup.disk_bandwidth_mb_s)
    numbers = {
        "ram_needed_gb": total / 1e9,
        "ram_budget_gb": budget_mb / 1e3,
        "flush_seconds": flush_s,
    }

    if margin >= 1.0:
        return _ok(
            "ram_capacity",
            HARD,
            margin,
            f"{total / 1e9:.1f} GB burst fits in the {budget_mb / 1e3:.0f} GB "
            f"RAM budget. Flushing it afterwards takes {flush_s / 60:.1f} min "
            f"at the measured {setup.disk_bandwidth_mb_s:.0f} MB/s -- the "
            "microscope is tied up for that long, but nothing is lost if it "
            "is slow.",
            **numbers,
        )
    max_s = (
        (budget_mb * 1e6) / setup.data_rate_bytes_s()
        if setup.data_rate_bytes_s() > 0
        else float("inf")
    )
    return CheckResult(
        "ram_capacity.exceeds_budget",
        HARD,
        margin,
        "fail",
        f"{total / 1e9:.1f} GB burst exceeds the {budget_mb / 1e3:.0f} GB RAM "
        f"budget. At this data rate the budget runs out after {max_s:.0f} s.",
        action=f"Shorten the acquisition to <= {max_s:.0f} s, lower the data "
        "rate, or raise the RAM budget -- but raising it past the "
        f"{ceiling / 1e3:.0f} GB ceiling needs a measurement of what the OS, "
        "MM, and the DMD/piezo/tweezers processes actually hold during an "
        "acquisition, which nobody has taken.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("data_rate", HARD, ("streams", "disk_bandwidth"), check_data_rate),
    Check("fps_provenance", BIAS, ("streams",), check_fps_provenance),
    Check("pixel_container", BIAS, ("streams",), check_pixel_container),
    Check("buffer", HARD, ("streams", "buffer_frames"), check_buffer),
    Check("capacity", HARD, ("streams", "acquisition_duration", "free_disk"), check_capacity),
    Check("realtime_cpu", HARD, ("streams",), check_realtime_cpu),
    Check(
        "ram_capacity",
        HARD,
        ("streams", "acquisition_duration", "disk_bandwidth"),
        check_ram_capacity,
    ),
]


# --------------------------------------------------------------------------
# Feasibility grading -- same table as optics.checks, kept local so this
# lens does not depend on the optical-path lens's module.
# --------------------------------------------------------------------------

GRADES: list[tuple[float, str]] = [
    (3.0, "ROUTINE"),
    (1.5, "COMFORTABLE"),
    (1.0, "TIGHT"),
    (0.5, "HARD"),
    (0.2, "MARGINAL"),
    (0.0, "INFEASIBLE"),
]

GRADE_NOTES = {
    "ROUTINE": "Comfortable headroom. If it fails, the settings are not to blame.",
    "COMFORTABLE": "Normal range.",
    "TIGHT": "No headroom. Sample preparation quality decides the outcome.",
    "HARD": "Operating at the limit. May proceed, but low success rate and poor reproducibility.",
    "MARGINAL": "Data comes out, but interpret with great care.",
    "INFEASIBLE": "Impossible without improvement.",
}


def grade(margin: float) -> str:
    for threshold, name in GRADES:
        if margin >= threshold:
            return name
    return "INFEASIBLE"


#: Grades in ascending order of quality, derived from GRADES so the two cannot
#: drift apart.
GRADE_ORDER: tuple[str, ...] = tuple(name for _, name in reversed(GRADES))


def meets_grade(feasibility: str, minimum: str = "TIGHT") -> bool:
    """Is this feasibility at least ``minimum``?

    docs/05-consensus-gate.md's Verdict schema requires ``feasibility >= TIGHT``
    for a verdict to advance. ``UNKNOWN`` -- and anything unrecognised -- does
    not: an ungraded verdict has not earned the right to move on.
    """
    if feasibility not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(feasibility) >= GRADE_ORDER.index(minimum)
