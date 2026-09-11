"""Velocity setup: the facts lens 9's checks need.

The lens is **conditional**, like 7 and 8: it is convened when the experiment
commands a motion -- a stage ramp, a trap sweep -- and not otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kinematics import drag_coefficient_pn_s_per_um

#: How the commanded motion is produced. Both exist on this instrument and
#: their DISTANCE scales were cross-checked against each other on 2026-09-03
#: (see `data/pixel_size.yaml`'s 100x row: closed-loop piezo 0.06460 um/px, AOD
#: trap 0.06445, agreeing to 0.24 % over 10 um). Their TIME base was not.
DRIVERS: tuple[str, ...] = ("piezo_stage", "aod_trap")


@dataclass
class VelocitySetup:
    #: Commanded velocity of the relative motion, um/s. Positive magnitude;
    #: the sign is the experiment's business.
    commanded_velocity_um_per_s: float | None = None
    #: Which subsystem produces it. See DRIVERS.
    driver: str | None = None

    #: Duration of one velocity step, ms. The bead approaches the steady
    #: offset exponentially, so a step shorter than a few tau reports a
    #: displacement that has not arrived yet.
    step_duration_ms: float | None = None

    # -- the bead and the medium -------------------------------------------
    particle_radius_um: float | None = None
    viscosity_pa_s: float | None = None

    # -- from lens 7 -------------------------------------------------------
    #: Radial trap stiffness, pN/um. Lens 7 owns it -- `TrapSetup.stiffness_n_per_m()`
    #: returns it with its provenance, and a MEASURED value beats the
    #: ray-optics model. Consumed here, never re-derived.
    stiffness_pn_per_um: float | None = None

    # -- from lens 2 -------------------------------------------------------
    #: Localization precision, 1 sigma, nm. Lens 2 computes it
    #: (`detection.photometry.localization_variance_nm2`); it sets the floor of
    #: the velocity window.
    localization_sigma_nm: float | None = None
    #: Achieved frame rate, for expressing the step duration in frames. Lens 2
    #: owns the rate and lens 3 owns whether it is achieved or merely
    #: requested (L3.2).
    achieved_fps: float | None = None

    # -- the experiment's own criterion ------------------------------------
    #: Target relative error on the quantity being measured, e.g. 0.05.
    #: **Every bound in this lens is derived from it**, which is why there is
    #: no LIMITS dict. It is the same input that left lens 6 when G11 was
    #: removed on 2026-09-11; here it sets a velocity rather than a sample size.
    target_relative_error: float | None = None

    # -- provenance --------------------------------------------------------
    #: True only if the TIME BASE of a commanded velocity has been checked on
    #: this instrument -- that a commanded um/s is the um/s that happens. The
    #: distance half is corroborated (see DRIVERS); this half is not, and
    #: nothing in kb/, data/, config/, hardware/ or calibration/ records it
    #: (verified 2026-09-11). Do not set it True on the strength of the
    #: controller being closed-loop: a closed loop holds its own scale, which
    #: is the thing in question.
    velocity_time_base_verified: bool = False
    #: Measured ratio of actual to commanded velocity, if somebody measures it.
    velocity_scale_ratio: float | None = None

    # -- derived -----------------------------------------------------------

    @property
    def resolved_drag_pn_s_per_um(self) -> float | None:
        if self.particle_radius_um is None or self.viscosity_pa_s is None:
            return None
        return drag_coefficient_pn_s_per_um(self.particle_radius_um, self.viscosity_pa_s)

    @property
    def relaxation_time_ms(self) -> float | None:
        """``tau = gamma / kappa``, in ms."""
        gamma = self.resolved_drag_pn_s_per_um
        if gamma is None or not self.stiffness_pn_per_um:
            return None
        return gamma / self.stiffness_pn_per_um * 1000.0
