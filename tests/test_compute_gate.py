"""Tests for compute.gate.evaluate -- mirrors tests/test_trapping_gate.py's
split: Phase 0 refusals are right, Phase 1/2 aggregation is right.
"""

from __future__ import annotations

from compute.gate import evaluate
from compute.setup import AcquisitionResourceSetup, Stream


def _setup(**overrides) -> AcquisitionResourceSetup:
    """A fully evidenced single-camera acquisition.

    Everything an ``advances: YES`` needs is switched on here so that each
    test can switch exactly one thing off and see it in the verdict --
    including the two that default to unverified in real use, the disk
    bandwidth's measurement path and the frame rate's provenance.
    """
    defaults = dict(
        frame_width_px=1608,
        frame_height_px=1608,
        fps=60.0,
        fps_source="measured",
        disk_bandwidth_mb_s=500.0,
        disk_bandwidth_path_confirmed=True,
        circular_buffer_frames=552,
        acquisition_duration_s=60.0,
        free_disk_gb=500.0,
    )
    defaults.update(overrides)
    return AcquisitionResourceSetup.single(**defaults)


def _dual(**overrides) -> AcquisitionResourceSetup:
    """Both Kinetix cameras at 2400x2400, the case from
    kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md."""
    defaults = dict(
        disk_bandwidth_mb_s=206.8,
        disk_bandwidth_path_confirmed=True,
        circular_buffer_frames=2500,
        acquisition_duration_s=60.0,
        free_disk_gb=2559.0,
    )
    defaults.update(overrides)
    return AcquisitionResourceSetup(
        streams=[
            Stream("red", 2400, 2400, 200.0, fps_source="measured"),
            Stream("blue", 2400, 2400, 200.0, fps_source="measured"),
        ],
        **defaults,
    )


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_when_no_stream_is_supplied():
    v = evaluate(AcquisitionResourceSetup(disk_bandwidth_mb_s=500.0))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.streams" for f in v.findings)


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
    assert v.advances is False
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


# ------------------------------------------------------ G12b provenance ---


def test_requested_frame_rate_downgrades_evidence():
    """docs/06 §C4: requested and delivered differed by 3x, and the camera
    was not the bottleneck -- so a requested rate cannot carry a verdict."""
    v = evaluate(_setup(fps_source="requested"))
    assert v.status == "PASS_WITH_CHANGES"
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any(f.code == "fps_provenance.requested" for f in v.findings)


def test_requested_rate_within_lens_2_ceiling_still_warns():
    v = evaluate(_setup(fps_source="requested", detector_max_fps=88.0))
    warns = [f for f in v.findings if f.code == "fps_provenance.unmeasured"]
    assert len(warns) == 1
    assert v.advances is False


def test_unrealizable_frame_rate_is_a_bias_finding_not_a_hard_fail():
    """Frame-rate realizability is lens 2's G9. This lens reports that its
    own numbers rest on a rate the camera cannot deliver, and lets the
    feasibility grade collapse -- it does not seize a verdict it does not
    own."""
    v = evaluate(_setup(fps_source="requested", detector_max_fps=30.0))
    finding = next(f for f in v.findings if f.code == "fps_provenance.unrealizable")
    assert finding.kind == "bias"
    assert finding.severity == "fail"
    assert v.status == "PASS_WITH_CHANGES"
    assert v.bottleneck == "fps_provenance.unrealizable"
    assert v.feasibility == "HARD"
    assert v.advances is False


# --------------------------------------------------- G12c pixel container ---


def test_eight_bit_mode_halves_the_data_rate_but_is_not_measured():
    """Kinetix Speed mode. The halving is real if MM writes one byte; that
    it does has never been checked on this adapter."""
    v = evaluate(_setup(bit_depth=8))
    #: keyed by the *result* code, not the check name -- every lens in this
    #: repo does that, so a failing check moves its own key.
    numbers = v.metrics["pixel_container.unconfirmed"]
    assert numbers["data_rate_mb_s"] * 2 == numbers["data_rate_if_upconverted_mb_s"]
    assert any(f.code == "pixel_container.unconfirmed" for f in v.findings)
    assert v.evidence == "assumed"
    assert v.advances is False


def test_confirming_the_container_clears_the_finding():
    v = evaluate(_setup(bit_depth=8, container_confirmed=True))
    assert not any(f.code.startswith("pixel_container") for f in v.findings)
    assert v.evidence == "measured"
    assert v.advances is True


# ------------------------------------------------------ disk bandwidth path ---


def test_unconfirmed_bandwidth_path_downgrades_evidence():
    """kb/calibrations/disk-bandwidth.yaml measured D:\\...\\_bench and says
    in its own note it is not confirmed to be MM's save directory."""
    v = evaluate(_setup(disk_bandwidth_path_confirmed=False))
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any("save directory" in i for i in v.assumed_inputs)


# ------------------------------------------------------------ multi-stream ---


def test_two_cameras_are_billed_together():
    """1608^2 @ 60 fps twice is 621 MB/s -- over a 500 MB/s disk's budget
    even though one camera alone would fit."""
    one = evaluate(_setup())
    two = evaluate(
        AcquisitionResourceSetup(
            streams=[
                Stream("red", 1608, 1608, 60.0, fps_source="measured"),
                Stream("blue", 1608, 1608, 60.0, fps_source="measured"),
            ],
            disk_bandwidth_mb_s=500.0,
            disk_bandwidth_path_confirmed=True,
            circular_buffer_frames=1000,
            acquisition_duration_s=60.0,
            free_disk_gb=500.0,
        )
    )
    assert one.status == "PASS"
    assert two.status == "FAIL"
    assert two.bottleneck == "data_rate.exceeds_disk"


def test_realtime_cpu_budget_is_set_by_the_total_frame_rate():
    """Two cameras at 200 fps each leave 2.5 ms per frame, not 5 ms."""
    v = evaluate(_dual(realtime_processing=True, cpu_per_frame_ms=3.0))
    assert v.metrics["realtime_cpu.overrun"]["budget_ms"] == 2.5
    assert v.margins["realtime_cpu.overrun"] < 1.0


# --------------------------------------------------------- G13d RAM capture ---


def test_ram_capture_lifts_the_real_time_disk_gate():
    v = evaluate(_dual(ram_capture=True, acquisition_duration_s=5.0))
    data_rate = [f for f in v.findings if f.code.startswith("data_rate")]
    assert not data_rate  # informational, so it never reaches findings
    assert v.margins["data_rate"] == 10.0


def test_ram_capture_gates_on_the_authorized_ceiling():
    """4608 MB/s for 60 s is 276 GB, far past the 32 GB ceiling authorized
    while the OS/MM/DMD RAM usage stays unmeasured."""
    v = evaluate(_dual(ram_capture=True))
    assert v.status == "FAIL"
    assert v.bottleneck == "ram_capacity.exceeds_budget"
    assert v.metrics["ram_capacity.exceeds_budget"]["ram_needed_gb"] > 250


def test_a_short_enough_burst_fits_the_ram_budget():
    v = evaluate(_dual(ram_capture=True, acquisition_duration_s=5.0))
    assert v.margins["ram_capacity"] > 1.0
    assert v.metrics["ram_capacity"]["ram_needed_gb"] < 32
    assert v.metrics["ram_capacity"]["flush_seconds"] > 0


def test_ram_capacity_is_not_applicable_when_streaming_to_disk():
    v = evaluate(_setup())
    assert v.margins["ram_capacity"] == 10.0
    assert not any(f.code.startswith("ram_capacity") for f in v.findings)


def test_raising_the_ram_budget_past_the_ceiling_is_an_assumption():
    v = evaluate(
        _dual(ram_capture=True, acquisition_duration_s=5.0, ram_capture_budget_mb=200_000.0)
    )
    assert v.evidence == "assumed"
    assert v.advances is False
    assert any("authorized ceiling" in i for i in v.assumed_inputs)
