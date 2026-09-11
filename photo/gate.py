"""The photo-perturbation lens's committee verdict (lens 5).

Mirrors optics.gate's Phase 0 / Phase 1 / Phase 2 structure and full
``Verdict`` schema, as compute.gate, detection.gate and sample.gate do.

Phase 0 here is unusually load-bearing. Every gate in this lens needs
**irradiance** at the sample plane, and as of 2026-09-09 the instrument has it:
power for nine lines at three objectives, and an illuminated area for all three
engines, which all put about the camera field on the sample
(kb/calibrations/illumination-power.yaml). So G21 and G22 compute.

TWO GATES WERE REMOVED FROM THIS LENS ON 2026-09-09 and neither number is
reused. G20 (saturation / triplet shelving) needed BOTH ext_coeff and
lifetime_ns, and both are empty for the proprietary bead colourants this
instrument images --
kb/decisions/2026-09-09-g20-saturation-removed.md.

G10 (photobleaching) was removed the same day -- it had never returned
anything but BLOCKED, its one lever the operator could not use was the dye, and
the intensity decay it guarded is measurable in the acquisition rather than
predictable from a dye constant. kb/decisions/2026-09-09-g10-photobleaching-removed.md.

Two limits on what remains. The area holds **at 20x only** -- it rests on the one
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
    #: REPORT | BLOCKED. This is a reporting section, not a judging lens
    #: (KH, 2026-09-10), so PASS / PASS_WITH_CHANGES / FAIL are gone: there is
    #: nothing here that can pass or fail. BLOCKED survives because a report
    #: still cannot be written without its inputs.
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

        A judging lens advances or refuses to. This section does neither: it
        cannot block a proposal and it cannot bless one, so answering ``False``
        would read as a refusal and answering ``True`` would claim an
        endorsement it has no gate to base on. Lens 6's L6.1 no longer looks for
        this section at all -- it left ``STANDING_LENSES`` on 2026-09-10.
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
                "scales with both.",
                action="Supply exposure_ms and n_frames.",
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
    if setup.frame_interval_ms is None:
        out.append("frame interval (duty cycle not computed)")
    if setup.photoresponsive is None:
        out.append(
            "sample photoresponsiveness (never asked, so light-driving is "
            "unconfirmed rather than cleared)"
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

    # ---- Phase 2 -- collate ----------------------------------------------
    # Nothing here is gradeable, by construction: every check is INFO since
    # 2026-09-10. So there is no worst margin, no bottleneck and no
    # feasibility -- and saying "UNKNOWN" would be wrong in the way that
    # matters, because UNKNOWN is what an ungraded JUDGEMENT looks like. This
    # is not an ungraded judgement; it is a report.
    gradeable = [r for r in results if r.kind in (HARD, SOFT, BIAS)]
    assert not gradeable, (
        "photo/ is a reporting section: every check must be INFO. "
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
                "This verdict used assumed values for: " + ", ".join(assumed) + ".",
                action="Supply the items listed above and re-run. Each one on "
                "its own is enough to keep this lens from advancing.",
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
