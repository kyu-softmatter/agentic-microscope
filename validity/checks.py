"""Individual measurement-validity checks -- G23 (bias ledger), G24 (pixel
calibration), G25 (photometric calibration), G27 (committee coverage).

docs/05-consensus-gate.md "Lens 6"; docs/06-pitfalls.md A1.

G23-G27 were new numbers (G1-G22 were taken by lenses 1/2/3/4/5/7).

TWO CHECKS LEFT THIS LENS ON 2026-09-11 (KH) AND NEITHER NUMBER IS REUSED.

**G11 (statistical power)** was the only quantity this lens computed rather
than reviewed, and the quantity it computed did not describe this instrument's
measurements. `1/sqrt(N_p x N_f)` counts independent samples, and
`validity/power.py` says so in its own docstring -- "in a crowded or
hydrodynamically coupled suspension they are not, and this is optimistic". A
single trapped bead is the worse case, because consecutive FRAMES are
correlated too: at 520 fps with tau = gamma/kappa = 12.1 ms there are 6.3
frames per relaxation time, so a 60 s movie of one bead is ~2,500 independent
samples and not 31,200. The gate reported 0.566% where ~2.0% is defensible --
**3.5x optimistic, and a margin of 78x where ~6x is real.** And the real
precision of a Stokes-drag calibration comes from the number of velocity steps,
which is not N_p x N_f at all. The arithmetic survives in `validity/power.py`
and `python -m validity.cli power`, which is where a floor belongs: something
you consult, not something that certifies.

**G26 (post-processing)** was re-charging a bias that is already caught where
it does damage. It gated on the self-declared `despeckle_enabled` boolean,
which nobody verifies. `detection/recommend.py` refuses on the same fact and
puts it more sharply -- "despeckle on -> the ADU->electron conversion is
invalid, full stop" -- and it refuses at the point where despeckle actually
destroys something computable: deriving a photon budget from a frame it was
applied to. A committee-level hard gate on an unverified boolean added no
information and could not see the camera.
kb/decisions/2026-09-11-g11-and-g26-removed.md

What is left is four checks that all **read other lenses' verdicts or
declarations** rather than hardware facts. That is now the whole of this lens's
job: deciding whether the intended physical quantity survives every bias the
committee found. It computes nothing.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .setup import UNCORRECTABLE

if TYPE_CHECKING:
    from .setup import ValiditySetup

HARD = "hard"
BIAS = "bias"
SOFT = "soft"
INFO = "info"

MAX_MARGIN = 10.0

#: EMPTY since 2026-09-11, when G26 went. `linearity_breaking_filters`
#: (`("despeckle",)`) was this lens's only numeric constant, and with the check
#: gone there is nothing here comparing against a threshold of its own -- every
#: remaining check compares a declaration or another lens's verdict. An entry
#: appearing here again means this lens has started computing rather than
#: reviewing, which is a decision and not a refactor.
LIMITS: dict = {}


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
    requires: tuple[str, ...]
    run: Callable[["ValiditySetup"], CheckResult]


def _ok(code, kind, margin, message, **numbers) -> CheckResult:
    """A pass that rests on a FACT. Severity "ok", so `gate.py` drops it.

    ⚠ READ THE RULE BEFORE ADDING A CALL. Every `gate.py` in this repository
    drops `severity == "ok"` from `findings`, so anything returned through here
    exists only in `metrics`, which no CLI prints. That is right for a pass
    whose basis the reader can reconstruct, and wrong for a pass that made a
    choice. The line, set 2026-09-11 (KH, option (a) of three):

        **A pass that rests on "this does not apply to you" is a DECISION and
        must be visible -- return severity "info" directly.
        A pass that rests on "you have it" is a FACT and may use `_ok`.**

    Four branches in this lens are decisions and do not come through here:
    G23's out-of-scope ruling and its declaration-accepted ruling, and G24's
    and G25's "not on the critical path" rulings. Each of those turned the
    check OFF on the strength of a lookup table -- `BIAS_SCOPE`,
    `CORRECTIONS`, `QUANTITY_REQUIREMENTS` -- and if the table is wrong, a
    silent pass is exactly how nobody finds out.

    This was the fifth and sixth instance of one defect in a single review
    (lens 5's G20, lens 4's wall drag, lens 7's `_ok`, lens 8's `_ok` and
    `convening`). The reason it keeps recurring is the name: `_ok` reads as
    "not graded" and behaves as "not visible".
    kb/decisions/2026-09-11-a-pass-that-decides-must-be-visible.md
    """
    return CheckResult(code, kind, margin, "ok", message, None, numbers)


# --------------------------------------------------------------------------
# Input availability (Phase 0)
# --------------------------------------------------------------------------


def available_facts(setup: "ValiditySetup") -> set[str]:
    facts: set[str] = set()
    if setup.upstream:
        facts.add("upstream")
    if setup.intended_quantity is not None:
        facts.add("intended_quantity")
    return facts


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_bias_ledger(setup: "ValiditySetup") -> CheckResult:
    """G23: is every bias the committee found either absent or corrected?

    This is what docs/05 means by giving lens 6 "final review of every bias
    gate". It does not recompute any of them -- it decides whether the intended
    quantity survives them. The margin it reports is the worst *uncorrected*
    upstream bias margin, so the committee's worst unhandled problem stays
    visible instead of being averaged away.

    HARD, not BIAS, deliberately. The individual upstream gates are the bias
    gates; this is the meta-check that they were all dealt with, and its failure
    means the intended physical quantity does not survive the setting. That is a
    veto on this lens's entire purpose, not one more correctable bias.

    Two things it does beyond counting:

    - **It scopes.** Only the biases that damage this quantity are judged
      (`BIAS_SCOPE`), so a session can report a biased MSD and a sound intensity
      profile instead of one collapsed status. Out-of-scope biases are named in
      the message rather than dropped -- they still stand against the
      quantities they do damage.
    - **It checks the declaration.** A code in `UNCORRECTABLE` is not cleared by
      declaring it; there is no such correction to have applied. A code in
      neither registry is accepted but costs the verdict its `measured` grade,
      because nobody has audited it.
    - **It does not let an ungraded bias rescue itself.** An uncorrected bias
      whose upstream margin is >= 1.0 drops this gate to 0.0, because a
      passing margin on an uncorrected bias means the origin lens declined to
      grade it rather than that the bias is small. See the comment at the
      margin computation. `unevaluated != cleared`, CLAUDE.md §3.
    """
    all_bias = setup.bias_findings()
    applicable = setup.applicable_bias_findings()
    out_of_scope = setup.out_of_scope_bias_findings()
    uncorrected = setup.uncorrected_bias_findings()
    false_claims = setup.falsely_corrected_bias_findings()
    unverified = setup.unverified_corrections()

    numbers = {
        "bias_findings": len(all_bias),
        "applicable": len(applicable),
        "out_of_scope_codes": [f.code for f in out_of_scope],
        "corrected": len(applicable) - len(uncorrected),
        "uncorrected": len(uncorrected),
        "uncorrected_codes": [f.code for f in uncorrected],
        "false_correction_codes": [f.code for f in false_claims],
        "unverified_correction_codes": unverified,
        "corrections_declared": sorted(setup.corrections_applied),
        #: Present in every branch so the metrics shape does not depend on
        #: which one ran. Filled in below when there is anything uncorrected.
        "worst_uncorrected_margin": None,
        "ungraded_uncorrected_codes": [],
    }

    scoped_note = ""
    if out_of_scope:
        scoped_note = (
            f" {len(out_of_scope)} further bias "
            + ("finding does" if len(out_of_scope) == 1 else "findings do")
            + f" not touch '{setup.intended_quantity}' "
            f"({', '.join(f.code for f in out_of_scope)})."
        )

    if not all_bias:
        return _ok(
            "validity.bias_ledger",
            HARD,
            MAX_MARGIN,
            "No upstream lens reported a bias finding, so there is nothing "
            "biasing the intended quantity that the committee knows about.",
            **numbers,
        )

    if not applicable:
        # severity "info", NOT "ok" (KH, 2026-09-11). This branch made a
        # DECISION -- it ruled every upstream bias out of scope from
        # `BIAS_SCOPE` -- and it carries an instruction the reader has to act
        # on: the biases still stand against the quantities they DO damage. As
        # `_ok` both vanished.
        return CheckResult(
            "validity.bias_ledger",
            HARD,
            MAX_MARGIN,
            "info",
            f"None of the {len(all_bias)} upstream bias findings damage "
            f"'{setup.intended_quantity}': "
            f"{', '.join(f.code for f in out_of_scope)}. They still stand "
            "against the quantities they do damage -- judge those separately.",
            action="Scoped out by validity.setup.BIAS_SCOPE, so this pass is "
            "only as good as that table. A bias absent from it damages every "
            "quantity by default; one listed with the wrong scope disappears "
            "silently for the quantities it is missing.",
            numbers=numbers,
        )

    if not uncorrected:
        msg = (
            f"All {len(applicable)} bias findings that bear on "
            f"'{setup.intended_quantity}' have a correction that exists and was "
            "declared applied." + scoped_note
        )
        if unverified:
            msg += (
                f" No correction is registered for {', '.join(unverified)}, "
                "though, so that clearance is unaudited and the verdict cannot "
                "be `measured`."
            )
        # severity "info", NOT "ok" (KH, 2026-09-11). This is the one place
        # the ledger can be talked out of a FAIL, and it does it on the
        # strength of `corrections_applied` -- a declaration. That is a
        # decision, and the `unverified` clause above is a live warning that
        # used to sit inside a branch nothing printed.
        return CheckResult(
            "validity.bias_ledger",
            HARD,
            MAX_MARGIN,
            "info",
            msg,
            action="Cleared by DECLARATION, not by anything this gate can "
            "check. Each code above was matched against "
            "validity.setup.CORRECTIONS; that the correction exists is checked, "
            "that it was actually applied is not."
            + (
                " And the unregistered ones are not even checked for "
                "existence."
                if unverified
                else ""
            ),
            numbers=numbers,
        )

    margins = [
        f.margin for f in uncorrected if getattr(f, "margin", None) is not None
    ]
    # AN UNCORRECTED BIAS MUST NOT BE RESCUED BY ITS OWN UPSTREAM MARGIN.
    #
    # The worst uncorrected margin is reported, because the committee's worst
    # unhandled problem should stay visible instead of being averaged away --
    # but only where that margin is a shortfall. A margin at or above 1.0 on an
    # *uncorrected* bias means the origin lens deliberately declined to GRADE
    # it, which is not the same as clearing it: `sample.geometry.wall_drag`
    # returns MAX_MARGIN for a trapped bead because the trap CAN absorb the
    # Faxen bound, and whether the absorption applies is this lens's question.
    # Taking 10.0 at face value let the principal bias of a drag calibration
    # report ROUTINE and `advances: True` (found 2026-09-11). So an ungraded
    # uncorrected bias drops the gate to 0.0 -- CLAUDE.md §3's
    # `unevaluated != cleared`, applied to a margin instead of a status.
    shortfalls = [m for m in margins if m < 1.0]
    margin = min(shortfalls) if shortfalls else 0.0
    ungraded = [
        f.code
        for f in uncorrected
        if getattr(f, "margin", None) is None or f.margin >= 1.0
    ]
    numbers["worst_uncorrected_margin"] = round(min(margins), 3) if margins else None
    numbers["ungraded_uncorrected_codes"] = ungraded

    if ungraded:
        numbers["ungraded_note"] = (
            "these arrived with a passing upstream margin because the origin "
            "lens declined to grade them, not because they are small"
        )
    worst = ", ".join(f"{f.lens}:{f.code}" for f in uncorrected[:4])
    more = f" (+{len(uncorrected) - 4} more)" if len(uncorrected) > 4 else ""

    message = (
        f"{len(uncorrected)} of the {len(applicable)} bias findings that bear on "
        f"'{setup.intended_quantity}' are uncorrected: {worst}{more}. The "
        "quantity carries those biases into the result." + scoped_note
    )
    action = (
        "For each one either apply a correction and declare its code in "
        "corrections_applied, or change the setting so the bias does not arise."
    )

    if false_claims:
        named = ", ".join(
            f"{f.code} ({UNCORRECTABLE[f.code]})" for f in false_claims
        )
        message = (
            f"A correction was declared for {len(false_claims)} bias "
            f"{'finding' if len(false_claims) == 1 else 'findings'} that has no "
            f"correction: {named}. " + message
        )
        action = (
            "Withdraw the false declaration -- there is no such correction to "
            "have applied, and naming it would otherwise have made this ledger "
            "read clean. " + action
        )

    return CheckResult(
        "validity.bias_ledger",
        HARD,
        margin,
        "fail",
        message,
        action=action,
        numbers=numbers,
    )


def check_pixel_calibration(setup: "ValiditySetup") -> CheckResult:
    """G24: is the pixel size measured, when the quantity depends on it?

    docs/06 A1. A wrong pixel size scales every distance, velocity and
    diffusion coefficient by an unknown constant, and nothing downstream can
    detect it -- the numbers look perfectly reasonable.
    """
    required = "pixel_size" in setup.required_calibrations
    numbers = {
        "required": required,
        "measured": setup.pixel_size_measured,
        "intended_quantity": setup.intended_quantity,
    }

    if not required:
        # severity "info", NOT "ok" (KH, 2026-09-11): this branch turned a HARD
        # gate OFF on the strength of QUANTITY_REQUIREMENTS. docs/06 A1 is that
        # a wrong pixel size is undetectable downstream, so "it does not matter
        # here" is the one claim worth seeing.
        return CheckResult(
            "validity.pixel_calibration",
            HARD,
            MAX_MARGIN,
            "info",
            f"Pixel size is not on the critical path for "
            f"'{setup.intended_quantity}', so this gate does not apply.",
            action="From validity.setup.QUANTITY_REQUIREMENTS. If that "
            "classification is wrong, every distance derived from this data is "
            "wrong by an unknown constant and nothing downstream can tell "
            "(docs/06 A1).",
            numbers=numbers,
        )

    if setup.pixel_size_measured:
        return _ok(
            "validity.pixel_calibration",
            HARD,
            MAX_MARGIN,
            f"Pixel size is measured, which '{setup.intended_quantity}' "
            "depends on directly.",
            **numbers,
        )

    return CheckResult(
        "validity.pixel_calibration",
        HARD,
        0.0,
        "fail",
        f"'{setup.intended_quantity}' scales directly with pixel size, and "
        "there is no measured pixel size on record. Every distance derived "
        "from this data would be wrong by an unknown constant factor, and the "
        "result would still look reasonable (docs/06 A1).",
        action="Measure pixel size with a stage micrometer at this "
        "magnification. kb/systems/current.md > pixel_size_calibration already "
        "has a measured table -- confirm the entry for this objective and "
        "intermediate magnification rather than using the geometric value.",
        numbers=numbers,
    )


def check_photometric_calibration(setup: "ValiditySetup") -> CheckResult:
    """G25: background, dark current and flat-field, for intensity quantities."""
    required = [
        c
        for c in setup.required_calibrations
        if c in {"background", "dark_current", "flat_field"}
    ]
    have = {
        "background": setup.background_measured,
        "dark_current": setup.dark_current_measured,
        "flat_field": setup.flat_field_measured,
    }
    missing = [c for c in required if not have[c]]

    numbers = {
        "required": required,
        "missing": missing,
        "intended_quantity": setup.intended_quantity,
    }

    if not required:
        # severity "info", NOT "ok" (KH, 2026-09-11), same reason as G24's
        # branch above: the check turned itself off from a lookup table.
        return CheckResult(
            "validity.photometric_calibration",
            BIAS,
            MAX_MARGIN,
            "info",
            f"'{setup.intended_quantity}' does not rest on photometric "
            "calibration, so this gate does not apply.",
            action="From validity.setup.QUANTITY_REQUIREMENTS -- this pass is "
            "only as good as that classification.",
            numbers=numbers,
        )

    if not missing:
        return _ok(
            "validity.photometric_calibration",
            BIAS,
            MAX_MARGIN,
            "Every photometric calibration this quantity needs is measured: "
            + ", ".join(required)
            + ".",
            **numbers,
        )

    margin = (len(required) - len(missing)) / len(required)
    return CheckResult(
        "validity.photometric_calibration",
        BIAS,
        margin,
        "warn",
        f"'{setup.intended_quantity}' is intensity-based but "
        + ", ".join(missing)
        + " "
        + ("is" if len(missing) == 1 else "are")
        + " not measured. Absolute intensities and anything derived from them "
        "carry that offset or non-uniformity.",
        action="Measure the missing frames on the instrument: a dark frame at "
        "the same exposure, a uniform-field image for flat-field, and a "
        "sample-free region for background. None can be computed.",
        numbers=numbers,
    )


def check_committee_coverage(setup: "ValiditySetup") -> CheckResult:
    """G27: did the committee actually convene, and did anyone refuse?

    docs/05 §6 has the computational lenses run before this one. There is no
    orchestrator in the codebase yet -- each lens is invoked separately by its
    own CLI -- so nothing otherwise notices that a standing lens never ran.
    This lens is called last, so it is where that gets caught.

    A BLOCKED upstream lens also matters: BLOCKED means "no basis to decide",
    and a quantity cannot be certified valid on top of a lens that had no basis.
    """
    missing = setup.missing_standing_lenses()
    blocked = setup.blocked_lenses()
    failed = setup.failed_lenses()

    numbers = {
        "present": sorted(setup.upstream),
        "missing_standing": missing,
        "blocked": blocked,
        "failed": failed,
    }

    if not missing and not blocked and not failed:
        return _ok(
            "validity.committee_coverage",
            HARD,
            MAX_MARGIN,
            "Every standing lens returned, none BLOCKED and none FAILED.",
            **numbers,
        )

    parts = []
    if missing:
        parts.append(f"never ran: {', '.join(missing)}")
    if blocked:
        parts.append(f"BLOCKED: {', '.join(blocked)}")
    if failed:
        parts.append(f"FAILED: {', '.join(failed)}")

    return CheckResult(
        "validity.committee_coverage",
        HARD,
        0.0,
        "fail",
        "The committee did not reach a reviewable state — "
        + "; ".join(parts)
        + ". A verdict on whether the intended quantity survives cannot be "
        "given while a standing lens is missing or had no basis to decide.",
        action="Run the missing lenses, and supply the measurements the "
        "BLOCKED ones named. A lens that FAILED means the setting is wrong: "
        "change it and re-run rather than reviewing on top of it.",
        numbers=numbers,
    )


CHECKS: list[Check] = [
    Check("committee_coverage", HARD, ("upstream",), check_committee_coverage),
    Check("bias_ledger", HARD, ("upstream",), check_bias_ledger),
    Check("pixel_calibration", HARD, ("intended_quantity",), check_pixel_calibration),
    Check(
        "photometric_calibration",
        BIAS,
        ("intended_quantity",),
        check_photometric_calibration,
    ),
]


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
