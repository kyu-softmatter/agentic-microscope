"""Sample geometry / optics setup: the facts lens 4's gates need."""

from __future__ import annotations

from dataclasses import dataclass

from optics.components import Objective

from .aberration import COVERSLIP_DESIGN_UM

#: Sample-medium refractive index used when the experiment does not state one.
#: Water-based, 20 C, 589 nm. **Confirmed 2026-08-19** (KH) as the settled
#: value for this lab's aqueous samples, not a placeholder -- so leaving
#: n_sample unset no longer downgrades a verdict's evidence.
#: kb/expertise/sample-medium-refractive-index.md.
#:
#: Ordinary buffer (PBS and similar) runs 1.334-1.337 depending on salt load.
#: That spread sits inside LIMITS["matched_ri_tolerance"] = 0.005, which is
#: why confirming the water value does not weaken G17's "index-matched"
#: verdict for the 40x WI -- the tolerance was sized for exactly this.
#:
#: The exclusions in that KB entry still stand: ATPS, glycerol/sucrose, high
#: polymer, and birefringent media are NOT covered by this default, and the
#: gate BLOCKs rather than substituting it (see gate._missing_inputs).
DEFAULT_N_SAMPLE = 1.333

#: Coverslip thickness this lab mounts on, um. KH 2026-08-20: the coverslips in
#: use are the 170 um ones. (The product line runs 140-180 um; 170 is the one
#: selected, which is what matters here.)
#:
#: This matches the design thickness of every objective on the nosepiece, so
#: G18 is not normally the bottleneck -- the routine case is a match, and the
#: 40x WI's 0.15-0.19 mm collar span brackets it comfortably.
#:
#: Kept as a separate constant from the objective's design value even though the
#: two currently coincide, because they answer different questions: this is what
#: the lab mounts, that is what the lens wants. Falling back to the design value
#: would make any future objective with a different design thickness silently
#: report a zero deviation.
#:
#: It stays `assumed`, not measured: it is a nominal product thickness, not a
#: micrometer reading of the coverslip on the stage. docs/06 records that the
#: real spread of a nominal coverslip is wider than its stated tolerance, so one
#: micrometer reading is still what earns `evidence: measured`.
LAB_DEFAULT_COVERSLIP_UM = 170.0


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
    #: Axial extent of the volume actually observed, um -- the slab whose
    #: particles land in one image. This is NOT imaging_depth_um, which says
    #: where the focal plane sits. For widefield the whole column above the
    #: field contributes and the two coincide; for a confocal / spinning-disk
    #: section the slab is the section thickness and is far smaller.
    #:
    #: G19's expected_count used to reuse imaging_depth_um unconditionally,
    #: which mattered because validity/setup.py::resolved_n_particles feeds
    #: that count into lens 6's G11 -- an over-generous extent became an
    #: overestimate of statistical power. Left None this falls back to the
    #: objective's depth of field when emission_nm is known, else to
    #: imaging_depth_um, and the check reports which it used.
    observed_slab_um: float | None = None
    #: Chamber height, um -- how far the sample extends past the inner surface
    #: of the coverslip. Same field name as stability.setup.SampleSetup so the
    #: two lenses can be fed from one answer.
    #:
    #: G16b needs it. Note what it is *not*: the spacer or gasket that sets this
    #: height forms the chamber walls and is not in the optical path, whichever
    #: way up the stand is, so it does not consume working distance. The only
    #: glass in the path is the coverslip facing the objective, and
    #: coverslip_actual_um already carries that -- including the case of imaging
    #: through something much thicker, like a plastic dish bottom.
    chamber_height_um: float | None = None
    #: Particle radius, um. Owned by lens 8 (stability.setup uses the same field
    #: name for settling) and lens 7 (Bead.radius_m); lens 4 consumes it only to
    #: bound the near-wall drag in G16c.
    particle_radius_um: float | None = None
    #: Is the optical trap holding the particle? Owned by lens 7; consumed here
    #: because it decides whether G16c's bound has an absorption route. With a
    #: trap, docs/06 D8's in-situ power-spectrum calibration at the working
    #: height returns kappa and the wall-corrected gamma together, so the bias
    #: is absorbed by measurement. Untrapped -- free-diffusion MSD -- there is
    #: no such step and the bound is the whole answer.
    trapped: bool = False
    #: True when there is no spacer or gasket -- the coverslip sits directly
    #: against the sample. KH 2026-08-20: this is how this lab's samples are
    #: usually mounted.
    #:
    #: It changes what chamber_height_um *is*. With a spacer the height is a
    #: part with a spec, so leaving it unset just means nobody looked it up.
    #: Without one the thickness is set by drop volume, wetting and the
    #: coverslip's own weight -- uncontrolled, varying between preparations, and
    #: wedge-shaped across a squashed drop. So an absent height here is not an
    #: unasked question but a statement that no designed thickness exists, and
    #: G16b says so out loud instead of skipping quietly.
    unspaced_mount: bool = False
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
        """Thickness to judge against, measured if supplied else the lab default.

        Falls back to LAB_DEFAULT_COVERSLIP_UM, **not** to the objective's
        design value. The two coincide today (both 170 um), so this changes no
        current verdict -- it is about what the fallback *means*. Falling back
        to design asserts "the coverslip matches whatever this lens wants",
        which would report a zero deviation for any future objective with a
        different design thickness. Falling back to the lab's actual glass
        states a fact instead, and lets the comparison do its job.
        """
        if self.coverslip_actual_um is not None:
            return self.coverslip_actual_um
        return LAB_DEFAULT_COVERSLIP_UM

    @property
    def design_coverslip_um(self) -> float:
        """Thickness the objective is corrected for -- a property of the lens."""
        design = self.objective.coverslip_um
        return COVERSLIP_DESIGN_UM if design is None else design

    def resolved_slab(self) -> tuple[float, str]:
        """Observed axial extent and where it came from.

        Returns ``(um, source)`` with source in ``explicit`` /
        ``depth_of_field`` / ``imaging_depth``. The source is reported in G19's
        numbers so lens 6 can see whether the count it inherits rests on a
        stated slab or on a widefield-column assumption nobody confirmed.

        Depth of field is the default rather than the full column because the
        count exists to feed G11 (statistical power), and a particle outside
        the DOF is blurred past localizing -- it inflates the count without
        contributing a measurement. That errs pessimistic, which is the right
        direction for a gate whose failure mode was optimism. A widefield
        acquisition that genuinely wants the column should say so via
        ``observed_slab_um``.
        """
        if self.observed_slab_um is not None:
            return float(self.observed_slab_um), "explicit"
        if self.emission_nm is not None:
            return self.objective.depth_of_field_nm(self.emission_nm) / 1000.0, "depth_of_field"
        return float(self.imaging_depth_um or 0.0), "imaging_depth"
