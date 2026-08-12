"""Individual compute-resource checks -- G12 (data rate), G13 (buffer /
capacity / real-time CPU). docs/04-decision-engine.md §8;
docs/05-consensus-gate.md §5.

Mirrors optics.checks / trapping.checks: independent margins
(achieved / required), never booleans -- see optics/checks.py's module
docstring.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .resources import buffer_bytes, buffer_seconds, data_rate_bytes_s, total_capacity_bytes

if TYPE_CHECKING:
    from .setup import AcquisitionResourceSetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    #: G12: never plan to sustain more than 70% of measured disk bandwidth.
    "disk_bandwidth_fraction": 0.7,
    #: G13: buffer must absorb at least this many seconds of transient
    #: disk latency before frames start dropping.
    "buffer_seconds_min": 5.0,
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


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "AcquisitionResourceSetup") -> set[str]:
    facts: set[str] = set()
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
    """G12: R < 0.7 * measured disk bandwidth. Exceeding it is a silent
    frame drop, not an error (docs/06-pitfalls.md §C5)."""
    rate = data_rate_bytes_s(setup.frame_width_px, setup.frame_height_px, setup.fps)
    budget = LIMITS["disk_bandwidth_fraction"] * setup.disk_bandwidth_mb_s * 1e6
    margin = budget / rate if rate > 0 else MAX_MARGIN

    if margin >= 1.0:
        return _ok(
            "data_rate",
            HARD,
            margin,
            f"Data rate {rate / 1e6:.0f} MB/s is within "
            f"{LIMITS['disk_bandwidth_fraction'] * 100:.0f}% of measured disk "
            f"bandwidth ({budget / 1e6:.0f} MB/s budget).",
            data_rate_mb_s=rate / 1e6,
            disk_budget_mb_s=budget / 1e6,
        )
    return CheckResult(
        "data_rate.exceeds_disk",
        HARD,
        margin,
        "fail",
        f"Data rate {rate / 1e6:.0f} MB/s exceeds the "
        f"{LIMITS['disk_bandwidth_fraction'] * 100:.0f}% disk-bandwidth budget "
        f"({budget / 1e6:.0f} MB/s). Frames will drop silently, not error "
        "(docs/06-pitfalls.md §C5).",
        action="Reduce ROI, frame rate, or write to faster storage.",
        numbers={"data_rate_mb_s": rate / 1e6, "disk_budget_mb_s": budget / 1e6},
    )


def check_buffer(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13a: circular buffer must absorb >= 5 s of data at the achieved rate."""
    frames = setup.resolved_buffer_frames()
    buf_bytes = buffer_bytes(frames, setup.frame_width_px, setup.frame_height_px)
    rate = data_rate_bytes_s(setup.frame_width_px, setup.frame_height_px, setup.fps)
    seconds = buffer_seconds(buf_bytes, rate)
    margin = seconds / LIMITS["buffer_seconds_min"]

    if margin >= 1.0:
        return _ok(
            "buffer",
            HARD,
            margin,
            f"{frames} frames ({buf_bytes / 1e6:.0f} MB) buffers "
            f"{seconds:.1f} s of data at {rate / 1e6:.0f} MB/s.",
            buffer_frames=frames,
            buffer_seconds=seconds,
        )
    return CheckResult(
        "buffer.too_small",
        HARD,
        margin,
        "fail",
        f"{frames} frames ({buf_bytes / 1e6:.0f} MB) only buffers "
        f"{seconds:.1f} s of data at {rate / 1e6:.0f} MB/s (need "
        f"{LIMITS['buffer_seconds_min']:.0f} s to absorb transient disk "
        "latency) -- a stall drops frames silently.",
        action="Increase CircularBufferFrameCount / available RAM, or lower "
        "the data rate (smaller ROI, lower fps, or fewer bits/pixel).",
        numbers={"buffer_frames": frames, "buffer_seconds": seconds},
    )


def check_capacity(setup: "AcquisitionResourceSetup") -> CheckResult:
    """G13b: total acquisition size must fit in free disk space."""
    rate = data_rate_bytes_s(setup.frame_width_px, setup.frame_height_px, setup.fps)
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
    processing is actually attached (docs/04 §8's fourth condition)."""
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
    budget_ms = 1000.0 / setup.fps if setup.fps > 0 else float("inf")
    margin = budget_ms / setup.cpu_per_frame_ms if setup.cpu_per_frame_ms > 0 else MAX_MARGIN

    if margin >= 1.0:
        return _ok(
            "realtime_cpu",
            HARD,
            margin,
            f"Per-frame budget {budget_ms:.2f} ms at {setup.fps:.0f} fps; "
            f"processing takes {setup.cpu_per_frame_ms:.2f} ms.",
            budget_ms=budget_ms,
            cpu_per_frame_ms=setup.cpu_per_frame_ms,
        )
    return CheckResult(
        "realtime_cpu.overrun",
        HARD,
        margin,
        "fail",
        f"Per-frame budget {budget_ms:.2f} ms at {setup.fps:.0f} fps; "
        f"processing takes {setup.cpu_per_frame_ms:.2f} ms -- falls behind "
        "and eventually drops frames.",
        action="Speed up the real-time processing step or lower the frame rate.",
        numbers={"budget_ms": budget_ms, "cpu_per_frame_ms": setup.cpu_per_frame_ms},
    )


CHECKS: list[Check] = [
    Check("data_rate", HARD, ("disk_bandwidth",), check_data_rate),
    Check("buffer", HARD, ("buffer_frames",), check_buffer),
    Check("capacity", HARD, ("acquisition_duration", "free_disk"), check_capacity),
    Check("realtime_cpu", HARD, (), check_realtime_cpu),
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
    "ROUTINE": "여유 있음. 실패하면 설정 탓이 아니다.",
    "COMFORTABLE": "정상 범위.",
    "TIGHT": "여유 없음. 시료 준비 품질이 결과를 좌우한다.",
    "HARD": "한계에서 동작. 진행 가능하나 성공률과 재현성이 낮다.",
    "MARGINAL": "데이터는 나오지만 해석에 큰 주의가 필요하다.",
    "INFEASIBLE": "개선 없이는 불가능하다.",
}


def grade(margin: float) -> str:
    for threshold, name in GRADES:
        if margin >= threshold:
            return name
    return "INFEASIBLE"
