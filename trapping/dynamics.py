"""Trap dynamics quantities beyond the raw ray-optics force model.

``trapping.goa`` computes force and stiffness at a single displacement;
this module adds the quantities a trapping verdict actually needs to judge
a configuration -- water viscosity (for the ones without a measured
value), corner frequency, and trap depth in units of k_B*T -- plus
``TrapSetup``, which bundles a configuration the way ``optics.path.Channel``
does for the optical lens.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .goa import Bead, Medium, ObjectiveBeam, trap_force
from .laser import LaserCalibration, power_per_trap

K_BOLTZMANN = 1.380649e-23  # J/K, exact SI definition

# CRC Handbook of Chemistry and Physics dynamic viscosity of water, mPa*s
# (= cP), at 1 atm. A lookup table, linearly interpolated -- not a fitted
# formula, so it is only as good as the nearest two entries.
_WATER_VISCOSITY_MPA_S = {
    0.0: 1.7910,
    5.0: 1.5192,
    10.0: 1.3059,
    15.0: 1.1382,
    20.0: 1.0016,
    25.0: 0.8905,
    30.0: 0.7972,
    35.0: 0.7194,
    40.0: 0.6529,
}


def water_viscosity_pa_s(temperature_c: float = 20.0) -> float:
    """Dynamic viscosity of pure water at ``temperature_c``.

    Defaults to 20 C -- this project's standing room-temperature assumption
    when no other temperature is specified (2026-08-10). Linearly
    interpolated from the CRC table above; raises outside 0-40 C rather
    than extrapolate, since that would be a guess, not a lookup.

    Only valid for water. A different medium (an ATPS phase, a
    density-matched buffer) needs its own measured or literature viscosity.
    """
    temps = sorted(_WATER_VISCOSITY_MPA_S)
    if not temps[0] <= temperature_c <= temps[-1]:
        raise ValueError(
            f"temperature_c={temperature_c} is outside the tabulated "
            f"{temps[0]}-{temps[-1]} C range; extrapolating water viscosity "
            "would be a guess, not a lookup."
        )
    mpa_s = float(np.interp(temperature_c, temps, [_WATER_VISCOSITY_MPA_S[t] for t in temps]))
    return mpa_s * 1e-3


def corner_frequency_hz(stiffness_n_per_m: float, viscosity_pa_s: float, radius_m: float) -> float:
    """Corner frequency of a trapped bead's Brownian-motion power spectrum.

    ``f_c = kappa / (2*pi*gamma)``, ``gamma = 6*pi*eta*r`` the Stokes drag
    on a sphere in an unbounded medium (no Faxen wall correction for
    coverslip proximity). This is the standard power-spectrum trap
    calibration relation (Berg-Sorensen & Flyvbjerg, Rev. Sci. Instrum. 75,
    594, 2004): a trapped bead's position power spectral density is a
    Lorentzian with this corner frequency. G14 (docs/04-decision-engine.md
    Section 9) requires the camera's sampling rate f_s >= 10*f_c to resolve
    it without aliasing bias.

    The unbounded-medium drag is a *decision*, not an omission (2026-08-19):
    a bead held near the coverslip feels the Faxen parallel-to-wall factor
    ``gamma/gamma_0 = 1/(1 - 9a/(16h))`` -- +12.7% for a 4 um bead at
    h = 10 um -- and this lens will not correct it by formula. Calibrate the
    trap in situ at the working height instead; a measured corner frequency
    returns kappa and the wall-corrected gamma together, absorbing the bias by
    measurement. See kb/decisions/2026-08-19-lens-7-scope.md and docs/06 D8.
    """
    if stiffness_n_per_m <= 0:
        raise ValueError(f"stiffness must be positive, got {stiffness_n_per_m}")
    if viscosity_pa_s <= 0:
        raise ValueError(f"viscosity must be positive, got {viscosity_pa_s}")
    if radius_m <= 0:
        raise ValueError(f"radius must be positive, got {radius_m}")
    gamma = 6 * np.pi * viscosity_pa_s * radius_m
    return stiffness_n_per_m / (2 * np.pi * gamma)


def trap_depth_kt(
    power_w: float,
    bead: Bead,
    medium: Medium,
    beam: ObjectiveBeam,
    temperature_k: float,
    *,
    n_points: int = 96,
    n_steps: int = 200,
) -> float:
    """Radial potential-well depth from the beam center to the edge of this
    model's validity domain (``|displacement| = bead.radius_m``), in units
    of k_B*T: ``U(x) - U(0) = -integral_0^x F_radial(x') dx'``.

    This is NOT the depth at which a bead actually escapes the trap.
    ``trapping.goa.trap_force``'s ray-optics geometry is only defined while
    the beam focus stays inside the bead; a bead that actually escapes
    moves the focus outside the bead entirely, a regime this model cannot
    see. Treat the return value as a lower bound on the true trap depth,
    not the depth itself. Stable trapping against thermal escape is
    commonly cited as needing U/kT ≳ 10 (Ashkin, Biophys. J. 61, 569, 1992;
    Neuman & Block, Rev. Sci. Instrum. 75, 2787, 2004) -- a rule of thumb,
    not a derived cutoff, evaluated here only over the range the model can
    see.
    """
    if temperature_k <= 0:
        raise ValueError(f"temperature_k must be positive, got {temperature_k}")
    xs = np.linspace(0.0, bead.radius_m, n_steps)
    forces = np.array(
        [trap_force(power_w, float(x), bead, medium, beam, n_points=n_points)[0] for x in xs]
    )
    work_j = -np.trapezoid(forces, xs)
    return float(work_j / (K_BOLTZMANN * temperature_k))


@dataclass
class TrapSetup:
    """Everything one trapping verdict needs -- mirrors optics.path.Channel."""

    bead: Bead
    medium: Medium
    beam: ObjectiveBeam
    calibration: LaserCalibration
    dial_percent: float
    n_traps: int = 1
    weights: list[float] | None = None
    #: 293.15 K (20 C) is this project's standing default when temperature
    #: is not otherwise specified (2026-08-10 user decision). Still counts
    #: as an assumed, not measured, input -- see temperature_measured.
    temperature_k: float = 293.15
    temperature_measured: bool = False
    #: Achieved camera frame rate from lens 2 (detection), for the G14
    #: cross-check f_s >= 10*f_c. None if lens 2 hasn't run yet.
    detector_fps: float | None = None

    def powers_w(self) -> list[float]:
        return power_per_trap(
            self.calibration, self.dial_percent, self.n_traps, weights=self.weights
        )

    def weakest_power_w(self) -> float:
        """The least-powered trap -- the binding constraint for confinement
        and trap-depth checks once the beam is split across several traps."""
        return min(self.powers_w())
