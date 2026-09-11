"""Lens 6 -- measurement validity.

Owns whether the result of every other lens together yields the intended
physical quantity without bias. docs/04-decision-engine.md §7;
docs/05-consensus-gate.md "Lens 6"; docs/06-pitfalls.md A1, C1.

    from validity import ValiditySetup, evaluate

    v = evaluate(ValiditySetup(
        intended_quantity="diffusion",
        upstream={"optics": v1, "detection": v2, "compute": v3, "sample": v4},
        pixel_size_measured=True,
    ))

Gates: L6.2 bias ledger, L6.3 pixel calibration, L6.4 photometric calibration,
L6.1 committee coverage.

**G11 AND G26 LEFT ON 2026-09-11 (KH) and neither number is reused.** G11 was
the only quantity this lens computed, and `1/sqrt(N_p x N_f)` counts
INDEPENDENT samples -- one trapped bead at 520 fps has 6.3 correlated frames
per relaxation time, so it was 3.5x optimistic about this instrument's own
measurement, and a drag calibration's precision comes from the number of
velocity steps instead. The arithmetic survives as a calculator:
`python -m validity.cli power`. G26 gated on a self-declared `despeckle`
boolean that nobody verified, and `detection/recommend.py` already refuses a
reference frame shot with it on -- the point at which despeckle destroys
something computable. kb/decisions/2026-09-11-g11-and-g26-removed.md

**Call it last.** Unlike every other lens, its primary input is the other
lenses' verdicts rather than hardware facts, so it has nothing to review if it
runs first. **It now computes nothing at all** -- every remaining check reads a
verdict or a declaration.

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
- L6.1 is currently the only place anything notices that the committee never
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
