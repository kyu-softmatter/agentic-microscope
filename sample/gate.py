"""The sample-geometry lens's committee verdict (lens 4).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema, as compute.gate and detection.gate do.

Phase 0 here carries a rule the other lenses do not need: a sample whose
refractive index cannot be described by one scalar -- ATPS with two phases,
or a birefringent liquid crystal -- must BLOCK rather than fall back to the
water default. kb/expertise/sample-medium-refractive-index.md records that
exclusion; this is where it is enforced instead of remembered.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import SampleSetup

LENS = "sample"


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


def _missing_inputs(setup: SampleSetup) -> list[Finding]:
    out: list[Finding] = []

    if setup.birefringent:
        out.append(
            Finding(
                "fail",
                "unmodellable.birefringent",
                "The sample is birefringent, so one isotropic refractive "
                "index does not describe it (5CB: n_o ~1.53, n_e ~1.71). "
                "Mismatch and focal shift depend on orientation.",
                action="Model the sample as birefringent, or restrict the "
                "verdict to a single known orientation and supply that index "
                "explicitly. Do not let the water default stand in.",
            )
        )

    if setup.multiphase and not setup.phase_n:
        out.append(
            Finding(
                "fail",
                "unmodellable.multiphase",
                "The sample has more than one phase with different refractive "
                "indices (ATPS dextran/PEG), so a single n_sample is "
                "meaningless and the interface itself refracts. "
                "docs/05-consensus-gate.md Lens 4 calls this out explicitly.",
                action="Supply phase_n, e.g. "
                '{"dextran_rich": 1.348, "peg_rich": 1.339}, from a '
                "refractometer reading of each phase, and judge each phase "
                "separately.",
            )
        )

    if setup.imaging_depth_um is None:
        out.append(
            Finding(
                "fail",
                "missing.imaging_depth",
                "No imaging depth on record. Working-distance headroom (G16) "
                "and depth-dependent aberration (G17) are both undefined "
                "without it.",
                action="Supply imaging_depth_um -- how far past the coverslip "
                "the focal plane must reach.",
            )
        )

    if setup.objective.wd_um is None:
        out.append(
            Finding(
                "fail",
                "missing.working_distance",
                f"No working distance on record for "
                f"'{setup.objective.label}'. G16 cannot be judged against a "
                "guess.",
                action="Add wd_um to the objective entry. "
                "kb/systems/current.md > objectives has the catalogue values "
                "for all six objectives on the nosepiece.",
            )
        )

    if setup.objective.na <= 0:
        out.append(
            Finding(
                "fail",
                "missing.na",
                f"Objective '{setup.objective.label}' has no NA. Neither NA "
                "feasibility (G15) nor resolution is computable.",
                action="Add the engraved NA to the objective entry.",
            )
        )

    return out


def _assumed_inputs(setup: SampleSetup) -> list[str]:
    """What this verdict leaned on that was not measured for this experiment.

    The sample-medium refractive index used to be listed here. It is not any
    more: KH confirmed DEFAULT_N_SAMPLE = 1.333 on 2026-08-19 as the settled
    value for aqueous samples, so falling back to it is no longer an
    assumption. The media that default does *not* cover (ATPS, glycerol,
    birefringent) BLOCK in _missing_inputs instead of arriving here.
    """
    out: list[str] = []
    if setup.coverslip_actual_um is None:
        out.append(
            f"coverslip thickness (assumed the lab's "
            f"{setup.resolved_coverslip_um:.0f} um glass against the "
            f"objective's {setup.design_coverslip_um:.0f} um design; a nominal "
            f"product thickness, not a reading of the coverslip on the stage, "
            f"and the real spread is wider than the stated tolerance)"
        )
    if not setup.objective.verified_na:
        out.append(f"NA of '{setup.objective.label}' (not marked verified)")
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(setup: SampleSetup) -> Verdict:
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
                action="Measure the coverslip with a micrometer and pass "
                "--coverslip-actual-um, then re-run. Since the sample-medium "
                "index was settled at 1.333, an unmeasured coverslip is "
                "normally the last assumption left in this lens.",
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
