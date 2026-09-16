"""Tests for `designer/questions.py` -- the R1 gaps as one ordered list.

The module adds no facts. Everything here is therefore about the ORDERING and
about where it is read from, because an ordering this module chose rather than
derived would be its own opinion dressed as the pipeline's.
"""

from __future__ import annotations

import textwrap

import pytest

from designer import brief as brief_mod
from designer import questions as questions_mod
from designer import run as run_mod
from designer.questions import CONSTRUCTS, CONSUMED, CONVENES

BRIEF = "config/briefs/active-microrheology.yaml"


@pytest.fixture
def asked():
    result = run_mod.run(brief_mod.load(BRIEF))
    return result, [q for q in questions_mod.questions(result) if q.answerable]


def test_only_r1_is_on_the_list(asked):
    """R1 is the operator's, in conversation. R2 is a measurement and R3 is
    nobody's, so neither belongs under a heading that says "answer these"."""
    result, questions = asked

    assert all(q.rank == "R1" for q in questions)
    off = [q for q in questions_mod.questions(result) if not q.answerable]
    assert {q.rank for q in off} == {"R2", "R3"}


def test_a_field_that_unblocks_a_whole_lens_is_asked_first(asked):
    """One answer that turns a silent lens into a speaking one is worth more
    than one that moves one margin -- and `NotConstructible` is the strongest
    signal available, because such a lens emits NO `missing.*` code at all."""
    _, questions = asked
    first = [q for q in questions if q.tier == CONSTRUCTS]

    assert {q.field for q in first} == {"exposure_ms", "trap_dial_percent"}
    assert questions[0].tier == CONSTRUCTS
    for q in first:
        assert "cannot be built" in q.unblocks


def test_the_two_sides_can_call_one_fact_two_names(asked):
    """The brief's gap is `trap_dial_percent`; `build.py`'s NotConstructible
    says `dial_percent`. A refiner harvesting the builder's name would ask for
    one and the brief would answer the other, and nothing would notice they
    had met -- so both names travel on the Question."""
    _, questions = asked
    dial = next(q for q in questions if q.field == "trap_dial_percent")

    assert dial.also_called == ("dial_percent",)


def test_the_convening_tier_is_read_off_the_seat_not_its_prose(asked):
    """`Seat.decided_by` exists because the first version of this matched
    `gap.field` against `seat.why` and missed `acquisition_duration_s`: the
    prose says "no acquisition duration", so neither the field nor any
    underscore substitution of it appears in the sentence."""
    result, questions = asked
    duration = next(q for q in questions if q.field == "acquisition_duration_s")

    assert duration.tier == CONVENES
    assert result.seats["stability"].decided_by == "acquisition_duration_s"
    assert "lens stability" in duration.unblocks


def test_the_rest_are_ordered_by_their_own_consumed_by(asked):
    """A declaration, not an inference: the count is the brief's own."""
    _, questions = asked
    rest = [q for q in questions if q.tier == CONSUMED]

    counts = [len(q.consumed_by) for q in rest]
    assert counts == sorted(counts, reverse=True)
    assert rest[0].field == "roi_height_px", "five consumers"


def test_the_gaps_with_no_instruction_are_reported_and_not_filled(asked):
    """CLAUDE.md §3: a refusal names what would resolve it, and a BLOCKED with
    no fix instruction is a bug. The rule is enforced in the gates' `missing.*`
    findings and NOT in the brief's own gap list, so a gap can be a question
    with no way to answer it. What would resolve each is the operator's to say
    (rule 2), so this reports rather than proposes."""
    result, questions = asked
    blank = questions_mod.without_an_action(result)

    assert blank, "the active brief has some"
    assert all(q.action is None for q in blank)
    assert all(q.rank == "R1" for q in blank)
    #: And the count is a measure of the brief, so it is worth being exact:
    #: TEN of twenty on the active brief as of 2026-09-16. Half the questions
    #: it asks have no instruction for answering them.
    assert len(blank) == 10
    assert len(questions) == 20


def test_a_brief_with_no_gaps_asks_nothing(tmp_path):
    """The empty case is not a special case -- it falls out of there being no
    gaps to order."""
    path = tmp_path / "b.yaml"
    path.write_text(textwrap.dedent("""
        meta: {id: t, date: 2026-09-16}
        facts:
          lens_1_optics:
            detector: {value: Kinetix22, source: "test"}
        gaps: []
    """), encoding="utf-8")
    result = run_mod.run(brief_mod.load(path))

    assert questions_mod.questions(result) == []
    assert questions_mod.without_an_action(result) == []
