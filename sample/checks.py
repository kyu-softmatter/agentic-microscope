"""Individual sample-geometry checks -- L4.1 (NA feasibility), L4.2 (working
distance), L4.3 (depth within chamber), L4.4 (near-wall drag bound),
L4.5 (refractive-index mismatch), L4.6 (count in field), plus the depth window
that reports L4.2/L4.3/L4.4/L4.5's bounds as one band.

G18 (coverslip thickness) was REMOVED 2026-09-10 and its number is not reused
-- kb/decisions/2026-09-10-lens-4-depth-window-and-g18-removed.md. The
coverslip is still in this lens twice: L4.2 subtracts its excess over design
from the working-distance budget, and an unmeasured coverslip is still an
`assumed_input` that withholds `advances`. What went is the graded margin.
docs/05-consensus-gate.md "Lens 4";
docs/06-pitfalls.md D5.

L4.1-L4.6 are new numbers: docs assigned lens 4 no gate IDs, and L1.1-L7.2–L7.4 were
taken by lenses 1/2/3/5/6/7. L4.3 follows lens 3's convention of suffixing an
extra criterion onto its nearest gate (L3.1-c, L3.4-d) rather than extending
the top of the range: it pairs with L4.2, which asks whether the objective can
*reach* the depth, by asking whether the sample *extends* that far.

Mirrors optics.checks / detection.checks / compute.checks / trapping.checks:
independent margins (achieved / required), never booleans.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .aberration import (
    areal_coverage_fraction,
    collection_half_angle_deg,
    free_working_distance_um,
    max_na,
    mean_areal_spacing_um,
    paraxial_focal_shift_ratio,
    settled_areal_density_per_um2,
    ri_mismatch,
    wall_drag_suppression,
)

if TYPE_CHECKING:
    from .setup import SampleSetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

LIMITS = {
    #: L4.5: depth x |dn| product beyond which spherical aberration must be
    #: quantified rather than tolerated, um. Anchored on docs/05 Lens 4's own
    #: checklist trigger -- "does the imaging depth exceed 10 um" -- evaluated
    #: at the oil-into-water mismatch of 0.185: 10 * 0.185 = 1.85.
    #:
    #: This is a screening heuristic, NOT a wave-optics result. It decides
    #: whether a real aberration calculation is owed; it does not substitute
    #: for one.
    "aberration_depth_mismatch_um": 1.85,
    #: L4.5: below this mismatch the media count as index-matched and the
    #: depth term is irrelevant. Covers water-immersion into a water-based
    #: medium (mismatch 0.000) and ordinary buffer-vs-water differences.
    "matched_ri_tolerance": 0.005,
    #: L4.6: mean nearest-neighbour distance must exceed this multiple of the
    #: Rayleigh resolution for particles to be separable.
    "overlap_resolution_multiple": 3.0,
    #: L4.4: fractional suppression of D by the nearby wall that an untrapped
    #: measurement may carry unabsorbed. An **order-of-magnitude screen**, not a
    #: precision threshold (docs/01 §3 Principle 1b): 10% sits with this repo's
    #: other bias limits (G10 bleaching at 20%, L2.4 blur at 0.3 tau) and just
    #: above docs/06 D8's tabulated 12.7% for a 4 um bead at h = 10 um, the case
    #: D8 considered worth writing down. Past it, say so; do not pretend the
    #: boundary is sharp.
    "wall_drag_suppression": 0.10,
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
    """L4.1 (was G15): ``NA <= n_immersion``. Exact, not an approximation.

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
    """L4.2 (was G16): free working distance must cover the imaging depth.

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


def check_depth_in_chamber(setup: "SampleSetup") -> CheckResult:
    """L4.3 (was G16b): is there any sample at the depth being focused to?

    L4.2 asks whether the objective can *reach* the depth. This asks whether the
    sample *extends* that far. Focus past the chamber's far wall and you image
    the wall, and nothing else in the committee notices: lens 8 holds
    ``chamber_height_um`` but spends it only on the sedimentation flag
    (``stability/checks.py`` L8.2), and lens 4 owned the imaging depth without
    ever seeing the height.

    HARD in character -- past the far wall the data is not biased, it is of
    something else -- but registered with **no** ``requires``, so an absent
    chamber height skips the check instead of BLOCKing the whole gate. Same
    reasoning as L4.6: a fact the user often does not have to hand must not take
    the rest of the lens down with it.

    Note what this check does not need: the spacer or gasket setting the height
    is not in the optical path (either orientation of stand), so it never enters
    the working-distance budget. Only the coverslip does, via L4.2.
    """
    depth = setup.imaging_depth_um
    height = setup.chamber_height_um

    if depth is None:
        return _ok(
            "geometry.depth_in_chamber",
            INFO,
            MAX_MARGIN,
            "Depth within chamber not evaluated (no imaging depth).",
            evaluated=False,
        )

    if height is None and setup.unspaced_mount:
        # Not the same as "nobody asked". With no spacer there is no designed
        # thickness to ask for, so say that rather than skipping quietly.
        # severity "info" keeps it out of the grade but puts it in findings.
        return CheckResult(
            "geometry.depth_in_chamber",
            INFO,
            MAX_MARGIN,
            "info",
            "No spacer, so the sample thickness is set by drop volume, wetting "
            "and the coverslip's weight rather than by a part with a spec. "
            f"There is no designed height to check the {depth:.1f} um focal "
            "depth against, and a squashed drop is a wedge -- the thickness "
            "differs across the field and between preparations.",
            action="Estimate or measure the sample thickness for this "
            "preparation and pass chamber_height_um, if the focal depth is "
            "more than a few um. Otherwise state that the depth is small "
            "against any plausible thickness and move on.",
            numbers={
                "imaging_depth_um": depth,
                "unspaced_mount": True,
                "evaluated": False,
            },
        )

    if height is None:
        return _ok(
            "geometry.depth_in_chamber",
            INFO,
            MAX_MARGIN,
            "Depth within chamber not evaluated (no chamber_height_um on "
            "record).",
            evaluated=False,
        )

    margin = height / depth if depth > 0 else MAX_MARGIN
    numbers = {
        "chamber_height_um": height,
        "imaging_depth_um": depth,
        "headroom_um": round(height - depth, 2),
        "unspaced_mount": setup.unspaced_mount,
        "evaluated": True,
    }
    # An unspaced height is one preparation's drop thickness, not a part spec,
    # so the margin is only as reproducible as the mounting.
    caveat = (
        " Unspaced mount, so this height is this preparation's drop thickness"
        " rather than a part spec -- expect it to vary across the field and"
        " between preparations."
        if setup.unspaced_mount
        else ""
    )

    if margin >= 1.0:
        return _ok(
            "geometry.depth_in_chamber",
            HARD,
            margin,
            f"The {height:.1f} um chamber holds sample at the requested "
            f"{depth:.1f} um focal depth ({height - depth:.1f} um to spare)."
            + caveat,
            **numbers,
        )

    return CheckResult(
        "geometry.depth_in_chamber",
        HARD,
        margin,
        "fail",
        f"The focal plane is {depth:.1f} um past the coverslip but the chamber "
        f"is only {height:.1f} um deep, so there is no sample there -- what "
        "comes into focus is the far wall." + caveat,
        action="Reduce the imaging depth below the chamber height, or build a "
        "taller chamber. Check this before blaming signal on the light level: "
        "an empty focal plane looks exactly like a dim one.",
        numbers=numbers,
    )


def check_wall_drag(setup: "SampleSetup") -> CheckResult:
    """L4.4 (was G16c): bound the near-wall drag bias on D, rather than merely naming it.

    The imaging depth *is* the wall distance -- ``h`` is measured from the
    coverslip's inner surface, which is the wall. So lens 4 already holds one of
    the two inputs; the bead radius is consumed from lens 7/8.

    This is the worked example of docs/01 §3 Principle 1b. There is no exact
    near-wall model here and none is wanted; the truncated Faxen term
    ``9a/(16h)`` over-states the drag, so reporting "D is low by at most this"
    is a computation and not a guess. docs/06 D8's decision not to *correct* by
    formula stands -- bounding and correcting are different acts.

    Trapped is the ordinary case in this lab, and it has an absorption route:
    D8's in-situ power-spectrum calibration at the working height returns kappa
    and the wall-corrected gamma together. So a trapped setup reports the bound
    at MAX_MARGIN with severity "info" -- **ungraded here, but BIAS-kind and
    under a distinct code, so it reaches lens 6's ledger**, which is where the
    absorption claim gets audited. Untrapped, nothing absorbs it and the bound
    is the answer, so it warns past the screening limit.
    """
    a = setup.particle_radius_um
    h = setup.imaging_depth_um

    if a is None or h is None:
        return _ok(
            "geometry.wall_drag",
            INFO,
            MAX_MARGIN,
            "Near-wall drag not bounded (no particle_radius_um).",
            evaluated=False,
        )

    suppression = wall_drag_suppression(a, h)
    if suppression is None:
        return CheckResult(
            "geometry.wall_drag",
            BIAS,
            0.0,
            "warn",
            f"A {a:.2f} um-radius particle {h:.1f} um from the wall is outside "
            "the Faxen expansion's domain (h <= a), so no bound is available -- "
            "not a small correction, an unquantified one.",
            action="Image further from the coverslip, or accept that the drag "
            "near contact is uncharacterised here. Do not substitute the bulk "
            "Stokes drag.",
            numbers={"particle_radius_um": a, "wall_distance_um": h, "evaluated": True},
        )

    limit = LIMITS["wall_drag_suppression"]
    margin = limit / suppression if suppression > 0 else MAX_MARGIN
    numbers = {
        "particle_radius_um": a,
        "wall_distance_um": h,
        "d_suppression_upper_bound": round(suppression, 4),
        "drag_penalty_upper_bound": round(1.0 / (1.0 - suppression) - 1.0, 4),
        "limit": limit,
        "trapped": setup.trapped,
        "evaluated": True,
    }
    pct = suppression * 100

    if setup.trapped:
        # THREE THINGS ARE DELIBERATE HERE AND EACH WAS A SEPARATE DEFECT.
        #
        # severity "info", NOT "ok" (KH, 2026-09-10). `_ok` is dropped from
        # `findings` by sample/gate.py, so this branch used to compute an
        # 18.3% drag inflation and then discard it into `metrics` -- a bias
        # with no trace in any verdict, on the strength of an absorption claim
        # the reader never got to check.
        #
        # kind BIAS, NOT INFO (KH, 2026-09-11). severity "info" fixed the
        # visibility and left a second hole: `validity.setup.bias_findings`
        # filters on the RESULT's kind, so an INFO-kind result never reached
        # lens 6's ledger. On a drag calibration that is the principal bias on
        # the measured quantity, so it was reaching a human reader and no gate.
        # BIAS at MAX_MARGIN does not cost lens 4 anything -- 10.0 is never the
        # worst margin -- and severity "info" still keeps it out of
        # PASS_WITH_CHANGES here. The grading stays with lens 6, which is whose
        # question it is.
        #
        # A DISTINCT CODE, `geometry.wall_drag.trapped` (KH, 2026-09-11),
        # following the `motion_blur` / `motion_blur.biased` convention. The
        # registries are keyed by code, and the two branches need different
        # answers: trapped HAS an absorption route (in-situ calibration) so it
        # belongs in CORRECTIONS, untrapped has none and belongs in
        # UNCORRECTABLE. One code could only get one answer.
        # kb/decisions/2026-09-11-wall-drag-reaches-the-bias-ledger.md
        return CheckResult(
            "geometry.wall_drag.trapped",
            BIAS,
            MAX_MARGIN,
            "info",
            f"D is suppressed by at most {pct:.1f}% at {h:.1f} um from the "
            f"wall (a = {a:.2f} um), which inflates the drag by "
            f"{numbers['drag_penalty_upper_bound'] * 100:.1f}%. Held as INFO "
            "because the trap CAN absorb it -- an in-situ power-spectrum "
            "calibration at the working height returns kappa and the "
            "wall-corrected drag together (docs/06 D8), and must be redone "
            "whenever the height changes.",
            action="⚠ THAT ABSORPTION IS A PREMISE, NOT A FACT, AND IT IS "
            "FALSE FOR SOME MEASUREMENTS. It holds when gamma comes OUT of "
            "the fit -- equipartition, or a PSD corner frequency. It does not "
            "hold when gamma goes IN as 6*pi*eta*a, which is what a "
            "Stokes-drag (velocity) calibration does: nothing absorbs "
            "anything there and the figure above lands directly on the "
            "result. Confirm an in-situ calibration at this height exists, or "
            "treat this as an uncorrected bias and hand it to lens 6.",
            numbers=numbers,
        )

    if margin >= 1.0:
        return _ok(
            "geometry.wall_drag",
            BIAS,
            margin,
            f"Untrapped, but D is suppressed by at most {pct:.1f}% at "
            f"{h:.1f} um from the wall (a = {a:.2f} um) -- inside the "
            f"{limit * 100:.0f}% screening limit. Upper bound, so the real "
            "figure is smaller.",
            **numbers,
        )

    return CheckResult(
        "geometry.wall_drag",
        BIAS,
        margin,
        "warn",
        f"Untrapped measurement {h:.1f} um from the wall with a {a:.2f} um "
        f"radius particle: D is low by up to {pct:.1f}% and any viscosity or "
        f"modulus inferred from it correspondingly stiff. Past the "
        f"{limit * 100:.0f}% screening limit, and there is no trap, so D8's "
        "in-situ calibration cannot absorb it.",
        action="Image further from the coverslip (the bound falls as 1/h), use "
        "a smaller particle, or report the result with this bound stated. Do "
        "not apply a Faxen correction -- that is a closed decision "
        "(kb/decisions/2026-08-19-lens-7-scope.md). Lens 6 rules on whether "
        "the bound is acceptable.",
        numbers=numbers,
    )


def check_depth_window(setup: "SampleSetup") -> CheckResult:
    """L4.7: The usable band of focal depths, both ends, in one place.

    L4.2, L4.3, L4.4 and L4.5 each bound the imaging depth, and until 2026-09-10
    a reader had to collect four margins and invert them by hand to learn where
    the focal plane may actually sit. Requested by KH: report the window.

    Which gate owns which end:

        LOWER  L4.4  near-wall drag. Working close to the coverslip is the
                     thing to avoid, so this is a floor: 9a/(16h) <= limit
                     gives h >= 9a/(16*limit).
        UPPER  L4.2   free working distance -- how far the objective reaches.
              L4.3   chamber height -- how far the SAMPLE extends. The spacer
                     correction on the same budget.
              L4.5    depth x |dn| screening limit, when the media are
                     mismatched. Not a reach limit; an aberration one.

    INFO, and deliberately so: every bound it restates is already graded by the
    gate that owns it, and grading the window too would double-count. What this
    adds is the **empty-window** case, which no single margin can express -- two
    bounds can each be satisfiable while no depth satisfies both.

    Depths are measured from the coverslip's inner surface, which is the datum
    an acquisition has to establish before any of this is actionable.
    """
    a = setup.particle_radius_um
    uppers: list[tuple[float, str]] = []

    free_wd = free_working_distance_um(
        setup.objective.wd_um,
        setup.resolved_coverslip_um,
        setup.design_coverslip_um,
    )
    if free_wd is not None:
        uppers.append((free_wd, "L4.2 free working distance"))
    if setup.chamber_height_um is not None:
        uppers.append((setup.chamber_height_um, "L4.3 chamber height"))

    # L4.5 used to cap this at 1.85/dn -- 10 um for oil into water. It stopped
    # gating on 2026-09-10 (its threshold was anchored on a checklist trigger,
    # and the operator has imaged well past it), so the ceiling is now reach
    # and sample extent only. The mismatch is still reported, as the z-to-depth
    # conversion, and the aberration it implies is no longer bounded by
    # anything -- see check_ri_mismatch.
    dn = ri_mismatch(setup.resolved_n_sample, setup.n_immersion)

    limit = LIMITS["wall_drag_suppression"]
    lower = 9.0 * a / (16.0 * limit) if a is not None else None

    numbers = {
        "depth_min_um": None if lower is None else round(lower, 2),
        "depth_min_set_by": None if lower is None else "L4.4 near-wall drag",
        "upper_bounds_um": {name: round(v, 2) for v, name in uppers},
        "ri_mismatch": round(dn, 4),
        "unspaced_mount": setup.unspaced_mount,
    }

    if not uppers:
        return CheckResult(
            "geometry.depth_window",
            INFO,
            MAX_MARGIN,
            "info",
            "Depth window not bounded above (no working distance and no "
            "chamber height).",
            numbers=numbers,
        )

    upper, upper_by = min(uppers, key=lambda t: t[0])
    numbers["depth_max_um"] = round(upper, 2)
    numbers["depth_max_set_by"] = upper_by

    if lower is None:
        return CheckResult(
            "geometry.depth_window",
            INFO,
            MAX_MARGIN,
            "info",
            f"Focal plane may sit anywhere up to {upper:.1f} um above the "
            f"coverslip ({upper_by}). No lower bound computed -- "
            "particle_radius_um is what sets it, via L4.4.",
            numbers=numbers,
        )

    numbers["window_um"] = round(upper - lower, 2)

    if lower <= upper:
        return CheckResult(
            "geometry.depth_window",
            INFO,
            MAX_MARGIN,
            "info",
            f"Usable focal depth **{lower:.1f} to {upper:.1f} um** above the "
            f"coverslip: floor from {numbers['depth_min_set_by']} "
            f"(a = {a:.2f} um), ceiling from {upper_by}. Work near the top of "
            "the band -- the wall term falls as 1/h and nothing else in the "
            "window prefers the bottom.",
            numbers=numbers,
        )

    return CheckResult(
        "geometry.depth_window.empty",
        BIAS,
        upper / lower if lower > 0 else 0.0,
        "warn",
        f"NO depth satisfies both ends. The near-wall drag bound needs "
        f"h >= {lower:.1f} um for a {a:.2f} um-radius particle, and "
        f"{upper_by} caps h at {upper:.1f} um. Every depth in this "
        f"configuration is either too close to the wall or past the "
        f"{upper_by.split()[0]} limit -- the two bounds are individually "
        "satisfiable and jointly are not, which is why no single margin says "
        "so.",
        action="Use a smaller particle (the floor scales with radius), or an "
        "objective whose ceiling is higher -- an index-matched one removes the "
        "L4.5 term entirely. Otherwise accept the wall bias with its bound "
        "stated and hand it to lens 6.",
        numbers=numbers,
    )


def check_ri_mismatch(setup: "SampleSetup") -> CheckResult:
    """L4.5 (was G17): the mechanical-z to optical-depth conversion. **INFO since
    2026-09-10** -- it reports, it does not gate.

    Why it stopped gating (KH, 2026-09-10): the screening product
    `depth x |dn| <= 1.85 um` was anchored circularly -- 1.85 is
    `10 um x 0.185`, i.e. docs/05's checklist trigger "does the imaging depth
    exceed 10 um" evaluated at the oil-into-water case and then generalised.
    So for oil into water the "tolerable depth" it produced was 10 um *by
    construction*, and it was capping the depth window on a number that came
    from a checklist rather than from this instrument. The operator has imaged
    a bead well at ~9 um through the 100x Oil, which is the observation that
    outranks a screening heuristic (CLAUDE.md §3).

    **What it reports instead is the number that is actually used.** Focus is
    driven by ZDrive and piezo, and those read out **mechanical travel**. The
    focal plane inside the medium moves by `n_sample/n_immersion` times that
    travel, because the refraction happens at the coverslip interface -- and
    the factor is the same whether the objective or the stage moves, since
    either way it is the interface-to-nominal-focus distance that changes. So
    a z reading is not a depth, and this is the conversion between them, both
    ways.

    ``SampleSetup.imaging_depth_um`` is defined as the **real** depth past the
    coverslip, so nothing downstream needs adjusting -- L4.4's wall distance
    and the depth window are already in the right units. What this check does
    is tell the operator which number to put there.

    **Paraxial first order only.** Ray by ray at NA 1.45 into water the ratio
    runs 0.878 near the axis down to 0.376 at NA_ray 1.3, and rays past
    NA 1.333 are totally internally reflected and never arrive. That spread
    *is* the spherical aberration -- there is no single focal plane -- so the
    number below is the optimistic end of a bracket, not a correction factor.
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
        return CheckResult(
            "geometry.ri_mismatch",
            INFO,
            MAX_MARGIN,
            "info",
            f"Index-matched: mismatch {dn:.4f} between "
            f"{setup.objective.immersion} (n = {n_i:.3f}) and the sample "
            f"medium (n = {n_s:.3f}). Mechanical z travel IS optical depth "
            "here -- no conversion, and no depth-dependent mismatch "
            "aberration.",
            numbers=numbers,
        )

    if depth is not None:
        numbers["z_travel_for_this_depth_um"] = round(depth / shift, 2)
        numbers["depth_at_this_z_travel_um"] = round(depth * shift, 2)
        detail = (
            f" Both ways at {depth:.1f} um: commanding {depth:.1f} um of z "
            f"reaches only {depth * shift:.2f} um of real depth, and reaching "
            f"{depth:.1f} um of real depth needs {depth / shift:.2f} um of z."
        )
    else:
        detail = ""

    return CheckResult(
        "geometry.ri_mismatch",
        INFO,
        MAX_MARGIN,
        "info",
        f"Mismatch {dn:.3f} ({setup.objective.immersion} n = {n_i:.3f} vs "
        f"sample medium n = {n_s:.3f}). **Mechanical z travel is not optical "
        f"depth**: multiply z by {shift:.4f} to get depth, divide to go back "
        f"-- a {abs(1.0 - shift) * 100:.1f}% axial scale error if uncorrected."
        + detail,
        action="Paraxial first order. At NA 1.45 into water the per-ray ratio "
        "runs 0.878 near the axis to 0.376 at NA_ray 1.3, and rays past "
        "NA 1.333 do not arrive at all -- that spread is the spherical "
        "aberration, so use this to convert a z reading, not to report a "
        "corrected depth.",
        numbers=numbers,
    )


def check_count_in_field(setup: "SampleSetup") -> CheckResult:
    """L4.6 (was G19): how crowded the coverslip gets once **everything** has sedimented.

    REWRITTEN 2026-09-10 (KH). It used to count particles in an observed
    *volume*, and that was unreliable for two reasons the operator named: bulk
    concentration is hard to predict in the first place, and a preparation
    loses particles to the walls and the pipette. Worse, the volume came from
    `resolved_slab()`, whose default is the depth of field -- 377 nm against a
    4950 nm bead, so the count came out ~260x low and fed lens 6's G11 that
    way.

    So the model changed rather than the number. **Assume total sedimentation:**
    the whole column above a patch of coverslip ends up on that patch, giving
    an areal density `sigma = c * H` with no slab to guess. That is the worst
    case for crowding -- nothing stays up, nothing is lost -- so a dilution
    derived from it is a **floor**, and every real preparation is sparser.
    docs/01 §3 Principle 1b: bound it, do not estimate it.

    Concentration comes from the vendor's %solids (w/v) through the polymer's
    literature density and a sphere of the recorded mean diameter. Both are
    approximations and deliberately so; the lot CV alone (7.9 % on diameter
    for the Bangs bead) is +-24 % on volume.

    **The separability limit is the particle, not the optics, for anything
    bigger than the PSF.** Two 5 um beads stop being resolvable when they
    touch, at 4.95 um centre-to-centre, long before 3x the 219 nm Rayleigh
    limit matters. So the requirement is `max(2a, 3 * Rayleigh)` -- the old
    check compared against the resolution term alone, which is right only for
    sub-diffraction tracers.

    INFO, unchanged: whether the count is *enough* is G11's call, and a
    missing concentration must not take the rest of the lens down.
    """
    a = setup.particle_radius_um
    h = setup.chamber_height_um
    w, hf = setup.field_width_um, setup.field_height_um
    c, source = setup.resolved_concentration_per_ml

    missing = [
        n
        for n, v in (
            ("particle_radius_um", a),
            ("chamber_height_um", h),
            ("concentration (solids_fraction_w_v + density_g_cm3, or concentration_per_ml)", c),
        )
        if v is None
    ]
    if missing:
        return _ok(
            "geometry.count_in_field",
            INFO,
            MAX_MARGIN,
            "Settled crowding not evaluated (missing: " + ", ".join(missing) + ").",
            evaluated=False,
        )

    sigma = settled_areal_density_per_um2(c, h)
    coverage = areal_coverage_fraction(sigma, a)
    spacing = mean_areal_spacing_um(sigma)

    required = 2.0 * a
    basis = "particle diameter (touching)"
    if setup.emission_nm is not None:
        rayleigh = setup.objective.resolution_nm(setup.emission_nm) / 1e3
        optical = LIMITS["overlap_resolution_multiple"] * rayleigh
        if optical > required:
            required, basis = optical, f"{LIMITS['overlap_resolution_multiple']:.0f}x Rayleigh"

    numbers = {
        "evaluated": True,
        "concentration_per_ml": c,
        "concentration_source": source,
        "dilution_factor": setup.dilution_factor,
        "settled_areal_density_per_um2": round(sigma, 6),
        "areal_coverage_fraction": round(coverage, 4),
        "mean_spacing_um": None if spacing is None else round(spacing, 2),
        "required_spacing_um": round(required, 3),
        "required_spacing_basis": basis,
    }

    if w is not None and hf is not None:
        count = sigma * w * hf
        numbers["expected_count"] = round(count, 3)
        target = setup.target_particles_in_field
        if count > 0 and target > 0:
            numbers["min_dilution_factor"] = round(
                setup.dilution_factor * count / target, 1
            )
            numbers["target_particles_in_field"] = target

    dil = numbers.get("min_dilution_factor")
    dil_txt = (
        f" To reach {numbers.get('target_particles_in_field', 1):g} in the "
        f"{w:.0f}x{hf:.0f} um field, dilute the stock at least {dil:g}x."
        if dil
        else ""
    )

    if coverage >= 0.5:
        return CheckResult(
            "geometry.count_in_field.jammed",
            BIAS,
            0.5 / coverage,
            "warn",
            f"Settled monolayer would cover {coverage * 100:.0f}% of the "
            f"coverslip -- jammed, so the Poisson spacing below is meaningless "
            f"and particles are in contact. Concentration from {source}, "
            f"diluted {setup.dilution_factor:g}x, in a {h:.0f} um chamber."
            + dil_txt,
            action="Dilute. This is an upper bound on crowding (total "
            "sedimentation, no losses), so the real layer is sparser -- but "
            "not by the factor this needs.",
            numbers=numbers,
        )

    margin = (spacing / required) if spacing and required > 0 else MAX_MARGIN
    if margin >= 1.0:
        return CheckResult(
            "geometry.count_in_field",
            INFO,
            margin,
            "info",
            f"Once settled: {sigma:.4f} particles/um^2, {coverage * 100:.1f}% "
            f"areal coverage, mean spacing {spacing:.1f} um against "
            f"{required:.2f} um required ({basis}). Separable."
            + dil_txt,
            numbers=numbers,
        )

    return CheckResult(
        "geometry.count_in_field.crowded",
        BIAS,
        margin,
        "warn",
        f"Once settled, mean spacing {spacing:.1f} um is below the "
        f"{required:.2f} um two particles need to stay separable ({basis}); "
        f"{coverage * 100:.1f}% areal coverage. Tracking will swap identities "
        f"-- 2026-09-03 §10 is what that looks like." + dil_txt,
        action="Dilute the stock. The figure above assumes total sedimentation "
        "and no preparation losses, so it is a floor on the dilution, not an "
        "estimate of it.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("na_feasibility", HARD, ("na",), check_na_feasibility),
    Check("working_distance", HARD, ("imaging_depth", "working_distance"), check_working_distance),
    # L4.3: HARD, but `requires` is empty on purpose. A missing chamber height
    # must skip the check, not BLOCK the gate -- see check_depth_in_chamber.
    Check("depth_in_chamber", HARD, (), check_depth_in_chamber),
    # L4.4: BIAS, no `requires` -- an absent particle radius skips the bound
    # rather than BLOCKing, same as L4.3 and L4.6.
    Check("wall_drag", BIAS, (), check_wall_drag),
    # L4.5: INFO since 2026-09-10 -- a z-to-depth converter, not a gate.
    Check("ri_mismatch", INFO, (), check_ri_mismatch),
    Check("count_in_field", INFO, (), check_count_in_field),
    Check("depth_window", INFO, (), check_depth_window),
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
