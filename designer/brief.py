"""Reading an experiment brief -- the designer's input (CLAUDE.md §2).

The brief is the query refiner's output, hand-written until that layer exists.
Its whole purpose is that **every value carries the entry it came from**, so
this module refuses to hand out a value without one: `Fact` is a triple, not a
number, and there is no accessor that returns the number alone.

What this module does NOT do, on purpose:

* **No defaults.** A field the brief does not carry comes back `None`. Filling
  one in here would originate a physical number at the one point in the
  pipeline that looks least like a decision (CLAUDE.md rule 2).
* **No validation of physics.** Whether 0.1625 um/px is right for a 40x is the
  lenses' question, not this reader's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: Resolver ranks, in the order they appear in the planning-layer entry.
#: R1 is answerable by the operator; R2 never is, and the designer must not
#: default past one -> kb/decisions/2026-09-13-the-planning-layer.md
RANKS = ("R0", "R1", "R2", "R3")


@dataclass(frozen=True)
class Fact:
    """One value and where it came from. The source is not optional."""

    value: Any
    source: str
    evidence: str = "assumed"  # measured | estimated | computed | assumed

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError(
                "a fact without a source is not a fact -- put it in `gaps` "
                "with a resolver rank instead (CLAUDE.md rule 2)"
            )


@dataclass(frozen=True)
class Gap:
    """A field the brief could not fill, and who could."""

    field: str
    rank: str
    consumed_by: tuple[str, ...] = ()
    why: str | None = None
    action: str | None = None
    #: The `missing.*` codes this gap answers, where the brief knows them.
    #:
    #: Optional, and it exists because the alternative was worse. Matching a
    #: gap to a code by substring called `target_relative_error` a field the
    #: brief had not predicted -- it had, under exactly that name, and the
    #: emitted code is `missing.target_error`. That number is reported as a
    #: measure of the brief's quality, so a false surprise in it is a false
    #: accusation. Naming the code is explicit and guesses nothing; the
    #: substring fallback stays for the gaps that do not.
    answers: tuple[str, ...] = ()

    @property
    def blocks(self) -> bool:
        """R2 is measurable and unmeasured, so no answer exists to default to.

        R1 is answerable and R3 is nobody's, so neither stops the designer:
        R1 becomes a question and R3 becomes a recorded absence.
        """
        return self.rank == "R2"


@dataclass
class Brief:
    path: Path
    meta: dict
    goal: dict
    facts: dict
    gaps: tuple[Gap, ...]
    departures: tuple[dict, ...]
    #: Dotted paths of every fact `get()` has returned. What is left over is a
    #: fact the brief carried and no lens asked for -- worth reporting, since
    #: it is either a wasted question or a lens that should have consumed it.
    consumed: set[str] = field(default_factory=set)

    @property
    def intended_quantity(self) -> str | None:
        return self.goal.get("intended_quantity")

    def get(self, dotted: str) -> Fact | None:
        """`brief.get("lens_2_detection.pixel_size_um_per_px")`.

        Returns `None` for anything absent -- never a default, and never a
        bare number even when present.
        """
        node: Any = self.facts
        # The nearest enclosing dict that carries provenance. A brief nests
        # plain scalars under a node that sources them once -- `objective:
        # {value: ..., na: 1.25, source: ...}` -- so `na` inherits the
        # objective's source rather than repeating it on every line.
        provenance: dict = {}
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            if "source" in node:
                provenance = node
            node = node[part]

        if isinstance(node, dict):
            if "value" not in node:
                return None
            if "source" in node:
                provenance = node
            value = node["value"]
        else:
            value = node

        if value is None:
            # A `value: null` entry is a deliberate "known to be undecided",
            # written beside a `see:` pointing at the gap. Not a fact.
            return None

        source = provenance.get("source", "")
        if not source:
            # Refusing here rather than inventing an empty source is the point
            # of the type -- see Fact.__post_init__.
            raise ValueError(
                f"{self.path}: '{dotted}' has a value and no source anywhere "
                "above it. Add a `source:` to it or to its parent."
            )
        self.consumed.add(dotted)
        return Fact(value=value, source=source,
                    evidence=provenance.get("evidence", "assumed"))

    def value(self, dotted: str) -> Any:
        fact = self.get(dotted)
        return None if fact is None else fact.value

    def gap(self, name: str) -> Gap | None:
        for g in self.gaps:
            if g.field == name:
                return g
        return None

    @property
    def blocking_gaps(self) -> tuple[Gap, ...]:
        return tuple(g for g in self.gaps if g.blocks)


def load(path: str | Path) -> Brief:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    gaps = []
    for g in raw.get("gaps") or ():
        rank = g.get("rank")
        if rank not in RANKS:
            raise ValueError(f"{path}: gap '{g.get('field')}' has rank {rank!r}, not one of {RANKS}")
        gaps.append(
            Gap(
                field=g["field"],
                rank=rank,
                consumed_by=tuple(g.get("consumed_by") or ()),
                why=g.get("why"),
                action=g.get("action"),
                answers=tuple(g.get("answers") or ()),
            )
        )

    return Brief(
        path=path,
        meta=raw.get("meta") or {},
        goal=raw.get("goal") or {},
        facts=raw.get("facts") or {},
        gaps=tuple(gaps),
        departures=tuple(raw.get("departures") or ()),
    )
