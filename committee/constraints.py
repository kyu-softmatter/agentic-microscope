"""The nine cross-lens constraints, read out of the document that owns them.

`docs/01-architecture.md` §4's table is the roster of what **no single lens
catches** — the real reason for having a committee. CLAUDE.md §2 points at it
and does not restate it, and until 2026-09-15 no code could see it at all.

So stage 2 handed each judgment lens its own gate's verdict and the numbers
another lens carried to it, and **not the verdict of the lens it is paired
with**. Both agent files say in their own descriptions that this is wrong:
`sample-optics` — *"Must be invoked together with optics (Lens 1) — immersion
vs depth is a cross-constraint between the two lenses (01 §4)"* — and
`photo-perturbation` the same for lenses 1 and 2. That is CLAUDE.md E6, and the
packets were missing exactly what it names.

**Parsed, not copied.** A table transcribed into a dict here would be a second
definition of the nine and would drift from the prose, which is the failure
`committee/` exists to stop and which its two bias registries had already
committed twice. The document stays the single definition; this reads it.

    from committee import constraints

    constraints.partners_of(4)      # -> (1, 8)
    constraints.for_lens(4)         # -> the Constraint rows naming lens 4

⚠ **A pair here is not a handoff.** `designer.run`'s `CROSS_TIER` records a
*number* crossing from one lens to another; these record a constraint **neither
lens owns**, which is why both verdicts have to be read side by side and why
one of them cannot simply compute it. Two of the nine have no code at all
(01 §4 says so of ROI-vs-statistics and of the dead 4 → 6 half).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "01-architecture.md"

#: The heading the table sits under. Matched exactly: a rename should break
#: this loudly rather than silently return no constraints, which would read as
#: "no lens is paired with any other".
_HEADING = "### Cross-lens constraints"

#: A struck-through span, e.g. `~~4 → 6~~`. Removed before the lens numbers are
#: read, because the strikethrough is the document saying that half is GONE --
#: the 4 -> 6 particle count died with G11 on 2026-09-11. A parser that ignored
#: the markup would resurrect a constraint nothing implements.
_STRUCK = re.compile(r"~~.*?~~")


@dataclass(frozen=True)
class Constraint:
    """One row of 01 §4: what it is, and which lenses share it."""

    name: str
    lenses: tuple[int, ...]
    #: The row's own prose, verbatim. Carried so a packet can quote the
    #: document rather than paraphrase it.
    content: str
    #: True where the row records a half that has been removed, so the pair
    #: count and the prose can disagree without either being wrong.
    partly_retired: bool = False


def _rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(_HEADING))
    except StopIteration as exc:  # pragma: no cover - guarded by a test
        raise ValueError(
            f"{_DOC}: no {_HEADING!r} heading. The cross-lens table is the "
            "single definition of the nine constraints; if it moved, this "
            "parser has to be pointed at it rather than quietly find none."
        ) from exc

    out: list[list[str]] = []
    for ln in lines[start + 1 :]:
        stripped = ln.strip()
        if stripped.startswith("## ") or stripped == "---":
            break
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        out.append(cells)
    return out


@lru_cache(maxsize=1)
def all_constraints() -> tuple[Constraint, ...]:
    """Every row of 01 §4's table, in document order."""
    rows = _rows(_DOC.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError(f"{_DOC}: the cross-lens table has no rows")

    header, *data = rows
    name_at, lenses_at = header.index("Constraint"), header.index("Lenses")
    content_at = header.index("Content")

    out = []
    for row in data:
        raw = row[lenses_at]
        live = _STRUCK.sub("", raw)
        numbers = tuple(dict.fromkeys(int(n) for n in re.findall(r"\d+", live)))
        if not numbers:
            continue
        out.append(
            Constraint(
                name=row[name_at],
                lenses=numbers,
                content=row[content_at] if content_at < len(row) else "",
                partly_retired=bool(_STRUCK.search(raw)),
            )
        )
    return tuple(out)


def for_lens(lens: int) -> tuple[Constraint, ...]:
    """The constraints that name this lens."""
    return tuple(c for c in all_constraints() if lens in c.lenses)


def partners_of(lens: int) -> tuple[int, ...]:
    """The other lenses this one shares a constraint with, ascending.

    This is the roster E6 is about: *"convene lenses 1 and 5 together, and 1
    and 4 likewise"*. It is derived from the table rather than from E6's prose,
    so a constraint added to 01 §4 reaches the packets without anything here
    being edited -- and one removed stops reaching them.
    """
    others = {n for c in for_lens(lens) for n in c.lenses if n != lens}
    return tuple(sorted(others))
