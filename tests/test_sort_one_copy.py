"""`sort_two_species.py` is a front end for `sort_core.py`, not a second copy.

`sort_core.py`'s own docstring states the rule -- *"The logic lives here so
there is one copy"* -- and until 2026-09-06 the CLI violated it: it carried its
own `detect`, `blue_to_red`, `px_to_trap_um`, `trap_um_to_px`, `path_is_clear`
and `min_separation_during_move`, plus its own `LINES`, `SPECIES`,
`BLUE_TO_RED_PX` and `TRAP_HALF_RANGE_UM`.

**The copies had already drifted, and the direction is the interesting part.**
All six were numerically identical over 20 000 random cases -- the only
difference was `min_separation_during_move` at up to 1.1e-13 px, which is
`x**2` against `x*x` in the last bit against a 6 um collision threshold. But
four of them carried *fuller docstrings in the CLI than in the shared module*.
So the divergence was live and running in documentation rather than behaviour,
which is precisely the state in which the next divergence goes unnoticed. The
better documentation was moved into `sort_core.py`; the copies were deleted.

This file is the guard. It does not check that the two agree -- agreement is
what a copy is good at right up until it is not. It checks there is only one.
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

SESSION = REPO / "config" / "session"
CORE = SESSION / "sort_core.py"
CLI = SESSION / "sort_two_species.py"

#: The geometry and detection shared by every caller of the sort.
SHARED_FUNCS = ("detect", "blue_to_red", "px_to_trap_um", "trap_um_to_px",
                "path_is_clear", "min_separation_during_move")
SHARED_CONSTS = ("LINES", "SPECIES", "BLUE_TO_RED_PX")


def _top_level(path: Path):
    """Module-level function and assignment names, by kind."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs, consts = set(), set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    consts.add(target.id)
    return funcs, consts


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"_t_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# there is one definition
# --------------------------------------------------------------------------

def test_the_shared_logic_is_defined_in_sort_core():
    funcs, consts = _top_level(CORE)
    assert set(SHARED_FUNCS) <= funcs
    assert set(SHARED_CONSTS) <= consts


@pytest.mark.parametrize("name", SHARED_FUNCS)
def test_the_cli_does_not_redefine_a_shared_function(name):
    funcs, _ = _top_level(CLI)
    assert name not in funcs, (
        f"sort_two_species.py defines {name}() again. sort_core.py is the one "
        "copy -- import it. A fix applied to one of two copies reaches one of "
        "two callers, and the CLI and the live view are different callers.")


def test_the_cli_binds_the_shared_names_from_sort_core():
    """Not just absent -- actually pointing at the shared module's objects."""
    cli = _load(CLI)
    for name in SHARED_FUNCS:
        fn = getattr(cli, name)
        assert fn.__module__ == "_sort_core", (
            f"{name} in sort_two_species.py resolves to {fn.__module__!r}, "
            "not the loaded sort_core module")
    core = cli._CORE
    for name in SHARED_CONSTS:
        assert getattr(cli, name) is getattr(core, name)


def test_the_cli_still_owns_its_own_entry_point():
    """Consolidation must not have turned the front end into a second core."""
    funcs, consts = _top_level(CLI)
    assert "main" in funcs
    assert "DEFAULT_CFG" in consts
    # and it must not have grown the orchestration back
    assert "sort_once" not in funcs and "sort_until_full" not in funcs


# --------------------------------------------------------------------------
# the falsified statistic is gone
# --------------------------------------------------------------------------

def test_the_falsified_rms_test_is_not_lying_around():
    """`rms_nm` was dead code implementing a test measured wrong 5 times of 5.

    A bead's RMS excursion over 1.5 s called four held beads free and one
    unheld bead held on 2026-09-04, because a bead stuck to the coverslip sits
    as still as a trapped one and a bead just trapped is still travelling into
    the well. No threshold fixes it -- the statistic does not separate the
    populations. What does is moving the trap and seeing whether the bead comes
    (98.6-99.8 % follow against 2.9 %).

    It was defined and never called, which is the worst state to leave it in:
    available to anyone who greps for a held-bead test, with nothing at the
    call site to warn them.
    """
    for path in (CLI, CORE):
        funcs, _ = _top_level(path)
        assert "rms_nm" not in funcs, (
            f"{path.name} defines rms_nm() again. Excursion does not separate "
            "held from stuck -- measure by moving the trap instead.")


# --------------------------------------------------------------------------
# behaviour, so the guard above is not the only thing standing
# --------------------------------------------------------------------------

def test_min_separation_finds_a_midpoint_approach_two_endpoints_would_miss():
    """The case the closed form exists for, and a sampled check walks past."""
    core = _load(CORE)
    # Two beads swapping sides: far apart at both ends, crossing in the middle.
    d, s = core.min_separation_during_move((-50.0, 0.0), (50.0, 0.0),
                                           (50.0, 0.0), (-50.0, 0.0))
    assert d == pytest.approx(0.0, abs=1e-9)
    assert s == pytest.approx(0.5)


def test_min_separation_handles_parallel_equal_length_moves():
    core = _load(CORE)
    d, s = core.min_separation_during_move((0.0, 0.0), (10.0, 0.0),
                                           (0.0, 8.0), (10.0, 8.0))
    assert d == pytest.approx(8.0)
    assert s == 0.0


def test_path_is_clear_ignores_obstacles_sitting_at_either_endpoint():
    """The cargo is at one end and the destination's occupant is not ours."""
    core = _load(CORE)
    a, b = (0.0, 0.0), (100.0, 0.0)
    at_ends = [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}]
    assert core.path_is_clear(a, b, at_ends, clear_px=10.0) == (True, None)
    midway = at_ends + [{"x": 50.0, "y": 3.0}]
    ok, worst = core.path_is_clear(a, b, midway, clear_px=10.0)
    assert not ok and worst == pytest.approx(3.0)


def test_px_and_trap_um_round_trip_with_the_y_flip():
    core = _load(CORE)
    p0, um = (600.0, 600.0), 0.065
    for px in ((610.0, 590.0), (500.0, 700.0)):
        u = core.px_to_trap_um(px, p0, um)
        back = core.trap_um_to_px(u, p0, um)
        assert back[0] == pytest.approx(px[0])
        assert back[1] == pytest.approx(px[1])
    # image y runs down, trap y runs up
    assert core.px_to_trap_um((600.0, 590.0), p0, um)[1] > 0
