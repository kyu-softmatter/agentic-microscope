"""Find an interpreter that can run the MCP server, then hand off to it.

    python mcp_server/bootstrap.py

**Stdlib only, and that is the point.** This file is launched by whatever
`python` the MCP client finds on PATH, which is exactly the interpreter that
does *not* have the dependencies -- so it must not need any. Its whole job is
to locate one that does and get out of the way.

WHY THIS EXISTS
---------------
`.mcp.json` used to name the interpreter directly::

    "command": "C:\\\\Users\\\\Takatori lab\\\\venvs\\\\auto_microscope\\\\Scripts\\\\python.exe"

which is two problems in one line. **It carries a Windows account name**, so on
any other account or machine the client fails with

    ENOENT: Executable not found in $PATH: C:\\Users\\Takatori lab\\...

-- observed 2026-09-06 on the macOS working machine, which is where this
repository is edited. And **it was the only file in the repository that knew
where the venv lived**, so every cold start re-derived it: `python -m pytest`
answers "No module named pytest" on the system Python, and the venv had to be
found by searching the filesystem before the suite could run.

Note what is NOT wrong with the old line: the venv living *outside* the
repository. `C:\\Users\\<you>\\venvs\\auto_microscope` survives a clean
checkout, which is a real argument for keeping it there, so this file looks in
user-home locations as well as repo-local ones rather than insisting on a
`.venv/`.

WHAT IT REFUSES TO DO
---------------------
**It never installs anything and never picks an interpreter that cannot import
`mcp`.** A server that starts on the wrong interpreter fails at
`from mcp.server.mcpserver import MCPServer` -- inside the MCP handshake, where
the client reports it as a broken server rather than as a missing dependency.
Refusing early with the install command on stderr is the difference between a
five-second fix and a debugging session. `requirements-mcp.txt` pins `mcp>=2.1,<3`
for the same reason: the SDK renamed FastMCP to MCPServer at 2.0, so a 1.x
install fails at import rather than at run time.

STDOUT IS THE PROTOCOL
----------------------
The MCP server speaks JSON-RPC over stdout. Every diagnostic here goes to
**stderr**; a single stray `print()` would corrupt the stream and read to the
client as a malformed server.

ONE EXTRA PROCESS, ON PURPOSE
-----------------------------
The handoff is `subprocess` with inherited stdio rather than `os.execv`. Exec on
Windows terminates the calling process and starts a new one, which changes the
PID the client is holding; inheriting the handles instead keeps one parent alive
and passes the real handles straight through, with no relay in between. So each
server instance shows up as **two** processes -- which is what the README's MCP
section already records as normal, and the reason it says to count instances by
parent process rather than by process.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Set this to skip the search entirely. The one thing to reach for when the
#: layout here does not match your machine.
OVERRIDE_ENV = "AGENTIC_MICROSCOPE_PYTHON"

#: The venv this instrument's PC actually uses, named without the account.
#: Python 3.12.10, built 2026-08-11, outside the repo so it survives checkouts.
KNOWN_VENV_NAMES = ("auto_microscope",)


def _log(msg: str) -> None:
    """stderr, always -- stdout belongs to the protocol."""
    print(f"[bootstrap] {msg}", file=sys.stderr, flush=True)


def _interpreter(venv: Path) -> Path:
    """The interpreter inside a venv directory, per platform layout."""
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def candidates() -> list[tuple[Path, str]]:
    """Interpreters to try, best first, each with why it was considered.

    Order is deliberate: an explicit override beats discovery, an already-active
    environment beats a guess, and a repo-local `.venv` beats a shared one
    because it is the one a contributor just made.
    """
    out: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def add(path: Path | None, why: str) -> None:
        if path is None:
            return
        try:
            resolved = Path(path).resolve()
        except OSError:
            return
        if resolved not in seen:
            seen.add(resolved)
            out.append((resolved, why))

    override = os.environ.get(OVERRIDE_ENV)
    if override:
        add(Path(override), f"${OVERRIDE_ENV}")

    add(Path(sys.executable), "the interpreter running this file")

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        add(_interpreter(Path(virtual_env)), "$VIRTUAL_ENV (an activated venv)")

    for name in (".venv", "venv"):
        add(_interpreter(REPO / name), f"{name}/ beside the repository")

    home = Path.home()
    for name in KNOWN_VENV_NAMES:
        for parent in ("venvs", ".venvs", "Envs"):
            add(_interpreter(home / parent / name),
                f"~/{parent}/{name} (outside the repo, survives a checkout)")

    return out


def has_mcp(interpreter: Path) -> bool:
    """Can this interpreter import `mcp`? Asked by running it, not by guessing.

    The current interpreter is checked in-process; anything else costs one short
    subprocess, which is cheaper than a failed MCP handshake.
    """
    if not interpreter.exists():
        return False
    if interpreter == Path(sys.executable).resolve():
        try:
            import mcp  # noqa: F401, PLC0415
        except Exception:
            return False
        return True
    try:
        done = subprocess.run(
            [str(interpreter), "-c", "import mcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def choose() -> tuple[Path, str] | None:
    tried: list[str] = []
    for interpreter, why in candidates():
        if not interpreter.exists():
            tried.append(f"  - {interpreter}  [{why}]  not present")
            continue
        if not has_mcp(interpreter):
            tried.append(f"  - {interpreter}  [{why}]  present, no `mcp`")
            continue
        return interpreter, why
    _log("no interpreter with the `mcp` package. Tried, in order:")
    for line in tried:
        _log(line)
    _log("")
    _log("To fix, either point at one directly:")
    _log(f'  set {OVERRIDE_ENV} to a python.exe that has `mcp`')
    _log("or install the dependencies into one:")
    _log("  python -m pip install -r requirements.txt -r requirements-mcp.txt")
    _log("(`mcp>=2.1,<3` -- a 1.x install fails at import, not at run time.)")
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    chosen = choose()
    if chosen is None:
        return 2
    interpreter, why = chosen
    _log(f"using {interpreter}  [{why}]")

    if "--dry-run" in argv:
        # For tests and for `doctor`-style checks: resolve and report, run
        # nothing. Keeps this file verifiable without starting a server.
        argv.remove("--dry-run")
        print(interpreter)          # the one intentional stdout write
        return 0

    cmd = [str(interpreter), "-m", "mcp_server.server", *argv]
    try:
        # cwd = REPO so `-m mcp_server.server` resolves wherever the client
        # launched us from. stdio is inherited, not piped: the server speaks
        # JSON-RPC on the handles the client opened, and nothing sits between.
        return subprocess.call(cmd, cwd=str(REPO))
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        _log(f"could not start {interpreter}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
