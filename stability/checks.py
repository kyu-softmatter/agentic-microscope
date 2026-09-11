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

AND AS OF 2026-09-10 NOTHING HERE IS GRADED AT ALL: this is a reporting
section, like lens 5 became the same day. G31 and G32 became INFO on KH's
instruction -- G31 because it was comparing a whole run's free settling against
a depth of field and calling every real bead INFEASIBLE (5 um polystyrene in
water moves 41 um/min against 0.375 um), when a TRAPPED bead does not settle at
all and the free case is already lens 4's G19; G32 because sealing is
declarable and an evaporation rate is not, and its 0.5 stand-in margin was a
number invented to mean "not quantified".

`vibration` is gone too, and on a physical argument rather than a scheduling
one: **every part of this microscope sits on the same isolation table, so the
camera and the sample move together.** An image shows their RELATIVE motion,
and common-mode motion of a rigid assembly cancels out of it -- so there is no
channel to measure, not merely an unbuilt one. Note the contrast with drift,
which is differential expansion in the path between objective and holder and
therefore does show up: that is why `drift_budget` survives and `vibration`
does not.

So what this lens reports is what IS knowable before the run starts -- the
settling velocity and the time it takes to be over, the evaporative
concentration if a rate exists, and the drift rate the plan could absorb -- and
`stability/gate.py` returns `status: REPORT` with `advances: None`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .drift import (
    concentration_factor,
    evaporated_fraction,
)
from .setup import CONVENE_DURATION_MIN

if TYPE_CHECKING:
    from .setup import StabilitySetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

#: EMPTY, AND THAT IS THE STATE OF THE LENS. Both entries went on 2026-09-10
#: when G31 and G32 became reports: `settling_dof_fraction` (1.0) had nothing
#: left to compare, and `evaporated_fraction_max` (0.05) was a threshold on a
#: quantity the plan cannot supply. An entry appearing here again means a
#: judging gate has come back, which is a decision and not a refactor.
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
    run: Callable[["StabilitySetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    """Severity **"info"**, not "ok", and the distinction is load-bearing.

    Every `gate.py` in this repository drops `severity == "ok"` from
    `findings`, so a check that computed a number and returned `_ok` put it in
    `metrics` and nowhere a reader would see it. That defect was found three
    times during the 2026-09-10 review, twice in this lens. **Ungraded and
    invisible are different things**, and in a reporting section -- where
    nothing is graded and the findings ARE the output -- an invisible check is
    the whole lens failing silently. Nothing here returns "ok".
    """
    return CheckResult(code, kind, margin, "info", message, None, numbers)


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
    """G31: how fast does the population move, and how long until it stops?

    REPORTS, DOES NOT GATE, since 2026-09-10 (KH): *"침강 상승 속도와 평형에
    도달하는 시간 정도만 계산하고 인포로 남겨두자."* It used to compare the
    distance settled over the whole acquisition against the depth of field,
    which put out a margin of 0.00 for any real bead -- 5 um polystyrene in
    water moves 41 um/min against a 0.375 um DOF, so the gate said INFEASIBLE
    to every experiment this instrument actually runs, including the ones that
    work. Two reasons that reading was wrong:

    - **A trapped bead does not settle.** The lens has no `trapped` field, so
      the gate applied the free-settling velocity to a bead held in a trap,
      whose axial sag under gravity is its buoyant weight over the AXIAL
      stiffness: 0.032 pN for a 5 um polystyrene bead, so **32 nm for every
      1 pN/um of kappa_z**. That arithmetic is exact; kappa_z is not, because
      NOTHING IN THIS REPOSITORY COMPUTES OR MEASURES IT. `trapping.goa` gives
      the radial stiffness only -- `trap_force` documents that it "assumes zero
      axial offset", so there is no z to difference. Do not close the number
      with a kappa_z/kappa_xy ratio; none is recorded here.
    - **The free-settling case is already lens 4's.** G19 rebuilt itself on a
      total-sedimentation premise on 2026-09-10: it assumes the population has
      reached the floor and works out the areal density there. Two lenses were
      charging the same fact against different thresholds.

    What is left is the pair of numbers that premise needs and nobody was
    reporting: **the velocity, and the time until it is over.** G19 assumes the
    settled state; this says when the settled state arrives.
    """
    v = setup.settling_velocity_um_per_s
    numbers = {"duration_min": setup.duration_min}

    if v is None:
        return CheckResult(
            "stability.sedimentation",
            INFO,
            MAX_MARGIN,
            "info",
            "No settling velocity: it needs particle radius, the "
            "particle-minus-medium density difference and the medium "
            "viscosity. Nothing is gated on it, but the time for the "
            "suspension to settle out is worth knowing before a long run.",
            action="Supply particle_radius_um, delta_density_kg_m3 (0 for a "
            "density-matched suspension) and viscosity_pa_s.",
            numbers=numbers,
        )

    direction = "settles" if v > 0 else "creams upward" if v < 0 else "neither"
    speed = abs(v)
    numbers.update(
        {
            "settling_velocity_um_per_s": round(v, 6),
            "settling_velocity_um_per_min": round(v * 60.0, 4),
            "direction": direction,
            "chamber_height_um": setup.chamber_height_um,
        }
    )

    if speed == 0.0:
        return CheckResult(
            "stability.sedimentation",
            INFO,
            MAX_MARGIN,
            "info",
            "Density-matched: the settling term is exactly zero, so the "
            "population stays where it was put for as long as the run lasts. "
            "Nothing else in this check applies.",
            action=None,
            numbers=numbers,
        )

    # Time to equilibrium. The equilibrium of a settling suspension under
    # gravity is the floor (or the ceiling, creaming) -- for a micron-scale
    # bead the sedimentation-diffusion balance sits far below one bead
    # diameter, so there is no suspended steady state to reach instead. The
    # chamber height is what sets the clock, and it is a planning input.
    if setup.chamber_height_um:
        t_min = setup.chamber_height_um / speed / 60.0
        numbers["time_to_equilibrium_min"] = round(t_min, 3)
        if setup.duration_min:
            numbers["equilibrium_before_end"] = t_min < setup.duration_min
            numbers["duration_over_equilibrium_time"] = round(
                setup.duration_min / t_min, 2
            )
        clock = (
            f" A particle starting at the top of a "
            f"{setup.chamber_height_um:.0f} um chamber reaches the "
            f"{'bottom' if v > 0 else 'top'} in {t_min:.1f} min"
        )
        if setup.duration_min and t_min < setup.duration_min:
            clock += (
                f" -- {setup.duration_min / t_min:.0f}x inside the "
                f"{setup.duration_min:.0f} min acquisition, so the suspension "
                "is already settled out for most of it, which is the premise "
                "lens 4's G19 works from."
            )
        elif setup.duration_min:
            clock += (
                f", longer than the {setup.duration_min:.0f} min acquisition, "
                "so the population is still in transit when the run ends and "
                "G19's settled-state premise does not hold yet."
            )
        else:
            clock += "."
    else:
        clock = (
            " No chamber height on record, so there is no clock: supply "
            "chamber_height_um for the time to equilibrium."
        )

    return CheckResult(
        "stability.sedimentation",
        INFO,
        MAX_MARGIN,
        "info",
        f"The population {direction} at {speed * 60.0:.2f} um/min "
        f"({speed:.4f} um/s), by Stokes.{clock}",
        action="Not gated: a trapped bead does not settle (its axial sag is "
        "the buoyant weight over kappa_z, 32 nm per pN/um, and kappa_z is not "
        "computed anywhere in this repository), and the free-settling "
        "case belongs to lens 4's G19, which assumes the settled state this "
        "reports the arrival time of. Density-matching removes the term "
        "entirely; settling goes as radius squared.",
        numbers=numbers,
    )


def check_evaporation(setup: "StabilitySetup") -> CheckResult:
    """G32: how much does the sample concentrate during the acquisition?

    REPORTS, DOES NOT GATE, since 2026-09-10 (KH). The reason is in the input:
    **sealing is declarable, an evaporation rate is not.** A sealed chamber is
    a fact about the plan, and it already answers the question -- the term
    vanishes. Unsealed, the only honest input is a weighed rate, and weighing a
    chamber before and after is something you do around a run, not while
    designing one. The old gate handled that by returning a stand-in margin of
    0.5, which graded HARD and blocked `advances` on an acquisition nobody had
    measured anything about; a number invented to represent "not quantified" is
    exactly what this repository is not supposed to produce.

    So: sealed is reported as answered, unsealed with a rate is reported as
    arithmetic, unsealed without one is reported as unquantified -- and none of
    the three is graded.
    """
    numbers = {
        "chamber_sealed": setup.chamber_sealed,
        "duration_min": setup.duration_min,
    }

    if setup.chamber_sealed:
        return CheckResult(
            "stability.evaporation",
            INFO,
            MAX_MARGIN,
            "info",
            "Chamber declared sealed, so there is no evaporative "
            "concentration. This is the one input in this lens that a plan can "
            "settle outright rather than measure.",
            action=None,
            numbers=numbers,
        )

    rate = setup.evaporation_rate_ul_per_hour
    volume = setup.sample_volume_ul

    if rate is None or volume is None:
        span = (
            f"a {setup.duration_min:.0f} min acquisition"
            if setup.duration_min
            else "an acquisition of unstated length"
        )
        return CheckResult(
            "stability.evaporation",
            INFO,
            MAX_MARGIN,
            "info",
            f"Chamber is unsealed for {span} and no evaporation rate is on "
            "record, so the concentration drift is UNQUANTIFIED -- not small. "
            "Solvent leaving concentrates everything left behind, and every "
            "concentration-dependent quantity drifts with it.",
            action="Seal the chamber, which settles it. Otherwise weigh an "
            "identical unsealed chamber before and after a run of this length "
            "for a uL/hour rate; it cannot be computed from the setting.",
            numbers=numbers,
        )

    frac = evaporated_fraction(rate, volume, setup.duration_min)
    factor = concentration_factor(frac)
    numbers.update(
        {
            "evaporation_rate_ul_per_hour": rate,
            "sample_volume_ul": volume,
            "evaporated_fraction": round(frac, 4),
            "concentration_factor": round(factor, 3)
            if math.isfinite(factor)
            else None,
        }
    )
    return CheckResult(
        "stability.evaporation",
        INFO,
        MAX_MARGIN,
        "info",
        f"About {frac * 100:.1f}% of the volume evaporates over "
        f"{setup.duration_min:.0f} min, concentrating the sample "
        + (f"{factor:.3f}x" if math.isfinite(factor) else "without bound")
        + ". Read it against the precision the measurement needs: a few "
        "percent moves a viscosity, and on a multiphase sample a few percent "
        "of water can cross a phase boundary.",
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

    ⚠ IT DOES CARRY A MODEL, AND THE OUTPUT SAYS SO. Dividing by the duration
    presumes drift is **monotonic and linear for the whole run** -- that it
    accumulates in one direction and never comes back. `drift.py` records why
    that is the optimistic case: thermal drift is worst in the first hour after
    the enclosure is disturbed, so a real run front-loads it and blows the
    quoted rate early while averaging under it. And it is pessimistic in the
    other direction for any run that re-establishes focus part way through,
    where the window that matters is the interval between re-focuses, not the
    total length. So read the number as **the requirement a linear reading of
    the plan places on the instrument**, not as a prediction. Duration and
    depth of field are the only two planning inputs in it; the monotonicity is
    an assumption and is stated in the message.
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
        f"DOF -- {rate_full_dof / 2:.1f} nm/min for half of it. ASSUMES DRIFT "
        "IS MONOTONIC FOR THE WHOLE RUN, which is the only part of this that "
        "is a model: thermal drift is worst in the first hour after the "
        "enclosure is disturbed, so a real run front-loads it and can blow "
        "this rate early while averaging under it. Read it as the requirement "
        "a linear reading of the plan places on the instrument, not as a "
        "prediction -- and if the run re-establishes focus part way through, "
        "recompute it on that interval instead of the total length.",
        action="Axial: config/session/focus_monitor.py already samples ZDrive "
        "and both cameras several times a second, so the rate falls out of the "
        "run's own focus scores. Lateral: data/particles.yaml records that most "
        "of the bead population is stuck to the coverslip, so a stuck bead in "
        "the same frames is the fiducial -- no extra acquisition either way. "
        "Note this is NOT the argument that killed the vibration check: the "
        "table moves camera and sample together, so vibration is common-mode "
        "and cancels out of an image, while drift is differential expansion in "
        "the path between objective and holder and does not. Judge both after "
        "the fact, like compute.drops does.",
        numbers={
            "duration_min": duration,
            "depth_of_field_um": dof_um,
            "axial_rate_for_one_dof_nm_per_min": round(rate_full_dof, 3),
            "axial_rate_for_half_dof_nm_per_min": round(rate_full_dof / 2, 3),
            "assumes_monotonic_drift": True,
            "gated": False,
        },
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
    # All INFO since 2026-09-10, so `requires` is documentation here rather
    # than a gate: Phase 0 only withholds non-INFO checks. Each one handles its
    # own missing input and says what is absent, which is why one absent number
    # no longer takes the whole lens down with it.
    Check("sedimentation", INFO, ("settling_inputs",), check_sedimentation),
    Check("evaporation", INFO, (), check_evaporation),
    Check("drift_budget", INFO, (), check_drift_budget),
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
    #: Not a grade. `stability/gate.py` reports `feasibility: "N/A"` because
    #: nothing in this lens is gradeable, and an empty note would read as a
    #: lookup miss rather than as the deliberate answer it is.
    "N/A": "Not graded. This lens is a reporting section -- every check is "
    "INFO, so there is no margin to grade and no bottleneck to name.",
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
