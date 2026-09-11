"""Individual trapping checks -- G14a (confinement), G14b (trap depth),
G14c (sampling), plus two INFO reports that carry no number.

G14 was one number covering two of these and silently omitting the third
until 2026-09-10: `check_trap_depth` already called itself "G14's
escape-resistance half", and `check_confinement` -- `hard`, and the first
thing that fails -- had no number at all. Sub-lettered on lens 3's
convention (G12a-c, G13a-d) rather than given new numbers, because they are
one question asked three ways: can this trap hold this bead, deeply enough,
and can the camera see it move.

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
    # Added 2026-09-10. Until then `confinement` and `trap_depth` had EMPTY
    # `requires`, so they always ran -- and with a placeholder dial -> mW map
    # they graded a stiffness derived from a number nobody had measured. Two
    # hard gates on fiction. Now:
    #
    #   laser.calibrated  the power is real, so the model can be evaluated
    #   stiffness         kappa is knowable at all, from a measurement or
    #                     from the model on a real power
    if setup.calibration.measured:
        facts.add("laser.calibrated")
    if setup.calibration.measured or setup.measured_stiffness_n_per_m is not None:
        facts.add("stiffness")
    return facts


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    """Severity "info", not "ok" (2026-09-10).

    `trapping/gate.py` drops severity "ok" from `findings`, so a passing check
    computed its number and threw it away -- and the numbers ARE this lens:
    stiffness, trap depth in kT, corner frequency. On a configuration where
    everything passed, the only visible finding was the TIR notice. Same
    correction as sample/checks.py's G16c and photo/checks.py the same day:
    ungraded and invisible are different things.
    """
    return CheckResult(code, kind, margin, "info", message, None, numbers)


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
    """G14a: does the trap actually restore toward the center at all?

    Checked on the weakest trap when the beam is split across several --
    that is the one that fails first. A measured stiffness wins over the
    model (2026-09-10).
    """
    power = setup.weakest_power_w()
    kappa, kappa_from = setup.stiffness_n_per_m()

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
            numbers={
                "stiffness_n_per_m": kappa,
                "stiffness_source": kappa_from,
                "power_w": power,
            },
        )
    return _ok(
        "trap.confinement",
        HARD,
        MAX_MARGIN,
        f"Radial stiffness {kappa:.3g} N/m (positive, restoring), from the "
        f"{kappa_from}.",
        stiffness_n_per_m=kappa,
        stiffness_source=kappa_from,
        power_w=power,
    )


def check_trap_depth(setup: "TrapSetup") -> CheckResult:
    """G14b: is the well deep enough against kT?

    **Stays on the model even when a stiffness has been measured** (KH,
    2026-09-10). U comes from the power, not from kappa, so a measured kappa
    does not supply it. It could be rescaled -- `U/kappa` is a constant of
    this model, both being linear in power -- but that rescaling assumes the
    model's error is in its response to power and not in its shape, which
    nothing here establishes. So the depth is the model's, and the ratio is
    REPORTED instead of applied.
    """
    power = setup.weakest_power_w()
    u_kt = trap_depth_kt(power, setup.bead, setup.medium, setup.beam, setup.temperature_k)
    margin = u_kt / REQUIRED_TRAP_DEPTH_KT
    over = setup.model_over_measured()
    if (
        over is None
        and setup.measured_stiffness_n_per_m is not None
        and setup.measured_stiffness_dial_percent is None
    ):
        # The comparison is not merely absent, it is unanchored -- and the
        # difference matters, because a reader who sees a measured stiffness
        # in the setup will assume the model was checked against it.
        caveat = (
            " ⚠ A measured stiffness was supplied but not the dial it was "
            "taken at, so this depth CANNOT be checked against it: comparing "
            "them needs the model evaluated at the measurement's own power. "
            "The depth below is the model's, unvalidated. Record the dial "
            "with the next measurement and one line settles it."
        )
    else:
        caveat = (
        ""
        if over is None or 0.5 < over < 2.0
        else (
            f" ⚠ The model's stiffness is {over:.0f}x the measured one at this "
            f"dial, and this depth comes from the same model at the same "
            f"power -- so treat it as carrying the same factor. It is not "
            f"rescaled here: U/kappa is a model constant, but using it to "
            f"correct U assumes the error is in the response to power rather "
            f"than in the shape."
        )
    )

    if margin >= 1.0:
        return _ok(
            "trap.depth",
            HARD,
            margin,
            f"Trap depth (to the model's validity edge) is {u_kt:.1f} kT "
            f"(need ~{REQUIRED_TRAP_DEPTH_KT:.0f} kT for stable confinement)."
            + caveat,
            trap_depth_kt=u_kt,
            power_w=power,
            temperature_k=setup.temperature_k,
            model_over_measured_stiffness=over,
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
    """G14c: f_s >= 10*f_c.

    Reports the corner frequency either way; only gates when lens 2
    (detection) has actually supplied an achieved frame rate. This lens
    does not own frame rate, so its absence is informational, not
    blocking -- see docs/01-architecture.md's 7<->2 cross-lens constraint.
    """
    kappa, kappa_from = setup.stiffness_n_per_m()
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


def check_power_window(setup: "TrapSetup") -> CheckResult:
    """Propose the laser power, as a STIFFNESS window (KH, 2026-09-10).

    The two hard checks judge a power the operator already chose. This one
    answers the question they actually have: what power should I use? The
    bounds are the same two physical facts, inverted --

        FLOOR    trap depth >= 10 kT, or thermal motion kicks the bead out.
        CEILING  G14's f_s >= 10 f_c, so the corner frequency stays resolvable
                 at the frame rate lens 2 achieved: kappa <= 2*pi*gamma*f_s/10.

    ⚠ **REPORTED AS STIFFNESS, NOT AS A DIAL SETTING, AND THAT IS THE WHOLE
    POINT.** The dial% -> mW map here is an uncalibrated placeholder and the
    laser's power is neither readable nor settable on this instrument
    (kb/decisions/2026-09-04-closed-loop-trapping-measured.md), so any mW or
    dial figure is fiction. **Both ends of the stiffness window are free of
    it:**

    * the ceiling is ``2*pi*gamma*f_s/10`` -- only gamma and the frame rate;
    * the floor is ``10*kT / (U/kappa)``, and ``U/kappa`` is a constant of this
      model because the GOA stiffness and trap depth are both linear in power,
      so the scale cancels.

    So the window is a real physical statement even though the dial that
    reaches it is not, and a measured kappa can be compared against it
    directly -- which is the only way to use this lens quantitatively until
    something can be told a measured stiffness.

    INFO: it proposes, it does not grade. The two hard checks already judge
    whatever power was chosen.
    """
    gamma = 6 * math.pi * setup.medium.viscosity_pa_s * setup.bead.radius_m
    ref_power = setup.weakest_power_w()
    kappa_ref = radial_stiffness_n_per_m(ref_power, setup.bead, setup.medium, setup.beam)
    u_ref = trap_depth_kt(
        ref_power, setup.bead, setup.medium, setup.beam, setup.temperature_k
    )

    if kappa_ref <= 0 or u_ref <= 0:
        return CheckResult(
            "trap.power_window",
            INFO,
            MAX_MARGIN,
            "info",
            "No power window: the model returns a non-positive stiffness or "
            "trap depth at the reference dial, so there is nothing to scale.",
            numbers={"evaluated": False},
        )

    #: kappa per kT of trap depth -- a constant of the model, scale-free.
    kappa_per_kt = kappa_ref / u_ref
    kappa_min = REQUIRED_TRAP_DEPTH_KT * kappa_per_kt

    numbers = {
        "evaluated": True,
        "gamma_pn_s_per_um": round(gamma * 1e6, 6),
        "kappa_min_pn_per_um": round(kappa_min * 1e6, 4),
        "kappa_min_set_by": f"trap depth >= {REQUIRED_TRAP_DEPTH_KT:.0f} kT",
        "kappa_at_this_dial_pn_per_um": round(kappa_ref * 1e6, 3),
        "dial_percent": setup.dial_percent,
    }

    if setup.detector_fps is None:
        return CheckResult(
            "trap.power_window",
            INFO,
            MAX_MARGIN,
            "info",
            f"Stiffness floor {kappa_min * 1e6:.3f} pN/um "
            f"({numbers['kappa_min_set_by']}). No ceiling: G14 sets it from "
            "the achieved frame rate, and lens 2 has not supplied one. The "
            "dial is not the unit to state this in -- see the check's "
            "docstring.",
            action="Pass detector_fps from lens 2 for the ceiling.",
            numbers=numbers,
        )

    kappa_max = 2 * math.pi * gamma * setup.detector_fps / REQUIRED_SAMPLING_RATIO
    f_c_max = setup.detector_fps / REQUIRED_SAMPLING_RATIO
    numbers.update(
        kappa_max_pn_per_um=round(kappa_max * 1e6, 4),
        kappa_max_set_by=f"G14 at {setup.detector_fps:.0f} fps",
        corner_frequency_max_hz=round(f_c_max, 2),
        detector_fps=setup.detector_fps,
        #: Placeholder-derived, and labelled so at every use.
        dial_percent_for_kappa_max=round(
            setup.dial_percent * kappa_max / kappa_ref, 3
        )
        if kappa_ref > 0
        else None,
    )

    km = setup.measured_stiffness_n_per_m
    if km is None:
        measured_note = ""
    else:
        inside = kappa_min <= km <= kappa_max
        numbers["measured_stiffness_pn_per_um"] = round(km * 1e6, 3)
        numbers["measured_inside_window"] = inside
        measured_note = (
            f" The MEASURED {km * 1e6:.2f} pN/um is "
            f"{'inside' if inside else 'OUTSIDE'} the window, and it is what "
            "G14c was judged on."
        )

    if kappa_min > kappa_max:
        return CheckResult(
            "trap.power_window.empty",
            INFO,
            MAX_MARGIN,
            "info",
            f"NO stiffness satisfies both ends: the trap needs "
            f">= {kappa_min * 1e6:.3f} pN/um to hold the bead against kT, and "
            f"G14 at {setup.detector_fps:.0f} fps allows only "
            f"<= {kappa_max * 1e6:.3f} pN/um. Raise the frame rate (lens 2) or "
            "use a bead the trap holds at lower stiffness.",
            numbers=numbers,
        )

    return CheckResult(
        "trap.power_window",
        INFO,
        MAX_MARGIN,
        "info",
        f"Use a stiffness between **{kappa_min * 1e6:.3f} and "
        f"{kappa_max * 1e6:.2f} pN/um**: floor from "
        f"{numbers['kappa_min_set_by']}, ceiling from "
        f"{numbers['kappa_max_set_by']} (corner frequency must stay under "
        f"{f_c_max:.1f} Hz). This dial computes to "
        f"{kappa_ref * 1e6:.3f} pN/um." + measured_note + " For a drag "
        "calibration prefer the SOFT end -- x_eq = gamma*v/kappa, so a softer "
        "trap gives a bigger, more measurable displacement at the same "
        "velocity.",
        action="The dial equivalents are placeholder arithmetic and not a "
        "setting to type in: the dial-to-mW map is uncalibrated and this "
        "laser's power is neither readable nor settable. Compare a MEASURED "
        "kappa against the window instead -- the window itself does not depend "
        "on the placeholder.",
        numbers=numbers,
    )


def check_temperature_basis(setup: "TrapSetup") -> CheckResult:
    """Report what the temperature rests on. INFO, unnumbered, always visible.

    The 20 C this lens computes with is **the lab's air-conditioning
    setpoint** (KH, 2026-09-11), which makes it a sourced number rather than
    the bare default it was documented as. It is also the temperature of the
    ROOM, and every quantity here wants the sample's at the focus.

    That gap is trap heating, and trap heating is **ungated by decision**
    (CLAUDE.md E3, docs/06 D6, kb/decisions/2026-08-19-lens-7-scope.md). So
    this reports and does not grade -- an INFO caution is what KH asked for,
    and it replaces an `assumed_inputs` entry that used to block `advances` on
    every trapping verdict. Blocking on a residual the committee has already
    decided not to gate was charging twice for one decision.

    Why it is worth saying at all: `dD/D = 2.74 %/K` in water
    (kb/expertise/microrheology-standard-conditions.md), so a few K between the
    room and the focus is a few percent on any diffusivity, viscosity or
    stiffness inferred through kT or eta -- larger than most effects anyone is
    chasing here.
    """
    t_c = setup.temperature_k - 273.15
    numbers = {
        "temperature_k": round(setup.temperature_k, 2),
        "temperature_c": round(t_c, 2),
        "measured": setup.temperature_measured,
        "basis": "sample measurement" if setup.temperature_measured
        else "lab air-conditioning setpoint",
        "d_diffusivity_per_kelvin_pct": 2.74,
        "gated": False,
    }

    if setup.temperature_measured:
        return CheckResult(
            "trapping.temperature_basis",
            INFO,
            MAX_MARGIN,
            "info",
            f"Temperature {t_c:.1f} C is declared MEASURED, so kT and the "
            "viscosity rest on the sample rather than on the room.",
            action=None,
            numbers=numbers,
        )

    return CheckResult(
        "trapping.temperature_basis",
        INFO,
        MAX_MARGIN,
        "info",
        f"Temperature {t_c:.1f} C is the LAB SETPOINT, not a sample "
        "measurement. The room is known; the sample at the focus is not, and "
        "with a 1064 nm trap on and an oil objective against the coverslip the "
        "two differ. Water's dD/D is 2.74 %/K, so a few K is a few percent on "
        "anything inferred through kT or eta -- kappa included.",
        action="Ungated on purpose: the gap IS trap heating, which is ungated "
        "by decision (CLAUDE.md E3). Treat this as a caution, not a blocker. "
        "Set temperature_measured only for a measurement of the sample, and if "
        "one is ever taken and differs by more than ~2 K, every stored kappa "
        "and D needs rescaling rather than re-running "
        "(kb/expertise/microrheology-standard-conditions.md).",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("effective_na", INFO, (), check_effective_na),
    # G14a/b/c and their `requires`, both added 2026-09-10. Until then these
    # two had EMPTY requires and so always ran -- grading a stiffness derived
    # from a placeholder dial -> mW map. Two hard gates on fiction.
    Check("confinement", HARD, ("stiffness",), check_confinement),
    Check("trap_depth", HARD, ("laser.calibrated",), check_trap_depth),
    Check("sampling", HARD, ("stiffness", "medium.viscosity"), check_sampling),
    # Proposes rather than judges -- see check_power_window.
    Check("power_window", INFO, ("medium.viscosity",), check_power_window),
    Check("temperature_basis", INFO, (), check_temperature_basis),
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
