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

    # -- drift: NO FIELDS, ON PURPOSE --------------------------------------
    # Three drift fields stood here (axial rate, lateral rate, lateral
    # tolerance) and fed G29/G30. All three left on 2026-09-10: a drift rate is
    # measured during a run, so it is not an input to a design. The depth of
    # field and duration above are all `stability.drift_budget` needs to state
    # what the run can tolerate. Do not add a rate field back without reading
    # kb/decisions/2026-09-10-drift-is-not-a-design-element.md first.

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

    # -- vibration: NO FIELD, AND NO CHECK ---------------------------------
    # `vibration_measured` stood here and fed an INFO check that reported the
    # absence of a measurement channel. Removed 2026-09-10 (KH), on a physical
    # argument rather than a scheduling one: **every part of this microscope
    # sits on the same vibration-isolation table, so the camera and the sample
    # move together.** What an image can show is their RELATIVE motion, and
    # common-mode motion of a rigid assembly cancels out of it -- so there is
    # no channel to measure, not merely an unbuilt one, and a stuck-bead PSD in
    # the acquisition would not supply it either.
    # kb/decisions/2026-09-10-drift-is-not-a-design-element.md

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
