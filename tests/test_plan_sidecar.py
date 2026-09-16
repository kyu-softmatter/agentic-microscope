"""The structured half of a plan, and what it refuses.

`kb/plans/<slug>.json` exists because a plan is prose, and prose is where a
physical number can live with nothing checking it. CLAUDE.md rule 2 -- never
originate a physical number -- had no mechanical enforcement until this, and
two failures in one session paid for it: a motion-blur coefficient that was
twice too large for two rounds of an inter-repository exchange, and three
citations that resolved to entries on another branch.

Each test names the failure it stands for. What the check does **not** cover is
in `knowledge.sidecar.check`'s docstring and is deliberate: the derived tables
are not in scope yet, which means the blur coefficient itself would still get
through. That limit is tested here too, so it cannot quietly become untrue.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.index import KB_ROOT
from knowledge.plans import check_plan
from knowledge.sidecar import scaffold, sidecar_path, tables

PLAN = """---
id: 2026-09-09-example
question: "Does the example plan pass its own check"
date: 2026-09-09
status: planned
subsystems: [microscope]
---

# 2026-09-09 · Example

## Request
Track one bead.

## Proposed setting + rationale

| Axis | Value | Source |
|---|---|---|
| Exposure | **20 ms** | `data/detectors.yaml` |

### A derived table, in the same section

| h | blur |
|---|---|
| 3.0 | 1.21 % |

## Committee verdict
| Lens | Verdict |
|---|---|
| 1 optics | ROUTINE |

**Not evaluated:** lens 7, no trap in this run.

## Preconditions
- [ ] objective is 100x Oil — *checked by:* `microscope.state()`

## Sequence
| # | Subsystem | Action | Flag required | Confirmed by |
|---:|---|---|---|---|
| 1 | microscope | set exposure | — | the value read back |

## Stop conditions
- Focus lost: stop acquiring, leave the stage where it is.
"""

ONE_SETTING = {
    "symbol": "t_exp",
    "value": 20,
    "unit": "ms",
    "source": "data/detectors.yaml",
    "evidence": "handbook",
    "role": "setting",
}


def write(tmp_path: Path, sidecar: dict | None, text: str = PLAN) -> Path:
    plans = tmp_path / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / "a.md"
    plan.write_text(text, encoding="utf-8")
    if sidecar is not None:
        sidecar_path(plan).write_text(json.dumps(sidecar), encoding="utf-8")
    return plan


def problems_for(tmp_path: Path, sidecar: dict | None, text: str = PLAN) -> list[str]:
    return [str(p) for p in check_plan(write(tmp_path, sidecar, text))]


# --------------------------------------------------------------------------
# the rule
# --------------------------------------------------------------------------


def test_a_plan_with_no_sidecar_is_checked_exactly_as_before(tmp_path):
    """Not retroactive, on purpose.

    Backfilling a sidecar from prose would put numbers in a structured block
    with nobody re-deriving them -- which is the act that produced the blur
    coefficient in the first place.
    """
    assert not problems_for(tmp_path, None)


def test_a_setting_that_exists_only_in_prose_is_refused(tmp_path):
    """The failure this module exists for, in its narrowest form."""
    sidecar = {"plan": "2026-09-09-example", "settings": [dict(ONE_SETTING, value=10)]}
    assert any("appears in the Value column" in p for p in problems_for(tmp_path, sidecar))


def test_a_setting_declared_in_the_sidecar_passes(tmp_path):
    sidecar = {"plan": "2026-09-09-example", "settings": [ONE_SETTING]}
    assert not problems_for(tmp_path, sidecar)


def test_a_number_inside_backticks_is_a_name_not_a_number(tmp_path):
    """`100x-Oil` is a key in data/objectives.yaml, not a value this plan set.

    Without this the rule demands a sidecar entry for the 100 in an objective's
    name, the 16 in a preset, and the 1 in `1x1` -- which trains the reader to
    add entries that mean nothing, and an inventory of meaningless entries is
    how a real omission stops being visible.
    """
    text = PLAN.replace("| Exposure | **20 ms** |", "| Objective | `100x-Oil` |")
    sidecar = {"plan": "2026-09-09-example", "settings": [ONE_SETTING]}
    assert not problems_for(tmp_path, sidecar, text)


# --------------------------------------------------------------------------
# what the sidecar itself refuses
# --------------------------------------------------------------------------


def test_a_threshold_sourced_from_an_import_is_refused(tmp_path):
    """CLAUDE.md rule 3, held where provenance exists.

    A gate clearing against a simulated ceiling emits a margin that reads as
    measured. The gates cannot catch this -- they receive bare floats -- so the
    plan boundary is the only place the origin of a number is still known.
    """
    sidecar = {
        "plan": "2026-09-09-example",
        "settings": [
            dict(
                ONE_SETTING,
                symbol="epsilon_max",
                role="threshold",
                source="kb/external/bd/trap-stiffness-recovery.r8.md",
            )
        ],
    }
    assert any("is a threshold sourced from" in p for p in problems_for(tmp_path, sidecar))


def test_an_assumed_fact_must_say_what_would_resolve_it(tmp_path):
    """A refusal names the missing input, or it is a bug (CLAUDE.md rule 2)."""
    sidecar = {
        "plan": "2026-09-09-example",
        "facts": [dict(ONE_SETTING, symbol="T", role="fact", evidence="assumed")],
        "settings": [ONE_SETTING],
    }
    assert any("does not say" in p for p in problems_for(tmp_path, sidecar))


def test_an_unknown_evidence_class_is_refused(tmp_path):
    sidecar = {
        "plan": "2026-09-09-example",
        "settings": [dict(ONE_SETTING, evidence="probably")],
    }
    assert any("is not one of" in p for p in problems_for(tmp_path, sidecar))


def test_a_sidecar_for_another_plan_is_refused(tmp_path):
    """Worse than no sidecar: it reads as provenance for numbers it never saw."""
    sidecar = {"plan": "2026-09-10-something-else", "settings": [ONE_SETTING]}
    assert any("sits beside" in p for p in problems_for(tmp_path, sidecar))


def test_unreadable_json_is_reported_not_crashed(tmp_path):
    plan = write(tmp_path, None)
    sidecar_path(plan).write_text("{not json", encoding="utf-8")
    assert any("not readable JSON" in str(p) for p in check_plan(plan))


# --------------------------------------------------------------------------
# the parser, and the limit that is not a bug
# --------------------------------------------------------------------------


def test_tables_are_split_rather_than_concatenated():
    """The regression this module shipped with, for one iteration.

    `plans._table_rows` returns every pipe-line in its input as one table, so a
    section holding two tables had the second one's column 1 read as the first
    one's `Value`. That silently widened the rule from the settings table to
    every table in the section.
    """
    text = "| Axis | Value |\n|---|---|\n| a | 1 |\n\nprose\n\n| h | blur |\n|---|---|\n| 3.0 | 1.21 |\n"
    assert [len(rows) for rows in tables(text)] == [2, 2]


def test_a_derived_table_is_not_covered_and_that_is_stated(tmp_path):
    """The blur coefficient would still get through, and the docstring says so.

    `1.21 %` sits in a derived table inside the settings section and no sidecar
    entry declares it. Catching that class needs the declaration to be per
    column and to carry the formula -- `u/3, u = t_exp/tau_k` -- which is also
    the artefact that would have made the wrong coefficient reviewable. Until
    that exists this test pins the limit, so nobody reads the check as covering
    more than it does.
    """
    sidecar = {"plan": "2026-09-09-example", "settings": [ONE_SETTING]}
    assert not problems_for(tmp_path, sidecar)


def test_scaffold_fills_the_value_and_nothing_else(tmp_path):
    """A scaffold that guesses a unit is a scaffold that gets committed unread."""
    out = scaffold(write(tmp_path, None), "2026-09-09-example", PLAN)
    assert [entry["value"] for entry in out["settings"]] == [20]
    entry = out["settings"][0]
    assert entry["symbol"] == "" and entry["unit"] == "" and entry["evidence"] == ""


# --------------------------------------------------------------------------
# the repository's own
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plan",
    sorted(p for p in (KB_ROOT / "plans").glob("*.md") if not p.name.startswith("_")),
    ids=lambda p: p.stem,
)
def test_a_committed_sidecar_agrees_with_its_plan(plan):
    """Every plan that has a sidecar passes; a plan without one is untouched."""
    assert not check_plan(plan, root=KB_ROOT)
