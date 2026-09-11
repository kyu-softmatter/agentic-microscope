"""Photo-perturbation REPORTS -- light-driving, total dose, trap heating.

⚠ **THIS IS NOT A JUDGING LENS ANY MORE (KH, 2026-09-10).** Every check here
is `INFO`: it reports, it does not grade, and it cannot block. `G21` and `G22`
are vacant alongside `G10` and `G20`, because in this repository a gate number
means "this can fail and stop or bias the result", and nothing here can.
kb/decisions/2026-09-10-lens-5-becomes-a-reporting-section.md

Why: two things the illumination numbers cannot see. Samples get radical
scavengers and other mitigations that change the answer without changing the
irradiance, and often there is no sample information at all -- and warning on
the absence of information made "we do not know" block a verdict. Reporting
what the light does, and letting the operator judge it against a sample they
know and the gate does not, is the honest division.
docs/04-decision-engine.md §5; docs/05-consensus-gate.md "Lens 5";
docs/06-pitfalls.md D2, D3.

TWO GATES HAVE BEEN REMOVED FROM THIS LENS AND NEITHER NUMBER IS REUSED.
G10 (photobleaching) went on 2026-09-09 --
kb/decisions/2026-09-09-g10-photobleaching-removed.md. G20 (saturation /
triplet shelving) went the same day, for the same reason one step further on --
kb/decisions/2026-09-09-g20-saturation-removed.md. Both computed against
per-dye constants that are empty for every dye in data/fluorophores.yaml, so
both had exactly one answer. G21 and G22 need no dye constant and remain.

Mirrors optics.checks / detection.checks / compute.checks / trapping.checks /
sample.checks: independent margins (achieved / required), never booleans.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dose import (
    duty_cycle,
    total_dose_j_cm2,
    total_illuminated_time_s,
)

if TYPE_CHECKING:
    from .setup import IlluminationSetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

#: Empty since 2026-09-09. This lens's only numeric threshold belonged to G20
#: and went with it; G21 compares against a per-sample measured threshold and
#: G22 against a caller-supplied ceiling, so neither has a constant to keep
#: here. The name stays because every lens exports one and `photo.LIMITS` is
#: part of that shape.
LIMITS: dict[str, float] = {}


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
    run: Callable[["IlluminationSetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    """Severity "info", not "ok" -- this is a reporting section.

    `photo/gate.py` drops severity "ok" from `findings`, so `_ok` used to mean
    "compute this and then throw it away". That cost the dose number every
    time: `check_total_dose`'s docstring says it "always reports the number"
    and the no-ceiling branch -- the only branch that ever runs, since no dye
    or bead here has a dose ceiling -- discarded it into `metrics`. Ungraded
    and invisible are different things, and only the first was intended
    (2026-09-10, the same correction made in sample/checks.py's L4.4).
    """
    return CheckResult(code, kind, margin, "info", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "IlluminationSetup") -> set[str]:
    facts: set[str] = set()
    if setup.resolved_irradiance is not None:
        facts.add("irradiance")
    if setup.resolved_emitted_per_s is not None:
        facts.add("emitted_rate")
    if setup.exposure_ms is not None and setup.n_frames is not None:
        facts.add("exposure_plan")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_light_driving(setup: "IlluminationSetup") -> CheckResult:
    """L5.1: Is the illumination driving the sample rather than measuring it?

    docs/06 D2. This is lens 5's reason to exist -- lens 1 says raise the light
    for SNR, and this is the only lens that can answer "that ruins the
    experiment".

    Three answers, not two. ``photoresponsive`` is ``None`` until somebody
    says, and that state warns rather than passing: a default of "no" would
    make the gate silent in exactly the case docs/06 D2 is about. A confirmed
    "yes" with no measured threshold BLOCKs in Phase 0 rather than being
    compared against a guess.
    """
    irradiance = setup.resolved_irradiance

    if setup.photoresponsive is None:
        return CheckResult(
            "perturbation.light_driving",
            INFO,
            MAX_MARGIN,
            "warn",
            "Nobody has said whether this sample responds to light, so "
            f"{irradiance:.1f} W/cm^2 is unevaluated, not cleared. docs/06 D2's "
            "accident is the unasked question rather than a wrong number: "
            "light-driven colloids, photo-crosslinking and LC photo-alignment "
            "all look like ordinary imaging until someone checks. Recorded as "
            "unconfirmed, which keeps this verdict from advancing. The margin "
            "below is not a judgement -- there is nothing yet to judge.",
            action="Answer the question: is this particle/molecule "
            "photoresponsive at this wavelength? A confirmed no clears the "
            "check (photoresponsive=False). A yes needs "
            "light_driving_threshold_w_cm2 from a control experiment -- vary "
            "the light level with everything else fixed and find where the "
            "behaviour changes. I do not know is a valid answer too, and "
            "leaves this warning standing.",
            numbers={
                "irradiance_w_cm2": round(irradiance, 2),
                "photoresponsive": None,
                "evaluated": False,
            },
        )

    if not setup.photoresponsive:
        return _ok(
            "perturbation.light_driving",
            INFO,
            MAX_MARGIN,
            f"Sample confirmed not photoresponsive; {irradiance:.1f} W/cm^2 is "
            "treated as measurement light only.",
            irradiance_w_cm2=round(irradiance, 2),
            photoresponsive=False,
            evaluated=True,
        )

    threshold = setup.light_driving_threshold_w_cm2
    margin = threshold / irradiance if irradiance > 0 else MAX_MARGIN
    numbers = {
        "irradiance_w_cm2": round(irradiance, 2),
        "threshold_w_cm2": threshold,
        "photoresponsive": True,
        "evaluated": True,
    }

    if margin >= 1.0:
        return _ok(
            "perturbation.light_driving",
            INFO,
            margin,
            f"{irradiance:.1f} W/cm^2 stays under the {threshold:.1f} W/cm^2 "
            "at which this sample starts responding to the light.",
            **numbers,
        )

    return CheckResult(
        "perturbation.light_driving",
        INFO,
        margin,
        "warn",
        f"{irradiance:.1f} W/cm^2 exceeds the {threshold:.1f} W/cm^2 at which "
        "this sample responds to light. The illumination is an experimental "
        "variable here, not a measurement tool: what is being observed is "
        "partly the light's own effect.",
        action="Drop the light level below the threshold and recover SNR some "
        "other way (longer exposure, brighter label, higher-NA objective, "
        "binning), or state explicitly that light-driving is the intended "
        "condition. Do not raise the level to fix SNR and leave this "
        "unresolved.",
        numbers=numbers,
    )


def check_total_dose(setup: "IlluminationSetup") -> CheckResult:
    """L5.2: Accumulated energy per unit area, and the duty cycle that sets it.

    INFO, because a dose ceiling is sample-specific: without one supplied there
    is nothing to gate against, and inventing a limit would be exactly the
    guessing this project refuses. What it always does is report the number.
    """
    irradiance = setup.resolved_irradiance
    if irradiance is None or setup.exposure_ms is None or setup.n_frames is None:
        return _ok(
            "perturbation.total_dose",
            INFO,
            MAX_MARGIN,
            "Total dose not evaluated (needs irradiance and an exposure plan).",
            evaluated=False,
        )

    dose = total_dose_j_cm2(irradiance, setup.exposure_ms, setup.n_frames)
    duty = duty_cycle(setup.exposure_ms, setup.frame_interval_ms)
    numbers = {
        "total_dose_j_cm2": round(dose, 3),
        "irradiance_w_cm2": round(irradiance, 2),
        "illuminated_time_s": round(
            total_illuminated_time_s(setup.exposure_ms, setup.n_frames), 4
        ),
        "duty_cycle": round(duty, 4) if duty is not None else None,
        "evaluated": True,
    }

    duty_note = (
        f" Duty cycle {duty * 100:.1f}%." if duty is not None else ""
    )

    if setup.dose_limit_j_cm2 is None:
        return _ok(
            "perturbation.total_dose",
            INFO,
            MAX_MARGIN,
            f"Total dose {dose:.2f} J/cm^2 over {setup.n_frames} frames."
            + duty_note
            + " No dose ceiling supplied, so this is reported, not gated.",
            **numbers,
        )

    margin = setup.dose_limit_j_cm2 / dose if dose > 0 else MAX_MARGIN
    numbers["dose_limit_j_cm2"] = setup.dose_limit_j_cm2

    if margin >= 1.0:
        return _ok(
            "perturbation.total_dose",
            INFO,
            margin,
            f"Total dose {dose:.2f} J/cm^2 is within the "
            f"{setup.dose_limit_j_cm2:.2f} J/cm^2 ceiling." + duty_note,
            **numbers,
        )

    return CheckResult(
        "perturbation.total_dose",
        INFO,
        margin,
        "warn",
        f"Total dose {dose:.2f} J/cm^2 exceeds the stated "
        f"{setup.dose_limit_j_cm2:.2f} J/cm^2 ceiling." + duty_note,
        action="Reduce the light level, the exposure, or the frame count; or "
        "lower the duty cycle by spacing frames further apart.",
        numbers=numbers,
    )


def check_trap_heating_ownership(setup: "IlluminationSetup") -> CheckResult:
    """L5.3: Refuse to let the 5 -> 7 handoff for trap heating vanish silently.

    docs/06 D6 assigns 1064 nm trap heating to lens 7, which does not implement
    it (`trapping/` has confinement, trap_depth, sampling only) and **will not**
    -- ungated by decision, user 2026-08-19, kb/decisions/2026-08-19-lens-7-scope.md.
    Lens 5 does not own it either; it covers visible excitation light.

    So this is a named ungated risk rather than an oversight, and the point of
    reporting it here is that a named risk still has to reach whoever reads the
    verdict. Silence would let the reader assume some lens had it.
    """
    if not setup.trap_on:
        return _ok(
            "perturbation.trap_heating_unowned",
            INFO,
            MAX_MARGIN,
            "Tweezers not in use; trap heating does not apply.",
            trap_on=False,
        )

    base = (
        "The 1064 nm trap is on and its local heating is ungated by decision "
        "(2026-08-19): docs/06 D6 assigns it to lens 7, which has no heating "
        "check and is not getting one, and lens 5 covers visible excitation "
        "light only. Water absorbs strongly at 1064 nm, so the trap warms the "
        "medium at its focus. Named, not caught."
    )
    numbers = {"trap_on": True, "temperature_sensitive": setup.temperature_sensitive}

    if setup.temperature_sensitive:
        return CheckResult(
            "perturbation.trap_heating_unowned",
            INFO,
            MAX_MARGIN,
            "info",
            base + " ⚠ AND THIS SAMPLE IS DECLARED TEMPERATURE-SENSITIVE, "
            "which changes what is at stake. For a liquid crystal near a "
            "clearing point, an ATPS near a phase boundary, or a gel near its "
            "gel point, trap heating does not bias a number -- it can move "
            "the sample across the transition, at the focus, exactly where "
            "the measurement is. Nothing in the committee sees that: G21 "
            "covers light-DRIVING through the visible line, which is a "
            "different wavelength and a different mechanism from thermal.",
            action="Treat this as a first-order design constraint, not a "
            "footnote. Bracket the trap power against the transition (hold a "
            "particle at reducing power and watch for the boundary moving), "
            "or work far enough below the transition that the unquantified "
            "heating cannot reach it. Declaring the sensitivity does not "
            "clear it -- no lens computes the temperature rise.",
            numbers=numbers,
        )

    tail = (
        " That changes viscosity and therefore D, so any microrheology result "
        "from this configuration may be contaminated."
    )
    if setup.temperature_sensitive is None:
        tail += (
            " ⚠ And nobody has said whether this sample has a "
            "temperature-sensitive state -- a liquid-crystal transition, an "
            "ATPS phase boundary, a gel point. For those the trap can move "
            "the sample across a boundary rather than merely biasing a "
            "viscosity, so the answer changes how much this matters. "
            "Unasked, not cleared."
        )

    return CheckResult(
        "perturbation.trap_heating_unowned",
        INFO,
        MAX_MARGIN,
        "info",
        base + tail,
        action="Treat the medium temperature near the trap as the experiment's "
        "assumption, not the gate's. Before trusting a diffusion or viscosity "
        "number from this setup, quantify the heating separately or show it is "
        "small at this power. No lens computes it. If the sample has a "
        "temperature-sensitive state, say so (temperature_sensitive=True) and "
        "read this notice again -- it says something stronger.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    # All INFO since 2026-09-10 -- see the module docstring. BIAS is still
    # imported because the severity vocabulary is shared, but no check uses it.
    Check("light_driving", INFO, ("irradiance",), check_light_driving),
    Check("total_dose", INFO, (), check_total_dose),
    Check("trap_heating", INFO, (), check_trap_heating_ownership),
]


# --------------------------------------------------------------------------
# Feasibility grading
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
