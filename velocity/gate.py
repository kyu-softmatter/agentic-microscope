"""Lens 9's committee verdict -- the velocity lens.

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and the full
``Verdict`` schema, as the other eight do.

**Conditional lens**, like 7 and 8: convened when the experiment commands a
motion -- a stage ramp, a trap sweep -- and absent otherwise. Absent is a hole
and not a pass (CLAUDE.md E4), and nothing in `validity`'s `STANDING_LENSES`
can express that yet; that gap is deferred to the pipeline rework.

⚠ **THIS LENS FAILS ON EVERY REAL CONFIGURATION TODAY, AND THAT IS THE POINT.**
L9.1 is `hard` and there is no commanded-versus-actual velocity anywhere in the
repository, so the verdict is FAIL until somebody measures one. That is not a
placeholder: the whole reason the lens exists is that a Stokes-drag
calibration multiplies the commanded velocity straight into
``kappa = gamma v / x_eq``, and nothing was guarding it. Reporting FAIL is more
honest than the silence that preceded it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import (
    BIAS,
    CHECKS,
    GRADE_NOTES,
    HARD,
    INFO,
    SOFT,
    CheckResult,
    available_facts,
    grade,
    meets_grade,
)
from .setup import VelocitySetup

LENS = "velocity"


@dataclass
class Finding:
    severity: str  # fail | warn | info
    code: str
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)
    lens: str = LENS
    kind: str | None = None
    margin: float | None = None


@dataclass
class Verdict:
    status: str  # PASS | PASS_WITH_CHANGES | FAIL | BLOCKED
    feasibility: str = "UNKNOWN"
    evidence: str = "assumed"
    confidence: str = "low"
    bottleneck: str | None = None
    margins: dict[str, float] = field(default_factory=dict)
    assumed_inputs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status in {"PASS", "PASS_WITH_CHANGES"}

    @property
    def advances(self) -> bool:
        return (
            self.passed
            and self.evidence == "measured"
            and meets_grade(self.feasibility)
        )

    def to_dict(self) -> dict:
        return {
            "lens": LENS,
            "status": self.status,
            "feasibility": self.feasibility,
            "feasibility_note": GRADE_NOTES.get(self.feasibility, ""),
            "advances": self.advances,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "bottleneck": self.bottleneck,
            "margins": self.margins,
            "assumed_inputs": self.assumed_inputs,
            "metrics": self.metrics,
            "findings": [asdict(f) for f in self.findings],
        }


# --------------------------------------------------------------------------
# Phase 0
# --------------------------------------------------------------------------


def _missing_inputs(setup: VelocitySetup) -> list[Finding]:
    out: list[Finding] = []

    if setup.commanded_velocity_um_per_s is None:
        out.append(
            Finding(
                "fail",
                "missing.commanded_velocity",
                "No commanded velocity. This lens has nothing to judge without "
                "it -- it is the input whose scale and consequences are the "
                "whole subject.",
                action="Supply commanded_velocity_um_per_s, and `driver` "
                "(piezo_stage or aod_trap).",
            )
        )

    if setup.target_relative_error is None:
        out.append(
            Finding(
                "fail",
                "missing.target_error",
                "No target relative error. **Every bound in this lens is "
                "derived from it** -- the offset floor is sigma/target and the "
                "step duration is ln(1/target) time constants -- so without it "
                "there is no window, only arithmetic. Picking a value would be "
                "originating a physical number.",
                action="State target_relative_error, e.g. 0.05 for 5% on "
                "kappa. It comes from the experiment, not the instrument "
                "(docs/04 §9).",
            )
        )

    if setup.resolved_drag_pn_s_per_um is None:
        out.append(
            Finding(
                "fail",
                "missing.drag",
                "Cannot compute the drag: it needs particle_radius_um and "
                "viscosity_pa_s. Both are sample properties, so they are "
                "answerable rather than measurements of the instrument.",
                action="Supply particle_radius_um and viscosity_pa_s.",
            )
        )

    if not setup.stiffness_pn_per_um:
        out.append(
            Finding(
                "fail",
                "missing.stiffness",
                "No trap stiffness. Lens 7 owns it -- "
                "`TrapSetup.stiffness_n_per_m()` returns it with its "
                "provenance, and a MEASURED value beats the ray-optics model. "
                "The offset is gamma*v/kappa, so without kappa there is no "
                "displacement to judge.",
                action="Run lens 7 and pass its stiffness in pN/um. A measured "
                "kappa exists for this bench: 3.65-4.5 pN/um, 2026-09-03.",
            )
        )

    if not setup.localization_sigma_nm:
        out.append(
            Finding(
                "fail",
                "missing.localization_sigma",
                "No localization precision. Lens 2 computes it "
                "(`detection.photometry.localization_variance_nm2`), and it "
                "sets the floor of the velocity window -- the offset has to "
                "exceed the noise by 1/target.",
                action="Run lens 2 and pass its 1-sigma localization "
                "precision in nm.",
            )
        )

    if setup.step_duration_ms is None:
        out.append(
            Finding(
                "fail",
                "missing.step_duration",
                "No velocity-step duration, so whether the offset has time to "
                "arrive cannot be judged. The bead approaches its steady "
                "offset exponentially and a short step reads low, which makes "
                "kappa read high.",
                action="Supply step_duration_ms -- the time the stage or trap "
                "holds one velocity before changing it.",
            )
        )

    return out


def _assumed_inputs(setup: VelocitySetup) -> list[str]:
    out: list[str] = []
    if not setup.velocity_time_base_verified:
        out.append(
            "commanded velocity time base (never checked on this instrument; "
            "the distance half is corroborated to 0.24%, the time half is not)"
        )
    elif setup.velocity_scale_ratio is None:
        out.append(
            "velocity scale ratio (declared verified without a measured "
            "actual/commanded number, so nothing downstream can re-check it)"
        )
    if setup.driver is None:
        out.append("which subsystem drives the motion (piezo_stage or aod_trap)")
    out.append(
        "near-wall drag (gamma here is the unbounded Stokes value; lens 4's "
        "L4.4 bounds the inflation and deliberately does not correct it, so a "
        "velocity chosen from this window inherits it)"
    )
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: VelocitySetup) -> Verdict:
    assumed = _assumed_inputs(setup)
    evidence = "measured" if not assumed else "assumed"

    blocking = _missing_inputs(setup)
    facts = available_facts(setup)
    unrunnable = [
        c for c in CHECKS if c.kind != INFO and not set(c.requires).issubset(facts)
    ]

    if blocking or unrunnable:
        for c in unrunnable:
            gaps = sorted(set(c.requires) - facts)
            if gaps and not any(f.code.startswith("missing.") for f in blocking):
                blocking.append(
                    Finding(
                        "fail",
                        f"missing.{gaps[0]}",
                        f"Check '{c.code}' needs {', '.join(gaps)}, which this "
                        "configuration does not supply.",
                        action="Supply the missing fact; a computed value here "
                        "would be fiction.",
                    )
                )
        return Verdict(
            status="BLOCKED",
            feasibility="UNKNOWN",
            evidence=evidence,
            confidence="none",
            assumed_inputs=assumed,
            findings=blocking,
        )

    results: list[CheckResult] = [c.run(setup) for c in CHECKS]

    hard_failed = [r for r in results if r.kind == HARD and r.margin < 1.0]
    gradeable = [r for r in results if r.kind in (HARD, SOFT, BIAS)]
    worst = min(gradeable, key=lambda r: r.margin) if gradeable else None

    feasibility = grade(worst.margin) if worst else "UNKNOWN"
    bottleneck = worst.code if worst else None

    findings = [
        Finding(
            severity=r.severity,
            code=r.code,
            message=r.message,
            action=r.action,
            numbers=r.numbers,
            kind=r.kind,
            margin=r.margin,
        )
        for r in results
        if r.severity != "ok"
    ]

    if assumed:
        findings.append(
            Finding(
                "info",
                "evidence.assumed",
                "This verdict used assumed values for: " + ", ".join(assumed) + ".",
                action="The time base is the one that matters and the one "
                "nobody has measured -- see L9.1's action. The near-wall entry "
                "cannot be retired here by design; it belongs to lens 4 and "
                "reaches lens 6's ledger from there.",
                kind=INFO,
            )
        )

    if hard_failed:
        status = "FAIL"
    elif any(f.severity in {"fail", "warn"} for f in findings):
        status = "PASS_WITH_CHANGES"
    else:
        status = "PASS"

    return Verdict(
        status=status,
        feasibility=feasibility,
        evidence=evidence,
        confidence="high" if evidence == "measured" else "low",
        bottleneck=bottleneck,
        margins={r.code: round(r.margin, 3) for r in results},
        assumed_inputs=assumed,
        findings=findings,
        metrics={r.code: r.numbers for r in results},
    )
