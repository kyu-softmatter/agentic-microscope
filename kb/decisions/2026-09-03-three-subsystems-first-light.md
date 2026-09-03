# 2026-09-03 — three subsystems together, and what the instrument said back

**Status:** measured on the microscope PC. Every number below was read off the
hardware this session unless marked `user` (operator report) or `assumed`.

**What was attempted.** A 5 µm PS bead (555 ex / red em) trapped at the image
centre; the optical trap driven sinusoidally in **y** at 10 µm amplitude, 1 Hz;
the piezo stage driven identically in **x** at the same moment; a 30 fps
timestamped video for 5 s. This is README item 1 (three subsystems on one
timeline) with item 4.1 (drag calibration) falling out of it.

**What was achieved.** All three subsystems driven together from this
repository, recorded, with per-frame timestamps — and a first κ. What was *not*
achieved is a **controlled phase** between the two drives, for a reason that
took the whole session to find and is stated in §5.

---

## 1. Micro-Manager on the real instrument — first time from this repo

28 devices load. Two have to come out first, and both diagnoses are new:

| device | why it fails | resolution |
|---|---|---|
| `MightexPolygon1000` | `mmgr_dal_MightexPolygon1000` is absent from the pymmcore-plus nightly. Vendor package is pinned to MM device interface **v71** and lives only in `C:\Program Files\Micro-Manager-2.0`. Aborts the whole load at `Core,Initialize,1`. | dropped → `config/micromanager/single_cam_red_noDMD.cfg`. This is the same pin README 4.3 names as the FRAP blocker. |
| `Aura` | `Error in device "Aura": Error : 573`. **Not a port conflict** — COM7 opened cleanly from a bare `System.IO.Ports.SerialPort`, so the port was free and the chassis was not answering. It was powered off. | switch it on; initialises first try. 573 from the Lumencor adapter means *no reply*, not *no port*. |

**The API-75 blocker is gone.** `mmcore install` has been run and
`Micro-Manager_2.0.3_20260806` is in place; pymmcore 12.5.0.75.0 loads against
it. The note in `config/session/run_parallel.py` ("every adapter in the lab's MM
install fails against device API 75") is out of date.

**NIS-Elements must be closed** — it holds the Ti2 serial link and a camera.
Standing permission from the user to close it (2026-09-03).

**Camera identity, which the parent config asks for and nobody had answered:**

    Camera-1 = serial A23H723003   (Kinetix_blue)
    Camera-2 = serial A24M723015   (Kinetix_red)

Both read with the other body free. Whether the indices hold while the Tweez GUI
holds one is **still untested**.

### Two devices break `microscope.state()`

`CSUW1-Bright` and `LUNF-Blanking` are state devices whose positions were never
named, so `getStateLabel` answers *"Cannot get current position label"* and the
unguarded call took the whole read-state layer down. Fixed: falls back to
`"state N"`. `CSUW1-Bright` also fails `getState`, but its `BrightFieldPort`
property reads fine (`Bright Field` / `Confocal`).

### Config gaps found while there

- **`Core.Focus` is unset.** `ZDrive` loads but holds no role, so no Z or
  autofocus call works. One line: `Property,Core,Focus,ZDrive`.
- **`getPixelSizeUm()` returns 0.0** — the `.cfg` has no PixelSize configs at
  all, so nothing stamps µm/px into metadata. See §7 for what the value should
  actually be.
- **Only one ConfigGroup exists** (`LaserLine`). There is no widefield channel
  preset; a 555/red channel has to be set property by property.
- **Both filter turrets read `Empty`** at every position. The cubes are real
  (§4); the labels were never filled in by the 2026-07-03 Configurator run.

---

## 2. The turret shutters are in series, and both gate the image

`Turret1Shutter` and `Turret2Shutter` (Ti2-E, one per turret) were **both
closed**, and either one closed is a black frame regardless of what the light
engine is doing. Two live-view sessions were spent looking at a dark field
before this was checked.

**`Turret2Shutter` is also the 1064 nm coupling path.** Closing it drops a live
trap. It is **not** in `hardware/microscope.LASER_DEVICES`, which covers only
`LUNF-Blanking` — so opening it is not gated as a laser action. Worth
reconsidering.

Operator rule recorded: the OT laser may stay on while the camera is handed
away; never drop the trap to free the camera or to tidy up on exit.

---

## 3. The light-source records are wrong about both engines

Read off the devices. `data/light_sources.yaml` disagrees with both.

| MM label | device says | lines (named, not numeric) |
|---|---|---|
| `LightEngine` | `Spectra III 8-NII-XS`, s/n 28145, fw 3.5.4, COM3 | VIOLET · BLUE · CYAN · TEAL · **GREEN** · YELLOW · RED · NIR |
| `Aura` | `Aura III 5-NII-WA`, s/n 30859, fw 3.14.7, COM7 | UV · CYAN · **GREEN** · RED · NIR |

The yaml claims LightEngine has **7** lines (365/440/488/514/561/594/640) and
explicitly records "8-NII-XS" as a dropped wrong assumption — the device carries
that exact model string. It claims Aura has 405/440/488/561/640. Neither
matches. Both were "read from NIS-Elements diagram icons", which is the common
factor.

Each line is `<NAME>` (0/1) plus `<NAME>_Intensity` (**0–1000 per-mille**, not
percent). The `LightEngine` connection in the yaml is also wrong: it says
Ethernet 192.168.201.200, the `.cfg` and the device say COM3.

**Consequence for the session:** 555 nm excitation exists after all, as
`GREEN` on either engine. `light_sources.yaml` should be corrected from the
devices, not from the diagrams.

---

## 4. The filter cubes, and the emission window they actually give

Both were already in `data/filters.yaml`; the operator confirmed the physical
slots.

- **FilterTurret1 slot 1** — `MXR00724`, Nikon 5-band (DAPI/FITC/TRITC/Cy5/Cy7).
  EX 544–565 contains 555 dead centre; EM 589–623 is the red band.
- **FilterTurret2 slot 1** — the OT path: `OT-Dichroic-750LP` (reflects >750 nm,
  couples 1064 to the objective) + `OT-EM-750SP` (blocks ≥750 nm off the camera).

**The effective red window is narrower than the emitter.** `MXR00724-DM`
transmits 580–611 and `MXR00724-EM` passes 589–623, so the intersection is
**589–611 nm**, 22 nm, not 34. Triage only — the DM bands are a NIS dialog
readout whose reflection-vs-passband sense has never been cross-checked against
the vendor curve.

1064 blocking survives Turret 1 being empty: the 750/SP is in Turret 2, and 1064
is above the 849 nm top edge of every MXR00724 band anyway.

---

## 5. The breakpoint does nothing — `Enable Bits` is `0000`

**This is the session's most important finding and it invalidates a design.**

The intended scheme: `TRAP_ASSIGN_PATTERN` parks the trap at the breakpoint
(point 0 of the sine, the zero crossing), then `TRAP_PATT_RELEASE_BP` releases
it and the piezo is scheduled off that release's own anchor — so both drives
share a zero to within half a TCP round trip.

Measured instead, from a run with a **1 s quiet lead** before the trigger:

    x (stage)  lead std 0.0378 µm   drive std 0.4820 µm   ratio 12.7
    y (trap)   lead std 7.0402 µm   drive std 7.1290 µm   ratio  1.0
    y onset at frame 7; the trigger was recorded after frame 29

The trap was oscillating **at full amplitude through the entire lead**. It starts
when `TRAP_ASSIGN_PATTERN` lands — before the camera opens — and
`TRAP_PATT_RELEASE_BP` returns 0 while doing nothing. Exactly the failure
`gated_oscillations.py` warns about, now measured.

So every release-round-trip figure quoted this session is precision on a command
with no effect. The **lead mechanism itself works** — the stage was genuinely
quiet at 12.7:1 — which is what made the trap's behaviour visible.

**Fix:** `Trap 1 > Properties > Breakpoints > Enable Bits` → `0001`, GUI-only.
`Release Bits` must also cover the value or the trap parks and never releases.

Until then the phase is **measurable but not controlled**: both drives run at
exactly 1.0000 Hz, so their relative phase is constant within a run and can be
read off the video once.

---

## 6. TCP and timing, measured under three loads

`LOAD_PATTERN` **argument order is settled: name first.**

    LOAD_PATTERN "Sine 1Hz Y" "C:\...\sine-1hz-y-bp.tpf"  ->  0

The Command List (manual p.68) is right; the worked example (p.69, file first,
`.tsf`, relative path) is the sloppy one. `hardware/optical_tweezers.py` updated.

Round trip for one no-op command, and it depends entirely on what else is
running:

| context | median | worst |
|---|---|---|
| MM not loaded, no viewer | **2.93 ms** | — |
| MM loaded, recording | 10.5 ms | 60.1 ms |
| live view running | **51.4 ms** | — |

**The tweezers cannot be polled at 100 Hz.** A 500-step 10 ms schedule gave
486 overruns and 1.45 s of accumulated drift, against 0 overruns for the piezo
and microscope on the same run. This is the number behind the 2026-08-26
pattern-vs-direct decision, now measured under real load.

**Watching costs measuring.** With the live view up, the piezo took 2 overruns
and 25.75 ms max slip; without it, 0 and 1.50 ms. Do not run a live view during
a run you intend to measure from.

Two traps in the loop **halve the pattern frequency**: period =
`points × n_traps / rate`. 50,000 points at 50 kHz is 1.000 s with one trap and
2.000 s with two. They also share the laser power, so κ per trap roughly halves.

The GUI's switching rate is **already 50 kHz** — inferred from the trap running
at exactly 1.0000 Hz with 50,000 points and one trap. So `BEAM_SET_PARAMS` was
never needed for the rate, and the risk of overwriting the GUI's blanking time
with it was avoidable.

`TRAP_REMOVE_PATTERN` → 0 and the trap keeps holding its bead.

---

## 7. Camera: two adapter claims that are wrong, and one that matters

**`intervalMs` in `startSequenceAcquisition` is ignored.** Requested 33.333 ms
at a 5 ms exposure, got 5.000 ms → 200 fps. Confirmed on the Kinetix and on the
demo camera. **You cannot get 30 fps by asking for it.**

**Readout is pipelined, so the frame period equals the exposure exactly.** At a
512×512 ROI, +0.000 ms overhead at every point tested:

    exposure  5.00 ms -> period  5.000 ms (200.00 fps)
    exposure 10.00 ms -> period 10.000 ms (100.00 fps)
    exposure 30.00 ms -> period 30.000 ms ( 33.33 fps)

So **30.000 fps = 33.333 ms exposure**, not "exposure + readout". A 150-frame run
delivered 29.9980 fps, span 4967.0 ms, 0 dropped, jitter fraction 0.00000.

**`PixelType` reports `12bit` and the data is 16-bit.** One 512×512 frame held
**12,441 distinct values** with a modal spacing of 1 LSB and a maximum of
**34,917**. Twelve bits cannot represent any of that. Full scale is 65535;
`BitDepth: 16` (operator confirmed). Trusting `PixelType` would scale every
count by 16.

**`ElapsedTime-ms` is quantised to 1 ms** in this build, so every interval at
33.33 ms rounds to the same integer and the median jitter reads exactly 0. The
rate must come from the **span across n−1 intervals**, not the median interval.

Per-frame metadata attached by MMCore (measured, not assumed):
`ElapsedTime-ms` · `ImageNumber` · `TimeReceivedByCore` · `Binning` · `Camera` ·
`Height` · `Width` · `PixelType` · `ROI-X-start` · `ROI-Y-start`.
`ImageNumber` gaps are the only *proof* of a drop; the archive path cannot see
them because MM's metadata files do not record it.

Data rate at 512² / 16-bit / 30 fps is **15.8 MB/s** — 7.6% of the measured
206.8 MB/s disk, so no RAM detour is needed. Full frame would be 345 MB/s and
would force one.

**Displaying every frame during acquisition is free**: 13 ms median encode,
0/150 dropped at 30 fps.

---

## 8. Piezo

- **COM4 only, never TCP** (user). The driver accepts an IP; there is no network
  path to this controller.
- DLL taken from the NanoBench GUI install is **2.8.1**, not the 2.7.9 the driver
  was written against. Firmware 6.7.8, 3 channels, travel **0–600 µm** on all
  three, matching the 2026-08-27 record.
- **All three axes were parked at ~0 µm**, the bottom of travel — so a ±10 µm
  sine is out of range and `run_sine_hold.py` refuses rather than clips.
  Centring must happen **before** a bead is trapped: moving x by 300 µm
  translates the sample 300 µm and would tear the bead out.
- `unlock("0xDEC0DED")` → `User`. Standing permission to use `user` level.
- Host-timed 1 Hz sine, 100 samples/cycle: **0 overruns over 71 consecutive
  cycles**, slip median 0.4–0.9 µs, max 0.195 ms. Returned to centre within 7 nm.
- **Creep ≈ 0.9 µm** in the minute after a move ends. A continuous drive must be
  played about a *fixed* centre; re-reading the centre each cycle walks the axis.
- **The sine must be closed with a final sample at the centre.** Without it the
  last sample is one step short and the axis parks off-centre — measured 1.5 µm
  low on a 5-cycle run — which compounds across a series.
- A 300 µm move must be ramped, not stepped, or the closed loop rings.

---

## 9. Physics: a first κ, and a pixel size that needs revising

**Trap calibration is correct for the 100× objective.** The nosepiece was rotated
from 4× to 100× mid-session, which silently invalidates both Tweez calibrations
and is unreadable over TCP — so this was an open gate blocker all session. It is
retired by measurement: commanded ±10.000 µm, measured **9.9672** and
**10.0852 µm** in two runs. A 60× calibration would have given 6 or 16.7 µm.

**Three independent routes to κ:**

| route | κ (pN/µm) |
|---|---|
| y amplitude deficit (bead vs trap) | 3.65 |
| x drag displacement, static trap | 3.87 |
| x drag displacement, driven trap | 4.3–4.5 |

γ = 6πηa = 0.04712 pN·s/µm, peak drag γAω = 2.961 pN, γω = 0.2961 pN/µm.
All three ride on **η = 10⁻³ Pa·s assumed** (temperature unrecorded, ~2.4%/°C),
**a = 2.5 µm nominal**, and **no Faxén correction** — worth +16% at 10 µm from
the coverslip and +39% at 5 µm, and the trapping height is unknown. Faxén is
likely most of the 20% spread.

**The pixel size is ~0.7% too large.** Two independent 10 µm rulers, different
hardware, same sign:

    piezo stage (chamber-stuck particle)  10.000 µm commanded -> 10.0612 µm  (+0.61%)
    AOD trap    (trapped bead, y)         10.000 µm commanded -> 10.0852 µm  (+0.85%)

So ~**0.0645 µm/px**, not the 0.0650 in `kb/systems/current.md >
pixel_size_calibration` — which is a 2025-04 spreadsheet value equal to the
nominal 6.5/100 and should be recorded as `assumed`, with this as the first
measured cross-check. κ ∝ 1/pixel size, so this propagates.

**Motion blur is configuration-dependent and my first estimate was for the wrong
axis.** At ±10 µm and 1 Hz the peak velocity is 62.8 µm/s → 2.09 µm (32 px) of
smear at a 33.33 ms exposure, which applies to the **trap-driven y** axis. The
**drag-displaced x** axis moves only ±0.66 µm, so its peak velocity is 4.8 µm/s
and the smear is 1.4% of the amplitude.

**No measurable photobleaching** over 5 s at Aura GREEN 50/1000 (5%): first 15
frames vs last 15, **+2.19%** (it rose). Bead peak ~30,100 counts over a 208
background — 46% of the 65535 full scale.

**Archive precedent for this channel:** `TRITC555_Las10_Exp100_100x_1x1` and many
`Las10_Exp50/100_100x_1x1` — level 10, 50–100 ms. On the older Spectra X, so the
*level* does not transfer; the exposure-product (~1000 %·ms/frame) does. At 30 fps
the ceiling is ~33 ms, so this experiment runs at 1/3 of precedent's photons.

---

## 10. The sample is too concentrated to track automatically

Six blobs of near-identical brightness in one 156 µm field (27,200–29,140
counts). Every brightness-based tracker written this session locked onto the
wrong one, repeatedly, and produced *plausible* fits — an undriven axis
oscillating more than the driven one, residuals exceeding amplitudes, an onset
before its own trigger.

**The discriminator that works: the trapped bead is the only object that does
not translate with the stage.** Drive the stage ±10 µm and measure each blob's
displacement:

    blob (x=1202, y=1183) val 25690  ->  x span  23.89 px =  1.553 µm   TRAPPED
    seven others          val ~10-11k ->  x span 248-360 px = 16-23 µm

Unambiguous, and it uses hardware under our control rather than a tuned
threshold. It also showed the trapped bead is 2.3× brighter than the rest and
sits at the sensor centre — stable across every run of the session.

**A more dilute sample would make every measurement today easier to trust.**
That is a sample-prep call, not a code one.

---

## 11. Mistakes made this session, recorded because the guards came from them

- **Rotated the nosepiece at ZDrive = 8288.740 µm.** The stand ran **no
  escape** — Z moved +0.000 µm — so a 0.13 mm working-distance lens swung under
  a sample at an unchanged Z. The user's rule ("do not go top; the sample is at
  2800–3200 µm") arrived after. Guard added: `SAMPLE_Z_WINDOW_UM`,
  `NOSEPIECE_HAS_NO_ESCAPE`, `_require_clear_of_sample()`, 9 tests. It is
  deliberately **sign-independent** — it refuses at the sample plane and makes no
  claim about which side is retracted, because that is still unconfirmed.
- **`live_view.py` restored the turret shutters on exit.** Their prior state was
  *closed*, so "restore" and "drop the trap" were the same action, in the exact
  case that mattered. Now left open; `--close-turret-shutters` to opt in.
- **Mixed relative and absolute time conventions in one record.** `Mark.t_s` is
  already relative (`Clock.now_s()`); a raw `perf_counter()` is not. Subtracting
  the anchor from both put the marks 15 minutes after their own frames. Use
  `clock.wall_of()` for marks.
- **Claimed saturation against a 4095 full scale** when the data is 16-bit — see
  §7. Told the operator to hold power down when they had 2× headroom.
- **Invented a mechanism to explain a bad track:** claimed
  `TRAP_REMOVE_PATTERN` parks the trap off-centre and had cost 14.1 µm. It does
  not; the trap never moved. The tracker was on the wrong blob.
- **Quoted release-round-trip precision for six hours** on a command that, per
  §5, has no effect.

---

## 12. Still open

- **`Breakpoints > Enable Bits` → `0001`** and `Release Bits` to match (§5).
  Nothing else blocks a phase-controlled run.
- The GUI's standing **blanking time**, if `BEAM_SET_PARAMS` is ever needed —
  probably never, since the rate is already 50 kHz.
- `Repeat > Enabled` and `Count`, still unread.
- **Trapping height**, which dominates κ through Faxén.
- Room temperature, for η.
- Whether PVCAM's `Camera-1`/`Camera-2` indices hold while the Tweez GUI holds
  one body.
- A **hardware trigger** (`function.trigger-inputs.*`, `/Dev1/PFI0`) is the only
  thing that removes the host from the timing path.
