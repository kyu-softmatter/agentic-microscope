"""`.mcp.json` must not name one machine's interpreter, and must still refuse.

THE BUG THIS HOLDS CLOSED
-------------------------
`.mcp.json` named the interpreter by absolute path::

    "command": "C:\\\\Users\\\\Takatori lab\\\\venvs\\\\auto_microscope\\\\Scripts\\\\python.exe"

On 2026-09-06 that produced, on the macOS machine this repository is edited
from::

    ENOENT: Executable not found in $PATH: C:\\Users\\Takatori lab\\...

Two defects in one line, and they fail differently. The **account name** breaks
the server on any other user or machine, loudly. The **single point of
knowledge** -- no other file said which interpreter to use -- cost a filesystem
search on every cold start, quietly.

WHAT IS ACTUALLY TESTED
-----------------------
Not "the server starts", which needs a client. Three narrower things:

  1. the config no longer pins a machine, and cannot regress to one;
  2. the bootstrap resolves an interpreter, honouring an override, and
     **refuses with instructions** rather than handing the client an
     interpreter that will die inside the MCP handshake;
  3. **nothing it says goes to stdout.** stdout is JSON-RPC. One stray print
     reads to the client as a malformed server, which is indistinguishable
     from the failure this whole file exists to remove.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mcp_server import bootstrap  # noqa: E402

MCP_JSON = REPO / ".mcp.json"
SERVER_NAME = "agentic-microscope-hardware"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(MCP_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def server(config) -> dict:
    return config["mcpServers"][SERVER_NAME]


# --------------------------------------------------------------------------
# the config does not pin a machine
# --------------------------------------------------------------------------

def test_mcp_json_is_valid_json(config):
    assert SERVER_NAME in config["mcpServers"]


def test_the_command_is_not_an_absolute_path(server):
    """The load-bearing test. An absolute interpreter path is the bug."""
    command = server["command"]
    assert not Path(command).is_absolute(), (
        f"command {command!r} is an absolute path. It will be right on exactly "
        "one machine -- resolve the interpreter at launch instead, in "
        "mcp_server/bootstrap.py.")
    # A drive letter is absolute on Windows and merely a relative path with a
    # colon in it on POSIX, so `is_absolute()` alone does not catch it here.
    assert ":\\" not in command and ":/" not in command


def test_no_account_name_anywhere_in_the_config(config):
    """`Takatori lab` was in the committed path. Nothing user-specific returns."""
    blob = json.dumps(config)
    for token in ("Takatori", "Users\\\\", "/Users/", "/home/", "C:\\\\"):
        assert token not in blob, f"{token!r} is back in .mcp.json"


def test_the_config_launches_the_bootstrap(server):
    assert server["args"], "no args -- the bootstrap is not being launched"
    target = REPO / server["args"][0]
    assert target.exists()
    assert target.name == "bootstrap.py"


def test_both_write_switches_still_ship_off(server):
    """Unrelated to the path, and the thing most easily lost while editing it.

    A fresh session must answer `refused: true` to every move-tier call. The
    README states this as the configured default, so it is the default a config
    edit is most likely to break silently.
    """
    env = server["env"]
    assert env["AGENTIC_MICROSCOPE_ALLOW_MOTION"] == "0"
    assert env["AGENTIC_MICROSCOPE_ALLOW_LASER"] == "0"


# --------------------------------------------------------------------------
# the bootstrap needs nothing installed
# --------------------------------------------------------------------------

def test_the_bootstrap_imports_only_the_standard_library():
    """It is launched by the interpreter that does NOT have the dependencies.

    A third-party import at module level would make it fail exactly where it is
    supposed to be diagnosing. The `import mcp` inside `has_mcp` is
    function-level on purpose and is not a module-level import.
    """
    stdlib = set(sys.stdlib_module_names)
    tree = ast.parse((REPO / "mcp_server" / "bootstrap.py").read_text(encoding="utf-8"))
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module.split(".")[0]]
        for name in names:
            assert name in stdlib, f"module-level import of {name!r} is not stdlib"


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------

def test_an_override_is_tried_first(monkeypatch):
    monkeypatch.setenv(bootstrap.OVERRIDE_ENV, sys.executable)
    first, why = bootstrap.candidates()[0]
    assert first == Path(sys.executable).resolve()
    assert bootstrap.OVERRIDE_ENV in why


def test_candidates_are_deduplicated_and_carry_a_reason(monkeypatch):
    monkeypatch.setenv(bootstrap.OVERRIDE_ENV, sys.executable)
    monkeypatch.setenv("VIRTUAL_ENV", str(REPO / ".venv"))
    got = bootstrap.candidates()
    paths = [p for p, _ in got]
    assert len(paths) == len(set(paths))
    assert all(why for _, why in got)


def test_the_running_interpreter_is_always_a_candidate(monkeypatch):
    monkeypatch.delenv(bootstrap.OVERRIDE_ENV, raising=False)
    assert Path(sys.executable).resolve() in [p for p, _ in bootstrap.candidates()]


def test_a_stale_override_does_not_abort_the_search(monkeypatch):
    """The exact old value must degrade to a fallback, not to ENOENT.

    This is the regression: someone's environment, or an old note, still
    carries the Windows path. It should be skipped, not fatal.
    """
    monkeypatch.setenv(
        bootstrap.OVERRIDE_ENV,
        "C:\\Users\\Takatori lab\\venvs\\auto_microscope\\Scripts\\python.exe")
    chosen = bootstrap.choose()
    assert chosen is not None
    assert chosen[0].exists()


def test_has_mcp_is_false_for_something_that_is_not_there(tmp_path):
    assert not bootstrap.has_mcp(tmp_path / "nope" / "python")


def test_has_mcp_is_false_for_an_interpreter_without_the_package(tmp_path):
    """A file that exists and is not a working interpreter must not be chosen."""
    fake = tmp_path / ("python.exe" if sys.platform == "win32" else "python")
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    assert not bootstrap.has_mcp(fake)


# --------------------------------------------------------------------------
# refusal, and where it is written
# --------------------------------------------------------------------------

def test_choose_refuses_when_nothing_has_mcp(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "has_mcp", lambda _p: False)
    assert bootstrap.choose() is None
    err = capsys.readouterr().err
    # It must say what to do, not merely that it failed.
    assert bootstrap.OVERRIDE_ENV in err
    assert "requirements-mcp.txt" in err


def test_main_exits_nonzero_rather_than_launching_a_doomed_interpreter(monkeypatch):
    monkeypatch.setattr(bootstrap, "choose", lambda: None)
    assert bootstrap.main([]) == 2


def test_nothing_diagnostic_reaches_stdout(monkeypatch, capsys):
    """stdout is the JSON-RPC channel. Everything explanatory is stderr."""
    monkeypatch.setattr(bootstrap, "has_mcp", lambda _p: False)
    bootstrap.choose()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


def test_dry_run_prints_only_the_interpreter_on_stdout():
    """End to end, as a subprocess, the way the client launches it."""
    done = subprocess.run(
        [sys.executable, "mcp_server/bootstrap.py", "--dry-run"],
        cwd=str(REPO), capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"stdout carried more than the interpreter: {lines}"
    assert Path(lines[0]).exists()
