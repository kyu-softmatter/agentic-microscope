"""The detection lens's committee verdict.

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema (feasibility included, per docs/07-roadmap.md's note that
lens 2/3 should get lens 1's complete schema, not lens 7's narrower one):

    Phase 0   input availability -> BLOCKED if a required fact is missing
    Phase 1   every check runs, independently, and returns a margin
    Phase 2   aggregate: hard veto, feasibility grade, bottleneck

No early return between checks -- see optics/gate.py's module docstring for
the full rationale (the experimenter walks to the microscope once).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import DetectionSetup

LENS = "detection"


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
    """See optics.gate.Verdict for the three-axis rationale
    (status / evidence / feasibility)."""

    status: str  # PASS | PASS_WITH_CHANGES | FAIL | BLOCKED
    feasibility: str = "UNKNOWN"  # ROUTINE .. INFEASIBLE
    evidence: str = "assumed"  # measured | assumed
    confidence: str = "low"
    bottleneck: str | None = None  # code of the worst gradeable check
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


def _missing_inputs(setup: DetectionSetup) -> list[Finding]:
    out: list[Finding] = []
    obj = setup.objective
    cam = setup.camera

    if not obj.na or obj.na <= 0:
        out.append(
            Finding(
                "fail",
                "missing.na",
                f"Objective '{obj.label}' has no NA. Resolution and pixel-size "
                "checks are undefined without it.",
                action="Read the NA off the objective barrel.",
            )
        )
    if not cam.detector.pixel_um:
        out.append(
            Finding(
                "fail",
                "missing.pixel_um",
                f"Detector '{cam.detector.label}' has no pixel pitch on record.",
                action=f"Add '{cam.detector.label}' pixel pitch to data/detectors.yaml.",
            )
        )
    if setup.acquisition.task_kind not in {"imaging", "tracking"}:
        out.append(
            Finding(
                "fail",
                "missing.task_kind",
                "No task kind specified. G5 (sampling) and G8 (motion blur) go "
                "in opposite directions for morphology imaging vs. single-"
                "particle tracking (docs/04 §2) -- this is not a default worth "
                "guessing.",
                action="Ask the experimenter: is this morphology imaging or "
                "single-particle tracking?",
            )
        )
    if cam.effective_bit_depth() is None or cam.effective_read_noise_e() is None:
        out.append(
            Finding(
                "fail",
                "missing.detector_mode",
                f"Detector '{cam.detector.label}' mode {cam.mode!r} has no bit "
                "depth or read noise on record.",
                action="Confirm which camera mode is in use and either pass "
                "camera.mode, or add the mode to data/detectors.yaml.",
            )
        )
    if cam.effective_row_time_us() is None:
        out.append(
            Finding(
                "fail",
                "missing.row_time",
                "No row/line readout time on record. Frame-rate realizability "
                "(G9) and motion blur (G8) are both undefined without it.",
                action="Run `python -m calibration.cli camera-readout` on the "
                "microscope PC once reconnected, or supply camera.row_time_us.",
            )
        )

    return out


def _assumed_inputs(setup: DetectionSetup) -> list[str]:
    out: list[str] = []
    if not setup.objective.verified_na:
        out.append(f"{setup.objective.label} NA")
    if setup.camera.detector.dark_e_per_s is None:
        out.append(f"{setup.camera.detector.label} dark current (assumed 0 e-/s)")
    if setup.camera.row_time_us is None and setup.camera.resolved_mode() is not None:
        out.append(f"{setup.camera.detector.label} row time (datasheet mode value, not measured)")
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: DetectionSetup) -> Verdict:
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
                action="Measure the outstanding facts and re-run.",
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
