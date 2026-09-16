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

#: What one ruling may be.
#:
#: `unevaluated` is here and it is the important one: a reviewer who cannot
#: rule on something must be able to say so, or the only way to return a
#: verdict is to pretend. `unevaluated` != `cleared` (§3) holds inside a
#: judgment verdict exactly as it holds between lenses.
RULINGS = ("accept", "refuse", "unevaluated")


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

        subjects = _own_findings(run.verdict)
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
        if r.ruling not in RULINGS:
            out.append(Refusal(
                "unknown-ruling",
                f"{r.code}: ruling {r.ruling!r} is not one of {RULINGS}",
                "`unevaluated` is the honest answer where a ruling is not "
                "possible; it is not the same as `accept`",
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
        if subject is None or r.ruling != "accept":
            continue
        if subject.kind == "hard" and subject.m is not None and subject.m < 1.0:
            out.append(Refusal(
                "cleared-a-stop",
                f"{r.code}: accepted a `hard` finding at m={subject.m:.2f}",
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
