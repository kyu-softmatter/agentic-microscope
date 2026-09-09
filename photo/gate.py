"""The photo-perturbation lens's committee verdict (lens 5).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema, as compute.gate, detection.gate and sample.gate do.

Phase 0 here is unusually load-bearing. Every gate in this lens needs
**irradiance** at the sample plane, and as of 2026-09-09 the instrument has it:
power for nine lines at three objectives, and an illuminated area for all three
engines, which all put about the camera field on the sample
(kb/calibrations/illumination-power.yaml). So G20, G21 and G22 compute.

**G10 does not, and is now the only thing this lens blocks on.** It needs
`bleach_photons`, which is per dye, empty for every dye, and not something a
power meter supplies. docs/04 §9 marks it BLOCKED for exactly that.

Two limits on the rest. The area holds **at 20x only** -- it rests on the one
row of data/pixel_size.yaml carrying `evidence: measured`, and every other
objective's pixel size is `nominal`. And a percent setting in the metadata is
still not a physical quantity: what transfers is the mW, or the W/cm^2.

Two axes, and the difference matters. A missing *number* blocks (Phase 0). A
missing *answer* -- has anyone checked whether this sample responds to the
light, does k_ex carry the real spectral overlap -- lands in
``assumed_inputs``, which costs the verdict ``advances`` while still letting it
say everything else it can. Neither one is ever substituted with a guess.
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
                action="Supply power_mw_at_sample and illuminated_area_um2 for "
                "this evaluation. Both exist on this instrument as of "
                "2026-09-09 and neither is filled in automatically: power for "
                "nine lines at three objectives in data/light_sources.yaml, and "
                "603654 um^2 at 20x for all three engines, which put about the "
                "camera field on the sample. Together they give 1.1-7.7 W/cm^2 "
                "at 100 % level -- see kb/calibrations/illumination-power.yaml, "
                "which also carries the per-line level linearity, since below "
                "about 30 % the percent setting is not proportional to power. "
                "The area is 20x only; other objectives rest on a `nominal` "
                "pixel size.",
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

    if setup.photoresponsive is True and setup.light_driving_threshold_w_cm2 is None:
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
    """What this verdict had to stand in for -- each entry costs it `advances`.

    Unconfirmed photoresponsiveness belongs here rather than in Phase 0. It is
    not a missing number, it is a missing answer, and the lens can still say
    everything else it has to say; what it must not do is let the silence read
    as a clearance (docs/06 D2).
    """
    out: list[str] = []
    if setup.quantum_yield is None:
        out.append("quantum yield (absent, so emitted photons cannot be scaled)")
    if setup.frame_interval_ms is None:
        out.append("frame interval (duty cycle not computed)")
    if setup.photoresponsive is None:
        out.append(
            "sample photoresponsiveness (never asked, so light-driving is "
            "unconfirmed rather than cleared)"
        )
    if setup.excitation_coupling_assumed:
        out.append(
            "spectral overlap coupling (no channel supplied, so k_ex assumes "
            "the line sits on the absorption peak -- an upper bound, which "
            "makes G10 and G20 stricter than the instrument warrants)"
        )
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
                action="Supply the items listed above and re-run. Each one on "
                "its own is enough to keep this lens from advancing.",
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
