"""The measurement-validity lens's committee verdict (lens 6).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full ``Verdict``
schema, as the other lenses do.

**Call this lens last.** Its primary input is the other lenses' verdicts, not
hardware facts, so running it first leaves it nothing to review. docs/05
gives it "G11 + final review of every bias gate".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from .checks import BIAS, CHECKS, GRADE_NOTES, GRADE_ORDER, HARD, INFO, SOFT, CheckResult, available_facts, grade, meets_grade
from .setup import ValiditySetup

LENS = "validity"


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
    #: Which intended physical quantity this finding belongs to, when several
    #: were judged. ``None`` means it applies to all of them (committee
    #: coverage, statistical power) or that only one quantity was judged.
    physical_quantity: str | None = None


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


def _missing_inputs(setup: ValiditySetup) -> list[Finding]:
    out: list[Finding] = []

    if not setup.upstream:
        out.append(
            Finding(
                "fail",
                "missing.upstream_verdicts",
                "No other lens has returned a verdict, so there is nothing to "
                "review. This lens's primary input is the rest of the "
                "committee's output, not hardware facts -- it has to be called "
                "last.",
                action="Run the standing lenses first (optics, detection, "
                "compute, sample, photo, plus trapping if the tweezers are in "
                "use) and pass their verdicts in as `upstream`.",
            )
        )

    if setup.intended_quantity is None:
        out.append(
            Finding(
                "fail",
                "missing.intended_quantity",
                "No intended physical quantity stated. Which calibrations "
                "matter depends entirely on it: a wrong pixel size ruins a "
                "diffusion coefficient and is irrelevant to a stoichiometry, "
                "and flat-field is the reverse.",
                action="State intended_quantity (position, diffusion, msd, "
                "rheology, morphology, intensity, concentration, "
                "stoichiometry, frap, colocalization, ...), or "
                "intended_quantities if the session is after more than one.",
            )
        )
    elif not setup.required_calibrations:
        out.append(
            Finding(
                "fail",
                "missing.quantity_requirements",
                f"'{setup.intended_quantity}' is not in the quantity table, so "
                "which calibrations it depends on is unknown. Guessing would "
                "mean certifying validity against the wrong criteria.",
                action="Add the quantity to "
                "validity.setup.QUANTITY_REQUIREMENTS with the calibrations it "
                "actually rests on, or use one of the existing names.",
            )
        )

    if setup.target_relative_error is None:
        out.append(
            Finding(
                "fail",
                "missing.target_error",
                "No target relative error stated, so statistical power (G11) "
                "has no criterion. docs/04 §9 marks G11 'ask' for exactly this "
                "reason -- the target comes from the experiment, not the "
                "instrument.",
                action="State target_relative_error, e.g. 0.05 for 5%.",
            )
        )

    if setup.resolved_n_particles is None or setup.n_frames is None:
        out.append(
            Finding(
                "fail",
                "missing.sample_size",
                "No particle count and/or frame count, so G11 cannot be "
                "computed. The particle count normally comes from lens 4's G19 "
                "(`geometry.count_in_field`); supplying that lens's verdict is "
                "enough.",
                action="Pass the sample lens's verdict in `upstream` with G19 "
                "evaluated, or set n_particles directly, and set n_frames.",
            )
        )

    return out


def _assumed_inputs(setup: ValiditySetup) -> list[str]:
    out: list[str] = []
    if setup.analysis_script is None:
        out.append(
            "analysis script (not declared; which script processes the data "
            "changes the setting requirements -- docs/05 Lens 6)"
        )
    if setup.n_particles is None and "sample" in setup.upstream:
        out.append(
            "particle count (taken from lens 4's G19 estimate, which rests on "
            "a stated concentration rather than a count of what is in frame)"
        )
    for code in setup.unverified_corrections():
        out.append(
            f"correction for '{code}' (declared applied, but no correction is "
            "registered for that bias, so the clearance is unaudited)"
        )
    return sorted(set(out))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------

#: Aggregate status when several quantities were judged. FAIL outranks BLOCKED
#: because it is the actionable one -- "change the setting" against BLOCKED's
#: "go measure". Neither advances, and the per-quantity table keeps both
#: visible, so the ordering only decides the headline.
_STATUS_RANK = {"PASS": 0, "PASS_WITH_CHANGES": 1, "BLOCKED": 2, "FAIL": 3}
_CONFIDENCE_RANK = {"high": 0, "low": 1, "none": 2}


def evaluate_per_quantity(setup: ValiditySetup) -> dict[str, Verdict]:
    """One verdict per intended quantity, in stated order.

    docs/05 Lens 6: the unit of verdict may be an individual physical quantity
    rather than the channel. Motion blur ruins the MSD of a session whose
    intensity profile is untouched, and one status cannot say that.
    """
    return {q: _evaluate_one(setup.for_quantity(q)) for q in setup.quantities}


def evaluate(setup: ValiditySetup) -> Verdict:
    """The committee-facing verdict.

    With no quantity or exactly one, this is the single-quantity gate. With
    several, it judges each separately and returns the aggregate -- every
    per-quantity verdict stays in ``metrics["validity.per_quantity"]`` and each
    finding is tagged with the quantity it belongs to, so nothing collapses.
    """
    quantities = setup.quantities
    if not quantities:
        return _evaluate_one(setup)
    if len(quantities) == 1:
        # Normalise, so a one-entry `intended_quantities` behaves exactly like
        # the singular field rather than reading an unset `intended_quantity`.
        return _evaluate_one(setup.for_quantity(quantities[0]))
    return _combine(evaluate_per_quantity(setup))


def _combine(per: dict[str, Verdict]) -> Verdict:
    """Aggregate per-quantity verdicts without losing the split.

    ``advances`` needs no special handling: an aggregate can only advance if
    every quantity passed, every one was `measured`, and the worst grade is at
    least TIGHT -- which is exactly "all of them advance".
    """
    status = max(
        (v.status for v in per.values()), key=lambda s: _STATUS_RANK.get(s, 3)
    )
    evidence = (
        "measured"
        if all(v.evidence == "measured" for v in per.values())
        else "assumed"
    )
    confidence = max(
        (v.confidence for v in per.values()),
        key=lambda c: _CONFIDENCE_RANK.get(c, 2),
    )

    grades = [v.feasibility for v in per.values()]
    feasibility = (
        "UNKNOWN"
        if any(g not in GRADE_ORDER for g in grades)
        else min(grades, key=GRADE_ORDER.index)
    )

    margins = {
        f"{q}:{code}": m for q, v in per.items() for code, m in v.margins.items()
    }
    blocked = [q for q, v in per.items() if v.status == "BLOCKED"]
    if blocked:
        bottleneck = f"{blocked[0]}:blocked"
    elif margins:
        bottleneck = min(margins, key=lambda k: margins[k])
    else:
        bottleneck = None

    # A finding identical across every quantity is quantity-independent
    # (committee coverage, statistical power) -- emit it once, untagged, rather
    # than repeating it per quantity.
    counts: dict[tuple, int] = {}
    for v in per.values():
        for f in v.findings:
            key = (f.code, f.message, f.severity)
            counts[key] = counts.get(key, 0) + 1

    findings: list[Finding] = []
    emitted: set[tuple] = set()
    for q, v in per.items():
        for f in v.findings:
            key = (f.code, f.message, f.severity)
            if counts[key] == len(per):
                if key in emitted:
                    continue
                emitted.add(key)
                findings.append(replace(f, physical_quantity=None))
            else:
                findings.append(replace(f, physical_quantity=q))

    metrics: dict = {q: v.metrics for q, v in per.items()}
    metrics["validity.per_quantity"] = {
        q: {
            "status": v.status,
            "feasibility": v.feasibility,
            "evidence": v.evidence,
            "advances": v.advances,
            "bottleneck": v.bottleneck,
        }
        for q, v in per.items()
    }

    return Verdict(
        status=status,
        feasibility=feasibility,
        evidence=evidence,
        confidence=confidence,
        bottleneck=bottleneck,
        margins=margins,
        assumed_inputs=sorted({a for v in per.values() for a in v.assumed_inputs}),
        findings=findings,
        metrics=metrics,
    )


def _evaluate_one(setup: ValiditySetup) -> Verdict:
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
                action="Name the analysis script that will process the data, "
                "and prefer a counted particle number over the concentration "
                "estimate.",
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
