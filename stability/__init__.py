"""Lens 8 -- mechanical and environmental (conditional, long acquisitions).

Owns sedimentation and evaporation -- what the sample does to itself over
time. Drift, PFS lock state, vibration and stage repeatability are lens 8's
subject matter too, but none of them is GATED here; see below.
docs/05-consensus-gate.md "Lens 8"; docs/06-pitfalls.md D7.

    from optics.components import find_objective
    from stability import StabilitySetup, evaluate

    v = evaluate(StabilitySetup(
        duration_min=60.0,
        objective=find_objective("100x-Oil"), emission_nm=520.0,
        particle_radius_um=0.5, delta_density_kg_m3=50.0,
        viscosity_pa_s=1.0e-3,
    ))

Gates: G31 sedimentation, G32 evaporation. G28, G29 and G30 were here and are
vacant -- see below.

Conditional on acquisitions longer than 30 min (docs/01 §4). That threshold is
**reported, not enforced**: settling and drift scale continuously with time and
do not switch on at 30 minutes, so when this lens is called it answers.

What it can and cannot do, honestly:

- **G28 (PFS lock) is gone**, to the hardware execution stage (2026-09-10).
  It read `PFS in Range` as the servo state and that property reports the
  coverslip; `hardware/focus.py` asks MMCore's autofocus API instead.
- **G31 works today** because Stokes settling follows from particle radius,
  density contrast and viscosity -- sample properties, not instrument
  measurements. It bites hard: a 1 um polystyrene sphere in water settles about
  49 um in 30 minutes, against a 0.375 um depth of field on the 100x oil.
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
- **Vibration and stage repeatability are ungated**, and the lens says so
  rather than passing quietly. There is no measurement channel for either.
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
