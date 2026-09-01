"""Tests for the hardware MCP server.

Four things are worth testing at an MCP boundary, and they are not the same
things worth testing in a driver.

**Equivalence.** Every number a tool returns has to equal the one the planner or
driver produced. `DrivePlan` mixes properties and methods, and a bound method
put into a result dict serialises without complaint -- so a tool can silently
return a callable's repr where a float belongs. That happened while this was
being written, which is why `test_plan_fields_equal_the_driveplan` compares
field by field rather than spot-checking.

**Refusals survive.** `advances: false`, `check: REFUSED` and `refused: true`
all have to arrive as values with their reasons attached. A tool that raises
instead reads to the calling model as a broken tool, and a model that believes a
tool is broken routes around it.

**Nothing is reached while a switch is off.** Not "the refusal was returned" --
that the device was never opened. The tests that matter here replace the driver
with something that raises on construction.

**The surface is the surface.** Two destructive tools, both named; nothing else
in the list can move anything.

`asyncio.run` rather than pytest-asyncio: the server's own `call_tool` is a
coroutine, and one `asyncio.run` per test is cheaper than a plugin dependency.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from hardware.piezo_waveform import CALIBRATED, PM_PER_UM, WaveformError, sine
from hardware.tweezers_drive import command_sequence, load_spec, plan
from mcp_server.server import build
from mcp_server.switches import ENV_LASER, ENV_MOTION, Switches

SPEC = "config/tweezers/active-microrheology-drive.yaml"

#: The whole surface. A tool appearing or disappearing should fail a test rather
#: than be noticed by a reader of a diff.
EXPECTED_TOOLS = {
    "tweezers_plan",
    "tweezers_command_sequence",
    "tweezers_write_tpf",
    "tweezers_probe",
    "tweezers_run",
    "piezo_waveform_preview",
    "piezo_reference_commands",
    "piezo_read_state",
    "piezo_move",
}

#: The only two that may be annotated destructive, and the only two gated.
MOVES = {"tweezers_run", "piezo_move"}


def tools(server=None):
    return asyncio.run((server or build()).list_tools())


def call(name: str, args: dict, server=None) -> dict:
    """Call a tool through the MCP layer and return its structured result."""
    server = server or build()
    result = asyncio.run(server.call_tool(name, args))
    assert not result.is_error, f"{name} raised: {result.content}"
    out = getattr(result, "structured_content", None)
    if out is None:
        out = json.loads(result.content[0].text)
    return out


# ---- the surface -------------------------------------------------------


def test_the_tool_list_is_exactly_the_two_hardware_paths():
    assert {t.name for t in tools()} == EXPECTED_TOOLS


def test_every_tool_belongs_to_one_of_the_two_subsystems():
    for t in tools():
        assert t.name.startswith(("tweezers_", "piezo_")), t.name


def test_only_the_two_moving_tools_are_annotated_destructive():
    destructive = {
        t.name for t in tools() if t.annotations and t.annotations.destructive_hint
    }
    assert destructive == MOVES


def test_every_tool_declares_annotations_and_a_description():
    for t in tools():
        assert t.annotations is not None, t.name
        assert t.description and len(t.description) > 40, t.name


def test_every_tool_input_schema_is_a_json_schema_object():
    for t in tools():
        schema = t.input_schema
        assert schema["type"] == "object", t.name
        assert isinstance(schema.get("properties"), dict), t.name


# ---- equivalence with the driver ---------------------------------------


def test_plan_fields_equal_the_driveplan():
    """Field by field, because a bound method serialises silently."""
    p = plan(load_spec(SPEC))
    out = call("tweezers_plan", {"spec_path": SPEC})

    assert out["name"] == p.name
    assert out["trap"] == p.trap
    assert out["pattern"]["points"] == len(p.pattern)
    assert out["pattern"]["path_length_um"] == pytest.approx(p.pattern.path_length_um)
    assert out["native_speed_um_s"] == pytest.approx(p.native_speed_um_s)
    assert out["slowdown_factor"] == pytest.approx(p.slowdown_factor)
    assert out["wait_states"] == p.wait_states
    assert out["range_status"] == p.range_status
    assert out["advances"] is p.advances
    assert out["blockers"] == list(p.blockers)
    assert out["report"] == p.report()

    # The four that are methods on DrivePlan, not properties.
    assert out["effective_cycle_time_s"] == pytest.approx(p.effective_cycle_time_s())
    assert out["effective_speed_um_s"] == pytest.approx(p.effective_speed_um_s())
    assert out["switching_rate_hz_to_send"] == pytest.approx(p.switching_rate_hz())
    assert out["pattern"]["points"] == len(p.emitted_pattern())


def test_no_plan_field_carries_a_repr_instead_of_a_value():
    """The failure mode the test above is guarding: a bound method reaching the
    client as a string. Nothing in a plan should mention 'bound method'."""
    out = call("tweezers_plan", {"spec_path": SPEC})
    assert "bound method" not in json.dumps(out)


def test_command_sequence_is_the_drivers_own_sequence():
    tpf = "C:/tweez/drive.tpf"
    out = call(
        "tweezers_command_sequence", {"spec_path": SPEC, "tpf_path_on_scope": tpf}
    )
    assert out["commands"] == list(command_sequence(plan(load_spec(SPEC)), tpf))


def test_file_first_reaches_the_driver():
    tpf = "C:/tweez/drive.tpf"
    normal = call(
        "tweezers_command_sequence", {"spec_path": SPEC, "tpf_path_on_scope": tpf}
    )["commands"]
    flipped = call(
        "tweezers_command_sequence",
        {"spec_path": SPEC, "tpf_path_on_scope": tpf, "file_first": True},
    )["commands"]
    assert normal != flipped
    assert f"LOAD_PATTERN {tpf}" in " ".join(flipped)


def test_write_tpf_emits_the_point_list(tmp_path):
    out_path = tmp_path / "drive.tpf"
    out = call(
        "tweezers_write_tpf", {"spec_path": SPEC, "out_path": str(out_path)}
    )
    assert out_path.exists()
    assert out["points"] == len(plan(load_spec(SPEC)).emitted_pattern())
    assert out["bytes"] == out_path.stat().st_size


def test_write_tpf_rejects_a_decimal_separator_it_cannot_use(tmp_path):
    out = call(
        "tweezers_write_tpf",
        {"spec_path": SPEC, "out_path": str(tmp_path / "x.tpf"), "decimal": ";"},
    )
    assert "error" in out
    assert not (tmp_path / "x.tpf").exists()


# ---- refusals survive the boundary -------------------------------------


def test_the_shipped_spec_does_not_advance_and_says_why():
    """The repository's own worked spec is BLOCKED, and that has to arrive as a
    result with reasons rather than as a tool error."""
    out = call("tweezers_plan", {"spec_path": SPEC})
    assert out["advances"] is False
    assert out["range_status"] == "BLOCKED"
    assert len(out["blockers"]) == 3
    assert all(isinstance(b, str) and b for b in out["blockers"])


def test_a_spec_the_planner_refuses_returns_blocked_not_an_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: bad\n"
        "pattern: {shape: circle, radius_um: 5.0, n_points: 100}\n"
        "loop: {switching_rate_hz: 100000, n_traps: 1}\n"
        "drive: {target_speed_um_s: 0}\n",
        encoding="utf-8",
    )
    out = call("tweezers_plan", {"spec_path": str(bad)})
    assert out["status"] == "BLOCKED"
    assert out["advances"] is False
    assert "target_speed_um_s" in out["reason"]


def test_a_pattern_shape_typo_is_named_rather_than_defaulted(tmp_path):
    """`build_pattern` refuses an unknown shape instead of falling back, and that
    refusal has to reach the caller as a reason, not as a tool error."""
    bad = tmp_path / "typo.yaml"
    bad.write_text(
        "name: typo\n"
        "pattern: {shape: kircle, radius_um: 5.0, n_points: 100}\n"
        "drive: {target_speed_um_s: 30}\n",
        encoding="utf-8",
    )
    out = call("tweezers_plan", {"spec_path": str(bad)})
    assert out["status"] == "BLOCKED"
    assert "unknown pattern shape" in out["reason"]


def test_a_waveform_outside_the_travel_is_refused_with_its_reason():
    out = call(
        "piezo_waveform_preview",
        {"kind": "sine", "n_samples": 1000, "amplitude_um": 5000.0},
    )
    assert out["check"] == "REFUSED"
    assert "outside travel" in out["reason"]

    # ...and the reason is the driver's own.
    with pytest.raises(WaveformError) as exc:
        sine(5000.0 * PM_PER_UM, 1000, 1, travel=CALIBRATED).check(CALIBRATED)
    assert out["reason"] == str(exc.value)


def test_a_waveform_inside_the_travel_passes_and_reports_the_fallback():
    out = call(
        "piezo_waveform_preview",
        {
            "kind": "sine",
            "n_samples": 1000,
            "amplitude_um": 5.0,
            "sample_period_s": 0.001,
        },
    )
    assert out["check"] == "OK"
    assert out["fits_within_travel"] is True
    assert out["duration_s"] == pytest.approx(1.0)
    # No travel was supplied, so the result has to say so rather than imply the
    # bounds were read off the controller.
    assert out["travel_supplied_by_caller"] is False
    assert "travel_note" in out


def test_an_unknown_generator_is_an_error_not_a_guess():
    out = call("piezo_waveform_preview", {"kind": "sawtooth", "n_samples": 100})
    assert "error" in out


def test_the_reference_command_set_is_the_recorded_one():
    out = call("piezo_reference_commands", {})
    assert out["total_recorded"] == 414
    assert "COM4" in out["source"]

    filtered = call("piezo_reference_commands", {"name_filter": "function.waveform"})
    assert 0 < filtered["count"] < out["total_recorded"]
    assert all("function.waveform" in c for c in filtered["commands"])


def test_piezo_read_state_answers_instead_of_raising():
    """The vendor DLL is absent from any machine that is not the microscope PC,
    and that is an answer. This test does not assume which machine it is on."""
    out = call("piezo_read_state", {})
    assert "available" in out
    if not out["available"]:
        assert "NOTICE" in out["note"]
        assert "DLL" in out["error"]


# ---- nothing is reached while a switch is off --------------------------


def test_tweezers_run_is_refused_and_keeps_the_commands():
    out = call(
        "tweezers_run",
        {"spec_path": SPEC, "tpf_path_on_scope": "C:/tweez/drive.tpf"},
    )
    assert out["refused"] is True
    assert out["switch"] == "allow_motion"
    assert ENV_MOTION in out["how_to_enable"]
    assert out["what_would_have_happened"]["commands"] == list(
        command_sequence(plan(load_spec(SPEC)), "C:/tweez/drive.tpf")
    )


def test_tweezers_run_opens_no_socket_while_a_switch_is_off(monkeypatch):
    import hardware.optical_tweezers as ot

    def explode(*a, **k):
        raise AssertionError("the tweezers driver was constructed despite a refusal")

    monkeypatch.setattr(ot, "OpticalTweezers", explode)
    out = call(
        "tweezers_run",
        {"spec_path": SPEC, "tpf_path_on_scope": "C:/tweez/drive.tpf"},
    )
    assert out["refused"] is True


def test_the_laser_switch_is_checked_as_well_as_motion():
    """allow_motion alone is not enough: the tweezers steer a trapping laser."""
    server = build(Switches(allow_motion=True, allow_laser=False))
    out = call(
        "tweezers_run",
        {"spec_path": SPEC, "tpf_path_on_scope": "C:/tweez/drive.tpf"},
        server=server,
    )
    assert out["refused"] is True
    assert out["switch"] == "allow_laser"
    assert ENV_LASER in out["how_to_enable"]


def test_both_switches_on_still_refuses_a_plan_that_does_not_advance(monkeypatch):
    """The switches are about permission; `advances` is about the plan. Passing
    the first must not bypass the second."""
    import hardware.optical_tweezers as ot

    def explode(*a, **k):
        raise AssertionError("a plan that does not advance reached the driver")

    monkeypatch.setattr(ot, "OpticalTweezers", explode)
    server = build(Switches(allow_motion=True, allow_laser=True))
    out = call(
        "tweezers_run",
        {"spec_path": SPEC, "tpf_path_on_scope": "C:/tweez/drive.tpf"},
        server=server,
    )
    assert out["refused"] is True
    assert out["switch"] is None
    assert out["reason"] == "the plan does not advance"
    assert out["blockers"]


def test_piezo_move_is_refused_and_keeps_the_target():
    out = call("piezo_move", {"target_um": 12.5})
    assert out["refused"] is True
    assert out["switch"] == "allow_motion"
    assert out["what_would_have_happened"]["target_um"] == 12.5


def test_piezo_move_loads_no_dll_while_the_switch_is_off(monkeypatch):
    import hardware.piezo_stage as ps

    def explode(*a, **k):
        raise AssertionError("the piezo driver was constructed despite a refusal")

    monkeypatch.setattr(ps, "PiezoStage", explode)
    out = call("piezo_move", {"target_um": 12.5})
    assert out["refused"] is True


def test_piezo_read_state_never_asks_for_motion(monkeypatch):
    """Even with both switches on, the read tool constructs the stage with
    allow_motion=False -- it has no reason to move anything."""
    import hardware.piezo_stage as ps

    seen: list[dict] = []

    def spy(*a, **k):
        seen.append(k)
        raise ps.PiezoStageError("controller DLL not found: spy")

    monkeypatch.setattr(ps, "PiezoStage", spy)
    server = build(Switches(allow_motion=True, allow_laser=True))
    out = call("piezo_read_state", {}, server=server)
    assert out["available"] is False
    assert seen == [{"allow_motion": False}]


# ---- the switches themselves -------------------------------------------


def test_switches_default_to_off():
    s = Switches()
    assert s.allow_motion is False
    assert s.allow_laser is False
    assert Switches.from_env({}) == s


def test_only_an_explicit_truthy_value_turns_a_switch_on():
    for value, expected in [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("maybe", False),
    ]:
        got = Switches.from_env({ENV_MOTION: value}).allow_motion
        assert got is expected, f"{value!r} -> {got}"


def test_a_refusal_names_the_switch_the_variable_and_the_action():
    r = Switches().require("allow_laser", "fire the trapping laser", power=1.0)
    assert r["switch"] == "allow_laser"
    assert r["action"] == "fire the trapping laser"
    assert ENV_LASER in r["how_to_enable"]
    assert r["what_would_have_happened"] == {"power": 1.0}


def test_an_enabled_switch_produces_no_refusal():
    assert Switches(allow_laser=True).require("allow_laser", "anything") is None
