"""A derived column names the code that computes it, not a formula.

The failure this is built against is `2*D*t_exp/3`: the free-particle MSD blur
term applied to a trapped bead, in a markdown column, twice too large for two
rounds of an inter-repository exchange. A formula written into a JSON field
would not have caught it -- a formula string is one more number in prose, and
nothing can run it. **A dotted path either resolves to a callable or it does
not**, which is the only kind of declaration a check can act on.

So `kb/plans/<slug>.json` gains a `tables` block, and every value column of
every table in the plan has to name exactly one of:

    computed_by     module.function in this repository -- imported and called
    imported_from   a path under kb/external/ -- opened
    measured_in     a path under data/ or kb/calibrations/ -- opened
    declared_in     "facts" or "settings" -- and the values have to be there
    unbacked        nothing computes it, and it says what would

`unbacked` is the honest state and the interesting one: six of the sixteen
columns in the drag-calibration plan are unbacked, which is the finding rather
than a gap in the schema. The plan's derived tables are largely arithmetic no
code performs, and that is the soil the blur coefficient grew in.
"""

from __future__ import annotations

import json
from pathlib import Path

from knowledge.index import KB_ROOT
from knowledge.plans import check_plan
from knowledge.sidecar import sidecar_path, value_column_inventory

SECTION = "A derived table, in the same section"

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
| 8.0 | 1.86 % |

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

#: Two real callables, so a passing case is not a stub.
REAL = "sample.aberration.wall_drag_suppression"
REAL_TOO = "trapping.dynamics.corner_frequency_hz"


def write(tmp_path: Path, sidecar: dict | None) -> Path:
    plans = tmp_path / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / "a.md"
    plan.write_text(PLAN, encoding="utf-8")
    if sidecar is not None:
        sidecar_path(plan).write_text(json.dumps(sidecar), encoding="utf-8")
    return plan


def problems_for(tmp_path: Path, tables: list[dict]) -> list[str]:
    sidecar = {"plan": "2026-09-09-example", "settings": [ONE_SETTING], "tables": tables}
    return [str(p) for p in check_plan(write(tmp_path, sidecar))]


def both(blur: dict) -> list[dict]:
    """The `blur` declaration under test, plus a valid one for `h`."""
    return [
        dict(section=SECTION, column="blur", **blur),
        {"section": SECTION, "column": "h", "computed_by": REAL_TOO},
    ]


def test_an_undeclared_value_column_is_refused(tmp_path):
    """Undeclared is not skipped: a column nobody declared is one nothing checks."""
    assert any("declared nowhere" in p for p in problems_for(tmp_path, []))


def test_computed_by_must_actually_import(tmp_path):
    """The check a formula string cannot have."""
    problems = problems_for(tmp_path, both({"computed_by": "trapping.dynamics.nope"}))
    assert any("is not a callable" in p for p in problems)


def test_a_real_function_passes(tmp_path):
    assert not problems_for(tmp_path, both({"computed_by": REAL}))


def test_unbacked_must_say_what_would_back_it(tmp_path):
    """A refusal names what would resolve it, and an unbacked column is a refusal.

    Without that clause `unbacked` becomes the way to silence the check.
    """
    problems = problems_for(tmp_path, both({"unbacked": "nothing"}))
    assert any("what would back it" in p for p in problems)


def test_unbacked_with_a_remedy_passes(tmp_path):
    assert not problems_for(
        tmp_path,
        both({"unbacked": "no function computes u/3; back it with a helper in trapping/dynamics.py"}),
    )


def test_two_sources_on_one_column_is_refused(tmp_path):
    """A column with two provenances has neither."""
    problems = problems_for(
        tmp_path,
        both({"computed_by": REAL, "imported_from": "kb/external/bd/x.md"}),
    )
    assert any("declares 2 sources" in p for p in problems)


def test_a_declaration_matching_no_column_is_refused(tmp_path):
    """How a renamed column stops being checked without anybody noticing."""
    tables = both({"computed_by": REAL})
    tables.append({"section": SECTION, "column": "gone", "computed_by": REAL})
    assert any("the plan does not have" in p for p in problems_for(tmp_path, tables))


def test_declared_in_checks_the_values_are_there(tmp_path):
    """Checking only the word would make it the weakest of the five kinds."""
    problems = problems_for(tmp_path, both({"declared_in": "settings"}))
    assert any("appear in no entry" in p for p in problems)


def test_imported_from_must_be_under_kb_external(tmp_path):
    """`kb/calibrations/` means measured here; an import may not claim it."""
    problems = problems_for(
        tmp_path, both({"imported_from": "kb/calibrations/camera-readout.yaml"})
    )
    assert any("is not under" in p for p in problems)


def test_a_label_column_is_not_a_value_column():
    """`| 1 optics |` and a sequence step's `| 9a |` are labels, not values.

    Demanding a provenance for a row number would be noise, and noise is what
    hides the columns where provenance matters.
    """
    found = {column for _, column, _ in value_column_inventory(PLAN)}
    assert {"h", "blur"} <= found
    assert "Lens" not in found and "#" not in found


def test_the_committed_plan_declares_every_column():
    """The repository's own, so the rule is exercised on the real thing."""
    plan = KB_ROOT / "plans" / "2026-09-15-drag-calibration-stiffness-vs-size.md"
    assert not check_plan(plan, root=KB_ROOT)


def test_the_committed_sidecar_has_unbacked_columns_and_says_so():
    """Six of sixteen, and the blur column is one of them.

    Pinned because it is the finding: the plan's derived tables are largely
    arithmetic no code performs. If that number falls, someone wrote the
    functions -- which is the point -- and this test should be updated to say
    so rather than deleted.
    """
    sidecar = json.loads(
        (KB_ROOT / "plans" / "2026-09-15-drag-calibration-stiffness-vs-size.json")
        .read_text(encoding="utf-8")
    )
    unbacked = [entry for entry in sidecar["tables"] if "unbacked" in entry]
    assert len(unbacked) == 6
    assert any("u/3" in entry["unbacked"] for entry in unbacked)
