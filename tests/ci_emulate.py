"""Hide the optional dependency stacks, so a local run fails the way CI does.

**Why this exists.** CI installs `requirements.txt` + `requirements-mcp.txt` and
nothing else. The instrument PC's venv (`~/venvs/auto_microscope`) has the other
two stacks as well -- `opencv-python` and `pymmcore_plus` -- so a test that
reaches into one of them passes here and errors there. That is not hypothetical:
CI was red for three commits after `062db16`, because
`tests/test_objective_offsets.py` calls `locate_centroid`, which defers
`import cv2` into its function body. The module imported, collection succeeded,
and seven tests then raised `ModuleNotFoundError` on the runner only.

Activated by an environment variable rather than by default, because a run that
silently skipped things would be worse than the problem::

    PYTEST_CI_EMULATE=ci   pytest -q -rs   # what the badge runs: expect 1150 passed, 10 skipped
    PYTEST_CI_EMULATE=base pytest -q -rs   # requirements.txt alone: 1120 collected

In PowerShell: `$env:PYTEST_CI_EMULATE = "ci"`, and `Remove-Item Env:\\PYTEST_CI_EMULATE` after.

This hides *dependencies* only. The runner also sets `CI`, which widens the
real-clock overshoot bound in `tests/test_runtime_ticker.py` -- so the closest
reproduction of a job is `CI=1 PYTEST_CI_EMULATE=ci pytest -q -rs`. Deliberately
two variables: one says what is installed, the other says whose machine it is,
and conflating them would make a timing tolerance depend on an import.

**Both halves of the hiding matter, and for different reasons.**

* A `meta_path` finder makes a real `import cv2` fail. This is what reproduces
  the failure -- without it, an unmarked test still passes locally and the next
  occurrence of `062db16` goes out the same way.
* `importlib.util.find_spec` is patched to answer `None` for the same names.
  This is what lets `requires_cv2` decide to skip. A raising finder alone would
  make `find_spec` propagate the error out of the `skipif` expression and turn a
  skip into a collection error, which is a third behaviour belonging to neither
  environment.
"""

from __future__ import annotations

import importlib.util
import os
import sys

#: mode -> module roots that must disappear. `ci` is the badge's environment;
#: `base` additionally drops the MCP stack, i.e. `requirements.txt` on its own.
MODES: dict[str, tuple[str, ...]] = {
    "ci": ("cv2", "pymmcore_plus"),
    "base": ("cv2", "pymmcore_plus", "mcp"),
}

#: `1` is accepted for `ci` because that is what a shell reflexively types.
ALIASES = {"1": "ci", "true": "ci", "yes": "ci"}


def blocked_for(value: str | None) -> tuple[str, ...]:
    """Module roots to hide for an environment-variable value.

    An unset or empty value hides nothing -- the plugin has to be inert unless
    it was asked for. An unrecognised value is an error rather than a silent
    no-op: a typo in `PYTEST_CI_EMULATE` that produced a normal run would let
    someone believe they had checked something they had not.
    """
    if value is None or not value.strip():
        return ()
    key = value.strip().lower()
    key = ALIASES.get(key, key)
    if key not in MODES:
        raise ValueError(
            f"PYTEST_CI_EMULATE={value!r} is not a mode. "
            f"Use one of {sorted(MODES)} (or 1 for 'ci')."
        )
    return MODES[key]


class _Blocker:
    """A `meta_path` finder that refuses a fixed set of module roots."""

    def __init__(self, blocked: tuple[str, ...]) -> None:
        self.blocked = blocked

    def _is_blocked(self, name: str) -> bool:
        return name.split(".")[0] in self.blocked

    def find_spec(self, name, path=None, target=None):
        if self._is_blocked(name):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None      # not ours; let the real finders answer


def activate(value: str | None, *, announce=True) -> tuple[str, ...]:
    """Hide the stacks named by `value`. Returns what was hidden."""
    blocked = blocked_for(value)
    if not blocked:
        return ()

    for name in list(sys.modules):
        if name.split(".")[0] in blocked:
            del sys.modules[name]

    blocker = _Blocker(blocked)
    sys.meta_path.insert(0, blocker)

    real_find_spec = importlib.util.find_spec

    def find_spec(name, package=None):
        if blocker._is_blocked(name):
            return None
        return real_find_spec(name, package)

    importlib.util.find_spec = find_spec

    if announce:
        # Loud, and on stderr: a run with hidden dependencies must not be
        # mistakeable for a full one when the numbers are read later.
        print(
            f"[ci_emulate] hiding {', '.join(blocked)} — this is NOT a full run",
            file=sys.stderr,
        )
    return blocked


def activate_from_env(*, announce=True) -> tuple[str, ...]:
    return activate(os.environ.get("PYTEST_CI_EMULATE"), announce=announce)
