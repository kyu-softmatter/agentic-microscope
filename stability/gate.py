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

from .checks import BIAS, CHECKS, GRADE_NOTES, HARD, INFO, SOFT, CheckResult, available_facts
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
    #: REPORT | BLOCKED. A reporting section, not a judging lens, since
    #: 2026-09-10 -- every check here is INFO, so PASS / PASS_WITH_CHANGES /
    #: FAIL are gone: nothing in this lens can pass or fail. BLOCKED survives
    #: because a report still cannot be written without its inputs. Same shape
    #: as lens 5 took on the same day, and for a related reason.
    status: str
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
        """A report is written or it is not; it does not pass."""
        return self.status == "REPORT"

    @property
    def advances(self) -> None:
        """**Not applicable.** ``None``, not ``False``.

        A judging lens advances or refuses to. This section does neither: with
        every check INFO it cannot block a proposal and it cannot bless one, so
        ``False`` would read as a refusal and ``True`` would claim an
        endorsement it has no gate to base on. Lens 5 took the same shape on
        the same day.

        ⚠ **This is what the unconditional drift entry in ``assumed_inputs``
        cost.** While this lens still graded, that entry pinned ``evidence`` to
        ``assumed`` and so pinned ``advances`` to ``False`` -- drift blocked a
        long acquisition from advancing on lens 8 alone. It no longer blocks
        anything, because a reporting section has nothing to block with. The
        entry stays and ``evidence`` is still reported, so a reader can see the
        bias is uncorrected; nothing in the code stops on it. Lens 6 is the
        only place left that can.
        """
        return None

    def to_dict(self) -> dict:
        return {
            "lens": LENS,
            "status": self.status,
            "feasibility": self.feasibility,
            "feasibility_note": GRADE_NOTES.get(self.feasibility, ""),
            #: None -- see Verdict.advances. Consumers must not read this as
            #: False; a reporting section neither advances nor refuses.
            "advances": self.advances,
            "reporting_only": True,
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

    # NOTHING ELSE BLOCKS, AND THAT IS THE POINT OF THE 2026-09-10 REVIEW.
    # `missing.depth_of_field` and `missing.settling_inputs` stood here and
    # made Phase 0 all-or-nothing: one absent number returned BLOCKED with
    # empty `margins` and empty `metrics`, so a missing density contrast took
    # down the evaporation report too, and a missing drift rate -- the standing
    # state of the repository -- took down everything. Each check now reports
    # its own absent input and says where it comes from, which is strictly more
    # information than a blanket refusal. Duration survives because it is the
    # one input every quantity here is a rate against, and because the
    # convening decision (docs/01 §4) is a comparison to it.
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

    # ---- Phase 2 -- collate ----------------------------------------------
    # Nothing here is gradeable, by construction: every check is INFO since
    # 2026-09-10. So there is no worst margin, no bottleneck and no
    # feasibility -- and "UNKNOWN" would be wrong in the way that matters,
    # because UNKNOWN is what an ungraded JUDGEMENT looks like. This is not an
    # ungraded judgement; it is a report. Lens 5 asserts the same invariant.
    gradeable = [r for r in results if r.kind in (HARD, SOFT, BIAS)]
    assert not gradeable, (
        "stability/ is a reporting section: every check must be INFO. "
        f"Gradeable: {[r.code for r in gradeable]}"
    )
    feasibility = "N/A"
    bottleneck = None

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
                "This report rests on assumed values for: "
                + ", ".join(assumed)
                + ".",
                action="The drift entry cannot be retired at planning time by "
                "design -- judge it from the acquisition's own frames. Any "
                "others listed above can be: seal the chamber, or weigh a rate.",
                kind=INFO,
            )
        )

    return Verdict(
        status="REPORT",
        feasibility=feasibility,
        evidence=evidence,
        confidence="high" if evidence == "measured" else "low",
        bottleneck=bottleneck,
        margins={r.code: round(r.margin, 3) for r in results},
        assumed_inputs=assumed,
        findings=findings,
        metrics={r.code: r.numbers for r in results},
    )
