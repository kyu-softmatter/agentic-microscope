"""Piezo tools: generate a waveform, read the command set, read state, move.

The waveform tools are pure and are the reason this subsystem is worth exposing
first: `hardware.piezo_waveform` refuses a waveform the controller would clip,
and that refusal is the interesting thing to carry across the MCP boundary
intact.

The two device tools go through `hardware.piezo_stage.PiezoStage`, which loads
a vendor DLL that **this repository does not publish** (NOTICE section 3). Its
constructor raises a `PiezoStageError` naming the release to obtain; both tools
below catch it and return it as `available: false` rather than as an exception,
because "the driver is not installed here" is an answer and not a malfunction.

`sim:/NPC6330` is the DLL's own simulator, so on a machine that has the DLL both
device tools can be exercised without a stage under the objective.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from hardware.piezo_waveform import (
    CALIBRATED,
    PM_PER_UM,
    StageTravel,
    Waveform,
    WaveformError,
    ramp,
    sine,
    staircase,
    triangle,
)

from .switches import Switches

#: The generators this exposes, by name. Anything not here is not reachable --
#: the alternative is passing a callable name through, which is how an MCP tool
#: turns into an eval().
GENERATORS = ("ramp", "triangle", "sine", "staircase")

DLL_ABSENT_NOTE = (
    "the vendor DLL is not published in this repository and the working PC is "
    "not the microscope PC. See NOTICE.md section 3 for the release to obtain "
    "and where to put it."
)


def travel_from(
    min_um: float | None, max_um: float | None, resolution_pm: float | None
) -> tuple[StageTravel, bool]:
    """A StageTravel, and whether the caller supplied it.

    Falling back to the recorded travel is allowed but reported, because a wrong
    travel bound is how a generated waveform ends up commanding the stage into
    its end stop -- `hardware/piezo_waveform.py` says so where StageTravel is
    defined, and requires it rather than defaulting it.
    """
    if min_um is None or max_um is None or resolution_pm is None:
        return CALIBRATED, False
    return (
        StageTravel(
            min_pm=min_um * PM_PER_UM,
            max_pm=max_um * PM_PER_UM,
            resolution_pm=resolution_pm,
        ),
        True,
    )


def waveform_dict(
    w: Waveform,
    travel: StageTravel,
    travel_supplied: bool,
    sample_period_s: float | None,
    iterations: int,
) -> dict:
    """A Waveform as JSON, with the travel check run and reported either way."""
    lo, hi = w.span_pm
    out: dict = {
        "name": w.name,
        "channel": w.channel,
        "samples": len(w),
        "span_um": [lo / PM_PER_UM, hi / PM_PER_UM],
        "travel_um": [travel.min_pm / PM_PER_UM, travel.max_pm / PM_PER_UM],
        "travel_supplied_by_caller": travel_supplied,
        "fits_within_travel": w.fits_within(travel),
        "quantisation_error_pm": w.quantisation_error_pm(travel),
        "first_samples_um": [s / PM_PER_UM for s in w.samples[:5]],
    }
    if not travel_supplied:
        out["travel_note"] = (
            "travel was not supplied, so the recorded calibration was used. "
            "Read the real bounds off the controller before playing this."
        )
    try:
        w.check(travel)
        out["check"] = "OK"
    except WaveformError as exc:
        out["check"] = "REFUSED"
        out["reason"] = str(exc)
    if sample_period_s is not None:
        out["duration_s"] = w.duration_s(sample_period_s, iterations=iterations)
        out["peak_speed_um_s"] = w.peak_speed_um_s(sample_period_s)
        out["iterations"] = iterations
    return out


def register(server, switches: Switches) -> None:
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False)
    touches_device = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=True
    )
    moves = ToolAnnotations(
        read_only_hint=False, destructive_hint=True, open_world_hint=True
    )

    @server.tool(annotations=read_only)
    def piezo_waveform_preview(
        kind: str,
        n_samples: int,
        amplitude_um: float | None = None,
        start_um: float | None = None,
        stop_um: float | None = None,
        step_um: float | None = None,
        n_steps: int | None = None,
        dwell_samples: int | None = None,
        centre_um: float | None = None,
        channel: int = 1,
        travel_min_um: float | None = None,
        travel_max_um: float | None = None,
        travel_resolution_pm: float | None = None,
        sample_period_s: float | None = None,
        iterations: int = 1,
    ) -> dict:
        """Generate a piezo waveform and check it against the travel. No device.

        `kind` is one of ramp, triangle, sine, staircase. ramp needs start_um and
        stop_um; triangle and sine need amplitude_um; staircase needs start_um,
        step_um, n_steps and dwell_samples (and ignores n_samples).

        Returns the span, whether it fits the travel, the quantisation error, and
        check=REFUSED with a reason when the controller would clip it -- a
        refusal, not an error. Supply travel_min_um / travel_max_um /
        travel_resolution_pm read off the controller; without them the recorded
        calibration is used and the result says so.
        """
        if kind not in GENERATORS:
            return {"error": f"kind must be one of {list(GENERATORS)}"}
        travel, supplied = travel_from(
            travel_min_um, travel_max_um, travel_resolution_pm
        )
        centre_pm = None if centre_um is None else centre_um * PM_PER_UM
        try:
            if kind == "ramp":
                if start_um is None or stop_um is None:
                    return {"error": "ramp needs start_um and stop_um"}
                w = ramp(
                    start_um * PM_PER_UM, stop_um * PM_PER_UM, n_samples, channel
                )
            elif kind in {"triangle", "sine"}:
                if amplitude_um is None:
                    return {"error": f"{kind} needs amplitude_um"}
                fn = triangle if kind == "triangle" else sine
                w = fn(
                    amplitude_um * PM_PER_UM,
                    n_samples,
                    channel,
                    centre_pm=centre_pm,
                    travel=travel,
                )
            else:
                missing = [
                    n
                    for n, v in (
                        ("start_um", start_um),
                        ("step_um", step_um),
                        ("n_steps", n_steps),
                        ("dwell_samples", dwell_samples),
                    )
                    if v is None
                ]
                if missing:
                    return {"error": f"staircase needs {missing}"}
                w = staircase(
                    start_um * PM_PER_UM,
                    step_um * PM_PER_UM,
                    n_steps,
                    dwell_samples,
                    channel,
                )
        except WaveformError as exc:
            return {"check": "REFUSED", "reason": str(exc), "kind": kind}
        return waveform_dict(w, travel, supplied, sample_period_s, iterations)

    @server.tool(annotations=read_only)
    def piezo_reference_commands(name_filter: str = "") -> dict:
        """The controller's command set, from the recorded reference. No device.

        Reads reference/npcd-command-set.md -- 414 names read off the live
        controller over COM4 on 2026-08-27 at User security level, not pulled
        out of the DLL. `name_filter` is a substring match.

        The security level decides what exists: locked, the controller answers
        188 commands and `stage.position.command.set` is invisible rather than
        merely unavailable. So absence from this list at one level is not proof
        the controller cannot do it.
        """
        from hardware.piezo_stage import reference_commands

        names = sorted(reference_commands())
        if name_filter:
            hit = [n for n in names if name_filter in n]
        else:
            hit = names
        return {
            "total_recorded": len(names),
            "filter": name_filter or None,
            "count": len(hit),
            "commands": hit,
            "source": "reference/npcd-command-set.md (COM4, 2026-08-27, level User)",
        }

    @server.tool(annotations=touches_device)
    def piezo_read_state(link: str = "sim:/NPC6330", channel: int = 1) -> dict:
        """Open the controller and read its state. Moves nothing.

        `link` is a COM port, an IP address, or "sim:/NPC6330" for the DLL's own
        simulator. The stage is constructed with allow_motion=False regardless of
        this server's switches, because this tool has no reason to move anything.

        Returns available=false when the vendor DLL is absent, which is the
        answer from any machine that is not the microscope PC.
        """
        try:
            from hardware.piezo_stage import PiezoStage, PiezoStageError
        except Exception as exc:  # pragma: no cover - import-time DLL adapter
            return {"available": False, "error": str(exc), "note": DLL_ABSENT_NOTE}

        try:
            stage = PiezoStage(allow_motion=False)
        except PiezoStageError as exc:
            return {"available": False, "error": str(exc), "note": DLL_ABSENT_NOTE}

        try:
            with stage:
                stage.connect(link)
                out = {
                    "available": True,
                    "link": link,
                    "dll_version": stage.dll_version(),
                    "identity": stage.identity(),
                    "channels": stage.channels(),
                    "security_level": stage.security_level(),
                    "position_um": stage.get_position_um(channel),
                    "travel_pm": stage.travel_pm(channel),
                    "mode_flags": stage.mode_flags(channel),
                    "is_playing": stage.is_playing(channel),
                }
                stage.disconnect()
                return out
        except PiezoStageError as exc:
            return {"available": True, "link": link, "error": str(exc)}

    @server.tool(annotations=moves)
    def piezo_move(
        target_um: float,
        link: str = "sim:/NPC6330",
        channel: int = 1,
    ) -> dict:
        """Command the piezo stage to a position. Moves the stage.

        Refused unless allow_motion is on. The refusal names the target it would
        have commanded. Even when allowed, the driver checks the commanded
        position against the controller's own travel bounds and raises rather
        than clipping.
        """
        refusal = switches.require(
            "allow_motion",
            "command the piezo stage to a position",
            target_um=target_um,
            link=link,
            channel=channel,
        )
        if refusal is not None:
            return refusal

        try:
            from hardware.piezo_stage import PiezoStage, PiezoStageError

            stage = PiezoStage(allow_motion=True)
        except Exception as exc:
            return {"available": False, "error": str(exc), "note": DLL_ABSENT_NOTE}

        try:
            with stage:
                stage.connect(link)
                before = stage.get_position_um(channel)
                stage.set_position_um(channel, target_um)
                after = stage.get_position_um(channel)
                stage.disconnect()
                return {
                    "ok": True,
                    "link": link,
                    "channel": channel,
                    "target_um": target_um,
                    "position_before_um": before,
                    "position_after_um": after,
                }
        except PiezoStageError as exc:
            return {"ok": False, "error": str(exc), "target_um": target_um}
