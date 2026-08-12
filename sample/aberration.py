"""Sample geometry and optics: the physics behind lens 4's gates.

Pure functions, no gate logic -- mirrors compute/resources.py and
trapping/dynamics.py. docs/05-consensus-gate.md "Lens 4";
docs/06-pitfalls.md D5.

The refractive indices this module compares are recorded in
kb/expertise/immersion-media-in-use.md (immersion: oil 1.518 Nikon Type F,
water 1.333) and kb/expertise/sample-medium-refractive-index.md (sample
medium: 1.333 default, **assumed**, water-based).
"""

from __future__ import annotations

import math

#: Coverslip design thickness the objectives are corrected for, um.
#: Nikon #1.5 nominal. kb/systems/current.md > objectives records
#: cover_glass_mm 0.17 for every objective except the 40x WI (0.15-0.19).
COVERSLIP_DESIGN_UM = 170.0

#: #1.5 vendor tolerance, um. docs/06-pitfalls.md notes the real spread is
#: wider than this, which is why a measured value beats the nominal.
COVERSLIP_TOLERANCE_UM = 5.0


def ri_mismatch(n_sample: float, n_immersion: float) -> float:
    """Absolute refractive-index mismatch across the coverslip.

    0.185 for an oil objective (1.518) looking into a water-based medium
    (1.333) -- the case kb/expertise/sample-medium-refractive-index.md
    quantifies. 0.0 for the 40x WI in the same medium.
    """
    return abs(n_sample - n_immersion)


def paraxial_focal_shift_ratio(n_sample: float, n_immersion: float) -> float:
    """Actual focal depth per unit of nominal z travel, ``n_sample/n_immersion``.

    0.878 for oil into water: 10 um of commanded z is ~8.78 um of real
    depth, a 12.2% axial scaling error if uncorrected.

    **Paraxial first order only.** At NA 1.42-1.45 the high-angle rays focus
    differently and the effective shift is depth- and NA-dependent, so this
    is a screening number for "does the correction matter", never a
    corrected depth to report. docs/05-consensus-gate.md forbids passing an
    approximation off as an answer.
    """
    if n_immersion <= 0:
        raise ValueError("n_immersion must be positive")
    return n_sample / n_immersion


def max_na(n_immersion: float) -> float:
    """The largest NA physically reachable in this immersion medium.

    ``NA = n sin(theta) <= n``. Exact, not an approximation: an objective
    whose engraved NA exceeds its immersion index is either mislabelled or
    being used in the wrong medium.
    """
    return float(n_immersion)


def collection_half_angle_deg(na: float, n_immersion: float) -> float | None:
    """Half-angle of the collection cone, degrees, or None if NA > n.

    ``optics.components.Objective.collection_efficiency`` silently clamps
    this case with ``min(na/n, 1.0)``; returning None instead is what lets
    the gate refuse rather than emit a plausible number for an impossible
    configuration.
    """
    if n_immersion <= 0 or na > n_immersion:
        return None
    return math.degrees(math.asin(na / n_immersion))


def free_working_distance_um(
    wd_um: float,
    coverslip_actual_um: float,
    coverslip_design_um: float = COVERSLIP_DESIGN_UM,
) -> float:
    """Working distance still available for imaging into the sample, um.

    Vendor WD is quoted to the specimen-facing surface of the design
    coverslip, so the design thickness is already inside the spec and must
    not be subtracted again -- the 100x Oil's WD of 130 um against a 170 um
    coverslip only makes sense on that reading. Only the *excess* over
    design eats into the budget.
    """
    excess = max(0.0, coverslip_actual_um - coverslip_design_um)
    return wd_um - excess


def particles_in_field(
    concentration_per_ml: float,
    field_width_um: float,
    field_height_um: float,
    depth_um: float,
) -> float:
    """Expected particle count in the observed volume.

    1 mL = 1e12 um^3.
    """
    volume_um3 = field_width_um * field_height_um * depth_um
    return concentration_per_ml * volume_um3 / 1e12


def mean_nearest_neighbour_um(concentration_per_ml: float) -> float | None:
    """Mean nearest-neighbour distance for a random 3D suspension, um.

    ``0.554 n^(-1/3)`` for a Poisson point process. Used to judge overlap:
    if this approaches the PSF width, single-particle tracking stops being
    single-particle.
    """
    if concentration_per_ml <= 0:
        return None
    per_um3 = concentration_per_ml / 1e12
    return 0.554 * per_um3 ** (-1.0 / 3.0)
