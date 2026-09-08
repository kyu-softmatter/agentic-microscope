r"""Guarded ``ZDrive`` motion, and a focus sweep built on it.

**This is the first software stage motion in this repository, and that is the
thing to understand before reading anything else.** SAFETY.md §2 says it
plainly: ``Microscope`` exposes no stage-motion API at all -- only property
writes -- so a real Z move goes through ``core.setPosition("ZDrive", ...)`` on
the raw MMCore and never reaches ``_require_write``. ``ZDrive``'s membership in
``COLLISION_DEVICES`` guards writes to ZDrive *properties*, not Z motion.
``focus_monitor.py`` was written to keep it that way: the operator turns the
knob, the script names the peak afterwards.

So this module exists to make the *other* half possible without giving up the
guarantee. It does not relax the rule; it re-states it as code:

  1. ``allow_motion=True`` is required, mirroring ``Microscope``'s switch. The
     default refuses.
  2. **PFS must not be servoing.** A held focus fights a sweep -- the stage is
     commanded to Z, PFS drives it back, and the recorded curve is of a plane
     that was never visited. 2026-09-07 lost a session partly to this ("PFS
     holds a focus, it does not find one"). Read through MMCore's own autofocus
     API, not a property-name guess.
  3. **The ceiling is computed, never assumed.** Increasing Z moves TOWARD the
     sample (``Z_RETRACT_DIRECTION = -1``, measured KH 2026-09-05, and since
     2026-09-06 the configs say so too: ``FocusDirection,ZDrive,1``). Collision
     therefore lives at HIGH Z, and every sweep is capped at
     ``min(absolute ceiling, centre + fraction x free working distance)``.
     At 100x Oil that fraction is 52 um out of 130 um of WD.
  4. **Every sweep ascends.** The first move is a retract to the low end -- the
     safe direction -- and the approach to the sample is then monotonic and in
     steps no larger than the sweep step. It also makes the measurement
     cleaner: every point is approached from the same side, so backlash enters
     as an offset rather than as scatter.
  5. **Every move is verified by readback.** A commanded Z that did not arrive
     is a refusal, not a data point. This is what catches a limit, a jam, or a
     PFS that was re-enabled underneath the sweep.
  6. ``dry_run=True`` prints the whole Z list and commands nothing.

What it deliberately does NOT do: touch the camera or the light. ``sweep()``
takes a ``grab`` callable and calls it at each Z. Ownership of the camera, the
illuminator, and the dose budget stays with the caller, where the light-off
``finally`` already lives.

THE STEP SIZE IS PHYSICS, NOT TASTE
-----------------------------------
``suggest_step_um`` returns half the wave-optical depth of field
(``n lambda / NA^2``, ``optics.components.Objective.depth_of_field_nm``), which
is ~0.19 um at 100x Oil / NA 1.45 in green and ~6.9 um at 4x / NA 0.20. A
sweep coarser than that cannot resolve the peak it is looking for; much finer
just costs dose and time. The peak is then refined below the step by a
three-point parabola, so the reported Z is not quantised to the grid.

WHAT IT REFUSES TO CALL A PEAK
------------------------------
An argmax at either end of the span is not a peak -- the curve was still
climbing when the sweep ran out -- and ``FocusCurve.peak_interior`` is False.
A curve whose maximum barely exceeds its own median has no peak either
(``contrast_ratio``). A saturated frame scores LOW on Tenengrad because
clipping flattens the gradient, so a sweep with saturated points can invert;
those are flagged rather than averaged in. All three are reported, none is
adjudicated here -- that is the caller's, and ultimately the operator's, call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from hardware.microscope import (
    SAMPLE_Z_WINDOW_UM,
    Z_RETRACT_DIRECTION,
)

Z_DEVICE = "ZDrive"

#: Fraction of the objective's free working distance a single sweep may span
#: either side of its centre. 0.4 leaves the majority of the WD unspent at the
#: moment the sweep reaches its ceiling: 52 um of 130 um at 100x Oil, 64 um of
#: 160 um at 40x WI. Not derived from anything -- chosen, and named here so a
#: change to it is a visible change rather than an edit inside a function.
SWEEP_WD_FRACTION = 0.4

#: Absolute ceiling on any commanded Z, um. The top of the window the operator
#: stated and a measurement confirmed (`SAMPLE_Z_WINDOW_UM`, user 2026-09-03:
#: "your sample is usually around 2800-3200um in z"; focused at 100x with a
#: trapped bead at ZDrive = 2959.000, PFS `In Range`).
#:
#: A sweep is capped at this OR at the working-distance limit, whichever is
#: lower -- 3200 is 241 um above the measured sample plane, which is more than
#: the 100x Oil's whole 130 um of WD, so this bound alone is not protection.
DEFAULT_Z_CEILING_UM = SAMPLE_Z_WINDOW_UM[1]

#: Retracting is always safe, so the floor is generous. 0.0 is where the
#: operator's own objective-change sequence parks the stage (`Z -> 0`, rotate,
#: `Z -> 2800`) -- SAFETY.md §2.
DEFAULT_Z_FLOOR_UM = 0.0

#: How close a readback must land to the commanded Z to count as arrived, um.
#: The Ti2 ZDrive's own step is finer than this; the tolerance is here to
#: catch a move that did not happen, not to certify one that did.
ARRIVAL_TOLERANCE_UM = 0.5

#: Refuse a sweep longer than this many points. A time and dose guard, not a
#: safety one: at 0.19 um steps a 52 um half-range is already 548 points, so
#: hitting this means the plan wants a coarse pass first.
MAX_SWEEP_POINTS = 400

#: Minimum peak-over-median a COARSE sweep must show to be called a peak. The
#: coarse pass asks "is there focus anywhere in this range", so a curve that
#: barely rises above its own median answers no.
MIN_CONTRAST_COARSE = 1.2

#: The same bar for a FINE sweep, and it has to be far lower -- 2026-09-07, when
#: a perfectly good 4x fine pass was rejected at 1.09 against the coarse bar.
#:
#: The reason is structural, not empirical. A fine pass is deliberately centred
#: on a peak the coarse pass already found and spans only a few depths of field,
#: so **every** point in it is near the maximum and max/median is ~1 BY
#: CONSTRUCTION. Judging it by the coarse bar rejects exactly the passes that
#: worked, and the flatter the true peak the more certainly it does: at 4x the
#: depth of field is 13.75 um, so a +/-30 um fine span is barely two DOF wide.
#:
#: What still has to hold for a fine pass is that the peak is INTERIOR -- that
#: check is untouched, and it is the one that catches a fine sweep centred on
#: the wrong place. The contrast bar here only rejects a DEGENERATE curve (a
#: dead-flat or saturated one); it is not doing the real work.
#:
#: 1.005 rather than 1.02, and the margin is the point: the 4x fine pass that
#: exposed this measured 1.02 on the bench, so a 1.02 bar sat exactly on the
#: observed value and would have rejected the next slightly flatter peak. A
#: threshold tuned to one measurement is not a threshold.
MIN_CONTRAST_FINE = 1.005

#: Emission used for the default step size when the caller names none. Green,
#: because both current arms are green-ish (Dragon Green and the Abvigen red
#: bead read on the GREEN line) and DOF varies as lambda -- a 640 nm choice
#: would only make the step coarser.
DEFAULT_EMISSION_NM = 550.0


class FocusError(Exception):
    """A refusal. Raised for every guard in this module.

    Deliberately not ``MicroscopeError``: that type means "the device
    configuration was refused", and these mean "the motion was refused". A
    caller that wants to catch one and not the other can.
    """


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def registry_key(name: str) -> str:
    """Canonical ``data/objectives.yaml`` key for a name or a Micro-Manager label.

    ``core.getStateLabel("Nosepiece")`` answers ``"6-Plan Apo LmbdD0.13 100x Oil"``
    and the registry key is ``"100x-Oil"``. ``find_objective`` accepts either --
    the registry is keyed by both -- but everything *recorded* should carry the
    canonical key, so a result file does not identify the same lens two ways
    depending on which end of the code wrote it.
    """
    from optics.components import find_objective, objective_keys

    obj = find_objective(name)
    if obj is None:
        raise FocusError(
            f"no objective {name!r} in data/objectives.yaml; "
            f"known keys: {', '.join(objective_keys())}"
        )
    for key in objective_keys():
        if find_objective(key) is obj:
            return key
    return name  # unreachable while objectives() is keyed by both


def free_working_distance_um(objective_key: str) -> float:
    """Free WD for a registry objective, um, with the coverslip accounted for.

    Delegates to ``sample.aberration.free_working_distance_um``, which holds
    the reading that makes the numbers make sense: vendor WD is quoted to the
    specimen-facing surface of the *design* coverslip, so only the excess over
    design eats into the budget. Imported lazily so this module stays
    importable without the optics/sample packages, the way
    ``hardware.microscope`` stays importable without Micro-Manager.
    """
    from optics.components import find_objective
    from sample.aberration import free_working_distance_um as fwd

    obj = find_objective(objective_key)
    if obj is None:
        from optics.components import objective_keys

        raise FocusError(
            f"no objective {objective_key!r} in data/objectives.yaml; "
            f"known keys: {', '.join(objective_keys())}"
        )
    if obj.wd_um is None:
        raise FocusError(
            f"objective {objective_key!r} has no wd_um in data/objectives.yaml, "
            "so a working-distance bound cannot be computed -- and this module "
            "will not sweep without one"
        )
    return float(fwd(obj.wd_um, float(obj.coverslip_um or 170.0)))


def suggest_step_um(objective_key: str, emission_nm: float = DEFAULT_EMISSION_NM) -> float:
    """Half the wave-optical depth of field, um. See the module docstring."""
    from optics.components import find_objective

    obj = find_objective(objective_key)
    if obj is None:
        raise FocusError(f"no objective {objective_key!r} in data/objectives.yaml")
    return float(obj.depth_of_field_nm(emission_nm)) / 2.0 / 1000.0


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ZSpan:
    """A checked, ascending list of Z positions. Produced only by ``plan_span``."""

    lo_um: float
    hi_um: float
    step_um: float
    objective_key: str
    ceiling_um: float
    ceiling_reason: str

    @property
    def positions(self) -> list[float]:
        """Ascending -- the approach to the sample is the second half of the sweep."""
        n = self.n_points
        return [self.lo_um + i * self.step_um for i in range(n)]

    @property
    def n_points(self) -> int:
        return int(round((self.hi_um - self.lo_um) / self.step_um)) + 1

    def describe(self) -> str:
        return (
            f"{self.lo_um:.3f} -> {self.hi_um:.3f} um in {self.step_um:.4f} um steps "
            f"({self.n_points} points, ascending); ceiling {self.ceiling_um:.3f} um "
            f"({self.ceiling_reason})"
        )


def plan_span(objective_key: str,
              z_center_um: float,
              half_range_um: float,
              step_um: float | None = None,
              *,
              z_ceiling_um: float = DEFAULT_Z_CEILING_UM,
              z_floor_um: float = DEFAULT_Z_FLOOR_UM,
              wd_fraction: float = SWEEP_WD_FRACTION,
              emission_nm: float = DEFAULT_EMISSION_NM) -> ZSpan:
    """Turn a requested sweep into a checked one, or refuse and say why.

    Every refusal names both numbers it compared, because "out of range" with
    no arithmetic in it is the message that gets worked around.
    """
    if half_range_um <= 0:
        raise FocusError(f"half_range_um must be positive, got {half_range_um}")

    fwd_um = free_working_distance_um(objective_key)
    wd_limit_um = wd_fraction * fwd_um
    if half_range_um > wd_limit_um:
        raise FocusError(
            f"refusing a +/-{half_range_um:.1f} um sweep at {objective_key}: the "
            f"limit is {wd_limit_um:.1f} um, which is {wd_fraction:g} x the "
            f"{fwd_um:.1f} um free working distance. Increasing Z moves TOWARD "
            f"the sample (Z_RETRACT_DIRECTION = {Z_RETRACT_DIRECTION}) and the "
            f"stand runs no escape, so the WD is the whole budget."
        )

    if step_um is None:
        step_um = suggest_step_um(objective_key, emission_nm)
    if step_um <= 0:
        raise FocusError(f"step_um must be positive, got {step_um}")
    if step_um > half_range_um:
        raise FocusError(
            f"step {step_um:.4f} um is larger than the half-range "
            f"{half_range_um:.4f} um -- that sweep has fewer than three points "
            f"and cannot have an interior peak"
        )

    # The ceiling: whichever of the two bounds bites first.
    wd_ceiling = z_center_um + wd_limit_um
    if wd_ceiling <= z_ceiling_um:
        ceiling_um, reason = wd_ceiling, (
            f"{wd_fraction:g} x {fwd_um:.0f} um WD above centre"
        )
    else:
        ceiling_um, reason = z_ceiling_um, "absolute SAMPLE_Z_WINDOW_UM ceiling"

    hi = min(z_center_um + half_range_um, ceiling_um)
    lo = max(z_center_um - half_range_um, z_floor_um)
    if hi <= lo:
        raise FocusError(
            f"empty span at {objective_key}: centre {z_center_um:.3f} um with "
            f"+/-{half_range_um:.1f} um clips to [{lo:.3f}, {hi:.3f}] against "
            f"floor {z_floor_um:.1f} and ceiling {ceiling_um:.3f}"
        )

    # Snap `hi` down onto the step grid so the last commanded point is inside
    # the ceiling rather than rounded over it.
    n = int((hi - lo) / step_um) + 1
    if n < 3:
        raise FocusError(
            f"only {n} point(s) fit in [{lo:.3f}, {hi:.3f}] um at a "
            f"{step_um:.4f} um step; a peak needs at least three"
        )
    if n > MAX_SWEEP_POINTS:
        raise FocusError(
            f"{n} points exceeds MAX_SWEEP_POINTS = {MAX_SWEEP_POINTS}. Run a "
            f"coarse pass first (larger --step), then a fine pass around its "
            f"peak -- which is what `autofocus()` does."
        )
    hi = lo + (n - 1) * step_um

    return ZSpan(
        lo_um=lo, hi_um=hi, step_um=step_um, objective_key=objective_key,
        ceiling_um=ceiling_um, ceiling_reason=reason,
    )


# --------------------------------------------------------------------------
# the curve
# --------------------------------------------------------------------------

@dataclass
class FocusPoint:
    z_um: float          # commanded
    z_readback_um: float  # where the stage said it was
    score: float
    diagnostics: dict = field(default_factory=dict)


@dataclass
class FocusCurve:
    """A sweep and what can honestly be concluded from it."""

    points: list[FocusPoint]
    span: ZSpan | None = None

    @property
    def scores(self) -> list[float]:
        return [p.score for p in self.points]

    @property
    def argmax_index(self) -> int:
        s = self.scores
        return max(range(len(s)), key=s.__getitem__)

    @property
    def peak_interior(self) -> bool:
        """False when the argmax sits at an end -- the sweep ran out before the
        curve turned over, so the peak is a lower bound on Z, not a location."""
        i = self.argmax_index
        return 0 < i < len(self.points) - 1

    @property
    def contrast_ratio(self) -> float:
        """Peak score over the median score. ~1 means there is no peak here."""
        s = sorted(self.scores)
        median = s[len(s) // 2] if s else 0.0
        return (max(self.scores) / median) if median > 0 else float("inf")

    @property
    def saturated_points(self) -> int:
        return sum(1 for p in self.points if p.diagnostics.get("saturated"))

    @property
    def peak_z_um(self) -> float:
        """Sub-step peak Z by three-point parabola, or the raw argmax Z.

        The parabola is fitted to the argmax and its two neighbours. Falls back
        to the raw grid position when the peak is at an end (no neighbours) or
        the three points are collinear (zero curvature), rather than dividing
        by ~0 and reporting a Z somewhere off the span.
        """
        i = self.argmax_index
        if not self.peak_interior:
            return self.points[i].z_um
        y0, y1, y2 = (self.points[i - 1].score,
                      self.points[i].score,
                      self.points[i + 1].score)
        denom = y0 - 2.0 * y1 + y2
        if denom == 0:
            return self.points[i].z_um
        delta = 0.5 * (y0 - y2) / denom
        if abs(delta) > 1.0:  # a parabola pointing outside the bracket
            return self.points[i].z_um
        step = self.span.step_um if self.span else (
            self.points[i + 1].z_um - self.points[i].z_um)
        return self.points[i].z_um + delta * step

    def verdict(self, min_contrast: float = MIN_CONTRAST_COARSE) -> tuple[bool, str]:
        """``(usable, why)``. Never decides for the caller -- just states it.

        ``min_contrast`` is a parameter and not a constant because the same bar
        cannot judge both passes. See :data:`MIN_CONTRAST_FINE`.
        """
        if len(self.points) < 3:
            return False, f"only {len(self.points)} points"
        if not self.peak_interior:
            i = self.argmax_index
            end = "low" if i == 0 else "high"
            return False, (
                f"peak is at the {end} end of the span ({self.points[i].z_um:.3f} um) "
                f"-- the curve was still climbing when the sweep ran out, so widen "
                f"the range or re-centre; this Z is a bound, not a focus"
            )
        if self.contrast_ratio < min_contrast:
            return False, (
                f"no peak worth the name: max/median = {self.contrast_ratio:.2f} "
                f"against a bar of {min_contrast:.2f}. Either the target has no "
                f"contrast at this magnification, or the whole span is out of focus"
            )
        if self.saturated_points:
            return True, (
                f"peak at {self.peak_z_um:.3f} um, but {self.saturated_points} of "
                f"{len(self.points)} points were saturated -- clipping flattens the "
                f"gradient, so those score LOW and can invert the curve. Re-run "
                f"with less light before trusting this Z"
            )
        return True, (
            f"peak at {self.peak_z_um:.3f} um, max/median = "
            f"{self.contrast_ratio:.2f}, interior"
        )


# --------------------------------------------------------------------------
# the axis
# --------------------------------------------------------------------------

class FocusAxis:
    """Guarded ``ZDrive`` motion. See the module docstring for the guards."""

    def __init__(self, core, objective_key: str, *,
                 allow_motion: bool = False,
                 dry_run: bool = False,
                 z_ceiling_um: float = DEFAULT_Z_CEILING_UM,
                 z_floor_um: float = DEFAULT_Z_FLOOR_UM,
                 wd_fraction: float = SWEEP_WD_FRACTION,
                 arrival_tolerance_um: float = ARRIVAL_TOLERANCE_UM,
                 log: Callable[[str], None] = print):
        self.core = core
        self.objective_key = objective_key
        self.allow_motion = bool(allow_motion)
        self.dry_run = bool(dry_run)
        self.z_ceiling_um = float(z_ceiling_um)
        self.z_floor_um = float(z_floor_um)
        self.wd_fraction = float(wd_fraction)
        self.arrival_tolerance_um = float(arrival_tolerance_um)
        self.log = log
        self.moves: list[tuple[float, float]] = []  # (commanded, readback)

    # ---- reads -----------------------------------------------------------

    def position_um(self) -> float:
        return float(self.core.getPosition(Z_DEVICE))

    def pfs_state(self) -> dict:
        """PFS servo state, read through MMCore's autofocus API.

        ``PFS`` is registered as an AutoFocus device (``Device,PFS,NikonTi2,PFS``),
        so ``isContinuousFocusEnabled`` answers this without guessing at a
        property name -- which matters, because the one PFS property this repo
        does name (``PFS in Range``) reports the *coverslip*, not the servo, and
        ``In Range`` is the normal reading for a focused sample. It can veto;
        it can never permit (SAFETY.md §2.4).
        """
        state: dict = {}
        for key, fn in (("enabled", "isContinuousFocusEnabled"),
                        ("locked", "isContinuousFocusLocked")):
            try:
                state[key] = bool(getattr(self.core, fn)())
            except Exception as exc:  # adapter without the call, or no device
                state[key] = None
                state[f"{key}_error"] = str(exc)
        try:
            from hardware.microscope import PFS_IN_RANGE_PROPERTY

            state["in_range"] = str(self.core.getProperty("PFS", PFS_IN_RANGE_PROPERTY))
        except Exception as exc:
            state["in_range"] = None
            state["in_range_error"] = str(exc)
        return state

    # ---- guards ----------------------------------------------------------

    def require_motion(self, what: str) -> None:
        if not self.allow_motion:
            raise FocusError(
                f"refusing {what}: this FocusAxis was constructed without "
                f"allow_motion. ZDrive is in COLLISION_DEVICES and the stand "
                f"runs no objective-escape (SAFETY.md §2) -- pass "
                f"allow_motion=True, and check clearance first."
            )

    def require_pfs_quiet(self, *, disable: bool = False) -> dict:
        """Refuse to sweep while PFS is servoing; optionally switch it off.

        Switching PFS *off* moves nothing -- it stops the servo. Switching it on
        does move, which is why only the off direction is offered here.
        """
        state = self.pfs_state()
        if state.get("enabled") is None:
            self.log(
                f"  PFS: servo state unreadable ({state.get('enabled_error')}). "
                f"Proceeding -- but if focus fights the sweep, this is why."
            )
            return state
        if not state["enabled"]:
            self.log(f"  PFS: off (in-range flag reads {state.get('in_range')!r})")
            return state
        if not disable:
            raise FocusError(
                "refusing to sweep while PFS is enabled: the servo will drive Z "
                "back and the curve will describe planes the stage never held. "
                "2026-09-07: 'PFS holds a focus, it does not find one'. Switch it "
                "off at the stand, or pass disable_pfs=True (off is a safe "
                "direction -- it stops the servo, it does not move)."
            )
        self.require_motion("disabling PFS")
        if self.dry_run:
            self.log("  PFS: would disable (dry run)")
            return state
        self.core.enableContinuousFocus(False)
        try:
            self.core.waitForDevice("PFS")
        except Exception:
            pass
        after = self.pfs_state()
        if after.get("enabled"):
            raise FocusError("asked PFS to disable and it still reports enabled")
        self.log("  PFS: disabled")
        return after

    # ---- motion ----------------------------------------------------------

    def move_to(self, z_um: float, *, allow_ascent_um: float | None = None) -> float:
        """Command Z and verify it arrived. Returns the readback.

        ``allow_ascent_um`` caps how far this single move may go toward the
        sample. ``None`` means "no ascent at all beyond the tolerance" -- so a
        caller that wants to climb has to say how far, every time. Descending
        (retracting) is unrestricted: smaller Z is away from the sample.
        """
        self.require_motion(f"a Z move to {z_um:.3f} um")
        if z_um > self.z_ceiling_um:
            raise FocusError(
                f"refusing Z -> {z_um:.3f} um: above the ceiling "
                f"{self.z_ceiling_um:.3f} um. Increasing Z moves toward the sample."
            )
        if z_um < self.z_floor_um:
            raise FocusError(
                f"refusing Z -> {z_um:.3f} um: below the floor {self.z_floor_um:.3f} um"
            )

        here = self.position_um()
        ascent = z_um - here
        cap = self.arrival_tolerance_um if allow_ascent_um is None else allow_ascent_um
        if ascent > cap:
            raise FocusError(
                f"refusing Z {here:.3f} -> {z_um:.3f} um: that is {ascent:.3f} um "
                f"TOWARD the sample in one move, and this call allows "
                f"{cap:.3f} um. Approach in steps, from retracted."
            )

        if self.dry_run:
            self.log(f"    dry run: Z -> {z_um:.3f} um (from {here:.3f})")
            self.moves.append((z_um, float("nan")))
            return z_um

        self.core.setPosition(Z_DEVICE, z_um)
        self.core.waitForDevice(Z_DEVICE)
        landed = self.position_um()
        self.moves.append((z_um, landed))
        if abs(landed - z_um) > self.arrival_tolerance_um:
            raise FocusError(
                f"commanded Z {z_um:.3f} um, stage reports {landed:.3f} um "
                f"({landed - z_um:+.3f} um, tolerance "
                f"{self.arrival_tolerance_um:.3f}). Refusing to continue: a move "
                f"that did not arrive means a limit, a jam, or PFS servoing "
                f"underneath the sweep."
            )
        return landed

    # ---- the sweep -------------------------------------------------------

    def plan(self, z_center_um: float, half_range_um: float,
             step_um: float | None = None,
             emission_nm: float = DEFAULT_EMISSION_NM) -> ZSpan:
        return plan_span(
            self.objective_key, z_center_um, half_range_um, step_um,
            z_ceiling_um=self.z_ceiling_um, z_floor_um=self.z_floor_um,
            wd_fraction=self.wd_fraction, emission_nm=emission_nm,
        )

    def sweep(self, span: ZSpan, grab: Callable[[], object], *,
              score: Callable[[object], dict] | None = None,
              settle_s: float = 0.15) -> FocusCurve:
        """Walk ``span`` upward, scoring one frame per Z.

        ``grab`` returns a frame; ``score`` turns it into a dict carrying at
        least ``sharp``. The default score is
        ``detection.focus_metric.score_frame`` with no bead window -- right for
        an edge or a graticule, which is what a cross-objective fiducial
        usually is.
        """
        import time

        if score is None:
            from detection.focus_metric import score_frame

            def score(frame):  # noqa: E306 -- local default, deliberately narrow
                return score_frame(frame)

        self.log(f"  sweep: {span.describe()}")

        # Get to the low end of the span. From a retracted stage this is an
        # ASCENT, and often a long one -- the stand parks at Z ~ 0 and a sweep
        # of the sample window starts at 2800.
        #
        # It is permitted, and the bound that makes it safe is the span's own
        # ceiling rather than the step size. `plan_span` has already established
        # that every Z in [lo, hi] is below `min(absolute ceiling, centre + 0.4
        # x free working distance)`, and `lo` is the most retracted point of
        # that approved range. Stepping there in 0.2 um increments would not add
        # safety -- there is nothing to see below focus to stop for -- it would
        # just spend 14000 moves.
        #
        # This is also the operator's own documented sequence: SAFETY.md §2 ends
        # an objective change with a single `Z -> 2800`.
        here = self.position_um()
        if span.lo_um - here > self.arrival_tolerance_um:
            self.log(
                f"    approach: Z {here:.3f} -> {span.lo_um:.3f} um "
                f"({span.lo_um - here:+.1f} um toward the sample) to reach the "
                f"low end of the span; ceiling {span.ceiling_um:.3f} um "
                f"({span.ceiling_reason})"
            )
        self.move_to(span.lo_um, allow_ascent_um=max(0.0, span.lo_um - here))

        points: list[FocusPoint] = []
        for z in span.positions:
            # Each step is one `span.step_um` toward the sample and no more.
            landed = self.move_to(z, allow_ascent_um=span.step_um + self.arrival_tolerance_um)
            if settle_s:
                time.sleep(settle_s)
            diag = dict(score(grab()))
            points.append(FocusPoint(
                z_um=z, z_readback_um=landed,
                score=float(diag.get("sharp", 0.0)), diagnostics=diag,
            ))
        return FocusCurve(points=points, span=span)

    def autofocus(self, z_center_um: float, half_range_um: float,
                  grab: Callable[[], object], *,
                  coarse_step_um: float | None = None,
                  fine: bool = True,
                  fine_half_range_factor: float = 3.0,
                  score: Callable[[object], dict] | None = None,
                  settle_coarse_s: float = 0.05,
                  settle_fine_s: float = 0.20,
                  emission_nm: float = DEFAULT_EMISSION_NM,
                  ) -> tuple[FocusCurve, FocusCurve | None]:
        """Coarse sweep, then a fine sweep around its peak.

        Returns ``(coarse, fine_or_None)``. The fine pass is skipped -- and that
        is reported rather than silently patched over -- when the coarse curve
        has no interior peak, because a fine sweep centred on a bound is a fine
        sweep of the wrong place.

        **The two passes settle differently on purpose** (user, 2026-09-07: "you
        can go a little fast before PFS enable"). The coarse pass is looking for
        which side of focus it is on, and a 50 ms settle is enough for that; the
        fine pass is measuring a Z to report, so it waits long enough that the
        stage has stopped creeping into the frame it is about to score. Sweeping
        fast is safe here for a reason that is not about speed: PFS is off for
        both passes (``require_pfs_quiet``), so nothing is fighting the stage --
        PFS comes in afterwards, to HOLD the peak, via ``enable_pfs_hold``.
        """
        if coarse_step_um is None:
            # A coarse pass wants ~40 points across the range, floored at the
            # DOF-derived step so it never goes finer than useful.
            coarse_step_um = max(2.0 * half_range_um / 40.0,
                                 suggest_step_um(self.objective_key, emission_nm))
        coarse = self.sweep(
            self.plan(z_center_um, half_range_um, coarse_step_um, emission_nm),
            grab, score=score, settle_s=settle_coarse_s,
        )
        ok, why = coarse.verdict()
        self.log(f"  coarse: {why}")
        if not fine or not coarse.peak_interior:
            return coarse, None

        fine_half = fine_half_range_factor * coarse.span.step_um
        fine_curve = self.sweep(
            self.plan(coarse.peak_z_um, fine_half, None, emission_nm),
            grab, score=score, settle_s=settle_fine_s,
        )
        # MIN_CONTRAST_FINE, not the coarse bar -- a fine pass is flat by
        # construction. See that constant.
        self.log(f"  fine:   {fine_curve.verdict(MIN_CONTRAST_FINE)[1]}")
        return coarse, fine_curve

    def park_at(self, z_um: float) -> float:
        """Move to ``z_um``, approaching from below so it matches the sweep.

        The sweep measured every point on an ascent, so backlash sits in those
        numbers as an offset. Arriving at the peak from above would not cancel
        it -- it would apply it with the opposite sign. Retract a little first,
        then climb.
        """
        self.require_motion(f"parking at {z_um:.3f} um")
        backoff = max(2.0 * self.arrival_tolerance_um, 1.0)
        self.move_to(max(self.z_floor_um, z_um - backoff))
        return self.move_to(z_um, allow_ascent_um=backoff + self.arrival_tolerance_um)

    def enable_pfs_hold(self) -> dict:
        """Hand the found focus to PFS so it holds. **This commands motion.**

        Where the peak goes afterwards is the gap README to-do 6 names -- "handing
        it to PFS ... is currently the operator retyping a number". This closes
        it, and it is gated because enabling the servo is not a passive act: PFS
        drives Z to acquire its lock, so it is a stage move in a direction this
        call cannot predict. Only worth doing once ``best_z_um`` returned a Z and
        the stage is parked there.

        Returns the state afterwards. ``locked`` False is a real outcome, not an
        error: PFS needs the coverslip inside its capture range, and an objective
        it cannot use, or a plane too far off the glass, both fail to lock. It
        can veto; it can never permit (SAFETY.md §2.4).
        """
        self.require_motion("enabling PFS (the servo drives Z to acquire lock)")
        if self.dry_run:
            self.log("  PFS: would enable to hold focus (dry run)")
            return self.pfs_state()
        before = self.position_um()
        self.core.enableContinuousFocus(True)
        try:
            self.core.waitForDevice("PFS")
        except Exception:
            pass
        state = self.pfs_state()
        state["z_before_um"] = before
        state["z_after_um"] = self.position_um()
        moved = state["z_after_um"] - before
        self.log(
            f"  PFS: enabled={state.get('enabled')} locked={state.get('locked')} "
            f"in_range={state.get('in_range')!r}; acquiring the lock moved Z "
            f"{moved:+.3f} um"
        )
        return state


def best_z_um(coarse: FocusCurve, fine: FocusCurve | None) -> tuple[float | None, str]:
    """The Z to use, and the provenance string that says which pass gave it.

    The fine curve is judged against :data:`MIN_CONTRAST_FINE` and the coarse
    one against :data:`MIN_CONTRAST_COARSE`, which is the whole reason those are
    two constants: on 2026-09-07 a good 4x fine pass scored 1.09 and was thrown
    away against the coarse bar, so the answer fell back to the 10 um coarse
    grid when a 6.875 um refinement of it was sitting right there.
    """
    if fine is not None:
        ok, why = fine.verdict(MIN_CONTRAST_FINE)
        if ok:
            return fine.peak_z_um, f"fine pass: {why}"
    ok, why = coarse.verdict(MIN_CONTRAST_COARSE)
    if ok:
        return coarse.peak_z_um, f"coarse pass only: {why}"
    return None, f"no usable peak -- {why}"
