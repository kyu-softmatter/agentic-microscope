"""The switches, and what a refusal looks like when one of them is off.

`hardware/microscope.py` gates its writes behind `allow_write` / `allow_motion`
/ `allow_laser`, all default off, and `hardware/piezo_stage.py` gates motion
behind `allow_motion`. This is the same idea one layer up, because the caller
here is a language model rather than a person who typed a command and can see
the bench.

**`hardware/optical_tweezers.py` has no switch of its own.** Unlike the other
two drivers, all 28 of its commands are directly callable -- `laser_on()`
included -- and its constructor opens the socket. So for the tweezers this
module is the only brake in the path. That asymmetry is worth closing in the
driver itself (MHS puts safety limits *in the driver* for exactly this reason,
docs/mhs-integration.md), but closing it changes six call sites, so it is not
done here and this file carries the load meanwhile.

Two departures from the drivers, both deliberate.

**A refused tool returns a value; it does not raise.** A tool that raises reads
to the calling model as "this tool is broken", and a model that believes a tool
is broken routes around it -- which is the failure mode the whole repository is
built against. A structured refusal naming the switch is instead a fact the
model can report back.

**A refusal carries what would have happened.** The exact command lines, or the
exact target position. The README's refusal section and docs/06 make the same
point about gates: a refusal that does not say what would resolve it is a dead
end.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Environment variables, so the switch is set where the server is launched --
#: in .mcp.json -- and not by anything the model can reach at run time.
ENV_MOTION = "AGENTIC_MICROSCOPE_ALLOW_MOTION"
ENV_LASER = "AGENTIC_MICROSCOPE_ALLOW_LASER"

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Switches:
    """Both default off. Nothing in a session can turn one on."""

    allow_motion: bool = False
    allow_laser: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Switches:
        return cls(
            allow_motion=env.get(ENV_MOTION, "").strip().lower() in _TRUE,
            allow_laser=env.get(ENV_LASER, "").strip().lower() in _TRUE,
        )

    def enabled(self, switch: str) -> bool:
        return bool(getattr(self, switch))

    def require(self, switch: str, action: str, **would_have) -> dict | None:
        """``None`` if the switch is on. Otherwise the refusal, verbatim.

        Callers return it as the tool result -- they do not raise it.
        """
        if self.enabled(switch):
            return None
        env = {"allow_motion": ENV_MOTION, "allow_laser": ENV_LASER}[switch]
        out = {
            "refused": True,
            "action": action,
            "switch": switch,
            "reason": (
                f"{switch} is off, which is the default. Nothing in this "
                "session can turn it on."
            ),
            "how_to_enable": (
                f"set {env}=1 in the environment the MCP server is launched "
                "with (.mcp.json > mcpServers > agentic-microscope-hardware > "
                "env), then "
                "restart it. Do that only at the instrument, with clearance "
                "checked."
            ),
        }
        if would_have:
            out["what_would_have_happened"] = would_have
        return out
