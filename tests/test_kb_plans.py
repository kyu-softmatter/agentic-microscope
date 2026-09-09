"""A `kb/plans/` entry is what a hardware skill reads instead of the conversation.

That is what makes its shape worth a guard. Stage 5 of docs/05 §6 exists so that
stage 6 has something to act on that is not chat history, and a skill that
misreads the plan does not produce a bad document -- it moves a stage or steers
a trapping laser on a misreading.

Two of these tests are the repository's own rules rather than formatting:

- **`unevaluated` is not `cleared`** (CLAUDE.md §3). A plan that lists six
  passing lenses and says nothing about lens 7 reads as though the trap was
  checked. It was not convened.
- **A return code is not a confirmation** (SAFETY §0). Six wrong tweezers states
  and success are the same byte, so a plan that writes "returns 0" in the
  confirmation column has confirmed nothing, and is refused here rather than at
  the instrument.

`kb/plans/` is empty today. These tests are written before the first plan on
purpose: the shape is cheap to hold from the start and expensive to impose on
entries that already exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hardware.orchestrator import SUBSYSTEMS
from knowledge.index import KB_ROOT
from knowledge.plans import (
    NON_CONFIRMATIONS,
    PLAN_STATUSES,
    REQUIRED_SECTIONS,
    check_all,
    check_plan,
)

TEMPLATE = KB_ROOT / "plans" / "_template.md"

GOOD = """---
id: 2026-09-09-example
question: "Does the example plan pass its own check"
date: 2026-09-09
status: planned
subsystems: [microscope, piezo]
---

# 2026-09-09 · Example

## Request
Track one bead.

## Proposed setting + rationale
100x Oil, 1x1, 20 ms.

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
| 1 | piezo | centre at mid-travel | `--unlock` | `get_position_um` readback |

## Stop conditions
- Focus lost: stop acquiring, leave the stage where it is.
"""


def plan(tmp_path: Path, text: str, name: str = "a.md") -> Path:
    path = tmp_path / "plans"
    path.mkdir(parents=True, exist_ok=True)
    target = path / name
    target.write_text(text, encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# the template, and the repository's own kb/plans/
# --------------------------------------------------------------------------


def test_the_template_exists_and_is_not_indexed():
    """`_template.md` is the form to copy, not an entry -- knowledge.index skips it."""
    assert TEMPLATE.is_file()
    from knowledge.index import EXCLUDED_NAMES

    assert TEMPLATE.name in EXCLUDED_NAMES


def test_the_template_carries_every_required_section():
    """A template missing a section is how the section stops being written."""
    text = TEMPLATE.read_text(encoding="utf-8")
    missing = [name for name in REQUIRED_SECTIONS if f"## {name}" not in text]
    assert not missing, f"the template is missing: {missing}"


def test_every_committed_plan_is_usable():
    """Empty today. This is the test that starts mattering with the first plan."""
    problems = check_all(KB_ROOT / "plans")
    assert not problems, "\n".join(str(problem) for problem in problems)


# --------------------------------------------------------------------------
# the mechanism
# --------------------------------------------------------------------------


def test_a_well_formed_plan_passes(tmp_path):
    assert not check_plan(plan(tmp_path, GOOD))


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_a_missing_section_is_reported(tmp_path, section):
    text = GOOD.replace(f"## {section}", f"## Not {section}")
    problems = check_plan(plan(tmp_path, text))
    assert any(section in str(problem) for problem in problems)


def test_an_unknown_subsystem_is_refused(tmp_path):
    """The names come from hardware.orchestrator, so a plan cannot invent one."""
    text = GOOD.replace("[microscope, piezo]", "[microscope, confocal]")
    problems = check_plan(plan(tmp_path, text))
    assert any("confocal" in str(problem) for problem in problems)
    assert all(name in SUBSYSTEMS for name in ("microscope", "tweezers", "piezo"))


def test_a_plan_with_no_subsystem_cannot_dispatch(tmp_path):
    text = GOOD.replace("subsystems: [microscope, piezo]", "subsystems: []")
    problems = check_plan(plan(tmp_path, text))
    assert any("nothing can dispatch" in str(problem) for problem in problems)


def test_a_status_outside_the_life_cycle_is_refused(tmp_path):
    text = GOOD.replace("status: planned", "status: probably-fine")
    problems = check_plan(plan(tmp_path, text))
    assert any("probably-fine" in str(problem) for problem in problems)
    assert "planned" in PLAN_STATUSES


def test_a_verdict_silent_on_what_was_not_evaluated_is_refused(tmp_path):
    """Six passing lenses and no mention of lens 7 reads as though it passed."""
    text = GOOD.replace("**Not evaluated:** lens 7, no trap in this run.", "")
    problems = check_plan(plan(tmp_path, text))
    assert any("not evaluated" in str(problem).lower() for problem in problems)


@pytest.mark.parametrize("phrase", NON_CONFIRMATIONS)
def test_a_return_code_is_not_a_confirmation(tmp_path, phrase):
    """SAFETY §0, held at the plan rather than at the instrument."""
    text = GOOD.replace("`get_position_um` readback", phrase)
    problems = check_plan(plan(tmp_path, text))
    assert any("not a confirmation" in str(problem) for problem in problems)


def test_an_empty_confirmation_is_refused(tmp_path):
    text = GOOD.replace("| `--unlock` | `get_position_um` readback |", "| `--unlock` |  |")
    problems = check_plan(plan(tmp_path, text))
    assert any("Confirmed by" in str(problem) for problem in problems)


def test_a_sequence_without_the_column_is_refused(tmp_path):
    text = GOOD.replace("| Flag required | Confirmed by |", "| Flag required |")
    problems = check_plan(plan(tmp_path, text))
    assert any("Confirmed by" in str(problem) for problem in problems)


def test_a_sequence_with_no_table_is_refused(tmp_path):
    text = GOOD.replace(
        "| # | Subsystem | Action | Flag required | Confirmed by |\n"
        "|---:|---|---|---|---|\n"
        "| 1 | piezo | centre at mid-travel | `--unlock` | `get_position_um` readback |",
        "centre the piezo, then run",
    )
    problems = check_plan(plan(tmp_path, text))
    assert any("no table" in str(problem) for problem in problems)


def test_a_plan_with_no_frontmatter_is_reported_not_crashed(tmp_path):
    problems = check_plan(plan(tmp_path, "# just a title\n"))
    assert any("frontmatter" in str(problem) for problem in problems)


def test_underscore_files_are_not_checked_as_plans(tmp_path):
    """`_template.md` is the form, and the form has placeholders where values go."""
    plan(tmp_path, "# not a plan\n", name="_template.md")
    assert not check_all(tmp_path / "plans")


def test_a_missing_plans_directory_is_empty_not_an_error(tmp_path):
    assert check_all(tmp_path / "nothing-here") == []
