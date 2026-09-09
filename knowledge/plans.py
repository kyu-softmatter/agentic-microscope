"""Refuse a hardware plan whose shape has been lost.

A `kb/plans/` entry is the artefact between the committee and the instrument
(docs/05 §6 stage 5): the main agent writes it, and one skill per subsystem
reads it and acts. So a malformed plan is not a documentation problem -- it is a
skill acting on a misreading. This module is the check that runs first.

    python -m knowledge.cli plan-check

Two of the checks are the repository's own rules, not formatting:

**`unevaluated` is not `cleared`** (CLAUDE.md §3). A plan must carry the lenses
that were *not* convened, so a conditional lens nobody ran cannot be mistaken
for one that passed.

**A return code is not a confirmation** (SAFETY §0). On the tweezers, six wrong
states and success are the same byte, so every step in the sequence has to name
something *observed* as its confirmation. A plan that writes "returns 0" in that
column is refused here rather than at the instrument.

What this does not do is judge the plan. Whether the sequence is a good one is
the committee's job and the operator's; this only holds the shape that makes
those judgements readable.
"""

from __future__ import annotations

from pathlib import Path

from hardware.orchestrator import SUBSYSTEMS

from .index import Problem, read_entry, split_frontmatter

#: Where a plan is in its life. `planned` is written before the run; `run`
#: means it happened and the entry is ready to graduate into `kb/decisions/`
#: with its outcome; `abandoned` is a run that did not happen, which stays
#: visible rather than being deleted.
PLAN_STATUSES = ("planned", "run", "abandoned")

#: Sections every plan carries, whatever its status.
REQUIRED_SECTIONS = (
    "Request",
    "Proposed setting + rationale",
    "Committee verdict",
    "Preconditions",
    "Sequence",
    "Stop conditions",
)

#: The column in the sequence table that SAFETY §0 makes load-bearing.
CONFIRMATION_COLUMN = "Confirmed by"

#: Phrases that are not confirmations, however they are dressed up. Matched
#: case-insensitively against the confirmation cell. This list is short on
#: purpose: it names the failure that has actually happened on this instrument
#: rather than trying to recognise every bad answer.
NON_CONFIRMATIONS = (
    "return code",
    "returns 0",
    "returned 0",
    "exit 0",
    "exit code",
    "rc=0",
    "no error",
    "ok",
)


def _headings(body: str) -> list[str]:
    """The `## ` headings in a document, in order, stripped."""
    return [
        line[3:].strip()
        for line in body.splitlines()
        if line.startswith("## ") and not line.startswith("###")
    ]


def _section(body: str, name: str) -> str:
    """The text under one `## ` heading, up to the next one. `""` if absent."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip() == name:
            for j, later in enumerate(lines[i + 1 :], start=i + 1):
                if later.startswith("## "):
                    return "\n".join(lines[i + 1 : j])
            return "\n".join(lines[i + 1 :])
    return ""


def _table_rows(text: str) -> list[list[str]]:
    """Markdown table rows as cell lists. The `|---|` separator is dropped."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(cells)
    return rows


def _check_sequence(path: Path, body: str) -> list[Problem]:
    """Every step names something observed as its confirmation, or none of it counts."""
    rows = _table_rows(_section(body, "Sequence"))
    if not rows:
        return [Problem(path, "Sequence has no table")]

    header, *data = rows
    try:
        column = header.index(CONFIRMATION_COLUMN)
    except ValueError:
        return [
            Problem(
                path,
                f"the Sequence table has no {CONFIRMATION_COLUMN!r} column "
                "-- SAFETY §0 makes it the load-bearing one",
            )
        ]

    problems: list[Problem] = []
    for n, row in enumerate(data, start=1):
        if column >= len(row) or not row[column]:
            problems.append(
                Problem(path, f"Sequence step {n} has no {CONFIRMATION_COLUMN!r}")
            )
            continue
        cell = row[column].lower()
        hit = next((bad for bad in NON_CONFIRMATIONS if bad in cell), None)
        if hit is not None:
            problems.append(
                Problem(
                    path,
                    f"Sequence step {n} confirms on {hit!r}. A return code is not "
                    "a confirmation (SAFETY §0) -- name what is observed",
                )
            )
    return problems


def check_plan(path: Path, root: Path | None = None) -> list[Problem]:
    """Everything wrong with one plan file. Empty means it is usable."""
    root = path.parent.parent if root is None else root
    entry, problems = read_entry(path, root=root)
    if entry is None:
        return problems

    if entry.status not in PLAN_STATUSES:
        problems.append(
            Problem(path, f"status {entry.status!r} is not one of {PLAN_STATUSES}")
        )

    subsystems = entry.meta.get("subsystems")
    if not subsystems:
        problems.append(Problem(path, "no subsystems -- nothing can dispatch on it"))
    else:
        unknown = [s for s in subsystems if s not in SUBSYSTEMS]
        if unknown:
            problems.append(
                Problem(path, f"unknown subsystems {unknown} -- known: {list(SUBSYSTEMS)}")
            )

    _, body = split_frontmatter(path.read_text(encoding="utf-8"))
    present = set(_headings(body))
    missing = [name for name in REQUIRED_SECTIONS if name not in present]
    if missing:
        problems.append(Problem(path, f"missing sections: {', '.join(missing)}"))

    if "Sequence" in present:
        problems.extend(_check_sequence(path, body))

    if "Committee verdict" in present:
        verdict = _section(body, "Committee verdict")
        if "unevaluated" not in verdict.lower() and "not evaluated" not in verdict.lower():
            problems.append(
                Problem(
                    path,
                    "Committee verdict does not say what was not evaluated. "
                    "`unevaluated` is not `cleared` (CLAUDE.md §3) -- if every "
                    "lens ran, say so",
                )
            )

    return problems


def check_all(plans_dir: Path) -> list[Problem]:
    """Every plan in a directory. Missing directory is not an error -- it is empty."""
    if not plans_dir.is_dir():
        return []
    problems: list[Problem] = []
    for path in sorted(plans_dir.glob("*.md")):
        if path.name.startswith("_"):
            continue
        problems.extend(check_plan(path, root=plans_dir.parent))
    return problems
