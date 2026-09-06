---
id: dualcam-config-corrections-pending
question: "What is wrong with config/micromanager/DMD_dualcam_LUNF.cfg, and what
  is the live device state under it, as observed on 2026-09-05"
source: operator memo + Device Property Browser readback + cfg inspection
expert: KH
date: 2026-09-05
confidence: high
scope: "config/micromanager/DMD_dualcam_LUNF.cfg — the only dual-camera config"
applies_to_systems: [current-laser]
review_after: 2026-12-05
supersedes: null
---

## Status: NOTHING HERE IS APPLIED YET

This is a running memo. The operator's instruction on 2026-09-05 was to collect
the corrections and revise the config file later, all together. **The `.cfg` is
untouched.** Do not treat any item below as fixed.

---

## 1. `LappMainBranch1` label/state mapping is INVERTED in the cfg

**Operator, 2026-09-05:** the physical correspondence is

    mirror_in   <->  State 1
    mirror_out  <->  State 0

The cfg declares the opposite ([DMD_dualcam_LUNF.cfg:139-140](../../config/micromanager/DMD_dualcam_LUNF.cfg)):

    Label,LappMainBranch1,1,mirror_out
    Label,LappMainBranch1,0,mirror_in

So every label this device reports is the wrong name for the position it is in.
The Device Property Browser on 2026-09-05 read `Label: mirror_in / State: 0`,
which by the corrected mapping means the branch was physically at **mirror_out**.

### This reconciles the 2026-09-04 contradiction rather than adding to it

The 2026-09-04 photometry measured, unambiguously and independent of any label:

| branch state | p99.9 | max | verdict |
|---|---|---|---|
| dark | 139 | 1183 | — |
| **State 0** | 139 | 1314 | identical to dark, light BLOCKED |
| **State 1** | 21083 | 25889 | full signal |

That session read the cfg's labels at face value and therefore concluded
"`mirror_out` (state 1) is the Aura position, and
`kb/systems/current.md > lapp_branch` is wrong." **Both halves of that
conclusion need revising.** With the label swap applied, State 1 — the state
that measurably passes light — is physically `mirror_in`, so:

- **The physics was right:** State 1 passes light, State 0 blocks it. Unchanged.
- **The label attribution was wrong:** it is `mirror_in`, not `mirror_out`, that
  couples the Lapp branch light to the sample. Which is also the physically
  sensible reading — a mirror *inserted* into the branch is what couples it in.
- **`kb/systems/current.md > lapp_branch` was RIGHT ALL ALONG.** It records that
  `mirror_out` has nothing to couple Aura in and so does not reach the sample.
  The apparent conflict with the measurement was manufactured entirely by the
  cfg's swapped Label lines.

The lesson from that session survives intact and gains a second layer: a
readback confirms the device went where it was told, never that the *name* it
reports for that position is correct. A mislabelled enum makes a correct record
look falsified.

### Correction to apply later

    Label,LappMainBranch1,1,mirror_in
    Label,LappMainBranch1,0,mirror_out

⚠ Applying this INVERTS the meaning of every `mirror_in` / `mirror_out` string
in existing code and notes. Grep for both tokens before changing the cfg, or
scripts that currently work by name will silently switch to the wrong position.

---

## 2. Dual-camera needs `CSUW1-Port`, and the cfg never sets it

**Operator, 2026-09-05:**

    dual-cam     ->  CSUW1-Port-Label: blue_red   / State 1   (REQUIRED)
    single-cam   ->  CSUW1-Port-Label: red_only   / State 2   (fine)

Verified against the cfg: it declares the labels
([lines 171-173](../../config/micromanager/DMD_dualcam_LUNF.cfg)) —
`2 red_only`, `1 blue_red`, `0 blue_only` — but there is **no `Property` line and
no `ConfigGroup` preset that sets `CSUW1-Port` at load.** The only ConfigGroup in
the file is `LaserLine` (405/488/561/640/AllOff over `LUNF-Blanking` lines
2/4/6/8).

**Consequence, and it is a silent trap:** loading `DMD_dualcam_LUNF.cfg` leaves
the port wherever it physically was. On 2026-09-05 that was `red_only` / State 2
— single-camera. **The file named "dualcam" does not put the instrument in
dual-camera mode.** Nothing errors; `Kinetix_blue` simply receives no light.

Fix options, to decide later: add a `Property,CSUW1-Port,...` line so the state
is set at load, or add a `ConfigGroup` for camera mode (`blue_red` / `red_only`)
so it is at least selectable as a preset and visible in Studio.

---

## 2b. The 2026-08-11 emission-filter correction was applied to only one scope profile

Found 2026-09-05 while checking the Aura path. `config/scopes/current-laser.yaml`
removed `88000v2-EM` / `EM1-455/50` / `EM1-525/36` / `EM1-605/52` / `EM1-705/72`
on 2026-08-11 as a misattribution — they are not EM1/EM2's actual filters — and
now lists only `EM-Open`. **`config/scopes/current-aura.yaml:26-29` still lists
four of them.** Same physical wheels, two contradictory records.

And neither record matches what the device actually reports, which is
`multi / 405 / 488 / 555 / 647 / b1-b4 / open`. So there are three accounts of
one filter wheel and no part number behind any of them. Resolve all three
together with the wheel part numbers.

## 3. Read-only vs changeable properties — ANSWERED 2026-09-05

Operator supplied the `Show read-only` view. Read-only rows render darker in the
Device Property Browser. Nothing here is settable from a script; several are
device-derived numbers worth more than anything in the registries, because they
are the hardware reporting itself rather than a datasheet being transcribed.

### Cameras — read-only set (identical on `Kinetix_blue` and `Kinetix_red`)

| property | blue | red | why it matters |
|---|---|---|---|
| `BitDepth` / `PixelType` | 12 / `12bit` | 12 / `12bit` | **ceiling is 4095 ADU** — confirms the clipping warning |
| `FullWellCapacity` | 15,000 | 15,000 | **contradicts the 200 e⁻ figure used so far — see below** |
| `X-dimension` / `Y-dimension` | 2400 / 2400 | 2400 / 2400 | 5.8 MP — **confirms these are Kinetix22, not Kinetix** |
| `ScanLineTime` | 7,063 ns | 7,063 ns | with the readout time, fixes the architecture |
| `Timing-ReadoutTimeNs` | 8,475,000 | 8,475,000 | 8.475 ms full frame |
| `Timing-ExposureTimeNs` | 30,002,000 | 30,002,000 | the 30 ms request, as actually applied |
| `Timing-ClearingTimeNs` / `-PreTriggerDelayNs` | 0 / 0 | 0 / 0 | |
| `Timing-PostTriggerDelayNs` | 7,062 ns | 7,062 ns | one line time |
| `ChipName` | `TMP-Kinetix` | `TMP-Kinetix` | |
| `SerialNumber` | `A23H723003` | `A24M723015` | **first record of which body is which** |
| `Name` | `PMPCIECam00` | `PMPCIECam01` | PVCAM enumeration order |
| `FirmwareVersion` | 30.48 | 30.48 | |
| `PVCAM Version` / `Adapter` | 3.10.2 / 1.3.75 | same | |
| `ReadoutRateName` | `Standard` | `Standard` | |
| `CCDTemperature` | 0.03 | 0 | setpoint 0, so it is holding |
| `ImageFormat` | `Mono16` | `Mono16` | 16-bit **container**, 12 significant bits |
| `FTCapable` / `Color` | No / OFF | No / OFF | |
| `PreampDelay` / `ScanLineDelay` / `ScanWidth` | 0 / 0 / 2.399 | same | |
| `CircularBufferFrameCount` | 93 | 93 | |
| `PP 0..5` *name* rows | module names | module names | see below |

**The `PP` rows split two ways, and this clarifies the despeckle picture.** The
*names* are read-only labels identifying each module — `PP 0 DESPECKLE BRIGHT
LOW`, `PP 1 DESPECKLE BRIGHT HIGH`, `PP 2 DESPECKLE DARK LOW`, `PP 3 DESPECKLE
DARK HIGH`, `PP 4 LARGE CLUSTER CORRECTION`, `PP 5 FRAME AVERAGING`. The
`ENABLED` / `THRESHOLD` / `MIN ADU AFFECTED` rows are **writable**. So the flags
can be turned off (they just do not stay off across a config load), and the
naming now confirms exactly what the six modules are rather than leaving it
inferred.

### ⚠ `FullWellCapacity` = 15,000 contradicts the figure used in this repo

The device reports **15,000 e⁻** while `Port` = `Sensitivity` and `ReadoutRate` =
`100MHz 12bit`. Earlier notes in this session, and the README's per-mode list
(200 / 1000 / 1000 / 15000), put Sensitivity at **200 e⁻** — the lowest of the
four modes. Both cannot be right. The likely reconciliation is that PVCAM's
`PARAM_FWELL_CAPACITY` reports the **sensor's** physical well rather than the
per-mode effective one, in which case the 200 e⁻ figure may still describe this
mode and the device is simply answering a different question. **Not resolved —
do not use either number for a saturation margin until it is.**

What is NOT in doubt: `BitDepth` = 12 and `PixelType` = `12bit`, both read-only,
so the digital ceiling is 4095 ADU. The measured 3500 ADU on
`abvigen-red-5um-cooh` under GREEN is 85.5% of that regardless of how the
electron well resolves.

### Readout architecture, derived from the read-only timing

`ScanLineTime` × 2400 rows = 16.951 ms, but `Timing-ReadoutTimeNs` = 8.475 ms —
a ratio of exactly **2.00**. So the sensor reads **dual-port, 1200 rows per half
simultaneously**, and frame time ≈ (rows / 2) × 7.063 µs. That gives a real,
device-sourced frame-rate ceiling instead of a datasheet claim:

| target | rows | height at 0.065 µm/px |
|---|---|---|
| 118 fps (readout-limited, full frame) | 2400 | 156 µm |
| 500 fps | 566 | 36.8 µm |
| 1000 fps | 283 | 18.4 µm |
| **3159 fps** (what G14 asked for) | **90** | **5.8 µm** |

The trapping gate's G14 wanted ≥ 3159 fps to sample a 316 Hz corner frequency
without aliasing bias. That needs a **90-row ROI — 5.8 µm tall, barely one 5 µm
bead**. Worth knowing before designing any stiffness measurement from camera
data: full-frame at 30 ms is 33 fps, two orders of magnitude short.

### Light engines — identity now read directly from the devices

| | `LightEngine` | `Aura` |
|---|---|---|
| `LEModel` | **Spectra III 8-NII-XS** | **Aura III 5-NII-WA** |
| `SerialNumber` | 28145 | 30859 |
| `FirmwareVersion` | 3.5.4 | 3.14.7 |
| lines | VIOLET · BLUE · CYAN · TEAL · GREEN · YELLOW · RED · NIR (8) | UV · CYAN · GREEN · RED · NIR (5) |
| `Name` | `LightEngine` | **`LightEngine`** |

⚠ **Both engines report `Name` = `LightEngine`.** The MM device labels differ
(`LightEngine` vs `Aura`) so nothing breaks, but any code or metadata that keys
off the device-reported `Name` rather than the MM label cannot tell the
SpectraIII from the Aura. Worth checking before trusting a `Name` field in an
archive.

The SpectraIII's eight named lines are also now on record — `data/light_sources.yaml`
should carry them the same way the Aura's five now are (observations, no centres
or widths, since none are published).

### Other read-only rows

`PFS-PFS Status` = `0000000100000000`, `PFS-PFS in Range` = `In Range`,
`IntermediateMagnification-Magnification` = `1.0x`,
`LUNF-Blanking-TriggerInputPin` = `Dev1/port0/line31`,
`MightexPolygon1000-OutputTriggerEnable` = 1 / `-OutputTriggerDelay` = 0, and the
`Description` / `Name` pair on every CSUW1 sub-device (`CSUW1-Hub`,
`-Filter_Red`, `-Filter_Blue`, `-Dichroic`, `-Bright`, `-Port`).

---

## 4. State changes between the two readbacks (both 2026-09-05)

Four things moved, and one of them answers an open question.

| property | first readback | read-only readback |
|---|---|---|
| **`CSUW1-Port`** | `red_only` / State 2 | **`blue_red` / State 1** |
| `Core-Camera` | `Kinetix_red` | **`Kinetix_blue`** |
| `CSUW1-Filter_Red` | `open` / State 9 | **`multi` / State 0** |
| `LappMainBranch1` | `mirror_in` / State 0 | `mirror_out` / **State 1** |
| `CSUW1-Filter_Blue` | `open` / State 9 | `open` / State 9 (unchanged) |
| `DiaLamp-Intensity` | 2.100 | 490 |
| `Kinetix_blue-ActualInterval-ms` | 0 | 30.22 |

**`CSUW1-Port` = `blue_red` settles §2's consequence and the splitter question.**
The port is now genuinely in dual-camera mode, so light is reaching both
detectors and the 561 nm split is live. It also means the port must have been
set by hand — the cfg still contains no line that would do it, so this will need
setting again on every load until §2 is fixed.

`LappMainBranch1` at State 1 is, by §1's corrected mapping, the light-passing
position — consistent with the fact that images were being acquired.

⚠ But `CSUW1-Filter_Red` is at `multi` (position 0) while `CSUW1-Filter_Blue` is
still `open` (position 9). So the blue arm has **no emission filter at all**. Any
observation on `Kinetix_blue` is currently unfiltered apart from the 561 splitter
edge and the MXR00724 cube.

---

## Live device state observed 2026-09-05 (Device Property Browser)

Recorded because several of these bear directly on today's session.

### Both emission wheels are OPEN — no filter in either arm

    CSUW1-Filter_Red-Label:  open   State 9
    CSUW1-Filter_Blue-Label: open   State 9

This is the live confirmation of the `optics.cli check` verdict on
[config/channels/abvigen-bangs-green-red-2color.yaml](../../config/channels/abvigen-bangs-green-red-2color.yaml):
**INFEASIBLE**, 0.09 OD of excitation blocking against 7 required, excitation and
detection bands overlapping. The wheels each carry positions
`0 multi / 1 405 / 2 488 / 3 555 / 4 647 / 5-8 b1-b4 / 9 open`, so a bandpass
exists in hardware — position 2 for the green arm, 4 for the red — but no
passband or part number has ever been recorded for any of them, which is why
none can be registered in `data/filters.yaml` or computed with.

### All six post-processing flags are ON, on BOTH cameras

    Kinetix_blue-PP 1..6 ENABLED: Yes
    Kinetix_red -PP 1..6 ENABLED: Yes

The known sticky PVCAM default: despeckle bright/dark low/high, large-cluster
correction and frame averaging revert to `Yes` on every config load, and they
**modify pixel values** — measured 2026-09-04, dark-frame max 148 ADU with them
on vs 1193 ADU with them off, so ADU is not proportional to electrons and the
frames cannot be repaired afterwards. Fatal for tracking and photometry.

**New consequence for dual-cam:** this must now be disabled on **two** cameras,
after the config load and before the first frame, every run.
`config/session/run_wall_diffusion.py::disable_post_processing()` does it for
one — it needs checking against a two-camera path before any dual-cam
acquisition is trusted.

### Camera mode is settled: Sensitivity, 12-bit — the tightest full well

    Kinetix_blue-Port: Sensitivity   ReadoutRate: 100MHz 12bit
    Kinetix_red -Port: Sensitivity   ReadoutRate: 100MHz 12bit

This closes the open `detection.setup.Camera.mode` question flagged in
`config/channels/particle647-yoyo1-2color.yaml`. Note which mode it is:
Sensitivity carries the **lowest full well of the four (200 e-, against
1000/1000/15000)**, so G6 saturation is at its most restrictive here — the
opposite end from DynamicRange. Any exposure/light-level headroom must be
computed in this mode, not a generic one.

Also both cameras are at `Gain: 1-Standard`, `Binning: 1x1`, `Offset: 100`,
`TriggerMode: Internal Trigger`, `ExposeOutMode: First Row`, `Exposure: 10` ms,
`CircularBufferEnabled: ON`, `FrameFfSummingEnabled: No`, `DiskStreamingEnabled: No`.
`Kinetix_red-ActualInterval-ms` reads 10.02 while blue reads 0 — red has been
acquiring, blue has not.

### No `Multi Camera` device is loaded

The 30 devices include `Kinetix_blue` and `Kinetix_red` as two independent PVCAM
cameras, with `Core-Camera: Kinetix_red`. There is **no `Multi Camera` utility
device** (grep finds "multi" only as a filter-wheel label). Micro-Manager's usual
route to one co-timestamped dual-camera stream is that Utilities device, so as
configured the Core addresses one camera at a time. Setting `CSUW1-Port` to
`blue_red` gets light to both detectors; it does not by itself give a single
two-channel acquisition. **This is the open architectural question for
"dual-cam" and needs settling before the session, not during it.**

### Other state worth having on record

| property | value | note |
|---|---|---|
| `Nosepiece-Label` | `1-Plan Apo LmbdD20 4x` (State 0) | **4x**, not the 100x Oil the channel config assumes |
| `PFS-FocusMaintenance` | `Off` | not locked; lens 8 for any long run |
| `PFS-DichroicMirrorInserted` | `Yes` | |
| `MightexPolygon1000-AffineTransform.m00..m12` | all `0` | DMD transform zeroed/uncalibrated — patterned illumination has no valid mapping |
| `LightPath-Label` | `4-L100` (State 3) | |
| `CSUW1-Dichroic-Label` | `on` (State 0) | |
| `CSUW1-Shutter-State` | `Closed` | |
| `Turret1Shutter / Turret2Shutter` | `1` / `0` | turret 1 open, turret 2 closed |
| `FilterTurret1 / 2` | `1-MXR00724 -Empty` / `1-Empty` | Ti2 turrets empty — not the emission path |
| `LUNF-Blanking-Blanking` | `On`, lines 2-8 all `0` | all laser lines blanked off |
| `NIDAQHub-SampleRateHz` | `10,000` | |
| `LightEngine` | all lines `0` | |
| `Aura` | all states `0`, intensities `50` | |
| `DiaLamp` | State `0`, Intensity `2.100` | |
| `Core-Shutter` / `Core-SLM` / `Core-AutoFocus` | `LightEngine` / `MightexPolygon1000` / `PFS` | |

---

## Related

`kb/systems/current.md > lapp_branch` (now believed correct — see §1) ·
[[lapp-branch-mirror-out-is-aura]] (agent memory, needs the label correction) ·
[[despeckle-reverts-every-load]] ·
`config/channels/abvigen-bangs-green-red-2color.yaml` ·
`data/particles.yaml` · `config/scopes/current-laser.yaml`
