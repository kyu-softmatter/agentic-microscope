"""What a commanded velocity does to a trapped bead. Pure functions.

Mirrors `trapping/dynamics.py`, `compute/resources.py`, `sample/aberration.py`:
no gate logic here, and nothing reads a file.

**Every bound in this module is derived from the caller's own precision target
or from a limit the model states about itself.** There is no threshold constant
anywhere in this lens, which is why `velocity.checks.LIMITS` is empty. That is
deliberate: a velocity window is only meaningful against a stated precision,
and inventing one would be the thing CLAUDE.md rule 2 forbids.
"""

from __future__ import annotations

import math

#: Density of water at 20 C, kg/m^3, for the Reynolds number only. Not a
#: threshold -- it is the medium's property, and the check that uses it reports
#: rather than gates.
WATER_DENSITY_KG_M3 = 998.2


def drag_coefficient_pn_s_per_um(radius_um: float, viscosity_pa_s: float) -> float:
    """Stokes drag ``gamma = 6 pi eta a``, in pN*s/um.

    Unbounded medium. Near a wall the real gamma is larger -- lens 4's L4.4
    bounds that and deliberately does not correct it, so a velocity computed
    here inherits the same bias. `L9.2` says so rather than silently absorbing
    it.
    """
    if radius_um <= 0 or viscosity_pa_s <= 0:
        raise ValueError("radius_um and viscosity_pa_s must be positive")
    return 6.0 * math.pi * viscosity_pa_s * (radius_um * 1e-6) * 1e12 / 1e6


def equilibrium_offset_um(
    velocity_um_per_s: float, drag_pn_s_per_um: float, stiffness_pn_per_um: float
) -> float:
    """Steady-state offset of a dragged bead, ``x_eq = gamma v / kappa``.

    The whole measurement: with gamma and v known, x_eq gives kappa. Which is
    also why the velocity has to be chosen so that x_eq is both **resolvable**
    and **inside the trap's linear region** -- neither is automatic.
    """
    if stiffness_pn_per_um <= 0:
        raise ValueError("stiffness_pn_per_um must be positive")
    return drag_pn_s_per_um * velocity_um_per_s / stiffness_pn_per_um


def velocity_for_offset_um_per_s(
    offset_um: float, drag_pn_s_per_um: float, stiffness_pn_per_um: float
) -> float:
    """Inverse of :func:`equilibrium_offset_um` -- the actionable direction."""
    if drag_pn_s_per_um <= 0:
        raise ValueError("drag_pn_s_per_um must be positive")
    return offset_um * stiffness_pn_per_um / drag_pn_s_per_um


def minimum_offset_um(localization_sigma_nm: float, target_relative_error: float) -> float:
    """Smallest offset that carries the wanted precision on kappa.

    ``kappa = gamma v / x_eq``, so ``dkappa/kappa = dx/x_eq`` at fixed v and
    gamma -- the offset has to exceed the localization noise by exactly the
    reciprocal of the target. **Derived, not chosen**: a 5 % target on kappa and
    a 10 nm sigma give 200 nm, and nobody had to pick a multiple.

    Note what this makes of the target relative error: it left lens 6 when G11
    was removed on 2026-09-11 (`1/sqrt(N_p x N_f)` did not describe a
    single-bead measurement) and it is a real input again here, where it sets a
    velocity rather than a sample size.
    """
    if localization_sigma_nm <= 0:
        raise ValueError("localization_sigma_nm must be positive")
    if not 0 < target_relative_error < 1:
        raise ValueError("target_relative_error must be in (0, 1)")
    return localization_sigma_nm / target_relative_error / 1000.0


def settling_time_constants(target_relative_error: float) -> float:
    """How many ``tau`` a velocity step must last, ``ln(1/target)``.

    The approach to the steady offset is exponential, so the residual after
    ``n tau`` is ``e^-n``; requiring that below the precision target gives
    ``n = ln(1/target)``. 5 % needs 3.0 tau, 2 % needs 3.9. **Derived, so no
    "about five time constants" rule of thumb appears anywhere in this lens.**
    """
    if not 0 < target_relative_error < 1:
        raise ValueError("target_relative_error must be in (0, 1)")
    return math.log(1.0 / target_relative_error)


def reynolds_number(
    velocity_um_per_s: float,
    radius_um: float,
    viscosity_pa_s: float,
    density_kg_m3: float = WATER_DENSITY_KG_M3,
) -> float:
    """``Re = rho v a / eta``. Stokes drag assumes ``Re << 1``.

    Reported and never gated in this lens, because on this instrument it cannot
    bind: ``Re = 1`` for a 2.5 um bead in water needs about 4e5 um/s, which is
    four orders above anything the stage or the AOD will do. Saying that once,
    with the number, is more useful than a gate that always passes.
    """
    return density_kg_m3 * (velocity_um_per_s * 1e-6) * (radius_um * 1e-6) / viscosity_pa_s


def reynolds_unity_velocity_um_per_s(
    radius_um: float,
    viscosity_pa_s: float,
    density_kg_m3: float = WATER_DENSITY_KG_M3,
) -> float:
    """The velocity at which ``Re = 1`` -- the number that retires the gate."""
    return viscosity_pa_s / (density_kg_m3 * radius_um * 1e-6) * 1e6


# --------------------------------------------------------------------------
# Statistical precision of a stiffness read off a velocity step (L9.6)
# --------------------------------------------------------------------------
#
# `kappa = gamma * v / x_eq` is only as precise as `x_eq`, and `x_eq` is a MEAN
# over a step of a quantity that never stops moving. The bead in the trap is an
# Ornstein-Uhlenbeck process: variance `kT/kappa` by equipartition, correlation
# time `tau = gamma/kappa`. Those are the two numbers below, and both come from
# lens 7 rather than from here.


def thermal_position_sigma_um(kt_pn_um: float, stiffness_pn_per_um: float) -> float:
    """``sqrt(kT / kappa)`` -- equipartition, the bead's 1-sigma wander."""
    if stiffness_pn_per_um <= 0:
        raise ValueError("stiffness must be positive")
    return math.sqrt(kt_pn_um / stiffness_pn_per_um)


def averaged_sigma_um(sigma_um: float, relaxation_time_s: float, averaging_time_s: float) -> float:
    """1-sigma of the MEAN of an OU process over ``averaging_time_s``.

        Var(x_bar) = (2 sigma^2 tau / T) * [1 - (tau/T)(1 - exp(-T/tau))]

    The exact expression, not the ``T >> tau`` limit, because the limit is
    wrong in exactly the regime this lens cares about: L9.3 already tells the
    caller their step may be only a few tau long, and at ``T = tau`` the simple
    form overstates the averaging benefit by 37 %. As ``T -> 0`` this returns
    ``sigma`` -- averaging over no time buys nothing, which is the check that
    the formula is the right one.

    **This is the arithmetic G11 did not do.** `1/sqrt(N_frames)` assumes every
    frame is an independent sample; consecutive frames inside one relaxation
    time are not, and on this instrument's own calibration that was 3.5x
    optimistic -> kb/decisions/2026-09-11-g11-and-g26-removed.md
    """
    if relaxation_time_s <= 0:
        raise ValueError("relaxation time must be positive")
    if averaging_time_s <= 0:
        return sigma_um
    ratio = relaxation_time_s / averaging_time_s
    bracket = 1.0 - ratio * (1.0 - math.exp(-1.0 / ratio))
    return sigma_um * math.sqrt(2.0 * ratio * bracket)


def steps_for_relative_error(per_step_relative_error: float, target_relative_error: float) -> float:
    """Steps needed so that ``eps_1 / sqrt(N) <= target``.

    Steps are independent of each other in the way frames inside a step are
    not: each one is a fresh approach to a fresh offset, so ``1/sqrt(N)`` is
    honest here for the same reason it was not honest in G11.
    """
    if target_relative_error <= 0:
        raise ValueError("target_relative_error must be positive")
    return (per_step_relative_error / target_relative_error) ** 2
