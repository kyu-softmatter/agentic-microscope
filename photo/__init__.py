"""Lens 5 -- photo-perturbation.

Owns light level, illumination duty, total dose, wavelength choice.
docs/04-decision-engine.md §5-§6; docs/05-consensus-gate.md "Lens 5";
docs/06-pitfalls.md D2.

    from photo import IlluminationSetup, evaluate

    v = evaluate(IlluminationSetup(
        power_mw_at_sample=2.0, illuminated_area_um2=10000.0,
        wavelength_nm=488.0, exposure_ms=50.0, n_frames=1000,
        ext_coeff_m1cm1=75000, quantum_yield=0.92, lifetime_ns=4.1,
        bleach_photons=3.0e4, photoresponsive=False,
    ))
    print(v.status, v.bottleneck)

``photoresponsive`` is tri-state and defaults to ``None`` -- nobody asked. Omit
it and G21 warns and withholds ``advances`` instead of quietly clearing the
illumination, because the accident docs/06 D2 describes is the unasked
question. ``IlluminationSetup.from_channel`` is the preferred constructor: the
bare fields make k_ex from epsilon and flux alone, with the spectral overlap
lens 1 computes silently set to 1.

Gates: G10 photobleaching (specified in docs/04 §6, previously unimplemented),
G20 saturation / triplet shelving, G21 light-driving, G22 total dose.

**This lens BLOCKS on the real instrument today**, and that is the right
answer: `power_at_sample_mw` is empty for every line of every source in
data/light_sources.yaml, and no dye in data/fluorophores.yaml has
`bleach_photons`. A percent setting in the metadata is not a physical quantity.

The excitation chain (`P -> I -> phi -> sigma phi`) belongs to lens 1 --
``optics.path.Channel.excitation_rate_per_s`` and ``emitted_photons_per_s``.
``IlluminationSetup.from_channel`` consumes them rather than recomputing.

This lens is also the one that says **illumination is an experimental
variable, not a measurement tool**: lens 1 wants more light for SNR, G21 is
what can answer that it ruins the experiment.
"""

from __future__ import annotations

from .checks import CHECKS, GRADE_NOTES, LIMITS, CheckResult, grade
from .dose import (
    bleached_fraction,
    duty_cycle,
    emitted_photons_per_molecule,
    excited_state_fraction,
    irradiance_w_cm2,
    photon_flux_per_cm2_s,
    saturation_irradiance_w_cm2,
    total_dose_j_cm2,
    total_illuminated_time_s,
)
from .gate import Finding, Verdict, evaluate
from .setup import IlluminationSetup

__all__ = [
    "CHECKS",
    "GRADE_NOTES",
    "LIMITS",
    "CheckResult",
    "Finding",
    "IlluminationSetup",
    "Verdict",
    "bleached_fraction",
    "duty_cycle",
    "emitted_photons_per_molecule",
    "evaluate",
    "excited_state_fraction",
    "grade",
    "irradiance_w_cm2",
    "photon_flux_per_cm2_s",
    "saturation_irradiance_w_cm2",
    "total_dose_j_cm2",
    "total_illuminated_time_s",
]
