"""Lens 4 -- sample geometry and optics.

Owns objective choice, immersion, coverslip, imaging depth, chamber.
docs/05-consensus-gate.md "Lens 4"; docs/06-pitfalls.md D5.

    from optics.components import Objective
    from sample import SampleSetup, evaluate

    obj = Objective("6-Plan Apo LmbdD0.13 100x Oil", 100, 1.45, "oil",
                    wd_um=130.0, verified_na=True)
    verdict = evaluate(SampleSetup(objective=obj, imaging_depth_um=15.0))
    print(verdict.status, verdict.bottleneck)   # L4.1..L4.6

Gates: L4.1 NA feasibility, L4.2 working distance, L4.3 depth within
chamber, L4.4 near-wall drag bound, L4.5 refractive-index
mismatch, G18 coverslip thickness, L4.6 count in field. These numbers are
new -- docs assigned lens 4 none, and L1.1-L7.2–L7.4 were already taken.

The refractive indices come from kb/expertise/immersion-media-in-use.md and
kb/expertise/sample-medium-refractive-index.md. The sample-medium default of
1.333 was **confirmed 2026-08-19**, so leaving n_sample unset no longer
downgrades evidence; an unmeasured coverslip is what does. The media that
default does not cover (ATPS, glycerol, birefringent) still BLOCK.
"""

from __future__ import annotations

from .aberration import (
    COVERSLIP_DESIGN_UM,
    COVERSLIP_TOLERANCE_UM,
    collection_half_angle_deg,
    free_working_distance_um,
    max_na,
    mean_nearest_neighbour_um,
    paraxial_focal_shift_ratio,
    particles_in_field,
    ri_mismatch,
    wall_drag_suppression,
)
from .checks import CHECKS, GRADE_NOTES, LIMITS, CheckResult, grade
from .gate import Finding, Verdict, evaluate
from .setup import DEFAULT_N_SAMPLE, LAB_DEFAULT_COVERSLIP_UM, SampleSetup

__all__ = [
    "CHECKS",
    "COVERSLIP_DESIGN_UM",
    "COVERSLIP_TOLERANCE_UM",
    "DEFAULT_N_SAMPLE",
    "GRADE_NOTES",
    "LAB_DEFAULT_COVERSLIP_UM",
    "LIMITS",
    "CheckResult",
    "Finding",
    "SampleSetup",
    "Verdict",
    "collection_half_angle_deg",
    "evaluate",
    "free_working_distance_um",
    "grade",
    "max_na",
    "mean_nearest_neighbour_um",
    "paraxial_focal_shift_ratio",
    "particles_in_field",
    "ri_mismatch",
    "wall_drag_suppression",
]
