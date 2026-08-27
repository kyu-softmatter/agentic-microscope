"""Tests for hardware.orchestrator -- no devices, no sockets, no DLL.

The coordinator is deliberately device-free, so everything it does is testable
here: the shared clock, the latency statistics, the camera handoff, and the
setup ordering. Concurrency is exercised with real threads rather than mocked,
since the point of the module is that three drivers run at once.
"""

from __future__ import annotations

import threading
import time

import pytest

from hardware.orchestrator import (
    MICROMANAGER,
    TWEEZERS,
    CameraArbiter,
    Clock,
    LatencyLog,
    Op,
    OrchestratorError,
    Phase,
    Session,
    SharedState,
)


# ---- clock -------------------------------------------------------------


def test_clock_starts_near_zero_and_advances():
    clock = Clock()
    first = clock.now_s()
    time.sleep(0.01)
    assert 0 <= first < 0.05
    assert clock.now_s() > first


def test_clock_keeps_a_wall_anchor_for_correlating_with_mm_metadata():
    """Host stamps have to be mappable onto MM's own ElapsedTime-ms series."""
    clock = Clock()
    wall0, _ = clock.anchor
    assert abs(clock.wall_of(clock.now_s()) - wall0) < 1.0


def test_one_clock_is_shared_so_subsystems_are_comparable():
    session = Session()
    assert session.latency.clock is session.clock
    assert session.state.clock is session.clock


# ---- latency log -------------------------------------------------------


def test_timed_records_a_successful_operation():
    log = LatencyLog(Clock())
    with log.timed("tweezers", "TRAP_POSITION"):
        time.sleep(0.005)
    (op,) = log.ops
    assert op.subsystem == "tweezers" and op.ok
    assert op.duration_ms >= 5.0


def test_timed_keeps_the_latency_of_a_failed_call_and_reraises():
    """A command that errors after a long wait is exactly what ruins a
    host-timed drive -- dropping it would hide the problem."""
    log = LatencyLog(Clock())
    with pytest.raises(ValueError):
        with log.timed("tweezers", "LOAD_PATTERN"):
            raise ValueError("boom")
    (op,) = log.ops
    assert not op.ok
    assert "ValueError: boom" in op.detail
    assert op.duration_s >= 0


def test_stats_group_by_subsystem_and_operation():
    log = LatencyLog(Clock())
    for _ in range(3):
        with log.timed("piezo", "position.get"):
            pass
    with log.timed("micromanager", "setProperty"):
        pass
    stats = log.stats()
    assert stats[("piezo", "position.get")]["count"] == 3
    assert stats[("micromanager", "setProperty")]["count"] == 1


def test_stats_report_failures_separately():
    log = LatencyLog(Clock())
    with log.timed("tweezers", "probe"):
        pass
    with pytest.raises(RuntimeError):
        with log.timed("tweezers", "probe"):
            raise RuntimeError
    s = log.stats()[("tweezers", "probe")]
    assert s["count"] == 2 and s["failures"] == 1


def test_percentiles_are_real_order_statistics():
    """A latency budget wants a number the instrument actually produced, so no
    interpolation between samples."""
    log = LatencyLog(Clock())
    for ms in (1.0, 2.0, 3.0, 4.0, 100.0):
        log.record(Op("x", "y", 0.0, ms / 1e3, True))
    s = log.stats()[("x", "y")]
    assert s["min_ms"] == pytest.approx(1.0)
    assert s["median_ms"] == pytest.approx(3.0)
    assert s["max_ms"] == pytest.approx(100.0)
    assert s["p95_ms"] in (pytest.approx(4.0), pytest.approx(100.0))


def test_report_is_a_table_with_a_row_per_operation():
    log = LatencyLog(Clock())
    with log.timed("tweezers", "TRAP_POSITION"):
        pass
    lines = log.report().splitlines()
    assert lines[0].startswith("subsystem")
    assert any("TRAP_POSITION" in line for line in lines[1:])


def test_report_says_so_when_nothing_was_measured():
    assert LatencyLog(Clock()).report() == "no operations recorded"


def test_log_is_safe_under_concurrent_writers():
    log = LatencyLog(Clock())

    def worker(name: str) -> None:
        for _ in range(50):
            with log.timed(name, "op"):
                pass

    threads = [threading.Thread(target=worker, args=(f"s{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(log.ops) == 200


# ---- camera arbiter ----------------------------------------------------


def test_second_owner_is_refused_while_the_first_holds_it():
    arbiter = CameraArbiter("Kinetix_red")
    arbiter.acquire(TWEEZERS)
    with pytest.raises(OrchestratorError, match="held by 'tweezers'"):
        arbiter.acquire(MICROMANAGER)


def test_reacquiring_by_the_same_owner_is_allowed():
    arbiter = CameraArbiter("Kinetix_red")
    arbiter.acquire(TWEEZERS)
    arbiter.acquire(TWEEZERS)
    assert arbiter.owner == TWEEZERS


def test_release_then_the_other_owner_may_take_it():
    arbiter = CameraArbiter("Kinetix_red")
    arbiter.acquire(TWEEZERS)
    arbiter.release(TWEEZERS)
    arbiter.acquire(MICROMANAGER)
    assert arbiter.owner == MICROMANAGER


def test_a_non_owner_cannot_release():
    arbiter = CameraArbiter("Kinetix_red")
    arbiter.acquire(TWEEZERS)
    with pytest.raises(OrchestratorError, match="cannot release"):
        arbiter.release(MICROMANAGER)


def test_require_free_names_the_current_holder():
    arbiter = CameraArbiter("Kinetix_blue")
    arbiter.acquire(TWEEZERS)
    with pytest.raises(OrchestratorError, match="still held by 'tweezers'"):
        arbiter.require_free(MICROMANAGER)


def test_held_by_releases_even_when_the_body_raises():
    arbiter = CameraArbiter("Kinetix_red")
    with pytest.raises(ZeroDivisionError):
        with arbiter.held_by(TWEEZERS):
            1 / 0
    assert arbiter.owner is None


# ---- shared state ------------------------------------------------------


def test_shared_state_round_trips_a_value():
    state = SharedState(Clock())
    state.set("objective", "4-Apo LmbdS 40x WI")
    assert state.get("objective") == "4-Apo LmbdS 40x WI"


def test_shared_state_reports_how_stale_a_value_is():
    """Commanded values, not read-back ones -- on the tweezers side commanded is
    all there is, so a reader needs the age."""
    state = SharedState(Clock())
    state.set("trap_xy_um", (0.0, 0.0))
    time.sleep(0.02)
    assert state.age_s("trap_xy_um") >= 0.02
    assert state.age_s("never_written") is None


def test_shared_state_default_for_a_missing_key():
    assert SharedState(Clock()).get("nope", "fallback") == "fallback"


def test_shared_state_is_safe_under_concurrent_writers():
    state = SharedState(Clock())

    def worker(i: int) -> None:
        for n in range(100):
            state.set(f"k{i}", n)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(state.get(f"k{i}") == 99 for i in range(4))


# ---- the ordered handoff ----------------------------------------------


def test_the_happy_path_walks_the_phases_in_order():
    session = Session()
    assert session.phase is Phase.IDLE
    with session.tweezers_setup():
        assert session.phase is Phase.TWEEZERS_SETUP
        assert session.camera.owner == TWEEZERS
    assert session.phase is Phase.CAMERA_RELEASED
    assert session.camera.owner is None
    session.microscope_setup()
    assert session.camera.owner == MICROMANAGER
    session.start_running()
    assert session.phase is Phase.RUNNING


def test_micromanager_cannot_set_up_before_the_camera_is_released():
    """The rule this whole module exists to enforce."""
    session = Session()
    with pytest.raises(OrchestratorError, match="needs phase CAMERA_RELEASED"):
        session.microscope_setup()


def test_micromanager_cannot_set_up_while_the_tweezers_still_hold_the_camera():
    session = Session()
    session.advance_to(Phase.CAMERA_RELEASED)
    session.camera.acquire(TWEEZERS)
    with pytest.raises(OrchestratorError, match="still held by 'tweezers'"):
        session.microscope_setup()


def test_running_requires_the_microscope_to_be_set_up():
    session = Session()
    with session.tweezers_setup():
        pass
    with pytest.raises(OrchestratorError, match="needs phase MICROSCOPE_SETUP"):
        session.start_running()


def test_phases_only_move_forward():
    session = Session()
    session.advance_to(Phase.MICROSCOPE_SETUP)
    with pytest.raises(OrchestratorError, match="cannot go back"):
        session.advance_to(Phase.TWEEZERS_SETUP)


def test_tweezers_setup_releases_the_camera_even_when_it_raises():
    session = Session()
    with pytest.raises(RuntimeError):
        with session.tweezers_setup():
            raise RuntimeError("calibration abandoned")
    assert session.camera.owner is None
    assert session.phase is Phase.CAMERA_RELEASED


def test_instrument_feeds_the_shared_latency_log():
    session = Session()
    with session.instrument("tweezers", "LOAD_PROJECT"):
        pass
    assert ("tweezers", "LOAD_PROJECT") in session.latency.stats()


def test_three_subsystems_logging_concurrently_land_on_one_timeline():
    """The actual goal: parallel operation, one comparable set of stamps."""
    session = Session()

    def worker(subsystem: str) -> None:
        for _ in range(20):
            with session.instrument(subsystem, "op"):
                time.sleep(0.001)

    threads = [
        threading.Thread(target=worker, args=(s,))
        for s in ("tweezers", "micromanager", "piezo")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = session.latency.stats()
    assert {s for s, _ in stats} == {"tweezers", "micromanager", "piezo"}
    starts = [op.t_start_s for op in session.latency.ops]
    assert min(starts) >= 0 and max(starts) <= session.clock.now_s()
