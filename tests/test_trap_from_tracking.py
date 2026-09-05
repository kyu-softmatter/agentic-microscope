"""Tests for the px <-> trap-um transform and the drive that measures it.

None of this can be run against the instrument from here, but the parts that
decide **where a 1064 nm trap is sent** are pure arithmetic, and those are the
parts that must not be wrong. The transform carries an unknown rotation and an
unknown handedness (the Tweez *Beam Position* calibration is
rotation+translation+scale, and nothing in the TCP interface reads it back), so
a sign error is not a small error: it puts the trap at a mirrored position, and
the only symptom is that nothing gets trapped.

So the central test drives a **synthetic** bead through a known matrix and
checks the fit gets it back, including the sign, the handedness, the rotation
and the origin offset -- with a mid-exposure lag, a linear drift and
localisation noise all present at once, because they are all present in the
real measurement.

`config/` is not a package, so the module is loaded by path the way
tests/test_session_scripts.py does it.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # @dataclass needs it registered
    spec.loader.exec_module(module)
    return module


TFT = _load("config/tweezers/trap_from_tracking.py", "_trap_from_tracking")

UM_PX = 0.065                           # 100x at 1x intermediate
SCALE = 1.0 / UM_PX


def _b_true(theta_deg=20.0, flip=True):
    th = math.radians(theta_deg)
    r = np.array([[math.cos(th), -math.sin(th)],
                  [math.sin(th), math.cos(th)]])
    return SCALE * r @ (np.diag([1.0, -1.0]) if flip else np.eye(2))


def _drive_bead(axis, b_true, p0, centre, amp=5.0, freq=1.0, cycles=5.0,
                fps=30.0, tau=0.0165, drift=(0.4, -0.3), noise=0.3, seed=7):
    """A trapped bead following a single-axis sine, as the camera would see it.

    ``tau`` is the mid-exposure lag of a 33 ms frame -- real and unavoidable,
    and the reason the fit de-phases rather than reading the in-phase part.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, cycles / freq, 1.0 / fps)
    d = amp * np.sin(2 * math.pi * freq * (t - tau))
    um = np.tile(np.asarray(centre, dtype=float), (len(t), 1))
    um[:, 0 if axis == "x" else 1] += d
    px = (b_true @ um.T).T + np.asarray(p0) + np.asarray(drift) * t[:, None]
    return t, px + rng.normal(0.0, noise, px.shape)


def _fit_both(b_true, p0, centre, **kw):
    cols, lags, resids, offs, follows = [], [], [], [], []
    for axis in ("x", "y"):
        t, px = _drive_bead(axis, b_true, p0, centre, **kw)
        col, lag, resid, off, _ = TFT.column_from_fit(
            t, px[:, 0], px[:, 1], kw.get("amp", 5.0), kw.get("freq", 1.0))
        cols.append(col)
        lags.append(lag)
        resids.append(resid)
        offs.append(off)
        follows.append(float(np.linalg.norm(col) * UM_PX))
    b = np.column_stack(cols)
    return b, np.mean(offs, axis=0) - b @ np.asarray(centre, dtype=float), \
        lags, resids, follows


# ---- the transform comes back out of the drive -------------------------

def test_fit_recovers_a_known_matrix_including_its_signs():
    b_true, p0_true, centre = _b_true(), np.array([1207.0, 1193.0]), (1.5, -2.0)
    b, p0, *_ = _fit_both(b_true, p0_true, centre)
    # 0.5% of scale: the signs and cross terms are what matter, and a sign
    # error would be 200%.
    assert np.abs(b - b_true).max() / SCALE < 0.005
    assert np.allclose(np.sign(b), np.sign(b_true))
    assert np.allclose(p0, p0_true, atol=1.0)


def test_recovered_scale_rotation_and_handedness():
    b, _, *_ = _fit_both(_b_true(theta_deg=20.0), np.zeros(2), (0.0, 0.0))
    um_px, aniso, rot, handed = TFT.decompose(b)
    assert um_px == pytest.approx(UM_PX, rel=0.002)
    assert rot == pytest.approx(20.0, abs=0.5)
    assert handed == -1                      # image y runs down
    assert aniso < TFT.MAX_ANISOTROPY


@pytest.mark.parametrize("theta", [0.0, 37.0, 90.0, 180.0, -125.0])
def test_rotation_recovered_at_every_orientation(theta):
    """Eight orientations fit 'the origin is the centre'. Guessing is a coin
    flip taken four times, so the fit has to work at all of them."""
    b, _, *_ = _fit_both(_b_true(theta_deg=theta), np.zeros(2), (0.0, 0.0))
    _, _, rot, handed = TFT.decompose(b)
    assert handed == -1
    assert math.cos(math.radians(rot - theta)) > math.cos(math.radians(1.0))


def test_unflipped_handedness_is_reported_as_such():
    b, _, *_ = _fit_both(_b_true(flip=False), np.zeros(2), (0.0, 0.0))
    assert TFT.decompose(b)[3] == +1


def test_origin_is_walked_back_from_a_non_zero_drive_centre():
    """The fit sees the bead while the trap sits at ``centre``, not at (0, 0).
    Reading the fitted offset as p0 directly would put the origin off by
    ``B @ centre`` -- 100 px here, 6 um of trap position."""
    b_true, p0_true = _b_true(), np.array([1200.0, 1200.0])
    centre = (4.0, -3.0)
    b, p0, *_ = _fit_both(b_true, p0_true, centre)
    assert np.allclose(p0, p0_true, atol=1.0)
    naive = p0 + b @ np.asarray(centre)      # what skipping the step gives
    assert np.linalg.norm(naive - p0_true) > 50.0


def test_lag_is_measured_and_does_not_eat_the_amplitude():
    """A 33 ms exposure reports the mid-exposure position: -5.9 deg at 1 Hz.
    Reading the in-phase part alone would under-read the scale by cos(lag)."""
    _, _, lags, resids, follows = _fit_both(_b_true(), np.zeros(2), (0.0, 0.0),
                                            tau=0.0165)
    for lag in lags:
        assert lag == pytest.approx(-360.0 * 1.0 * 0.0165, abs=1.0)
    assert all(f == pytest.approx(1.0, abs=0.01) for f in follows)
    assert all(r < TFT.MAX_RESIDUAL for r in resids)


def test_drift_does_not_leak_into_the_amplitude():
    """A periodic drive separates drift from response; a step calibration
    cannot. 20 px/s over 5 s is 100 px, well past the 77 px response."""
    _, _, _, _, follows = _fit_both(_b_true(), np.zeros(2), (0.0, 0.0),
                                    drift=(20.0, -14.0))
    assert all(f == pytest.approx(1.0, abs=0.02) for f in follows)


# ---- the confirmation half: is the bead actually held? -----------------

def test_a_free_bead_is_reported_as_not_trapped():
    rng = np.random.default_rng(3)
    t = np.arange(0.0, 5.0, 1.0 / 30.0)
    free = np.cumsum(rng.normal(0.0, 1.2, (len(t), 2)), axis=0)
    col, *_ = TFT.column_from_fit(t, free[:, 0], free[:, 1], 5.0, 1.0)
    assert float(np.linalg.norm(col) * UM_PX) < TFT.MIN_FOLLOW_FRAC


def test_a_half_following_bead_trips_the_follow_check():
    t, px = _drive_bead("x", _b_true() * 0.4, np.zeros(2), (0.0, 0.0))
    col, lag, resid, _, _ = TFT.column_from_fit(t, px[:, 0], px[:, 1], 5.0, 1.0)
    follow = float(np.linalg.norm(col) * UM_PX)
    t_ok = _transform(follow_frac=[follow, follow])
    assert any("not trapped" in p for p in t_ok.problems)


def _transform(**over):
    b = _b_true()
    um_px, aniso, rot, handed = TFT.decompose(b)
    kw = dict(b=b.tolist(), p0=[1200.0, 1200.0], objective="100x",
              camera="Kinetix_red", frame_shape=[2400, 2400],
              nominal_um_per_px=UM_PX, fitted_um_per_px=um_px,
              anisotropy=aniso, rotation_deg=rot, handedness=handed,
              lag_deg=[-6.0, -6.0], follow_frac=[1.0, 1.0],
              residual=[0.01, 0.01], amp_um=5.0, freq_hz=1.0, taken="test")
    kw.update(over)
    return TFT.TrapTransform(**kw)


def test_healthy_transform_has_no_problems_and_round_trips():
    t = _transform()
    assert t.problems == ()
    probe = np.array([3.0, -4.0])
    assert np.allclose(t.to_um(t.to_px(probe)), probe, atol=1e-9)
    assert "px <-> trap um" in t.report()


@pytest.mark.parametrize("over,expect", [
    ({"anisotropy": 0.3}, "anisotropy"),
    ({"lag_deg": [-80.0, -6.0]}, "lags"),
    ({"follow_frac": [1.0, 0.1]}, "not trapped"),
    ({"residual": [0.5, 0.01]}, "common phase"),
])
def test_each_check_fires_on_its_own_failure(over, expect):
    problems = _transform(**over).problems
    assert problems and any(expect in p for p in problems)


# ---- the drive refuses rather than deforming ---------------------------

def test_schedule_reaches_the_commanded_amplitude_in_the_right_axis():
    sched = TFT.sine_schedule(5.0, 1.0, "x", 2.0, 50.0, (0.0, 0.0))
    xs = np.array([x for _, x, _ in sched])
    ys = np.array([y for _, _, y in sched])
    assert xs.max() == pytest.approx(5.0, abs=0.02)
    assert xs.min() == pytest.approx(-5.0, abs=0.02)
    assert np.allclose(ys, 0.0)
    assert len(sched) == 101                 # 2 cycles at 50 Hz, plus the end


def test_offsets_are_refused_not_clamped():
    """The GUI clips a position outside the trapezoid silently and does not
    draw it, so clamping here would deform the drive with no error anywhere."""
    sched = TFT.sine_schedule(30.0, 1.0, "x", 1.0, 50.0, (0.0, 0.0))
    with pytest.raises(SystemExit, match="REFUSED"):
        TFT.check_offsets(sched, TFT.MAX_OFFSET_UM)
    # and the schedule itself is untouched -- no silent clamp on the way in
    assert max(abs(x) for _, x, _ in sched) == pytest.approx(30.0, abs=0.1)


def test_the_drive_centre_counts_towards_the_offset_limit():
    sched = TFT.sine_schedule(5.0, 1.0, "x", 1.0, 50.0, (18.0, 0.0))
    with pytest.raises(SystemExit, match="REFUSED"):
        TFT.check_offsets(sched, TFT.MAX_OFFSET_UM)


def test_missing_calibration_refuses_rather_than_guessing(tmp_path):
    with pytest.raises(SystemExit, match="REFUSED"):
        TFT.load_transform(tmp_path / "absent.yaml")


def test_transform_survives_a_save_load_round_trip(tmp_path):
    path = tmp_path / "px-to-trap-um.yaml"
    TFT.save_transform(_transform(), path)
    back = TFT.load_transform(path)
    assert np.allclose(back.matrix, _transform().matrix)
    assert back.objective == "100x"
    assert "objective is recorded below and checked on load" in \
        path.read_text(encoding="utf-8")


# ---- detector windows follow the objective -----------------------------

def test_bead_windows_scale_with_the_pixel_size():
    """The offline analysis hardcodes mask_r=45 / win=32 for 60x. At 100x a
    5 um bead is r = 38 px, so both would sit inside the bead: the mask would
    find one particle repeatedly and the refine window would clip its own
    signal."""
    at_60 = TFT.bead_scale(0.10833)
    at_100 = TFT.bead_scale(0.065)
    assert at_60["r_px"] == pytest.approx(23.0, abs=1.0)
    assert at_100["r_px"] == pytest.approx(38.5, abs=1.0)
    # the windows track the pixel size, so the ratio is the pixel-size ratio
    assert at_100["r_px"] / at_60["r_px"] == pytest.approx(0.10833 / 0.065,
                                                           rel=0.02)
    for s in (at_60, at_100):
        assert s["mask_r"] > s["r_px"]       # do not re-find the same bead
        assert s["win"] > s["r_px"]          # do not clip the bead
    assert at_100["win"] > 32                # the analysis default is too small


# ---- the space-bar sequence: its guards, not its window ----------------

TS = _load("config/tweezers/trap_sequence.py", "_trap_sequence")


def test_provisional_transform_flips_y_and_centres_the_origin():
    """Image y runs down, so +y in trap um has to go UP in pixels. Getting
    this backwards is one of the eight orientations and it is the one that
    looks nearly right -- the trap lands mirrored about the centre line."""
    t = TS.provisional_transform(UM_PX, (1200, 1200), "100x", "Kinetix_red")
    assert t.p0 == [600.0, 600.0]
    assert t.taken == "PROVISIONAL"
    assert t.to_px(np.array([0.0, 0.0]))[1] == pytest.approx(600.0)
    assert t.to_px(np.array([0.0, 5.0]))[1] < 600.0      # +y um is up in px
    assert t.to_px(np.array([5.0, 0.0]))[0] > 600.0


def _saved(tmp_path, name="cal.yaml", **over):
    t = _transform(p0=[600.0, 600.0], frame_shape=[1200, 1200], **over)
    TFT.save_transform(t, tmp_path / name)
    return tmp_path / name


def test_a_matching_saved_transform_is_used_as_is(tmp_path):
    t, why = TS.usable_transform(_saved(tmp_path), (1200, 1200), "100x",
                                 UM_PX, "Kinetix_red")
    assert why is None
    assert t.taken == "test"


def test_a_different_roi_falls_back_to_the_guess(tmp_path):
    """p0 lives in ROI-relative pixels, so the same calibration read at a
    different ROI puts the origin half the size difference out -- 600 px at
    1200 vs 2400, which is 39 um of trap position."""
    t, why = TS.usable_transform(_saved(tmp_path), (2400, 2400), "100x",
                                 UM_PX, "Kinetix_red")
    assert "taken at 1200x1200" in why
    assert t.taken == "PROVISIONAL"


def test_a_different_objective_falls_back_to_the_guess(tmp_path):
    _, why = TS.usable_transform(_saved(tmp_path), (1200, 1200), "60x",
                                 UM_PX, "Kinetix_red")
    assert "taken on '100x'" in why


def test_a_transform_that_failed_its_checks_is_not_used(tmp_path):
    path = _saved(tmp_path, follow_frac=[0.1, 1.0])
    _, why = TS.usable_transform(path, (1200, 1200), "100x", UM_PX, "K")
    assert "unresolved problems" in why


def test_no_saved_file_is_reported_rather_than_raising(tmp_path):
    """`load_transform` refuses outright; the sequence has to keep going so
    stage 3 can measure one, so it substitutes the guess and says so."""
    t, why = TS.usable_transform(tmp_path / "absent.yaml", (1200, 1200),
                                 "100x", UM_PX, "K")
    assert why == "no saved transform"
    assert t.taken == "PROVISIONAL"


def test_the_held_cut_sits_between_a_free_and_a_trapped_bead():
    """A free 5 um bead near the wall covers sqrt(2 D t) at the D measured on
    2026-09-04. The cut has to be below that and above localisation noise."""
    free_nm = math.sqrt(2 * 0.0395 * TS.GRAB_WATCH_S) * 1000.0
    assert free_nm > TS.HELD_EXCURSION_NM > 3 * 0.3 * UM_PX * 1000.0


# ---- the straight-line move to the origin ------------------------------
#
# This one drives a 1064 nm trap across the field, so the geometry is worth
# pinning even though the window it lives in cannot be tested from here. A
# single TRAP_POSITION to the origin would imply ~1000 um/s over a 16 um trip
# and leave the bead behind; the ramp is what makes the move survivable, and
# the invariants below are the ones that make it a ramp.

import types                                                    # noqa: E402


class _StubOt:
    def __init__(self):
        self.sent = []

    def set_trap_position(self, name, x, y):
        self.sent.append((float(x), float(y)))


class _StubCore:
    def getImageHeight(self):
        return 200

    def getImageWidth(self):
        return 200


def _blob(h=200, w=200, cx=100.0, cy=100.0, r=8.0):
    yy, xx = np.mgrid[0:h, 0:w]
    return 1000.0 * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r ** 2)))


def _sequence(um_start=(12.0, -5.0), speed=10.0):
    args = types.SimpleNamespace(
        centre_um=[0.0, 0.0], trap_name="Trap 1", speed_um_s=speed,
        amp_um=5.0, freq_hz=1.0, cycles=5.0, max_offset_um=20.0,
        isolation_um=12.0)
    seq = TS.Sequence(_StubCore(), "cam", _StubOt(), None,
                      TS.provisional_transform(UM_PX, (200, 200), "100x",
                                               "cam"),
                      None, args, UM_PX)
    seq.target_um = None if um_start is None else np.array(um_start)
    seq.target_px = np.array([100.0, 100.0])
    return seq


def test_ramp_walks_a_straight_line_to_the_origin():
    seq = _sequence()
    seq.enter_hold()
    assert seq.ramping is True
    assert seq.ramp_dist == pytest.approx(13.0)          # 12, -5
    img = _blob()
    for k in range(1, 40):
        seq._ramp_tick(img, seq.t_stage + k * 0.05)
        if not seq.ramping:
            break
    sent = np.array(seq.ot.sent)
    # every commanded point is on the segment from ramp_from to the origin
    unit = seq.ramp_from / seq.ramp_dist
    cross = sent[:, 0] * unit[1] - sent[:, 1] * unit[0]
    assert np.abs(cross).max() < 1e-9
    # monotonically inward, and it ends exactly at the origin
    dist = np.linalg.norm(sent, axis=1)
    assert np.all(np.diff(dist) <= 1e-9)
    assert dist[-1] == pytest.approx(0.0, abs=1e-9)
    assert dist[0] < seq.ramp_dist                        # it moved on tick 1


def test_ramp_does_not_overshoot_the_origin():
    """f is clamped at 1, so a late tick lands on the origin rather than
    sailing through it to the far side."""
    seq = _sequence()
    seq.enter_hold()
    seq._ramp_tick(_blob(), seq.t_stage + 100.0)          # absurdly late
    assert seq.ot.sent[-1] == (0.0, 0.0)
    assert seq.ramping is False


def test_ramp_takes_distance_over_speed():
    seq = _sequence(um_start=(30.0, 40.0), speed=10.0)    # 50 um at 10 um/s
    seq.enter_hold()
    img = _blob()
    seq._ramp_tick(img, seq.t_stage + 4.99)
    assert seq.ramping is True                            # not there yet at 5 s
    seq._ramp_tick(img, seq.t_stage + 5.01)
    assert seq.ramping is False


def test_a_faster_ramp_is_the_same_path_in_less_time():
    """Speed changes the schedule, never the path -- the bead has to travel
    the same line whatever the drag budget allows."""
    slow, fast = _sequence(speed=5.0), _sequence(speed=20.0)
    for seq in (slow, fast):
        seq.enter_hold()
        img = _blob()
        for k in range(1, 200):
            seq._ramp_tick(img, seq.t_stage + k * 0.02)
            if not seq.ramping:
                break
    for seq in (slow, fast):
        unit = seq.ramp_from / seq.ramp_dist
        s = np.array(seq.ot.sent)
        assert np.abs(s[:, 0] * unit[1] - s[:, 1] * unit[0]).max() < 1e-9
    assert len(slow.ot.sent) > len(fast.ot.sent)


def test_no_ramp_when_the_trap_is_already_at_the_origin():
    seq = _sequence(um_start=None)
    seq.enter_hold()
    assert seq.ramping is False
    assert seq.ot.sent == [(0.0, 0.0)]


# ---- the drive gate, and the locked hold target ------------------------

def test_a_drive_that_would_leave_the_range_is_refused_before_it_starts():
    """Measured 2026-09-04: the bead sat 17.5 um out, +5 um of x drive put
    the peak at 22.4 um, and the per-tick check aborted the run after 4
    tracked frames -- for a fit that needs 20. Computable in advance."""
    seq = _sequence(um_start=(16.9, -4.55))
    assert seq.start_drive() is False
    assert seq.stage == 0                     # did not enter OSCILLATE
    assert seq.ot.sent == []                  # and sent nothing
    assert "press H" in seq.message


def test_the_same_bead_can_be_driven_once_it_is_at_the_origin():
    """Which is the point of the refusal's advice: HOLD first, then drive."""
    seq = _sequence(um_start=(0.0, 0.0))
    assert seq.start_drive() is True
    assert seq.stage == 3


def test_the_gate_accounts_for_the_full_amplitude_not_just_the_centre():
    seq = _sequence(um_start=(17.0, 0.0))     # inside 20 on its own
    assert np.linalg.norm(seq.target_um) < seq.args.max_offset_um
    assert seq.start_drive() is False         # 17 + 5 is not


def test_hold_locks_onto_one_bead_and_does_not_re_pick_each_tick():
    """The first version re-picked the nearest-to-centre detection every
    tick, so with two beads competing the history mixed two positions and
    the RMS it reported was the distance between them. Measured: a verdict
    chattering 55, 152, 61, 155, 143, 151, 149 nm while the reported
    position jumped 300 px."""
    seq = _sequence(um_start=None)
    seq.enter_hold()
    # two beads, the far one very slightly nearer the centre on later ticks
    seq.circles = np.array([[100.0, 100.0, 8.0], [160.0, 160.0, 8.0]])
    img = _blob(cx=100.0, cy=100.0)
    seq._hold_tick(img, 0.0)
    locked = seq.hold_lock.copy()
    seq.circles = np.array([[160.0, 160.0, 8.0], [100.0, 100.0, 8.0]])
    for k in range(1, 12):
        seq._hold_tick(img, k * 0.03)
    assert np.allclose(seq.hold_lock, locked)
    assert np.linalg.norm(seq.target_px - np.array([100.0, 100.0])) < 2.0


def test_hold_judges_a_still_bead_as_held_and_says_where_it_is():
    seq = _sequence(um_start=None)
    seq.enter_hold()
    seq.circles = np.array([[100.0, 100.0, 8.0]])
    img = _blob(cx=100.0, cy=100.0)
    for k in range(80):
        seq._hold_tick(img, k * 0.033)        # 2.6 s, a full window
    assert seq.hold_state is True
    assert "HELD" in seq.message


def test_the_held_verdict_has_hysteresis_rather_than_one_cut():
    assert TS.HELD_ENTER_NM < TS.HELD_EXCURSION_NM < TS.HELD_LEAVE_NM
    # and the band brackets the measured chatter that motivated it
    for observed in (143.0, 149.0, 151.0, 152.0, 155.0):
        assert TS.HELD_ENTER_NM < observed < TS.HELD_LEAVE_NM
    # while the two clean single-bead windows sit clear of it
    for held in (55.0, 61.0):
        assert held < TS.HELD_ENTER_NM
