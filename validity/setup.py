"""Measurement-validity setup: the facts lens 6's gates need.

Unlike every other lens, lens 6's primary input is **other lenses' verdicts**.
It does not recompute their physics; it decides whether the intended physical
quantity survives all of them together. So it must be called last, after the
other lenses have returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    Deliberately does NOT require ``feasibility``: ``trapping.gate.Verdict``
    does not have that field while the other five do. Read it with
    ``getattr(v, "feasibility", "UNKNOWN")``. The duplication is a known gap --
    six copies of Verdict/Finding/Check/CheckResult, one per lens -- and until
    there is a shared committee type, structural typing is what lets this lens
    review all of them.
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

#: Standing lenses that should have returned a verdict before this one runs.
#: Lens 8 is absent from the codebase entirely, so it is not listed.
STANDING_LENSES: tuple[str, ...] = ("optics", "detection", "compute", "sample", "photo")


@dataclass
class ValiditySetup:
    #: What physical quantity the experiment is actually after. Drives which
    #: calibrations are mandatory -- see QUANTITY_REQUIREMENTS.
    intended_quantity: str | None = None
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
        if self.intended_quantity is None:
            return ()
        return QUANTITY_REQUIREMENTS.get(self.intended_quantity.strip().lower(), ())

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

    def uncorrected_bias_findings(self) -> list[Any]:
        return [f for f in self.bias_findings() if f.code not in self.corrections_applied]

    def missing_standing_lenses(self) -> list[str]:
        return [name for name in STANDING_LENSES if name not in self.upstream]

    def blocked_lenses(self) -> list[str]:
        return sorted(
            name for name, v in self.upstream.items() if v.status == "BLOCKED"
        )

    def failed_lenses(self) -> list[str]:
        return sorted(name for name, v in self.upstream.items() if v.status == "FAIL")
