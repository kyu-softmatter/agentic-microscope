"""The addressable trap range: one source, keyed on the objective, refusing.

Two defects are held closed here, and they are the same defect at two scales.

**The value was a literal in four places.** `TRAP_HALF_RANGE_UM = 40.0` was
hardcoded in `sort_core.py`, `sort_two_species.py`, `live_dualcam_view.py` and
`trap_brightest.py` -- three of them with no comment saying which objective it
belonged to. `hardware/tweezers_drive.py` has refused an unrecorded
`trapping_range` since it was written and
`tests/test_tweezers_drive.py::test_range_check_blocked_not_passed_when_unrecorded`
holds that line; the four literals bypassed it entirely.

**And it was applied whatever objective was in place.** The ±40 um is the 100x
figure (operator, 2026-09-06). The AOD covers a wider sample field at lower
magnification, so at 40x the number is a different quantity -- and the failure
is silent in the direction that matters, because points outside the calibrated
field are clipped by the Tweez GUI with no error on either side.

The tests below are deliberately split between *the reader refuses* and *the
files do not contain the literal any more*, because either one alone can pass
while the defect is live: a reader nobody calls refuses nothing.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from optics import components  # noqa: E402

SESSION = REPO / "config" / "session"
#: Every script that decides whether a particle is reachable.
RANGE_CONSUMERS = ("sort_core.py", "sort_two_species.py",
                   "live_dualcam_view.py", "trap_brightest.py")


def _load(name: str):
    src = SESSION / name
    spec = importlib.util.spec_from_file_location(f"_t_{src.stem}", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sort_core():
    return _load("sort_core.py")


class FakeCore:
    """Just enough MMCore to answer "which objective is in place"."""

    def __init__(self, label="6-Plan Apo LmbdD0.13 100x Oil", raise_on_read=False):
        self.label, self.raise_on_read = label, raise_on_read

    def getStateLabel(self, device):
        if self.raise_on_read:
            raise RuntimeError("device not loaded")
        assert device == "Nosepiece"
        return self.label


# --------------------------------------------------------------------------
# the registry reader
# --------------------------------------------------------------------------

def test_the_100x_is_recorded_and_carries_its_evidence_tier():
    hit = components.trapping_range_um(100)
    assert hit is not None
    half_w, half_h, evidence = hit
    assert (half_w, half_h) == (40.0, 40.0)
    # `stated` and not `measured`: the operator said it, nobody has read it off
    # the GUI's own Beam Position calibration. Collapsing those two is how a
    # statement acquires provenance it did not earn.
    assert evidence == "stated"


@pytest.mark.parametrize("mag", [4, 10, 20, 40, 60])
def test_every_other_objective_returns_none_rather_than_the_100x_figure(mag):
    """The load-bearing test. A fallback here is the whole bug.

    40x is the one that matters: `active-microrheology-drive.yaml` is specified
    at 40x and its own `trapping_range` is null for exactly this reason.
    """
    assert components.trapping_range_um(mag) is None


def test_a_non_integer_magnification_is_not_guessed_at():
    assert components.trapping_range_um(1.5) is None
    assert components.trapping_range_um(63.5) is None


def test_the_table_offers_no_scaling_rule_to_be_tempted_by():
    """No `nominal` tier, so nothing can be derived and then read as recorded."""
    table = components.trapping_range_table().get("table") or {}
    tiers = {(row or {}).get("evidence") for row in table.values()}
    assert tiers <= {"stated", "measured", None}


# --------------------------------------------------------------------------
# the resolver the scripts share
# --------------------------------------------------------------------------

def test_resolver_returns_the_half_extent_at_100x(sort_core):
    assert sort_core.resolve_half_range_um(FakeCore()) == 40.0


def test_resolver_refuses_an_objective_with_no_recorded_extent(sort_core):
    with pytest.raises(SystemExit) as exc:
        sort_core.resolve_half_range_um(FakeCore("4-Apo LmbdS 40x WI"))
    msg = str(exc.value)
    assert "REFUSED" in msg and "40x" in msg
    # It must also say why deriving it is not on the table, or the next reader
    # will helpfully add the magnification ratio.
    assert "magnification ratio" in msg


def test_resolver_refuses_an_unreadable_nosepiece(sort_core):
    with pytest.raises(SystemExit):
        sort_core.resolve_half_range_um(FakeCore(raise_on_read=True))


def test_resolver_refuses_a_label_it_cannot_read_one_magnification_from(sort_core):
    with pytest.raises(SystemExit) as exc:
        sort_core.resolve_half_range_um(FakeCore("Nosepiece position 3"))
    assert "REFUSED" in str(exc.value)


# --------------------------------------------------------------------------
# the consumers actually go through it
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", RANGE_CONSUMERS)
def test_no_script_carries_the_range_as_a_module_level_literal(name):
    """A reader nobody calls refuses nothing. This is the half that checks.

    Any module-level assignment of a bare number to a range-shaped name is the
    defect returning, whatever it gets called.
    """
    tree = ast.parse((SESSION / name).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if "HALF_RANGE" in target.id or "TRAP_RANGE" in target.id:
                assert not isinstance(node.value, ast.Constant), (
                    f"{name}: {target.id} is a module-level constant again. "
                    "The addressable range belongs to the objective -- resolve "
                    "it through sort_core.resolve_half_range_um.")


def test_slot_count_follows_the_range_rather_than_being_fixed_at_nine(sort_core):
    """9 slots per species was reported as a property of the sort. It is not.

    It is `2*floor(range/pitch)+1` at the 100x's 40 um and a 10 um pitch, and
    the README's "18 beads against 43-50 detected" argument rests on it. A
    wider field is more destinations, so the count has to move.
    """
    opts = sort_core.SortOpts(slot_pitch_um=10.0)
    opts.half_range_um = 40.0
    assert len(sort_core.slot_ys(opts)) == 9
    opts.half_range_um = 78.0
    assert len(sort_core.slot_ys(opts)) == 15


@pytest.mark.parametrize("fn_name", ["slot_ys", "plan"])
def test_geometry_refuses_an_unresolved_range_instead_of_defaulting(sort_core, fn_name):
    opts = sort_core.SortOpts()
    assert opts.half_range_um is None
    args = {"slot_ys": (opts,),
            "plan": ({"red": [], "green": []}, (0.0, 0.0), 0.065, opts)}[fn_name]
    with pytest.raises(ValueError, match="half_range_um"):
        getattr(sort_core, fn_name)(*args)


def test_slot_ys_runs_centre_outward(sort_core):
    """Unrelated to the range, but it is the other half of what slot_ys promises."""
    opts = sort_core.SortOpts(slot_pitch_um=10.0)
    opts.half_range_um = 40.0
    ys = sort_core.slot_ys(opts)
    assert ys[0] == 0.0
    assert [abs(y) for y in ys] == sorted(abs(y) for y in ys)
