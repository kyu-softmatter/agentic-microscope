"""Tests for hardware.orchestrator -- no devices, no sockets, no DLL.

The coordinator is deliberately device-free, so everything it does is testable
here: the shared clock, the latency statistics, the camera handoff, and the
setup ordering. Concurrency is exercised with real threads rather than mocked,
since the point of the module is that three drivers run at once.
"""

from __future__ import annotations

import csv
import threading
import time

import pytest

from hardware.orchestrator import (
    HARDWARE,
    HOST_SCHED,
    LOST_WITHOUT,
    MICROMANAGER,
    MICROSCOPE,
    PIEZO,
    SESSION,
    TWEEZERS,
    CameraArbiter,
    Clock,
    HardwareAnchor,
    LatencyLog,
    Op,
    OrchestratorError,
    Phase,
    Roster,
    Session,
    SharedState,
    Timeline,
    start_spread_s,
    track_report,
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
    session = Session(TWEEZERS)
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
    """The rule this whole module exists to enforce -- when the tweezers are on."""
    session = Session(TWEEZERS)
    with pytest.raises(OrchestratorError, match="needs phase CAMERA_RELEASED"):
        session.microscope_setup()


def test_micromanager_cannot_set_up_while_the_tweezers_still_hold_the_camera():
    session = Session(TWEEZERS)
    session.advance_to(Phase.CAMERA_RELEASED)
    session.camera.acquire(TWEEZERS)
    with pytest.raises(OrchestratorError, match="still held by 'tweezers'"):
        session.microscope_setup()


def test_running_requires_the_microscope_to_be_set_up():
    session = Session(TWEEZERS)
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
    session = Session(TWEEZERS)
    with pytest.raises(RuntimeError):
        with session.tweezers_setup():
            raise RuntimeError("calibration abandoned")
    assert session.camera.owner is None
    assert session.phase is Phase.CAMERA_RELEASED


def test_instrument_feeds_the_shared_latency_log():
    session = Session(TWEEZERS)
    with session.instrument(TWEEZERS, "LOAD_PROJECT"):
        pass
    assert (TWEEZERS, "LOAD_PROJECT") in session.latency.stats()


def test_three_subsystems_logging_concurrently_land_on_one_timeline():
    """The actual goal: parallel operation, one comparable set of stamps."""
    session = Session(TWEEZERS, PIEZO)

    def worker(subsystem: str) -> None:
        for _ in range(20):
            with session.instrument(subsystem, "op"):
                time.sleep(0.001)

    threads = [
        threading.Thread(target=worker, args=(s,))
        for s in (TWEEZERS, MICROSCOPE, PIEZO)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = session.latency.stats()
    assert {s for s, _ in stats} == {TWEEZERS, MICROSCOPE, PIEZO}
    starts = [op.t_start_s for op in session.latency.ops]
    assert min(starts) >= 0 and max(starts) <= session.clock.now_s()


# ---- roster: what is switched on ---------------------------------------


def test_the_microscope_is_on_the_roster_whether_or_not_it_is_named():
    """It is always on, and everything else is timed against its frames."""
    assert MICROSCOPE in Roster()
    assert MICROSCOPE in Roster(PIEZO)


def test_a_roster_lists_what_is_present_in_a_stable_order():
    assert list(Roster(PIEZO, TWEEZERS)) == [MICROSCOPE, TWEEZERS, PIEZO]
    assert list(Roster()) == [MICROSCOPE]


def test_an_unknown_subsystem_is_refused_rather_than_silently_ignored():
    with pytest.raises(OrchestratorError, match="unknown subsystem"):
        Roster("piezzo")


def test_absent_names_what_is_switched_off():
    assert Roster(TWEEZERS).absent == (PIEZO,)
    assert Roster().absent == (TWEEZERS, PIEZO)
    assert Roster(TWEEZERS, PIEZO).absent == ()


def test_the_report_says_what_an_absent_subsystem_costs_the_record():
    """An absent instrument must not read afterwards like a null result."""
    missing = Roster().missing_from_record()
    assert any("x_trap" in line for line in missing)
    assert any(line.startswith(f"{PIEZO}:") for line in missing)
    assert Roster(TWEEZERS, PIEZO).missing_from_record() == ()
    assert set(LOST_WITHOUT) == {TWEEZERS, PIEZO}


def test_a_session_exposes_its_roster():
    session = Session(PIEZO)
    assert session.has(PIEZO) and session.has(MICROSCOPE)
    assert not session.has(TWEEZERS)
    assert session.absent == (TWEEZERS,)


# ---- the handoff only happens when there is a handoff to make ----------


def test_the_microscope_comes_up_immediately_when_the_tweezers_are_off():
    """The rule: with nothing holding the Kinetix there is no release to wait
    for, so IDLE -> MICROSCOPE_SETUP directly."""
    session = Session()
    assert session.phase is Phase.IDLE
    session.microscope_setup()
    assert session.phase is Phase.MICROSCOPE_SETUP
    assert session.camera.owner == MICROMANAGER
    session.start_running()
    assert session.phase is Phase.RUNNING


def test_a_piezo_only_session_never_enters_either_camera_phase():
    session = Session(PIEZO)
    session.microscope_setup()
    session.start_running()
    assert session.phase is Phase.RUNNING


def test_the_release_is_still_enforced_when_the_tweezers_are_on():
    """The other half of the rule -- the handoff is not weakened, only made
    conditional on there being a second program to hand the camera to."""
    session = Session(TWEEZERS)
    with pytest.raises(OrchestratorError, match="needs phase CAMERA_RELEASED"):
        session.microscope_setup()


def test_tweezers_setup_is_refused_when_they_are_switched_off():
    """Taking the camera for a program that is not running would block the
    microscope for the rest of the session."""
    session = Session(PIEZO)
    with pytest.raises(OrchestratorError, match="not on this session's roster"):
        with session.tweezers_setup():
            pass


def test_driving_a_switched_off_subsystem_raises_at_the_call_site():
    session = Session(TWEEZERS)
    with pytest.raises(OrchestratorError, match="not on this session's roster"):
        with session.instrument(PIEZO, "position.measured.get"):
            pass


def test_the_refusal_says_how_to_fix_it():
    session = Session()
    with pytest.raises(OrchestratorError, match=r"Session\(PIEZO, \.\.\.\)"):
        session.require_present(PIEZO)


# ---- tracks: parallel, one barrier -------------------------------------


def test_a_track_for_a_switched_off_subsystem_is_dropped_not_run():
    """The program keeps its shape when a device is off."""
    session = Session()
    ran: list[str] = []
    assert session.add_track(MICROSCOPE, lambda s, stop: ran.append(MICROSCOPE))
    assert session.add_track(TWEEZERS, lambda s, stop: ran.append(TWEEZERS)) is False
    results = session.run_tracks(join_timeout_s=10.0)
    assert ran == [MICROSCOPE]
    assert set(results) == {MICROSCOPE}
    marks = session.timeline.marks
    skipped = [m.subsystem for m in marks if m.event == "track skipped"]
    assert skipped == [TWEEZERS]


def test_one_track_per_subsystem_keeps_the_dll_handle_on_one_thread():
    session = Session(PIEZO)
    session.add_track(PIEZO, lambda s, stop: None, name="waveform")
    with pytest.raises(OrchestratorError, match="already has a track"):
        session.add_track(PIEZO, lambda s, stop: None, name="readback")


def test_tracks_genuinely_overlap_rather_than_taking_turns():
    """Each track waits for the other, so this deadlocks if they are
    serialised. Passing is the proof of overlap."""
    session = Session(PIEZO)
    arrived = {MICROSCOPE: threading.Event(), PIEZO: threading.Event()}

    def body(mine: str, theirs: str):
        def run(sess, stop):
            arrived[mine].set()
            assert arrived[theirs].wait(timeout=5.0), f"{theirs} never arrived"
            return "overlapped"

        return run

    session.add_track(MICROSCOPE, body(MICROSCOPE, PIEZO))
    session.add_track(PIEZO, body(PIEZO, MICROSCOPE))
    results = session.run_tracks(join_timeout_s=10.0)
    assert all(r.ok for r in results.values())
    assert {r.value for r in results.values()} == {"overlapped"}


def test_the_barrier_starts_every_track_together():
    session = Session(TWEEZERS, PIEZO)
    for subsystem in (MICROSCOPE, TWEEZERS, PIEZO):
        session.add_track(subsystem, lambda s, stop: time.sleep(0.01))
    results = session.run_tracks(join_timeout_s=10.0)
    assert len(results) == 3
    # Generous: the point is that it is OS scheduling, not the sum of three
    # driver connect times.
    assert start_spread_s(results) < 0.5


def test_a_failing_track_sets_stop_and_the_others_see_it():
    """Three instruments live: the other two still need winding down."""
    session = Session(PIEZO)

    def doomed(sess, stop):
        raise RuntimeError("piezo link dropped")

    def watcher(sess, stop):
        return "stopped early" if stop.wait(timeout=5.0) else "ran to completion"

    session.add_track(PIEZO, doomed)
    session.add_track(MICROSCOPE, watcher)
    results = session.run_tracks(join_timeout_s=10.0)

    assert isinstance(results[PIEZO].error, RuntimeError)
    assert not results[PIEZO].ok
    assert results[MICROSCOPE].value == "stopped early"
    assert session.stop.is_set()


def test_a_track_failure_does_not_escape_run_tracks():
    session = Session()
    session.add_track(MICROSCOPE, lambda s, stop: 1 / 0)
    results = session.run_tracks(join_timeout_s=10.0)
    assert isinstance(results[MICROSCOPE].error, ZeroDivisionError)


def test_a_track_records_when_it_ran_on_the_shared_clock():
    session = Session()
    session.add_track(MICROSCOPE, lambda s, stop: time.sleep(0.02))
    r = session.run_tracks(join_timeout_s=10.0)[MICROSCOPE]
    assert r.started and r.ok
    assert r.duration_s >= 0.02
    assert 0 <= r.t_start_s < r.t_end_s <= session.clock.now_s()


def test_run_tracks_with_nothing_registered_is_not_an_error():
    session = Session()
    assert session.run_tracks() == {}
    assert any(m.event == "no tracks to run" for m in session.timeline.marks)


def test_a_track_still_running_past_the_join_timeout_raises():
    """A stuck driver thread with a class-4 laser armed is not something to
    return a partial result about."""
    session = Session()
    release = threading.Event()
    session.add_track(MICROSCOPE, lambda s, stop: release.wait(timeout=10.0))
    try:
        with pytest.raises(OrchestratorError, match="still running after"):
            session.run_tracks(join_timeout_s=0.05)
        assert session.stop.is_set()
    finally:
        release.set()


def test_track_report_names_the_outcome_of_each_track():
    session = Session(PIEZO)

    def doomed(sess, stop):
        raise RuntimeError("boom")

    session.add_track(MICROSCOPE, lambda s, stop: "frames")
    session.add_track(PIEZO, doomed)
    text = track_report(session.run_tracks(join_timeout_s=10.0))
    assert "FAILED -- RuntimeError: boom" in text
    assert "frames" in text
    assert "started within" in text


def test_start_spread_is_zero_when_there_is_nothing_to_compare():
    assert start_spread_s({}) == 0.0


# ---- one timeline, and the hardware clocks on it ------------------------


def test_a_mark_lands_on_the_shared_clock():
    session = Session(PIEZO)
    m = session.timeline.mark(PIEZO, "waveform uploaded", "100 samples")
    assert m.subsystem == PIEZO and m.detail == "100 samples"
    assert 0 <= m.t_s <= session.clock.now_s()


def test_the_roster_is_the_first_thing_on_the_timeline():
    session = Session(TWEEZERS)
    first = session.timeline.marks[0]
    assert first.subsystem == SESSION and first.event == "roster"
    assert TWEEZERS in first.detail and PIEZO in first.detail


def test_anchor_brackets_the_start_command_and_reports_the_uncertainty():
    session = Session(PIEZO)
    with session.timeline.anchor(PIEZO, "sine 1 Hz", clock=HOST_SCHED, rate_hz=100.0):
        time.sleep(0.02)  # stands in for the start command's round trip
    a = session.timeline.anchor_of(PIEZO)
    assert a.label == "sine 1 Hz" and a.rate_hz == 100.0
    assert a.t_before_s <= a.host_t0_s <= a.t_after_s
    assert a.uncertainty_s >= 0.009  # half of the 20 ms bracket


def test_sample_times_come_from_the_hardware_rate_not_from_host_stamps():
    """100 samples at 100 Hz is exactly 1.000 s later, however slow the host
    was -- which is why the hardware is asked for its own clock."""
    session = Session(PIEZO)
    with session.timeline.anchor(PIEZO, "sine", clock=HOST_SCHED, rate_hz=100.0):
        pass
    t0 = session.timeline.anchor_of(PIEZO).host_t0_s
    assert session.timeline.host_of_sample(PIEZO, 100) == pytest.approx(t0 + 1.0)
    assert session.timeline.host_of(PIEZO, 0.25) == pytest.approx(t0 + 0.25)


def test_a_sample_time_without_a_recorded_rate_is_refused():
    session = Session(PIEZO)
    with session.timeline.anchor(PIEZO, "step", clock=HOST_SCHED):
        pass
    with pytest.raises(OrchestratorError, match="no rate recorded"):
        session.timeline.host_of_sample(PIEZO, 10)


def test_alignment_error_is_the_sum_of_the_two_uncertainties():
    """The number that decides whether "the stage was at the peak on frame
    412" is a claim you may make."""
    session = Session(TWEEZERS, PIEZO)
    with session.timeline.anchor(PIEZO, "waveform", clock=HARDWARE):
        time.sleep(0.005)
    with session.timeline.anchor(TWEEZERS, "pattern assigned", clock=HARDWARE):
        time.sleep(0.005)
    timeline = session.timeline
    expected = (
        timeline.anchor_of(PIEZO).uncertainty_s
        + timeline.anchor_of(TWEEZERS).uncertainty_s
    )
    assert timeline.alignment_error_s(PIEZO, TWEEZERS) == pytest.approx(expected)
    assert timeline.alignment_error_s(PIEZO, TWEEZERS) > 0.004


def test_a_subsystem_that_was_never_anchored_cannot_be_placed_on_the_timeline():
    session = Session(PIEZO)
    with pytest.raises(OrchestratorError, match="no hardware anchor"):
        session.timeline.host_of(PIEZO, 0.5)
    assert session.timeline.anchor_of(PIEZO) is None


def test_the_latest_anchor_wins_because_a_restart_resets_the_zero():
    session = Session(TWEEZERS)
    with session.timeline.anchor(TWEEZERS, "first assign", clock=HARDWARE):
        pass
    time.sleep(0.005)
    with session.timeline.anchor(TWEEZERS, "re-assigned", clock=HARDWARE):
        pass
    assert session.timeline.anchor_of(TWEEZERS).label == "re-assigned"
    assert len(session.timeline.anchors) == 2


def test_a_start_that_raised_records_no_anchor_because_the_zero_is_unknown():
    session = Session(PIEZO)
    with pytest.raises(RuntimeError):
        with session.timeline.anchor(PIEZO, "waveform", clock=HARDWARE):
            raise RuntimeError("function.command.start refused")
    assert session.timeline.anchor_of(PIEZO) is None
    assert any(m.event == "start failed" for m in session.timeline.marks)


def test_an_anchor_is_arithmetic_only_and_needs_no_session():
    a = HardwareAnchor(
        PIEZO, "sine", t_before_s=1.0, t_after_s=1.002, clock=HARDWARE, rate_hz=50.0
    )
    assert a.host_t0_s == pytest.approx(1.001)
    assert a.uncertainty_s == pytest.approx(0.001)
    assert a.host_of_sample(50) == pytest.approx(2.001)


def test_merged_interleaves_marks_and_timed_operations_in_time_order():
    session = Session(PIEZO)
    session.timeline.mark(PIEZO, "first")
    with session.instrument(PIEZO, "position.measured.get"):
        time.sleep(0.002)
    session.timeline.mark(PIEZO, "last")

    rows = session.timeline.merged(session.latency)
    events = [e.event for e in rows]
    assert (
        events.index("first")
        < events.index("position.measured.get")
        < events.index("last")
    )
    assert [e.t_s for e in rows] == sorted(e.t_s for e in rows)
    kinds = {e.event: e.kind for e in rows}
    assert kinds["first"] == "mark"
    assert kinds["position.measured.get"] == "op"
    durations = {e.event: e.duration_ms for e in rows}
    assert durations["position.measured.get"] >= 2.0


def test_merged_without_a_latency_log_is_marks_alone():
    session = Session()
    with session.instrument(MICROSCOPE, "getProperty"):
        pass
    assert all(e.kind == "mark" for e in session.timeline.merged())


def test_the_timeline_report_shows_the_anchor_and_its_uncertainty():
    session = Session(PIEZO)
    with session.timeline.anchor(PIEZO, "sine 1 Hz", clock=HOST_SCHED, rate_hz=100.0):
        time.sleep(0.002)
    text = session.timeline.report(session.latency)
    assert "anchor" in text and "sine 1 Hz" in text and "100 Hz" in text
    assert "+/-" in text


def test_the_timeline_report_says_so_when_nothing_happened():
    timeline = Timeline(Clock())
    assert "nothing recorded" in timeline.report()


def test_to_csv_carries_wall_time_so_it_can_meet_mm_metadata(tmp_path):
    session = Session(PIEZO)
    with session.instrument(PIEZO, "position.measured.get"):
        pass
    out = session.timeline.to_csv(tmp_path / "timeline.csv", session.latency)

    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert rows
    wall0, _ = session.clock.anchor
    assert all(float(r["wall_s"]) >= wall0 - 1.0 for r in rows)
    assert {r["subsystem"] for r in rows} >= {SESSION, PIEZO}
    assert {r["kind"] for r in rows} == {"mark", "op"}


def test_the_timeline_is_safe_under_concurrent_writers():
    session = Session(TWEEZERS, PIEZO)

    def worker(subsystem: str) -> None:
        for i in range(50):
            session.timeline.mark(subsystem, f"step {i}")

    threads = [
        threading.Thread(target=worker, args=(s,))
        for s in (MICROSCOPE, TWEEZERS, PIEZO)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([m for m in session.timeline.marks if m.event.startswith("step")]) == 150


def test_an_anchor_records_which_clock_carries_the_run():
    """HOST_SCHED and HARDWARE are different guarantees. The piezo is the first
    today and becomes the second once its generator's sample unit is settled,
    and the record must not make those two runs look identical."""
    session = Session(TWEEZERS, PIEZO)
    with session.timeline.anchor(PIEZO, "sine", clock=HOST_SCHED, rate_hz=100.0):
        pass
    with session.timeline.anchor(
        TWEEZERS, "pattern", clock=HARDWARE, rate_hz=50_000.0
    ):
        pass
    assert session.timeline.anchor_of(PIEZO).clock == HOST_SCHED
    assert session.timeline.anchor_of(TWEEZERS).clock == HARDWARE
    text = session.timeline.report()
    assert f"[{HOST_SCHED}]" in text and f"[{HARDWARE}]" in text


def test_the_clock_kind_has_no_default_and_must_be_named():
    session = Session(PIEZO)
    with pytest.raises(TypeError):
        session.timeline.anchor(PIEZO, "sine")


def test_the_mark_for_a_started_run_names_the_clock():
    session = Session(PIEZO)
    with session.timeline.anchor(PIEZO, "sine", clock=HOST_SCHED):
        pass
    assert any(m.event == f"{HOST_SCHED} started" for m in session.timeline.marks)
