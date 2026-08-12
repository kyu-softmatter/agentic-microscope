"""Sample geometry / optics setup: the facts lens 4's gates need."""

from __future__ import annotations

from dataclasses import dataclass

from optics.components import Objective

from .aberration import COVERSLIP_DESIGN_UM

#: Sample-medium refractive index used when the experiment does not state one.
#: Water-based, 20 C, 589 nm. This is an **assumed** default, not a
#: measurement -- kb/expertise/sample-medium-refractive-index.md. Any verdict
#: that leans on it reports evidence: assumed.
DEFAULT_N_SAMPLE = 1.333


@dataclass
class SampleSetup:
    objective: Objective
    #: Depth into the sample, past the coverslip, that must be in focus.
    imaging_depth_um: float | None = None
    #: Sample-medium refractive index. Left None it falls back to
    #: DEFAULT_N_SAMPLE and downgrades the verdict's evidence.
    n_sample: float | None = None
    #: Measured coverslip thickness. Left None the objective's design value
    #: is assumed, which is also an evidence downgrade -- docs/06-pitfalls.md
    #: warns the real #1.5 spread is wider than the nominal tolerance.
    coverslip_actual_um: float | None = None
    #: True when the sample has more than one phase with different
    #: refractive indices (ATPS dextran/PEG). A single n_sample cannot
    #: describe it, so the gate blocks instead of substituting a default.
    multiphase: bool = False
    #: Per-phase refractive indices, which is what makes a multiphase sample
    #: judgeable. e.g. {"dextran_rich": 1.348, "peg_rich": 1.339}.
    phase_n: dict[str, float] | None = None
    #: True for a birefringent sample (liquid crystal 5CB: n_o ~1.53,
    #: n_e ~1.71). One isotropic index is meaningless, so the gate blocks.
    birefringent: bool = False
    #: Particle concentration, for the count-in-field check.
    concentration_per_ml: float | None = None
    #: Field of view at the sample, um. Owned by lenses 1/2 (objective +
    #: camera); lens 4 only consumes it.
    field_width_um: float | None = None
    field_height_um: float | None = None
    #: Emission wavelength, nm. Owned by lens 1; lens 4 consumes it only to
    #: size the PSF when judging whether particles overlap.
    emission_nm: float | None = None
    #: Was the correction collar actually adjusted for this coverslip?
    #: docs/05 Lens 4 checklist asks precisely this. Having a collar and
    #: leaving it at the factory mark is a common silent aberration source.
    collar_adjusted: bool = False

    @property
    def n_immersion(self) -> float:
        """Immersion index, from optics.components.IMMERSION_N."""
        return self.objective.n_medium

    @property
    def resolved_n_sample(self) -> float:
        return DEFAULT_N_SAMPLE if self.n_sample is None else self.n_sample

    @property
    def resolved_coverslip_um(self) -> float:
        if self.coverslip_actual_um is not None:
            return self.coverslip_actual_um
        design = self.objective.coverslip_um
        return COVERSLIP_DESIGN_UM if design is None else design

    @property
    def design_coverslip_um(self) -> float:
        design = self.objective.coverslip_um
        return COVERSLIP_DESIGN_UM if design is None else design
