"""Ray-optics verification of the GOA MATLAB trap-force model.

Committee lens #7 in the making (docs/01-architecture.md "조건부 소집"), kept
deliberately narrow for now: a single homogeneous sphere in the ray-optics
regime, ported from ``D:\\codes\\Geometric_optics_approximation\\GOA_ab.m``,
plus the two facts that script does not model -- a 0-100% software power
dial and power-splitting across simultaneous traps.

    from trapping import Bead, Medium, ObjectiveBeam, trap_force
    from trapping import LaserCalibration, power_per_trap
    from trapping import TrapSetup, water_viscosity_pa_s, evaluate

    bead = Bead(radius_m=2.5e-6, n=1.45)       # silica
    cal = LaserCalibration(placeholder_max_w=1.0)   # measured=False until calibrated
    medium = Medium(n=1.33, viscosity_pa_s=water_viscosity_pa_s(20.0))  # water @ 20C
    beam = ObjectiveBeam(na=1.33, wavelength_m=1064e-9)

    setup = TrapSetup(bead=bead, medium=medium, beam=beam, calibration=cal, dial_percent=50)
    verdict = evaluate(setup)   # confinement, trap depth (U/kT), G14 sampling

Committee-gate schema (``Check`` / ``CheckResult`` / ``Verdict``) now mirrors
``optics.gate`` (docs/08 "다른 렌즈에도 같은 구조를 쓴다"). Still not covered:
Janus/coated beads, ellipsoids, birefringent LC droplets (only ``GOA_ab.m``
is ported), and a measured dial%->mW calibration curve.
"""

from .checks import CHECKS, Check, CheckResult
from .dynamics import (
    TrapSetup,
    corner_frequency_hz,
    trap_depth_kt,
    water_viscosity_pa_s,
)
from .gate import Finding, Verdict, evaluate
from .goa import (
    Bead,
    Medium,
    ObjectiveBeam,
    ray_optics_regime,
    radial_stiffness_n_per_m,
    trap_force,
)
from .laser import LaserCalibration, power_per_trap

__all__ = [
    "Bead",
    "CHECKS",
    "Check",
    "CheckResult",
    "Finding",
    "LaserCalibration",
    "Medium",
    "ObjectiveBeam",
    "TrapSetup",
    "Verdict",
    "corner_frequency_hz",
    "evaluate",
    "power_per_trap",
    "radial_stiffness_n_per_m",
    "ray_optics_regime",
    "trap_depth_kt",
    "trap_force",
    "water_viscosity_pa_s",
]
