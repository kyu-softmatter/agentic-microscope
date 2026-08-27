"""Microscope configuration control through Micro-Manager (pymmcore-plus).

The third control surface alongside hardware/optical_tweezers.py (TCP) and
hardware/piezo_stage.py (vendor DLL) -- but the opposite kind: everything here
is a device Micro-Manager *does* own, so there is no vendor protocol to
reverse. Reading and writing configuration is plain MMCore
``getProperty``/``setProperty``/``setConfig``, which is why this module is
mostly guardrails rather than transport.

Which devices that covers on this system is settled, not assumed -- the
2026-08-12 pymmcore-plus load on the microscope PC read every device in
``config/micromanager/DMD_dualcam_LUNF.cfg`` live (kb/systems/current.md >
devices_not_in_mm_config): the Ti2-E stand and its children (Nosepiece,
FilterTurret1/2, CondenserTurret, LightPath, IntermediateMagnification,
LappMainBranch1, PFS, PFSOffset, ZDrive, XYStage), both Kinetix cameras,
SpectraIII/AuraIII, the CSU-W1 group (Dichroic, Filter_Red=EM1,
Filter_Blue=EM2, Bright, Port, Shutter), and the DMD (MightexPolygon1000).
Per the 2026-08-11 project decision the NIS-Elements path is not used.

Not covered, because they are not MM devices: the Splitter (manual only), the
LUN-F XL per-line power (hardware/lunf_power.py), the piezo stage
(hardware/piezo_stage.py), the tweezers (hardware/optical_tweezers.py).

STAGING
-------
docs/07-roadmap.md Phase 5 stages this deliberately, and the split shows up in
the API:

    5a  read state          snapshot() · state() · groups() · current_preset()
    5b  compare            diff() · preset_diff()
    5c  generate a preset  define_preset() · save_config()   (core-side only)
    5d  apply, revertible  apply() · set_preset() · temporarily()

Only 5d touches hardware, and it is off unless you pass ``allow_write=True``.
5a-5c are safe against a live instrument. Every write reads back and raises on
mismatch rather than trusting that the device moved.

VERIFIED
--------
Against pymmcore-plus's bundled demo config on macOS/arm64
(tests/test_microscope.py) -- the same surrogate calibration/mm_live.py uses,
and for the same reason: the real adapters only exist on the microscope PC.
The demo config carries a state device per real-device kind we care about
(Objective~Nosepiece, Dichroic/Emission/Excitation~FilterTurret1 + EM1/EM2,
Path~LightPath, Z, XY, Autofocus~PFS) plus ConfigGroups, so the MMCore
semantics under test are the ones the real .cfg exercises. What it cannot
check is per-adapter behaviour: NikonTi2 turret move times, whether PVCAM
rejects a property mid-acquisition, CSU-W1 wheel settling.

Note the NikonTi2 adapter needs ``Ti2_Mic_Driver.dll`` present in the MM
folder or every stand child fails to load -- the ``mmcore install`` build is
missing it; copy it from the lab's ``C:\\Program Files\\Micro-Manager-2.0``
(kb/systems/current.md, closing note).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from math import isclose
from pathlib import Path

from pymmcore_plus import CMMCorePlus, DeviceType, PropertyType

#: Device-adapter strings that must never appear in a loaded configuration,
#: mapped to why. MM initializes an analog-output device by writing 0 V, and
#: ``Dev1/ao2`` is still physically cabled to the NPC-D piezo controller's
#: analog input (0-400 um <-> 0-10 V) -- loading it would command the stage to
#: 0 um. This repo drives that stage over USB/DLL instead
#: (hardware/piezo_stage.py); the analog route is ignored, which is not the
#: same as safe to write. See kb/systems/current.md > devices_not_in_mm_config
#: > "piezo stage" > hazard.
FORBIDDEN_DEVICES = {
    "NIDAQAO-Dev1/ao2": (
        "analog line cabled to the NPC-D piezo controller -- MM would write "
        "0 V on initialize and drive the stage to 0 um"
    ),
}

#: Devices whose properties gate laser emission. Writing a blanking line opens
#: a class-4 shutter, so these need their own opt-in on top of allow_write.
#: The LUN-F blanking lines are Dev1/port0/line2/4/6/8 for 405/488/561/640
#: (config/micromanager/DMD_dualcam_LUNF.cfg, ConfigGroup LaserLine).
LASER_DEVICES = frozenset({"LUNF-Blanking"})

#: Devices whose motion can drive glass into glass. An objective change swings
#: a different working distance under a sample that has not moved, and a Z move
#: does the same thing directly; either can crash a 100x Oil front element into
#: the coverslip. Neither is a configuration knob you flip to see what happens,
#: so they need their own opt-in -- and with PFS holding focus, changing the
#: Nosepiece under it is the specific case to think twice about.
#:
#: The Nosepiece carries a second, unrelated consequence that this gate also
#: covers by accident, and that is worth knowing before overriding it: an
#: objective change silently invalidates **both** optical-tweezers calibrations
#: -- the Tweez GUI's px->um Magnification and its AOD trapping-field response
#: (Tweez300UserManual pp. 28-32, 35-38). Neither is readable or settable over
#: the tweezers' TCP interface, so afterwards every TRAP_POSITION in um lands
#: somewhere else and nothing on either side reports it. See
#: kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md.
COLLISION_DEVICES = frozenset({"Nosepiece", "ZDrive", "PFSOffset"})

#: Devices this repo does not exclusively own. The optical-tweezers GUI loads a
#: Kinetix, uses it, then releases it (user, 2026-08-26), and PVCAM hands a
#: camera to one process at a time -- so whoever opens it first locks the other
#: out. Consequences worth knowing before debugging a load failure:
#:
#:   - While the Tweez GUI holds the camera, initializing it here fails.
#:   - While this module holds it, the Tweez GUI cannot show a live image, which
#:     blocks its GUI calibration (it needs to see trapped beads) and visual
#:     trap placement. The GUI *can* run cameraless (manual p. 34), and TCP
#:     commands need no image, so only the interactive parts are lost.
#:
#: The ordering that follows: let the Tweez GUI take the camera first, do the
#: calibration and trap setup, release, then load a configuration here.
SHARED_DEVICES = {
    "Kinetix_red": "optical-tweezers GUI (loads then releases it)",
    "Kinetix_blue": "optical-tweezers GUI (loads then releases it)",
}

#: Read-only in practice even where the adapter does not say so: identity
#: strings, not configuration. Excluded from snapshot()/diff() so a state
#: comparison is not swamped by them.
_IDENTITY_PROPERTIES = frozenset({"Description", "Name", "HubID"})

#: Read-back tolerance for numeric properties, relative and absolute.
#:
#: A numeric write cannot be checked by string equality: MM echoes floats in
#: the adapter's own formatting (write ``"50"`` to a stage Position, read back
#: ``"50.0000"``), and devices quantise to their own step -- a Kinetix rounds
#: exposure to a row time, PFSOffset to an encoder count. 0.1% is loose enough
#: for that and still tight enough that a write which did not land at all
#: fails. Change.after always carries the value the device actually reports, so
#: a caller needing exactness compares it directly.
READBACK_RTOL = 1e-3
READBACK_ATOL = 1e-6

_NUMERIC_TYPES = frozenset({PropertyType.Float, PropertyType.Integer})


class MicroscopeError(RuntimeError):
    """Raised for a refused write, a failed read-back, or a hazard match."""


@dataclass(frozen=True)
class Setting:
    """One ``(device, property, value)`` triple, as MMCore stores them."""

    device: str
    property: str
    value: str


@dataclass(frozen=True)
class Change:
    """A property that would move, or did. ``before == after`` means no-op."""

    device: str
    property: str
    before: str
    after: str

    @property
    def is_noop(self) -> bool:
        return self.before == self.after


def _as_settings(wanted: Mapping | Iterable) -> tuple[Setting, ...]:
    """Accept the three shapes callers naturally have: a nested mapping
    ``{device: {prop: value}}``, a flat mapping ``{(device, prop): value}``,
    or any iterable of Setting/3-tuples.
    """
    if isinstance(wanted, Mapping):
        out: list[Setting] = []
        for key, value in wanted.items():
            if isinstance(value, Mapping):
                out.extend(Setting(key, p, str(v)) for p, v in value.items())
            else:
                device, prop = key
                out.append(Setting(device, prop, str(value)))
        return tuple(out)
    return tuple(
        item if isinstance(item, Setting) else Setting(item[0], item[1], str(item[2]))
        for item in wanted
    )


def check_config_file(cfg_path: str | Path) -> None:
    """Refuse a ``.cfg`` that declares a device in FORBIDDEN_DEVICES.

    Checked as text before loading, because the damage in the piezo case
    happens during ``initializeDevice`` -- once the core has loaded it there is
    nothing left to prevent.
    """
    text = Path(cfg_path).read_text(encoding="utf-8", errors="replace")
    hits = [name for name in FORBIDDEN_DEVICES if name in text]
    if hits:
        detail = "; ".join(f"{n}: {FORBIDDEN_DEVICES[n]}" for n in hits)
        raise MicroscopeError(f"{cfg_path} declares a forbidden device -- {detail}")


def _load_failure_hint(cfg_path: str | Path, exc: Exception) -> str:
    """Turn a config-load failure into something actionable.

    The most likely cause on this system is a camera already owned by another
    process -- PVCAM is exclusive and the tweezers GUI takes a Kinetix. That
    surfaces as an opaque adapter error, so name the suspect.
    """
    text = str(exc)
    contended = [d for d in SHARED_DEVICES if d in text]
    if contended:
        who = "; ".join(f"{d} <- {SHARED_DEVICES[d]}" for d in contended)
        return (
            f"{cfg_path}: failed to load ({text}). {contended} is shared and "
            f"PVCAM is exclusive -- check whether it is already held: {who}"
        )
    return f"{cfg_path}: failed to load ({text})"


class Microscope:
    """Reads and (opt-in) writes Micro-Manager device configuration.

    ``allow_write=False`` -- the default -- makes every mutating call raise, so
    stages 5a-5c can run against a live instrument without a way to move it.
    ``allow_laser=True`` is additionally required for LASER_DEVICES, and
    ``allow_motion=True`` for COLLISION_DEVICES. Three separate switches
    because they are three different accidents.
    """

    def __init__(
        self,
        core: CMMCorePlus,
        *,
        allow_write: bool = False,
        allow_laser: bool = False,
        allow_motion: bool = False,
    ):
        self.core = core
        self.allow_write = allow_write
        self.allow_laser = allow_laser
        self.allow_motion = allow_motion

    @classmethod
    def connect(
        cls,
        cfg_path: str | Path | None = None,
        *,
        allow_write: bool = False,
        allow_laser: bool = False,
        allow_motion: bool = False,
        mm_dir: str | Path | None = None,
    ) -> Microscope:
        """Load a system configuration. ``None`` loads pymmcore-plus's bundled
        demo config -- a smoke test, not a measurement.

        ``mm_dir`` pins the device-adapter folder, needed on the microscope PC
        to point at the lab's MM install rather than the ``mmcore install``
        build (see module docstring on Ti2_Mic_Driver.dll).
        """
        core = CMMCorePlus()
        if mm_dir is not None:
            core.setDeviceAdapterSearchPaths([str(mm_dir)])
        if cfg_path is None:
            core.loadSystemConfiguration()
        else:
            check_config_file(cfg_path)
            try:
                core.loadSystemConfiguration(str(cfg_path))
            except Exception as exc:
                raise MicroscopeError(_load_failure_hint(cfg_path, exc)) from exc
        return cls(
            core,
            allow_write=allow_write,
            allow_laser=allow_laser,
            allow_motion=allow_motion,
        )

    def close(self) -> None:
        self.core.unloadAllDevices()

    def __enter__(self) -> Microscope:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ---- 5a: read state -------------------------------------------------

    def devices(self) -> dict[str, str]:
        """Loaded device label -> DeviceType name (``Core`` included)."""
        return {
            label: self.core.getDeviceType(label).name
            for label in self.core.getLoadedDevices()
        }

    def settable_properties(self, device: str) -> tuple[str, ...]:
        """Properties on ``device`` that configuration can actually move.

        Excludes read-only properties, pre-init properties (settable only
        before ``initializeDevice``, so not a runtime knob), and identity
        strings.
        """
        return tuple(
            prop
            for prop in self.core.getDevicePropertyNames(device)
            if prop not in _IDENTITY_PROPERTIES
            and not self.core.isPropertyReadOnly(device, prop)
            and not self.core.isPropertyPreInit(device, prop)
        )

    def snapshot(self) -> tuple[Setting, ...]:
        """Every settable property on every loaded device, current value.

        This is the revert basis for temporarily() and the left-hand side of
        diff(). Uses one cached system-state read rather than a property-by-
        property sweep, so it is one round trip per device tree.
        """
        state = {
            (device, prop): value for device, prop, value in self.core.getSystemState()
        }
        out: list[Setting] = []
        for device in self.core.getLoadedDevices():
            for prop in self.settable_properties(device):
                value = state.get((device, prop))
                if value is not None:
                    out.append(Setting(device, prop, value))
        return tuple(out)

    def state(self) -> dict[str, str]:
        """The turret/wheel/path position of every state device, by label.

        The human-legible half of a snapshot: what an operator would read off
        the stand -- objective, filter turrets, light path, CSU-W1 port. Core
        roles (Camera, Shutter, Focus) are folded in under ``Core.<role>``
        because they are configuration too and MM stores them the same way.
        """
        out: dict[str, str] = {}
        for label, kind in self.devices().items():
            if kind == DeviceType.StateDevice.name:
                out[label] = self.core.getStateLabel(label)
        for role in ("Camera", "Shutter", "Focus", "XYStage", "AutoFocus"):
            try:
                out[f"Core.{role}"] = self.core.getProperty("Core", role)
            except Exception:  # role not defined on this core
                continue
        return out

    def groups(self) -> dict[str, tuple[str, ...]]:
        """ConfigGroup name -> its preset names."""
        return {
            group: tuple(self.core.getAvailableConfigs(group))
            for group in self.core.getAvailableConfigGroups()
        }

    def current_preset(self, group: str) -> str | None:
        """Which preset of ``group`` the hardware currently matches.

        ``None`` when the live state matches no preset -- the normal result
        after a manual tweak, and the case 5b has to report rather than
        silently pick the nearest.
        """
        return self.core.getCurrentConfig(group) or None

    def preset_settings(self, group: str, preset: str) -> tuple[Setting, ...]:
        return tuple(
            Setting(device, prop, value)
            for device, prop, value in self.core.getConfigData(group, preset)
        )

    # ---- 5b: compare ----------------------------------------------------

    def diff(self, wanted: Mapping | Iterable) -> tuple[Change, ...]:
        """What ``wanted`` would change, hardware untouched.

        No-ops are kept in the result (``Change.is_noop``) so a caller can show
        "already correct" instead of an empty diff that reads as "nothing to
        do because I could not tell".
        """
        return tuple(
            Change(
                s.device,
                s.property,
                self.core.getProperty(s.device, s.property),
                s.value,
            )
            for s in _as_settings(wanted)
        )

    def preset_diff(self, group: str, preset: str) -> tuple[Change, ...]:
        return self.diff(self.preset_settings(group, preset))

    # ---- 5c: generate a preset, nothing applied -------------------------

    def define_preset(
        self, group: str, preset: str, settings: Mapping | Iterable
    ) -> tuple[Setting, ...]:
        """Define ``group``/``preset`` in the core's configuration table.

        Core-side only -- defining a preset does not move hardware, so this
        stays available with ``allow_write=False`` on purpose. Pair it with
        save_config() to hand a human a ``.cfg`` to apply, which is what 5c
        is for.
        """
        resolved = _as_settings(settings)
        if group not in self.core.getAvailableConfigGroups():
            self.core.defineConfigGroup(group)
        for s in resolved:
            self._check_value(s)
            self.core.defineConfig(group, preset, s.device, s.property, s.value)
        return resolved

    def save_config(self, path: str | Path) -> Path:
        """Write the core's current configuration out as a ``.cfg``."""
        out = Path(path)
        self.core.saveSystemConfiguration(str(out))
        return out

    # ---- 5d: apply, revertible ------------------------------------------

    def set_property(self, device: str, prop: str, value) -> Change:
        """Write one property, then read it back and confirm it took."""
        setting = Setting(device, prop, str(value))
        self._require_write(setting)
        self._check_value(setting)
        before = self.core.getProperty(device, prop)
        self.core.setProperty(device, prop, setting.value)
        self.core.waitForDevice(device)
        after = self.core.getProperty(device, prop)
        if not self._readback_ok(device, prop, setting.value, after):
            raise MicroscopeError(
                f"{device}.{prop}: wrote {setting.value!r} but reads back {after!r}"
            )
        return Change(device, prop, before, after)

    def _readback_ok(self, device: str, prop: str, wanted: str, got: str) -> bool:
        """Did the device land on ``wanted``? Numeric properties compared with
        tolerance, everything else exactly. See READBACK_RTOL."""
        if got == wanted:
            return True
        if self.core.getPropertyType(device, prop) not in _NUMERIC_TYPES:
            return False
        try:
            return isclose(
                float(got), float(wanted), rel_tol=READBACK_RTOL, abs_tol=READBACK_ATOL
            )
        except ValueError:
            return False

    def apply(self, settings: Mapping | Iterable) -> tuple[Change, ...]:
        """Write several properties in the order given.

        Order is the caller's, not sorted -- turret/shutter sequencing matters
        (close the shutter before moving a cube, not after) and this module has
        no model of which order is safe for a given path. Stops at the first
        failure and raises; already-applied changes are returned on the
        exception's ``applied`` attribute so a caller can roll back.
        """
        done: list[Change] = []
        for s in _as_settings(settings):
            try:
                done.append(self.set_property(s.device, s.property, s.value))
            except Exception as exc:
                exc.applied = tuple(done)  # type: ignore[attr-defined]
                raise
        return tuple(done)

    def set_preset(self, group: str, preset: str) -> tuple[Change, ...]:
        """Apply a ConfigGroup preset via MMCore, reporting what moved.

        Goes through ``setConfig`` rather than looping over apply() so MM's own
        ordering and any adapter-side grouping are preserved.
        """
        settings = self.preset_settings(group, preset)
        for s in settings:
            self._require_write(s)
        wanted = {(s.device, s.property): s.value for s in settings}
        before = {
            (s.device, s.property): self.core.getProperty(s.device, s.property)
            for s in settings
        }
        self.core.setConfig(group, preset)
        self.core.waitForConfig(group, preset)
        changes = tuple(
            Change(
                s.device,
                s.property,
                before[(s.device, s.property)],
                self.core.getProperty(s.device, s.property),
            )
            for s in settings
        )
        mismatched = [
            c
            for c in changes
            if not self._readback_ok(
                c.device, c.property, wanted[(c.device, c.property)], c.after
            )
        ]
        if mismatched:
            detail = ", ".join(f"{c.device}.{c.property}={c.after!r}" for c in mismatched)
            raise MicroscopeError(f"{group}/{preset} did not fully take: {detail}")
        return changes

    @contextmanager
    def temporarily(self, settings: Mapping | Iterable):
        """Apply ``settings``, yield, then restore the previous values.

        Restore runs on the way out including on exception, in reverse order,
        and is best-effort: a device that fails to come back raises
        MicroscopeError *after* the remaining restores are attempted, rather
        than abandoning the rest of the state mid-revert.
        """
        resolved = _as_settings(settings)
        previous = [
            Setting(s.device, s.property, self.core.getProperty(s.device, s.property))
            for s in resolved
        ]
        self.apply(resolved)
        try:
            yield self
        finally:
            failures: list[str] = []
            for s in reversed(previous):
                try:
                    self.set_property(s.device, s.property, s.value)
                except Exception as exc:
                    failures.append(f"{s.device}.{s.property}: {exc}")
            if failures:
                raise MicroscopeError("revert incomplete -- " + "; ".join(failures))

    # ---- guards ---------------------------------------------------------

    def _require_write(self, setting: Setting) -> None:
        if setting.device in FORBIDDEN_DEVICES:
            raise MicroscopeError(
                f"{setting.device} is forbidden -- {FORBIDDEN_DEVICES[setting.device]}"
            )
        if not self.allow_write:
            raise MicroscopeError(
                f"refusing to write {setting.device}.{setting.property}: "
                "constructed read-only (pass allow_write=True)"
            )
        if setting.device in LASER_DEVICES and not self.allow_laser:
            raise MicroscopeError(
                f"{setting.device}.{setting.property} gates laser emission: "
                "pass allow_laser=True and confirm the interlock/power state first"
            )
        if setting.device in COLLISION_DEVICES and not self.allow_motion:
            raise MicroscopeError(
                f"{setting.device}.{setting.property} moves glass toward the "
                "sample: pass allow_motion=True and check clearance/PFS first"
            )

    def _check_value(self, setting: Setting) -> None:
        """Validate against the adapter's own allowed values / limits.

        Catches a typo'd label before it reaches the device. MMCore would also
        reject it, but the error it raises does not list what was allowed.
        """
        device, prop, value = setting.device, setting.property, setting.value
        if prop not in self.core.getDevicePropertyNames(device):
            raise MicroscopeError(f"{device} has no property {prop!r}")
        allowed = tuple(self.core.getAllowedPropertyValues(device, prop))
        if allowed and value not in allowed:
            raise MicroscopeError(
                f"{device}.{prop}={value!r} not allowed; allowed: {list(allowed)}"
            )
        if self.core.hasPropertyLimits(device, prop):
            low = self.core.getPropertyLowerLimit(device, prop)
            high = self.core.getPropertyUpperLimit(device, prop)
            try:
                numeric = float(value)
            except ValueError:
                raise MicroscopeError(
                    f"{device}.{prop} takes a number in [{low}, {high}], got {value!r}"
                ) from None
            if not low <= numeric <= high:
                raise MicroscopeError(
                    f"{device}.{prop}={numeric} outside [{low}, {high}]"
                )
