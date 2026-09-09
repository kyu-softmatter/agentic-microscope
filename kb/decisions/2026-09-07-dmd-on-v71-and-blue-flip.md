---
# frontmatter added 2026-09-09 for kb/INDEX.md. `question` restates this
# file's own title and Request/Context; the link fields read its own
# supersession notes. A retrieval aid, not evidence -- see knowledge/index.py.
id: 2026-09-07-dmd-on-v71-and-blue-flip
question: "Does the DMD load from this repository, and why can the blue camera image flip not live in the `.cfg`?"
date: 2026-09-07
---

# 2026-09-07 · The DMD does load, on a v71 core — and the blue flip cannot live in the `.cfg`

> Measured on the microscope PC. `3-Plan Apo LmbdD0.8 20x` at 1× intermediate,
> bin 2×2, both Kinetix in `Port = Dynamic Range` (16-bit), Spectra III on COM3,
> DMD patterns written straight to the SLM. Two independent findings, both from
> chasing one question: can the Spectra→DMD→sample path be driven from this
> repository?
>
> Corrects **two claims made within this session** — see "Retractions".

---

## 1. The Polygon1000 DMD loads. README's "will not load" is true only of `pymmcore-plus`

README item 4.1 records the DMD as *"the one device that does not load through
pymmcore-plus"*. That is exactly right and should stay. What was **not** recorded
is that it loads fine through **raw `pymmcore` pinned to device interface 71**,
and that this repository's own `DMD_dualcam_LUNF.cfg` then loads **complete**:

    31 devices, DMD included: MightexPolygon1000 (912x1140 SLM),
    Kinetix_blue + Kinetix_red, Spectra III 8-NII-XS, Aura III 5-NII-WA,
    Ti2-E and its sub-devices, CSU-W1, NIDAQ, SerialManager

### The wall, stated exactly

    Incompatible device interface version (MMCore requires 75; device adapter has 71)

The check is **exact-match, not a floor**. The Mightex vendor package
(V1.0-202103) is built against device interface 71; `pymmcore 12.5.0.75.0`
requires 75. Comparing the two cores' API surfaces: **45 methods added, 0
removed** (267 → 312), Module API unchanged at 10. The additions are a new pump
device type, oblique/tilted pixel-size support (`getPixelSizedxdz`), binning as
a first-class Core call, device timeouts, and log control. **This repository uses
none of them** (checked by grep). So nothing in v75 is needed here; the only cost
of staying at 71 is `pymmcore-plus`, which floors at `pymmcore>=11.10.0.74.0`.

That floor is why `bacteria2` wraps **raw `pymmcore`** rather than
`pymmcore-plus` — see `Desktop/bacteria2/pycoli2.yaml` (`pymmcore==11.1.1.71.2`)
and `Desktop/bacteria2/lib/devices_mm.py`.

### The recipe — three things, and the DLL one is not obvious

    venv:  pymmcore==11.1.1.71.2          # the .71. in the version IS the interface
    MM  :  C:\Program Files\Micro-Manager-2.0    # the v71 tree, not pymmcore-plus's
    code:  os.add_dll_directory(MM)       # <- vendor SDK deps resolve via the
           os.environ["PATH"] = MM + ...  #    Windows search order, which does NOT
           os.chdir(MM)                   #    include the adapter's own directory
           core.setDeviceAdapterSearchPaths([MM])

Without `add_dll_directory` the failure is
`The module, or a module it depends upon, could not be found` — which reads like
a missing file and is not one. `MT_Polygon1000_SDK.dll`, `mt_polygon1000_sdd.dll`
and `mtplgdriver.dll` are all present in the MM root; they simply are not on the
search path. **A missing-file-shaped error here means a search-path problem.**

Built at `C:\Users\Takatori lab\venvs\dmd_v71`.

### Consequence: no split-process architecture is needed

A two-process design (DMD on v71, everything else on v75) was validated and
does work — the DMD is USB3, touches no COM port, and the two processes coexist
with no contention (v71 holding Spectra+DMD while v75 loaded 29 devices).
**It is also unnecessary**, because the full config loads on v71 in one process.
Keep the simple thing.

### The DMD is not binary, and the mapping is a 180° rotation

Wrote an asymmetric test pattern (top-right = 255, bottom-left = 122, rest 0)
and imaged it:

| DMD quadrant | written | Kinetix_red | Kinetix_blue |
|---|---|---|---|
| top-right | 255 | **bottom-left** | **top-left** |
| bottom-left | 122 | top-right | bottom-right |

- **Grayscale is proportional, not thresholded.** Measured brightest/second =
  **1.99** (red) and **2.24** (blue) against a written 255/122 = **2.09**.
  `Kyu_test/project_single_dmd_pattern_dualcam.py` forces binary at
  `DMD_BINARY_THRESHOLD = 127`, which discards this — fine for its purpose, but
  it is a choice, not a device limit.
- **Red is a 180° rotation** of the DMD; **blue is a horizontal flip only.** The
  two arms differ by exactly one vertical flip — see §2.
- Pattern submit costs **~42 ms** (`setSLMImage` → `displaySLMImage` →
  `waitForDevice`), a **~23 Hz ceiling**. The camera does 118 fps full frame, so
  the DMD is the bottleneck for per-frame patterning.

### ⚠ Do not call `MT_Polygon1000_SDK.dll` with guessed signatures

The SDK exports 53 `MTPLG_*` symbols and `ctypes.WinDLL` loads it fine **from
the v75 venv** — `MTPLG_InitDevice()` returned `1` (one device) with no MM
involved, so a pure-ctypes path is genuinely feasible and would sidestep the ABI
wall entirely. But **there is no `MT_Polygon1000_SDK.h` anywhere on this
machine**, only the runtime DLLs, so the signatures are unknown:

- `MTPLG_ConnectDev(n)` returns `-5` for every `n` in 0..7 — not a 0-based index
- `MTPLG_GetDevUSBNumbers` is **not** `(int*)`; calling it that way raised
  `access violation reading 0xFFFFFFFFFFFFFFFF`

**That access violation wedged the DMD**: MM then failed with
`Unable to communicate with the device. (35)` while the device still enumerated
healthy at the OS level as `Cypress FX3 USB StreamerExample Device`
(`USB\VID_04B4&PID_00F1`), Status OK. Recovered by `MTPLG_ResetDevices()`
(no-arg, so no signature risk) + `MTPLG_UnInitDevice()` + ~8 s settle, after
which MM loaded and patterned normally again. Note `ResetDevices` **returned
`-1`** and recovery still happened, so it is not established which step did it.

Before trying ctypes again: get the header from Mightex, or read the argument
handling out of `mmgr_dal_MightexPolygon1000.dll` — the one piece of code on
this machine that provably calls the SDK correctly. Do not probe against live
hardware.

---

## 2. `Kinetix_blue-TransposeMirrorY` is inert. The blue flip must stay in software

`Kinetix_blue` exposes `TransposeMirrorX`, `TransposeMirrorY`, `TransposeXY` and
`TransposeCorrection`, all `0/1`. **None of them touch the pixels.** Same DMD
pattern, same light, toggling `TransposeMirrorY`:

| set | readback | TL | TR | BL | BR | top/bot |
|---|---|---|---|---|---|---|
| 0 | 0 | 1135.2 | 249.3 | 180.8 | 607.8 | 1.755 |
| **1** | **1** | 1146.2 | 250.7 | 181.5 | 612.1 | **1.760** |
| 0 | 0 | 1144.1 | 250.7 | 181.2 | 610.7 | 1.761 |

The property is accepted and reads back changed; the quadrant means move by
under 1 % and the top/bottom ratio does not invert. These are display and
stage-mapping hints for MMStudio; the Core image path ignores them.

**So a `Property,Kinetix_blue,TransposeMirrorY,1` line in the `.cfg` would be
worse than no line at all** — it would read back as configured while every frame
arrived unflipped. This is the `lapp_branch` lesson again in a new place: a
readback confirms the device was *told*, never that anything *happened*. Compare
`kb/systems/current.md > lapp_branch`, and §1's `ResetDevices` returning `-1`
while recovery nonetheless happened.

### Where it already lives, and today's confirmation of it

- `config/session/live_dualcam_view.py` — `--flip-y` defaults **True**
  (2026-09-06, operator observation), with `transform_point()` so detections go
  through the same transform as the image.
- `config/session/sort_core.py` — `BLUE_TO_RED_PX = (-1.21, 1.32)` applied
  **after a vertical flip**, measured 2026-09-06 (24/27 objects within 8 px,
  scale 0.99932).

Today's DMD pattern **upgrades the 2026-09-06 by-eye observation to a
measurement**: against a known asymmetric pattern the two arms differ by exactly
one vertical flip (§1 table). `--flip-y` default True is correct, and the
physical reason already recorded in `live_dualcam_view.py` — Kinetix_blue is the
reflect side of the DM A561LP, and a reflection reverses handedness — is the
right explanation.

Note the `flip` variable inside `sort_core.plan()` is a **different thing**:
destination-slot polarity in x, not the camera transform. Do not conflate them.

---

## 3. Excitation crosstalk, measured per line

One Spectra line on at a time, intensity 25, 16-bit, 10 ms, bin 2×2, DMD pattern
displayed:

| line | Kinetix_blue p99.9 | Kinetix_red p99.9 |
|---|---|---|
| **CYAN** | **10833** | **2121** |
| **GREEN** | 223 | **2145** |
| VIOLET · BLUE · TEAL · YELLOW · RED · NIR | ~222 | ~289 (YELLOW 364) |

**CYAN drives the red arm as strongly as GREEN does** (2121 vs 2145). The blue
arm is cleanly CYAN-only. This is the same phenomenon `sort_core.py` already
documents as its reason for strobing — *"with both lines lit the red camera sees
BOTH species and the assignment collapses"* — now with a per-line number.
**Species assignment must keep strobing** (`--alternate`, default True).
Simultaneous CYAN+GREEN is fine for geometry work like §1's orientation check.

---

## 4. Unexplained: the blue arm's response to CYAN is sub-linear

CYAN-only, all other lines verified at 0, blue camera p99.9:

    CYAN  2 ->  9458      CYAN  8 -> 9907
    CYAN  4 ->  9720      CYAN 16 -> 10388

**8× the level for +10 % signal**, reproducibly. Two explanations were tested and
**both fail**:

- *Photobleaching* — 8 repeats at one level retained **100.9 %** (blue) and
  **99.6 %** (red). No decay. A descending sweep gave the same near-flat shape
  as an ascending one, so it is not order-dependent either.
- *Stray lines* — all eight lines read `on=0, I=0` before anything was zeroed.

The red arm over a comparable sweep is roughly linear (GREEN 10→100 gave
2662→11199). So this is specific to blue/CYAN and **the cause is not known**.
Untested next guess: the Spectra's CYAN has a high output floor at low settings —
sweep CYAN 25→500 to see whether the curve ever becomes linear. **Blue-arm
photometry should not be treated as quantitative until this is understood.**

---

## Retractions — both claims were made within this session

1. **"The Spectra is on COM4."** It is on **COM3 with `Model = GEN3`**, exactly
   as `kb/systems/current.md` and all three original configs in
   `Desktop/Maintanance/micromanager/` already said: `Spectra III 8-NII-XS`,
   fw 3.5.4, s/n 28145. COM4 is the **piezo**; a config pointing the Lumencor
   adapter at it hung ~30 min waiting for a reply that cannot come. The COM4
   guess came from `Win32_SerialPort` showing a lone `USB Serial Device (COM4)`;
   the full PnP map shows COM4 is a Microsoft CDC device while **every Lumencor
   is FTDI** (COM3, COM7). A third FTDI port, COM8, answered a Lumencor probe by
   echoing the command back at itself; it was briefly guessed here to be the
   temperature stage, which was wrong — **COM8 is the LUN-F's USB-B port**
   (FT232R, EEPROM serial `FTDD2RRL`), already recorded in
   `2026-09-02-lunf-first-light-measured-limits.md` §1, and NIS does not use it.
   Checking that doc first would have saved the guess.

2. **"The Spectra is powered off / the port is blocked."** The first `Error 573`
   was genuine (chassis off, before the operator connected it). Everything after
   was **self-inflicted**: `Access denied` was this session's own orphaned
   processes holding COM3, and `E UNKNOWNCMD` was a raw PowerShell probe having
   written non-protocol strings (`GET_LEModel`) into the port, leaving stale
   bytes in the FTDI buffer. **Do not write raw strings to a device's port to
   "test" it** — the adapter is the thing that knows the protocol.

Method note: orphaned `--dry-run` preflights held COM10 (CSU-W1) for ~30 min and
made an unrelated config load fail with a misleading error. Long device-holding
runs must be reaped before the next load.
