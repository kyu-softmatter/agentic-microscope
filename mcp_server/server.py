"""The MCP server itself: assemble the tools, run over stdio.

    python -m mcp_server.server

Launched by an MCP client, normally through `.mcp.json` in the repository root.
The switches come from the environment the client launches it with, so they are
set where the server is configured and not by anything reachable during a
session -- see mcp_server/switches.py.

Deliberately absent: the eight committee lenses. They are the other half of an
MCP surface for this repository and a larger job, since each lens's CLI would
have to grow a `--json` and hand its parser over as the schema. This server is
the two hardware paths only, which is the half that had no abstraction at all.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import piezo, tweezers
from .switches import Switches

NAME = "agentic-microscope-hardware"

INSTRUCTIONS = """\
Two hardware paths on one microscope: the Aresis Tweez 300 optical tweezers
(TCP to its GUI) and the Prior/Queensgate NPC-D piezo stage (vendor DLL).

Read the annotations before calling. Tools marked read-only touch no device or
only read one; tools marked destructive move a stage or steer a trapping laser
and are refused by default.

Three things about the results.

A refusal is a value, not an error. `refused: true` with a `switch` means a
safety switch is off; `advances: false` with `blockers` means the plan itself is
not ready. Neither is a malfunction and neither should be worked around --
report the blockers instead.

`available: false` from a piezo tool means the vendor DLL is not installed on
this machine. That is expected away from the microscope PC.

No tool here invents a physical number. Each calls the planner or driver the
repository's own command-line scripts call, so if a tool and a script disagree,
that is a bug worth reporting.
"""


def build(switches: Switches | None = None) -> MCPServer:
    """The server, with both tool sets registered. Opens no device."""
    switches = Switches() if switches is None else switches
    server = MCPServer(name=NAME, instructions=INSTRUCTIONS, version="0.1.0")
    tweezers.register(server, switches)
    piezo.register(server, switches)
    return server


def main() -> None:
    build(Switches.from_env(dict(os.environ))).run(transport="stdio")


if __name__ == "__main__":
    main()
