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


class TweezersError(RuntimeError):
    """Raised when the Tweez 300 GUI reports a non-zero command status."""


def _quote(name):
    return f'"{name}"' if " " in name else name


class OpticalTweezers:
    """Sends Tweez 300 external-control commands over its TCP/IP socket.

    Connect to 127.0.0.1:2070 by default; the port increments for each
    additional active GUI instance (2071, 2072, ...) per the manual.
    """

    def __init__(self, host="127.0.0.1", port=2070, timeout=5.0):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""

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

    def send_command(self, command, read_reply=True, reply_timeout=2.0):
        """Send a raw command line; returns the parsed status code, or None
        if read_reply is False or no reply arrived within reply_timeout."""
        self._sock.sendall(command.encode("utf-8") + b"\r\n")
        if not read_reply:
            return None
        reply = self._readline(reply_timeout)
        if reply is None:
            return None
        try:
            return int(reply)
        except ValueError:
            return reply

    def do(self, command, reply_timeout=2.0):
        """Send a command and raise TweezersError unless it replies 0 (success)."""
        status = self.send_command(command, reply_timeout=reply_timeout)
        if status is None:
            raise TweezersError(f"{command!r}: no reply within {reply_timeout}s")
        if status != 0:
            reason = _RETURN_CODES.get(status, "unknown error")
            raise TweezersError(f"{command!r} failed: {status} ({reason})")
        return status

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
    def load_pattern(self, pattern_name, pattern_file):
        self.do(f"LOAD_PATTERN {_quote(pattern_name)} {_quote(pattern_file)}")

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
