"""The compute-resource lens's committee verdict.

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema -- see detection/gate.py's module docstring for the same
rationale (docs/07-roadmap.md: lens 2/3 get lens 1's complete schema).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import AcquisitionResourceSetup

LENS = "compute"


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


def _missing_inputs(setup: AcquisitionResourceSetup) -> list[Finding]:
    out: list[Finding] = []

    if setup.disk_bandwidth_mb_s is None:
        out.append(
            Finding(
                "fail",
                "missing.disk_bandwidth",
                "No measured sustained disk write bandwidth on record. Data "
                "rate (G12) cannot be judged against a guess.",
                action="Run `python -m calibration.cli disk-bandwidth <dir>` "
                "on the microscope PC's actual acquisition drive -- this "
                "cannot be computed, only measured.",
            )
        )
    if setup.resolved_buffer_frames() is None:
        out.append(
            Finding(
                "fail",
                "missing.buffer_frames",
                "No circular buffer frame count on record. Buffer headroom "
                "(G13) is undefined without it.",
                action="Read CircularBufferFrameCount from Micro-Manager, or "
                "supply ram_budget_mb to derive it.",
            )
        )
    if setup.acquisition_duration_s is None or setup.free_disk_gb is None:
        out.append(
            Finding(
                "fail",
                "missing.capacity_inputs",
                "No planned acquisition duration and/or free disk space on "
                "record. Total-capacity headroom (G13) is undefined.",
                action="Supply acquisition_duration_s and free_disk_gb.",
            )
        )

    return out


def _assumed_inputs(setup: AcquisitionResourceSetup) -> list[str]:
    out: list[str] = []
    if setup.circular_buffer_frames is None and setup.ram_budget_mb is not None:
        out.append(
            "circular buffer frame count (derived from a RAM budget, not read "
            "from MM's CircularBufferFrameCount)"
        )
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: AcquisitionResourceSetup) -> Verdict:
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

    # ---- Phase 1 — every check runs -------------------------------------
    results: list[CheckResult] = [c.run(setup) for c in CHECKS]

    # ---- Phase 2 — aggregate ---------------------------------------------
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
                action="Read the literal MM CircularBufferFrameCount and re-run.",
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
