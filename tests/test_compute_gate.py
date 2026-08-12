"""Tests for compute.gate.evaluate -- mirrors tests/test_trapping_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

from compute.gate import evaluate
from compute.setup import AcquisitionResourceSetup


def _setup(**overrides) -> AcquisitionResourceSetup:
    defaults = dict(
        frame_width_px=1608,
        frame_height_px=1608,
        fps=60.0,
        disk_bandwidth_mb_s=500.0,
        circular_buffer_frames=552,
        acquisition_duration_s=60.0,
        free_disk_gb=500.0,
    )
    defaults.update(overrides)
    return AcquisitionResourceSetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_when_disk_bandwidth_is_not_measured():
    v = evaluate(_setup(disk_bandwidth_mb_s=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.disk_bandwidth" for f in v.findings)


def test_blocked_when_buffer_frame_count_is_unresolved():
    v = evaluate(_setup(circular_buffer_frames=None, ram_budget_mb=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.buffer_frames" for f in v.findings)


def test_blocked_when_capacity_inputs_are_missing():
    v = evaluate(_setup(acquisition_duration_s=None, free_disk_gb=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.capacity_inputs" for f in v.findings)


# ------------------------------------------------------- Phase 1/2, pass ---


def test_passes_with_literal_buffer_frame_count():
    v = evaluate(_setup())
    assert v.status == "PASS"
    assert v.evidence == "measured"
    assert v.advances is True


def test_evidence_downgrades_to_assumed_with_ram_derived_buffer():
    """Deriving a frame count from a RAM budget is not the same as reading
    MM's literal CircularBufferFrameCount."""
    v = evaluate(_setup(circular_buffer_frames=None, ram_budget_mb=2854.57))
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert any("circular buffer" in i for i in v.assumed_inputs)


def test_realtime_cpu_not_applicable_when_no_processing_attached():
    v = evaluate(_setup())  # realtime_processing=False by default
    assert v.margins["realtime_cpu"] == 10.0
    assert not any(f.code.startswith("realtime_cpu") for f in v.findings)


def test_realtime_cpu_is_informational_without_a_measured_cpu_time():
    v = evaluate(_setup(realtime_processing=True))
    unconfirmed = [f for f in v.findings if f.code == "realtime_cpu.unconfirmed"]
    assert len(unconfirmed) == 1
    assert unconfirmed[0].severity == "info"
    assert v.status == "PASS"


# ------------------------------------------------------- Phase 1/2, fail ---


def test_fails_data_rate_when_it_exceeds_the_disk_bandwidth_budget():
    """1608^2 @ 60 fps is 310 MB/s (docs/04 §8); a 100 MB/s disk cannot
    sustain even 70% of that."""
    v = evaluate(_setup(disk_bandwidth_mb_s=100.0))
    assert v.status == "FAIL"
    assert v.bottleneck == "data_rate.exceeds_disk"


def test_fails_buffer_when_it_holds_less_than_five_seconds():
    v = evaluate(_setup(circular_buffer_frames=50))
    assert v.status == "FAIL"
    assert v.bottleneck == "buffer.too_small"


def test_fails_capacity_when_acquisition_exceeds_free_disk():
    v = evaluate(_setup(acquisition_duration_s=3600.0, free_disk_gb=500.0))
    assert v.status == "FAIL"
    assert v.bottleneck == "capacity.insufficient"


def test_fails_realtime_cpu_when_processing_cannot_keep_up():
    v = evaluate(_setup(realtime_processing=True, cpu_per_frame_ms=50.0))
    assert v.status == "FAIL"
    assert v.bottleneck == "realtime_cpu.overrun"
