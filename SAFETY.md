# SAFETY — hazards, order of operations, and the failure modes that return 0

> **STATUS: FIRST DRAFT / MEMO, 2026-09-03.** Written at the operator's request
> after the first three-subsystem session. **Not yet reviewed by the operator.**
> Everything here is either measured on this instrument or an operator
> instruction, and each item says which. Nothing in it is inferred from a manual
> unless labelled as such.
>
> Intended to become the top-priority document in the repository. Until it is
> reviewed, treat it as a record of what was learned, not as an approved
> procedure.

This instrument has a **class-4 laser**, a **0.13 mm working-distance objective
above a coverslip**, and a **write-only control interface that answers 0 to
commands it ignores**. Those three facts generate almost every hazard below.

---

## 0. The single most important property of this instrument

**On the optical tweezers, a return code of 0 means "the GUI accepted the
command", not "the thing happened".** The Tweez 300 TCP interface has **no
readback of any kind** — no position, no force, no trap list, no calibration
(manual pp. 66–69).

Measured consequences, all of which return 0:

| what is wrong | what you see |
|---|---|
| `Breakpoints > Enable Bits` = `0000` (the default) | `TRAP_PATT_RELEASE_BP` → **0**, and the breakpoint never held. Confirmed 2026-09-03. |
| `Breakpoints > Release Bits` doesn't cover the value | trap parks at the breakpoint and never releases → **0** |
| `Repeat > Enabled` = False (the default) | pattern traverses once and parks → **0** |
| pattern overruns the calibrated trapping range | points **silently clipped** to the edge → **0** |
| GUI calibrated at a different objective | every commanded µm is wrong by that ratio → **0** |
| trap named in a command doesn't hold your bead | drive runs perfectly on an empty trap → **0** |

**Rule: never treat a 0 from the tweezers as confirmation.** Confirm by eye in
the GUI, or by measuring the result in the camera data. Three of the six rows
above were resolved this session *only* by measuring the bead's motion.

---

## 1. Class-4 1064 nm trap laser (Aresis Tweez 300)

**Arm the laser at the GUI, with the interlocks in view.** That is the default
and `config/tweezers/run_pattern.py` sends no `LASER_ON` for this reason.

- **`hardware/optical_tweezers.py` has no safety switch of its own** — unlike
  `piezo_stage.py` (`allow_motion`) and `microscope.py`
  (`allow_write`/`allow_laser`/`allow_motion`), its constructor opens the socket
  and **all 28 commands including `laser_on()` are directly callable**. Today
  `mcp_server/switches.py` is the only brake in that path. This is a known gap
  (README item 0c) and the switch belongs in the driver.
- **`LOAD_PROJECT` can turn the laser on.** A project file stores "the state of
  the laser operation and beam setting" (manual p.65), so loading a project
  saved laser-on arms the laser. **Save every template with the laser OFF.**
- **Laser power is not readable or settable from software.** Dial % → mW is
  uncalibrated (deferred 2026-08-19). Write the number down or it leaves no
  record.
- **`Turret2Shutter` gates the 1064 coupling path** and is **not** in
  `hardware/microscope.LASER_DEVICES` (which covers only `LUNF-Blanking`), so
  opening it is not gated as a laser action. Consider adding it.

**Never send `TRAP_OFF` or `LASER_OFF`, or close `Turret2Shutter`, merely to
release the camera or to tidy up on exit.** That drops the bead. Operator
instruction, 2026-09-03: the OT laser may stay on while the camera is handed
away — the trap is the expensive thing to re-establish. `live_view.py` leaves
both turret shutters open on exit for exactly this reason.

## 1b. LUN-F XL confocal lasers (405 / 488 / 561 / 640)

- Reachable only as **blanking** on NIDAQ digital lines
  `Dev1/port0/line2/4/6/8`, via the `LaserLine` ConfigGroup. Park it at
  **`AllOff`** when not in use (it was already `AllOff` on 2026-09-03).
- **Per-line power is refused, deliberately.** `hardware/lunf_power.py` is
  complete as transport and will not transmit, because Nikon does not document
  the DAC word format and a guessed byte goes into a laser driver. Do not
  "fix" this by guessing.

---

## 2. Objective / coverslip collision — the worst irreversible risk

**The stand runs no objective-escape on a Micro-Manager nosepiece write.**
Measured 2026-09-03: rotating 4× → 100× Oil left `ZDrive` at 8288.740 µm and
moved it **+0.000 µm**. Whatever Z the outgoing objective was at is where the
incoming one arrives. `Plan Apo LmbdD0.13 100x Oil` has **130 µm** of working
distance to absorb the difference.

**I rotated the nosepiece at Z = 8288.740 µm before being told the rule. It did
not crash, and that was luck, not clearance.**

### Measured facts

- **Sample plane: `ZDrive` ≈ 2959 µm** — measured 2026-09-03, focused at 100×
  with a trapped bead, `PFS in Range = In Range`. Inside the operator's stated
  2800–3200 µm window.
- **The Z sign convention is UNMEASURED.** Which direction of `ZDrive` retracts
  the objective is not established. The circumstantial argument (a 130 µm WD
  lens survived being 5.3 mm from the sample plane, so +Z is probably retracted)
  is **not encoded anywhere**, and `hardware/microscope.Z_RETRACT_DIRECTION` is
  `None` on purpose. **Do not infer it.**

### Procedure

1. **Change objectives at the stand or in NIS**, where the Ti2's own escape runs
   and you can see the lens. Not from software.
2. If it must be done from software, **retract clear of the sample first** and
   confirm `PFS in Range` reads `Out of Range`.
3. Two guards now refuse the write, both **sign-free**
   (`Microscope._require_clear_of_sample`):
   - **PFS `In Range` → refuse.** A measurement: PFS bounces IR off the real
     coverslip.
   - **Z inside `SAMPLE_Z_WINDOW_UM` → refuse.** An assumption: that the sample
     is where it was recorded.
4. **PFS `Out of Range` authorises nothing.** An objective PFS cannot use, a
   missing coverslip, and a genuinely retracted lens all read the same. It can
   veto; it can never permit.

**Also: an objective change silently invalidates both optical-tweezers
calibrations** — the GUI's px→µm magnification and the AOD trapping-field
response — and neither is readable over TCP. After any objective change, every
`TRAP_POSITION` in µm lands somewhere else and nothing reports it. Verify by
driving a known amplitude and measuring it (this session: commanded ±10.000 µm,
measured 9.9672 and 10.0852 µm → calibration good for 100×).

---

## 3. Piezo stage (Prior/Queensgate NPC-D, 0–600 µm)

- **`NIDAQAO-Dev1/ao2` is a forbidden device.** It is the analogue line cabled
  to the piezo controller, and Micro-Manager writes 0 V on initialize, which
  drives the stage to 0 µm. `microscope.check_config_file()` refuses any `.cfg`
  declaring it, checked as **text before loading**, because the damage happens
  inside `initializeDevice` and there is nothing to prevent afterwards.
- **COM4 only, never TCP** (operator, 2026-09-03). The driver accepts an IP;
  there is no network path to this controller.
- **The port is exclusive.** The vendor NanoBench 6000 GUI holds it while it has
  a session open; close that session first.
- **Centre the axis before a bead is trapped, never after.** All three axes were
  parked at ~0 µm (bottom of travel), so a ±10 µm sine is out of range. Moving x
  to mid-travel translates the sample by 300 µm and would tear a trapped bead
  out of the trap.
- **Ramp large moves, don't step them.** A bare 300 µm command rings the closed
  loop; 100 steps over ~1 s settles to +39 nm.
- **Close every sine with a final sample at the centre.** Without it the last
  sample is one step short and the axis parks off-centre — measured 1.5 µm low —
  and each run re-centres on wherever the last one stopped, so it compounds.
- **Creep is ~0.9 µm** in the minute after a move. A continuous drive must be
  played about a *fixed* centre.
- Trajectories are **range-checked against the travel the controller reports and
  refused, never clipped**.

---

## 4. Camera ownership, and the order it forces

**PVCAM hands a Kinetix to one process at a time.** Three things want a camera:
the Tweez GUI (trap view and its GUI calibration), Micro-Manager
(acquisition), and `live_view.py`.

Order when the tweezers are involved:

1. Tweez GUI takes a camera → do the camera-bound work (GUI calibration, visual
   trap placement)
2. release
3. Micro-Manager loads its configuration

`config/micromanager/single_cam_red_LUNF.cfg` exists to make "one owner each"
expressible: it loads `Kinetix_red` only, leaving `Kinetix_blue` for the GUI.
TCP trap and pattern commands need no camera at all (manual p.34).

**Camera identity — check the serial, not the label:**

    Camera-1 = A23H723003   (Kinetix_blue)
    Camera-2 = A24M723015   (Kinetix_red)

Whether the PVCAM indices hold while the Tweez GUI holds one body is **still
untested**.

**Do not force-kill a script that has light on or devices open.** `Stop-Process
-Force` skips the `finally` block, so the excitation stays on and shutters stay
as they were. Use the clean exit path (Esc for `live_view.py`, the stop-file for
a continuous drive) unless a trap depends on the shutters staying open — in
which case a force-kill is the *safer* option precisely because it skips the
cleanup.

---

## 5. Light path — either turret shutter closed is a black frame

**`Turret1Shutter` and `Turret2Shutter` are in series.** Both were closed at the
start of the 2026-09-03 session, and two live-view sessions were spent looking at
a dark field before anyone checked. Both must be open to see anything, and
Turret 2 is also the 1064 path (§1).

Other path state worth confirming before blaming the sample:

- `CSUW1-Bright / BrightFieldPort` = `Bright Field` for widefield (disk bypassed)
- `CSUW1-Port` = `red_only` to send everything to `Kinetix_red`
- `CSUW1-Filter_Red` = `open` to let the cube do all the filtering, or `555`
- `LaserLine` = `AllOff` when the confocal is not in use

---

## 6. Sample exposure

- **Light is off by default and must be asked for.** `live_view.py` enables no
  line without both `--line` and `--intensity`, turns autoshutter **off** so the
  state is exactly what was requested, and takes the light down in a `finally`.
- **Intensity is per-mille (0–1000), not percent.** 50 is 5%. Read the unit off
  the device, not off a manual.
- **No absolute dose can be computed on this instrument.**
  `power_at_sample_mw` is empty for **every line of every source** and no dye has
  `bleach_photons`, so lens 5 returns BLOCKED on any absolute claim. This is
  README item 0a — a ~30 minute power-meter measurement that code cannot
  substitute for.
- **Set exposure by counts, not by a number someone suggested.** Full scale is
  **65535** (the camera reports `PixelType = 12bit` and lies — see below). Aim
  for the peak at roughly a third to a half of full scale.
- **Measure bleaching in the run itself.** Mean intensity of the first 10% of
  frames vs the last 10%. On 2026-09-03 at Aura GREEN 50/1000 with a 33.33 ms
  exposure, 5 s of acquisition showed **+2.19%** — no measurable bleaching.

---

## 7. Data integrity hazards that look like results

- **`PixelType` reports `12bit`; the data is 16-bit.** One 512×512 frame held
  12,441 distinct values with a modal spacing of 1 LSB and a maximum of 34,917.
  Trusting `PixelType` scales every count by 16.
- **`startSequenceAcquisition`'s `intervalMs` is ignored.** You cannot get 30 fps
  by asking. The frame period equals the exposure exactly (readout is pipelined),
  so 30.000 fps = 33.333 ms exposure. **Always report the achieved rate from
  `ElapsedTime-ms`, never the requested one.**
- **`ElapsedTime-ms` is quantised to 1 ms**, so the median interval reads exactly
  33.000 and jitter reads exactly 0. Take the rate from the **span across n−1
  intervals**.
- **MMCore raises nothing when it drops a frame.** `ImageNumber` gaps are the
  only proof; MM's own metadata files do not record it.
- **Never backfill a missing timestamp from host time.** An invented timestamp
  looks like data. Count it as `frames_without_timestamp`.
- **The host clock is not the experiment clock.** Mapping host stamps onto MM's
  series afterwards is a correlation, not a synchronisation.
- **Relative and absolute time conventions coexist and mixing them is silent.**
  `Clock.now_s()` is already relative; a raw `perf_counter()` is not. Subtracting
  the anchor from both put marks 15 minutes away from their own frames.
- **A live view during a measurement degrades timing ~20×** — TCP round trip
  2.93 ms quiet vs 51.4 ms with the viewer up, and the piezo took 2 overruns.
  **Do not watch a run you intend to measure from.**
- **In a crowded field, brightness cannot identify the trapped bead.** Six blobs
  within 27,200–29,140 counts produced six plausible-but-wrong fits. The
  discriminator that works: **the trapped bead is the only object that does not
  translate with the stage.**

---

## 8. Running procedure, in order

**Setup**

1. Close **NIS-Elements** (it holds the Ti2 and a camera). Operator permission
   standing.
2. Close the **NanoBench 6000** session if open (it holds COM4).
3. Power on the **Aura** if it is to be used — `Error : 573` on init means the
   chassis is not answering, not a port conflict.
4. **Change the objective at the stand**, per §2, before anything else.
5. **Centre the piezo** at mid-travel — before a bead exists.
6. Open **both turret shutters**.
7. Start the **Tweez GUI**, connect System Manager and the device, confirm the
   TCP server is listening.
8. Build/verify the trap template: `Enable Bits`, `Release Bits`,
   `Repeat > Enabled` + `Count`. **All GUI-only, all silent when wrong (§0).**
9. **Arm the laser at the GUI.**
10. Trap the bead.

**Per run**

11. Verify the trap's calibration by driving a known amplitude and **measuring**
    it, if the objective has changed since it was taken.
12. Confirm which trap holds the bead — by name.
13. **Close the live view** before a measurement run.
14. Run. Nothing moves without an explicit flag; the piezo additionally needs
    its unlock.
15. Check the run report: achieved rate, dropped frames by **both** detectors,
    `contaminated`.

**Never**

- Send a trap position step larger than the capture range with a bead trapped —
  a 14 µm jump simply drops it.
- Close `Turret2Shutter` or send `TRAP_OFF`/`LASER_OFF` to tidy up.
- Rotate the nosepiece with PFS `In Range`.
- Send `BEAM_SET_PARAMS` without the GUI's standing blanking time — it carries
  the rate **and** the blanking in one command. (Probably never needed: the rate
  is already 50 kHz.)
- Trust a 0 from the tweezers.

---

## 9. Open safety questions

- **The Z retract direction is unmeasured** (§2). This is the most consequential
  gap in this document.
- **The trapping height is unknown**, which dominates κ through Faxén and also
  determines how close the front element is to the coverslip.
- `Repeat > Enabled` and `Count` are still unread.
- Whether PVCAM's camera indices hold under contention.
- `Turret2Shutter` is not gated as a laser device.
- `hardware/optical_tweezers.py` still has no safety switch (§1).
