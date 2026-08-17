"""The `advances` rule, checked across every lens at once.

docs/05-consensus-gate.md's Verdict schema:

    advances: bool   # feasibility >= TIGHT and evidence == measured
                     #   and no hard gate below 1.0

Until 2026-08-12 all eight lenses implemented only the middle clause, so a
verdict graded INFEASIBLE whose failures were all bias-kind reported
`advances=True` -- a setting the committee had judged unusable was allowed to
move to the next step. The bug was silent, which is why it is pinned here for
every lens rather than in one module's tests.
"""

from __future__ import annotations

import importlib

import pytest

LENS_MODULES = [
    "optics",
    "detection",
    "compute",
    "trapping",
    "sample",
    "photo",
    "validity",
    "stability",
]

#: Grades at or above TIGHT, which may advance.
ADVANCING = ["ROUTINE", "COMFORTABLE", "TIGHT"]
#: Grades below TIGHT, which may not.
NOT_ADVANCING = ["HARD", "MARGINAL", "INFEASIBLE"]


def _verdict_cls(mod: str):
    return importlib.import_module(f"{mod}.gate").Verdict


def _checks(mod: str):
    return importlib.import_module(f"{mod}.checks")


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_every_lens_has_a_feasibility_field(mod):
    """trapping was the exception until grading was added there."""
    v = _verdict_cls(mod)(status="PASS")
    assert v.feasibility == "UNKNOWN"


@pytest.mark.parametrize("mod", LENS_MODULES)
@pytest.mark.parametrize("feasibility", ADVANCING)
def test_measured_and_graded_at_least_tight_advances(mod, feasibility):
    v = _verdict_cls(mod)(
        status="PASS", feasibility=feasibility, evidence="measured"
    )
    assert v.advances is True


@pytest.mark.parametrize("mod", LENS_MODULES)
@pytest.mark.parametrize("feasibility", NOT_ADVANCING)
def test_grade_below_tight_does_not_advance(mod, feasibility):
    """The clause that was missing. A bias-only failure leaves the status
    passing, so nothing else would have stopped it."""
    v = _verdict_cls(mod)(
        status="PASS", feasibility=feasibility, evidence="measured"
    )
    assert v.advances is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_ungraded_verdict_does_not_advance(mod):
    """UNKNOWN is not a grade that has earned anything."""
    v = _verdict_cls(mod)(status="PASS", feasibility="UNKNOWN", evidence="measured")
    assert v.advances is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_assumed_evidence_never_advances(mod):
    v = _verdict_cls(mod)(
        status="PASS", feasibility="ROUTINE", evidence="assumed"
    )
    assert v.advances is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_failed_status_never_advances(mod):
    """A hard gate below 1.0 makes the status FAIL, which is how docs/05's
    third clause is already satisfied."""
    v = _verdict_cls(mod)(
        status="FAIL", feasibility="ROUTINE", evidence="measured"
    )
    assert v.advances is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_blocked_status_never_advances(mod):
    v = _verdict_cls(mod)(
        status="BLOCKED", feasibility="ROUTINE", evidence="measured"
    )
    assert v.advances is False


# ------------------------------------------------- the grade helper -------


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_grade_order_is_derived_from_grades(mod):
    """GRADE_ORDER is built from GRADES so the two cannot drift apart."""
    c = _checks(mod)
    assert c.GRADE_ORDER == tuple(name for _, name in reversed(c.GRADES))


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_meets_grade_boundary_is_tight_inclusive(mod):
    c = _checks(mod)
    assert c.meets_grade("TIGHT") is True
    assert c.meets_grade("HARD") is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_meets_grade_rejects_unrecognised_grades(mod):
    c = _checks(mod)
    assert c.meets_grade("UNKNOWN") is False
    assert c.meets_grade("SPLENDID") is False


@pytest.mark.parametrize("mod", LENS_MODULES)
def test_all_lenses_share_one_grade_scale(mod):
    """Eight duplicated copies of the grade table; they must at least agree."""
    reference = _checks("optics")
    assert _checks(mod).GRADES == reference.GRADES
    assert _checks(mod).GRADE_NOTES == reference.GRADE_NOTES
