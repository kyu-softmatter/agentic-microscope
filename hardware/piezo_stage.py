"""Python control for the Prior/Queensgate NPC-D piezo stage controller (Nanobench 6000).

Wraps the vendor ctypes DLL adapter, copied into hardware/piezo/vendor/
(original source archived outside this repo -- see manual/README.md; the
vendor's full C/C++/Python SDK and driver installers no longer live in this
repo, only the manuals do). Full protocol reference:
manual/Piezo Stage/Controller Interface DLL & Drivers/NPC-D Digital Controller Interface DLL Production Release/NPC-D_Series_Digital_Controller_Interface_Library_2.7.9.pdf

The controller command set is not bundled in this repo (see "NPC-D-6xx0 NanoMechanism
Controller Interface Command Set And Control System" in the vendor docs) -- available
commands should be confirmed with find_commands()/describe_command() against the real
controller before relying on a command name.

Connection is a comms-link string: a COM port ("COM4"), an IP address
("192.168.0.7"), or "sim:/NPC6330" to run against the DLL's built-in simulator.
"""

import ctypes
import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).parent / "piezo" / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
import dll_adapter  # noqa: E402  vendor module, path set above

_DLL_FILENAMES = {
    8: "controller_interface64.dll",
    4: "controller_interface.dll",
}

#: Extracted command-name list, with its provenance and its superset caveat.
REFERENCE_COMMANDS = Path(__file__).parent.parent / "reference" / "npcd-command-set.md"

#: Argument layout for ``function.waveform.data.set`` -- how many arguments it
#: takes and in what order. **Not documented anywhere in this repo**: the
#: "NPC-D-6xx0 NanoMechanism Controller Interface Command Set And Control
#: System" manual is not here, only the DLL library manual. While this is None,
#: upload_waveform() refuses rather than sending guessed arguments to a stage
#: that can drive an objective into a coverslip -- the same stance as
#: ``lunf_power.PROTOCOL``.
#:
#: Two ways to fill it in, neither needing the missing manual:
#:   1. ``config/piezo/verify_piezo_commands.py`` prints the real signature,
#:      read straight out of the DLL via command_parameters().
#:   2. the vendor's ``function_waveform_demo`` example, whose source is in the
#:      archived SDK (see manual/README.md).
WAVEFORM_PROTOCOL = None

_COMMAND_LINE = re.compile(r"^[a-z]+(?:\.[a-z0-9]+)+$", re.MULTILINE)


def reference_commands():
    """Command names from reference/npcd-command-set.md, as a set.

    A superset across the NPC-D family, not this controller's command set --
    see that file's caveat. Used to cross-check what find_commands() reports.
    """
    if not REFERENCE_COMMANDS.exists():
        return set()
    # Matched by shape rather than by tracking code fences: a bare dotted
    # lowercase token on its own line is a command and nothing else in the file
    # looks like one (prose keeps them in backticks, the quoted shell block is
    # blockquoted, headings start with #).
    return set(
        _COMMAND_LINE.findall(REFERENCE_COMMANDS.read_text(encoding="utf-8"))
    )


class PiezoStageError(RuntimeError):
    """Raised for controller DLL load, connection, or command failures."""


def _read_string(fn, *leading_args):
    """Call a vendor GetXxx(..., buffer, bufferLen) function and decode its result.

    Follows the two-call sizing pattern used throughout the vendor DLL API:
    the first call with a too-small buffer reports the required size.
    """
    probe = ctypes.create_string_buffer(2)
    size = fn(*leading_args, probe, 1)
    if size < 0:
        return None
    buf = ctypes.create_string_buffer(size + 1)
    fn(*leading_args, buf, size + 1)
    return buf.value.decode("utf-8")


class PiezoStage:
    """Controls a Prior/Queensgate NPC-D digital piezo stage controller."""

    def __init__(self, dll_path=None, allow_motion=False):
        """``allow_motion=False`` -- the default -- makes every call that can
        move the stage raise. Reads, discovery and waveform inspection stay
        available, so the verification script can run against a live controller
        with a sample in place."""
        if dll_path is None:
            filename = _DLL_FILENAMES[ctypes.sizeof(ctypes.c_voidp)]
            dll_path = str(_VENDOR_DIR / filename)
        self.allow_motion = allow_motion
        self._dll = dll_adapter.DllAdapter()
        if not self._dll.Init(dll_path):
            raise PiezoStageError(f"failed to load controller DLL: {dll_path}")

    def _require_motion(self, what):
        if not self.allow_motion:
            raise PiezoStageError(
                f"refusing {what}: constructed without allow_motion=True. "
                "Check clearance and the travel bounds first"
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._dll.Uninit()

    def dll_version(self):
        return self._dll.GetDllVersion()

    def list_devices(self):
        return self._dll.GetDevices()

    def connect(self, device):
        if not self._dll.OpenSession(device):
            raise PiezoStageError(f"could not open comms link to {device!r}")

    def disconnect(self):
        self._dll.CloseSession()

    def is_connected(self):
        return self._dll.IsSessionOpen()

    def channels(self):
        """Number of stage channels supported by the connected controller."""
        n = self._dll.dllHandle.GetChannels(self._dll.dllInstanceHandle)
        if n < 0:
            raise PiezoStageError("no controller connection open")
        return n

    def find_commands(self, filter=""):
        """List available command names, optionally restricted to a prefix."""
        h, inst = self._dll.dllHandle, self._dll.dllInstanceHandle
        n = h.FindCommands(inst, filter.encode("utf-8"))
        if n < 0:
            raise PiezoStageError("no controller connection open")
        return [_read_string(h.GetCommand, inst, i) for i in range(n)]

    def describe_command(self, command_name):
        h, inst = self._dll.dllHandle, self._dll.dllInstanceHandle
        name_c = command_name.encode("utf-8")
        description = _read_string(h.GetCommandDescription, inst, name_c)
        if description is None:
            raise PiezoStageError(f"unknown command: {command_name!r}")
        return description

    def command_parameters(self, command_name):
        """List (name, units_type, units) for each parameter of a command."""
        h, inst = self._dll.dllHandle, self._dll.dllInstanceHandle
        name_c = command_name.encode("utf-8")
        count = h.GetCommandParameters(inst, name_c)
        if count < 0:
            raise PiezoStageError(f"unknown command: {command_name!r}")
        params = []
        for i in range(count):
            pname = _read_string(h.GetCommandParameterName, inst, name_c, i)
            units_type = _read_string(h.GetCommandParameterUnitsType, inst, name_c, i)
            units = _read_string(h.GetCommandParameterUnits, inst, name_c, i)
            params.append((pname, units_type, units))
        return params

    def command_results(self, command_name):
        """List (name, units_type, units) for each result of a command."""
        h, inst = self._dll.dllHandle, self._dll.dllInstanceHandle
        name_c = command_name.encode("utf-8")
        count = h.GetCommandResults(inst, name_c)
        if count < 0:
            raise PiezoStageError(f"unknown command: {command_name!r}")
        results = []
        for i in range(count):
            rname = _read_string(h.GetCommandResultName, inst, name_c, i)
            units_type = _read_string(h.GetCommandResultUnitsType, inst, name_c, i)
            units = _read_string(h.GetCommandResultUnits, inst, name_c, i)
            results.append((rname, units_type, units))
        return results

    def do_command(self, command):
        """Issue one or more '\\n'-separated commands; returns [(name, value), ...]."""
        results = self._dll.DoCommand(command)
        if results and results[0] == "Connection not initialised":
            raise PiezoStageError(results[0])
        return results

    def get_result(self, name, results):
        """Pull a named value out of a do_command() result list, or None."""
        for result_name, value in results:
            if result_name == name:
                return value
        return None

    def identity(self):
        """Controller firmware version string, e.g. 'major.minor.build'."""
        results = self.do_command("identity.software.version.get")
        raw = self.get_result("version", results)
        if raw is None:
            return None
        version = int(raw)
        major = (version >> 24) & 0xFF
        minor = (version >> 16) & 0xFF
        build = version & 0xFFFF
        return f"{major}.{minor}.{build}"

    def get_position_pm(self, channel):
        """Measured stage position in picometres for the given channel (1-based)."""
        results = self.do_command(f"stage.position.measured.get {channel}")
        value = self.get_result("value", results)
        if value is None:
            raise PiezoStageError(f"stage.position.measured.get failed: {results}")
        return float(value)

    def get_position_um(self, channel):
        return self.get_position_pm(channel) * 1.0e-6

    def security_level(self):
        return self.get_result("security", self.do_command("controller.security.user.get"))

    def unlock(self, code):
        """Raises the controller's security level (needed for .set/move commands).

        The access code is a fixed per-level constant defined by the vendor
        software config (not a secret the user chooses) -- pass it in rather
        than hardcoding it here.
        """
        results = self.do_command(f"controller.security.user.set {code}")
        level = self.get_result("security", results)
        if level is None:
            raise PiezoStageError(f"unlock failed: {results}")
        return level

    def lock(self):
        self.do_command("controller.security.lock")

    # ---- discovery: what this controller actually supports --------------

    def verify_command_set(self):
        """Cross-check ``find_commands()`` against the extracted reference.

        Returns ``(supported, reference_only, controller_only)``. The reference
        is a family-wide superset, so ``reference_only`` is expected to be
        non-empty and is not an error -- it is how you learn which commands are
        for other NPC-D models. ``controller_only`` is the interesting one: the
        DLL knew a name that the extraction missed.
        """
        supported = set(c for c in self.find_commands() if c)
        reference = reference_commands()
        return (
            sorted(supported),
            sorted(reference - supported),
            sorted(supported - reference),
        )

    def describe_family(self, prefix):
        """Full signature of every command starting with ``prefix``.

        ``{name: {"description", "parameters", "results"}}``, with parameters
        and results as ``(name, units_type, units)`` triples straight from the
        DLL. This is what replaces the missing command-set manual.
        """
        out = {}
        for name in self.find_commands(prefix):
            if not name:
                continue
            out[name] = {
                "description": self.describe_command(name),
                "parameters": self.command_parameters(name),
                "results": self.command_results(name),
            }
        return out

    def position_units(self, command="stage.position.measured.get"):
        """Units the controller reports for a position command.

        Library manual 5.2: a distance may come back in picometres for a linear
        stage or picoradians for an angular one, and applications "should always
        check the units". ``get_position_pm`` assumes picometres; this is how to
        find out whether that assumption holds here.
        """
        return self.command_results(command)

    def stage_mode(self, channel=1):
        """``stage.mode.get`` -- which command input the controller is acting on.

        This is the query kb/systems/current.md asks for and never got: the
        analogue cable from ``Dev1/ao2`` is still connected, and whether the
        controller acts on it depends on this setting. Note there is no
        ``stage.mode.set`` in the command set, so the mode is readable from here
        but not changeable.
        """
        return self.do_command(f"stage.mode.get {channel}")

    # ---- waveform generator (function.*) --------------------------------

    def function_state(self):
        """``function.state.get`` -- what the waveform generator is doing.

        Unlike the optical tweezers, this interface can be *read*. Whatever a
        playback is doing is observable, so a drive here can be verified rather
        than assumed.
        """
        return self.do_command("function.state.get")

    def function_stop(self):
        """Stop playback. Always allowed -- it reduces motion."""
        return self.do_command("function.command.stop")

    def function_pause(self):
        """Pause playback. Always allowed -- it reduces motion."""
        return self.do_command("function.command.pause")

    def function_unpause(self):
        self._require_motion("function.command.unpause")
        return self.do_command("function.command.unpause")

    def function_start(self):
        """Start playback. **This moves the stage.**"""
        self._require_motion("function.command.start")
        return self.do_command("function.command.start")

    def upload_waveform(self, waveform, travel):
        """Refuses, by design, until WAVEFORM_PROTOCOL is known.

        Validates the waveform against ``travel`` first, so the range check is
        still useful today, then raises rather than sending guessed arguments to
        ``function.waveform.data.set``. Build waveforms with
        hardware/piezo_waveform.py; confirm the signature with
        config/piezo/verify_piezo_commands.py.
        """
        waveform.check(travel)
        if WAVEFORM_PROTOCOL is None:
            raise PiezoStageError(
                "upload_waveform is not implemented: the argument layout of "
                "function.waveform.data.set is undocumented in this repo "
                "(WAVEFORM_PROTOCOL is None). Run "
                "config/piezo/verify_piezo_commands.py --describe function "
                "against the controller to read the real signature, then fill "
                "it in. Refusing to guess -- this command moves a stage."
            )
        raise PiezoStageError("WAVEFORM_PROTOCOL set but no encoder implemented")
