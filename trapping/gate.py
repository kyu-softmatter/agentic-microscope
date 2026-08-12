"""The trapping lens: committee member #7 (conditional -- called only when
optical tweezers are in use, docs/01-architecture.md "Conditional").

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and Verdict
schema (docs/08 "The same structure is used for the other lenses"):

    Phase 0   input availability -> BLOCKED if a required fact is missing
    Phase 1   every check runs and returns a margin
    Phase 2   aggregate: hard veto, bottleneck

Narrower than optics.gate in one way: there is no feasibility grade here
yet (that needs a wider spread of check kinds than this lens currently
has -- see trapping/README notes in the trapping-lens7-groundwork memory).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import CHECKS, HARD, INFO, CheckResult, available_facts
from .dynamics import TrapSetup
from .goa import ray_optics_regime

LENS = "trapping"


@dataclass
class Finding:
    severity: str  # fail | info
    code: str
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)
    lens: str = LENS
    kind: str | None = None  # hard | info
    margin: float | None = None


@dataclass
class Verdict:
    """What the physics says and how sure we are -- see optics.gate.Verdict
    for the three-axis rationale (status / evidence / advances)."""

    status: str  # PASS | FAIL | BLOCKED
    evidence: str = "assumed"  # measured | assumed
    confidence: str = "low"
    bottleneck: str | None = None  # code of the worst-margin check
    margins: dict[str, float] = field(default_factory=dict)
    assumed_inputs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def advances(self) -> bool:
        """The committee's criterion: sound **and** grounded in measurement."""
        return self.passed and self.evidence == "measured"

    def to_dict(self) -> dict:
        return {
            "lens": LENS,
            "status": self.status,
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


def _blocking_findings(setup: TrapSetup) -> list[Finding]:
    out: list[Finding] = []

    regime, x = ray_optics_regime(setup.bead, setup.beam, setup.medium)
    if regime != "ray_optics":
        out.append(
            Finding(
                "fail",
                "missing.regime",
                f"Mie size parameter x={x:.2f} puts this bead in the "
                f"'{regime}' regime, not ray optics -- a GOA force number "
                "here would be fiction.",
                action="Use Rayleigh scattering theory (x<0.3) or full "
                "Lorenz-Mie theory / GLMT (x~1) instead; trapping.goa only "
                "covers x>10.",
            )
        )
    return out


def _assumed_inputs(setup: TrapSetup) -> list[str]:
    out: list[str] = []
    if not setup.calibration.measured:
        out.append("laser dial% -> mW calibration")
    if not setup.temperature_measured:
        out.append(f"medium temperature ({setup.temperature_k:.1f} K default)")
    return out


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: TrapSetup) -> Verdict:
    assumed = _assumed_inputs(setup)
    evidence = "measured" if not assumed else "assumed"

    # ---- Phase 0 --------------------------------------------------------
    blocking_findings = _blocking_findings(setup)
    facts = available_facts(setup)
    unrunnable = [
        c for c in CHECKS if c.kind != INFO and not set(c.requires).issubset(facts)
    ]

    if blocking_findings or unrunnable:
        for c in unrunnable:
            gaps = sorted(set(c.requires) - facts)
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
            evidence=evidence,
            confidence="none",
            assumed_inputs=assumed,
            findings=blocking_findings,
        )

    # ---- Phase 1 — every check runs -------------------------------------
    results: list[CheckResult] = [c.run(setup) for c in CHECKS]

    # ---- Phase 2 — aggregate ---------------------------------------------
    hard_failed = [r for r in results if r.kind == HARD and r.margin < 1.0]
    gradeable = [r for r in results if r.kind == HARD]
    worst = min(gradeable, key=lambda r: r.margin) if gradeable else None
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
                action="Measure the laser dial calibration curve and/or "
                "confirm the sample temperature, then re-run.",
                kind=INFO,
            )
        )

    status = "FAIL" if hard_failed else "PASS"

    return Verdict(
        status=status,
        evidence=evidence,
        confidence="high" if evidence == "measured" else "low",
        bottleneck=bottleneck,
        margins={r.code: round(r.margin, 3) for r in results},
        assumed_inputs=assumed,
        findings=findings,
        metrics={r.code: r.numbers for r in results},
    )
