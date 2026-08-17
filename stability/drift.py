"""Mechanical and environmental stability physics: drift, sedimentation,
evaporation.

Pure functions, no gate logic -- mirrors compute/resources.py,
sample/aberration.py, photo/dose.py, validity/power.py.
docs/05-consensus-gate.md "Lens 8"; docs/06-pitfalls.md D7.

Lens 8 is the conditional lens for long acquisitions. Most of what it owns
needs a measurement nobody has taken yet (drift rate, vibration spectrum,
stage repeatability), so those gates BLOCK. Sedimentation is the exception: it
follows from particle size, density contrast and viscosity, all of which are
knowable without instrumenting the microscope.
"""

from __future__ import annotations

#: Standard gravity, m/s^2.
G = 9.80665


def total_drift_nm(rate_nm_per_min: float, duration_min: float) -> float:
    """Accumulated drift over the acquisition.

    Linear in time, which is the optimistic case: thermal drift is usually
    worst in the first hour after the enclosure is disturbed, so a rate
    measured late underestimates the start of a run.
    """
    return rate_nm_per_min * duration_min


def stokes_settling_velocity_um_per_s(
    radius_um: float, delta_density_kg_m3: float, viscosity_pa_s: float
) -> float:
    """Terminal settling velocity of a sphere, ``(2/9) dRho g a^2 / eta``.

    Low-Reynolds Stokes drag, valid for the micron-scale particles this lab
    images. Returns a signed value: negative density contrast (a particle
    lighter than the medium) creams upward rather than settling.

    Ignores hindered settling in a concentrated suspension and wall effects
    near the coverslip, both of which slow real settling down -- so the
    magnitude here is an upper bound.
    """
    if viscosity_pa_s <= 0:
        raise ValueError("viscosity_pa_s must be positive")
    a_m = radius_um * 1e-6
    v_m_s = (2.0 / 9.0) * delta_density_kg_m3 * G * a_m * a_m / viscosity_pa_s
    return v_m_s * 1e6


def settling_distance_um(velocity_um_per_s: float, duration_min: float) -> float:
    """How far the population moves axially over the acquisition."""
    return velocity_um_per_s * duration_min * 60.0


def evaporated_fraction(
    rate_ul_per_hour: float, volume_ul: float, duration_min: float
) -> float:
    """Fraction of the sample volume lost to evaporation.

    Clamped at 1.0: past that the chamber is dry and the number stops meaning
    anything.
    """
    if volume_ul <= 0:
        raise ValueError("volume_ul must be positive")
    lost = rate_ul_per_hour * (duration_min / 60.0)
    return min(lost / volume_ul, 1.0)


def concentration_factor(evaporated_fraction_: float) -> float:
    """How much the solute concentrates as solvent leaves, ``1/(1-f)``.

    This is why evaporation is a bias and not just an inconvenience: every
    concentration-dependent quantity drifts through the acquisition even if
    focus is held perfectly. Returns ``inf`` at complete evaporation.
    """
    if evaporated_fraction_ >= 1.0:
        return float("inf")
    if evaporated_fraction_ < 0.0:
        raise ValueError("evaporated_fraction must be in [0, 1]")
    return 1.0 / (1.0 - evaporated_fraction_)
