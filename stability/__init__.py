"""Lens 8 -- mechanical and environmental (conditional, long acquisitions).

Owns drift (thermal and mechanical), PFS lock state, sedimentation,
evaporation, vibration and stage repeatability.
docs/05-consensus-gate.md "Lens 8"; docs/06-pitfalls.md D7.

    from optics.components import find_objective
    from stability import StabilitySetup, evaluate

    v = evaluate(StabilitySetup(
        duration_min=60.0,
        objective=find_objective("100x-Oil"), emission_nm=520.0,
        axial_drift_rate_nm_per_min=5.0,
        pfs_enabled=True, pfs_in_range=True,
        particle_radius_um=0.5, delta_density_kg_m3=50.0,
        viscosity_pa_s=1.0e-3,
    ))

Gates: G28 PFS lock, G29 axial drift, G30 lateral drift, G31 sedimentation,
G32 evaporation. New numbers -- lens 8 had none, because it had no code.

Conditional on acquisitions longer than 30 min (docs/01 §4). That threshold is
**reported, not enforced**: settling and drift scale continuously with time and
do not switch on at 30 minutes, so when this lens is called it answers.

What it can and cannot do, honestly:

- **G28 works today with no new measurement.** It is a state check on metadata
  that already exists, and it catches docs/06 D7: the archive has sessions with
  `PFS-FocusMaintenance: On` but `PFS in Range: Out of Range`. An unrecorded
  range flag is itself a failure, because the on state alone cannot tell a held
  focus from a wandered one.
- **G31 works today** because Stokes settling follows from particle radius,
  density contrast and viscosity -- sample properties, not instrument
  measurements. It bites hard: a 1 um polystyrene sphere in water settles about
  49 um in 30 minutes, against a 0.375 um depth of field on the 100x oil.
- **G29 BLOCKS.** No drift rate exists anywhere in the repo, and a guessed one
  would decide the gate wrongly in whichever direction the guess leaned.
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
