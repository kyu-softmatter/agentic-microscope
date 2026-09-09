"""Lens 5 -- photo-perturbation.

Owns light level, illumination duty, total dose, wavelength choice.
docs/04-decision-engine.md §5-§6; docs/05-consensus-gate.md "Lens 5";
docs/06-pitfalls.md D2.

    from photo import IlluminationSetup, evaluate

    v = evaluate(IlluminationSetup(
        power_mw_at_sample=2.0, illuminated_area_um2=10000.0,
        wavelength_nm=488.0, exposure_ms=50.0, n_frames=1000,
        ext_coeff_m1cm1=75000, quantum_yield=0.92, lifetime_ns=4.1,
        photoresponsive=False,
    ))
    print(v.status, v.bottleneck)

``photoresponsive`` is tri-state and defaults to ``None`` -- nobody asked. Omit
it and G21 warns and withholds ``advances`` instead of quietly clearing the
illumination, because the accident docs/06 D2 describes is the unasked
question. ``IlluminationSetup.from_channel`` is the preferred constructor: the
bare fields make k_ex from epsilon and flux alone, with the spectral overlap
lens 1 computes silently set to 1.

Gates: G20 saturation / triplet shelving, G21 light-driving, G22 total dose.

**This lens computes as of 2026-09-09**, for the first time. Power is populated
for nine lines across the Aura, Spectra and LUN-F-XL at three objectives, and
all three engines put about the camera field on the sample, so irradiance
exists -- 1.1 to 7.7 W/cm^2 by line at 20x, 100 % level
(kb/calibrations/illumination-power.yaml).

G10 (photobleaching) was removed the same day, having never returned anything
but BLOCKED: kb/decisions/2026-09-09-g10-photobleaching-removed.md. The area
holds at 20x only -- it rests on the single pixel size marked `measured`, the
rest being `nominal`. A percent setting in the metadata is still not a physical
quantity.

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
    duty_cycle,
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
    "duty_cycle",
    "evaluate",
    "excited_state_fraction",
    "grade",
    "irradiance_w_cm2",
    "photon_flux_per_cm2_s",
    "saturation_irradiance_w_cm2",
    "total_dose_j_cm2",
    "total_illuminated_time_s",
]
