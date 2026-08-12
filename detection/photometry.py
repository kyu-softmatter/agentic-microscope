"""Photometric formulas: sampling, SNR, saturation, localization precision.

(docs/04-decision-engine.md §2, §4). Pure functions -- no dataclasses, no
registry lookups. ``optics.components.Objective.resolution_nm``/
``psf_sigma_nm`` own the diffraction-limit half of §2; this module owns the
pixel geometry and photon-statistics half.
"""

from __future__ import annotations

import math


def effective_pixel_nm(
    pixel_um: float, binning: int, mag_objective: float, mag_intermediate: float = 1.0
) -> float:
    """``p_sample = p_sensor * B / (M_obj * M_int)``, in nm."""
    p_um = pixel_um * binning / (mag_objective * mag_intermediate)
    return p_um * 1000.0


def quantization_noise_e(full_well_e: float, bit_depth: int) -> float:
    """``q/sqrt(12)``, ``q = full_well_e / 2**bit_depth`` (docs/04 §4).

    Always computable from full well and bit depth -- not an inference.
    """
    e_per_adu = full_well_e / (2**bit_depth)
    return e_per_adu / math.sqrt(12.0)


def effective_read_noise_e(read_noise_e: float, full_well_e: float, bit_depth: int) -> float:
    """``sqrt(read_noise^2 + quantization_noise^2)``.

    At 12-bit this can dominate the datasheet read noise entirely
    (docs/06-pitfalls.md §C2) -- choosing a fast/low-bit-depth mode for
    speed costs SNR even though nothing on the camera got noisier.
    """
    q = quantization_noise_e(full_well_e, bit_depth)
    return math.sqrt(read_noise_e**2 + q**2)


def snr(
    signal_e: float,
    background_e: float,
    dark_e: float,
    n_pix: int,
    effective_read_noise_e_: float,
) -> float:
    """``SNR = N_sig / sqrt(N_sig + N_bg + N_dark + n_pix * sigma_read^2)``."""
    noise_var = signal_e + background_e + dark_e + n_pix * effective_read_noise_e_**2
    return signal_e / math.sqrt(noise_var) if noise_var > 0 else float("inf")


def peak_electrons(signal_e: float, dark_e: float) -> float:
    return signal_e + dark_e


def peak_adu(peak_e: float, full_well_e: float, bit_depth: int, offset_adu: float) -> float:
    """Forward model of the raw ADU reading (offset ADDED, not subtracted --
    the inverse of docs/04 §4's "subtract the observed Offset" instruction,
    which applies when going from a *measured* ADU value back to electrons).
    """
    e_per_adu = full_well_e / (2**bit_depth)
    return peak_e / e_per_adu + offset_adu


def localization_variance_nm2(
    sigma_psf_nm: float, pixel_nm: float, n_photons: float, background_e: float = 0.0
) -> float:
    """Thompson-Larson-Webb / Mortensen localization variance (docs/04 §2).

    ``sigma_a^2 = sigma_psf^2 + p^2/12``
    ``var = sigma_a^2/N + 8*pi*sigma_a^4*b^2 / (p^2 * N^2)``

    The second (background) term is what makes the optimal pixel size
    *finite* -- without it, ever-finer pixels are always better, which is
    not what docs/06-pitfalls.md §C6 warns about.
    """
    sigma_a2 = sigma_psf_nm**2 + pixel_nm**2 / 12.0
    shot_term = sigma_a2 / n_photons
    bg_term = (8 * math.pi * sigma_a2**2 * background_e**2) / (pixel_nm**2 * n_photons**2)
    return shot_term + bg_term


def required_photons(sigma_psf_nm: float, pixel_nm: float, target_precision_nm: float) -> float:
    """Background-free lower bound: ``N >~ sigma_a^2 / sigma_loc_target^2``
    (docs/04 §4). With background present the true requirement is larger.
    """
    sigma_a2 = sigma_psf_nm**2 + pixel_nm**2 / 12.0
    return sigma_a2 / target_precision_nm**2
