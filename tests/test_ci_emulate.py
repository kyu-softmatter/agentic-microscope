"""Tests for the optional-dependency emulation itself.

Two things here can be wrong without anyone noticing, and they are the two the
plugin exists to prevent:

    * **it is inert unless asked.** A plugin that hid a stack on every run would
      turn the suite's headline number into a quieter lie than the one it was
      written to catch.
    * **an unrecognised mode is an error, not a no-op.** A typo in
      `PYTEST_CI_EMULATE` that produced a normal, green run would let someone
      believe they had checked the runner's environment when they had not.

The activation path itself is deliberately not exercised here: it mutates
`sys.meta_path` and `importlib.util.find_spec` process-wide, so testing it
in-process would change the environment of every test collected after it. It is
covered instead by using it -- `PYTEST_CI_EMULATE=ci` must reproduce the badge's
`1150 passed, 10 skipped`, which is the number the README quotes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(relative: str, name: str):
    """Same by-path load the conftest uses, and for the same reason."""
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CE = _load("tests/ci_emulate.py", "_ci_emulate_under_test")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unset_hides_nothing(value):
    """The default has to be a full run."""
    assert CE.blocked_for(value) == ()


def test_ci_mode_hides_exactly_what_the_runner_lacks():
    """`requirements.txt` + `requirements-mcp.txt` is what CI installs, so cv2
    and pymmcore_plus are the two absences to reproduce -- and `mcp` is NOT one
    of them, which is the mistake that would make the emulated number too low."""
    assert set(CE.blocked_for("ci")) == {"cv2", "pymmcore_plus"}
    assert "mcp" not in CE.blocked_for("ci")


def test_base_mode_also_hides_mcp():
    assert set(CE.blocked_for("base")) == {"cv2", "pymmcore_plus", "mcp"}


@pytest.mark.parametrize("alias", ["1", "true", "YES", "Ci", " ci "])
def test_the_aliases_a_shell_reflexively_types_all_mean_ci(alias):
    assert CE.blocked_for(alias) == CE.MODES["ci"]


def test_an_unrecognised_mode_refuses_instead_of_running_normally():
    """The whole failure mode this guards: a typo that quietly gives a green,
    full-environment run to someone who thinks they emulated the runner."""
    with pytest.raises(ValueError, match="not a mode"):
        CE.blocked_for("cl")          # a plausible mistyping of `ci`


def test_the_blocker_refuses_submodules_too():
    """`import cv2.data` has to fail the same way `import cv2` does, or a
    partial import would look like a working OpenCV."""
    blocker = CE._Blocker(("cv2",))
    with pytest.raises(ModuleNotFoundError):
        blocker.find_spec("cv2")
    with pytest.raises(ModuleNotFoundError):
        blocker.find_spec("cv2.data")
    assert blocker.find_spec("numpy") is None      # not ours: defer
