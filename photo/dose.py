"""Photo-perturbation physics: dose, bleaching, saturation.

Pure functions, no gate logic -- mirrors compute/resources.py,
trapping/dynamics.py, sample/aberration.py. docs/04-decision-engine.md §5-§6;
docs/05-consensus-gate.md "Lens 5".

The excitation chain itself (``P -> I -> phi -> sigma phi``) belongs to lens 1
and lives in ``optics.path.Channel.excitation_rate_per_s`` /
``emitted_photons_per_s``. This module takes those rates as inputs rather than
recomputing them, the same way lens 2 consumes the photon budget.
"""

from __future__ import annotations

import math

_H = 6.62607015e-34  # J*s
_C = 2.99792458e8  # m/s


def irradiance_w_cm2(power_mw_at_sample: float, illuminated_area_um2: float) -> float:
    """``I = P/A`` at the sample plane, W/cm^2. docs/04 §5."""
    if illuminated_area_um2 <= 0:
        raise ValueError("illuminated_area_um2 must be positive")
    return (power_mw_at_sample * 1e-3) / (illuminated_area_um2 * 1e-8)


def photon_flux_per_cm2_s(irradiance: float, wavelength_nm: float) -> float:
    """``phi = I lambda/(hc)``, photons cm^-2 s^-1. docs/04 §5."""
    if wavelength_nm <= 0:
        raise ValueError("wavelength_nm must be positive")
    photon_energy_j = _H * _C / (wavelength_nm * 1e-9)
    return irradiance / photon_energy_j


def total_illuminated_time_s(exposure_ms: float, n_frames: int) -> float:
    """Time the sample actually spends under light.

    Only exposure counts: between frames the shutter/AOTF is closed, which is
    the whole point of duty cycle as a lever.
    """
    return exposure_ms * 1e-3 * n_frames


def duty_cycle(exposure_ms: float, frame_interval_ms: float) -> float | None:
    """Fraction of wall-clock time under illumination, or None if undefined."""
    if frame_interval_ms is None or frame_interval_ms <= 0:
        return None
    return min(exposure_ms / frame_interval_ms, 1.0)


def emitted_photons_per_molecule(
    emitted_per_s: float, exposure_ms: float, n_frames: int
) -> float:
    """``N_emitted = k_em t_exp N_frames`` -- docs/04 §6."""
    return emitted_per_s * total_illuminated_time_s(exposure_ms, n_frames)


def bleached_fraction(n_emitted: float, bleach_photons: float) -> float:
    """``f = 1 - exp(-N_emitted / N_bleach)`` -- docs/04 §6.

    docs/04 §6 flags this as a **lower bound**: bleaching is often superlinear
    in intensity because of triplet pathways, which this single-exponential
    form does not capture.
    """
    if bleach_photons <= 0:
        raise ValueError("bleach_photons must be positive")
    return 1.0 - math.exp(-n_emitted / bleach_photons)


def excited_state_fraction(excitation_rate_per_s: float, lifetime_ns: float) -> float:
    """Steady-state fraction of molecules parked in the excited state.

    ``k_ex tau / (1 + k_ex tau)`` for a two-level system. As this approaches
    1 the molecule is saturated: emission stops rising with power, so the
    photon budget lenses 1 and 2 compute from a linear assumption
    overestimates, while the dose keeps climbing.

    Ignores triplet shelving, which pushes real saturation *earlier*, so this
    is an optimistic estimate of how much headroom is left.
    """
    if lifetime_ns <= 0:
        raise ValueError("lifetime_ns must be positive")
    k_tau = excitation_rate_per_s * lifetime_ns * 1e-9
    return k_tau / (1.0 + k_tau)


def saturation_irradiance_w_cm2(
    ext_coeff_m1cm1: float, lifetime_ns: float, wavelength_nm: float
) -> float:
    """Irradiance at which ``k_ex tau = 1`` (excited-state fraction 0.5).

    A useful scale for "how much light is too much" that does not depend on
    the current setting.
    """
    if lifetime_ns <= 0:
        raise ValueError("lifetime_ns must be positive")
    #: cm^2 per (M^-1 cm^-1) -- same conversion optics.path uses.
    sigma = 3.82e-21 * ext_coeff_m1cm1
    flux_at_saturation = 1.0 / (sigma * lifetime_ns * 1e-9)  # photons cm^-2 s^-1
    photon_energy_j = _H * _C / (wavelength_nm * 1e-9)
    return flux_at_saturation * photon_energy_j


def total_dose_j_cm2(irradiance: float, exposure_ms: float, n_frames: int) -> float:
    """Accumulated energy per unit area over the whole movie, J/cm^2."""
    return irradiance * total_illuminated_time_s(exposure_ms, n_frames)
