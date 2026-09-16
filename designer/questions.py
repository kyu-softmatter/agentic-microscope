"""The R1 gaps as one list somebody can answer in one sitting.

`Result.unresolved` already carries every gap with its rank, the checks that
consume it and the action that would resolve it. What it does not carry is an
**order**, and without one a run reports twenty questions as a flat list in
which the one that unblocks a whole lens sits between two that unblock one
check each.

That is the whole of this module: no new facts, one ordering, and the ordering
is **derived** rather than chosen.

    python -m designer.cli questions config/briefs/active-microrheology.yaml

Three tiers, and each is read off something the pipeline already computed:

``makes a lens constructible``
    `designer/build.py` returns ``NotConstructible`` naming the required
    argument it could not fill, so the gate is never called and **emits no
    `missing.*` code at all**. One answer turns a silent lens into a speaking
    one, which is worth more than one answer that moves one margin.

``decides whether a lens is convened``
    `designer/roster.py` gives a seat the state ``undecided`` with the input
    that would settle it. Until that arrives the lens is neither convened nor
    absent, and recording it as absent would be the guess E4 exists to stop.

``named by N checks``
    the brief's own ``consumed_by``, descending. A declaration, not an
    inference.

⚠ **This module ranks questions; it does not rank importance.** A field named
by one check can matter more than one named by five -- `characteristic_time_s`
feeds only L2.6 and L2.6 grades nothing, while it is also the number eight
settings in the operator's inventory are bounded from below by. The tiers say
what is *structurally* upstream, which is a different claim and the only one
derivable from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


from .run import Result

#: Tier labels, in the order they are asked.
CONSTRUCTS = "makes a lens constructible"
CONVENES = "decides whether a lens is convened at all"
CONSUMED = "named by its consumers"


@dataclass
class Question:
    """One thing to ask the operator, and what answering it does."""

    field: str
    rank: str
    tier: str
    #: The checks the brief says consume it.
    consumed_by: tuple[str, ...] = ()
    #: What would resolve it. `None` is a defect, not a blank: CLAUDE.md §3
    #: says a refusal names what would resolve it, so a gap without one is
    #: reported as missing an instruction rather than shown empty.
    action: str | None = None
    why: str | None = None
    #: For the first two tiers: the lens this answer unblocks, and how.
    unblocks: str | None = None
    #: Where the brief's name for a field and the builder's name for the same
    #: fact differ. Both are kept -- see `_constructible_by`.
    also_called: tuple[str, ...] = field(default_factory=tuple)

    @property
    def answerable(self) -> bool:
        """R1 is the operator's, in conversation. R2 is a measurement and R3
        is nobody's, so neither belongs on a list headed "answer these"."""
        return self.rank == "R1"


def _constructible_by(result: Result) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Field -> (lens, the builder's own names for it).

    ⚠ THE TWO SIDES DO NOT ALWAYS AGREE ON THE NAME. The brief's gap is
    `trap_dial_percent` and `build.py`'s `NotConstructible` says
    `dial_percent`; they are one fact with two names. Matched on containment
    and **both names are kept on the Question**, because a refiner harvesting
    the builder's name would ask for `dial_percent` and the brief would answer
    `trap_dial_percent` -- and nothing would notice they had met.
    """
    out: dict[str, tuple[str, tuple[str, ...]]] = {}
    for row in result.unevaluated:
        if row["state"] != "not_constructible":
            continue
        for missing in row.get("missing") or ():
            out[missing] = (row["lens"], (missing,))
    return out


def _convening(result: Result) -> dict[str, str]:
    """The input that would settle an `undecided` seat, from `Seat.decided_by`.

    Read off the seat rather than parsed out of its sentence. The first
    version of this matched `gap.field` against `seat.why` and missed
    `acquisition_duration_s` -- the prose says "no acquisition duration", so
    neither the field nor any underscore substitution of it appears. A seat
    that knows which gap it consulted should say so, and now does.
    """
    return {
        seat.decided_by: f"lens {lens}: {seat.why}"
        for lens, seat in result.seats.items()
        if seat.state == "undecided" and seat.decided_by
    }


def questions(result: Result) -> list[Question]:
    """Every gap as a Question, ordered by what answering it unblocks."""
    constructs = _constructible_by(result)
    convenes = _convening(result)

    out: list[Question] = []
    for gap in result.brief.gaps:
        tier, unblocks, also = CONSUMED, None, ()

        hit = next(
            (
                (name, lens, names)
                for name, (lens, names) in constructs.items()
                if name == gap.field or name in gap.field or gap.field in name
            ),
            None,
        )
        if hit is not None:
            name, lens, names = hit
            tier, unblocks = CONSTRUCTS, (
                f"lens {lens} -- its Setup cannot be built, so the gate is "
                "never called and emits no `missing.*` code at all"
            )
            also = tuple(n for n in names if n != gap.field)
        elif gap.field in convenes:
            tier, unblocks = CONVENES, convenes[gap.field]

        out.append(
            Question(
                field=gap.field,
                rank=gap.rank,
                tier=tier,
                consumed_by=gap.consumed_by,
                action=gap.action,
                why=gap.why,
                unblocks=unblocks,
                also_called=also,
            )
        )

    order = {CONSTRUCTS: 0, CONVENES: 1, CONSUMED: 2}
    out.sort(key=lambda q: (order[q.tier], -len(q.consumed_by), q.field))
    return out


def without_an_action(result: Result) -> list[Question]:
    """R1 gaps carrying no instruction.

    CLAUDE.md §3: *"A refusal names what would resolve it -- the missing input
    and where it lives. A `BLOCKED` with no fix instruction is a bug."* The
    rule is enforced in the gates' `missing.*` findings and **not** in the
    brief's own gap list, so a gap can be a question with no way to answer it.
    Reported rather than filled in: what would resolve it is the operator's to
    say, not this module's to guess (rule 2).
    """
    return [q for q in questions(result) if q.answerable and not q.action]
