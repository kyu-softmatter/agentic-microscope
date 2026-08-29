"""Python control for the Prior/Queensgate NPC-D piezo stage controller (Nanobench 6000).

Wraps the vendor ctypes DLL adapter in hardware/piezo/vendor/. **The two DLLs it
loads are not published here** -- they are vendor-licensed and were removed on
2026-08-28. Obtain the NPC-D Digital Controller Interface DLL release (2.7.9 is
what this was written and tested against) from Prior/Queensgate and copy
controller_interface.dll and controller_interface64.dll out of its
controller_interface/bin/Windows/ into hardware/piezo/vendor/. Constructing
PiezoStage without them raises with those instructions. See NOTICE.md.

Neither vendor document is in this repo either -- not the protocol reference
(NPC-D_Series_Digital_Controller_Interface_Library_2.7.9.pdf) and not the
command-set manual ("NPC-D-6xx0 NanoMechanism Controller Interface Command Set
And Control System"). So the names and signatures used here were read off the
controller itself with config/piezo/verify_piezo_commands.py -- see
WAVEFORM_PROTOCOL. That is the better source anyway: the manual covers the whole
NPC-D family, this is what *this* controller answered.

Connection is a comms-link string: a COM port ("COM4"), an IP address
("192.168.0.7"), or "sim:/NPC6330" to run against the DLL's built-in simulator.
A COM port is the bare name with no scheme -- "COM4", not "com:/COM4" -- and
list_devices() does not enumerate a USB-serial controller (it answers [] on
COM4), so the link has to be named rather than discovered.

**The port is exclusive.** The vendor NanoBench 6000 GUI holds it for as long as
it has a session open, and connect() then fails with "could not open comms link";
close the GUI's session first.

CONFIRMED ON THE REAL CONTROLLER (2026-08-27, COM4)
---------------------------------------------------
DLL 2.7.9, firmware 6.7.8, 3 channels = x, y, z, stage SP-XYZ-600 serial 107866,
travel 0..600 um per axis (stage.position.calibrated-range.*), servo period 20 us
(controller.sampling-time.get), closed loop on, calibration preset 6 "Customer 1".
All three axes report stage.mode.digital-command = 1 and
stage.mode.analogue-command = 0: the controller acts on *this* interface and
ignores the analogue input from Dev1/ao2. A position round trip measured ~0.4 ms
median, which is the ceiling on any host-timed drive.
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

#: Argument layout of the commands that move the stage, read off the real
#: controller on 2026-08-27 (firmware 6.7.8 over COM4) with
#: ``GetCommandParameters``/``GetCommandParameterName``. This is what replaces
#: the missing command-set manual, and it improves on it: the manual covers the
#: whole NPC-D family, this is what *this* controller answered.
#:
#: Re-read it with::
#:
#:     python config/piezo/verify_piezo_commands.py --link COM4 --unlock 0xDEC0DED --describe function
#:
#: **None of it is visible until the security level is raised** (see ``unlock``).
#: Locked, the controller reports 188 commands of which exactly one is a ``.set``
#: -- ``controller.security.user.set``. ``stage.position.command.set`` is not
#: merely unavailable, it is *invisible*, and asking for its signature answers
#: "Invalid command name", which reads like "this controller cannot do it" and
#: is not what it means. Unlocked to User: 414 commands.
WAVEFORM_PROTOCOL = {
    # one command per sample; index is the position in the channel buffer
    "function.waveform.data.set": ("channel", "index", "value"),
    "function.waveform.command-transition.set": ("channel", "index", "value"),
    # per channel
    "function.waveform.count.set": ("channel", "value"),          # samples/iteration
    "function.waveform.waveform-start.set": ("channel", "value"),
    "function.waveform.waveform-end.set": ("channel", "value"),
    "function.waveform.repeat-start.set": ("channel", "value"),
    "function.waveform.repeat-end.set": ("channel", "value"),
    "function.waveform.iterations.set": ("channel", "value"),
    "function.waveform.sample-period.set": ("channel", "value"),  # seconds
    "function.waveform.repeat-count.set": ("channel", "value"),   # 0 = forever
    # flags, one per target -- NOT zero arguments, which is what the old
    # function_start()/function_stop() sent
    "function.command.start": ("snapshot", "internal-channel0",
                               "channel1", "channel2", "channel3"),
    "function.command.stop": ("snapshot", "internal-channel0",
                              "channel1", "channel2", "channel3"),
    "function.command.pause": ("internal-channel0",
                               "channel1", "channel2", "channel3"),
    "function.command.unpause": ("internal-channel0",
                                 "channel1", "channel2", "channel3"),
    # the direct, non-generator move
    "stage.position.command.set": ("channel", "value"),
}

#: Vendor security-level access codes, read out of the NanoBench GUI own config
#: file, "C:/Program Files (x86)/NanoBench 6000/data/config.ini", section
#: [SecurityLevels]. Fixed per-level constants the vendor chose, not secrets
#: anyone picks -- but they stay non-implicit here: ``unlock()`` still takes the
#: code as an argument, so nothing raises the level by accident.
#:
#: The controller parses the code as a number, so the "0x" prefix is required:
#: DEC0DED alone comes back "Not enough parameters for command", 0xDEC0DED
#: returns security = User. "user" was confirmed on COM4 on 2026-08-27;
#: "super-user" is straight from the config file and has not been tried.
ACCESS_CODES = {"user": "0xDEC0DED", "super-user": "0xB01DFACE"}

#: What ``function.waveform.data.set`` values *mean*. **Unknown, and known not
#: to be picometres**, which is the one thing WAVEFORM_PROTOCOL above does not
#: tell you: it gives the arity, not the unit.
#:
#: Measured 2026-08-27 on COM4. A 100-sample sine of +/-5 um about x = 300 um was
#: uploaded in picometres -- the unit ``stage.position.command.set`` takes -- with
#: the playback window set to 0..99 and the sample period to 10 ms. Every sample
#: read back byte-identical with ``function.waveform.data.get``. Playing it swung
#: the axis over a measured **313.9 um**, roughly 31x the commanded 10 um
#: peak-to-peak, with centre crossings 1-25 ms apart rather than the requested
#: 1 s. The readback is not the problem: 2000 static reads at 400 um spanned
#: 74 nm with no outlier beyond 1 um.
#:
#: Two candidates, neither tested: the value is a DAC code rather than a
#: distance (300 um of picometres wraps around a 24-bit code, which would
#: scatter samples across the travel exactly like this), or it is an offset
#: rather than an absolute position. The way to tell, cheaply and boundedly, is
#: a *constant* waveform -- every sample the same -- which cannot oscillate
#: whatever the unit, so wherever the stage parks is the answer. Do that on a
#: lateral axis, never on Z.
#:
#: Until this is filled in, function_start() refuses. upload_waveform() does
#: not: loading a buffer moves nothing, and being able to load one is how the
#: question gets answered.
WAVEFORM_DATA_UNITS = None

#: Command names on this controller carry hyphens -- stage.mode.digital-command.get,
#: function.waveform-generator.sample-period.get -- which the first version of this
#: pattern could not match, so the whole hyphenated half of the real command set
#: read as "not in the reference".
_COMMAND_LINE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+$", re.MULTILINE)

#: Longest string any GetXxx() result here plausibly is. Only a bad read asks for
#: more; see _read_string.
_MAX_STRING = 65536


def reference_commands():
    """Command names from reference/npcd-command-set.md, as a set.

    As of 2026-08-27 that file is what this controller answered at User security
    level (414 names), not the family-wide guess it used to be. Still worth
    diffing against find_commands(): at the base security level the controller
    reports only 188 of them, so the diff is how you see whether the level is
    raised.
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
    if size > _MAX_STRING:
        raise PiezoStageError(
            f"the DLL asked for a {size}-byte string buffer, which is not a size "
            "any of these results has -- treating it as a bad read rather than "
            "allocating it"
        )
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
        if not Path(dll_path).exists():
            raise PiezoStageError(
                f"controller DLL not found: {dll_path}\n"
                "This repository does not publish the vendor DLLs. Obtain the "
                "NPC-D Digital Controller Interface DLL release (2.7.9) from "
                "Prior/Queensgate and copy controller_interface.dll and "
                "controller_interface64.dll out of its "
                "controller_interface/bin/Windows/ into hardware/piezo/vendor/. "
                "See NOTICE.md."
            )
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

    def command_parameters(self, command_name, with_units=False):
        """List (name, units_type, units) for each parameter of a command.

        ``with_units`` is off by default, and that is the fix for the crash that
        made this function unusable on real hardware:
        GetCommandParameterUnitsType and its three siblings raise "OSError:
        access violation writing 0x...0001" -- the buffer *length* argument is
        being dereferenced as a pointer, so the real 2.7.9 signature is not the
        one hardware/piezo/vendor/dll_adapter.py declares. Seen against both the
        DLL simulator and the live controller on COM4, where it took down the
        pre-move signature check in try_hardware.py and stopped a drive that was
        otherwise ready to run.

        Dropping the units costs nothing measurable: on the runs where the call
        answered instead of crashing, it answered an empty string for every
        parameter and result of the position commands (2026-08-27, firmware
        6.7.8). So these units are not knowable from this API either way, and
        get_position_pm()'s picometre assumption rests on a range cross-check
        instead -- the controller reports 6.0e8 for the SP-XYZ-600's 600 um
        travel, which is picometres and nothing else.

        Pass with_units=True to try the fragile calls anyway; they raise OSError
        when they misbehave, so guard the call.
        """
        h = self._dll.dllHandle
        return self._signature(
            command_name, with_units, h.GetCommandParameters,
            h.GetCommandParameterName, h.GetCommandParameterUnitsType,
            h.GetCommandParameterUnits,
        )

    def _signature(self, command_name, with_units, count_fn, name_fn,
                   units_type_fn, units_fn):
        inst = self._dll.dllInstanceHandle
        name_c = command_name.encode("utf-8")
        count = count_fn(inst, name_c)
        if count < 0:
            raise PiezoStageError(f"unknown command: {command_name!r}")
        out = []
        for i in range(count):
            item_name = _read_string(name_fn, inst, name_c, i)
            units_type = units = None
            if with_units:
                units_type = _read_string(units_type_fn, inst, name_c, i)
                units = _read_string(units_fn, inst, name_c, i)
            out.append((item_name, units_type, units))
        return out

    def command_results(self, command_name, with_units=False):
        """List (name, units_type, units) for each result of a command.

        ``with_units`` off by default for the reason in command_parameters().
        """
        h = self._dll.dllHandle
        return self._signature(
            command_name, with_units, h.GetCommandResults,
            h.GetCommandResultName, h.GetCommandResultUnitsType,
            h.GetCommandResultUnits,
        )

    def do_command(self, command):
        """Issue one or more '\\n'-separated commands; returns [(name, value), ...]."""
        results = self._dll.DoCommand(command)
        if results and results[0] == "Connection not initialised":
            raise PiezoStageError(results[0])
        return results

    def get_result(self, name, results):
        """Pull a named value out of a do_command() result list, or None.

        do_command returns either [(name, value), ...] or a one-element list
        holding an error string, and the second shape used to reach the
        unpacking below and raise "ValueError: too many values to unpack",
        which buried the real failure -- a badly formatted access code, for
        one. Now it surfaces as PiezoStageError with the message in it.
        """
        for item in results:
            if not isinstance(item, tuple):
                raise PiezoStageError(f"command failed: {item}")
            result_name, value = item
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

    def set_position_pm(self, channel, value_pm):
        """``stage.position.command.set`` -- **this moves the stage.**

        Picometres, matching get_position_pm(). Behind the allow_motion gate,
        and it needs the security level raised (unlock): while locked the
        command is invisible and answers "Invalid command name".

        No range check here on purpose -- the bound to check against is the
        stage's, not this call's, and hardware/piezo_waveform.py owns it
        (StageTravel.check). Read the real bounds with travel_pm().
        """
        self._require_motion(f"stage.position.command.set on channel {channel}")
        results = self.do_command(
            f"stage.position.command.set {channel} {value_pm:.0f}"
        )
        value = self.get_result("value", results)
        if value is None:
            raise PiezoStageError(f"stage.position.command.set failed: {results}")
        return float(value)

    def set_position_um(self, channel, value_um):
        return self.set_position_pm(channel, value_um * 1.0e6) * 1.0e-6

    def travel_pm(self, channel):
        """(min, max) of the calibrated travel in picometres, from the controller.

        The number to build a waveform against, rather than a constant in this
        repo: on the SP-XYZ-600 it reads 0 .. 6.0e8 pm = 600 um per axis, which
        is also the cross-check that positions here really are picometres.
        """
        lo = self.get_result("value", self.do_command(
            f"stage.position.calibrated-range.minimum.get {channel}"))
        hi = self.get_result("value", self.do_command(
            f"stage.position.calibrated-range.maximum.get {channel}"))
        if lo is None or hi is None:
            raise PiezoStageError(
                f"could not read the calibrated range of channel {channel}")
        return float(lo), float(hi)

    def security_level(self):
        return self.get_result("security", self.do_command("controller.security.user.get"))

    def unlock(self, code):
        """Raise the controller's security level, which is what makes the .set
        half of the command set exist at all.

        ``code`` is a fixed per-level vendor constant -- ACCESS_CODES records
        where they come from -- and it **must carry its 0x prefix**: the
        controller parses it as a number, so "DEC0DED" fails with "Not enough
        parameters for command" while "0xDEC0DED" returns User.

        Confirmed 2026-08-27 on firmware 6.7.8: 188 visible commands before,
        414 after, and stage.position.command.set plus the whole
        function.waveform.* set are among the ones that appear. Note the level
        is **controller-side state that outlives the session** -- the vendor
        GUI leaves it at User -- so a fresh connect() may already be unlocked.
        Call lock() when done if that matters.
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
        """``stage.mode.get`` -- the raw mode and status words for one channel.

        Answered on 2026-08-27: mode 0x0327 on channel 1, 0x0323 on 2 and 3,
        status 0x0B17 on all three. mode_flags() is the readable form and is
        what to use; this is here for the raw words.
        """
        return self.do_command(f"stage.mode.get {channel}")

    #: The mode bits worth naming, as their own per-bit queries.
    MODE_FLAGS = (
        "digital-command",
        "analogue-command",
        "closed-loop",
        "is-sensor-only",
        "freeze-servo-output",
    )

    def mode_flags(self, channel=1):
        """Which command input the controller is acting on, as a dict of 0/1.

        This is the query kb/systems/current.md had open from 2026-08-19: the
        analogue cable from Dev1/ao2 is still connected, and whether the
        controller acts on it depends on this. **Answered 2026-08-27 on all
        three channels: digital-command 1, analogue-command 0** -- the
        controller acts on this interface and ignores the analogue input.

        Read-only in practice. There is no stage.mode.digital-command.set even
        at User level; what does appear there is stage.mode-mask.set and
        stage.mode-only.set, which write the raw mode word, and
        stage.mode.freeze-servo-output.set. This module deliberately wraps none
        of them -- flipping a servo mode under a mounted sample is not a thing
        to make one call away.
        """
        out = {}
        for flag in self.MODE_FLAGS:
            results = self.do_command(f"stage.mode.{flag}.get {channel}")
            value = self.get_result("value", results)
            out[flag] = None if value is None else int(value)
        return out

    # ---- waveform generator (function.*) --------------------------------

    def function_state(self):
        """``function.state.get`` -- what the waveform generator is doing.

        Unlike the optical tweezers, this interface can be *read*. Whatever a
        playback is doing is observable, so a drive here can be verified rather
        than assumed.
        """
        return self.do_command("function.state.get")

    def is_playing(self, channel):
        """Is the generator currently playing on this channel?"""
        state = self.function_state()
        value = self.get_result(f"running-channel{channel}", state)
        if value is None:
            raise PiezoStageError(
                f"function.state.get reported no running-channel{channel}: {state}"
            )
        return value != "0"

    def playback_window(self, channel):
        """``(start, end, count)`` of the generator's playback window.

        **Read this before any start.** Out of the box this controller reports
        start 0, end **500000** and count 1: the window spans the whole
        500 001-sample buffer while exactly one sample has been written. Loading
        100 samples and starting would play the other 499 901 -- whatever is in
        the buffer -- at 20 us a step. upload_waveform() therefore writes the
        window as well as the samples, and function_start() refuses a window
        that reaches past the loaded count.
        """
        values = []
        for command in ("function.waveform.waveform-start.get",
                        "function.waveform.waveform-end.get",
                        "function.waveform.count.get"):
            value = self.get_result("value", self.do_command(f"{command} {channel}"))
            if value is None:
                raise PiezoStageError(f"{command} failed on channel {channel}")
            values.append(int(float(value)))
        return tuple(values)

    def _function_flags(self, channels, snapshot=None, internal=False):
        """Build the flag list function.command.* actually takes.

        Five flags for start/stop (snapshot first), four for pause/unpause --
        see WAVEFORM_PROTOCOL. Sending these commands bare, which is what this
        module used to do, answers "Invalid command name" while locked and is
        wrong in any case.
        """
        wanted = {int(c) for c in channels}
        bad = wanted - {1, 2, 3}
        if bad:
            raise PiezoStageError(f"function channels are 1..3; got {sorted(bad)}")
        bits = [] if snapshot is None else ["1" if snapshot else "0"]
        bits.append("1" if internal else "0")
        bits += ["1" if ch in wanted else "0" for ch in (1, 2, 3)]
        return " ".join(bits)

    def function_stop(self, channels=(1, 2, 3), snapshot=True, internal=True):
        """Stop playback. Always allowed -- it reduces motion. Stops everything
        by default, which is what you want from a stop."""
        return self.do_command(
            "function.command.stop "
            + self._function_flags(channels, snapshot=snapshot, internal=internal)
        )

    def function_pause(self, channels=(1, 2, 3), internal=True):
        """Pause playback. Always allowed -- it reduces motion."""
        return self.do_command(
            "function.command.pause " + self._function_flags(channels, internal=internal)
        )

    def function_unpause(self, channels=(), internal=False):
        self._require_motion("function.command.unpause")
        return self.do_command(
            "function.command.unpause "
            + self._function_flags(channels, internal=internal)
        )

    def function_start(self, channels=(), snapshot=False, internal=False,
                       force=False):
        """Start playback on the given 1-based channels. **This moves the stage.**

        Needs the security level raised (unlock) as well as allow_motion.

        **Refuses while WAVEFORM_DATA_UNITS is None**, which is now: the unit
        the generator reads its samples in is not picometres and is not known,
        and assuming picometres produced a 314 um excursion from a 10 um
        request on 2026-08-27. Read that constant before passing ``force``.

        Also refuses, per channel, if the playback window reaches past the
        sample count -- the default window is the whole 500 001-sample buffer,
        so starting without setting it plays uninitialised memory as a
        trajectory. ``force=True`` skips both checks.
        """
        self._require_motion("function.command.start")
        if WAVEFORM_DATA_UNITS is None and not force:
            raise PiezoStageError(
                "refusing function.command.start: WAVEFORM_DATA_UNITS is None. "
                "The generator does not read its samples in picometres -- a "
                "+/-5 um sine uploaded as picometres swung the axis 314 um on "
                "2026-08-27. Establish the unit with a constant waveform on a "
                "lateral axis first, then set the constant. force=True to "
                "override, on a lateral axis, watching the stage"
            )
        if not force:
            for channel in channels:
                start, end, count = self.playback_window(channel)
                if end > count - 1 or start > end:
                    raise PiezoStageError(
                        f"channel {channel} playback window is {start}..{end} but "
                        f"only {count} sample(s) are declared loaded: starting "
                        f"would play {end - count + 1} sample(s) of whatever is "
                        "in the buffer. upload_waveform() sets the window; pass "
                        "force=True only if you set it yourself"
                    )
        return self.do_command(
            "function.command.start "
            + self._function_flags(channels, snapshot=snapshot, internal=internal)
        )

    def _set_value(self, command, channel, value):
        results = self.do_command(f"{command} {channel} {value}")
        got = self.get_result("value", results)
        if got is None:
            raise PiezoStageError(f"{command} failed: {results}")
        return got

    def upload_waveform(self, waveform, travel, sample_period_s=None,
                        iterations=None, repeat_count=None, batch=32, verify=3):
        """Upload a Waveform into the hardware generator. Does **not** start it.

        Range-checks against ``travel`` first and refuses rather than clipping.
        Nothing here moves the stage -- only function_start() does -- so this is
        not behind the allow_motion gate. It does overwrite the channel's
        buffer, so it refuses while that channel is playing, where an edit would
        be followed live.

        Needs the security level raised (unlock): while locked,
        function.waveform.data.set is invisible and answers "Invalid command
        name" rather than anything that sounds like a permission problem.

        **The samples go up in whatever unit the caller built them in, and the
        generator does not read picometres** -- see WAVEFORM_DATA_UNITS. This
        function will happily load a buffer that plays back wrong, which is why
        function_start() is the thing that refuses, not this.

        The protocol is one command per sample (WAVEFORM_PROTOCOL), so a long
        waveform is a lot of round trips; they go out newline-separated, ``batch``
        samples per DoCommand. At the ~0.4 ms round trip measured on COM4, 1000
        samples is a second or two and 50 000 is minutes. So prefer a slow
        sample period and few points -- the controller's servo period is 20 us,
        meaning it can play a waveform far faster than this can load one.

        ``iterations`` and ``repeat_count`` are left alone unless passed. The
        controller has both (function.waveform.iterations.set, and
        .repeat-count.set whose own description says 0 = repeat forever) and how
        the two interact has not been tested here, so nothing is defaulted.

        ``verify`` spot-checks that many samples back out of the controller with
        function.waveform.data.get. Returns the number of samples uploaded.
        """
        # NOTE the sample count is not the only thing that decides what plays:
        # waveform-start/end and repeat-start/end bound the window, they default
        # to the whole buffer, and they are set below.
        waveform.check(travel)
        channel = waveform.channel
        if self.is_playing(channel):
            raise PiezoStageError(
                f"channel {channel} is playing -- stop it before overwriting its "
                "waveform buffer, or the stage follows the edit"
            )
        if sample_period_s is not None:
            if sample_period_s <= 0:
                raise PiezoStageError("sample period must be positive")
            self._set_value("function.waveform.sample-period.set", channel,
                            f"{float(sample_period_s):.12g}")
        # The window, not just the count -- see playback_window(). Left stale,
        # these point at the whole buffer and the generator plays it.
        self._set_value("function.waveform.count.set", channel, len(waveform))
        self._set_value("function.waveform.waveform-start.set", channel, 0)
        self._set_value("function.waveform.waveform-end.set", channel,
                        len(waveform) - 1)
        self._set_value("function.waveform.repeat-start.set", channel, 0)
        self._set_value("function.waveform.repeat-end.set", channel,
                        len(waveform) - 1)
        if iterations is not None:
            self._set_value("function.waveform.iterations.set", channel,
                            int(iterations))
        if repeat_count is not None:
            self._set_value("function.waveform.repeat-count.set", channel,
                            int(repeat_count))

        samples = waveform.samples
        for start in range(0, len(samples), batch):
            chunk = samples[start:start + batch]
            block = "\n".join(
                f"function.waveform.data.set {channel} {start + i} {value:.0f}"
                for i, value in enumerate(chunk)
            )
            results = self.do_command(block)
            if len(results) != len(chunk):
                raise PiezoStageError(
                    f"function.waveform.data.set: sent {len(chunk)} samples from "
                    f"index {start} but the controller returned {len(results)} "
                    f"result(s): {results[:4]}"
                )

        if verify:
            step = max(1, len(samples) // max(1, int(verify)))
            tolerance = max(travel.resolution_pm, 1.0)
            for index in range(0, len(samples), step):
                got = self.get_result("value", self.do_command(
                    f"function.waveform.data.get {channel} {index}"))
                if got is None:
                    raise PiezoStageError(
                        f"could not read sample {index} back from channel {channel}")
                if abs(float(got) - samples[index]) > tolerance:
                    raise PiezoStageError(
                        f"sample {index} read back as {float(got):.0f} pm, not the "
                        f"{samples[index]:.0f} pm uploaded (tolerance "
                        f"{tolerance:.0f} pm, one quantisation step)"
                    )
        return len(samples)
