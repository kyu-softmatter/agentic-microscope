"""Measurement-validity setup: the facts lens 6's gates need.

Unlike every other lens, lens 6's primary input is **other lenses' verdicts**.
It does not recompute their physics; it decides whether the intended physical
quantity survives all of them together. So it must be called last, after the
other lenses have returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FindingLike(Protocol):
    """Structural view of any lens's Finding.

    All six lens modules define an identical Finding, so a protocol is enough
    and no lens has to import another's types.
    """

    severity: str
    code: str
    message: str
    lens: str


@runtime_checkable
class VerdictLike(Protocol):
    """Structural view of any lens's Verdict.

    Deliberately does NOT require ``feasibility``, even though all eight lenses
    now carry it: ``trapping.gate.Verdict`` lacked the field until 2026-08-12,
    and this lens should not start depending on it merely because the asymmetry
    was fixed. Read it with ``getattr(v, "feasibility", "UNKNOWN")``.

    The duplication behind all this is a known gap -- eight copies of
    Verdict/Finding/Check/CheckResult, one per lens -- and until there is a
    shared committee type, structural typing is what lets this lens review all
    of them.
    """

    status: str
    evidence: str
    margins: dict[str, float]
    findings: list[Any]
    metrics: dict


#: Which calibrations a given intended quantity actually depends on. This is
#: the mechanical half of docs/05 Lens 6's "is the intended quantity
#: extractable": a geometric quantity is ruined by a wrong pixel size and
#: indifferent to flat-field, while an intensity-based one is the reverse.
#:
#: "linearity" means pixel values must stay proportional to photons, which
#: despeckle and similar filters break (docs/06 C1).
QUANTITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    # geometry / kinematics
    "position": ("pixel_size",),
    "displacement": ("pixel_size",),
    "diffusion": ("pixel_size",),
    "velocity": ("pixel_size",),
    "msd": ("pixel_size",),
    "rheology": ("pixel_size",),
    "morphology": ("pixel_size",),
    "size": ("pixel_size",),
    # photometry
    "intensity": ("background", "dark_current", "flat_field", "linearity"),
    "concentration": ("background", "dark_current", "flat_field", "linearity"),
    "stoichiometry": ("background", "dark_current", "flat_field", "linearity"),
    "frap": ("background", "dark_current", "linearity"),
    # both
    "colocalization": ("pixel_size", "background", "linearity"),
    "tracking_intensity": ("pixel_size", "background", "dark_current", "linearity"),
}


def calibrations_for(quantity: str | None) -> tuple[str, ...]:
    """The calibrations one intended quantity rests on, or ``()`` if unknown.

    An unknown quantity returns empty rather than a guess -- the gate turns that
    into BLOCKED, because certifying validity against invented criteria is worse
    than refusing.
    """
    if quantity is None:
        return ()
    return QUANTITY_REQUIREMENTS.get(quantity.strip().lower(), ())

#: Upstream bias findings that have a correction which can actually be applied
#: after the fact, keyed by the code the origin lens emits **when the check
#: fails** (not the passing code -- `detection` emits `motion_blur` on the way
#: through and `motion_blur.biased` on failure). The value names the correction,
#: so a declaration in ``corrections_applied`` can be checked instead of taken
#: on faith.
CORRECTIONS: dict[str, str] = {
    "crosstalk": "linear unmixing from a measured mixing matrix",
    "motion_blur.biased": "Savin-Doyle blur correction (docs/04 §5)",
    "perturbation.photobleaching": "intensity-decay correction (docs/04 §6)",
    "stability.lateral_drift": "drift correction from a fiducial or image registration",
}

#: Bias findings with **no** post-hoc correction: the setting or the sample has
#: to change instead. Declaring one of these in ``corrections_applied`` is a
#: false claim, and G23 says so rather than clearing the bias -- which is what
#: it used to do, since the declaration was matched against nothing at all.
UNCORRECTABLE: dict[str, str] = {
    "geometry.ri_mismatch": "no aberration model is implemented (docs/06 D5) -- "
    "change the immersion, the medium or the depth",
    "geometry.coverslip": "the correction collar is hardware, not post-processing",
    "perturbation.saturation": "past saturation emission stops tracking power, so "
    "lenses 1 and 2 overestimate signal while dose keeps climbing -- lower the "
    "irradiance",
    "perturbation.light_driving": "the light is moving the sample; nothing "
    "downstream recovers the unperturbed dynamics (docs/06 D2)",
    "stability.evaporation": "the composition changed during the movie -- seal the "
    "chamber or shorten the acquisition",
}

#: Which of a quantity's required calibrations a bias actually damages. This is
#: what scopes a FAIL to the affected physical quantity rather than the whole
#: session (docs/05 Lens 6: "a FAIL is scoped to the affected physical
#: quantity, not to the whole session").
#:
#: **A bias absent from this table damages every quantity.** That is the
#: conservative default and the only honest one where no document scopes it:
#: light-driving and saturation move the sample itself, and crosstalk puts
#: another channel's particles in the frame, so all three are deliberately
#: absent rather than guessed at.
BIAS_SCOPE: dict[str, frozenset[str]] = {
    # docs/04 §5: the Savin-Doyle terms bias the MSD. A trajectory is ruined; an
    # integrated intensity is spread, not lost.
    "motion_blur.biased": frozenset({"pixel_size"}),
    # docs/06 D5: spherical aberration grows with depth, distorting the axial
    # PSF and near-interface geometry.
    "geometry.ri_mismatch": frozenset({"pixel_size"}),
    # Absolute position goes wrong and long-lag MSD points follow it.
    "stability.lateral_drift": frozenset({"pixel_size"}),
    # docs/04 §6 frames bleaching as an intensity decay. It costs a tracking
    # experiment statistics rather than accuracy -- particles vanish, which
    # lands in G11's particle count, not in a positional bias.
    "perturbation.photobleaching": frozenset(
        {"background", "dark_current", "flat_field", "linearity"}
    ),
}

#: Standing lenses that should have returned a verdict before this one runs.
#: Lens 8 is conditional (acquisitions past ~30 min), so it is not required
#: here -- but `stability/` does implement G28-G32 and two of its gates are
#: `kind: bias`, so pass its verdict in `upstream` when it convened and the
#: ledger will pick those up like any other lens's.
STANDING_LENSES: tuple[str, ...] = ("optics", "detection", "compute", "sample", "photo")


@dataclass
class ValiditySetup:
    #: What physical quantity the experiment is actually after. Drives which
    #: calibrations are mandatory -- see QUANTITY_REQUIREMENTS.
    intended_quantity: str | None = None
    #: Several intended quantities, when one session is after more than one.
    #: docs/05 Lens 6 lets the **unit of verdict be a physical quantity rather
    #: than the channel**: a session's MSD can be biased while its intensity
    #: profile is fine, and collapsing those into one status destroys
    #: information. Set this and `gate.evaluate` judges each one separately and
    #: reports the aggregate; `intended_quantity` remains the single-quantity
    #: form. If both are set this one wins.
    intended_quantities: tuple[str, ...] = ()
    #: Target relative error on that quantity, e.g. 0.05 for 5%.
    target_relative_error: float | None = None

    #: Verdicts from the other lenses, keyed by lens name ("optics",
    #: "detection", "compute", "sample", "photo", "trapping"). This lens's
    #: primary input.
    upstream: dict[str, VerdictLike] = field(default_factory=dict)

    # -- statistical power (G11) -------------------------------------------
    #: Particles in the observed volume. Lens 4 computes this as G19's
    #: `expected_count`; if omitted it is read from the sample verdict.
    n_particles: float | None = None
    n_frames: int | None = None

    # -- calibrations in hand ---------------------------------------------
    #: Measured pixel size at the sample. docs/06 A1: without it every
    #: distance, velocity and diffusion coefficient is wrong by an unknown
    #: scale factor. kb/systems/current.md > pixel_size_calibration has a
    #: measured table.
    pixel_size_measured: bool = False
    background_measured: bool = False
    dark_current_measured: bool = False
    flat_field_measured: bool = False

    # -- post-processing (docs/06 C1) --------------------------------------
    #: Filters that break the proportionality between pixel value and photon
    #: count. PVCAM on-camera despeckle was enabled in every archive
    #: generation (data/detectors.yaml).
    despeckle_enabled: bool = False
    #: Any other declared post-processing that breaks linearity.
    nonlinear_filters: tuple[str, ...] = ()

    # -- the bias ledger ---------------------------------------------------
    #: Upstream bias-finding codes the experimenter asserts are corrected, with
    #: a correction that is actually applied. Asserting a correction that does
    #: not exist is the failure this gate is meant to catch, so the codes are
    #: named explicitly rather than waved at.
    corrections_applied: frozenset[str] = frozenset()

    #: Which analysis script will process the data. docs/05 Lens 6: the only
    #: lens that also reads the analysis code, because which script runs
    #: changes the setting requirements. Left None, the verdict is downgraded
    #: to assumed -- this lens does not read D:\\codes itself.
    analysis_script: str | None = None

    # -- derived -----------------------------------------------------------

    @property
    def required_calibrations(self) -> tuple[str, ...]:
        return calibrations_for(self.intended_quantity)

    @property
    def quantities(self) -> tuple[str, ...]:
        """Every intended quantity to judge, in stated order, deduplicated."""
        if self.intended_quantities:
            return tuple(dict.fromkeys(self.intended_quantities))
        if self.intended_quantity is not None:
            return (self.intended_quantity,)
        return ()

    def for_quantity(self, quantity: str) -> "ValiditySetup":
        """This setup narrowed to one quantity, for the per-quantity pass."""
        return replace(self, intended_quantity=quantity, intended_quantities=())

    @property
    def resolved_n_particles(self) -> float | None:
        """Explicit count, else lens 4's G19 metric."""
        if self.n_particles is not None:
            return self.n_particles
        sample = self.upstream.get("sample")
        if sample is None:
            return None
        m = (sample.metrics or {}).get("geometry.count_in_field") or {}
        return m.get("expected_count") if m.get("evaluated") else None

    def bias_findings(self) -> list[Any]:
        """Every bias-kind finding from upstream, in lens order.

        These are what this lens exists to review: docs/05 gives it "G11 + final
        review of every bias gate".
        """
        out: list[Any] = []
        for name in sorted(self.upstream):
            v = self.upstream[name]
            for f in v.findings or []:
                if getattr(f, "kind", None) == "bias" and f.severity in {"warn", "fail"}:
                    out.append(f)
        return out

    def applicable_bias_findings(self) -> list[Any]:
        """The upstream biases that damage **this** setup's intended quantity.

        A bias in BIAS_SCOPE only counts if its scope overlaps the calibrations
        the quantity rests on; an unscoped bias counts always. That is what lets
        a session report a biased MSD and a sound intensity profile at once.
        """
        required = set(self.required_calibrations)
        out: list[Any] = []
        for f in self.bias_findings():
            scope = BIAS_SCOPE.get(f.code)
            if scope is None or (scope & required):
                out.append(f)
        return out

    def out_of_scope_bias_findings(self) -> list[Any]:
        applicable = {id(f) for f in self.applicable_bias_findings()}
        return [f for f in self.bias_findings() if id(f) not in applicable]

    def _cleared(self, code: str) -> bool:
        """Is this bias genuinely cleared by a declared correction?

        Declaring a code that appears in UNCORRECTABLE does not clear it: there
        is no such correction to have applied.
        """
        return code in self.corrections_applied and code not in UNCORRECTABLE

    def uncorrected_bias_findings(self) -> list[Any]:
        return [f for f in self.applicable_bias_findings() if not self._cleared(f.code)]

    def falsely_corrected_bias_findings(self) -> list[Any]:
        """Biases declared corrected for which no correction exists.

        Louder than a plain uncorrected bias: the ledger would have read clean.
        """
        return [
            f
            for f in self.applicable_bias_findings()
            if f.code in self.corrections_applied and f.code in UNCORRECTABLE
        ]

    def unverified_corrections(self) -> list[str]:
        """Declared codes that cleared a bias but are in neither registry.

        Accepted -- refusing an unknown gate's correction would block work on
        gates this table has not caught up with -- but they cost the verdict its
        `measured` grade, so an unaudited declaration cannot advance.
        """
        applicable = {f.code for f in self.applicable_bias_findings()}
        return sorted(
            c
            for c in self.corrections_applied
            if c in applicable and c not in CORRECTIONS and c not in UNCORRECTABLE
        )

    def missing_standing_lenses(self) -> list[str]:
        return [name for name in STANDING_LENSES if name not in self.upstream]

    def blocked_lenses(self) -> list[str]:
        return sorted(
            name for name, v in self.upstream.items() if v.status == "BLOCKED"
        )

    def failed_lenses(self) -> list[str]:
        return sorted(name for name, v in self.upstream.items() if v.status == "FAIL")
