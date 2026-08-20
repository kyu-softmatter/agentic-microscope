"""Lens 6 -- measurement validity.

Owns whether the result of every other lens together yields the intended
physical quantity without bias. docs/04-decision-engine.md §7;
docs/05-consensus-gate.md "Lens 6"; docs/06-pitfalls.md A1, C1.

    from validity import ValiditySetup, evaluate

    v = evaluate(ValiditySetup(
        intended_quantity="diffusion",
        target_relative_error=0.05,
        upstream={"optics": v1, "detection": v2, "compute": v3,
                  "sample": v4, "photo": v5},
        n_frames=2000,
        pixel_size_measured=True,
    ))

Gates: G11 statistical power (specified in docs/04 §7, previously
unimplemented), G23 bias ledger, G24 pixel calibration, G25 photometric
calibration, G26 post-processing, G27 committee coverage.

**Call it last.** Unlike every other lens, its primary input is the other
lenses' verdicts rather than hardware facts, so it has nothing to review if it
runs first. G11 is the only quantity it computes; everything else reviews what
the committee already found.

Two things it does that no counting of verdicts would:

- **The verdict's unit can be a physical quantity, not the channel.** Pass
  ``intended_quantities`` and each is judged separately, because motion blur
  ruins the MSD of a session whose intensity profile is untouched
  (``evaluate_per_quantity``, and ``BIAS_SCOPE`` for which bias damages what).
- **A declared correction is checked, not believed.** ``CORRECTIONS`` lists the
  biases a correction exists for and ``UNCORRECTABLE`` the ones it does not, so
  naming ``geometry.ri_mismatch`` in ``corrections_applied`` no longer clears
  it. A code in neither registry is accepted but costs the verdict its
  ``measured`` grade.

Two consequences worth knowing:

- It reads every lens's verdict through a structural protocol
  (``VerdictLike``), because each lens defines its own copy of
  ``Verdict``/``Finding`` and ``trapping``'s has no ``feasibility`` field.
  That duplication is a known gap; structural typing is what lets this lens
  review all six without any lens importing another's types.
- G27 is currently the only place anything notices that the committee never
  convened. There is no orchestrator in the codebase -- each lens is invoked
  by its own CLI -- so a standing lens that never ran, or one that returned
  BLOCKED, would otherwise go unremarked.
"""

from __future__ import annotations

from .checks import CHECKS, GRADE_NOTES, LIMITS, CheckResult, grade
from .gate import Finding, Verdict, evaluate, evaluate_per_quantity
from .power import (
    relative_error,
    required_frames,
    required_particles,
    required_sample_product,
    roi_speed_tradeoff,
)
from .setup import (
    BIAS_SCOPE,
    CORRECTIONS,
    QUANTITY_REQUIREMENTS,
    STANDING_LENSES,
    UNCORRECTABLE,
    FindingLike,
    ValiditySetup,
    VerdictLike,
    calibrations_for,
)

__all__ = [
    "BIAS_SCOPE",
    "CHECKS",
    "CORRECTIONS",
    "GRADE_NOTES",
    "LIMITS",
    "QUANTITY_REQUIREMENTS",
    "STANDING_LENSES",
    "UNCORRECTABLE",
    "CheckResult",
    "Finding",
    "FindingLike",
    "ValiditySetup",
    "Verdict",
    "VerdictLike",
    "calibrations_for",
    "evaluate",
    "evaluate_per_quantity",
    "grade",
    "relative_error",
    "required_frames",
    "required_particles",
    "required_sample_product",
    "roi_speed_tradeoff",
]
