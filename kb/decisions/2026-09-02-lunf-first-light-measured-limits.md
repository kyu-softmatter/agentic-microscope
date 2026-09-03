# 2026-09-02 · LUN-F first light: the DAC answers, and the AO route is dead

> First session in which the LUN-F was **driven** from this repo rather than read
> about. Everything below was measured on the microscope PC against the live
> combiner — LUN-F, 4 lines on one fiber (405/488/561/640), NI PCIe-6323 `Dev1`,
> FTDI FT4222H `00294-BO` rev D at 60 MHz.
>
> Third in the "first light" series after
> `2026-08-27-piezo-first-light-measured-limits.md` and
> `2026-08-27-tweezers-first-light-measured-limits.md`. The contrast with those
> is the point: the piezo reads back, the tweezers do not, and the LUN-F does
> not either — but unlike the tweezers it turned out to be **writable**, which
> nothing in the record before today established.
>
> Two long-standing open items close here, one positively and one negatively, and
> one claim made mid-session was **too strong and is corrected below** — see
> §7 and "Corrections to the record".

## What was achieved

Working control from Python, with NIS not running:

1. **Wavelength selection and on/off**, per line, via the PCIe-6323 blanking
   lines. Verified on 561 and 640 by eye.
2. **Blanking polarity settled: active-HIGH.** Undocumented by Nikon; both
   `hardware/lunf_power.py` and `config/micromanager/verify_lunf_daq.py` said so
   and refused to assume. Now measured.
3. **The FT4222 SPI link reaches the DAC, and writes are channel-selective.** A
   burst of candidate frames carrying data = 0 extinguished 561 and left 640
   untouched.
4. **Arbitrary levels are writable, not just zero.** Driving the DAC 5 V ↔ 0 V at
   0.5 s with the blanking line held open produced visible flicker.
5. **A verified handoff from NIS.** Force-killing NIS releases Dev1's port0 and
   FT4222 A/B/C while leaving the fiber shutter open, so Python takes over a
   running instrument. This is the difference between "blocked on the shutter"
   and "blocked on a nicer way to do the shutter" — see §9.

What is **not** achieved: the exact word format. See §6 — the field is narrowed
from "undocumented" to one of **nine** candidate framings, but the bisection that
would name it has not been run.

## 1. The USB-B port is real, is COM8, and NIS does not use it

The 2026-08-19 plan — "connect it straight over USB-B" — was carried out.

| | |
|---|---|
| port | **COM8** |
| chip | FTDI **FT232R** (VID 0403 / PID 6001) |
| EEPROM serial | `FTDD2RRL` |
| EEPROM product | `USB Serial Converter` (not the factory default `FT232R USB UART`, so vendor-programmed) |
| unsolicited output | **none** at 9600 / 19200 / 38400 / 57600 / 115200 |
| handshake lines | CTS/DSR/DCD all low — **and so are COM3's**, a working Lumencor, so this says nothing |

Identity established by unplug/replug while watching the PnP tree, the COM list
and the ftd2xx device count — all three moved together, and the port returned as
COM8 because FTDI binds by EEPROM serial.

**NIS never opens it.** With NIS running and Fiber1 open, ftd2xx reports
`00294-BOA/B/C/D` and `B003RRFR` as OPEN-by-other while `FTDD2RRL` stays free.
So the USB-B route is not a second view of the same path — it is a separate link
whose command set is still entirely unknown, and nothing sent to it, ever.

## 2. NIS's "USB" means the FT4222, not a COM port

`v6_w32_device_LUNF.dll` contains no `COM`, `baud` or `serial port` strings at
all — only `FTD2XX.dll`, `FT4222 A`, `GetFTDIDevices@CNIDAQEngine` and
`IsFTDI@CNIDAQResource_AOPort`. The Control dropdown's three values are
`Power Only` / `Power & Blanking` / **`USB Power & Blanking`**, and the live
dialog shows the third on all four lines (`Control%d=2`).

This retires the hope in `lunf_power.py`'s docstring that the chassis USB port
"supersedes the SPI-capture plan". It does not supersede anything: NIS's own USB
path *is* the FT4222.

## 3. The configuration, read off the live dialog

Read directly from the NIS "LUN-F Configuration" window, which outranks the
device DB:

```
Type LUNF   Card PCIe-6323 - Dev1   Connector Block: Not Specified
Lines 4     Fibers 1
  405  DAC 0  Dev1/port0/line2  USB Power & Blanking
  488  DAC 1  Dev1/port0/line4  USB Power & Blanking
  561  DAC 2  Dev1/port0/line6  USB Power & Blanking
  640  DAC 3  Dev1/port0/line8  USB Power & Blanking
Enable Triggering ✓
```

**405 is line2.** Three copies of the record exist in
`DeviceDatabase_6_00.dat`, and two of them say `line1`; the most recent
(`PFI_TimeStamp` 2026-08-19) says `line2` and the dialog agrees. The repo was
right; `verify_lunf_daq.py` and `DMD_dualcam_LUNF.cfg` need no change.

### The sliders are in volts, and full scale is 5 V

GUI Options had `Segmented Linear Scale` **off** and `Value [V] or [mW]`
**selected**. mW requires a calibration table, and there is none, so the number
beside each slider is **volts**:

```
405 → 2.95 V     488 → 2.40 V     561 → 1.50 V     640 → 2.35 V      range 0–5 V
```

**DAC full scale is 5 V.** That was one of the questions drafted for Nikon; it is
now answered for free, and those four (channel, voltage) pairs are a ready-made
answer key for decoding any later capture.

## 4. There is no stored mW calibration, and NIS's mW is not a measurement

Every calibration record in the device DB is empty — `CALIBRATED0..3=0`,
`m_uiCalibValsCount0..3=0`, zero non-sentinel `m_dCalibVals` anywhere, and no
calibration XML/CSV under any Laboratory Imaging path. `m_strUnits=mW` appears in
8 records but carries no data.

The dialog explains why: the column header is `Value [V] or [mW]` against
`Percentage [%]`, under a `Segmented Linear Scale` checkbox. **The mW NIS can
display is a user-entered interpolation table, not something the LUN-F reports.**
No per-line nominal-maximum constants exist in the DLL either.

## 5. Nothing about the LUN-F can be read back. Nothing.

Checked exhaustively, because a status path would have changed the design:

- **DAC** — write-only by construction; `lunf_power.get_power()` already said so.
- **Blanking** — a DO readback is our own echo, not the shutter's state.
- **DAQ analog inputs** — all 32 read 10.9015 V, the ±10 V rail. That is floating
  RSE inputs, not signal; the per-channel spread is mux settling. **No LUN-F
  monitor is wired to the DAQ.**
- **The DLL** — `SetShutterState@CNIDAQAbstraction_AOTF`, `CLxLUNFShutter` and
  `ILxDeviceShutter` are **not exported**. The PE export table has 33 entries and
  none contain `Shutter` or `AOTF`; the only real entry points are
  `LX_ConstructorForCLxLUNFDevice` and its `...Sim` twin. Those names came from
  the string table and RTTI, and calling them would mean reconstructing NIS's
  device manager.

So control of this device is **open-loop, and will remain so** unless Nikon
documents a query interface. That is now the most important thing to ask them.

## 6. The SPI word format: narrowed from unknown to one of nine

This is the part the record has been blocked on since 2026-08-19.

### Why writing guessed bytes became allowable

`kb/decisions/2026-08-29-device-discovery-scope.md` forbids writing to a device
to find out what it does. That rule was written when there was no way to bound
the consequence. Two things changed on 2026-09-02:

- **blanking control** — measured, active-HIGH, so the laser can be gated off in
  software *before* any SPI byte is sent;
- **a power meter** — retiring the 2026-08-19 "measurement deferred" decision.

The probe was designed so that the rule's *purpose* still held: every frame in
the discovery burst carried **data = 0**, so no candidate could raise the output,
and all four blanking lines were closed for the duration. The relaxation was the
user's decision, taken explicitly.

### What the burst established

32 frames, SPI mode 0, 469 kHz, covering 24-bit `[cmd|addr][hi][lo]`
(AD5064 / LTC2604 / AD5665 / MAX5715 shapes), TI DAC8564-style control bytes,
32-bit AD5628/5668, 16-bit MCP4922 and a generic `[ch<<6|data]`, each against
addresses 0–3.

**561 went dark. 640 kept working.** Before the burst both emitted; between the
two observations nothing happened but those 32 frames. So:

- the FT4222 SPI link **reaches the DAC** — previously only "transport reachable";
- writes are **channel-selective**, not a global reset or a shutter side effect.

### Arbitrary levels, not just zero

Nine candidates addressing DAC index 2 were then alternated between full scale
and zero, 0.5 s apart, five cycles, **with 561's blanking held open the whole
time** so the shutter could not be the cause. 561 flickered.

`lunf_power.PROTOCOL` is therefore reachable from here, and its shape is one of:

```
3B/16b  [cmd<<4|2][d>>8][d]      cmd ∈ {0,1,2,3}
3B/16b  [0x14][d>>8][d]          DAC8564-style
4B/12b  [0x03][0x20|d>>8][d][0]  AD5628 / AD5668
2B/14b  [0x80|d>>8][d]
2B/12b  [0x30|d>>8][d]           MCP4922 A
2B/12b  [0xB0|d>>8][d]           MCP4922 B
```

**Three bisection rounds would name it.** The reset is now free — re-sending the
data = 0 burst extinguishes 561 on demand, so each round needs no NIS restart.
That is the immediate next step and it was not taken today.

## 7. The AO route is dead, and this closes a 2026-08-19 open item

`lunf_power.py` asked whether the LUN-F's analog power inputs might be cabled to
the DAQ instead — "*worth checking first*", never checked. Checked now, and the
answer is **no**:

- `Dev1` is a PCIe-6323 with exactly 4 AO channels at ±10 V, and the LUN-F has
  exactly 4 lines — suggestive, and wrong.
- ao0–ao3 driven together, 0 → 5 V in 1 V steps, then 0 ↔ 5 V for contrast: no
  change.
- Then at speed — 5, 1, 4, 2, 0 V at 0.5 s for 20 s, from one persistent DAQmx
  task so the pattern was actually delivered at rate, **with the blanking line
  held open** so the light never went off: no flicker.
- Then per channel: `ao2` against 561, `ao3` against 640: no flicker.

Consistent with `Connector Block: Not Specified` and with the Power column being
fixed text (`DAC 0..3`) rather than a resource selector in this Control mode.

**No one needs to propose this route again.**

## 8. NIS and Python cannot share the DAQ

With NIS running, taking `Dev1/port0/line6` fails with

```
-200587  the specified digital lines are either reserved ... by another task
```

`nis_ar.exe` holds port0 exclusively. With NIS gone, all four blanking lines
reserve cleanly. So the operating model in `verify_lunf_daq.py` — *set the levels
in NIS, close NIS, drive blanking from here* — is the only shape available; it is
not a preference, it is forced.

## 9. The fiber shutter closes on NIS's *clean* shutdown, not on link loss

`Fiber1` in the LUN-F Pad is a real shutter device in NIS's model
(`CLxLUNFShutter` implementing `ILxDeviceShutter`, one logical device per fiber,
`Temporary_shutter_name_for_lunf_fiber%d`), gating the per-line blanking. It is
not reachable from this repo: those names are string-table and RTTI entries, and
the DLL's 33 exports contain neither.

Two observations looked contradictory at first — the user reported that closing
NIS closes `Fiber1`, yet later 561 and 640 both emitted with NIS gone. The test
that separates the explanations is a **force**-kill, which skips whatever the
clean shutdown path does. It was run properly on the second attempt
(`config/lunf/handoff_from_nis.py --kill`):

```
BEFORE   nis_ar.exe [6544]   FT4222 A openable: False   Dev1 line6 free: False
KILL     SUCCESS: The process with PID 6544 has been terminated.
AFTER    nis_ar.exe none     FT4222 A openable: True    Dev1 line6 free: True
         -> 561 blinked, 10x at 0.5 s, driven from Python
```

**The shutter survives a kill.** So it is NIS's clean shutdown that closes it,
and the LUN-F has **no link-drop watchdog** — losing the USB host does not by
itself shut the fiber.

### The handoff, which is now a supported workflow

```
1. start NIS, open Fiber1, set the four line voltages on the pad
2. taskkill /F nis_ar.exe          <- releases Dev1 port0 and FT4222 A/B/C
3. drive blanking from Python      <- wavelength select + on/off, microseconds
```

`config/lunf/handoff_from_nis.py` performs steps 2–3 and verifies each one, and
**refuses to run if NIS is not already up** — the first attempt at this test
failed silently in exactly that way, killing a stale PID and reporting a null
result that looked like evidence.

### Why this is a workaround and not the answer

It leaves a per-session NIS dependency, which is against
[[project-pymmcore-only-no-nis]]. It depends on force-killing rather than any
documented interface, so a NIS update can break it. And it holds a laser shutter
open by skipping the vendor's own shutdown path, which is not a thing to build
on quietly. The supported way to open the shutter is still a question for Nikon;
the difference is that we are no longer blocked while we wait.

## Corrections to the record

- **Mid-session claim: right conclusion, asserted before the evidence.** It was
  stated during this session that the shutter closes because of NIS's
  clean-shutdown routine, and called confirmed. At that moment it was not — the
  `taskkill` that would have shown it had returned *process not found* and
  killed nothing. The claim was withdrawn, the test was then run properly, and
  §9 now carries it on evidence. Recorded this way on purpose: the conclusion
  surviving does not make the original assertion sound, and a reader should be
  able to tell which claims in this file are load-bearing.
- **`lunf_power.py` docstring, "NEXT THING TO TRY FIRST".** The USB-B route was
  tried. It produced a port (COM8) but no command set, and §2 shows it cannot
  supersede the SPI plan because NIS's USB path is the FT4222 itself.
- **`lunf_power.py` docstring, the NIDAQ-AO paragraph.** Answered: not cabled (§7).
- **`kb/systems/current.md`, "try USB-B first, capture second. Not yet
  attempted."** Attempted; see §1.
- **The DAC voltage range** was an unknown to be asked of Nikon. It is 0–5 V (§3).

## Still unknown

1. **Which of the nine framings is correct** — three bisection rounds away.
2. **Volts → mW.** The meter exists now but is a standalone display, not
   PC-readable, so the calibration is a manual exercise.
3. **A *supported* way to open the fiber shutter** (§9). The force-kill handoff
   is verified and works, but it is a workaround: a per-session NIS dependency,
   no documented interface, and it holds a laser shutter open by skipping the
   vendor's own shutdown path. Worth one question to Nikon — but no longer a
   blocker while we wait for the answer.
4. **Any status/query interface at all** (§5). Likely none; worth one question to
   Nikon so the answer is on the record either way.
5. **What COM8 speaks.** Nothing has been sent to it, and nothing should be until
   there is a documented command set.
6. **What FT4222 interfaces B and C do.** NIS holds them alongside A; unexplored.
