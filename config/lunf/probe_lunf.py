"""Drive and probe the LUN-F from Python, with NIS closed. Self-contained.

The tooling behind `kb/decisions/2026-09-02-lunf-first-light-measured-limits.md`.
Sibling of config/piezo/run_sine_hold.py: the script that made the measurements,
kept so they can be repeated rather than re-derived.

Talks to two things directly, neither through Micro-Manager:

    blanking   NI PCIe-6323 digital lines, via nicaiu.dll (NI-DAQmx) by ctypes.
               No nidaqmx package needed. This is on/off AND wavelength select.
    power      the LUN-F's FT4222H SPI DAC, via LibFT4222 by ctypes -- the same
               transport hardware/lunf_power.py opens.

PRECONDITIONS, ALL OF THEM LOAD-BEARING
---------------------------------------
1. **NIS must not be running.** It holds Dev1's port0 exclusively (a DO task
   elsewhere gets -200587) and FT4222 interfaces A/B/C.
2. **The fiber shutter must be open.** `Fiber1` in the LUN-F Pad. It is not
   reachable from here -- see the module docstring of hardware/lunf_power.py --
   so it has to be open already or nothing below emits, and every subcommand
   will look like a null result.
3. **The DAC holds whatever was last written to it.** With NIS gone there is no
   readback, so the level is whatever NIS or a previous run of this script left.

SAFETY, AND WHY THE DEFAULTS ARE WHAT THEY ARE
-----------------------------------------------
`spi-probe` sends frames whose format is not yet known. Every one carries
DATA = 0, so no candidate can raise the output, and all four blanking lines are
closed before the first byte goes out. `spi-modulate` does write non-zero levels,
so it takes an explicit --high and gates on the same closed-blanking preamble.

Every subcommand closes all four blanking lines in a `finally`, including on
Ctrl-C.

    python config/lunf/probe_lunf.py blink --nm 561
    python config/lunf/probe_lunf.py ao-sweep --nm 561
    python config/lunf/probe_lunf.py spi-probe
    python config/lunf/probe_lunf.py spi-modulate --nm 561 --high 5.0
"""

from __future__ import annotations

import argparse
import ctypes as C
import os
import sys
import time

NICAIU = r"C:\Windows\System32\nicaiu.dll"
LIBFT4222 = r"C:\Program Files\NIS-Elements\LibFT4222-64.dll"
FTD2XX = r"C:\Windows\System32\ftd2xx.dll"
FT4222_SERIAL = b"00294-BOA"

#: wavelength -> (blanking line, DAC index). Read off the live NIS "LUN-F
#: Configuration" dialog on 2026-09-02, which outranks the device DB -- two of
#: the three DB records disagree about 405 and are stale.
WL = {
    "405": ("Dev1/port0/line2", 0),
    "488": ("Dev1/port0/line4", 1),
    "561": ("Dev1/port0/line6", 2),
    "640": ("Dev1/port0/line8", 3),
}

#: measured 2026-09-02: the level that OPENS a blanking line. Nikon does not
#: document this and it is not assumed anywhere else in the repo.
OPEN, CLOSED = 1, 0

#: read off the NIS pad: the sliders are in volts and top out at 5 V.
FULL_SCALE_V = 5.0

DAQmx_Val_Volts = 10348
DAQmx_Val_GroupByChannel = 0
DAQmx_Val_ChanPerLine = 0
FT_OPEN_BY_SERIAL = 1
SPI_IO_SINGLE, CLK_DIV_128, SS_0 = 1, 7, 1


# --------------------------------------------------------------------------
# NI-DAQmx, by ctypes
# --------------------------------------------------------------------------

class Daq:
    def __init__(self) -> None:
        self.d = C.WinDLL(NICAIU)

    def _chk(self, rc: int, where: str) -> None:
        if rc >= 0:
            return
        buf = C.create_string_buffer(2048)
        self.d.DAQmxGetExtendedErrorInfo(buf, C.c_uint32(2048))
        msg = buf.value.decode(errors="replace").strip().split("\n")[0]
        hint = ("  (is NIS still running? it holds Dev1/port0 exclusively)"
                if rc == -200587 else "")
        raise RuntimeError(f"{where} rc={rc}: {msg}{hint}")

    def write_line(self, line: str, level: int) -> None:
        t = C.c_void_p()
        self._chk(self.d.DAQmxCreateTask(b"", C.byref(t)), "CreateTask")
        try:
            self._chk(self.d.DAQmxCreateDOChan(
                t, line.encode(), b"", C.c_int32(DAQmx_Val_ChanPerLine)), "CreateDOChan")
            written = C.c_int32()
            self._chk(self.d.DAQmxWriteDigitalLines(
                t, C.c_int32(1), C.c_uint32(1), C.c_double(5.0),
                C.c_int32(DAQmx_Val_GroupByChannel), (C.c_ubyte * 1)(level),
                C.byref(written), None), "WriteDigitalLines")
        finally:
            self.d.DAQmxStopTask(t)
            self.d.DAQmxClearTask(t)

    def close_all(self) -> None:
        for line, _ in WL.values():
            self.write_line(line, CLOSED)


class AoTask:
    """One persistent AO task. Per-write create/clear costs ~50 ms a channel,
    which would swallow most of a 0.5 s modulation step."""

    def __init__(self, daq: Daq, phys: str, n: int) -> None:
        self.d, self.n, self.t = daq.d, n, C.c_void_p()
        daq._chk(self.d.DAQmxCreateTask(b"", C.byref(self.t)), "CreateTask(AO)")
        daq._chk(self.d.DAQmxCreateAOVoltageChan(
            self.t, phys.encode(), b"", C.c_double(-10.0), C.c_double(10.0),
            C.c_int32(DAQmx_Val_Volts), None), "CreateAOVoltageChan")
        daq._chk(self.d.DAQmxStartTask(self.t), "StartTask")
        self._daq = daq

    def set(self, v: float) -> None:
        written = C.c_int32()
        self._daq._chk(self.d.DAQmxWriteAnalogF64(
            self.t, C.c_int32(1), C.c_uint32(1), C.c_double(2.0),
            C.c_int32(DAQmx_Val_GroupByChannel),
            (C.c_double * self.n)(*([v] * self.n)), C.byref(written), None),
            "WriteAnalogF64")

    def close(self) -> None:
        try:
            self.set(0.0)
        finally:
            self.d.DAQmxStopTask(self.t)
            self.d.DAQmxClearTask(self.t)


# --------------------------------------------------------------------------
# FT4222 SPI, by ctypes -- same transport as hardware/lunf_power.py
# --------------------------------------------------------------------------

class Spi:
    def __init__(self, cpol: int = 0, cpha: int = 0) -> None:
        os.add_dll_directory(os.path.dirname(FTD2XX))
        self.d2, self.ft = C.WinDLL(FTD2XX), C.WinDLL(LIBFT4222)
        self.h, self.cpol, self.cpha = C.c_void_p(), cpol, cpha

    def __enter__(self) -> "Spi":
        rc = self.d2.FT_OpenEx(FT4222_SERIAL, FT_OPEN_BY_SERIAL, C.byref(self.h))
        if rc != 0:
            raise RuntimeError(
                f"FT_OpenEx({FT4222_SERIAL!r}) rc={rc} -- close NIS, it claims this interface")
        rc = self.ft.FT4222_SPIMaster_Init(
            self.h, SPI_IO_SINGLE, CLK_DIV_128,
            C.c_int(self.cpol), C.c_int(self.cpha), C.c_ubyte(SS_0))
        if rc != 0:
            self.d2.FT_Close(self.h)
            raise RuntimeError(f"FT4222_SPIMaster_Init rc={rc}")
        return self

    def __exit__(self, *exc) -> None:
        self.ft.FT4222_UnInitialize(self.h)
        self.d2.FT_Close(self.h)

    def write(self, payload: bytes) -> None:
        buf = (C.c_ubyte * len(payload)).from_buffer_copy(payload)
        sent = C.c_uint16()
        rc = self.ft.FT4222_SPIMaster_SingleWrite(
            self.h, buf, C.c_uint16(len(payload)), C.byref(sent), C.c_bool(True))
        if rc != 0:
            raise RuntimeError(f"FT4222_SPIMaster_SingleWrite rc={rc}")


def builders(addr: int):
    """(label, fraction -> bytes) for each surviving candidate framing.

    Narrowed 2026-09-02 to nine, all addressing one DAC index. Whichever of these
    turns out to be the real one becomes hardware/lunf_power.PROTOCOL.
    """
    def d16(f): return min(65535, max(0, round(f * 65535)))
    def d14(f): return min(16383, max(0, round(f * 16383)))
    def d12(f): return min(4095, max(0, round(f * 4095)))

    out = []
    for cmd, fam in ((0x3, "wr+upd"), (0x0, "wr-input"), (0x2, "cmd2"), (0x1, "cmd1")):
        out.append((f"3B/16b {fam} a{addr}",
                    lambda f, c=cmd: bytes([(c << 4) | addr, d16(f) >> 8, d16(f) & 0xFF])))
    out.append((f"3B/16b dac8564 a{addr}",
                lambda f: bytes([0x10 | (addr << 1), d16(f) >> 8, d16(f) & 0xFF])))
    out.append((f"4B/12b ad5628 a{addr}",
                lambda f: bytes([0x03, (addr << 4) | (d12(f) >> 8), d12(f) & 0xFF, 0x00])))
    out.append((f"2B/14b ch<<6 a{addr}",
                lambda f: bytes([(addr << 6) | (d14(f) >> 8), d14(f) & 0xFF])))
    for cfg, nm in ((0x30, "A g1"), (0xB0, "B g1")):
        out.append((f"2B/12b mcp4922 {nm}",
                    lambda f, c=cfg: bytes([c | (d12(f) >> 8), d12(f) & 0xFF])))
    return out


def discovery_frames():
    """Every candidate x every address, DATA = 0. Cannot raise any output.

    Re-sending this is also the reset used between bisection rounds: it puts the
    responding channel back to zero without needing NIS.
    """
    out = []
    for a in range(4):
        for label, build in builders(a):
            out.append((label, build(0.0)))
    return out


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------

def cmd_blink(a) -> int:
    """Is this line still emitting? A square wave is unmistakable; a static
    open window is easy to miss."""
    line, _ = WL[a.nm]
    daq = Daq()
    print(f"{a.nm} nm -> {line}, {a.repeat}x {a.period}s on/off")
    t0 = time.time()
    try:
        daq.close_all()
        time.sleep(1.0)
        print("  watch now", flush=True)
        for i in range(1, a.repeat + 1):
            daq.write_line(line, OPEN)
            time.sleep(a.period)
            daq.write_line(line, CLOSED)
            time.sleep(a.period)
            print(f"  t+{time.time()-t0:5.1f}s  blink {i}/{a.repeat}", flush=True)
    finally:
        daq.close_all()
        print("  all lines CLOSED")
    print(f"\nblinked -> {a.nm}'s DAC level is non-zero. dark -> it is zero, or "
          "the shutter is closed.")
    return 0


def cmd_ao_sweep(a) -> int:
    """Are Dev1/ao0..ao3 cabled to the LUN-F's analog power inputs?

    Answered 2026-09-02: no. Kept because a negative result nobody can reproduce
    gets re-proposed.
    """
    line, guess = WL[a.nm]
    chan = a.chan if a.chan is not None else str(guess)
    phys, n = (("Dev1/ao0:3", 4) if chan == "all" else (f"Dev1/ao{int(chan)}", 1))
    pattern = [5.0, 1.0, 4.0, 2.0, 0.0]

    daq = Daq()
    daq.close_all()
    ao = AoTask(daq, phys, n)
    t0 = time.time()
    print(f"{a.nm} nm -> {line}   driving {phys}")
    print(f"pattern {pattern} V @ {a.period}s x{a.repeat}, blanking held OPEN\n")
    try:
        ao.set(0.0)
        daq.write_line(line, OPEN)
        time.sleep(1.5)
        for cyc in range(1, a.repeat + 1):
            for v in pattern:
                ao.set(v)
                time.sleep(a.period)
            print(f"  t+{time.time()-t0:5.1f}s  cycle {cyc}/{a.repeat}", flush=True)
    finally:
        ao.close()
        daq.close_all()
        print("  AO 0 V, all blanking CLOSED")
    print("\nflicker -> an AO channel reaches this line's power input.")
    return 0


def cmd_spi_probe(a) -> int:
    """Send the DATA = 0 discovery burst, then blink the watched line."""
    line, _ = WL[a.nm]
    frames = discovery_frames()
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        frames = [f for i, f in enumerate(frames) if i in want]

    daq = Daq()
    print(f"SPI mode {a.cpol*2 + a.cpha} (CPOL={a.cpol} CPHA={a.cpha}), 469 kHz")
    print(f"{len(frames)} frames, every one DATA = 0\n")
    try:
        daq.close_all()
        time.sleep(0.3)
        with Spi(a.cpol, a.cpha) as spi:
            for i, (label, frame) in enumerate(frames):
                spi.write(frame)
                print(f"  [{i:2d}] {label:22} {frame.hex(' ')}")
                time.sleep(0.01)
        print(f"\n{len(frames)} frames sent with the laser gated off throughout\n")
        a.nm, a.period, a.repeat = a.nm, 0.5, 10
        return cmd_blink(a)
    finally:
        daq.close_all()


def cmd_spi_modulate(a) -> int:
    """Alternate the DAC between --high and --low with blanking held OPEN.

    Any flicker is the DAC, not the shutter -- the light is never gated off.
    """
    line, addr = WL[a.nm]
    cands = builders(addr)
    f_hi, f_lo = a.high / FULL_SCALE_V, a.low / FULL_SCALE_V

    print(f"{a.nm} nm -> {line}, DAC addr {addr}")
    print(f"{a.high} V <-> {a.low} V, {a.period}s each, {a.repeat} cycles")
    print(f"{len(cands)} candidate framings, all sent at each level\n")
    for i, (lbl, b) in enumerate(cands):
        print(f"  [{i}] {lbl:22} hi={b(f_hi).hex(' '):14} lo={b(f_lo).hex(' ')}")

    daq = Daq()
    t0 = time.time()
    try:
        daq.close_all()
        with Spi() as spi:
            for _, b in cands:
                spi.write(b(f_lo))
            daq.write_line(line, OPEN)
            print(f"\n{a.nm} OPEN and staying open -- watch for FLICKER\n")
            time.sleep(1.5)
            for cyc in range(1, a.repeat + 1):
                for _, b in cands:
                    spi.write(b(f_hi))
                time.sleep(a.period)
                for _, b in cands:
                    spi.write(b(f_lo))
                time.sleep(a.period)
                print(f"  t+{time.time()-t0:5.1f}s  cycle {cyc}/{a.repeat}", flush=True)
            for _, b in cands:
                spi.write(b(f_lo))
    finally:
        daq.close_all()
        print(f"  DAC left at {a.low} V, all blanking CLOSED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--nm", default="561", choices=sorted(WL))
        p.add_argument("--period", type=float, default=0.5)
        p.add_argument("--repeat", type=int, default=10)

    common(sub.add_parser("blink", help="is this line emitting?"))

    p = sub.add_parser("ao-sweep", help="is NI AO cabled to power? (answered: no)")
    common(p)
    p.set_defaults(repeat=8)
    p.add_argument("--chan", default=None, help="AO index, or 'all'")

    p = sub.add_parser("spi-probe", help="DATA=0 discovery burst, then blink")
    common(p)
    p.add_argument("--cpol", type=int, default=0, choices=(0, 1))
    p.add_argument("--cpha", type=int, default=0, choices=(0, 1))
    p.add_argument("--only", default=None, help="frame indices, for bisection")

    p = sub.add_parser("spi-modulate", help="swing the DAC, blanking held open")
    common(p)
    p.set_defaults(repeat=5)
    p.add_argument("--high", type=float, default=5.0)
    p.add_argument("--low", type=float, default=0.0)

    a = ap.parse_args()
    fn = {"blink": cmd_blink, "ao-sweep": cmd_ao_sweep,
          "spi-probe": cmd_spi_probe, "spi-modulate": cmd_spi_modulate}[a.cmd]
    try:
        return fn(a)
    except RuntimeError as exc:
        print(f"\n!! {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[abort] closing all blanking lines")
        Daq().close_all()
        return 130


if __name__ == "__main__":
    sys.exit(main())
