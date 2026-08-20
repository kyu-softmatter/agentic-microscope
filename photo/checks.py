"""Individual photo-perturbation checks -- G10 (photobleaching), G20
(saturation / triplet shelving), G21 (light-driving), G22 (total dose).
docs/04-decision-engine.md §5-§6; docs/05-consensus-gate.md "Lens 5";
docs/06-pitfalls.md D2, D3.

G10 was specified in the docs and never implemented. G20-G22 are new numbers:
G1-G19 were taken by lenses 1/2/3/4/6/7.

Mirrors optics.checks / detection.checks / compute.checks / trapping.checks /
sample.checks: independent margins (achieved / required), never booleans.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dose import (
    bleached_fraction,
    duty_cycle,
    emitted_photons_per_molecule,
    excited_state_fraction,
    saturation_irradiance_w_cm2,
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

LIMITS = {
    #: G10: fraction of molecules bleached over the whole movie.
    #: docs/04 §6 -- above this an intensity-decay correction must be possible.
    "bleached_fraction_max": 0.2,
    #: G20: steady-state excited-state fraction above which the linear
    #: photon-budget assumption that lenses 1 and 2 rely on stops holding.
    #: 0.1 keeps emission within ~10% of linear in power. Triplet shelving is
    #: not modelled and pushes real saturation earlier, so this is generous.
    "excited_state_fraction_max": 0.1,
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
    run: Callable[["IlluminationSetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "IlluminationSetup") -> set[str]:
    facts: set[str] = set()
    if setup.resolved_irradiance is not None:
        facts.add("irradiance")
    if setup.resolved_emitted_per_s is not None:
        facts.add("emitted_rate")
    if setup.resolved_excitation_rate is not None:
        facts.add("excitation_rate")
    if setup.exposure_ms is not None and setup.n_frames is not None:
        facts.add("exposure_plan")
    if setup.bleach_photons is not None:
        facts.add("bleach_photons")
    if setup.lifetime_ns is not None:
        facts.add("lifetime")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_photobleaching(setup: "IlluminationSetup") -> CheckResult:
    """G10: less than 20% of the label bleached over the movie. docs/04 §6."""
    emitted_rate = setup.resolved_emitted_per_s
    n_emitted = emitted_photons_per_molecule(
        emitted_rate, setup.exposure_ms, setup.n_frames
    )
    frac = bleached_fraction(n_emitted, setup.bleach_photons)
    limit = LIMITS["bleached_fraction_max"]
    margin = limit / frac if frac > 0 else MAX_MARGIN

    numbers = {
        "emitted_per_s": emitted_rate,
        "n_emitted_per_molecule": n_emitted,
        "bleach_photons": setup.bleach_photons,
        "bleached_fraction": round(frac, 4),
        "limit": limit,
        "illuminated_time_s": round(
            total_illuminated_time_s(setup.exposure_ms, setup.n_frames), 4
        ),
    }

    if margin >= 1.0:
        return _ok(
            "perturbation.photobleaching",
            BIAS,
            margin,
            f"About {frac * 100:.1f}% of the label bleaches over "
            f"{setup.n_frames} frames, within the "
            f"{limit * 100:.0f}% limit. Superlinear triplet pathways are not "
            "modelled, so treat this as a lower bound.",
            **numbers,
        )

    return CheckResult(
        "perturbation.photobleaching",
        BIAS,
        margin,
        "warn",
        f"About {frac * 100:.1f}% of the label bleaches over "
        f"{setup.n_frames} frames, past the {limit * 100:.0f}% limit. "
        "Intensity decays through the movie, so anything derived from "
        "brightness drifts with it. This is a **lower bound** -- bleaching is "
        "often superlinear in intensity (triplet pathways).",
        action="Cut the light level or the exposure, shorten the movie, reduce "
        "the illumination duty cycle, add an antifade, or switch to a more "
        "photostable dye. If none of those, an intensity-decay correction must "
        "be demonstrably possible before the data means anything.",
        numbers=numbers,
    )


def check_saturation(setup: "IlluminationSetup") -> CheckResult:
    """G20: is the dye being driven into saturation?

    Nothing else catches this. docs/04 §3 and optics.path.detected_e_per_s both
    assume emission is linear in power; past saturation that assumption breaks
    and lenses 1 and 2 overestimate signal while the dose keeps climbing.
    """
    k_ex = setup.resolved_excitation_rate
    frac = excited_state_fraction(k_ex, setup.lifetime_ns)
    limit = LIMITS["excited_state_fraction_max"]
    margin = limit / frac if frac > 0 else MAX_MARGIN

    numbers = {
        "excitation_rate_per_s": k_ex,
        "lifetime_ns": setup.lifetime_ns,
        "excited_state_fraction": round(frac, 4),
        "limit": limit,
    }
    if setup.ext_coeff_m1cm1 and setup.wavelength_nm:
        numbers["saturation_irradiance_w_cm2"] = round(
            saturation_irradiance_w_cm2(
                setup.ext_coeff_m1cm1, setup.lifetime_ns, setup.wavelength_nm
            ),
            1,
        )

    if margin >= 1.0:
        return _ok(
            "perturbation.saturation",
            BIAS,
            margin,
            f"{frac * 100:.2f}% of molecules sit in the excited state, inside "
            f"the {limit * 100:.0f}% linear-regime limit, so the photon budget "
            "lenses 1 and 2 compute is still trustworthy.",
            **numbers,
        )

    return CheckResult(
        "perturbation.saturation",
        BIAS,
        margin,
        "warn",
        f"{frac * 100:.1f}% of molecules are parked in the excited state "
        f"(k_ex tau = {k_ex * setup.lifetime_ns * 1e-9:.3f}), past the "
        f"{limit * 100:.0f}% linear limit. Emission no longer rises in "
        "proportion to power, so the photon budget from lenses 1 and 2 "
        "overestimates signal — while dose and bleaching keep climbing. "
        "Triplet shelving is not modelled and makes this worse.",
        action="Lower the light level and lengthen the exposure to keep the "
        "same photon count: below saturation those trade evenly, above it they "
        "do not.",
        numbers=numbers,
    )


def check_light_driving(setup: "IlluminationSetup") -> CheckResult:
    """G21: is the illumination driving the sample rather than measuring it?

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
            BIAS,
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
            BIAS,
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
            BIAS,
            margin,
            f"{irradiance:.1f} W/cm^2 stays under the {threshold:.1f} W/cm^2 "
            "at which this sample starts responding to the light.",
            **numbers,
        )

    return CheckResult(
        "perturbation.light_driving",
        BIAS,
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
    """G22: accumulated energy per unit area, and the duty cycle that sets it.

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
    """Refuse to let the 5 -> 7 handoff for trap heating vanish silently.

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

    return CheckResult(
        "perturbation.trap_heating_unowned",
        INFO,
        MAX_MARGIN,
        "info",
        "The 1064 nm trap is on and its local heating is ungated by decision "
        "(2026-08-19): docs/06 D6 assigns it to lens 7, which has no heating "
        "check and is not getting one, and lens 5 covers visible excitation "
        "light only. Water absorption at 1064 nm changes viscosity and "
        "therefore D, so any microrheology result from this configuration may "
        "be contaminated. Named, not caught.",
        action="Treat the medium temperature near the trap as the experiment's "
        "assumption, not the gate's. Before trusting a diffusion or viscosity "
        "number from this setup, quantify the heating separately or show it is "
        "small at this power. No lens computes it.",
        numbers={"trap_on": True},
    )


CHECKS: list[Check] = [
    Check(
        "photobleaching",
        BIAS,
        ("emitted_rate", "exposure_plan", "bleach_photons"),
        check_photobleaching,
    ),
    Check("saturation", BIAS, ("excitation_rate", "lifetime"), check_saturation),
    Check("light_driving", BIAS, ("irradiance",), check_light_driving),
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
