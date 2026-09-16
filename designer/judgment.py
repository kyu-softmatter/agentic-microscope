"""Stage 2's seam: what a judgment lens is handed, and what it may hand back.

Stage 1 runs the nine `gate.py` modules and every plan it writes has
4 · 5 · 6 · 8's judgment halves `unevaluated` -- a hole, not a pass (E4). This
module is the boundary those four cross.

**Code cannot convene a subagent, and this module does not pretend to.** The
four agents in `.claude/agents/` have Read/Grep/Glob and no more; the main
agent convenes them. What code *can* do is the part that decides whether the
exchange was honest, and there are two halves of it:

``build_packets``
    what each lens is handed. Its own gate's ``Verdict`` -- **to interpret, not
    to recompute** -- the numbers another lens carried to it, and the list of
    things it must rule on.

``read_judgment`` / ``check_judgment``
    what it may hand back. Nine refusals, every one of them a way a judgment
    verdict can look like a review and not be one.

Both halves live in one module on purpose: they are one contract, and a schema
written out in one file and read back in another drifts the first time either
moves.

**The `must_rule_on` list is derived, never declared.** It is assembled from
what the gates already emitted and from `validity.setup`'s own ledger, for the
reason [the planning-layer entry](../kb/decisions/2026-09-13-the-planning-layer.md)
§1 gives for the refiner: a checklist maintained beside the code drifts from
it, and `committee reconcile` is still reporting 7 and 8 because two such
tables did exactly that. A question this module invented would be a tenth
place for the same rot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .emit import JUDGMENT_LENSES, LENS_NUMBER
from .run import CROSS_TIER, INTRA_TIER, Result

#: Lens -> the agent definition that is its judgment half. The files are the
#: authority on what each one does; this maps name to lens and nothing more.
AGENTS = {
    "sample": "sample-optics",
    "photo": "photo-perturbation",
    "validity": "measurement-validity",
    "stability": "mechanical-env",
}

#: What a returned verdict may say. The same three words the gates use, so a
#: judgment verdict and a gate verdict can be read side by side.
JUDGMENT_STATUSES = ("PASS", "PASS_WITH_CHANGES", "FAIL", "BLOCKED")

#: What one ruling may be. **The ruling is about the FINDING**, which is the
#: part the first vocabulary left unsaid.
#:
#: It was `accept` / `refuse` / `unevaluated` until 2026-09-15, and the two
#: agents convened on the first real proposal used the two words in OPPOSITE
#: senses for the same act. Lens 4 ruled `accept` and wrote *"the gate's
#: refusal stands"*; lens 5 ruled `refuse` and wrote *"the finding stands"*.
#: Both meant the same thing. `accept` does not say whether what is accepted
#: is the finding or the configuration in spite of it -- and `cleared-a-stop`,
#: the rule that puts §2 precedence level 4 into code, keyed on exactly that
#: word. Lens 4's honest agreement would have been refused had the subject
#: carried `kind: hard` instead of a Phase-0 `None`.
#:
#: `unevaluated` is the third and it is not a formality: a reviewer who cannot
#: rule on something must be able to say so, or the only way to return a
#: verdict is to pretend. `unevaluated` != `cleared` (§3) holds inside a
#: judgment verdict exactly as it holds between lenses.
RULINGS = ("upheld", "overruled", "unevaluated")

#: The old words, and why each is now refused instead of guessed at.
#:
#: Refused rather than translated. A verdict written in an ambiguous
#: vocabulary cannot be read by picking the reading that happens to pass --
#: that is the whole defect, applied once more.
AMBIGUOUS_RULINGS = {
    "accept": "one convened lens used it for `upheld` (the finding stands) "
    "and the rule encoding §2 precedence level 4 read it as `overruled` "
    "(proceed in spite of the finding)",
    "refuse": "one convened lens used it for `upheld` (the finding stands) "
    "and its plain sense is `overruled`",
}


@dataclass(frozen=True)
class Subject:
    """One thing a lens must rule on, and why it is on the list."""

    code: str
    #: hard | bias | soft | info -- of the finding, which is what decides who
    #: may overrule it (§2 precedence).
    kind: str | None
    severity: str
    #: The gate's margin. Carried so the reviewer can cite it and so
    #: `check_judgment` can refuse a verdict that restates it differently.
    m: float | None
    #: Which of the derived lists put it here.
    because: str
    #: For a bias: the correction that exists, or why none does. From
    #: `validity.setup`'s two registries, not from this module.
    correction: str | None = None


@dataclass(frozen=True)
class Packet:
    """Everything one judgment lens is handed, and nothing it should derive."""

    lens: str
    number: int
    agent: str
    agent_file: str
    #: The gate's own verdict, as a dict. **The gate is authoritative over the
    #: agent file** (every one of the four says so in its own header), so this
    #: is the thing being interpreted.
    verdict: dict | None
    #: Handoffs INTO this lens: who carried what. A judgment lens never
    #: generates the number it is judging (§2), so the provenance of each
    #: number it will cite has to arrive with it.
    carried: list[dict] = field(default_factory=list)
    must_rule_on: list[Subject] = field(default_factory=list)
    #: D7: read the `assumed:` line of every verdict, it is the verdict's real
    #: content. Listed separately from the rulings because an assumed input is
    #: not a finding and cannot be ruled on -- it is what the rulings rest on.
    assumed_inputs: list[str] = field(default_factory=list)
    #: E4, inside the packet: what stage 1 could not evaluate in this lens's
    #: own scope, so the reviewer is not left to infer a pass from silence.
    unevaluated_in_scope: list[dict] = field(default_factory=list)
    #: The lenses 01 §4 pairs this one with, each with the constraint neither
    #: owns and that lens's verdict. **Not the same as `carried`**: that is a
    #: number crossing, this is a constraint with no owner, which is why both
    #: verdicts have to be read side by side (E6). Missing until 2026-09-15,
    #: which left `sample-optics` without lens 1 -- the pairing its own file
    #: names as mandatory.
    cross_lens: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = asdict(self)
        out["returns"] = _RETURN_SCHEMA
        return out


#: The shape `read_judgment` will accept, written into the packet so the
#: contract travels with the request instead of living only in a docstring.
_RETURN_SCHEMA = {
    "lens": "1..9, this packet's",
    "agent": "this packet's agent name",
    "status": list(JUDGMENT_STATUSES),
    "rulings": [
        {
            "code": "one of must_rule_on's codes -- a code not on that list is refused",
            "ruling": list(RULINGS),
            "ruling_means": {
                "upheld": "the gate's finding stands as reported -- including "
                "where the finding IS a refusal",
                "overruled": "this lens judges the finding does not hold for "
                "this proposal. Forbidden on a `hard` finding at m < 1 (§2 "
                "precedence level 4), permitted on a clean one, which is how "
                "lens 6 refuses to advance what 1-3 cleared",
                "unevaluated": "this lens cannot rule. Not the same as either "
                "of the other two (§3)",
            },
            "basis": "REQUIRED. A ruling with no basis is refused (§6: never "
            "store without a Why)",
            "source": "the kb/ entry or data file it rests on, where there is one",
        }
    ],
    "unevaluated": "REQUIRED KEY EVEN WHEN EMPTY. What this lens could not "
    "judge, and why -- an absent key reads as a cleared one (§3)",
}


# --------------------------------------------------------------------------
# out -- what each lens is handed
# --------------------------------------------------------------------------


def _carried_into(lens: str) -> list[dict]:
    """The handoff table's edges pointing at this lens."""
    return [
        {"from": src, "from_lens": LENS_NUMBER[src], "what": why}
        for (src, dst), why in {**INTRA_TIER, **CROSS_TIER}.items()
        if dst == lens
    ]


def _cross_lens(result: Result, lens: str) -> list[dict]:
    """The paired lenses' verdicts, from `committee.constraints`.

    E6 in the packet. `sample-optics` says in its own description *"Must be
    invoked together with optics (Lens 1) -- immersion vs depth is a
    cross-constraint between the two lenses (01 §4)"*, and
    `photo-perturbation` the same for lenses 1 and 2; until this existed the
    packets carried neither, so the two agents were being asked to judge
    without the lens their files say they cannot be judged without.

    The pairs are **parsed** from 01 §4's table, so a constraint added there
    reaches the packets with no edit here and one removed stops reaching them.

    ⚠ A partner that did not run contributes a row with `verdict: null` and
    the reason. That is not an omission: a constraint whose other half is
    unevaluated is `unevaluated`, not cleared (§3).
    """
    from committee import constraints

    by_number = {number: name for name, number in LENS_NUMBER.items()}
    reasons = {row["lens"]: row for row in result.unevaluated}

    out: list[dict] = []
    for constraint in constraints.for_lens(LENS_NUMBER[lens]):
        for number in constraint.lenses:
            if number == LENS_NUMBER[lens]:
                continue
            other = by_number[number]
            run = result.runs.get(other)
            row = {
                "constraint": constraint.name,
                "content": constraint.content,
                "partly_retired": constraint.partly_retired,
                "lens": number,
                "name": other,
                "verdict": None,
                "why_absent": None,
            }
            if run is not None and run.ran:
                row["verdict"] = run.verdict.to_dict()
                if run.per_channel:
                    # Lens 1 is judged per channel, and a two-colour proposal's
                    # arms differ: on the real brief the red arm fails L1.4 and
                    # the green does not. Handing over `verdict` alone would
                    # hand over one arm and call it the lens.
                    row["per_channel"] = {
                        name: v.to_dict() for name, v in run.per_channel.items()
                    }
            else:
                absent = reasons.get(other)
                row["why_absent"] = (
                    f"{absent['state']}: {absent['why']}" if absent
                    else "this lens produced no verdict"
                )
            out.append(row)
    return out


def _own_findings(verdict) -> list[Subject]:
    """Every finding the lens's own gate emitted.

    All of them, not the failures: an agent handed only the failures would be
    reading a filtered gate, and the filter would be this module's opinion
    about what matters.
    """
    return [
        Subject(
            code=f.code,
            kind=getattr(f, "kind", None),
            severity=f.severity,
            m=verdict.margins.get(f.code),
            because="this lens's own gate emitted it",
        )
        for f in verdict.findings
    ]


def _skipped_checks(lens: str, verdict) -> list[Subject]:
    """The lens's registered checks that produced no result.

    **Reported by both agents convened on the first real proposal, from
    opposite sides.** Lens 5: *"my gate stopped in Phase 0 -- so the list
    contains the two missing inputs and nothing about light-driving, dose, or
    trap heating. The three subjects this section exists for produced no
    findings, hence no subjects, hence no obligation to speak."* Lens 4, of
    its own L4.7: *"`check_depth_window` does not read `imaging_depth_um` at
    all … Phase 0 being all-or-nothing suppressed the one check that would
    have told the operator which depths are allowed."*

    They are right and the shortfall is structural: `must_rule_on` derived
    only from emitted findings collapses to "what was missing" for any lens
    whose Phase 0 stopped.

    Derived from ``verdict.margins``, which is ``{result.code: margin}`` in all
    nine gates, against the lens's own ``CHECKS`` registry -- so this needs no
    change to any gate and cannot drift from one. A check with no margin did
    not run.

    ⚠ The subject is the check's registered code, not an emitted one, so it
    carries the registration's `kind` and no margin. A reviewer cannot rule on
    a number that does not exist; what it can do is say whether the silence is
    acceptable, which is the whole point of putting it on the list.
    """
    import importlib

    from committee import collect

    checks = importlib.import_module(f"{lens}.checks").CHECKS
    ran = set(verdict.margins) | {f.code for f in verdict.findings}

    # A registered check's code is NOT its emitted code: lens 4's
    # `na_feasibility` emits `geometry.na_feasibility`. The relation is a
    # prefix in one lens and a suffix in another, so it is looked up in
    # `committee/`, which parses it out of each `checks.py` -- rather than
    # guessed at here with string surgery, which is what this did first and
    # which reported every check of a lens that HAD run as skipped.
    emits: dict[str, set[str]] = {}
    for site in collect(lens):
        if site.check:
            emits.setdefault(site.check, set()).add(site.emitted_code)

    return [
        Subject(
            code=c.code,
            kind=c.kind,
            severity="skipped",
            m=None,
            because="a registered check of this lens that produced NO result "
            "-- the gate stopped in Phase 0, so its silence is not a pass (§3)",
        )
        for c in checks
        if not (ran & (emits.get(c.code, set()) | {c.code}))
    ]


def _ledger_subjects(setup) -> list[Subject]:
    """Lens 6's review list, from `validity.setup`'s own ledger.

    Three states, and the middle one is why this is not just "the uncorrected
    biases": a bias declared corrected for which no correction exists would
    have read clean, and an unaudited declaration cannot advance. All three
    are already computed by the setup -- this only labels them.
    """
    from validity.setup import CORRECTIONS, UNCORRECTABLE

    out: list[Subject] = []
    for f, because in (
        [(f, "an applicable bias with no correction declared")
         for f in setup.uncorrected_bias_findings()]
        + [(f, "declared corrected, and NO correction exists -- the ledger "
            "would have read clean")
           for f in setup.falsely_corrected_bias_findings()]
    ):
        out.append(
            Subject(
                code=f.code,
                kind=getattr(f, "kind", None),
                severity=f.severity,
                #: The ORIGIN lens's margin, which this lens does not have and
                #: must not invent. None here is honest: the number is in that
                #: lens's own packet row.
                m=getattr(f, "margin", None),
                because=because,
                correction=CORRECTIONS.get(f.code) or UNCORRECTABLE.get(f.code),
            )
        )
    for code in setup.unverified_corrections():
        out.append(
            Subject(
                code=code, kind="bias", severity="info", m=None,
                because="declared corrected and in neither registry -- accepted, "
                "but it pins the verdict's evidence to `assumed` until audited",
                correction=None,
            )
        )
    return out


def _scope_unevaluated(result: Result, lens: str) -> list[dict]:
    """What stage 1 could not evaluate that this lens needs to know about.

    Lens 6 reviews the others, so **everything** is in its scope. For 4 · 5 ·
    8 it is their own row only -- and if their own gate ran, there is nothing
    here, which is the honest empty list rather than an omitted key.
    """
    rows = result.unevaluated
    if lens == "validity":
        return rows
    return [row for row in rows if row["lens"] == lens]


def build_packets(result: Result, judgments: dict[str, Any] | None = None) -> dict[str, Packet]:
    """One packet per judgment lens that has something to be judged.

    A lens whose seat is `absent`, `undecided` or `not_reached` gets **no
    packet**, and that is a fact rather than an omission: there is no verdict
    for its agent to interpret, so convening it would be asking for an opinion
    with no subject. The plan still carries its row as `unevaluated` (E4).

    **Lens 6 is refused a packet until the others have returned** -- E2. It
    reviews the other lenses' verdicts, so a packet built before they exist
    would hand it the gate results and silently drop the judgment half of
    exactly what it is convened to review.
    """
    judgments = judgments or {}
    packets: dict[str, Packet] = {}

    waiting = [
        lens
        for lens in JUDGMENT_LENSES
        if lens != "validity"
        and lens in result.runs
        and result.runs[lens].ran
        and lens not in judgments
    ]

    for lens in JUDGMENT_LENSES:
        run = result.runs.get(lens)
        if run is None or not run.ran:
            continue
        if lens == "validity" and waiting:
            continue

        subjects = _own_findings(run.verdict) + _skipped_checks(lens, run.verdict)
        if lens == "validity" and run.setup is not None:
            subjects = _ledger_subjects(run.setup) + subjects

        packets[lens] = Packet(
            lens=lens,
            number=LENS_NUMBER[lens],
            agent=AGENTS[lens],
            agent_file=f".claude/agents/{AGENTS[lens]}.md",
            verdict=run.verdict.to_dict(),
            carried=_carried_into(lens),
            must_rule_on=subjects,
            assumed_inputs=list(run.verdict.assumed_inputs),
            unevaluated_in_scope=_scope_unevaluated(result, lens),
            cross_lens=_cross_lens(result, lens),
        )
    return packets


def write_packets(result: Result, out_dir: Path, judgments=None) -> list[Path]:
    """One file per packet, so the boundary is testable without the agents.

    The same argument the planning-layer entry §3 makes for `brief.yaml`: a
    boundary only a function call crosses cannot be re-run from either side.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for lens, packet in build_packets(result, judgments).items():
        path = out_dir / f"packet-{packet.number}-{lens}.yaml"
        path.write_text(
            yaml.safe_dump(packet.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        written.append(path)
    return written


# --------------------------------------------------------------------------
# in -- what a lens may hand back
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ruling:
    code: str
    ruling: str
    basis: str
    source: str | None = None


@dataclass
class Judgment:
    lens: str
    agent: str
    status: str
    rulings: tuple[Ruling, ...]
    unevaluated: tuple[dict, ...]
    path: Path | None = None

    def ruling_for(self, code: str) -> Ruling | None:
        return next((r for r in self.rulings if r.code == code), None)


@dataclass(frozen=True)
class Refusal:
    """Why a judgment verdict is not a review. Carries the fix, like every
    other refusal in this repository (§3: a refusal names what would resolve
    it)."""

    rule: str
    why: str
    action: str


def read_judgment(path: str | Path) -> Judgment:
    """Parse one returned verdict. Shape only -- `check_judgment` judges it."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if "unevaluated" not in raw:
        # Refused here rather than in `check_judgment`, because a Judgment
        # with an invented empty list would already have lost the distinction.
        raise ValueError(
            f"{path}: no `unevaluated` key. It is required even when empty -- "
            "an absent key reads as a cleared one (§3). Write `unevaluated: []` "
            "if this lens judged everything it was handed."
        )

    rulings = []
    for r in raw.get("rulings") or ():
        rulings.append(
            Ruling(
                code=r.get("code"),
                ruling=r.get("ruling"),
                basis=(r.get("basis") or "").strip(),
                source=r.get("source"),
            )
        )
    return Judgment(
        lens=raw.get("lens"),
        agent=raw.get("agent"),
        status=raw.get("status"),
        rulings=tuple(rulings),
        unevaluated=tuple(raw.get("unevaluated") or ()),
        path=path,
    )


def check_judgment(
    judgment: Judgment, packet: Packet, others: dict[str, Judgment] | None = None
) -> list[Refusal]:
    """Everything wrong with one returned verdict. Empty means it is a review.

    ``others`` is the judgments already in hand, needed for E2 alone.
    """
    out: list[Refusal] = []
    others = others or {}

    if judgment.lens not in (packet.lens, packet.number):
        out.append(Refusal(
            "wrong-lens",
            f"the verdict says lens {judgment.lens!r} and the packet is lens "
            f"{packet.number} ({packet.lens})",
            "return the verdict for the packet it answers",
        ))

    if judgment.status not in JUDGMENT_STATUSES:
        out.append(Refusal(
            "unknown-status",
            f"status {judgment.status!r} is not one of {JUDGMENT_STATUSES}",
            "use the gates' own words, so the two verdicts read side by side",
        ))

    subjects = {s.code: s for s in packet.must_rule_on}

    for r in judgment.rulings:
        if r.ruling in AMBIGUOUS_RULINGS:
            out.append(Refusal(
                "ambiguous-ruling",
                f"{r.code}: {r.ruling!r} was withdrawn 2026-09-15 -- "
                + AMBIGUOUS_RULINGS[r.ruling],
                "say `upheld` if the finding stands, `overruled` if this lens "
                "judges it does not hold. The ruling is about the FINDING",
            ))
        elif r.ruling not in RULINGS:
            out.append(Refusal(
                "unknown-ruling",
                f"{r.code}: ruling {r.ruling!r} is not one of {RULINGS}",
                "`unevaluated` is the honest answer where a ruling is not "
                "possible; it is not the same as either of the others",
            ))
        if not r.basis:
            out.append(Refusal(
                "no-basis",
                f"{r.code}: ruled {r.ruling!r} with no basis",
                "state what the ruling rests on. A judgment with no Why is not "
                "storable (§6) and not reviewable",
            ))
        if r.code not in subjects:
            out.append(Refusal(
                "invented-subject",
                f"{r.code}: nothing in this packet asked about it",
                "rule on what the gate emitted. A subject this lens introduced "
                "is a finding it generated, and a judgment lens never generates "
                "the number it is judging (§2)",
            ))

    ruled = {r.code for r in judgment.rulings}
    silent_ok = {row.get("code") for row in judgment.unevaluated if isinstance(row, dict)}
    for code, subject in subjects.items():
        if code in ruled or code in silent_ok:
            continue
        out.append(Refusal(
            "silence",
            f"{code} ({subject.because}) has no ruling and is not in "
            "`unevaluated`",
            "rule on it, or name it in `unevaluated` with a reason. Omitting "
            "it reads as a pass (§3)",
        ))

    for r in judgment.rulings:
        subject = subjects.get(r.code)
        if subject is None or r.ruling != "overruled":
            continue
        if subject.kind == "hard" and subject.m is not None and subject.m < 1.0:
            out.append(Refusal(
                "cleared-a-stop",
                f"{r.code}: overruled a `hard` finding at m={subject.m:.2f}",
                "§2 precedence level 4 -- this lens may refuse to advance what "
                "1-3 cleared; it may not clear what they stopped. Return a "
                "revision instead",
            ))

    if judgment.lens in ("validity", LENS_NUMBER["validity"]):
        expected = {
            lens for lens in JUDGMENT_LENSES
            if lens != "validity" and lens in _ran_lenses(packet)
        }
        absent = sorted(expected - set(others))
        if absent:
            out.append(Refusal(
                "out-of-order",
                f"lens 6 returned before {', '.join(absent)}",
                "E2: lens 6 reviews the other lenses' verdicts, so it cannot "
                "run beside them. Convene it alone and last",
            ))

    return out


def _ran_lenses(packet: Packet) -> set[str]:
    """Which judgment lenses the packet's own `unevaluated_in_scope` shows as
    having run. Lens 6's packet carries every row, which is what makes this
    answerable from the packet alone rather than needing the Result back."""
    did_not = {row["lens"] for row in packet.unevaluated_in_scope}
    return {lens for lens in JUDGMENT_LENSES if lens not in did_not}


def judgment_rows(
    packets: dict[str, Packet],
    judgments: dict[str, Judgment],
    result: Result | None = None,
) -> list[dict]:
    """The `unevaluated_judgment` block, with the ones that came back filled in.

    **Four states, because a hole has four causes and they are not one fact.**
    A lens with a judgment stops being a hole; the other three are all still
    holes and each needs its own reason, or a reader has to guess which one
    happened:

    ``judged``     the verdict came back and survived `check_judgment`
    ``convened``   a packet was written and nothing came back
    ``awaiting``   the gate ran and the packet was WITHHELD -- lens 6 only,
                   because E2 will not let it review verdicts that do not
                   exist yet
    ``absent``     the gate produced no verdict, so there is nothing to
                   convene over. ``result`` supplies the reason; without it
                   the row says only that there is none

    Collapsing `awaiting` into `absent` was the first version of this and it
    was wrong in the worst available direction: lens 6's gate had returned
    FAIL, and the row said its gate produced no verdict.
    """
    reasons = {row["lens"]: row for row in (result.unevaluated if result else ())}
    rows = []
    for lens in JUDGMENT_LENSES:
        number = LENS_NUMBER[lens]
        judgment = judgments.get(lens)
        if judgment is not None:
            rows.append({
                "lens": number,
                "name": lens,
                "state": "judged",
                "agent": judgment.agent,
                "status": judgment.status,
                "rulings": [asdict(r) for r in judgment.rulings],
                "unevaluated": list(judgment.unevaluated),
            })
        elif lens in packets:
            rows.append({
                "lens": number,
                "name": lens,
                "state": "convened",
                "agent": AGENTS[lens],
                "why": "a packet was written for this lens and no verdict came "
                "back -- convened and unanswered, which is not the same as "
                "uncallable",
            })
        elif result is not None and lens in result.runs and result.runs[lens].ran:
            rows.append({
                "lens": number,
                "name": lens,
                "state": "awaiting",
                "agent": AGENTS[lens],
                "why": "the gate ran and the packet was withheld: E2, this lens "
                "reviews the others' verdicts and they have not returned",
            })
        else:
            row = reasons.get(lens)
            because = f" -- the gate is `{row['state']}`: {row['why']}" if row else ""
            rows.append({
                "lens": number,
                "name": lens,
                "state": "absent",
                "agent": AGENTS[lens],
                "why": "no packet: this lens's gate produced no verdict for its "
                f"agent to interpret{because}",
            })
    return rows
