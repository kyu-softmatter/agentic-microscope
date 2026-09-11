"""Lens 9's checks -- L9.1 (time base), L9.2 (displacement window),
L9.3 (steady state), L9.4 (Reynolds), L9.5 (time-axis owner).

docs/04-decision-engine.md §9; docs/05-consensus-gate.md "Lens 9".

**A new lens, 2026-09-11**, asked for by KH after the review found that nothing
in this repository records a commanded-versus-actual motion scale. The framing
is deliberately wider than the stage -- *"스테이지 속도라기보다는 시스템의
속도랄까?"* -- so it covers the piezo and the AOD trap together, and names lens
3 as the owner of the time axis rather than re-deriving it.

Why it earns a lens rather than a check somewhere else: a Stokes-drag
calibration multiplies the commanded velocity straight into
``kappa = gamma v / x_eq``, so an unverified velocity is an **unbounded scale
error on the measured stiffness** -- the same shape as the pixel-size error
docs/06 A1 is about, and nothing was guarding it.

⚠ `LIMITS` IS EMPTY AND STAYS EMPTY. Every bound here is derived from the
caller's own `target_relative_error` or from a limit the trap model states
about itself. A velocity window is meaningless without a stated precision, and
picking a multiple would be originating a physical number.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .kinematics import (
    equilibrium_offset_um,
    minimum_offset_um,
    reynolds_number,
    reynolds_unity_velocity_um_per_s,
    settling_time_constants,
    velocity_for_offset_um_per_s,
)

if TYPE_CHECKING:
    from .setup import VelocitySetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

#: EMPTY BY CONSTRUCTION -- see the module docstring. An entry here means
#: somebody has introduced a threshold that is not derived from the
#: experiment's precision target, which is a decision and not a refactor.
LIMITS: dict = {}


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
    run: Callable[["VelocitySetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    """A pass that rests on a FACT. Severity "info", not "ok".

    Written "info" from the start rather than inherited as "ok" and fixed
    later: every `gate.py` drops `severity == "ok"` from `findings`, and that
    turned into five separate invisible-computation defects across the other
    lenses in one review. A new lens does not get to repeat them.
    kb/decisions/2026-09-11-a-pass-that-decides-must-be-visible.md
    """
    return CheckResult(code, kind, margin, "info", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "VelocitySetup") -> set[str]:
    facts: set[str] = set()
    if setup.commanded_velocity_um_per_s is not None:
        facts.add("velocity")
    if setup.resolved_drag_pn_s_per_um is not None:
        facts.add("drag")
    if setup.stiffness_pn_per_um:
        facts.add("stiffness")
    if setup.localization_sigma_nm:
        facts.add("localization")
    if setup.target_relative_error is not None:
        facts.add("target_error")
    if setup.step_duration_ms is not None:
        facts.add("step_duration")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_time_base(setup: "VelocitySetup") -> CheckResult:
    """L9.1: has a commanded um/s ever been shown to be the um/s that happens?

    **This is the gate the lens was created for, and it BLOCKS today.**

    Read the asymmetry carefully, because half of this is settled and half is
    not. A velocity is a distance over a time.

    * **The distance half is corroborated.** On 2026-09-03 two independent
      length standards were driven 10 um and read off the camera: the
      closed-loop piezo gave 0.06460 um/px and the AOD trap 0.06445, agreeing
      to **0.24 %** (`data/pixel_size.yaml`, 100x row).
    * **The time half has never been checked.** Nothing in `kb/`, `data/`,
      `config/`, `hardware/` or `calibration/` records a commanded-versus-actual
      velocity (verified 2026-09-11).

    And it matters exactly as much as the pixel size does: a Stokes-drag
    calibration computes ``kappa = gamma v / x_eq`` from the COMMANDED v, so an
    unverified time base is an unbounded multiplicative error on kappa -- and
    like a wrong pixel size (docs/06 A1) it leaves a perfectly reasonable
    number behind.

    ⚠ **A closed loop is not an answer.** The controller holds its own scale;
    whether that scale is seconds is the question.
    """
    numbers = {
        "driver": setup.driver,
        "verified": setup.velocity_time_base_verified,
        "scale_ratio": setup.velocity_scale_ratio,
        "distance_half": "corroborated to 0.24% over 10 um, 2026-09-03",
    }

    if setup.velocity_time_base_verified:
        ratio = setup.velocity_scale_ratio
        if ratio is None:
            return CheckResult(
                "velocity.time_base",
                HARD,
                MAX_MARGIN,
                "info",
                "Velocity time base declared verified, but no measured "
                "actual/commanded ratio was supplied -- so the verdict rests "
                "on the declaration and not on a number.",
                action="Supply velocity_scale_ratio. A declaration with no "
                "ratio cannot be re-checked by anyone downstream.",
                numbers=numbers,
            )
        return _ok(
            "velocity.time_base",
            HARD,
            MAX_MARGIN,
            f"Velocity time base measured: actual/commanded = {ratio:.4f}. "
            f"Every velocity below is the commanded one; multiply by "
            f"{ratio:.4f} for the delivered one.",
            **numbers,
        )

    return CheckResult(
        "velocity.time_base",
        HARD,
        0.0,
        "fail",
        "No commanded-versus-actual velocity on record anywhere in this "
        "repository. The DISTANCE half of the scale is corroborated -- two "
        "length standards over 10 um agreeing to 0.24 % on 2026-09-03 -- but "
        "the TIME half has never been checked, and a Stokes-drag calibration "
        "multiplies the commanded velocity straight into kappa = gamma*v/x_eq. "
        "An unverified time base is an unbounded scale error on the measured "
        "stiffness, and it leaves a reasonable-looking number behind "
        "(the same failure docs/06 A1 describes for pixel size).",
        action="Measure it: command a constant velocity over a known "
        "displacement and time the traverse against the camera's own frame "
        "timestamps, not against the controller's clock -- the controller's "
        "clock is what is in question. Record it in kb/calibrations/ and set "
        "velocity_time_base_verified with velocity_scale_ratio. A closed-loop "
        "controller reporting position does NOT settle this.",
        numbers=numbers,
    )


def check_displacement_window(setup: "VelocitySetup") -> CheckResult:
    """L9.2: does the commanded velocity put the bead where it can be measured?

    The headline output of this lens: a **velocity window**, both ends derived.

        x_eq   = gamma v / kappa
        floor  = sigma / target        (dkappa/kappa = dx/x_eq)
        ceiling: |x_eq| < bead radius  -- the trap model's own stated limit

    Neither end is a chosen constant. The floor falls out of the precision the
    experiment asked for; the ceiling is where `trapping.goa.trap_force`
    refuses, because past the bead radius "the focus would fall outside the
    bead, which this model does not cover".

    ⚠ **The ceiling is generous and the report says so.** Linearity departs
    long before the focus leaves the bead: on the GOA curve for a 5 um
    polystyrene bead the force is 1.5 % above the linear extrapolation at
    20 % of the radius and 6.5 % at 40 %. So the window's upper end is a hard
    bound, not a recommendation, and the departure at the proposed offset is
    reported next to it.

    One bias rides along and is not corrected here: `gamma` is the unbounded
    Stokes drag, and lens 4's L4.4 bounds the near-wall inflation and
    deliberately does not correct it. A velocity chosen from this window
    inherits that, which is why L4.4 reaches lens 6's ledger.
    """
    v = setup.commanded_velocity_um_per_s
    gamma = setup.resolved_drag_pn_s_per_um
    kappa = setup.stiffness_pn_per_um
    sigma = setup.localization_sigma_nm
    target = setup.target_relative_error
    a = setup.particle_radius_um

    x_eq = equilibrium_offset_um(v, gamma, kappa)
    x_min = minimum_offset_um(sigma, target)
    v_min = velocity_for_offset_um_per_s(x_min, gamma, kappa)
    v_max = velocity_for_offset_um_per_s(a, gamma, kappa)

    numbers = {
        "commanded_velocity_um_per_s": v,
        "equilibrium_offset_nm": round(x_eq * 1000, 2),
        "offset_floor_nm": round(x_min * 1000, 2),
        "offset_ceiling_nm": round(a * 1000, 2),
        "velocity_window_um_per_s": [round(v_min, 3), round(v_max, 3)],
        "localization_sigma_nm": sigma,
        "target_relative_error": target,
        "implied_relative_error": round(sigma / (x_eq * 1000), 4) if x_eq else None,
        "offset_as_fraction_of_radius": round(x_eq / a, 4),
    }

    if x_eq < x_min:
        return CheckResult(
            "velocity.displacement_window",
            HARD,
            x_eq / x_min,
            "fail",
            f"{v:.3g} um/s puts the bead {x_eq * 1000:.1f} nm off centre, "
            f"below the {x_min * 1000:.0f} nm a {target:.0%} target on kappa "
            f"needs against a {sigma:.1f} nm localization sigma -- so the "
            f"measurement would carry {sigma / (x_eq * 1000):.1%} instead. "
            f"Raise the velocity to at least {v_min:.2f} um/s.",
            action=f"Usable window {v_min:.2f}-{v_max:.1f} um/s. Raising the "
            "velocity is the free lever; the alternatives are a smaller "
            "localization sigma (lens 2: more photons or a finer pixel) or a "
            "weaker trap, since the offset goes as 1/kappa.",
            numbers=numbers,
        )

    if x_eq >= a:
        return CheckResult(
            "velocity.displacement_window",
            HARD,
            a / x_eq,
            "fail",
            f"{v:.3g} um/s drives the bead {x_eq * 1000:.0f} nm off centre, "
            f"past its own {a * 1000:.0f} nm radius. The trap model does not "
            "cover that -- `trap_force` refuses, because the focus would fall "
            "outside the bead -- and in practice the bead escapes.",
            action=f"Usable window {v_min:.2f}-{v_max:.1f} um/s, and stay well "
            "inside the top: linearity departs from the GOA curve by a few "
            "percent by 20-40 % of the radius, long before the focus leaves "
            "the bead.",
            numbers=numbers,
        )

    return _ok(
        "velocity.displacement_window",
        HARD,
        min(x_eq / x_min, a / x_eq),
        f"{v:.3g} um/s puts the bead {x_eq * 1000:.1f} nm off centre "
        f"({x_eq / a:.1%} of its radius), inside the "
        f"{x_min * 1000:.0f}-{a * 1000:.0f} nm usable band -- so kappa comes "
        f"out at {sigma / (x_eq * 1000):.2%} against a {target:.0%} target. "
        f"Window {v_min:.2f}-{v_max:.1f} um/s.",
        **numbers,
    )


def check_steady_state(setup: "VelocitySetup") -> CheckResult:
    """L9.3: does the velocity step last long enough for the offset to arrive?

        n = ln(1 / target)        residual after n tau is e^-n
        tau = gamma / kappa

    Derived again: 5 % needs 3.0 tau, 2 % needs 3.9. **No "about five time
    constants" appears anywhere in this lens**, because the number the
    experiment actually needs follows from the precision it asked for.

    Reports the requirement in frames as well as ms, since that is the unit the
    acquisition is planned in -- and that conversion is the one place this lens
    touches the time axis, which lens 3's L3.2 owns. See L9.5.
    """
    target = setup.target_relative_error
    tau_ms = setup.relaxation_time_ms
    n = settling_time_constants(target)
    need_ms = n * tau_ms
    have_ms = setup.step_duration_ms

    numbers = {
        "relaxation_time_ms": round(tau_ms, 4),
        "time_constants_needed": round(n, 3),
        "step_duration_required_ms": round(need_ms, 3),
        "step_duration_ms": have_ms,
        "target_relative_error": target,
    }
    if setup.achieved_fps:
        numbers["frames_required"] = math.ceil(need_ms / 1000 * setup.achieved_fps)
        numbers["frames_available"] = math.floor(have_ms / 1000 * setup.achieved_fps)

    frames = (
        f" That is {numbers['frames_required']} frames at "
        f"{setup.achieved_fps:.0f} fps."
        if setup.achieved_fps
        else " Supply achieved_fps to get this in frames."
    )

    if have_ms < need_ms:
        return CheckResult(
            "velocity.steady_state",
            HARD,
            0.0 if need_ms <= 0 else have_ms / need_ms,
            "fail",
            f"A {have_ms:.1f} ms step is shorter than the {need_ms:.1f} ms "
            f"({n:.2f} tau, tau = {tau_ms:.1f} ms) the offset needs to come "
            f"within {target:.0%} of its steady value, so the displacement "
            f"read out is smaller than the real one and kappa comes out too "
            f"large.{frames}",
            action=f"Lengthen the step to at least {need_ms:.0f} ms, or accept "
            f"a residual of {math.exp(-have_ms / tau_ms):.1%} and report it as "
            "a bias. Shortening tau means a stiffer trap (lens 7), which also "
            "shrinks the offset -- the two levers pull against each other.",
            numbers=numbers,
        )

    return _ok(
        "velocity.steady_state",
        HARD,
        have_ms / need_ms,
        f"A {have_ms:.1f} ms step covers the {need_ms:.1f} ms ({n:.2f} tau) "
        f"the offset needs to arrive within {target:.0%}; the residual is "
        f"{math.exp(-have_ms / tau_ms):.2%}.{frames}",
        **numbers,
    )


def check_reynolds(setup: "VelocitySetup") -> CheckResult:
    """L9.4: is Stokes drag applicable at this velocity? Reports, never gates.

    ``Re = rho v a / eta``, and Stokes drag wants ``Re << 1``. It is INFO here
    on a computed argument rather than a guess: ``Re = 1`` for a 2.5 um bead in
    water needs about **4e5 um/s**, four orders of magnitude above anything the
    piezo or the AOD will produce. A gate that cannot fire is worse than a
    number stated once, so this states the number.

    It is not unconditional, though -- the margin to Re = 1 is reported, so a
    smaller particle in a less viscous medium would show up here rather than
    being assumed away.
    """
    v = setup.commanded_velocity_um_per_s
    a = setup.particle_radius_um
    eta = setup.viscosity_pa_s
    re = reynolds_number(v, a, eta)
    v_unity = reynolds_unity_velocity_um_per_s(a, eta)

    return _ok(
        "velocity.reynolds",
        INFO,
        MAX_MARGIN,
        f"Re = {re:.2e} at {v:.3g} um/s, so Stokes drag applies with enormous "
        f"margin: Re reaches 1 only at {v_unity:.3g} um/s, {v_unity / v:.0f}x "
        "this velocity. Ungated on that argument rather than assumed.",
        reynolds=float(f"{re:.4g}"),
        reynolds_unity_velocity_um_per_s=float(f"{v_unity:.5g}"),
        headroom=float(f"{v_unity / v:.4g}"),
    )


def check_time_axis_owner(setup: "VelocitySetup") -> CheckResult:
    """L9.5: name who owns the time axis, and what this lens inherits from it.

    A velocity is distance over time, and this lens does **not** own the time
    axis: lens 3's L3.2 (`fps_provenance`) judges whether a frame rate is
    achieved or merely requested, and lens 2 owns the rate itself. Re-deriving
    either here would double-charge them.

    What this reports is the inheritance, which was otherwise invisible. L9.3
    converts its requirement into frames, so a requested-but-not-achieved rate
    makes the frame count wrong in the direction that looks safe. And lens 3's
    three `fps_provenance.*` codes reach lens 6's bias ledger **registered
    nowhere** (`python -m committee.cli reconcile`), so no table says whether a
    frame-period error is correctable after the fact.
    """
    fps = setup.achieved_fps
    numbers = {"achieved_fps": fps, "time_axis_owner": "lens 3, L3.2 fps_provenance"}
    if fps is None:
        return _ok(
            "velocity.time_axis_owner",
            INFO,
            MAX_MARGIN,
            "No frame rate supplied, so L9.3's requirement is in ms only. The "
            "time axis belongs to lens 3 (L3.2 fps_provenance) and lens 2; "
            "this lens consumes it and does not re-derive it.",
            **numbers,
        )
    return _ok(
        "velocity.time_axis_owner",
        INFO,
        MAX_MARGIN,
        f"Step durations are expressed in frames at {fps:.0f} fps, which makes "
        "them only as good as lens 3's L3.2 verdict on whether that rate is "
        "achieved or requested. A requested rate biases the frame count in the "
        "direction that looks safe. Lens 3's fps_provenance codes are in "
        "neither of lens 6's correction registries, so nothing says whether a "
        "frame-period error can be corrected afterwards.",
        **numbers,
    )


CHECKS: list[Check] = [
    Check("time_base", HARD, (), check_time_base),
    Check(
        "displacement_window",
        HARD,
        ("velocity", "drag", "stiffness", "localization", "target_error"),
        check_displacement_window,
    ),
    Check(
        "steady_state",
        HARD,
        ("drag", "stiffness", "target_error", "step_duration"),
        check_steady_state,
    ),
    Check("reynolds", INFO, ("velocity", "drag"), check_reynolds),
    Check("time_axis_owner", INFO, (), check_time_axis_owner),
]


# --------------------------------------------------------------------------
# Feasibility grading -- identical scale to every other lens
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


GRADE_ORDER: tuple[str, ...] = tuple(name for _, name in reversed(GRADES))


def meets_grade(feasibility: str, minimum: str = "TIGHT") -> bool:
    if feasibility not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(feasibility) >= GRADE_ORDER.index(minimum)
