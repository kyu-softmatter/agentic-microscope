"""Python control for the Aresis Tweez 300/305/310 optical tweezers.

Uses the documented TCP/IP external control interface (Tweez300UserManual.pdf,
chapter "External Control (TCP/IP)", p.65). The Tweez 300 GUI application must
already be running and connected to its System Manager and the Tweez 305/310
device -- this class only sends the same text commands the GUI logs in its
Status Pane > TCP/IP Svr panel. It does not talk to the device directly and
cannot start the System Manager, unlock laser safety interlocks, or bypass any
hardware safety measures.

Command syntax and return codes are reproduced from the manual's Command
Reference; the wire format (raw text lines terminated by "\\r\\n") matches the
vendor's own sample: %ProgramFiles%\\Aresis\\Tweez300\\Samples\\TCP_IP\\Python\\TrapMoveCircle.py
"""

import socket
import time

_RETURN_CODES = {
    0: "success",
    -10: "invalid command line",
    -11: "unknown command",
    -12: "general command failure",
    -13: "command timeout",
    -14: "another command active",
    -15: "system manager not connected",
    -16: "device not ready",
    -17: "GUI not ready",
    -18: "GUI locked",
    -19: "calibration active",
    -20: "requested resource not supported",
    -21: "requested resource not available due to some other active process",
    -22: "no resource selected",
    -23: "resource not valid for this operation",
    -24: "element already exists",
    -25: "no such element",
    -26: "element locked",
    -27: "invalid parameters",
}


#: A name no operator would choose, used only as a readiness probe target.
_PROBE_TRAP = "__readiness_probe__"

#: Statuses that mean the GUI is up and processing commands. 0 is success, and
#: -25 ("no such element") and -22 ("no resource selected") both prove the
#: command reached a working GUI, which is the only thing a probe can establish
#: on an interface with no query command of any kind.
#:
#: -22 is here on measurement, not on the manual. Against Tweez300GUI on the
#: microscope PC (Kinetix A24M723015-PVCAM, licence Permanent, empty project)
#: on 2026-08-27, ``TRAP_DELETE`` of a name that does not exist answers **-22**,
#: not the -25 the Command Reference implies. Same session, same socket:
#: ``SIMPLE_TRAP_CREATE`` and a ``TRAP_DELETE`` of the trap it made both
#: answered 0, so the GUI was fully live while the probe was calling it dead.
#: Without -22 here, ``is_ready()`` is False on a healthy GUI, so
#: ``wait_until_ready()`` always times out and ``find_gui_port()`` always
#: returns None -- and the caller is then told no GUI answered at all, which is
#: the misleading diagnosis this probe exists to prevent.
READY_STATUSES = frozenset({0, -25, -22})

#: Statuses that mean "up, but not usable yet". Distinguishing these from a
#: dead socket is the whole point of probing: they tell you whether to keep
#: waiting (-16, -17, -19) or go fix something by hand (-15, -18).
NOT_READY_STATUSES = {
    -15: "System Manager not connected -- start it and connect the device",
    -16: "device not ready",
    -17: "GUI not ready",
    -18: "GUI locked -- unlock it in the GUI",
    -19: "calibration active -- finish or cancel it",
}

#: "another command active" -- the GUI rejected this command because it was
#: still busy with the previous one. Rejected, not queued and not executed,
#: which is what makes re-sending it safe. See send_command().
BUSY_STATUS = -14

#: Minimum wall time between two sends on one socket.
#:
#: Back-to-back sends race the GUI and come back -14. Measured on the
#: microscope PC on 2026-08-27, 24 readiness probes per gap: 16/24 came back
#: -14 with no gap at all, and 0/24 at every gap from 2 ms up (2, 5, 10, 20,
#: 50, 100). 10 ms is that floor with margin, and costs 60 ms across the
#: six-command drive sequence.
#:
#: A gap alone is not enough, though, and that is why BUSY_RETRIES exists: the
#: probe those numbers came from is one of the cheap commands. The same session
#: had a paced ``SIMPLE_TRAP_CREATE`` come back -14 at a 10 ms gap, so the
#: settling time is per-command and this constant cannot be tuned to cover the
#: slowest one without guessing.
MIN_COMMAND_GAP_S = 0.010

#: Re-sends allowed on BUSY_STATUS, and the wait before each.
#:
#: Safe here specifically because -14 is an *explicit* rejection: the GUI
#: answered, and its answer was "I did not run this". A missing reply is the
#: case that must never be retried -- there the command's fate is unknown, and
#: several commands in this set are incremental (``TRAP_POSITION_REL``,
#: ``TRAP_PATT_ROTATION_REL``, ``TRAP_PATT_SCALE_REL``), so re-sending one that
#: did land would move the trap twice. send_command() keeps those apart.
BUSY_RETRIES = 6
BUSY_BACKOFF_S = 0.05


class TweezersError(RuntimeError):
    """Raised when the Tweez 300 GUI reports a non-zero command status."""


def _quote(name):
    return f'"{name}"' if " " in name else name


def find_gui_port(host="127.0.0.1", ports=range(2070, 2076), timeout=1.0):
    """First port whose GUI answers a readiness probe, or None.

    The port increments per active GUI instance (2070, 2071, ...), and each GUI
    is bound to its own camera with its own calibration -- so the port is also
    the choice of *which* camera and calibration you are driving. Scan when a
    launch may have landed on a different instance than expected.
    """
    for port in ports:
        try:
            with OpticalTweezers(host=host, port=port, timeout=timeout) as tweez:
                if tweez.is_ready(reply_timeout=timeout):
                    return port
        except OSError:
            continue
    return None


class OpticalTweezers:
    """Sends Tweez 300 external-control commands over its TCP/IP socket.

    Connect to 127.0.0.1:2070 by default; the port increments for each
    additional active GUI instance (2071, 2072, ...) per the manual.
    """

    def __init__(self, host="127.0.0.1", port=2070, timeout=5.0,
                 min_gap_s=MIN_COMMAND_GAP_S):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""
        self._min_gap_s = min_gap_s
        self._last_send = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._sock.close()

    def _readline(self, timeout):
        self._sock.settimeout(timeout)
        try:
            while b"\n" not in self._buf:
                chunk = self._sock.recv(1024)
                if not chunk:
                    break
                self._buf += chunk
        except socket.timeout:
            return None
        line, sep, self._buf = self._buf.partition(b"\n")
        if not sep:
            return None
        return line.strip(b"\r\n").decode("utf-8")

    def send_command(self, command, read_reply=True, reply_timeout=2.0,
                     retry_busy=True):
        """Send a raw command line; returns the parsed status code, or None
        if read_reply is False or no reply arrived within reply_timeout.

        Paces sends by ``min_gap_s`` and, unless ``retry_busy`` is False,
        re-sends up to BUSY_RETRIES times while the GUI answers BUSY_STATUS.
        A missing reply is never retried -- read those two constants for the
        asymmetry, which is the whole reason this is not one code path.

        ``retry_busy=False`` is for measuring the GUI's own busy behaviour;
        callers driving hardware want the default.
        """
        attempts = BUSY_RETRIES + 1 if (read_reply and retry_busy) else 1
        for attempt in range(attempts):
            if self._last_send is not None and self._min_gap_s:
                remaining = self._min_gap_s - (time.monotonic() - self._last_send)
                if remaining > 0:
                    time.sleep(remaining)
            self._sock.sendall(command.encode("utf-8") + b"\r\n")
            self._last_send = time.monotonic()
            if not read_reply:
                return None
            reply = self._readline(reply_timeout)
            if reply is None:
                return None
            try:
                status = int(reply)
            except ValueError:
                return reply
            if status != BUSY_STATUS or attempt == attempts - 1:
                return status
            time.sleep(BUSY_BACKOFF_S)

    def do(self, command, reply_timeout=2.0):
        """Send a command and raise TweezersError unless it replies 0 (success)."""
        status = self.send_command(command, reply_timeout=reply_timeout)
        if status is None:
            raise TweezersError(f"{command!r}: no reply within {reply_timeout}s")
        if status != 0:
            reason = _RETURN_CODES.get(status, "unknown error")
            raise TweezersError(f"{command!r} failed: {status} ({reason})")
        return status

    # -- readiness --
    def probe(self, reply_timeout=2.0):
        """Send a harmless command and return its raw status.

        ``TRAP_DELETE`` against a sentinel name: if the GUI is working it
        answers -25 (no such element) and nothing changes; if it is not, it
        answers -15/-17/etc. or does not answer at all. There is no query
        command in the protocol, so this is the only available liveness test.
        """
        return self.send_command(
            f"TRAP_DELETE {_quote(_PROBE_TRAP)}", reply_timeout=reply_timeout
        )

    def is_ready(self, reply_timeout=2.0):
        """True when the GUI is up and accepting commands."""
        return self.probe(reply_timeout=reply_timeout) in READY_STATUSES

    def wait_until_ready(self, timeout=60.0, poll=0.5):
        """Block until the GUI is ready, or raise with the reason it is not.

        For scripting a launch: start the GUI, then wait here rather than
        sleeping a guessed number of seconds.
        """
        deadline = time.monotonic() + timeout
        status = None
        while time.monotonic() < deadline:
            status = self.probe()
            if status in READY_STATUSES:
                return status
            time.sleep(poll)
        reason = NOT_READY_STATUSES.get(status, f"last status {status!r}")
        raise TweezersError(f"GUI not ready after {timeout:.0f}s: {reason}")

    # -- project / laser --
    def clear_project(self):
        self.do("CLEAR_PROJECT")

    def load_project(self, file_name):
        self.do(f"LOAD_PROJECT {_quote(file_name)}")

    def laser_on(self):
        """Activates the tweezers laser. Class 4 laser -- physical safety hazard."""
        self.do("LASER_ON")

    def laser_off(self):
        self.do("LASER_OFF")

    def set_beam_focus(self, focus):
        """focus in [0, 1]."""
        self.do(f"BEAM_SET_FOCUS {focus}")

    def set_beam_params(self, switching_rate_hz, blanking_time_us):
        self.do(f"BEAM_SET_PARAMS {switching_rate_hz} {blanking_time_us}")

    # -- traps --
    def create_tracking_trap(self, name):
        self.do(f"TRACKING_TRAP_CREATE {_quote(name)}")

    def create_simple_trap(self, name):
        self.do(f"SIMPLE_TRAP_CREATE {_quote(name)}")

    def delete_trap(self, name):
        self.do(f"TRAP_DELETE {_quote(name)}")

    def set_trap_strength(self, name, strength):
        """strength in [0, 1]."""
        self.do(f"TRAP_STRENGTH {_quote(name)} {strength}")

    def set_trap_position(self, name, x_um, y_um):
        self.do(f"TRAP_POSITION {_quote(name)} {x_um} {y_um}")

    def move_trap(self, name, dx_um, dy_um):
        self.do(f"TRAP_POSITION_REL {_quote(name)} {dx_um} {dy_um}")

    def trap_on(self, name):
        self.do(f"TRAP_ON {_quote(name)}")

    def trap_off(self, name):
        self.do(f"TRAP_OFF {_quote(name)}")

    # -- patterns --
    def load_pattern(self, pattern_name, pattern_file, file_first=False):
        """Load a .tpf pattern file and name it.

        **Argument order settled 2026-09-03 on the real GUI: name first.**

            LOAD_PATTERN "Sine 1Hz Y" "C:\\agentic_microscope\\sine-1hz-y-bp.tpf"
            -> 0

        The manual contradicted itself and this was the one command here whose
        form was unconfirmed: the Command List (p.68) gives ``LOAD_PATTERN
        <pattern name> <pattern file>``, while the worked example (p.69) writes
        ``LOAD_PATTERN Sample.tsf "Patt 1"`` -- file first, with the extension
        misspelt (.tsf; it is .tpf everywhere else) and a relative path on the
        same page that states "File paths are absolute". The Command List wins;
        the example is the sloppier of the two, as suspected. ``file_first=True``
        is kept for the other GUI versions this has not been tried against.

        What the 0 does **not** establish, because the TCP interface has no
        readback of any kind: that the pattern arrived under the name asked for,
        or that its point count matches the file. Check the GUI's pattern list.
        Paths are absolute either way. Pattern files can be generated with
        hardware/tweezers_patterns.py.
        """
        args = (pattern_file, pattern_name) if file_first else (pattern_name, pattern_file)
        self.do(f"LOAD_PATTERN {_quote(args[0])} {_quote(args[1])}")

    def delete_pattern(self, pattern_name):
        self.do(f"DELETE_PATTERN {_quote(pattern_name)}")

    def assign_pattern(self, trap_name, pattern_name):
        self.do(f"TRAP_ASSIGN_PATTERN {_quote(trap_name)} {_quote(pattern_name)}")

    def remove_pattern(self, trap_name):
        self.do(f"TRAP_REMOVE_PATTERN {_quote(trap_name)}")

    def rotate_pattern(self, trap_name, phi_deg):
        self.do(f"TRAP_PATT_ROTATION {_quote(trap_name)} {phi_deg}")

    def rotate_pattern_rel(self, trap_name, d_phi_deg):
        self.do(f"TRAP_PATT_ROTATION_REL {_quote(trap_name)} {d_phi_deg}")

    def scale_pattern(self, trap_name, scale):
        self.do(f"TRAP_PATT_SCALE {_quote(trap_name)} {scale}")

    def scale_pattern_rel(self, trap_name, d_scale):
        self.do(f"TRAP_PATT_SCALE_REL {_quote(trap_name)} {d_scale}")

    def release_pattern_breakpoint(self, trap_name):
        """Release a trap halted at a ``colBP`` breakpoint.

        A 0 here means the command was accepted, NOT that anything was
        released. Measured on the microscope PC 2026-08-27: four of these in a
        row all answered 0 -- the first with the trap genuinely waiting at the
        breakpoint, the rest with the pattern already finished. The only thing
        the status distinguishes is whether the trap exists at all (a bad name
        gives -22). So a stepping protocol built on this cannot confirm a step
        happened; time it from the host, or use the hardware trigger.

        Two GUI-only properties gate whether there is anything to release:
        the trap's ``Breakpoints > Enable Bits`` is ANDed with ``colBP``, so a
        0000 mask means no point ever halts, and ``Repeat > Enabled`` decides
        whether the pattern comes back round to the breakpoint at all.
        """
        self.do(f"TRAP_PATT_RELEASE_BP {_quote(trap_name)}")

    # -- trap groups --
    def group_traps_on(self, group_name):
        self.do(f"GROUP_TRAPS_ON {_quote(group_name)}")

    def group_traps_off(self, group_name):
        self.do(f"GROUP_TRAPS_OFF {_quote(group_name)}")

    def group_traps_start_repeat(self, group_name):
        self.do(f"GROUP_TRAPS_START_REPEAT {_quote(group_name)}")

    def group_traps_stop_repeat(self, group_name):
        self.do(f"GROUP_TRAPS_STOP_REPEAT {_quote(group_name)}")

    def group_traps_release(self, group_name):
        self.do(f"GROUP_TRAPS_RELEASE {_quote(group_name)}")
