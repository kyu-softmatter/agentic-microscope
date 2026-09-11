"""Individual mechanical / environmental checks -- G31 (sedimentation),
G32 (evaporation).

docs/05-consensus-gate.md "Lens 8".

G29-G32 were new numbers (G1-G27 were taken by lenses 1-7). Lens 8 had no gate
IDs before it had an implementation.

THREE GATES HAVE LEFT THIS LENS, ALL ON 2026-09-10 (KH), AND NONE OF THE THREE
NUMBERS IS REUSED: G28 (PFS lock), G29 (axial drift), G30 (lateral drift).

G28 went first, to the hardware execution stage. It is not just a relocation:
the gate read `PFS in Range` as if it meant "the servo is holding", and
`hardware/focus.py::FocusAxis.pfs_state` records that that property reports
**the coverslip, not the servo** -- `In Range` is the normal reading for a
focused sample. The hardware stage asks MMCore's autofocus API instead
(`isContinuousFocusEnabled` / `isContinuousFocusLocked`), which is the actual
servo state. kb/decisions/2026-09-10-g28-moves-to-the-hardware-stage.md

G29 and G30 followed, for the reason that generalises G28's:

    "실험 중 측정해야한다면 디자인 요소로는 적합하지 않은듯"  -- KH, 2026-09-10
    (if it has to be measured during the experiment, it is not suitable as a
    design element)

A drift rate is learned from a run. Both drift rates ARE obtainable on this
instrument -- `config/session/focus_monitor.py` already samples ZDrive and both
cameras several times a second, and 8 of the 21 beads in `data/particles.yaml`
are stuck to the coverslip and serve as lateral fiducials -- but obtainable
*from the acquisition* is exactly the wrong timing for a gate that judges a
proposal. `compute.drops` is the precedent for where that work belongs: it
reads an acquisition that already ran, from its own timestamps, and does not
pretend to be a gate on a plan.
kb/decisions/2026-09-10-drift-is-not-a-design-element.md

What is left is what IS knowable before the run starts: what the sample does to
itself over time, from the particle, the medium and the chamber. Sedimentation
follows from particle size, density contrast and viscosity; evaporation from
the chamber. Vibration remains INFO -- no measurement channel is set up for it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .drift import (
    concentration_factor,
    evaporated_fraction,
    settling_distance_um,
)
from .setup import CONVENE_DURATION_MIN

if TYPE_CHECKING:
    from .setup import StabilitySetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    #: G31: settling over the acquisition, as a fraction of the depth of field.
    #: The population must stay in the plane it was characterised in.
    "settling_dof_fraction": 1.0,
    #: G32: fraction of sample volume that may evaporate before
    #: concentration-dependent quantities drift measurably. 5% evaporation is
    #: already a 5.3% concentration increase.
    "evaporated_fraction_max": 0.05,
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
    run: Callable[["StabilitySetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "StabilitySetup") -> set[str]:
    facts: set[str] = set()
    if setup.duration_min is not None:
        facts.add("duration")
    if setup.resolved_dof_um is not None:
        facts.add("depth_of_field")
    if setup.settling_velocity_um_per_s is not None:
        facts.add("settling_inputs")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_sedimentation(setup: "StabilitySetup") -> CheckResult:
    """G31: does the population stay in the plane it was characterised in?

    The one thing in this lens that needs no instrument measurement -- Stokes
    settling follows from particle size, density contrast and viscosity.
    """
    v = setup.settling_velocity_um_per_s
    dof = setup.resolved_dof_um
    distance = settling_distance_um(v, setup.duration_min)
    budget = LIMITS["settling_dof_fraction"] * dof
    margin = budget / abs(distance) if distance != 0 else MAX_MARGIN
    direction = "settles" if distance > 0 else "creams upward"

    numbers = {
        "settling_velocity_um_per_s": round(v, 6),
        "duration_min": setup.duration_min,
        "settling_distance_um": round(distance, 2),
        "depth_of_field_um": round(dof, 3),
        "budget_um": round(budget, 3),
        "chamber_height_um": setup.chamber_height_um,
    }

    if setup.chamber_height_um and abs(distance) >= setup.chamber_height_um:
        numbers["leaves_chamber"] = True

    if margin >= 1.0:
        return _ok(
            "stability.sedimentation",
            BIAS,
            margin,
            f"The population moves {abs(distance):.2f} um axially over "
            f"{setup.duration_min:.0f} min, inside a {dof:.2f} um depth of "
            "field.",
            **numbers,
        )

    extra = ""
    if numbers.get("leaves_chamber"):
        extra = (
            f" That exceeds the {setup.chamber_height_um:.0f} um chamber "
            "height, so the particles reach the wall and the bulk suspension "
            "is gone entirely."
        )

    return CheckResult(
        "stability.sedimentation",
        BIAS,
        margin,
        "warn",
        f"The population {direction} {abs(distance):.1f} um over "
        f"{setup.duration_min:.0f} min against a {dof:.2f} um depth of field "
        f"({abs(distance) / dof:.0f}x). What is in the focal plane at the end "
        f"is not the population that was there at the start, so any ensemble "
        f"average mixes two different samples.{extra}",
        action="Density-match the medium (this term vanishes at zero density "
        "contrast), use smaller particles — settling goes as radius squared — "
        "shorten the acquisition, or re-characterise the population at the end "
        "and treat the change as part of the measurement.",
        numbers=numbers,
    )


def check_evaporation(setup: "StabilitySetup") -> CheckResult:
    """G32: does the sample concentrate measurably during the acquisition?

    Evaporation is a bias, not an inconvenience: every concentration-dependent
    quantity drifts through the run even if focus is held perfectly.
    """
    numbers = {
        "chamber_sealed": setup.chamber_sealed,
        "duration_min": setup.duration_min,
    }

    if setup.chamber_sealed:
        return _ok(
            "stability.evaporation",
            BIAS,
            MAX_MARGIN,
            "Chamber sealed; no evaporative concentration.",
            **numbers,
        )

    rate = setup.evaporation_rate_ul_per_hour
    volume = setup.sample_volume_ul

    if rate is None or volume is None:
        if not setup.convenes:
            return _ok(
                "stability.evaporation",
                BIAS,
                MAX_MARGIN,
                f"Chamber unsealed but the acquisition is only "
                f"{setup.duration_min:.0f} min, under the "
                f"{CONVENE_DURATION_MIN:.0f} min where evaporation usually "
                "becomes measurable.",
                **numbers,
            )
        return CheckResult(
            "stability.evaporation",
            BIAS,
            0.5,
            "warn",
            f"Chamber is unsealed for a {setup.duration_min:.0f} min "
            "acquisition and no evaporation rate is on record, so the "
            "concentration drift cannot be quantified. Solvent leaving "
            "concentrates everything left behind.",
            action="Seal the chamber, or weigh an identical unsealed chamber "
            "before and after a run of this length to get a rate in uL/hour "
            "and supply it. This cannot be computed from the setting.",
            numbers=numbers,
        )

    frac = evaporated_fraction(rate, volume, setup.duration_min)
    factor = concentration_factor(frac)
    limit = LIMITS["evaporated_fraction_max"]
    margin = limit / frac if frac > 0 else MAX_MARGIN

    numbers.update(
        {
            "evaporation_rate_ul_per_hour": rate,
            "sample_volume_ul": volume,
            "evaporated_fraction": round(frac, 4),
            "concentration_factor": round(factor, 3)
            if math.isfinite(factor)
            else None,
            "limit": limit,
        }
    )

    if margin >= 1.0:
        return _ok(
            "stability.evaporation",
            BIAS,
            margin,
            f"About {frac * 100:.1f}% of the volume evaporates, concentrating "
            f"the sample {factor:.3f}x — inside the {limit * 100:.0f}% limit.",
            **numbers,
        )

    return CheckResult(
        "stability.evaporation",
        BIAS,
        margin,
        "warn",
        f"About {frac * 100:.1f}% of the volume evaporates over "
        f"{setup.duration_min:.0f} min, concentrating the sample "
        + (f"{factor:.2f}x" if math.isfinite(factor) else "without bound")
        + f", past the {limit * 100:.0f}% limit. Every "
        "concentration-dependent quantity drifts through the acquisition.",
        action="Seal the chamber, use an oil overlay, add a humidity reservoir, "
        "or shorten the acquisition.",
        numbers=numbers,
    )


def check_drift_budget(setup: "StabilitySetup") -> CheckResult:
    """Report the drift rate this run can tolerate. Not a gate; unnumbered.

    G29 and G30 stood here and gated on a MEASURED drift rate. They left on
    2026-09-10 because that number is learned from a run, not known before it
    (see the module docstring). What survives the move is the half of the
    question that IS answerable in advance: the plan's own duration and depth
    of field fix how much drift it can absorb, so instead of gating on a
    measurement that does not exist yet, this publishes the requirement the
    plan places on the instrument.

    The arithmetic is one division and carries no threshold -- the rate quoted
    is the one that walks the focus through exactly one depth of field over the
    acquisition. Any tolerance fraction scales it linearly: allow half a DOF
    and halve the rate.
    """
    dof_um = setup.resolved_dof_um
    duration = setup.duration_min

    if dof_um is None or duration is None or duration <= 0:
        return CheckResult(
            "stability.drift_budget",
            INFO,
            MAX_MARGIN,
            "info",
            "Cannot state a drift budget without both a depth of field and a "
            "duration. Drift itself is not gated here -- it is measured from "
            "the acquisition -- but the tolerance is a property of the plan "
            "and would be worth reporting.",
            action="Supply duration_min and the objective plus emission_nm "
            "(or depth_of_field_um) to get the budget.",
            numbers={},
        )

    dof_nm = dof_um * 1000.0
    rate_full_dof = dof_nm / duration

    return CheckResult(
        "stability.drift_budget",
        INFO,
        MAX_MARGIN,
        "info",
        f"Drift is not gated at planning time. This {duration:.0f} min run "
        f"against a {dof_um:.3f} um depth of field can absorb an axial drift "
        f"of {rate_full_dof:.1f} nm/min before the focus has walked one full "
        f"DOF -- {rate_full_dof / 2:.1f} nm/min for half of it. That is the "
        "requirement on the instrument; whether the instrument meets it is a "
        "measurement, and it is taken during the acquisition, not before.",
        action="Axial: config/session/focus_monitor.py already samples ZDrive "
        "and both cameras several times a second, so the rate falls out of the "
        "run's own focus scores. Lateral: data/particles.yaml records that most "
        "of the bead population is stuck to the coverslip, so a stuck bead in "
        "the same frames is the fiducial -- no extra acquisition either way. "
        "Judge both after the fact, like compute.drops does.",
        numbers={
            "duration_min": duration,
            "depth_of_field_um": dof_um,
            "axial_rate_for_one_dof_nm_per_min": round(rate_full_dof, 3),
            "axial_rate_for_half_dof_nm_per_min": round(rate_full_dof / 2, 3),
            "gated": False,
        },
    )


def check_vibration(setup: "StabilitySetup") -> CheckResult:
    """Report that vibration is not gated, rather than passing silently.

    docs/05 lists vibration and stage repeatability under lens 8, and neither
    has a measurement channel anywhere in the repo. Saying so is more useful
    than a gate built on a guessed amplitude.
    """
    if setup.vibration_measured:
        return _ok(
            "stability.vibration",
            INFO,
            MAX_MARGIN,
            "A vibration measurement was declared; this gate does not yet "
            "evaluate it.",
            vibration_measured=True,
        )

    return CheckResult(
        "stability.vibration",
        INFO,
        MAX_MARGIN,
        "info",
        "Vibration and stage repeatability are unmeasured and ungated. "
        "docs/05 assigns them to this lens, but there is no measurement "
        "channel for either, so nothing here evaluates them — a quiet pass on "
        "this line is an absence of evidence, not evidence of stability.",
        action="Measure the table's vibration spectrum, and the stage's "
        "repeatability if the acquisition is multipoint. Until then treat "
        "unexplained blur or position scatter as a live suspect.",
        numbers={"vibration_measured": False},
    )


def check_convening(setup: "StabilitySetup") -> CheckResult:
    """Report whether the committee would convene this lens at all.

    docs/01 §4 makes lens 8 conditional on acquisitions longer than 30 min.
    That threshold is reported, not enforced: sedimentation and drift scale
    continuously with time and do not switch on at 30 minutes. Whether to call
    this lens is the caller's decision; when called, it answers.
    """
    if setup.convenes:
        return _ok(
            "stability.convening",
            INFO,
            MAX_MARGIN,
            f"{setup.duration_min:.0f} min acquisition — past the "
            f"{CONVENE_DURATION_MIN:.0f} min threshold at which docs/01 §4 "
            "convenes this lens.",
            duration_min=setup.duration_min,
            convenes=True,
        )
    return _ok(
        "stability.convening",
        INFO,
        MAX_MARGIN,
        f"{setup.duration_min:.0f} min acquisition — under the "
        f"{CONVENE_DURATION_MIN:.0f} min threshold at which docs/01 §4 "
        "convenes this lens. The checks below still ran on their own merits.",
        duration_min=setup.duration_min,
        convenes=False,
    )


CHECKS: list[Check] = [
    Check("convening", INFO, ("duration",), check_convening),
    Check(
        "sedimentation",
        BIAS,
        ("duration", "depth_of_field", "settling_inputs"),
        check_sedimentation,
    ),
    Check("evaporation", BIAS, ("duration",), check_evaporation),
    Check("drift_budget", INFO, (), check_drift_budget),
    Check("vibration", INFO, (), check_vibration),
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
