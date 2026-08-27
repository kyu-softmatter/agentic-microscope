"""Tests for hardware.microscope against pymmcore-plus's bundled demo config.

Same arrangement as tests/test_calibration_mm_live.py: skipped without
pymmcore-plus or a device-adapter bundle (``mmcore install``), since this repo
targets an offline work PC and only the live-MM modules need either. The demo
config is a surrogate for the lab's DMD_dualcam_LUNF.cfg -- it exercises the
MMCore semantics (state devices, ConfigGroups, allowed values, read-back) but
not NikonTi2/PVCAM/CSU-W1 adapter behaviour. See the module docstring.

The hazard tests below need neither, and run everywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LAB_CFG = REPO / "config" / "micromanager" / "DMD_dualcam_LUNF.cfg"


# ---- hazards: no MM install needed ------------------------------------

pytest.importorskip("pymmcore_plus")

from hardware import microscope as mscope  # noqa: E402
from hardware.microscope import Microscope, MicroscopeError, Setting  # noqa: E402


def test_forbidden_device_is_the_piezo_analog_line():
    """The one hazard this module exists to hold: kb/systems/current.md >
    devices_not_in_mm_config > piezo stage > hazard."""
    assert "NIDAQAO-Dev1/ao2" in mscope.FORBIDDEN_DEVICES


def test_check_config_file_rejects_a_cfg_declaring_the_piezo_ao_line(tmp_path):
    bad = tmp_path / "bad.cfg"
    bad.write_text(
        "Device,NIDAQHub,NIDAQ,NIDAQHub\n"
        "Device,PiezoZ,NIDAQ,NIDAQAO-Dev1/ao2\n",
        encoding="utf-8",
    )
    with pytest.raises(MicroscopeError, match="forbidden device"):
        mscope.check_config_file(bad)


def test_the_labs_real_config_is_clean():
    """DMD_dualcam_LUNF.cfg deliberately contains no AO device -- assert it,
    so a later edit that adds one fails here instead of on the bench."""
    mscope.check_config_file(LAB_CFG)


def test_laser_blanking_device_is_gated():
    assert "LUNF-Blanking" in mscope.LASER_DEVICES


# ---- live demo core ---------------------------------------------------


@pytest.fixture
def scope():
    """A fresh read-only Microscope on the demo config, per test."""
    try:
        s = Microscope.connect(None)
    except Exception as exc:
        pytest.skip(f"no usable Micro-Manager device-adapter install: {exc}")
    yield s
    s.close()


@pytest.fixture
def writable(scope):
    scope.allow_write = True
    return scope


# -- 5a: read state


def test_devices_reports_labels_and_types(scope):
    devices = scope.devices()
    assert devices["Objective"] == "StateDevice"
    assert devices["Camera"] == "CameraDevice"


def test_settable_properties_drops_readonly_and_identity(scope):
    props = scope.settable_properties("Objective")
    assert "Label" in props and "State" in props
    assert "Description" not in props  # read-only
    assert "Name" not in props  # identity


def test_snapshot_covers_settable_properties_only(scope):
    snap = scope.snapshot()
    assert Setting("Objective", "Label", "Nikon 10X S Fluor") in snap
    assert not [s for s in snap if s.property in ("Name", "Description", "HubID")]


def test_state_reads_turret_labels_and_core_roles(scope):
    state = scope.state()
    assert state["Objective"] == "Nikon 10X S Fluor"
    assert state["Dichroic"] == "400DCLP"
    assert state["Core.Camera"] == "Camera"


def test_groups_lists_presets(scope):
    groups = scope.groups()
    assert set(groups["Channel"]) == {"DAPI", "FITC", "Rhodamine", "Cy5"}


def test_current_preset_is_none_when_state_matches_nothing(writable):
    assert writable.current_preset("Channel") == "DAPI"
    writable.set_property("Dichroic", "Label", "Q505LP")
    assert writable.current_preset("Channel") is None


def test_preset_settings_reads_the_config_table(scope):
    settings = scope.preset_settings("Channel", "DAPI")
    assert Setting("Dichroic", "Label", "400DCLP") in settings


# -- 5b: compare


def test_diff_reports_before_and_after_without_writing(scope):
    changes = scope.diff({"Objective": {"Label": "Nikon 40X Plan Fluor ELWD"}})
    assert changes[0].before == "Nikon 10X S Fluor"
    assert changes[0].after == "Nikon 40X Plan Fluor ELWD"
    assert not changes[0].is_noop
    # hardware untouched
    assert scope.state()["Objective"] == "Nikon 10X S Fluor"


def test_diff_keeps_noops_so_already_correct_is_visible(scope):
    (change,) = scope.diff([Setting("Objective", "Label", "Nikon 10X S Fluor")])
    assert change.is_noop


def test_preset_diff_against_a_matching_preset_is_all_noop(scope):
    assert all(c.is_noop for c in scope.preset_diff("Channel", "DAPI"))


def test_diff_accepts_flat_and_nested_mappings_alike(scope):
    nested = scope.diff({"Objective": {"Label": "Objective-2"}})
    flat = scope.diff({("Objective", "Label"): "Objective-2"})
    assert nested == flat


# -- read-only refusals


def test_read_only_scope_refuses_set_property(scope):
    with pytest.raises(MicroscopeError, match="constructed read-only"):
        scope.set_property("Objective", "Label", "Objective-2")
    assert scope.state()["Objective"] == "Nikon 10X S Fluor"


def test_read_only_scope_refuses_set_preset(scope):
    with pytest.raises(MicroscopeError, match="constructed read-only"):
        scope.set_preset("Channel", "FITC")


def test_forbidden_device_is_refused_even_with_write_allowed(writable, monkeypatch):
    monkeypatch.setitem(mscope.FORBIDDEN_DEVICES, "Objective", "test hazard")
    with pytest.raises(MicroscopeError, match="is forbidden"):
        writable.set_property("Objective", "Label", "Objective-2")


def test_laser_device_needs_its_own_opt_in(writable, monkeypatch):
    monkeypatch.setattr(mscope, "LASER_DEVICES", frozenset({"Objective"}))
    with pytest.raises(MicroscopeError, match="gates laser emission"):
        writable.set_property("Objective", "Label", "Objective-2")
    writable.allow_laser = True
    assert writable.set_property("Objective", "Label", "Objective-2").after == "Objective-2"


def test_collision_device_needs_its_own_opt_in(writable, monkeypatch):
    """The demo config has no Nosepiece, so stand in for it -- the gate under
    test is the guard, not the device name."""
    monkeypatch.setattr(mscope, "COLLISION_DEVICES", frozenset({"Objective"}))
    with pytest.raises(MicroscopeError, match="moves glass toward the sample"):
        writable.set_property("Objective", "Label", "Objective-2")
    writable.allow_motion = True
    assert writable.set_property("Objective", "Label", "Objective-2").after == "Objective-2"


def test_the_stands_objective_turret_and_z_are_gated():
    assert {"Nosepiece", "ZDrive"} <= mscope.COLLISION_DEVICES


# -- value validation


def test_bad_label_is_rejected_with_the_allowed_list(writable):
    with pytest.raises(MicroscopeError, match="not allowed; allowed:"):
        writable.set_property("Objective", "Label", "Nikon 100X Oil")


def test_unknown_property_is_rejected(writable):
    with pytest.raises(MicroscopeError, match="no property"):
        writable.set_property("Objective", "Nosepiece", "1")


def test_out_of_range_numeric_is_rejected(writable):
    """Exposure carries adapter limits; pick a value far outside them."""
    with pytest.raises(MicroscopeError, match="outside|not allowed"):
        writable.set_property("Camera", "Exposure", 1e12)


# -- 5d: apply and revert


def test_set_property_moves_the_turret_and_reads_back(writable):
    change = writable.set_property("Objective", "Label", "Nikon 40X Plan Fluor ELWD")
    assert (change.before, change.after) == (
        "Nikon 10X S Fluor",
        "Nikon 40X Plan Fluor ELWD",
    )
    assert writable.state()["Objective"] == "Nikon 40X Plan Fluor ELWD"


def test_numeric_readback_tolerates_the_adapters_own_formatting(writable):
    """MM echoes a Float property in the adapter's format -- write '50', read
    back '50.0000'. An exact string check called that a failed write."""
    change = writable.set_property("Z", "Position", 50)
    assert change.after == "50.0000"


def test_numeric_readback_still_catches_a_write_that_did_not_land(writable):
    ok = writable._readback_ok
    assert ok("Z", "Position", "50", "50.0000")
    assert ok("Camera", "Exposure", "10.0", "10.005")  # quantised, within 0.1%
    assert not ok("Z", "Position", "50", "0.0000")
    assert not ok("Camera", "Exposure", "10.0", "12.0")


def test_string_readback_stays_exact(writable):
    assert writable._readback_ok("Objective", "Label", "Objective-2", "Objective-2")
    assert not writable._readback_ok("Objective", "Label", "Objective-2", "Objective-4")


def test_apply_writes_in_the_order_given(writable):
    changes = writable.apply(
        [
            Setting("Objective", "Label", "Objective-2"),
            Setting("Dichroic", "Label", "Q505LP"),
        ]
    )
    assert [c.device for c in changes] == ["Objective", "Dichroic"]
    assert writable.state()["Dichroic"] == "Q505LP"


def test_apply_reports_what_it_already_did_when_it_fails(writable):
    with pytest.raises(MicroscopeError) as excinfo:
        writable.apply(
            [
                Setting("Objective", "Label", "Objective-2"),
                Setting("Dichroic", "Label", "not-a-filter"),
            ]
        )
    applied = excinfo.value.applied
    assert [c.device for c in applied] == ["Objective"]


def test_set_preset_applies_a_config_group(writable):
    changes = writable.set_preset("Channel", "FITC")
    assert writable.current_preset("Channel") == "FITC"
    assert any(c.device == "Dichroic" and not c.is_noop for c in changes)


def test_temporarily_restores_previous_state(writable):
    before = writable.state()["Objective"]
    with writable.temporarily({"Objective": {"Label": "Objective-4"}}):
        assert writable.state()["Objective"] == "Objective-4"
    assert writable.state()["Objective"] == before


def test_temporarily_restores_even_when_the_body_raises(writable):
    before = writable.state()["Objective"]
    with pytest.raises(ZeroDivisionError):
        with writable.temporarily({"Objective": {"Label": "Objective-4"}}):
            1 / 0
    assert writable.state()["Objective"] == before


# -- 5c: generate a preset without applying it


def test_define_preset_does_not_move_hardware(scope):
    before = scope.state()["Objective"]
    scope.define_preset(
        "Proposed", "probe-tracer", {"Objective": {"Label": "Objective-2"}}
    )
    assert "probe-tracer" in scope.groups()["Proposed"]
    assert scope.state()["Objective"] == before


def test_define_preset_validates_values(scope):
    with pytest.raises(MicroscopeError, match="not allowed"):
        scope.define_preset("Proposed", "bad", {"Objective": {"Label": "nope"}})


def test_save_config_round_trips_the_new_preset(scope, tmp_path):
    scope.define_preset(
        "Proposed", "probe-tracer", {"Objective": {"Label": "Objective-2"}}
    )
    out = scope.save_config(tmp_path / "proposed.cfg")
    text = out.read_text(encoding="utf-8")
    assert "ConfigGroup,Proposed,probe-tracer,Objective,Label,Objective-2" in text
