"""The structured half of a plan, and the rule that keeps the prose honest.

A plan is prose because the operator reads it. That makes it the one artefact
where a physical number can live with nothing checking it, and CLAUDE.md rule 2
-- *never originate a physical number* -- had no mechanical enforcement at all
until this module. Two failures in one session paid for it:

- **The motion-blur coefficient.** `2*D*t_exp/3` is the free-particle MSD term;
  a trapped bead's is `u/3`. Every entry of one table column was twice too large
  for two rounds of an inter-repository exchange, and the number reached the
  other agent as this instrument's own arithmetic. No gate read it, because it
  was in a markdown table.
- **Three citations that resolved to nothing**, one of them the source of the
  ROI, the exposure and the frame rate. `plans._check_citations` now refuses
  those.

So: `kb/plans/<slug>.json` beside `kb/plans/<slug>.md`, and **the structured
block is authoritative while the prose cites it**. The check is narrow on
purpose -- see `check` for exactly what it does and does not cover.

    python -m knowledge.cli plan-sidecar init kb/plans/<slug>.md
    python -m knowledge.cli plan-check              # enforces it where it exists

A sidecar is **optional**. A plan without one is checked exactly as before: this
is not retroactive, because the entries that predate it were written under rules
that did not ask for it, and a backfill would put numbers in a structured block
without anybody re-deriving them -- which is the same act that produced the blur
coefficient.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .index import Problem
from .plans import _section

#: The section whose numbers a hardware skill acts on. This is the enforced
#: scope, and it is narrower than "every number in the plan" for a reason
#: given in `check`.
SETTINGS_SECTION = "Proposed setting + rationale"

#: The column of that table carrying the value. Restricting the rule to it is
#: what keeps dates and citation text in the neighbouring columns from being
#: read as physical numbers.
VALUE_COLUMN = "Value"

#: How a number came to exist. The same vocabulary the bridge protocol uses, so
#: an exported ask does not have to translate it -- `simulated` and
#: `round_trip` exist precisely because a number can come back from another
#: repository and must not then read as locally measured.
EVIDENCE = ("measured", "handbook", "computed", "assumed", "simulated", "round_trip")

#: What a number is *for*. `fact` is the operator's or the KB's and may never be
#: originated in a plan; `setting` is the committee's to propose; `threshold` is
#: what a check refuses against.
ROLES = ("fact", "setting", "threshold")

#: Imported numbers live here, and a threshold may not come from one: a gate
#: clearing against a simulated ceiling emits a margin that reads as measured,
#: which is the disease CLAUDE.md rule 3 already names.
EXTERNAL_PREFIX = "kb/external/"

#: Numeric literals in a table cell. Deliberately does not match a bare `x` in
#: `1x1` or a unit -- only the numbers.
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

#: Backticked spans are stripped before numbers are read. A digit inside one is
#: part of a *name* -- `100x-Oil` is a key in `data/objectives.yaml` and
#: `Kinetix_red` is a camera preset -- and a name is not a number this plan
#: originated. The bolded `**0.06453 µm/px**` beside it is a number, and stays.
_CODE = re.compile(r"`[^`]*`")

#: Tolerance for calling a prose number and a structured one the same. Relative,
#: because the values here span 0.15 to 3200.
_REL_TOL = 1e-9


def sidecar_path(plan_path: Path) -> Path:
    """`kb/plans/<slug>.json` for `kb/plans/<slug>.md`.

    Same slug, deliberately: one run, one name, two readers. A `.json` in
    `kb/plans/` is invisible to `knowledge.index`, which globs `*.md`.
    """
    return plan_path.with_suffix(".json")


def numbers_in(text: str) -> list[str]:
    """Numeric literals in a table cell, as written, ignoring names."""
    return _NUMBER.findall(_CODE.sub(" ", text))


def tables(text: str) -> list[list[list[str]]]:
    """The markdown tables in a block of text, each as its own list of rows.

    `plans._table_rows` collects every pipe-line in its input into one list,
    which is right for the sequence table and wrong here: a `## ` section of
    this plan contains several tables, and treating the second table's rows as
    continuations of the first reads its column 1 as the first table's `Value`.
    That is not a hypothetical -- it is what this module did before the tables
    were split, and it silently widened the rule to every table in the section.
    """
    out: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= set("-: ") for cell in cells):
                continue
            current.append(cells)
            continue
        if current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def _settings_table(body: str) -> list[list[str]] | None:
    """The one table in the settings section that has a `Value` column."""
    for rows in tables(_section(body, SETTINGS_SECTION)):
        if rows and VALUE_COLUMN in rows[0]:
            return rows
    return None


def _values(sidecar: dict) -> list[float]:
    out: list[float] = []
    for group in ("facts", "settings"):
        for entry in sidecar.get(group, []):
            value = entry.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(float(value))
    return out


def _covers(value: float, declared: list[float]) -> bool:
    return any(
        abs(value - other) <= _REL_TOL * max(abs(value), abs(other), 1.0)
        for other in declared
    )


def _check_shape(path: Path, sidecar: dict, plan_id: str) -> list[Problem]:
    problems: list[Problem] = []

    if sidecar.get("plan") != plan_id:
        problems.append(
            Problem(
                path,
                f"sidecar says plan {sidecar.get('plan')!r} but sits beside "
                f"{plan_id!r} -- a sidecar describing another run is worse than none",
            )
        )

    if not sidecar.get("facts") and not sidecar.get("settings"):
        problems.append(Problem(path, "sidecar has neither `facts` nor `settings`"))

    for group in ("facts", "settings"):
        for i, entry in enumerate(sidecar.get(group, [])):
            where = f"{group}[{i}]"
            symbol = entry.get("symbol", where)

            for key in ("symbol", "value", "unit", "source", "evidence", "role"):
                if key not in entry:
                    problems.append(Problem(path, f"{where} has no {key!r}"))

            evidence = entry.get("evidence")
            if evidence is not None and evidence not in EVIDENCE:
                problems.append(
                    Problem(path, f"{symbol}: evidence {evidence!r} is not one of {EVIDENCE}")
                )

            role = entry.get("role")
            if role is not None and role not in ROLES:
                problems.append(
                    Problem(path, f"{symbol}: role {role!r} is not one of {ROLES}")
                )

            source = str(entry.get("source", ""))
            if role == "threshold" and EXTERNAL_PREFIX in source:
                problems.append(
                    Problem(
                        path,
                        f"{symbol} is a threshold sourced from {EXTERNAL_PREFIX} "
                        "-- an imported number may motivate a design and may not "
                        "be what a check clears against, because the margin then "
                        "reads as measured (CLAUDE.md rule 3). Cite it as a "
                        "`fact` and state the threshold this instrument uses",
                    )
                )

            if role == "fact" and evidence == "assumed" and "BLOCKED" not in source:
                problems.append(
                    Problem(
                        path,
                        f"{symbol} is an assumed `fact` whose source does not say "
                        "what would resolve it. A missing input is BLOCKED, and a "
                        "refusal names what fixes it (CLAUDE.md rule 2)",
                    )
                )

    return problems


def check(plan_path: Path, plan_id: str, body: str) -> list[Problem]:
    """Everything wrong with a plan's sidecar, and with the prose against it.

    **What it enforces.** Where a sidecar exists: its own shape, that no
    `threshold` is sourced from `kb/external/`, that an assumed `fact` names
    what would resolve it, and that **every number in the `Value` column of
    "Proposed setting + rationale" appears in the structured block**. That
    column is what a hardware skill acts on, so a number there with no
    structured home is a setting nobody can trace.

    **What it does not enforce, and this matters.** Numbers in the plan's
    *derived* tables -- the height ladder, the error budget, the imported
    verdicts -- are not covered. The blur coefficient that motivated this
    module lived in one of those, so **the rule as built would not have caught
    it.** Catching that class needs the declaration to be per column and to
    carry the formula (`u/3, u = t_exp/tau_k`), which is also the artefact that
    would have made the coefficient reviewable. That is the next step and it is
    named here rather than implied, because a check whose limits are not
    written down gets read as covering more than it does.
    """
    path = sidecar_path(plan_path)
    if not path.exists():
        return []

    try:
        sidecar = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Problem(path, f"is not readable JSON: {exc}")]
    if not isinstance(sidecar, dict):
        return [Problem(path, "is not a JSON object")]

    problems = _check_shape(path, sidecar, plan_id)
    declared = _values(sidecar)

    rows = _settings_table(body)
    if rows is None:
        problems.append(
            Problem(
                plan_path,
                f"{SETTINGS_SECTION!r} has no table with a {VALUE_COLUMN!r} column, "
                "so its settings cannot be checked against the sidecar",
            )
        )
        return problems

    header, *data = rows
    column = header.index(VALUE_COLUMN)

    for row in data:
        if column >= len(row):
            continue
        for literal in numbers_in(row[column]):
            if not _covers(float(literal), declared):
                problems.append(
                    Problem(
                        plan_path,
                        f"{literal} appears in the {VALUE_COLUMN} column but in no "
                        "sidecar entry. The structured block is authoritative and "
                        "the prose cites it -- a number that exists only in prose "
                        "is one nothing checks (CLAUDE.md rule 2)",
                    )
                )

    return problems


def scaffold(plan_path: Path, plan_id: str, body: str) -> dict:
    """A first sidecar, with one entry per number in the settings table.

    Every field a person has to fill is present and **empty**, because a
    scaffold that guesses a unit or an evidence class is a scaffold that gets
    committed unread. `value` is the only thing filled in, since it is the one
    thing that can be read off the prose without inventing anything.
    """
    rows = _settings_table(body)
    settings: list[dict] = []
    seen: set[float] = set()

    if rows is not None:
        header, *data = rows
        column = header.index(VALUE_COLUMN)
        axis = 0
        for row in data:
            if column >= len(row):
                continue
            label = row[axis] if axis < len(row) else ""
            for literal in numbers_in(row[column]):
                value = float(literal)
                if value in seen:
                    continue
                seen.add(value)
                settings.append(
                    {
                        "symbol": "",
                        "value": int(value) if value.is_integer() else value,
                        "unit": "",
                        "source": "",
                        "evidence": "",
                        "role": "setting",
                        "_from_prose": label,
                    }
                )

    return {
        "plan": plan_id,
        "_note": (
            "The structured block is authoritative; the prose cites it. Fill every "
            "empty field -- `evidence` must be one of "
            f"{list(EVIDENCE)} and `role` one of {list(ROLES)}. Delete `_from_prose` "
            "once the row is real; it records which table row the number was read "
            "off, and it is a scaffolding note rather than provenance."
        ),
        "facts": [],
        "settings": settings,
    }
