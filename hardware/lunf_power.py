"""Per-line laser power for the Nikon LUN-F XL, over its FTDI FT4222H SPI link.

A direct Python driver, in the same role as hardware/piezo_stage.py and
hardware/optical_tweezers.py: a device Micro-Manager does not own, driven
straight from Python. Since this project drives MM through pymmcore-plus, a
Micro-Manager device adapter would only add a layer -- one script can set power
here and blanking through the core in the same breath::

    from pymmcore_plus import CMMCorePlus
    from hardware.lunf_power import LUNFPower

    core = CMMCorePlus(); core.loadSystemConfiguration("laser_test.cfg")
    with LUNFPower() as lunf:
        lunf.set_power("488", 30.0)      # FT4222 SPI DAC  -- this module
        core.setConfig("LaserLine", "488")  # Dev1/port0/line4 -- NIDAQ adapter

(The PyDevice adapter, mmgr_dal_PyDevice.dll, was evaluated and dropped: it
loaded the device but surfaced none of its properties, and it buys nothing here.)

THE SPLIT
---------
The LUN-F XL is controlled over two paths (read out of the NIS-Elements device
DB, ``C:\\ProgramData\\Laboratory Imaging\\Platform\\DeviceDatabase_6_00.dat`` >
``dev_PhysicalDevice[LUN-F].sConfiguration``, confirmed against the NIS "LUN-F
Configuration" dialog)::

    Wave0=405  PowerResource0=FT4222_00294-BOA/AO_A_0  BlankingResource0=Dev1/port0/line2
    Wave1=488  PowerResource1=FT4222_00294-BOA/AO_A_1  BlankingResource1=Dev1/port0/line4
    Wave2=561  PowerResource2=FT4222_00294-BOA/AO_A_2  BlankingResource2=Dev1/port0/line6
    Wave3=640  PowerResource3=FT4222_00294-BOA/AO_A_3  BlankingResource3=Dev1/port0/line8

Power  -> SPI DAC behind the FT4222H  -> this module, ~1-3 ms per update
On/off -> NI PCIe-6323 digital lines  -> MM's stock NIDAQ adapter, 5.4 us measured

If the LUN-F's analog power inputs turn out to be cabled to the DAQ, NIS's
Control dropdown ("Power Only" / "Power & Blanking") can rebind PowerResource%d
to a ``%s/ao%d`` NI channel, and then power becomes a plain NIDAQAO device --
faster, sequenceable, and this module becomes unnecessary. Worth checking first.

**Checked 2026-09-02: they are not cabled. This route is dead.** Dev1 has
exactly four AO channels at +/-10 V and the LUN-F has exactly four lines, which
is suggestive and wrong. ao0..ao3 were driven together 0->5 V in steps, then
0<->5 V for contrast, then at speed (5, 1, 4, 2, 0 V at 0.5 s from one
persistent DAQmx task) with the blanking line **held open** so the light never
went off, then per channel -- ao2 against 561 and ao3 against 640. No response
at any point. Consistent with the dialog showing ``Connector Block: Not
Specified`` and the Power column as fixed text (DAC 0..3) rather than a resource
selector. Do not propose this again.

WHAT IS NOT KNOWN YET
---------------------
**The SPI framing -- narrowed, 2026-09-02, but still not named.** LibFT4222 puts
bytes on the wire, and it is now established that those bytes **reach the DAC**:
a burst of candidate frames carrying data = 0 extinguished 561 and left 640
alive, and a 5 V <-> 0 V alternation flickered 561 with its blanking line held
open. So writes land, they are channel-selective, and arbitrary levels are
writable -- not just zero.

What remains is *which* framing. The field is down to nine, all addressing DAC
index 2 (561 is Wave2, and the burst spared Wave3)::

    3B/16b  [cmd<<4|2][d>>8][d]      cmd in {0,1,2,3}
    3B/16b  [0x14][d>>8][d]          DAC8564-style control byte
    4B/12b  [0x03][0x20|d>>8][d][0]  AD5628 / AD5668
    2B/14b  [0x80|d>>8][d]
    2B/12b  [0x30|d>>8][d]           MCP4922 A
    2B/12b  [0xB0|d>>8][d]           MCP4922 B

**Three bisection rounds would name it**, and the reset is free: re-sending the
data = 0 burst extinguishes 561 on demand, so no NIS restart is needed between
rounds. Until one is named ``PROTOCOL`` stays ``None`` and ``set_power``
refuses -- knowing the answer is in a set of nine is not knowing the answer.

Full record: ``kb/decisions/2026-09-02-lunf-first-light-measured-limits.md``.

WHY GUESSED BYTES BECAME ALLOWABLE
----------------------------------
``kb/decisions/2026-08-29-device-discovery-scope.md`` forbids writing to a device
to find out what it does. That rule was written when there was no way to bound
the consequence. Two things changed on 2026-09-02: **blanking control** (measured
active-HIGH, so the laser is gated off in software before any SPI byte is sent)
and **a power meter** (retiring the 2026-08-19 deferral). The probe was built so
the rule's purpose still held -- every discovery frame carried data = 0, so no
candidate could raise the output, and all four blanking lines were closed for the
duration. The relaxation was the user's explicit decision, not an assumption.

THE USB-B PLAN (2026-08-19) WAS TRIED, AND DOES NOT SUPERSEDE THIS
------------------------------------------------------------------
The chassis was cabled straight over USB-B on 2026-09-02. It enumerates as
**COM8**, an FTDI FT232R with EEPROM serial ``FTDD2RRL`` and a vendor-programmed
product string; identity confirmed by unplug/replug. It is **silent** at 9600 /
19200 / 38400 / 57600 / 115200, and nothing has been sent to it.

But it cannot replace this module, because ``v6_w32_device_LUNF.dll`` contains no
``COM`` / ``baud`` / ``serial port`` strings at all -- only FTD2XX and FT4222
symbols. NIS's Control dropdown reads "**USB** Power & Blanking", and that USB
*is the FT4222*. So the capture plan stands on its own merits rather than as a
fallback.

Power *measurement* is no longer deferred -- a meter is available as of
2026-09-02 -- but it is a standalone display, not PC-readable, so volts -> mW is
a manual exercise. Do not confuse that with the word-format blocker.

MEASURED ON THIS MACHINE (2026-08-19)
-------------------------------------
    FT_OpenEx("00294-BOA")  ->  rc=0
    FT4222_GetVersion       ->  chipVersion 0x42220400 (rev D), dll 1.4.2.184
    FT4222_GetClock         ->  system clock 60 MHz
    interfaces              ->  00294-BOA/B/C/D, mode FT4222H_1_2

MEASURED ON THIS MACHINE (2026-09-02)
-------------------------------------
    FT4222_SPIMaster_Init   ->  rc=0  (SINGLE, div 128 = 469 kHz, mode 0, SS_0)
    SPI writes              ->  reach the DAC, channel-selective
    DAC full scale          ->  0-5 V, read off the NIS pad (Value [V], because
                                Segmented Linear Scale is off and there is no
                                calibration table -- CALIBRATED0..3 all 0)
    setpoints as found      ->  405 2.95 V | 488 2.40 V | 561 1.50 V | 640 2.35 V
    blanking polarity       ->  active-HIGH  (405 line2, 488 line4,
                                561 line6, 640 line8 -- from the live dialog)
    NIS holds, while running -> FT4222 A/B/C  (D stays free), and Dev1 port0
                                exclusively: a DO task elsewhere gets -200587
    DAC readback            ->  none, and no monitor on any of Dev1's 32 AI
                                channels (all 32 float to the +/-10 V rail)

THE FIBER SHUTTER, AND THE HANDOFF THAT GETS AROUND IT
-------------------------------------------------------
``Fiber1`` gates everything downstream of it, and it is **not reachable from
this repo** -- ``SetShutterState``, ``CLxLUNFShutter`` and ``ILxDeviceShutter``
are string-table and RTTI names; the DLL exports 33 symbols and none are those.
A correct set_power() with a closed shutter still emits nothing.

Measured 2026-09-02, and it is the reason this is not a hard blocker: **the
shutter survives a force-kill of NIS.** It is NIS's *clean* shutdown that closes
it, and the LUN-F has no link-drop watchdog. So::

    1. start NIS, open Fiber1, set the four line voltages on the pad
    2. taskkill /F nis_ar.exe        -- releases Dev1 port0 and FT4222 A/B/C
    3. drive from Python

``config/lunf/handoff_from_nis.py`` does steps 2-3 and verifies each. Treat it
as a workaround, not a solution: it leaves a per-session NIS dependency against
[[project-pymmcore-only-no-nis]], depends on force-killing rather than any
documented interface, and holds a laser shutter open by skipping the vendor's
shutdown path. A supported route is a question for Nikon.
"""

from __future__ import annotations

import ctypes as C
import os

#: NIS-Elements ships FTDI's FT4222 library; no separate install is needed.
LIBFT4222 = r"C:\Program Files\NIS-Elements\LibFT4222-64.dll"
FTD2XX = r"C:\Windows\System32\ftd2xx.dll"

#: Interface A carries the four power DACs -- PowerResource%d reads
#: "FT4222_00294-BOA/AO_A_%d", where the trailing A is the FT4222 interface.
FT4222_SERIAL = b"00294-BOA"

#: wavelength -> DAC channel, from PowerResource0..3 above
DAC_CHANNEL = {"405": 0, "488": 1, "561": 2, "640": 3}

FT_OPEN_BY_SERIAL_NUMBER = 1
SPI_IO_SINGLE = 1
CLK_DIV_128 = 7
CLK_IDLE_LOW = 0
CLK_LEADING = 0
SS_0 = 1

#: Set once the SPI word format is captured: a callable
#: ``(channel: int, fraction: float) -> bytes`` returning the exact bytes for one
#: DAC update, ``fraction`` in 0.0-1.0. While None, set_power() refuses.
PROTOCOL = None


class LUNFPowerError(RuntimeError):
    pass


class LUNFPower:
    """LUN-F XL per-line power, 0-100 % of each line's configured maximum.

    On/off is not here -- that is the DAQ blanking device (``LUNF-Blanking``
    lines 2/4/6/8 in the MM config). This only sets how bright a line is when
    it is open.
    """

    def __init__(self, serial: bytes = FT4222_SERIAL) -> None:
        os.add_dll_directory(os.path.dirname(FTD2XX))
        self._d2 = C.WinDLL(FTD2XX)
        self._ft = C.WinDLL(LIBFT4222)
        self._serial = serial
        self._h = C.c_void_p()
        self._spi_ready = False
        self._setpoint = {wl: None for wl in DAC_CHANNEL}

    # ---- lifecycle ----------------------------------------------------------

    def __enter__(self) -> LUNFPower:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        """Open interface A. Initialises SPI only if PROTOCOL is set."""
        rc = self._d2.FT_OpenEx(self._serial, FT_OPEN_BY_SERIAL_NUMBER, C.byref(self._h))
        if rc != 0:
            raise LUNFPowerError(
                f"FT_OpenEx({self._serial!r}) failed rc={rc}. "
                "Close NIS-Elements first - it claims this interface."
            )
        if PROTOCOL is not None:
            self._spi_init()

    def close(self) -> None:
        if self._h:
            if self._spi_ready:
                self._ft.FT4222_UnInitialize(self._h)
                self._spi_ready = False
            self._d2.FT_Close(self._h)
            self._h = C.c_void_p()

    @property
    def is_open(self) -> bool:
        return bool(self._h)

    # ---- chip info (safe: no SPI) -------------------------------------------

    def version(self) -> tuple[int, int]:
        """(chipVersion, dllVersion). 0x42220400 is FT4222 rev D."""
        class _Ver(C.Structure):
            _fields_ = [("chip", C.c_uint32), ("dll", C.c_uint32)]

        v = _Ver()
        rc = self._ft.FT4222_GetVersion(self._h, C.byref(v))
        if rc != 0:
            raise LUNFPowerError(f"FT4222_GetVersion failed rc={rc}")
        return v.chip, v.dll

    def clock_mhz(self) -> int:
        clk = C.c_int()
        rc = self._ft.FT4222_GetClock(self._h, C.byref(clk))
        if rc != 0:
            raise LUNFPowerError(f"FT4222_GetClock failed rc={rc}")
        return {0: 60, 1: 24, 2: 48, 3: 80}.get(clk.value, clk.value)

    @property
    def status(self) -> str:
        if not self.is_open:
            return "closed"
        if PROTOCOL is None:
            return (
                f"reachable (FT4222 rev 0x{self.version()[0]:08X}, {self.clock_mhz()} MHz) "
                "but SPI word format unknown - set lunf_power.PROTOCOL to enable set_power()"
            )
        return f"live (FT4222 rev 0x{self.version()[0]:08X}, {self.clock_mhz()} MHz)"

    # ---- power --------------------------------------------------------------

    def get_power(self, wavelength: str) -> float | None:
        """Last value this driver set, or None if it has not set one.

        The DAC is write-only over this path, so there is no readback — a None
        means the line is at whatever NIS or the front panel last left it.
        """
        return self._setpoint[self._check(wavelength)]

    def set_power(self, wavelength: str, percent: float) -> None:
        wl = self._check(wavelength)
        if PROTOCOL is None:
            raise LUNFPowerError(
                "SPI word format unknown - refusing to send guessed bytes to a laser "
                "AOTF driver. See this module's docstring for how to capture it."
            )
        if not self._spi_ready:
            raise LUNFPowerError("not open - use `with LUNFPower() as lunf:`")
        percent = max(0.0, min(100.0, float(percent)))
        self._spi_write(PROTOCOL(DAC_CHANNEL[wl], percent / 100.0))
        self._setpoint[wl] = percent

    # ---- internals ----------------------------------------------------------

    @staticmethod
    def _check(wavelength: str) -> str:
        wl = str(wavelength)
        if wl not in DAC_CHANNEL:
            raise LUNFPowerError(f"unknown line {wl!r}; have {sorted(DAC_CHANNEL)}")
        return wl

    def _spi_init(self) -> None:
        """Configure interface A as SPI master.

        Deliberately not called while PROTOCOL is None — this drives CLK/CS,
        which an unknown DAC could latch on.
        """
        rc = self._ft.FT4222_SPIMaster_Init(
            self._h, SPI_IO_SINGLE, CLK_DIV_128, CLK_IDLE_LOW, CLK_LEADING, SS_0
        )
        if rc != 0:
            raise LUNFPowerError(f"FT4222_SPIMaster_Init failed rc={rc}")
        self._spi_ready = True

    def _spi_write(self, payload: bytes) -> int:
        buf = (C.c_ubyte * len(payload)).from_buffer_copy(payload)
        sent = C.c_uint16()
        rc = self._ft.FT4222_SPIMaster_SingleWrite(
            self._h, buf, C.c_uint16(len(payload)), C.byref(sent), C.c_bool(True)
        )
        if rc != 0:
            raise LUNFPowerError(f"FT4222_SPIMaster_SingleWrite failed rc={rc}")
        return sent.value


if __name__ == "__main__":
    with LUNFPower() as lunf:
        print("status:", lunf.status)
        for wl, ch in DAC_CHANNEL.items():
            print(f"  {wl} nm -> DAC {ch}  setpoint {lunf.get_power(wl)}")
