"""Individual sample-geometry checks -- G15 (NA feasibility), G16 (working
distance), G16b (depth within chamber), G16c (near-wall drag bound),
G17 (refractive-index mismatch), G19 (count in field), plus the depth window
that reports G16/G16b/G16c/G17's bounds as one band.

G18 (coverslip thickness) was REMOVED 2026-09-10 and its number is not reused
-- kb/decisions/2026-09-10-lens-4-depth-window-and-g18-removed.md. The
coverslip is still in this lens twice: G16 subtracts its excess over design
from the working-distance budget, and an unmeasured coverslip is still an
`assumed_input` that withholds `advances`. What went is the graded margin.
docs/05-consensus-gate.md "Lens 4";
docs/06-pitfalls.md D5.

G15-G19 are new numbers: docs assigned lens 4 no gate IDs, and G1-G14 were
taken by lenses 1/2/3/5/6/7. G16b follows lens 3's convention of suffixing an
extra criterion onto its nearest gate (G12a-c, G13a-d) rather than extending
the top of the range: it pairs with G16, which asks whether the objective can
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
    collection_half_angle_deg,
    free_working_distance_um,
    max_na,
    mean_nearest_neighbour_um,
    paraxial_focal_shift_ratio,
    particles_in_field,
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
    #: G19: mean nearest-neighbour distance must exceed this multiple of the
    #: Rayleigh resolution for particles to be separable.
    "overlap_resolution_multiple": 3.0,
    #: G16c: fractional suppression of D by the nearby wall that an untrapped
    #: measurement may carry unabsorbed. An **order-of-magnitude screen**, not a
    #: precision threshold (docs/01 §3 Principle 1b): 10% sits with this repo's
    #: other bias limits (G10 bleaching at 20%, G8 blur at 0.3 tau) and just
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


def check_depth_in_chamber(setup: "SampleSetup") -> CheckResult:
    """G16b: is there any sample at the depth being focused to?

    G16 asks whether the objective can *reach* the depth. This asks whether the
    sample *extends* that far. Focus past the chamber's far wall and you image
    the wall, and nothing else in the committee notices: lens 8 holds
    ``chamber_height_um`` but spends it only on the sedimentation flag
    (``stability/checks.py`` G31), and lens 4 owned the imaging depth without
    ever seeing the height.

    HARD in character -- past the far wall the data is not biased, it is of
    something else -- but registered with **no** ``requires``, so an absent
    chamber height skips the check instead of BLOCKing the whole gate. Same
    reasoning as G19: a fact the user often does not have to hand must not take
    the rest of the lens down with it.

    Note what this check does not need: the spacer or gasket setting the height
    is not in the optical path (either orientation of stand), so it never enters
    the working-distance budget. Only the coverslip does, via G16.
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
    """G16c: bound the near-wall drag bias on D, rather than merely naming it.

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
    as INFO. Untrapped, nothing absorbs it and the bound is the answer, so it
    goes BIAS and warns past the screening limit.
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
        return _ok(
            "geometry.wall_drag",
            INFO,
            MAX_MARGIN,
            f"D is suppressed by at most {pct:.1f}% at {h:.1f} um from the "
            f"wall (a = {a:.2f} um). The trap absorbs this: an in-situ "
            "power-spectrum calibration at the working height returns kappa "
            "and the wall-corrected drag together (docs/06 D8). Redo that "
            "calibration if the working height changes.",
            **numbers,
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
    """The usable band of focal depths, both ends, in one place.

    G16, G16b, G16c and G17 each bound the imaging depth, and until 2026-09-10
    a reader had to collect four margins and invert them by hand to learn where
    the focal plane may actually sit. Requested by KH: report the window.

    Which gate owns which end:

        LOWER  G16c  near-wall drag. Working close to the coverslip is the
                     thing to avoid, so this is a floor: 9a/(16h) <= limit
                     gives h >= 9a/(16*limit).
        UPPER  G16   free working distance -- how far the objective reaches.
              G16b   chamber height -- how far the SAMPLE extends. The spacer
                     correction on the same budget.
              G17    depth x |dn| screening limit, when the media are
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
        uppers.append((free_wd, "G16 free working distance"))
    if setup.chamber_height_um is not None:
        uppers.append((setup.chamber_height_um, "G16b chamber height"))

    dn = ri_mismatch(setup.resolved_n_sample, setup.n_immersion)
    if dn > LIMITS["matched_ri_tolerance"]:
        uppers.append(
            (LIMITS["aberration_depth_mismatch_um"] / dn, "G17 index mismatch")
        )

    limit = LIMITS["wall_drag_suppression"]
    lower = 9.0 * a / (16.0 * limit) if a is not None else None

    numbers = {
        "depth_min_um": None if lower is None else round(lower, 2),
        "depth_min_set_by": None if lower is None else "G16c near-wall drag",
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
            "particle_radius_um is what sets it, via G16c.",
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
        "G17 term entirely. Otherwise accept the wall bias with its bound "
        "stated and hand it to lens 6.",
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


def check_count_in_field(setup: "SampleSetup") -> CheckResult:
    """G19: expected particle count and overlap in the observed volume.

    INFO, so a missing concentration leaves the rest of the gate runnable.
    Whether the count is *enough* is statistical power -- G11, lens 6 -- not
    this lens's call. What this lens owns is whether particles are so dense
    that they stop being separable.

    The count is taken over ``setup.resolved_slab()``, not over the imaging
    depth. The two are the same only for a widefield column; for a sectioning
    modality the depth is far larger, and this count is what
    ``validity/setup.py::resolved_n_particles`` hands to G11, so an
    over-generous extent lands as an overestimate of statistical power.
    ``axial_extent_source`` in the numbers says which extent was used.

    The separability half (``mean_NN``) is computed from bulk concentration and
    is unaffected by any of this.
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

    slab, slab_source = setup.resolved_slab()
    count = particles_in_field(c, w, h, slab)
    nn = mean_nearest_neighbour_um(c)
    numbers = {
        "expected_count": round(count, 1),
        "concentration_per_ml": c,
        "field_um": [w, h],
        "depth_um": depth,
        "axial_extent_um": round(slab, 3),
        "axial_extent_source": slab_source,
        "mean_nn_distance_um": round(nn, 3) if nn else None,
        "evaluated": True,
    }

    extent = (
        f"counted over a {slab:.2f} um axial extent ({slab_source.replace('_', ' ')})"
    )
    if slab_source == "imaging_depth":
        extent += " -- no emission wavelength to size the depth of field, so "
        extent += "this is the whole column and an upper bound"

    if setup.emission_nm is None or nn is None:
        head = (
            f"About {count:.0f} particles expected in the observed volume, "
            f"{extent}"
        )
        if nn:
            head += f"; mean nearest-neighbour distance {nn:.2f} um"
        return _ok(
            "geometry.count_in_field",
            INFO,
            MAX_MARGIN,
            head + ".",
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
            f"About {count:.0f} particles in the observed volume ({extent}), "
            f"mean nearest-neighbour {nn:.2f} um against a "
            f"{resolution_um:.2f} um resolution -- separable.",
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
    # G16b: HARD, but `requires` is empty on purpose. A missing chamber height
    # must skip the check, not BLOCK the gate -- see check_depth_in_chamber.
    Check("depth_in_chamber", HARD, (), check_depth_in_chamber),
    # G16c: BIAS, no `requires` -- an absent particle radius skips the bound
    # rather than BLOCKing, same as G16b and G19.
    Check("wall_drag", BIAS, (), check_wall_drag),
    Check("ri_mismatch", BIAS, ("imaging_depth",), check_ri_mismatch),
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
