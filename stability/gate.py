"""The mechanical / environmental lens's committee verdict (lens 8).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full ``Verdict``
schema, as the other lenses do.

Conditional lens: docs/01 §4 convenes it for acquisitions longer than 30 min.
The threshold is reported rather than enforced -- sedimentation and drift scale
continuously with time and do not switch on at 30 minutes.

Since 2026-09-10 this lens can never report ``evidence: measured``, because the
drift entry in ``_assumed_inputs`` is unconditional. That is deliberate and it
is not a bug: drift is the dominant bias on a long acquisition, it is only
measurable while the acquisition runs, and there is no planning input that can
honestly discharge it. A long run therefore does not ``advance`` on this lens's
say-so alone; it advances once the run's own frames have been checked.
kb/decisions/2026-09-10-drift-is-not-a-design-element.md
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import StabilitySetup

LENS = "stability"


@dataclass
class Finding:
    severity: str  # fail | warn | info
    code: str
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)
    lens: str = LENS
    kind: str | None = None  # hard | bias | soft | info
    margin: float | None = None


@dataclass
class Verdict:
    status: str  # PASS | PASS_WITH_CHANGES | FAIL | BLOCKED
    feasibility: str = "UNKNOWN"  # ROUTINE .. INFEASIBLE
    evidence: str = "assumed"  # measured | assumed
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
        """The committee's criterion, from docs/05's Verdict schema:
        ``feasibility >= TIGHT and evidence == measured and no hard gate < 1.0``.

        The hard-gate clause is already covered by ``passed``: a hard gate below
        1.0 makes the status FAIL. The feasibility clause was missing until
        2026-08-12, which let an INFEASIBLE verdict whose only failures were
        bias-kind report ``advances=True``.
        """
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
# Phase 0 -- what can we not see, or not compute at all?
# --------------------------------------------------------------------------


def _missing_inputs(setup: StabilitySetup) -> list[Finding]:
    out: list[Finding] = []

    if setup.duration_min is None:
        out.append(
            Finding(
                "fail",
                "missing.duration",
                "No acquisition length on record. Every quantity in this lens "
                "scales with it -- drift, settling and evaporation are all "
                "rate times time.",
                action="Supply duration_min.",
            )
        )

    if setup.resolved_dof_um is None:
        out.append(
            Finding(
                "fail",
                "missing.depth_of_field",
                "No depth of field available, so there is nothing to judge "
                "axial drift or settling against. It comes from the objective "
                "(lens 1) plus an emission wavelength.",
                action="Supply the objective and emission_nm, or "
                "depth_of_field_um directly.",
            )
        )

    if setup.settling_velocity_um_per_s is None:
        out.append(
            Finding(
                "fail",
                "missing.settling_inputs",
                "Cannot compute sedimentation: it needs particle radius, the "
                "particle-minus-medium density difference, and the medium "
                "viscosity. Unlike the drift terms these are properties of the "
                "sample, not measurements of the instrument.",
                action="Supply particle_radius_um, delta_density_kg_m3 (0 for a "
                "density-matched suspension) and viscosity_pa_s.",
            )
        )

    return out


def _assumed_inputs(setup: StabilitySetup) -> list[str]:
    out: list[str] = []
    #: Drift, both axes. Unconditional: G29 and G30 left on 2026-09-10 because
    #: a drift rate is measured during a run, so no planning input can retire
    #: this entry. It stays in the ledger because the bias is real and lens 6
    #: registers it (validity/setup.py) -- a plan that does not evaluate drift
    #: has not shown that drift is small, and `stability.drift_budget` reports
    #: the rate the plan can absorb precisely so the runtime check has a number
    #: to be judged against.
    out.append(
        "drift, axial and lateral (not gated here -- measured from the "
        "acquisition, not from the plan; see stability.drift_budget)"
    )
    if not setup.vibration_measured:
        out.append(
            "vibration and stage repeatability (unmeasured and ungated -- no "
            "measurement channel exists)"
        )
    if not setup.chamber_sealed and setup.evaporation_rate_ul_per_hour is None:
        out.append("evaporation rate (chamber unsealed and rate unmeasured)")
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: StabilitySetup) -> Verdict:
    assumed = _assumed_inputs(setup)
    evidence = "measured" if not assumed else "assumed"

    # ---- Phase 0 --------------------------------------------------------
    blocking_findings = _missing_inputs(setup)
    facts = available_facts(setup)
    unrunnable = [
        c for c in CHECKS if c.kind != INFO and not set(c.requires).issubset(facts)
    ]

    if blocking_findings or unrunnable:
        for c in unrunnable:
            gaps = sorted(set(c.requires) - facts)
            if gaps and not any(f.code.startswith("missing.") for f in blocking_findings):
                blocking_findings.append(
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
            findings=blocking_findings,
        )

    # ---- Phase 1 -- every check runs -------------------------------------
    results: list[CheckResult] = [c.run(setup) for c in CHECKS]

    # ---- Phase 2 -- aggregate --------------------------------------------
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
                action="Measure an evaporation rate and seal the chamber if "
                "you can. The drift entry cannot be retired at planning time "
                "by design -- judge it from the acquisition's own frames.",
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
