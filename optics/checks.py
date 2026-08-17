"""Individual optical checks.

Each check is independent and returns a **margin** — how much headroom there is,
as ``achieved / required``. A margin of 1.0 means exactly at the limit; 0.5
means half of what is needed; 3.0 means comfortable.

Margins, not booleans, because three things downstream need them:

* the feasibility grade (`ROUTINE` … `INFEASIBLE`) is the worst margin
* the improvement analysis needs to know *which* gate is the bottleneck and by
  how much
* an experiment at the edge of what the instrument can do is a real and valid
  situation. "Hard, and here is why, and here is what would fix it" is a far
  more useful answer than "FAIL"

Checks never early-return out of the suite. Every check runs on every
evaluation so the whole picture is available at once — the experimenter walks
to the microscope once, not once per discovered problem.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from .spectra import GRID

if TYPE_CHECKING:
    from .path import Channel


# --------------------------------------------------------------------------
# Kinds — what it means when this check fails. See docs/05 §2.
# --------------------------------------------------------------------------
#: does not work at all; no data worth taking
HARD = "hard"
#: produces data that looks fine but is systematically wrong
BIAS = "bias"
#: degrades quality; the experiment is merely harder
SOFT = "soft"
#: reported but does not participate in grading
INFO = "info"


#: Margins are clamped here. Beyond ~10x the limit the exact value is
#: meaningless — and some ratios (crosstalk with parametric spectra) blow up to
#: 1e28, which would swamp any display and skew any aggregate.
MAX_MARGIN = 10.0


@dataclass
class CheckResult:
    code: str
    kind: str
    margin: float
    severity: str  # ok | info | warn | fail
    message: str
    action: str | None = None
    numbers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.margin):
            self.margin = MAX_MARGIN
        self.margin = max(0.0, min(float(self.margin), MAX_MARGIN))

    @property
    def passed(self) -> bool:
        return self.margin >= 1.0


@dataclass
class Check:
    code: str
    kind: str
    #: which facts must exist before this check means anything
    requires: tuple[str, ...]
    run: Callable[["Channel", list["Channel"]], CheckResult]


# --------------------------------------------------------------------------
# Thresholds, in one place so they can be argued with.
# --------------------------------------------------------------------------
LIMITS = {
    "blocking_od": 5.0,
    #: approximated spectra have an idealized flat blocking floor, so demand
    #: more margin before believing a blocking number
    "blocking_od_assumed": 7.0,
    "crosstalk": 0.05,
    "spectral_collection": 0.15,
    "filter_efficiency": 0.50,
    "excitation_ratio": 0.20,
    "stokes_headroom_nm": 5.0,
}


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(channel: "Channel") -> set[str]:
    """Which inputs this channel actually supplies.

    A check whose ``requires`` is not satisfied is not run and not graded —
    it is reported as blocking, because a computed number would be fiction.
    """
    facts: set[str] = set()
    obj = channel.objective

    if obj.na and obj.na > 0:
        facts.add("objective.na")
    if obj.magnification and obj.magnification > 0:
        facts.add("objective.mag")
    if channel.source is not None:
        facts.add("source")
    if channel.detector.qe is not None:
        facts.add("detector.qe")
    if (
        channel.detector.pixel_um
        and channel.detector.read_noise_e
        and channel.detector.full_well_e
    ):
        facts.add("detector.specs")
    if channel.dye.absorption is not None:
        facts.add("dye.absorption")
    if channel.dye.emission is not None:
        facts.add("dye.emission")

    known = [
        el
        for el in channel.excitation_chain() + channel.emission_chain()
        if el.kind != "unknown"
    ]
    unknown = [
        el
        for el in channel.excitation_chain() + channel.emission_chain()
        if el.kind == "unknown"
    ]
    if not unknown:
        facts.add("path.complete")
    if known or not unknown:
        facts.add("path.partial")

    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_excitation(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """Does this line actually excite this dye through this path?"""
    from .path import Channel as _Channel

    ex_eff = channel.excitation_efficiency()
    ideal = _Channel(
        name=channel.name,
        dye=channel.dye,
        objective=channel.objective,
        detector=channel.detector,
        source=channel.source,
    ).excitation_efficiency()
    ratio = ex_eff / ideal if ideal > 0 else 0.0
    margin = ratio / LIMITS["excitation_ratio"]

    line_nm = channel.source.center_nm if channel.source else float("nan")
    abs_nm = channel.dye.absorption.peak_nm()

    if ex_eff <= 1e-9:
        return CheckResult(
            "excitation.none",
            HARD,
            0.0,
            "fail",
            f"Line '{channel.source.name}' ({line_nm:.0f} nm) does not excite "
            f"{channel.dye.name} at all (absorption peak {abs_nm:.0f} nm).",
            action="Choose a line nearer the absorption peak, or check that the "
            "excitation filter and dichroic reflection band match the source.",
            numbers={"line_nm": line_nm, "abs_peak_nm": abs_nm, "ex_eff": ex_eff},
        )

    if margin < 1.0:
        return CheckResult(
            "excitation.blocked",
            HARD,
            margin,
            "fail",
            f"The excitation path delivers only {ratio * 100:.0f}% of what this "
            f"line could couple into {channel.dye.name}.",
            action="Check the excitation filter and the dichroic reflection band "
            "against the source line.",
            numbers={"ratio": ratio, "delivery": channel.source_delivery()},
        )

    severity = "warn" if ratio < 0.5 else "ok"
    return CheckResult(
        "excitation.coupling",
        HARD,
        margin,
        severity,
        f"Excitation path couples {ratio * 100:.0f}% of the ideal into "
        f"{channel.dye.name}.",
        action=(
            "A wider excitation filter or a better-matched line would help if "
            "photon budget is tight."
            if severity == "warn"
            else None
        ),
        numbers={"ratio": ratio},
    )


def check_blocking(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """Is backscattered excitation kept out of the detector?"""
    od = channel.excitation_blocking_od()
    assumed = not _path_measured(channel)
    required = LIMITS["blocking_od_assumed" if assumed else "blocking_od"]

    if math.isinf(od):
        margin = 10.0
    else:
        margin = od / required

    if margin >= 1.0:
        return _ok(
            "blocking",
            HARD,
            margin,
            f"Detection path attenuates the excitation by {od:.1f} OD "
            f"(need {required:.0f}).",
            blocking_od=od,
            required_od=required,
        )

    return CheckResult(
        "blocking.insufficient",
        HARD,
        margin,
        "fail",
        f"The detection path attenuates the excitation by only {od:.1f} OD "
        f"(need {required:.0f}). Backscattered excitation will dominate; no "
        "exposure or gain setting recovers from this.",
        action=(
            f"Add an emission filter with adequate blocking at "
            f"{channel.source.center_nm:.0f} nm."
            if channel.source
            else "Add a blocking emission filter."
        ),
        numbers={"blocking_od": od, "required_od": required, "assumed": assumed},
    )


def check_collection(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """How much of the dye's emission survives to become electrons?"""
    coll = channel.spectral_collection()
    margin = coll / LIMITS["spectral_collection"]

    if margin >= 1.0:
        return _ok(
            "collection",
            SOFT,
            margin,
            f"{coll * 100:.0f}% of emission reaches the detector.",
            spectral_collection=coll,
        )

    return CheckResult(
        "collection.low",
        SOFT,
        margin,
        "fail",
        f"Only {coll * 100:.0f}% of {channel.dye.name}'s emission survives the "
        "detection path. The exposure this forces makes the experiment "
        "impractical.",
        action="Widen or re-centre the emission filter; check the dichroic edge "
        "is not cutting into the emission band.",
        numbers={"spectral_collection": coll},
    )


def check_filter_centering(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """Of the emission the detector *could* see, how much do the filters pass?

    Separates the filters' contribution from the camera's QE, which is what
    tells you whether a different filter would help.

    Deliberately ``INFO`` rather than ``SOFT``: this measures the same physical
    quantity as :func:`check_collection`, just decomposed. Grading both would
    double-count one weakness, and a filter passing 49% instead of a nominal
    50% would drag the whole experiment's feasibility down for no physical
    reason. ``collection`` owns the grade; this owns the explanation.
    """
    qe = channel.detector.qe
    em = channel.dye.emission.area_normalized()
    ceiling = float(np.trapezoid(em.values * qe.values, GRID))
    achieved = channel.spectral_collection()
    efficiency = achieved / ceiling if ceiling > 0 else 0.0
    margin = efficiency / LIMITS["filter_efficiency"]

    band = channel.emission_transmission().support(0.5)
    peak = channel.dye.emission.peak_nm()
    clipped = bool(band and band[0] > peak)

    if clipped:
        return CheckResult(
            "emission.peak_clipped",
            INFO,
            min(margin, 0.9),
            "warn",
            f"The detection band starts at {band[0]:.0f} nm, past "
            f"{channel.dye.name}'s emission peak ({peak:.0f} nm). The brightest "
            "part of the emission is being thrown away.",
            action="Move to an emission filter whose band starts below the peak, "
            "or a long-pass if crosstalk allows.",
            numbers={
                "band_start_nm": band[0],
                "em_peak_nm": peak,
                "filter_efficiency": efficiency,
            },
        )

    severity = "ok" if margin >= 1.0 else "warn"
    return CheckResult(
        "emission.centering",
        INFO,
        margin,
        severity,
        f"Filters pass {efficiency * 100:.0f}% of the QE-weighted emission "
        f"(ceiling {ceiling * 100:.0f}% set by the camera).",
        action=(
            "A wider or better-centred emission filter would recover signal."
            if severity == "warn"
            else None
        ),
        numbers={"filter_efficiency": efficiency, "qe_ceiling": ceiling},
    )


def check_stokes(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """Are the excitation and detection bands actually separated?"""
    head = channel.stokes_headroom_nm()
    if math.isnan(head):
        return _ok("spectral.separation", HARD, 1.0, "band edges undetermined")

    required = LIMITS["stokes_headroom_nm"]
    margin = max(head, 0.0) / required

    if margin >= 1.0:
        return _ok(
            "spectral.separation",
            HARD,
            margin,
            f"Excitation and detection bands are {head:.0f} nm apart.",
            stokes_headroom_nm=head,
        )

    return CheckResult(
        "spectral.overlap",
        HARD,
        margin,
        "fail",
        f"Excitation and detection bands are only {head:.0f} nm apart "
        "(overlapping if negative). This is a dye/filter-set mismatch, not "
        "something a setting can fix.",
        action="Use a dye with a larger Stokes shift, or a narrower excitation "
        "band with a long-pass emission filter.",
        numbers={
            "stokes_headroom_nm": head,
            "dye_stokes_nm": channel.dye.stokes_shift_nm,
        },
    )


def check_crosstalk(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """How much of a neighbouring channel leaks in here?

    Classified ``bias``: leaked signal is indistinguishable from real signal, so
    the data looks fine and the conclusion is wrong.
    """
    if not others:
        return _ok("crosstalk", BIAS, 10.0, "single channel; no crosstalk possible")

    worst, source = 0.0, ""
    for other in others:
        xt = channel.crosstalk_from(other)
        if xt > worst:
            worst, source = xt, other.name

    limit = LIMITS["crosstalk"]
    # Lower is better, so the margin inverts.
    margin = (limit / worst) if worst > 0 else 10.0

    if margin >= 1.0:
        return _ok(
            "crosstalk",
            BIAS,
            margin,
            f"Worst crosstalk {worst * 100:.1f}% (limit {limit * 100:.0f}%).",
            crosstalk=worst,
            source=source,
        )

    return CheckResult(
        "crosstalk",
        BIAS,
        margin,
        "fail",
        f"{worst * 100:.1f}% of {source}'s signal leaks into channel "
        f"'{channel.name}'. Leaked signal is indistinguishable from real signal.",
        action="Narrow the emission filter, image the channels sequentially "
        "rather than simultaneously, or measure a mixing matrix and unmix.",
        numbers={"crosstalk": worst, "from": source, "limit": limit},
    )


def check_port(channel: "Channel", others: list["Channel"]) -> CheckResult:
    """Is the collected light actually going to this camera?"""
    f = channel.port_fraction
    if f >= 0.99:
        return _ok("path.port", INFO, 1.0, "Full light path to the camera.", port=f)
    return CheckResult(
        "path.port_split",
        INFO,
        f,
        "warn",
        f"Only {f * 100:.0f}% of collected light reaches this camera port.",
        action="Switch to the 100% camera position unless the other port is in "
        "use (tweezers, DMD).",
        numbers={"port_fraction": f},
    )


CHECKS: list[Check] = [
    Check("excitation", HARD, ("source", "dye.absorption", "path.partial"), check_excitation),
    Check("blocking", HARD, ("source", "detector.qe", "path.complete"), check_blocking),
    Check("stokes", HARD, ("source", "dye.emission", "path.partial"), check_stokes),
    Check("collection", SOFT, ("dye.emission", "detector.qe", "path.complete"), check_collection),
    Check("centering", INFO, ("dye.emission", "detector.qe", "path.complete"), check_filter_centering),
    Check("crosstalk", BIAS, ("dye.emission", "detector.qe", "path.complete"), check_crosstalk),
    Check("port", INFO, (), check_port),
]


def _path_measured(channel: "Channel") -> bool:
    elements = channel.excitation_chain() + channel.emission_chain()
    return all(el.verified for el in elements) and channel.dye.verified


# --------------------------------------------------------------------------
# Feasibility grading
# --------------------------------------------------------------------------

GRADES: list[tuple[float, str]] = [
    (3.0, "ROUTINE"),
    (1.5, "COMFORTABLE"),
    (1.0, "TIGHT"),
    (0.5, "HARD"),
    (0.2, "MARGINAL"),
    (0.0, "INFEASIBLE"),
]

GRADE_NOTES = {
    "ROUTINE": "Comfortable headroom. If it fails, the settings are not to blame.",
    "COMFORTABLE": "Normal range.",
    "TIGHT": "No headroom. Sample preparation quality decides the outcome.",
    "HARD": "Operating at the limit. May proceed, but low success rate and poor reproducibility.",
    "MARGINAL": "Data comes out, but interpret with great care.",
    "INFEASIBLE": "Impossible without improvement.",
}


def grade(margin: float) -> str:
    for threshold, name in GRADES:
        if margin >= threshold:
            return name
    return "INFEASIBLE"


#: Grades in ascending order of quality, derived from GRADES so the two cannot
#: drift apart.
GRADE_ORDER: tuple[str, ...] = tuple(name for _, name in reversed(GRADES))


def meets_grade(feasibility: str, minimum: str = "TIGHT") -> bool:
    """Is this feasibility at least ``minimum``?

    docs/05-consensus-gate.md's Verdict schema requires ``feasibility >= TIGHT``
    for a verdict to advance. ``UNKNOWN`` -- and anything unrecognised -- does
    not: an ungraded verdict has not earned the right to move on.
    """
    if feasibility not in GRADE_ORDER or minimum not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(feasibility) >= GRADE_ORDER.index(minimum)
