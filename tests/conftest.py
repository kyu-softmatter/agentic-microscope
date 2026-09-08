"""Suite-wide setup. One job today: the optional-dependency emulation.

`ci_emulate` is loaded by path rather than by name. `tests/` has no
`__init__.py`, so whether `import ci_emulate` works depends on pytest's import
mode and on whether the runner said `pytest` or `python -m pytest` -- the same
`sys.path` difference `pyproject.toml` exists to paper over. A conftest that
failed to import would take the whole suite with it, so it does not depend on
that being settled.

The emulation is inert unless `PYTEST_CI_EMULATE` is set. See
`tests/ci_emulate.py` for what each mode hides and why.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_tests_ci_emulate", Path(__file__).with_name("ci_emulate.py")
)
ci_emulate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_emulate)

# At import time, which is before any test module is collected -- so a
# module-level `importorskip` and a `skipif` on an individual test both see the
# emulated environment rather than the real one.
HIDDEN = ci_emulate.activate_from_env()
