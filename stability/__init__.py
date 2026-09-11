"""Lens 8 -- mechanical and environmental (conditional, long acquisitions).

**A REPORTING SECTION, NOT A JUDGING LENS, SINCE 2026-09-10** -- the second
one, after lens 5 the same day. Every check is INFO, `LIMITS` is empty,
`evaluate` returns `status: REPORT` with `feasibility: "N/A"` and
`advances: None`. Nothing here can pass or fail.

Reports what the sample and the plan settle between them: the settling velocity
and the time until the suspension is over, the evaporative concentration if a
rate exists, and the drift rate the run could absorb. Drift, PFS lock state and
stage repeatability are lens 8's subject matter too but are judged elsewhere;
vibration is judged nowhere, on purpose. See below.
docs/05-consensus-gate.md "Lens 8"; docs/06-pitfalls.md D7.

    from optics.components import find_objective
    from stability import StabilitySetup, evaluate

    v = evaluate(StabilitySetup(
        duration_min=60.0,
        objective=find_objective("100x-Oil"), emission_nm=520.0,
        particle_radius_um=0.5, delta_density_kg_m3=50.0,
        viscosity_pa_s=1.0e-3,
    ))

Gate numbers: G31 (sedimentation) and G32 (evaporation) still name the two
reports, though neither grades any more. G28, G29 and G30 were here and are
vacant -- see below.

Conditional on acquisitions longer than 30 min (docs/01 §4). That threshold is
**reported, not enforced**: settling and drift scale continuously with time and
do not switch on at 30 minutes, so when this lens is called it answers.

What it can and cannot do, honestly:

- **G28 (PFS lock) is gone**, to the hardware execution stage (2026-09-10).
  It read `PFS in Range` as the servo state and that property reports the
  coverslip; `hardware/focus.py` asks MMCore's autofocus API instead.
- **G31 reports a velocity and a clock, and no longer a verdict.** It used to
  compare a whole run's settling against the depth of field, which called every
  real bead INFEASIBLE -- 5 um polystyrene in water moves 41 um/min against
  0.375 um -- including the experiments that work, because **a trapped bead
  does not settle** (gravity's axial sag is the buoyant weight over kappa_z --
  0.032 pN, so 32 nm per pN/um -- and kappa_z is computed nowhere in this
  repository, so the number cannot be closed) and this lens has no `trapped`
  field to tell the two apart. The
  free-settling case is lens 4's G19, which *assumes* the settled state; what
  this reports is when that state arrives. 100 um chamber, 5 um bead: 2.4 min.
- **G32 reports because sealing is declarable and a rate is not.** A sealed
  chamber settles the question outright. Unsealed without a weighed rate, the
  old gate returned a stand-in margin of 0.5 -- a number invented to mean "not
  quantified", which graded HARD and blocked `advances` on an acquisition
  nobody had measured anything about.
- **G29 and G30 are gone**, to the same place, on the same day, for a reason
  that generalises G28's: *"if it has to be measured during the experiment, it
  is not suitable as a design element"* (KH). Both rates are obtainable on this
  instrument -- `config/session/focus_monitor.py` already samples ZDrive and
  both cameras, and most of the bead population is stuck to the coverslip and
  serves as a lateral fiducial -- but obtainable *from the acquisition* is the
  wrong timing for a gate on a proposal. `compute.drops` is the precedent for
  where that judgement belongs.
  kb/decisions/2026-09-10-drift-is-not-a-design-element.md
- **What replaced them reports instead of gating.** `stability.drift_budget`
  turns the question around: the duration and depth of field fix how much
  drift the run can absorb, so the lens states that requirement and leaves the
  measurement to the run. One division, no threshold.
- **Drift still costs the evidence tier.** The `assumed_inputs` entry for it is
  unconditional, so this lens cannot report `evidence: measured` and a long
  acquisition does not `advance` on lens 8 alone. Deliberate: the dominant
  bias on a long run is not discharged by planning it well.
- **Vibration is not here at all, and not because nobody built the channel.**
  The check that reported its own absence was deleted on 2026-09-10: **every
  part of this microscope sits on the same isolation table, so the camera and
  the sample move together.** An image shows their RELATIVE motion, and
  common-mode motion of a rigid assembly cancels out of it -- a stuck-bead PSD
  in the acquisition would not supply it either. Contrast drift, which is
  differential expansion in the path between objective and holder and therefore
  does show up; that asymmetry is why `drift_budget` survives and vibration
  does not.
- **Stage repeatability is still ungated** and has no check at all.
"""

from __future__ import annotations

from .checks import CHECKS, GRADE_NOTES, LIMITS, CheckResult, grade
from .drift import (
    G,
    concentration_factor,
    evaporated_fraction,
    settling_distance_um,
    stokes_settling_velocity_um_per_s,
    total_drift_nm,
)
from .gate import Finding, Verdict, evaluate
from .setup import CONVENE_DURATION_MIN, StabilitySetup

__all__ = [
    "CHECKS",
    "CONVENE_DURATION_MIN",
    "G",
    "GRADE_NOTES",
    "LIMITS",
    "CheckResult",
    "Finding",
    "StabilitySetup",
    "Verdict",
    "concentration_factor",
    "evaluate",
    "evaporated_fraction",
    "grade",
    "settling_distance_um",
    "stokes_settling_velocity_um_per_s",
    "total_drift_nm",
]
