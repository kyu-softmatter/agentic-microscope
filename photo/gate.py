"""The photo-perturbation lens's committee verdict (lens 5).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema, as compute.gate, detection.gate and sample.gate do.

Phase 0 here is unusually load-bearing. Every gate in this lens needs mW at the
sample plane, and `power_at_sample_mw` is empty for every line of every source
in data/light_sources.yaml. So this lens BLOCKS on the real instrument today,
and that is the correct answer rather than a shortcoming: a percent setting in
the metadata is not a physical quantity, and docs/04 §9 marks G10 BLOCKED for
exactly this reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import IlluminationSetup

LENS = "photo"


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


def _missing_inputs(setup: IlluminationSetup) -> list[Finding]:
    out: list[Finding] = []

    if setup.resolved_irradiance is None:
        out.append(
            Finding(
                "fail",
                "missing.power_at_sample",
                "No measured mW at the sample plane (and/or no illuminated "
                "area), so irradiance is unknown and every dose quantity in "
                "this lens is undefined. The metadata's percent setting is not "
                "a physical quantity and does not transfer between "
                "instruments.",
                action="Measure sample-plane power with a power meter at each "
                "level setting and record it in "
                "data/light_sources.yaml > power_at_sample_mw. This is the "
                "project's top blocker -- it cannot be computed, only measured.",
            )
        )

    if setup.exposure_ms is None or setup.n_frames is None:
        out.append(
            Finding(
                "fail",
                "missing.exposure_plan",
                "No exposure and/or frame count on record. Total dose (G22) "
                "and the bleaching budget (G10) both scale with them.",
                action="Supply exposure_ms and n_frames.",
            )
        )

    if setup.bleach_photons is None:
        out.append(
            Finding(
                "fail",
                "missing.bleach_photons",
                "The dye has no `bleach_photons` on record, so the "
                "photobleaching budget (G10) has nothing to count against. "
                "docs/04 §6: the qualitative `photostability` grade is "
                "explicitly not a substitute.",
                action="Add bleach_photons (mean photons emitted before "
                "bleaching) to the dye's entry in data/fluorophores.yaml, from "
                "the literature or a measured decay curve. It is empty for "
                "every dye in the registry today.",
            )
        )

    if setup.lifetime_ns is None:
        out.append(
            Finding(
                "fail",
                "missing.lifetime",
                "The dye has no fluorescence lifetime on record, so the "
                "saturation check (G20) cannot tell whether emission is still "
                "linear in power.",
                action="Add lifetime_ns to the dye's entry in "
                "data/fluorophores.yaml.",
            )
        )

    if setup.photoresponsive and setup.light_driving_threshold_w_cm2 is None:
        out.append(
            Finding(
                "fail",
                "missing.light_driving_threshold",
                "The sample is marked photoresponsive but no irradiance "
                "threshold is on record, so there is no basis for deciding "
                "whether the illumination is driving it (docs/06 D2).",
                action="Supply light_driving_threshold_w_cm2 from a control "
                "experiment -- vary the light level with everything else "
                "fixed and find where the behaviour changes. A guessed "
                "threshold here would be worse than none.",
            )
        )

    return out


def _assumed_inputs(setup: IlluminationSetup) -> list[str]:
    out: list[str] = []
    if setup.quantum_yield is None:
        out.append("quantum yield (absent, so emitted photons cannot be scaled)")
    if setup.frame_interval_ms is None:
        out.append("frame interval (duty cycle not computed)")
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: IlluminationSetup) -> Verdict:
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
                action="Fill in the dye's quantum yield and the frame interval "
                "and re-run.",
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
