"""Tweezers tools: plan, emit the .tpf, show the TCP lines, probe, run.

The tiers mirror `config/tweezers/run_pattern.py`'s own `--plan` / `--write` /
`--run`, deliberately: that script is the interface that was reasoned about, so
this is a second front end onto it rather than a second implementation. Every
number below comes out of `hardware.tweezers_drive.plan` or
`hardware.tweezers_patterns`; nothing is recomputed here.

`tweezers_plan` returns `report` alongside the structured fields, because the
calling model should see the text a human reviewing the plan sees rather than a
summary of it.

**These tools reach one of the three control surfaces.** First light on the real
instrument (`kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md`)
established that the Tweez 300 has three: TCP external control on port 2070, 28
documented commands, which is what `hardware/optical_tweezers.py` speaks and all
that is exposed here; the GUI's embedded Python, which reaches everything in the
Properties panel but takes no external trigger; and the GUI by hand. Three
properties that gate a real drive -- `Breakpoints > Enable Bits`,
`Repeat > Enabled`, and laser power -- live only on the surfaces this cannot
reach, so a plan that `tweezers_run` accepts is still not a drive that runs
without a person at the GUI.
"""

from __future__ import annotations

from pathlib import Path

from mcp.types import ToolAnnotations

from hardware.tweezers_drive import (
    DrivePlan,
    blanking_time_note,
    command_sequence,
    load_spec,
    plan,
)
from hardware.tweezers_patterns import PatternError

from .switches import Switches

#: A plan that does not advance is the normal case, not an error -- the spec
#: shipped in config/tweezers/ returns three blockers. Tool descriptions say so,
#: because a model that reads `advances: false` as a tool failure will try to
#: route around it.
ADVANCES_NOTE = (
    "advances=false is a valid result and not a tool failure: it means the plan "
    "is not ready to run, and `blockers` says what would make it ready."
)


def plan_dict(p: DrivePlan) -> dict:
    """A DrivePlan as JSON. Field for field -- no derived quantities."""
    dx, dy = p.pattern.half_extent_um
    return {
        "name": p.name,
        "trap": p.trap,
        "pattern_name": p.pattern_name,
        "project": p.project,
        "project_problem": p.project_problem,
        "pattern": {
            "name": p.pattern.name,
            "points": len(p.pattern),
            "path_length_um": p.pattern.path_length_um,
            "half_extent_um": [dx, dy],
        },
        "loop": {
            "switching_rate_hz": p.loop.switching_rate_hz,
            "n_traps": p.loop.n_traps,
            "pass_time_s": p.loop.pass_time_s,
        },
        "native_speed_um_s": p.native_speed_um_s,
        "target_speed_um_s": p.target_speed_um_s,
        "slowdown_factor": p.slowdown_factor,
        "chosen_route": _route(p.chosen),
        "routes": [_route(r) for r in p.routes],
        "wait_states": p.wait_states,
        # These four are methods on DrivePlan, not properties -- the class mixes
        # both, and putting a bound method in this dict serialises without
        # complaint. tests/test_mcp_server.py compares every field against the
        # DrivePlan it came from for exactly that reason.
        "effective_cycle_time_s": p.effective_cycle_time_s(),
        "effective_speed_um_s": p.effective_speed_um_s(),
        "switching_rate_hz_to_send": p.switching_rate_hz(),
        "range_status": p.range_status,
        "range_note": p.range_note,
        "calibration": p.calibration,
        "field_calibration": p.field_calibration,
        "advances": p.advances,
        "blockers": list(p.blockers),
        "report": p.report(),
    }


def _route(r) -> dict:
    return {
        "kind": r.kind,
        "factor": r.factor,
        "python_settable": r.python_settable,
        "cost": r.cost,
    }


def blocked(exc: PatternError) -> dict:
    """A spec the planner refuses. Its own message names the fix."""
    return {
        "status": "BLOCKED",
        "advances": False,
        "reason": str(exc),
        "blockers": [str(exc)],
    }


def register(server, switches: Switches) -> None:
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False)
    emits_file = ToolAnnotations(read_only_hint=False, destructive_hint=False)
    touches_device = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=True
    )
    moves = ToolAnnotations(
        read_only_hint=False, destructive_hint=True, open_world_hint=True
    )

    @server.tool(annotations=read_only)
    def tweezers_plan(spec_path: str) -> dict:
        """Review an optical-tweezers drive spec. Touches no hardware.

        Reads a drive spec -- config/tweezers/active-microrheology-drive.yaml is
        the worked one -- and returns the plan: pattern geometry, trap-loop
        timing, native and target speed, every slowdown route with its cost, the
        trapping-range check, and whether the plan advances. `report` is the
        same text a human reviewing the plan reads.

        advances=false is a valid result and not a tool failure: it means the
        plan is not ready to run, and `blockers` says what would make it ready.
        """
        try:
            return plan_dict(plan(load_spec(spec_path)))
        except PatternError as exc:
            return blocked(exc)

    @server.tool(annotations=read_only)
    def tweezers_command_sequence(
        spec_path: str,
        tpf_path_on_scope: str,
        file_first: bool = False,
        blanking_time_us: float = 0.0,
    ) -> dict:
        """The exact TCP command lines a spec implies. Sends nothing.

        `tpf_path_on_scope` is the .tpf path as the Tweez GUI will see it, so it
        is a path on the microscope PC and need not exist here. `file_first`
        swaps LOAD_PATTERN's two arguments, because the manual's two editions
        disagree about the order -- a switch rather than a guess.

        Call this before tweezers_run: it returns the same list that tool sends.
        """
        try:
            p = plan(load_spec(spec_path))
        except PatternError as exc:
            return blocked(exc)
        return {
            "commands": list(
                command_sequence(
                    p,
                    tpf_path_on_scope,
                    file_first=file_first,
                    blanking_time_us=blanking_time_us,
                )
            ),
            "advances": p.advances,
            "blockers": list(p.blockers),
            "blanking_note": blanking_time_note(p.switching_rate_hz(), blanking_time_us),
        }

    @server.tool(annotations=emits_file)
    def tweezers_write_tpf(
        spec_path: str, out_path: str, decimal: str = "."
    ) -> dict:
        """Generate the .tpf point-list file for a spec. Touches no hardware.

        `decimal` is "." or "," -- the GUI parses whichever its locale uses, and
        the wrong one is read as a thousands separator. The file is written even
        when the plan does not advance: a point list on disk is reviewable and
        moves nothing.
        """
        if decimal not in {".", ","}:
            return {"error": "decimal must be '.' or ','"}
        try:
            p = plan(load_spec(spec_path))
        except PatternError as exc:
            return blocked(exc)
        pattern = p.emitted_pattern()
        written = pattern.write(out_path, decimal=decimal)
        return {
            "path": str(written),
            "points": len(pattern),
            "bytes": Path(written).stat().st_size,
            "advances": p.advances,
            "blockers": list(p.blockers),
        }

    @server.tool(annotations=touches_device)
    def tweezers_probe(host: str = "127.0.0.1", port: int = 2070) -> dict:
        """Ask the Tweez GUI whether it is there and ready. Moves nothing.

        Opens the external-control socket, sends one harmless command, reads the
        status. Returns reachable=false with the socket error when the GUI is
        not listening, which is the expected answer from anywhere that is not
        the microscope PC.
        """
        from hardware.optical_tweezers import OpticalTweezers, TweezersError

        try:
            with OpticalTweezers(host=host, port=port) as tweez:
                return {
                    "reachable": True,
                    "host": host,
                    "port": port,
                    "probe_status": tweez.probe(),
                    "ready": tweez.is_ready(),
                }
        except (OSError, TweezersError) as exc:
            return {
                "reachable": False,
                "host": host,
                "port": port,
                "error": f"{type(exc).__name__}: {exc}",
                "note": (
                    "the GUI listens on 2070 and increments per instance, and it "
                    "runs on the microscope PC, which is not this machine."
                ),
            }

    @server.tool(annotations=moves)
    def tweezers_run(
        spec_path: str,
        tpf_path_on_scope: str,
        host: str = "127.0.0.1",
        port: int = 2070,
        file_first: bool = False,
    ) -> dict:
        """Send a drive plan to the Tweez GUI. Steers the trapping laser.

        Refused unless allow_motion and allow_laser are both on, and refused
        again if the plan does not advance. Either refusal returns the command
        lines it would have sent, so what was refused stays reviewable.
        """
        try:
            p = plan(load_spec(spec_path))
        except PatternError as exc:
            return blocked(exc)
        commands = list(command_sequence(p, tpf_path_on_scope, file_first=file_first))
        would_have = {"commands": commands, "host": host, "port": port}

        for switch in ("allow_motion", "allow_laser"):
            refusal = switches.require(
                switch, "run a tweezers drive plan", **would_have
            )
            if refusal is not None:
                return refusal

        if not p.advances:
            return {
                "refused": True,
                "action": "run a tweezers drive plan",
                "switch": None,
                "reason": "the plan does not advance",
                "blockers": list(p.blockers),
                "what_would_have_happened": would_have,
            }

        from hardware.optical_tweezers import OpticalTweezers, TweezersError

        sent: list[str] = []
        try:
            with OpticalTweezers(host=host, port=port) as tweez:
                for line in commands:
                    tweez.do(line)
                    sent.append(line)
        except (OSError, TweezersError) as exc:
            return {
                "ok": False,
                "sent": sent,
                "failed_on": commands[len(sent)] if len(sent) < len(commands) else None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {"ok": True, "sent": sent}
