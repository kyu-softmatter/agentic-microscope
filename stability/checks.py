"""Individual mechanical / environmental checks -- G28 (PFS lock), G29 (axial
drift), G30 (lateral drift), G31 (sedimentation), G32 (evaporation).

docs/05-consensus-gate.md "Lens 8"; docs/06-pitfalls.md D7.

G28-G32 are new numbers (G1-G27 were taken by lenses 1-7). Lens 8 had no gate
IDs because it had no implementation.

Most of what this lens owns needs a measurement nobody has taken: there is no
drift rate, no vibration spectrum and no stage-repeatability figure anywhere in
the repo. Those gates BLOCK, and naming the missing measurement is the useful
output. Sedimentation is the exception -- it follows from particle size, density
contrast and viscosity.
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
    total_drift_nm,
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
    #: G29: accumulated axial drift must stay inside this fraction of the depth
    #: of field. Half, because drift eats the focus budget from one side while
    #: the sample's own thickness eats it from the other.
    "axial_drift_dof_fraction": 0.5,
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
    if setup.axial_drift_rate_nm_per_min is not None:
        facts.add("axial_drift_rate")
    if setup.settling_velocity_um_per_s is not None:
        facts.add("settling_inputs")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_pfs_lock(setup: "StabilitySetup") -> CheckResult:
    """G28: was focus maintenance on AND actually locked? docs/06 D7.

    The archive contains sessions with `PFS-FocusMaintenance: On` but
    `PFS in Range: Out of Range`. Recording only the on state cannot tell you
    whether focus was held, so an unrecorded range flag is itself the finding.

    Fully computable with no new measurement -- it is a state check on metadata
    that already exists.
    """
    numbers = {
        "pfs_enabled": setup.pfs_enabled,
        "pfs_in_range": setup.pfs_in_range,
        "duration_min": setup.duration_min,
    }

    if setup.pfs_enabled is None:
        return CheckResult(
            "stability.pfs_lock",
            HARD,
            0.0,
            "fail",
            "Focus-maintenance state was not recorded, so whether focus was "
            "held over the acquisition is unknown.",
            action="Record both `PFS-FocusMaintenance` and `PFS in Range`. "
            "docs/06 D7: both, not just the first.",
            numbers=numbers,
        )

    if not setup.pfs_enabled:
        if not setup.convenes:
            return _ok(
                "stability.pfs_lock",
                HARD,
                MAX_MARGIN,
                f"Focus maintenance off, but the acquisition is "
                f"{setup.duration_min:.0f} min — under the "
                f"{CONVENE_DURATION_MIN:.0f} min where drift usually forces it.",
                **numbers,
            )
        return CheckResult(
            "stability.pfs_lock",
            HARD,
            0.0,
            "fail",
            f"Focus maintenance is off for a {setup.duration_min:.0f} min "
            "acquisition. Nothing is holding the focal plane against thermal "
            "drift for that long.",
            action="Turn PFS on and confirm it reports In Range, or "
            "demonstrate with a measured drift rate that focus holds without "
            "it.",
            numbers=numbers,
        )

    if setup.pfs_in_range is None:
        return CheckResult(
            "stability.pfs_lock",
            HARD,
            0.0,
            "fail",
            "Focus maintenance is on but `PFS in Range` was not recorded. "
            "PFS can be on without being locked — this is exactly the case "
            "docs/06 D7 found in the archive, and the on state alone does not "
            "distinguish it.",
            action="Record `PFS in Range` alongside "
            "`PFS-FocusMaintenance`. Without it a session cannot be told apart "
            "from one where focus silently wandered.",
            numbers=numbers,
        )

    if not setup.pfs_in_range:
        return CheckResult(
            "stability.pfs_lock",
            HARD,
            0.0,
            "fail",
            "Focus maintenance is on but reports Out of Range: the loop is "
            "enabled and not holding. Focus was not maintained.",
            action="Re-establish the PFS offset within range before "
            "acquiring. Data already taken in this state has an unknown focal "
            "plane.",
            numbers=numbers,
        )

    return _ok(
        "stability.pfs_lock",
        HARD,
        MAX_MARGIN,
        "Focus maintenance is on and reports In Range; both flags recorded.",
        **numbers,
    )


def check_axial_drift(setup: "StabilitySetup") -> CheckResult:
    """G29: does accumulated axial drift stay inside the depth of field?"""
    dof = setup.resolved_dof_um
    drift_um = total_drift_nm(
        setup.axial_drift_rate_nm_per_min, setup.duration_min
    ) / 1000.0
    budget = LIMITS["axial_drift_dof_fraction"] * dof
    margin = budget / drift_um if drift_um > 0 else MAX_MARGIN

    numbers = {
        "axial_drift_rate_nm_per_min": setup.axial_drift_rate_nm_per_min,
        "duration_min": setup.duration_min,
        "total_drift_um": round(drift_um, 3),
        "depth_of_field_um": round(dof, 3),
        "budget_um": round(budget, 3),
    }

    if margin >= 1.0:
        return _ok(
            "stability.axial_drift",
            HARD,
            margin,
            f"Axial drift totals {drift_um:.2f} um over "
            f"{setup.duration_min:.0f} min, inside the {budget:.2f} um budget "
            f"(half of a {dof:.2f} um depth of field).",
            **numbers,
        )

    return CheckResult(
        "stability.axial_drift",
        HARD,
        margin,
        "fail",
        f"Axial drift totals {drift_um:.2f} um over "
        f"{setup.duration_min:.0f} min, past the {budget:.2f} um budget for a "
        f"{dof:.2f} um depth of field. The focal plane leaves the sample "
        "during the acquisition.",
        action="Enable focus maintenance, shorten the acquisition, let the "
        "enclosure equilibrate before starting, or re-focus periodically and "
        "record when. Note that drift is worst right after the enclosure is "
        "disturbed, so a rate measured late understates the start of a run.",
        numbers=numbers,
    )


def check_lateral_drift(setup: "StabilitySetup") -> CheckResult:
    """G30: does lateral drift stay inside the tolerance?

    BIAS rather than HARD: the field wandering does not destroy the data the
    way losing focus does, but it biases tracking (features leave the search
    window and links break) and any field-referenced measurement.
    """
    rate = setup.lateral_drift_rate_nm_per_min
    tol = setup.lateral_tolerance_um

    if rate is None or tol is None:
        missing = [
            n
            for n, v in (
                ("lateral_drift_rate_nm_per_min", rate),
                ("lateral_tolerance_um", tol),
            )
            if v is None
        ]
        return _ok(
            "stability.lateral_drift",
            BIAS,
            MAX_MARGIN,
            "Lateral drift not evaluated (missing: " + ", ".join(missing) + ").",
            evaluated=False,
        )

    drift_um = total_drift_nm(rate, setup.duration_min) / 1000.0
    margin = tol / drift_um if drift_um > 0 else MAX_MARGIN
    numbers = {
        "lateral_drift_rate_nm_per_min": rate,
        "total_drift_um": round(drift_um, 3),
        "tolerance_um": tol,
        "evaluated": True,
    }

    if margin >= 1.0:
        return _ok(
            "stability.lateral_drift",
            BIAS,
            margin,
            f"Lateral drift totals {drift_um:.2f} um, inside the {tol:.2f} um "
            "tolerance.",
            **numbers,
        )

    return CheckResult(
        "stability.lateral_drift",
        BIAS,
        margin,
        "warn",
        f"Lateral drift totals {drift_um:.2f} um over "
        f"{setup.duration_min:.0f} min, past the {tol:.2f} um tolerance. "
        "Features leave the tracking search window, so links break and "
        "trajectories fragment — which biases any displacement statistic "
        "toward short times.",
        action="Correct drift in post-processing against a fixed fiducial, "
        "widen the search window, or reduce the drift at source.",
        numbers=numbers,
    )


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
    Check("pfs_lock", HARD, ("duration",), check_pfs_lock),
    Check(
        "axial_drift",
        HARD,
        ("duration", "depth_of_field", "axial_drift_rate"),
        check_axial_drift,
    ),
    Check("lateral_drift", BIAS, ("duration",), check_lateral_drift),
    Check(
        "sedimentation",
        BIAS,
        ("duration", "depth_of_field", "settling_inputs"),
        check_sedimentation,
    ),
    Check("evaporation", BIAS, ("duration",), check_evaporation),
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
