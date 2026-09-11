"""Lens 9 -- the system's velocity (conditional, whenever something moves).

Owns the **scale and the consequences of a commanded motion**: the piezo
stage's ramps and the AOD trap's sweeps together, which is why it is the
system's velocity and not the stage's.

    from velocity import VelocitySetup, evaluate

    v = evaluate(VelocitySetup(
        commanded_velocity_um_per_s=20.0, driver="piezo_stage",
        step_duration_ms=60.0,
        particle_radius_um=2.5, viscosity_pa_s=1.0e-3,
        stiffness_pn_per_um=3.87,      # lens 7
        localization_sigma_nm=10.0,    # lens 2
        achieved_fps=520.0,            # lens 2, provenance from lens 3
        target_relative_error=0.05,
    ))

Checks: L9.1 time base, L9.2 displacement window, L9.3 steady state,
L9.4 Reynolds (info), L9.5 time-axis owner (info).

**Created 2026-09-11 (KH)** after the review found that nothing in this
repository records a commanded-versus-actual motion scale, while a Stokes-drag
calibration multiplies the commanded velocity straight into
``kappa = gamma v / x_eq``. That is an unbounded scale error on the measured
stiffness -- the same shape as the pixel-size error in docs/06 A1, and
unguarded.

Three things worth knowing before reading a verdict:

- **`LIMITS` is empty and stays empty.** Every bound is derived from the
  caller's `target_relative_error` -- the offset floor is `sigma/target`, the
  step duration is `ln(1/target)` time constants -- or from a limit the trap
  model states about itself (`trap_force` refuses past the bead radius). A
  velocity window is meaningless without a stated precision, and picking a
  multiple would be originating a physical number.
- **L9.1 FAILS on every real configuration today**, and that is the finding
  rather than a defect. The DISTANCE half of the scale is corroborated -- two
  length standards over 10 um agreeing to 0.24 % on 2026-09-03 -- and the TIME
  half has never been checked. A closed-loop controller reporting position does
  not settle it: the loop holds its own scale, which is the question.
- **It does not own the time axis.** Lens 2 owns the frame rate and lens 3's
  L3.2 owns whether that rate is achieved or requested. L9.5 names them and
  reports what this lens inherits, rather than re-deriving either.

Conditional, like lenses 7 and 8: convened when the experiment commands a
motion. Absent is a hole and not a pass (CLAUDE.md E4).
kb/decisions/2026-09-11-the-velocity-lens.md
"""

from __future__ import annotations

from .checks import CHECKS, GRADE_NOTES, LIMITS, CheckResult, grade
from .gate import Finding, Verdict, evaluate
from .kinematics import (
    WATER_DENSITY_KG_M3,
    drag_coefficient_pn_s_per_um,
    equilibrium_offset_um,
    minimum_offset_um,
    reynolds_number,
    reynolds_unity_velocity_um_per_s,
    settling_time_constants,
    velocity_for_offset_um_per_s,
)
from .setup import DRIVERS, VelocitySetup

__all__ = [
    "CHECKS",
    "DRIVERS",
    "GRADE_NOTES",
    "LIMITS",
    "WATER_DENSITY_KG_M3",
    "CheckResult",
    "Finding",
    "Verdict",
    "VelocitySetup",
    "drag_coefficient_pn_s_per_um",
    "equilibrium_offset_um",
    "evaluate",
    "grade",
    "minimum_offset_um",
    "reynolds_number",
    "reynolds_unity_velocity_um_per_s",
    "settling_time_constants",
    "velocity_for_offset_um_per_s",
]
