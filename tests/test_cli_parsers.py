"""Every `*/cli.py` can build its parser and print `--help`.

**Nothing in this suite did that, and a lens lost its command line for it.**
`photo/cli.py` raised `TypeError: _ActionsContainer._get_positional_kwargs()
missing 1 required positional argument: 'dest'` on *every* invocation,
`--help` included, from the moment `--bleach-photons` was removed with G10: the
deletion took the argument's body and left `c.add_argument(\n    )` behind.

The 1210 tests around it all passed, because they call `evaluate()` and the
check functions directly. An `argparse` mistake is not reachable that way --
the parser is only built inside `main()`, and `main()` is only reached from a
shell. So the defect was invisible to the suite and obvious to anyone who typed
the command.

`--help` is enough. `argparse` constructs every argument while building the
parser, so a malformed one fails there rather than at parse time, and
`SystemExit(0)` from `--help` is the cheapest proof that construction
completed. This does not test what any CLI *does* -- the gate tests do that.
"""

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Discovered rather than listed, so a new lens's CLI is covered the day it
#: lands instead of the day someone remembers this file.
CLIS = sorted(p.parent.name for p in ROOT.glob("*/cli.py"))


def test_the_discovery_found_the_clis():
    assert len(CLIS) >= 10, CLIS
    assert "photo" in CLIS


@pytest.mark.parametrize("package", CLIS)
def test_cli_help_exits_cleanly(package, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [package, "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module(f"{package}.cli", run_name="__main__")
    assert exc.value.code == 0, f"{package} --help exited {exc.value.code}"
    assert "usage" in capsys.readouterr().out.lower()
