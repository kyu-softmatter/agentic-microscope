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

    def __init__(self, dll_path=None):
        if dll_path is None:
            filename = _DLL_FILENAMES[ctypes.sizeof(ctypes.c_voidp)]
            dll_path = str(_VENDOR_DIR / filename)
        self._dll = dll_adapter.DllAdapter()
        if not self._dll.Init(dll_path):
            raise PiezoStageError(f"failed to load controller DLL: {dll_path}")

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
