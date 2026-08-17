"""The optical lens: committee member #1.

Structure (see docs/08 §0):

    Phase 0   input availability  -> BLOCKED if a required fact is missing
    Phase 1   every check runs, independently, and returns a margin
    Phase 2   aggregate: hard veto, feasibility grade, bottleneck, ablation

No early return between checks. The experimenter walks to the microscope once,
not once per discovered problem — so the whole picture has to come out in one
evaluation.

Design rules:

* **A missing input is not a pass.** No dye spectrum, no NA, no filter
  passband -> ``BLOCKED``. Silence about an unknown is how a recommender
  becomes dangerous.
* **Approximated spectra downgrade evidence, never status.** ``advances``
  requires both a good verdict and measured inputs.
* **Every failure carries an action.** A verdict the user cannot act on is a
  complaint, not a review.
* **Difficulty, not a boolean.** Experiments at the edge of the instrument are
  real. Say how hard, and what would make it easier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import (
    BIAS,
    CHECKS,
    GRADE_NOTES,
    HARD,
    INFO,
    LIMITS,
    SOFT,
    CheckResult,
    available_facts,
    grade,
    meets_grade,
)
from .components import filters, find_filter
from .path import Ablation, Channel, ablate

LENS = "optics"

#: Back-compat alias; thresholds now live in optics.checks.LIMITS
THRESHOLDS = LIMITS


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
    """What the physics says, how sure we are, and how hard it will be.

    Three axes that must not be collapsed:

    ``status``       is the configuration sound?
    ``evidence``     were the inputs measured or assumed?
    ``feasibility``  how much headroom is there?

    ``advances`` is the committee's criterion and requires the first two.
    ``feasibility`` is advice, not a veto: an experiment graded ``HARD`` is
    still an experiment worth doing if you know it is hard.
    """

    status: str  # PASS | PASS_WITH_CHANGES | FAIL | BLOCKED
    feasibility: str = "UNKNOWN"  # ROUTINE .. INFEASIBLE
    evidence: str = "assumed"  # measured | assumed
    confidence: str = "low"
    bottleneck: str | None = None  # code of the worst gradeable check
    margins: dict[str, float] = field(default_factory=dict)
    assumed_inputs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ablations: list[Ablation] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Physics is satisfactory. Not sufficient to proceed."""
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

    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fail"]

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
            "ablations": [asdict(a) for a in self.ablations],
            "suggestions": self.suggestions,
        }


# --------------------------------------------------------------------------
# Phase 0 — what can we not see?
# --------------------------------------------------------------------------


def _missing_inputs(channel: Channel) -> list[Finding]:
    out: list[Finding] = []

    if not channel.objective.na or channel.objective.na <= 0:
        out.append(
            Finding(
                "fail",
                "missing.na",
                f"Objective '{channel.objective.label}' has no NA. Collection "
                "efficiency, resolution and depth of field are all undefined "
                "without it.",
                action="Read the NA off the objective barrel and add it to the "
                "scope profile. Micro-Manager never records NA.",
            )
        )

    if channel.source is None:
        out.append(
            Finding(
                "fail",
                "missing.source",
                "No excitation line assigned to this channel.",
                action="Pick a line from data/light_sources.yaml.",
            )
        )

    det = channel.detector
    if det.read_noise_e is None or det.full_well_e is None or det.pixel_um is None:
        out.append(
            Finding(
                "fail",
                "missing.detector",
                f"Detector '{det.label}' is missing pixel pitch, read noise or "
                "full well. Sampling, SNR and saturation are uncomputable.",
                action=f"Add '{det.label}' to data/detectors.yaml from its "
                "datasheet. Do not substitute a similar camera.",
            )
        )

    reported: set[str] = set()
    for el in channel.excitation_chain() + channel.emission_chain():
        if el.kind == "unknown" and el.label not in reported:
            reported.add(el.label)
            out.append(
                Finding(
                    "fail",
                    "missing.filter_spec",
                    f"Element '{el.label}' has no passband on record, so its "
                    "effect on signal, blocking and crosstalk is unknown.",
                    action=f"Add '{el.label}' to data/filters.yaml with its part "
                    "number and passband, or load the vendor transmission curve "
                    "into data/spectra/.",
                )
            )

    return out


def _assumed_inputs(channel: Channel) -> list[str]:
    out: list[str] = []
    for el in channel.excitation_chain() + channel.emission_chain():
        if not el.verified:
            out.append(el.label)
    if not channel.dye.verified:
        out.append(f"{channel.dye.name} spectra")
    if not channel.objective.verified_na:
        out.append(f"{channel.objective.label} NA")
    if channel.objective.transmission is None:
        out.append(f"{channel.objective.label} transmission")
    if not channel.detector.qe.measured:
        out.append(f"{channel.detector.label} QE curve")
    if channel.source is not None and not channel.source.calibrated:
        out.append(f"{channel.source.name} power at sample")
    return sorted(set(out))


# --------------------------------------------------------------------------
# Filter suggestions
# --------------------------------------------------------------------------


def _suggest_filters(channel: Channel) -> list[str]:
    """Rank registry emission filters by how much of this dye they would pass."""
    suggestions: list[str] = []
    scored: list[tuple[float, str]] = []
    current = channel.spectral_collection()
    in_path = {el.label for el in channel.excitation_chain() + channel.emission_chain()}

    for name, spec in filters().items():
        if spec.get("kind") not in {"bandpass", "multiband", "longpass"}:
            continue
        if spec.get("position") not in {"emission", None}:
            continue
        if name in in_path:
            continue
        candidate = find_filter(name, position="emission")
        if candidate is None:
            continue
        trial = Channel(
            name=channel.name,
            dye=channel.dye,
            objective=channel.objective,
            detector=channel.detector,
            source=channel.source,
            excitation=list(channel.excitation),
            dichroic=channel.dichroic,
            emission=[candidate],
            port_fraction=channel.port_fraction,
        )
        if trial.excitation_blocking_od() < LIMITS["blocking_od"]:
            continue
        scored.append((trial.spectral_collection(), name))

    scored.sort(reverse=True)
    for value, name in scored[:3]:
        if value > current * 1.10:
            suggestions.append(
                f"Emission filter '{name}' would raise collection from "
                f"{current * 100:.0f}% to {value * 100:.0f}% "
                f"(x{value / current:.2f})."
            )
    return suggestions


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def evaluate(
    channel: Channel,
    others: list[Channel] | None = None,
    *,
    suggest_filters: bool = True,
) -> Verdict:
    others = others or []
    assumed = _assumed_inputs(channel)
    evidence = "measured" if not assumed else "assumed"

    # ---- Phase 0 --------------------------------------------------------
    blocking_findings = _missing_inputs(channel)
    facts = available_facts(channel)
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
            suggestions=[
                "Fill the missing hardware facts before any optical verdict is "
                "meaningful. See docs/02 §10 for the outstanding list."
            ],
        )

    # ---- Phase 1 — every check runs -------------------------------------
    results: list[CheckResult] = [c.run(channel, others) for c in CHECKS]

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

    ablations = ablate(
        channel,
        others,
        min_blocking_od=LIMITS["blocking_od"],
        max_crosstalk=LIMITS["crosstalk"],
        gain_threshold=1.10,
        spectra_measured=(evidence == "measured"),
    )
    for ab in ablations:
        if ab.verdict == "remove":
            findings.append(
                Finding(
                    "warn",
                    "element.removable",
                    f"'{ab.element}' ({ab.kind}) is costing signal: {ab.reason}",
                    action=f"Take '{ab.element}' out of the path and re-check.",
                    numbers={
                        "signal_gain": ab.signal_gain,
                        "blocking_od_after": ab.blocking_od_after,
                    },
                    kind=INFO,
                )
            )
        elif ab.verdict == "candidate":
            findings.append(
                Finding(
                    "info",
                    "element.removal_candidate",
                    f"'{ab.element}' ({ab.kind}) may be removable: {ab.reason}",
                    action=f"Load the measured curve for '{ab.element}' and re-run "
                    "before changing anything on the bench.",
                    numbers={"signal_gain": ab.signal_gain},
                    kind=INFO,
                )
            )

    if assumed:
        findings.append(
            Finding(
                "info",
                "evidence.assumed",
                "This verdict used assumed values for: "
                + ", ".join(assumed)
                + ". Blocking and crosstalk are decided in the far wings of a "
                "curve, which is exactly where a catalogue approximation is "
                "worthless. Triage only — it does not advance the proposal.",
                action="Load vendor transmission curves and dye spectra into "
                "data/spectra/, read NA off the barrel, and measure the "
                "illumination power at the sample. Then re-run.",
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
        metrics={
            "excitation_efficiency": channel.excitation_efficiency(),
            "source_delivery": channel.source_delivery(),
            "spectral_collection": channel.spectral_collection(),
            "geometric_collection": channel.objective.collection_efficiency(),
            "total_collection": channel.total_collection(),
            "blocking_od": channel.excitation_blocking_od(),
            "stokes_headroom_nm": channel.stokes_headroom_nm(),
            "resolution_nm": channel.objective.resolution_nm(
                channel.dye.emission.peak_nm()
            ),
            "depth_of_field_nm": channel.objective.depth_of_field_nm(
                channel.dye.emission.peak_nm()
            ),
        },
        ablations=ablations,
        suggestions=_suggest_filters(channel) if suggest_filters else [],
    )
