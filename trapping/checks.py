"""Individual trapping checks.

Mirrors optics.checks: independent margins (achieved / required), not
booleans, for the same reasons -- the feasibility grade is the worst
margin, the bottleneck needs to say *which* check and by how much, and an
experiment at the edge of what a trap can do is a real situation worth a
number, not a bare FAIL.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dynamics import corner_frequency_hz, trap_depth_kt
from .goa import radial_stiffness_n_per_m

if TYPE_CHECKING:
    from .dynamics import TrapSetup

HARD = "hard"
INFO = "info"

MAX_MARGIN = 10.0

#: Rule of thumb (Ashkin 1992; Neuman & Block 2004), not a derived cutoff --
#: see trapping.dynamics.trap_depth_kt.
REQUIRED_TRAP_DEPTH_KT = 10.0
#: Berg-Sorensen & Flyvbjerg power-spectrum calibration convention (G14).
REQUIRED_SAMPLING_RATIO = 10.0


@dataclass
class CheckResult:
    code: str
    kind: str
    margin: float
    severity: str  # ok | info | fail
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.margin):
            self.margin = MAX_MARGIN
        self.margin = max(0.0, min(float(self.margin), MAX_MARGIN))


@dataclass
class Check:
    code: str
    kind: str
    #: which facts must exist before this check means anything
    requires: tuple[str, ...]
    run: Callable[["TrapSetup"], CheckResult]


def available_facts(setup: "TrapSetup") -> set[str]:
    """Which inputs this setup actually supplies.

    A check whose ``requires`` is not satisfied is not run and not graded
    -- it is reported as blocking, because a computed number would be
    fiction (see trapping.gate.evaluate).
    """
    facts: set[str] = set()
    if setup.medium.viscosity_pa_s is not None:
        facts.add("medium.viscosity")
    return facts


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


def check_effective_na(setup: "TrapSetup") -> CheckResult:
    """Is the objective's design NA actually reaching the sample?

    Informational, never a veto: an oil objective focusing into an aqueous
    sample traps perfectly well at the clipped NA, and for beads well above
    the focus size the clipped stiffness is within a few percent of a
    water-immersion objective's. What this check exists for is to make sure
    the *cost* of getting there is never silent -- see
    ``trapping.goa.ObjectiveBeam.effective_na``.
    """
    beam, medium = setup.beam, setup.medium
    na_eff = beam.effective_na(medium)

    if not beam.clipped_by_tir(medium):
        return _ok(
            "effective_na",
            INFO,
            MAX_MARGIN,
            f"Design NA {beam.na:.3g} is fully admitted by a sample medium of "
            f"n={medium.n:.4g}; the objective is index-matched to the sample.",
            design_na=beam.na,
            effective_na=na_eff,
            clipped_by_tir=False,
        )

    return CheckResult(
        "effective_na.clipped_by_tir",
        INFO,
        MAX_MARGIN,
        "info",
        f"Design NA {beam.na:.3g} is clipped to an effective {na_eff:.4g} by "
        f"total internal reflection at the coverslip/sample interface "
        f"(n={medium.n:.4g}). The trap still works -- but every number in this "
        "verdict now carries three limits: (1) stiffness is an UPPER BOUND, "
        "because Fresnel transmission goes to zero at the critical angle, so "
        "the outermost surviving rays carry vanishing power; (2) spherical "
        "aberration from the same index step is NOT modelled here, so the real "
        "focus is worse than the computed one; (3) that index step also pins "
        "how deep you may work -- lens 4's G17 limits depth to "
        f"1.85/|dn| um, about {1.85 / abs(1.518 - medium.n):.0f} um for an oil "
        "objective, and being pinned near the coverslip adds a Faxen wall-drag "
        "bias that this lens does not correct.",
        action="Prefer an index-matched objective if the quantity you want is "
        "an absolute force or drag. If you keep the oil objective, calibrate "
        "the trap in situ at the actual working height (a power-spectrum "
        "corner frequency gives kappa and the wall-corrected drag together), "
        "and re-run lens 4 for the depth limit.",
        numbers={
            "design_na": beam.na,
            "effective_na": na_eff,
            "clipped_by_tir": True,
            "medium_n": medium.n,
            "lost_na": round(beam.na - na_eff, 4),
        },
    )


def check_confinement(setup: "TrapSetup") -> CheckResult:
    """Does the trap actually restore toward the center at all?

    Checked on the weakest trap when the beam is split across several --
    that is the one that fails first.
    """
    power = setup.weakest_power_w()
    kappa = radial_stiffness_n_per_m(power, setup.bead, setup.medium, setup.beam)

    if kappa <= 0:
        return CheckResult(
            "trap.unstable",
            HARD,
            0.0,
            "fail",
            f"Radial stiffness is {kappa:.3g} N/m -- non-positive, so this "
            "configuration does not confine the bead at all.",
            action="Increase power, re-check the beam NA/wavelength against "
            "the bead size, or re-check the trap-splitting weights.",
            numbers={"stiffness_n_per_m": kappa, "power_w": power},
        )
    return _ok(
        "trap.confinement",
        HARD,
        MAX_MARGIN,
        f"Radial stiffness {kappa:.3g} N/m (positive, restoring).",
        stiffness_n_per_m=kappa,
        power_w=power,
    )


def check_trap_depth(setup: "TrapSetup") -> CheckResult:
    """G14's escape-resistance half: is the well deep enough against kT?"""
    power = setup.weakest_power_w()
    u_kt = trap_depth_kt(power, setup.bead, setup.medium, setup.beam, setup.temperature_k)
    margin = u_kt / REQUIRED_TRAP_DEPTH_KT

    if margin >= 1.0:
        return _ok(
            "trap.depth",
            HARD,
            margin,
            f"Trap depth (to the model's validity edge) is {u_kt:.1f} kT "
            f"(need ~{REQUIRED_TRAP_DEPTH_KT:.0f} kT for stable confinement).",
            trap_depth_kt=u_kt,
            power_w=power,
            temperature_k=setup.temperature_k,
        )
    return CheckResult(
        "trap.shallow",
        HARD,
        margin,
        "fail",
        f"Trap depth is only {u_kt:.1f} kT (need ~{REQUIRED_TRAP_DEPTH_KT:.0f} "
        "kT). Thermal motion will kick the bead out.",
        action="Increase power, use a larger or higher-index bead, or a "
        "higher-NA objective.",
        numbers={"trap_depth_kt": u_kt, "power_w": power, "temperature_k": setup.temperature_k},
    )


def check_sampling(setup: "TrapSetup") -> CheckResult:
    """G14: f_s >= 10*f_c.

    Reports the corner frequency either way; only gates when lens 2
    (detection) has actually supplied an achieved frame rate. This lens
    does not own frame rate, so its absence is informational, not
    blocking -- see docs/01-architecture.md's 7<->2 cross-lens constraint.
    """
    power = setup.weakest_power_w()
    kappa = radial_stiffness_n_per_m(power, setup.bead, setup.medium, setup.beam)
    f_c = corner_frequency_hz(kappa, setup.medium.viscosity_pa_s, setup.bead.radius_m)
    required_fps = REQUIRED_SAMPLING_RATIO * f_c

    if setup.detector_fps is None:
        return CheckResult(
            "sampling.unconfirmed",
            INFO,
            MAX_MARGIN,
            "info",
            f"Corner frequency {f_c:.0f} Hz -> needs >= {required_fps:.0f} fps "
            "to sample without aliasing bias (G14), but no achieved frame "
            "rate from the detection lens has been supplied yet.",
            action="Pass detector_fps once lens 2 (detection) has a "
            "realized frame rate, to gate this directly.",
            numbers={"corner_frequency_hz": f_c, "required_fps": required_fps},
        )

    margin = setup.detector_fps / required_fps
    if margin >= 1.0:
        return _ok(
            "sampling",
            HARD,
            margin,
            f"{setup.detector_fps:.0f} fps clears the {required_fps:.0f} fps "
            f"G14 requirement (corner frequency {f_c:.0f} Hz).",
            corner_frequency_hz=f_c,
            required_fps=required_fps,
            detector_fps=setup.detector_fps,
        )
    return CheckResult(
        "sampling.aliased",
        HARD,
        margin,
        "fail",
        f"{setup.detector_fps:.0f} fps is below the {required_fps:.0f} fps "
        f"G14 needs to resolve a {f_c:.0f} Hz corner frequency without "
        "aliasing bias.",
        action="Raise the frame rate (lens 2), or lower power / use a "
        "softer trap to bring the corner frequency down.",
        numbers={
            "corner_frequency_hz": f_c,
            "required_fps": required_fps,
            "detector_fps": setup.detector_fps,
        },
    )


CHECKS: list[Check] = [
    Check("effective_na", INFO, (), check_effective_na),
    Check("confinement", HARD, (), check_confinement),
    Check("trap_depth", HARD, (), check_trap_depth),
    Check("sampling", HARD, ("medium.viscosity",), check_sampling),
]


# --------------------------------------------------------------------------
# Feasibility grading
# --------------------------------------------------------------------------
#
# Added 2026-08-12. This lens was the only one without grading, which is why
# its Verdict had no ``feasibility`` field while the other seven did -- and
# without that field it could not honour docs/05's rule that a verdict only
# advances at TIGHT or better.

GRADES: list[tuple[float, str]] = [
    (3.0, "ROUTINE"),
    (1.5, "COMFORTABLE"),
    (1.0, "TIGHT"),
    (0.5, "HARD"),
    (0.2, "MARGINAL"),
    (0.0, "INFEASIBLE"),
]

GRADE_NOTES = {
    "ROUTINE": "Comfortable headroom. If it fails, the settings are not to blame.",
    "COMFORTABLE": "Normal range.",
    "TIGHT": "No headroom. Sample preparation quality decides the outcome.",
    "HARD": "Operating at the limit. May proceed, but low success rate and poor reproducibility.",
    "MARGINAL": "Data comes out, but interpret with great care.",
    "INFEASIBLE": "Impossible without improvement.",
}


def grade(margin: float) -> str:
    for threshold, name in GRADES:
        if margin >= threshold:
            return name
    return "INFEASIBLE"


#: Grades in ascending order of quality, derived from GRADES so the two cannot
#: drift apart.
GRADE_ORDER: tuple[str, ...] = tuple(name for _, name in reversed(GRADES))


def meets_grade(feasibility: str, minimum: str = "TIGHT") -> bool:
    """Is this feasibility at least ``minimum``?

    docs/05-consensus-gate.md's Verdict schema requires ``feasibility >= TIGHT``
    for a verdict to advance. ``UNKNOWN`` -- and anything unrecognised -- does
    not: an ungraded verdict has not earned the right to move on.
    """
    if feasibility not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(feasibility) >= GRADE_ORDER.index(minimum)
