"""An MCP server over the two hardware paths that are not Micro-Manager.

The tweezers (TCP) and the piezo (vendor DLL) are the two subsystems this
repository drives itself, so they are the two that answer the question an MCP
server is being built to answer: can a language model reach a device here
through a declared interface rather than by reading a CLI's help text. Get
these two and the Micro-Manager path follows, because pymmcore-plus already
provides the abstraction the other two lack.

Three tiers, and every tool declares which one it is in its MCP annotations:

    plan     pure arithmetic, no device, no filesystem      read_only
    write    emits a file, still no device                  read_only=False
    read     opens the device, reads, moves nothing         read_only
    move     moves something                               destructive

Nothing here originates a number. Every tool calls the driver or the planner
that the CLIs in config/ already call, and returns what it returned -- so a
tool cannot drift away from the command line that was verified against the
hardware. See mcp_server/switches.py for what happens at the move tier.
"""

__all__ = ["switches", "tweezers", "piezo", "server"]
