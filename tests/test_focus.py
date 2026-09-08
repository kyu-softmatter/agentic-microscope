"""Tests for the guarded Z axis and the focus sweep (hardware/focus.py).

The point of these is narrow and it is not "does autofocus work" -- that needs
an instrument. It is: **every refusal in SAFETY.md §2 that this module claims to
enforce, fires.** ZDrive is a COLLISION_DEVICE, the stand runs no
objective-escape, and this is the first software Z motion in the repository, so
the guards are the feature. A guard that silently stopped working would leave a
module that moves the stage and reads as safe.
"""

from __future__ import annotations

import math

import pytest

from hardware.focus import (
    DEFAULT_Z_CEILING_UM,
    MAX_SWEEP_POINTS,
    SWEEP_WD_FRACTION,
    FocusAxis,
    FocusCurve,
    FocusError,
    FocusPoint,
    best_z_um,
    free_working_distance_um,
    plan_span,
    suggest_step_um,
)
from hardware.microscope import SAMPLE_Z_WINDOW_UM, Z_RETRACT_DIRECTION

SAMPLE_PLANE_UM = 2959.0  # measured 2026-09-03, 100x with a trapped bead


class _FakeCore:
    """A ZDrive that moves, plus the PFS autofocus calls MMCore exposes."""

    def __init__(self, z_um=SAMPLE_PLANE_UM, pfs_enabled=False, stuck=False):
        self._z = float(z_um)
        self._pfs = bool(pfs_enabled)
        self._stuck = bool(stuck)  # accepts the command, never arrives
        self.commanded: list[float] = []

    def getPosition(self, device):
        assert device == "ZDrive"
        return self._z

    def setPosition(self, device, z):
        assert device == "ZDrive"
        self.commanded.append(float(z))
        if not self._stuck:
            self._z = float(z)

    def waitForDevice(self, device):
        return None

    def isContinuousFocusEnabled(self):
        return self._pfs

    def isContinuousFocusLocked(self):
        return self._pfs

    def enableContinuousFocus(self, on):
        self._pfs = bool(on)

    def getProperty(self, device, prop):
        if device == "PFS":
            return "In Range"
        raise RuntimeError(f"no property {device}.{prop}")


def _axis(**kw):
    kw.setdefault("allow_motion", True)
    core = kw.pop("core", None) or _FakeCore()
    kw.setdefault("log", lambda *_: None)
    return FocusAxis(core, kw.pop("objective_key", "100x-Oil"), **kw), core


# ---- the geometry is read from the registry, not guessed ------------------

def test_the_sign_convention_this_module_depends_on_is_the_measured_one():
    """Every ceiling here assumes increasing Z moves TOWARD the sample. If that
    constant is ever flipped back to the pre-2026-09-05 guess, this fails and
    the whole module needs re-reading, not patching."""
    assert Z_RETRACT_DIRECTION == -1


def test_free_working_distance_matches_the_registry():
    # 100x Oil: 130 um WD against a 170 um design coverslip = no excess.
    assert free_working_distance_um("100x-Oil") == pytest.approx(130.0)
    assert free_working_distance_um("4x") == pytest.approx(20000.0)


def test_unknown_objective_is_refused_with_the_known_keys():
    with pytest.raises(FocusError, match="no objective"):
        free_working_distance_um("63x-Oil")


def test_step_size_is_finer_at_higher_na():
    """DOF is n lambda / NA^2, so the 100x/1.45 step must be far finer than the
    4x/0.20 one. A single constant step for both is the bug this prevents."""
    assert suggest_step_um("100x-Oil") < 0.5
    assert suggest_step_um("4x") > 5.0


# ---- plan_span refuses -----------------------------------------------------

def test_sweep_wider_than_the_working_distance_budget_is_refused():
    limit = SWEEP_WD_FRACTION * 130.0  # 52 um at 100x Oil
    with pytest.raises(FocusError, match="free working distance"):
        plan_span("100x-Oil", SAMPLE_PLANE_UM, limit + 1.0)


def test_sweep_inside_the_working_distance_budget_is_allowed():
    span = plan_span("100x-Oil", SAMPLE_PLANE_UM, 20.0, 1.0)
    assert span.lo_um == pytest.approx(SAMPLE_PLANE_UM - 20.0)
    assert span.hi_um <= span.ceiling_um


def test_the_absolute_ceiling_bites_when_it_is_the_lower_bound():
    """At 4x the WD is 20 mm, so only SAMPLE_Z_WINDOW_UM stops the sweep. This
    is the case where the working-distance bound alone would allow a sweep
    thousands of um past the sample."""
    span = plan_span("4x", 3150.0, 2000.0, 10.0)
    assert span.hi_um <= DEFAULT_Z_CEILING_UM == SAMPLE_Z_WINDOW_UM[1]
    assert "absolute" in span.ceiling_reason


def test_the_working_distance_ceiling_bites_at_high_na():
    span = plan_span("100x-Oil", SAMPLE_PLANE_UM, 40.0, 1.0)
    assert span.ceiling_um == pytest.approx(SAMPLE_PLANE_UM + SWEEP_WD_FRACTION * 130.0)
    assert "WD" in span.ceiling_reason


def test_a_step_coarser_than_the_half_range_is_refused():
    with pytest.raises(FocusError, match="fewer than three points"):
        plan_span("100x-Oil", SAMPLE_PLANE_UM, 1.0, 2.0)


def test_step_equal_to_the_half_range_is_the_minimum_viable_sweep():
    """Exactly three points -- enough for an interior peak and the parabola, and
    the boundary the refusal above sits against."""
    assert plan_span("100x-Oil", SAMPLE_PLANE_UM, 1.0, 1.0).n_points == 3


def test_a_span_clipped_to_fewer_than_three_points_is_refused():
    """The request is fine; the CEILING is what makes it unsweepable. Centring
    5 um below the absolute ceiling with a 5 um step leaves 6 um of room, so
    only two points fit -- and two points cannot have an interior peak. Refusing
    is the honest outcome: the alternative is a 'focus' that is really an
    endpoint."""
    with pytest.raises(FocusError, match="only 2 point"):
        plan_span("100x-Oil", DEFAULT_Z_CEILING_UM - 1.0, 5.0, 5.0)


def test_too_many_points_is_refused_and_says_to_go_coarse_first():
    with pytest.raises(FocusError, match="MAX_SWEEP_POINTS"):
        plan_span("100x-Oil", SAMPLE_PLANE_UM, 50.0, 50.0 / (MAX_SWEEP_POINTS + 10))


def test_positions_ascend_so_the_sample_is_approached_from_retracted():
    span = plan_span("100x-Oil", SAMPLE_PLANE_UM, 10.0, 1.0)
    pos = span.positions
    assert pos == sorted(pos)
    assert len(pos) == span.n_points
    assert pos[-1] <= span.ceiling_um


# ---- move_to refuses -------------------------------------------------------

def test_motion_without_the_switch_is_refused():
    axis, _ = _axis(allow_motion=False)
    with pytest.raises(FocusError, match="allow_motion"):
        axis.move_to(SAMPLE_PLANE_UM)


def test_a_move_above_the_ceiling_is_refused():
    axis, _ = _axis()
    with pytest.raises(FocusError, match="above the ceiling"):
        axis.move_to(DEFAULT_Z_CEILING_UM + 1.0)


def test_a_move_below_the_floor_is_refused():
    axis, _ = _axis()
    with pytest.raises(FocusError, match="below the floor"):
        axis.move_to(-1.0)


def test_a_large_ascent_in_one_move_is_refused_by_default():
    """The default allows no ascent beyond the arrival tolerance, so a caller
    that wants to climb toward the sample has to say how far."""
    axis, _ = _axis()
    with pytest.raises(FocusError, match="TOWARD the sample"):
        axis.move_to(SAMPLE_PLANE_UM + 20.0)


def test_descending_is_unrestricted_because_retracting_is_safe():
    axis, core = _axis()
    axis.move_to(SAMPLE_PLANE_UM - 500.0)
    assert core.getPosition("ZDrive") == pytest.approx(SAMPLE_PLANE_UM - 500.0)


def test_a_move_that_does_not_arrive_is_refused():
    axis, _ = _axis(core=_FakeCore(stuck=True))
    with pytest.raises(FocusError, match="stage reports"):
        axis.move_to(SAMPLE_PLANE_UM - 100.0)


def test_dry_run_commands_nothing():
    axis, core = _axis(dry_run=True)
    axis.move_to(SAMPLE_PLANE_UM - 100.0)
    assert core.commanded == []


# ---- PFS -------------------------------------------------------------------

def test_sweeping_while_pfs_servos_is_refused():
    axis, _ = _axis(core=_FakeCore(pfs_enabled=True))
    with pytest.raises(FocusError, match="PFS is enabled"):
        axis.require_pfs_quiet()


def test_pfs_can_be_switched_off_because_off_is_the_safe_direction():
    axis, core = _axis(core=_FakeCore(pfs_enabled=True))
    state = axis.require_pfs_quiet(disable=True)
    assert state["enabled"] is False
    assert core.isContinuousFocusEnabled() is False


def test_enabling_pfs_to_hold_needs_the_motion_switch():
    """Enabling the servo drives Z to acquire its lock, so it is a stage move."""
    axis, _ = _axis(allow_motion=False, core=_FakeCore(pfs_enabled=False))
    with pytest.raises(FocusError, match="allow_motion"):
        axis.enable_pfs_hold()


# ---- the curve -------------------------------------------------------------

def _curve(scores, z0=2950.0, step=1.0, **diag):
    pts = [FocusPoint(z_um=z0 + i * step, z_readback_um=z0 + i * step,
                      score=s, diagnostics=dict(diag))
           for i, s in enumerate(scores)]
    span = plan_span("100x-Oil", z0 + step * (len(scores) - 1) / 2,
                     max(step * len(scores) / 2, step * 1.5), step)
    return FocusCurve(points=pts, span=span)


def test_a_peak_at_the_end_of_the_span_is_not_called_a_peak():
    c = _curve([1.0, 2.0, 3.0, 4.0, 5.0])  # still climbing
    assert not c.peak_interior
    ok, why = c.verdict()
    assert not ok and "still climbing" in why


def test_a_flat_curve_has_no_peak_worth_the_name():
    c = _curve([1.0, 1.01, 1.0, 1.02, 1.0])
    ok, why = c.verdict()
    assert not ok and "no peak" in why


def test_parabolic_refinement_finds_a_peak_between_two_samples():
    """A Gaussian focus curve sampled on a 1 um grid, true peak deliberately
    off-grid at 2959.4. The refined answer must beat the grid."""
    true_peak = 2959.4
    z0, step = 2955.0, 1.0
    scores = [math.exp(-((z0 + i * step - true_peak) ** 2) / (2 * 1.5 ** 2))
              for i in range(9)]
    c = _curve(scores, z0=z0, step=step)
    assert c.peak_interior
    grid_peak = c.points[c.argmax_index].z_um
    assert abs(c.peak_z_um - true_peak) < abs(grid_peak - true_peak)
    assert c.peak_z_um == pytest.approx(true_peak, abs=0.1)


def test_saturation_is_reported_because_clipping_flattens_the_gradient():
    c = _curve([1.0, 2.0, 5.0, 2.0, 1.0], saturated=True)
    ok, why = c.verdict()
    assert ok and "saturated" in why


# ---- the sweep end to end, on the fake core --------------------------------

def test_sweep_visits_every_planned_z_ascending_and_scores_each():
    axis, core = _axis()
    span = axis.plan(SAMPLE_PLANE_UM, 5.0, 1.0)

    def grab():
        return core.getPosition("ZDrive")

    def score(z):
        return {"sharp": math.exp(-((z - SAMPLE_PLANE_UM) ** 2) / 2.0)}

    curve = axis.sweep(span, grab, score=score, settle_s=0.0)
    assert len(curve.points) == span.n_points
    assert [p.z_um for p in curve.points] == sorted(p.z_um for p in curve.points)
    # The retract to the low end, then one command per point.
    assert core.commanded[0] == pytest.approx(span.lo_um)
    assert curve.peak_z_um == pytest.approx(SAMPLE_PLANE_UM, abs=0.15)
    assert curve.verdict()[0]


# ---- the two contrast bars (added 2026-09-07, after a 4x pass was lost) ----

def test_a_flat_but_interior_fine_pass_is_accepted_where_a_coarse_one_is_not():
    """The bug this fixes, on real numbers from the bench.

    A 4x fine pass scored max/median = 1.02 -- flat, because a fine pass spans
    only a couple of depths of field around a peak the coarse pass already
    found, so every point in it is near the maximum. Judged against the coarse
    bar it was thrown away, and the answer fell back to the 10 um coarse grid
    while a 6.875 um refinement of it sat unused.
    """
    from hardware.focus import MIN_CONTRAST_COARSE, MIN_CONTRAST_FINE

    flat_peak = _curve([1.00, 1.02, 1.05, 1.02, 1.00])
    assert flat_peak.peak_interior
    assert not flat_peak.verdict(MIN_CONTRAST_COARSE)[0]
    assert flat_peak.verdict(MIN_CONTRAST_FINE)[0]


def test_the_fine_bar_still_requires_an_interior_peak():
    """Lowering the contrast bar must not lower the check that actually catches
    a fine sweep centred on the wrong place."""
    from hardware.focus import MIN_CONTRAST_FINE

    climbing = _curve([1.00, 1.01, 1.02, 1.03, 1.04])
    assert not climbing.peak_interior
    ok, why = climbing.verdict(MIN_CONTRAST_FINE)
    assert not ok and "still climbing" in why


def test_best_z_prefers_the_fine_pass_judged_on_its_own_bar():
    coarse = _curve([1.0, 2.0, 5.0, 2.0, 1.0], z0=2950.0, step=10.0)
    fine = _curve([1.00, 1.02, 1.05, 1.02, 1.00], z0=2968.0, step=2.0)
    z, why = best_z_um(coarse, fine)
    assert "fine pass" in why
    assert z == pytest.approx(fine.peak_z_um)


def test_best_z_falls_back_to_coarse_when_the_fine_peak_is_not_interior():
    coarse = _curve([1.0, 2.0, 5.0, 2.0, 1.0], z0=2950.0, step=10.0)
    fine = _curve([1.0, 1.1, 1.2, 1.3, 1.4], z0=2968.0, step=2.0)
    z, why = best_z_um(coarse, fine)
    assert "coarse pass only" in why
    assert z == pytest.approx(coarse.peak_z_um)
