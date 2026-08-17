"""Individual sample-geometry checks -- G15 (NA feasibility), G16 (working
distance), G17 (refractive-index mismatch), G18 (coverslip thickness),
G19 (count in field). docs/05-consensus-gate.md "Lens 4";
docs/06-pitfalls.md D5.

G15-G19 are new numbers: docs assigned lens 4 no gate IDs, and G1-G14 were
taken by lenses 1/2/3/5/6/7.

Mirrors optics.checks / detection.checks / compute.checks / trapping.checks:
independent margins (achieved / required), never booleans.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .aberration import (
    COVERSLIP_TOLERANCE_UM,
    collection_half_angle_deg,
    free_working_distance_um,
    max_na,
    mean_nearest_neighbour_um,
    paraxial_focal_shift_ratio,
    particles_in_field,
    ri_mismatch,
)

if TYPE_CHECKING:
    from .setup import SampleSetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    #: G17: depth x |dn| product beyond which spherical aberration must be
    #: quantified rather than tolerated, um. Anchored on docs/05 Lens 4's own
    #: checklist trigger -- "does the imaging depth exceed 10 um" -- evaluated
    #: at the oil-into-water mismatch of 0.185: 10 * 0.185 = 1.85.
    #:
    #: This is a screening heuristic, NOT a wave-optics result. It decides
    #: whether a real aberration calculation is owed; it does not substitute
    #: for one.
    "aberration_depth_mismatch_um": 1.85,
    #: G17: below this mismatch the media count as index-matched and the
    #: depth term is irrelevant. Covers water-immersion into a water-based
    #: medium (mismatch 0.000) and ordinary buffer-vs-water differences.
    "matched_ri_tolerance": 0.005,
    #: G18: excess coverslip thickness over design that an objective without
    #: a correction collar can absorb, um.
    "coverslip_tolerance_um": COVERSLIP_TOLERANCE_UM,
    #: G19: mean nearest-neighbour distance must exceed this multiple of the
    #: Rayleigh resolution for particles to be separable.
    "overlap_resolution_multiple": 3.0,
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
    run: Callable[["SampleSetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "SampleSetup") -> set[str]:
    facts: set[str] = set()
    if setup.imaging_depth_um is not None:
        facts.add("imaging_depth")
    if setup.objective.wd_um is not None:
        facts.add("working_distance")
    if setup.objective.na > 0:
        facts.add("na")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_na_feasibility(setup: "SampleSetup") -> CheckResult:
    """G15: ``NA <= n_immersion``. Exact, not an approximation.

    Catches an objective used in the wrong medium -- the 40x WI's NA 1.25 is
    unreachable dry (n=1.0). optics.components.Objective.collection_efficiency
    clamps this case with ``min(na/n, 1.0)`` and returns a plausible number
    instead of refusing, so nothing upstream notices.
    """
    na = setup.objective.na
    n = setup.n_immersion
    ceiling = max_na(n)
    ratio = ceiling / na if na > 0 else MAX_MARGIN
    theta = collection_half_angle_deg(na, n)

    if theta is None:
        return CheckResult(
            "geometry.na_feasibility",
            HARD,
            0.0,
            "fail",
            f"NA {na:.2f} is unreachable in {setup.objective.immersion} "
            f"(n = {n:.3f}): NA = n sin(theta) caps at {ceiling:.3f}.",
            action=f"Use the immersion medium this objective is designed for, "
            f"or correct the recorded NA/immersion for "
            f"'{setup.objective.label}'. Collection efficiency computed from "
            f"this pairing is fiction, not a low number.",
            numbers={
                "na": na,
                "n_immersion": n,
                "na_ceiling": ceiling,
                "na_ceiling_ratio": round(ratio, 3),
            },
        )

    # Pass returns MAX_MARGIN, not ``ceiling / na``, on purpose. This is a
    # binary physical-possibility veto, not a headroom measure: a high-NA
    # immersion objective is *designed* to sit just under its medium's index
    # (1.45 in oil gives 1.047), so grading on that ratio would drag every
    # correct high-NA setup to TIGHT and bury the real bottleneck. The ratio
    # stays in ``numbers`` for anyone who wants it.
    return _ok(
        "geometry.na_feasibility",
        HARD,
        MAX_MARGIN,
        f"NA {na:.2f} is reachable in {setup.objective.immersion} "
        f"(n = {n:.3f}); collection half-angle {theta:.1f} deg.",
        na=na,
        n_immersion=n,
        na_ceiling=ceiling,
        na_ceiling_ratio=round(ratio, 3),
        half_angle_deg=round(theta, 2),
    )


def check_working_distance(setup: "SampleSetup") -> CheckResult:
    """G16: free working distance must cover the imaging depth.

    Vendor WD is quoted past the design coverslip, so only coverslip excess
    over design is subtracted -- see aberration.free_working_distance_um.
    """
    depth = setup.imaging_depth_um
    free_wd = free_working_distance_um(
        setup.objective.wd_um,
        setup.resolved_coverslip_um,
        setup.design_coverslip_um,
    )
    margin = free_wd / depth if depth > 0 else MAX_MARGIN
    excess = max(0.0, setup.resolved_coverslip_um - setup.design_coverslip_um)

    numbers = {
        "wd_um": setup.objective.wd_um,
        "free_wd_um": round(free_wd, 2),
        "imaging_depth_um": depth,
        "coverslip_excess_um": round(excess, 2),
    }

    if margin >= 1.0:
        return _ok(
            "geometry.working_distance",
            HARD,
            margin,
            f"Free working distance {free_wd:.1f} um covers the "
            f"{depth:.1f} um imaging depth.",
            **numbers,
        )

    return CheckResult(
        "geometry.working_distance",
        HARD,
        margin,
        "fail",
        f"Free working distance {free_wd:.1f} um cannot reach "
        f"{depth:.1f} um into the sample"
        + (f" ({excess:.0f} um of that lost to coverslip excess)." if excess else "."),
        action="Use a longer-WD objective, image closer to the coverslip, or "
        "mount the sample on a thinner coverslip.",
        numbers=numbers,
    )


def check_ri_mismatch(setup: "SampleSetup") -> CheckResult:
    """G17: refractive-index mismatch x depth -- docs/06-pitfalls.md D5.

    Reports the paraxial focal-shift ratio as a number, and gates on the
    depth x mismatch product. BIAS, not HARD: mismatch does not stop the
    image forming, it biases what the image means.
    """
    depth = setup.imaging_depth_um
    n_s = setup.resolved_n_sample
    n_i = setup.n_immersion
    dn = ri_mismatch(n_s, n_i)
    shift = paraxial_focal_shift_ratio(n_s, n_i)

    numbers = {
        "n_sample": n_s,
        "n_immersion": n_i,
        "ri_mismatch": round(dn, 4),
        "imaging_depth_um": depth,
        "paraxial_focal_shift_ratio": round(shift, 4),
        "axial_scaling_error_pct": round(abs(1.0 - shift) * 100, 1),
    }

    if dn <= LIMITS["matched_ri_tolerance"]:
        return _ok(
            "geometry.ri_mismatch",
            BIAS,
            MAX_MARGIN,
            f"Index-matched: mismatch {dn:.4f} between "
            f"{setup.objective.immersion} (n = {n_i:.3f}) and the sample "
            f"medium (n = {n_s:.3f}). Depth-dependent spherical aberration "
            "from mismatch is not a concern here.",
            **numbers,
        )

    tolerable_depth = LIMITS["aberration_depth_mismatch_um"] / dn
    margin = tolerable_depth / depth if depth > 0 else MAX_MARGIN
    numbers["tolerable_depth_um"] = round(tolerable_depth, 2)

    if margin >= 1.0:
        return _ok(
            "geometry.ri_mismatch",
            BIAS,
            margin,
            f"Mismatch {dn:.3f} at {depth:.1f} um depth stays inside the "
            f"{tolerable_depth:.1f} um screening limit. Axial scale is still "
            f"off by {abs(1.0 - shift) * 100:.1f}% "
            f"(paraxial ratio {shift:.3f}) -- correct z distances before "
            "reporting any depth or 3D displacement.",
            **numbers,
        )

    return CheckResult(
        "geometry.ri_mismatch",
        BIAS,
        margin,
        "warn",
        f"Refractive-index mismatch {dn:.3f} "
        f"({setup.objective.immersion} n = {n_i:.3f} vs sample medium "
        f"n = {n_s:.3f}) at {depth:.1f} um depth exceeds the "
        f"{tolerable_depth:.1f} um screening limit. Spherical aberration "
        f"grows with depth and the axial scale is off by "
        f"{abs(1.0 - shift) * 100:.1f}%.",
        action="Switch to an index-matched objective (the 40x WI for aqueous "
        "media), image nearer the coverslip, or quantify the aberration and "
        "the axial correction properly -- the paraxial ratio here is a "
        "screening number, not a correction factor.",
        numbers=numbers,
    )


def check_coverslip(setup: "SampleSetup") -> CheckResult:
    """G18: coverslip thickness vs the thickness the objective is corrected for.

    docs/06-pitfalls.md: #1.5 is nominally 170+-5 um but the real spread is
    wider, so an unmeasured coverslip is an assumption, not a fact.
    """
    actual = setup.resolved_coverslip_um
    design = setup.design_coverslip_um
    deviation = abs(actual - design)
    tolerance = LIMITS["coverslip_tolerance_um"]
    margin = tolerance / deviation if deviation > 0 else MAX_MARGIN

    numbers = {
        "coverslip_actual_um": actual,
        "coverslip_design_um": design,
        "deviation_um": round(deviation, 2),
        "tolerance_um": tolerance,
        "measured": setup.coverslip_actual_um is not None,
        "correction_collar": setup.objective.correction_collar,
        "collar_adjusted": setup.collar_adjusted,
    }

    if setup.objective.correction_collar and not setup.collar_adjusted:
        return CheckResult(
            "geometry.coverslip",
            BIAS,
            min(margin, 0.8),
            "warn",
            f"'{setup.objective.label}' has a correction collar and there is "
            "no record of it being adjusted for this coverslip. An unadjusted "
            "collar reintroduces exactly the aberration the collar exists to "
            "remove.",
            action="Adjust the collar against this coverslip and record that "
            "you did, or state collar_adjusted=True if it was already done.",
            numbers=numbers,
        )

    if margin >= 1.0:
        return _ok(
            "geometry.coverslip",
            BIAS,
            margin,
            f"Coverslip {actual:.0f} um is within {tolerance:.0f} um of the "
            f"{design:.0f} um the objective is corrected for.",
            **numbers,
        )

    return CheckResult(
        "geometry.coverslip",
        BIAS,
        margin,
        "warn",
        f"Coverslip {actual:.0f} um deviates {deviation:.0f} um from the "
        f"{design:.0f} um design thickness, beyond the {tolerance:.0f} um "
        "tolerance.",
        action="Use a coverslip nearer the design thickness, or an objective "
        "with a correction collar and adjust it."
        if not setup.objective.correction_collar
        else "Adjust the correction collar for this thickness.",
        numbers=numbers,
    )


def check_count_in_field(setup: "SampleSetup") -> CheckResult:
    """G19: expected particle count and overlap in the observed volume.

    INFO, so a missing concentration leaves the rest of the gate runnable.
    Whether the count is *enough* is statistical power -- G11, lens 6 -- not
    this lens's call. What this lens owns is whether particles are so dense
    that they stop being separable.
    """
    c = setup.concentration_per_ml
    w, h = setup.field_width_um, setup.field_height_um
    depth = setup.imaging_depth_um

    if c is None or w is None or h is None or depth is None:
        missing = [
            n
            for n, v in (
                ("concentration_per_ml", c),
                ("field_width_um", w),
                ("field_height_um", h),
                ("imaging_depth_um", depth),
            )
            if v is None
        ]
        return _ok(
            "geometry.count_in_field",
            INFO,
            MAX_MARGIN,
            "Count in field not evaluated (missing: " + ", ".join(missing) + ").",
            evaluated=False,
        )

    count = particles_in_field(c, w, h, depth)
    nn = mean_nearest_neighbour_um(c)
    numbers = {
        "expected_count": round(count, 1),
        "concentration_per_ml": c,
        "field_um": [w, h],
        "depth_um": depth,
        "mean_nn_distance_um": round(nn, 3) if nn else None,
        "evaluated": True,
    }

    if setup.emission_nm is None or nn is None:
        return _ok(
            "geometry.count_in_field",
            INFO,
            MAX_MARGIN,
            f"About {count:.0f} particles expected in the observed volume; "
            f"mean nearest-neighbour distance "
            f"{nn:.2f} um." if nn else f"About {count:.0f} particles expected.",
            **numbers,
        )

    resolution_um = setup.objective.resolution_nm(setup.emission_nm) / 1000.0
    required = LIMITS["overlap_resolution_multiple"] * resolution_um
    margin = nn / required if required > 0 else MAX_MARGIN
    numbers["resolution_um"] = round(resolution_um, 3)
    numbers["required_nn_um"] = round(required, 3)

    if margin >= 1.0:
        return _ok(
            "geometry.count_in_field",
            INFO,
            margin,
            f"About {count:.0f} particles in the observed volume, mean "
            f"nearest-neighbour {nn:.2f} um against a {resolution_um:.2f} um "
            "resolution -- separable.",
            **numbers,
        )

    return CheckResult(
        "geometry.count_in_field",
        INFO,
        margin,
        "warn",
        f"At {c:.2e} /mL the mean nearest-neighbour distance is {nn:.2f} um, "
        f"under the {required:.2f} um needed to keep particles separable at "
        f"{resolution_um:.2f} um resolution. Tracking will mislink and "
        "intensities will be blended.",
        action="Dilute the sample, or image a thinner slice to reduce the "
        "number of overlapping particles along z.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("na_feasibility", HARD, ("na",), check_na_feasibility),
    Check("working_distance", HARD, ("imaging_depth", "working_distance"), check_working_distance),
    Check("ri_mismatch", BIAS, ("imaging_depth",), check_ri_mismatch),
    Check("coverslip", BIAS, (), check_coverslip),
    Check("count_in_field", INFO, (), check_count_in_field),
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
