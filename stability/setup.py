"""Mechanical / environmental setup: the facts lens 8's gates need."""

from __future__ import annotations

from dataclasses import dataclass

from optics.components import Objective

#: Acquisition length beyond which docs/01 §4 convenes lens 8. Reported as
#: context, not used to skip checks: sedimentation and drift scale continuously
#: with time and do not switch on at 30 minutes. Whether to call this lens at
#: all is the caller's decision; when called, it answers.
CONVENE_DURATION_MIN = 30.0


@dataclass
class StabilitySetup:
    #: Planned acquisition length. The one input everything here scales with.
    duration_min: float | None = None

    #: For the depth of field that axial drift and sedimentation are judged
    #: against. Owned by lens 1; consumed here.
    objective: Objective | None = None
    emission_nm: float | None = None
    #: Explicit override, if the DOF is known some other way.
    depth_of_field_um: float | None = None

    # -- drift (no measurement exists in the repo today) -------------------
    #: Measured axial drift, nm/min. Nothing in kb/calibrations/ records this,
    #: so the axial-drift gate BLOCKS until it is measured.
    axial_drift_rate_nm_per_min: float | None = None
    #: Measured lateral drift, nm/min.
    lateral_drift_rate_nm_per_min: float | None = None
    #: Lateral tolerance: how far the field may wander before the measurement
    #: is affected. For tracking this is the search window, not the field.
    lateral_tolerance_um: float | None = None

    # -- PFS (docs/06 D7) --------------------------------------------------
    #: `PFS-FocusMaintenance`. None means it was not recorded.
    pfs_enabled: bool | None = None
    #: `PFS in Range`. None means it was not recorded -- which is exactly the
    #: D7 trap: recording only the on state cannot tell you whether focus was
    #: actually held.
    pfs_in_range: bool | None = None

    # -- sedimentation -----------------------------------------------------
    particle_radius_um: float | None = None
    #: Particle minus medium density, kg/m^3. Polystyrene in water is about
    #: +50; a density-matched suspension is 0. Negative means it creams.
    delta_density_kg_m3: float | None = None
    viscosity_pa_s: float | None = None
    #: Chamber depth, for judging whether the population leaves the chamber
    #: rather than merely the focal plane.
    chamber_height_um: float | None = None

    # -- evaporation -------------------------------------------------------
    chamber_sealed: bool = False
    evaporation_rate_ul_per_hour: float | None = None
    sample_volume_ul: float | None = None

    # -- vibration (not implemented) ---------------------------------------
    #: True if a vibration spectrum was actually measured. There is no
    #: measurement channel for this, so the check only reports its absence.
    vibration_measured: bool = False

    # -- derived -----------------------------------------------------------

    @property
    def convenes(self) -> bool:
        """Would the committee convene this lens for this acquisition?"""
        return self.duration_min is not None and self.duration_min > CONVENE_DURATION_MIN

    @property
    def resolved_dof_um(self) -> float | None:
        if self.depth_of_field_um is not None:
            return self.depth_of_field_um
        if self.objective is None or self.emission_nm is None or self.objective.na <= 0:
            return None
        return self.objective.depth_of_field_nm(self.emission_nm) / 1000.0

    @property
    def settling_velocity_um_per_s(self) -> float | None:
        if (
            self.particle_radius_um is None
            or self.delta_density_kg_m3 is None
            or self.viscosity_pa_s is None
        ):
            return None
        from .drift import stokes_settling_velocity_um_per_s

        return stokes_settling_velocity_um_per_s(
            self.particle_radius_um, self.delta_density_kg_m3, self.viscosity_pa_s
        )
