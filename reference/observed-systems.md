# Observed system inventory — ⚠ OLD setup

> ## THIS DOCUMENT IS NOT THE CURRENT SYSTEM
>
> Everything written here is an **old setup, back-extracted from data acquired in
> the past**. The microscope in operation today is different from this, and
> several more devices are due to be connected on top of it.
>
> **Purpose**: material for interpreting past data, working out what information
> gets lost in the metadata, and validating the knowledge-base schema.
>
> **PROHIBITED**: do not use any value in this document as the basis for a
> current-system settings recommendation.
>
> **Update condition**: when an MM `.cfg` with full capability arrives, do not
> discard this document — keep it as `reference/legacy-systems.md`, then build a
> new `reference/current-system.md` from the new `.cfg` + an NIS-Elements
> cross-check. The diff between the two documents is precisely the "conversion
> table for moving past data onto the current equipment".

Measured contents extracted by exhaustively scanning the headers of **2,343**
Micro-Manager metadata records (30.17 GB) in `D:\data`. These are not estimates —
they are the values actually written in the files.

> Scan method: only the first 420 lines of each `*_metadata.txt` were read
> (= `Summary` + the full device snapshot of the first `FrameKey`). A single file
> can be up to 44 MB, so the whole file is never read.

---

## 1. Conclusion first — one microscope, three configuration generations

There are 3 computer names, but the hardware fingerprint (camera chip, stand
device set) is effectively the same family.
**Do not distinguish systems by PC name.**

| Generation | ComputerName | MM version | Illumination device | Distinguishing features | Records |
|---|---|---|---|---|---|
| **A** | `DESKTOP-221I6SM` | 1.4.23 (2020-09-17) | `Spectra` (Lumencor Spectra X) | Wheel-A, Triggering (NI DAQ), LightPath present | 2,137 |
| **B** | `PC-7C612437CB` | 2.0.3 (2023-11-17 / 2025-07-24) | `Spectra` **+ `LightEngine`** (Spectra III 8-NII-XS) | A + ZDrive added | 179 |
| **C** | `Takatori_lab` | 2.0.3 (2025-02-28) | `LightEngine` only | **No Wheel-A · LightPath · IntermediateMagnification · Triggering** | 27 |

Recorded acquisition periods: generation B is 2024-07-02 to 2026-04-17,
generation C is 2025-03-19.
Generation A has to be dated from file timestamps, since MM 1.4 does not write
`StartTime` into `Summary`.

### Design requirements that fall straight out of this

- System identity is judged by a fingerprint of the **device label set + camera
  chip/serial**.
- Generation C has no `IntermediateMagnification` device, yet the folder name is
  `..._100x1.5x_...`.
  → **The 1.5x magnifier was inserted by hand and never recorded in the
  metadata.** The folder name is the only record.
- In generation C the objective label is `"6-"` (empty string). Only the turret
  position is there, with no name.

---

## 2. Project distribution

| Project | Records | Main generation used |
|---|---|---|
| ATPS motility induced partitioning | 1,829 | A |
| Liquid crystal | 320 | A(300) / B(20) |
| Active particle control | 145 | B |
| ATPS passive particle | 27 | C |
| Actin rheology | 14 | B |
| tweezers calibration | 4 | A |
| ATPS inclusion | 4 | A |

---

## 3. Camera

Identical across all generations. `ChipName = GS144BSI`,
`X/Y-dimension = 1608`.

| Item | Value | Source |
|---|---|---|
| Device label | `Prime95B` (typo `Pirme95B` in 20 records from some sessions) | metadata |
| Sensor | GS144BSI, 1608 × 1608 | metadata |
| Model, assumed | **Photometrics Prime 95B 25mm** | the 1608² array is the 25mm version. The 18mm version is 1200² |
| Pixel pitch | 11 µm (assumed) | ⚠ needs datasheet confirmation |
| Cooling | setpoint −15 °C, measured −14.9 °C | metadata |
| Trigger | `Internal Trigger` — **2,339/2,343, all of them** | metadata |

### Only two readout modes were ever used

`ReadoutRate` and `Gain` are perfectly correlated.

| ReadoutRate | Gain | BitDepth | Records | Character |
|---|---|---|---|---|
| `100MHz 16bit` | `1-HDR` | 16 | 1,270 | high dynamic range, slow |
| `200MHz 12bit` | `1-Full well` | 12 | 1,069 | fast, DR sacrificed |

`FullWellCapacity = 62000 e⁻`, `Offset = 100 ADU` (measured values in 12bit
mode).

### ⚠ Post-processing filters are switched on

```
"Prime95B-PP  1   ENABLED": "Yes"   PP 1 DESPECKLE BRIGHT LOW/HIGH,  THRESHOLD 125
"Prime95B-PP  2   ENABLED": "Yes"   PP 2 DESPECKLE DARK LOW,         THRESHOLD 125
"Prime95B-PP  3   ENABLED": "Yes"   PP 3 DESPECKLE DARK HIGH,        THRESHOLD  80
"Prime95B-PP  4   ENABLED": "Yes"   PP 4 (MIN ADU AFFECTED 200),     THRESHOLD  75
```

PVCAM on-camera despeckle is active. It breaks the premises of quantitative
photometry and subpixel localization (pixel-value linearity, independent
noise). → [Pitfalls §4](../docs/06-pitfalls.md)

---

## 4. Objectives — the turret position is not a stable identifier

| Turret | Generation A label | Generation B label | Records (A/B) |
|---|---|---|---|
| 1 | Plan Fluor 10x | Plan Fluor 10x | 2 / 141 |
| 2 | Plan Fluor 20x | — | 7 / 0 |
| 3 | Plan Apo Lmbd 40x | — | 21 / 0 |
| 4 | Plan Apo Lmbd 60x **Oil** | Plan Apo VC 60x **WI** | 80 / 20 |
| 5 | Plan Apo Lmbd 100x Oil | Plan Apo Lmbd 100x Oil | 1,852 / 14 |
| 6 | Plan Apo Lmbd 60x Water | *(no label, generation C)* | 175 / 27 |

**Turret position 4 was physically swapped between generations.** Identifying a
lens by position number gives the wrong answer.

### NA values are not in the metadata — they must be filled in

Micro-Manager does not record NA. The values below are **assumed from the Nikon
product names and must not be used in calculations before verification.**

| Label | Assumed NA | Immersion | Verification status |
|---|---|---|---|
| Plan Apo Lmbd 100x Oil | 1.45 | oil | ⚠ unverified |
| Plan Apo Lmbd 60x Oil | 1.40 | oil | ⚠ unverified |
| Plan Apo VC 60x WI | 1.20 | water | ⚠ unverified |
| Plan Apo Lmbd 60x Water | ? | water | ⚠ **product name inconsistent** — the Plan Apo λ family has no water spec. Physical engraving needs checking |
| Plan Apo Lmbd 40x | 0.95 | air | ⚠ unverified |
| Plan Fluor 20x | 0.50 | air | ⚠ unverified |
| Plan Fluor 10x | 0.30 | air | ⚠ unverified |

### Intermediate magnification

`IntermediateMagnification-Magnification`: `1.0x` 2,298 records, `1.5x` 14
records, absent 31 records.

### Effective pixel size (assuming 11 µm pitch, binning 1×1)

| Objective | Intermediate mag | Total mag | Pixel at sample |
|---|---|---|---|
| 100x | 1.5x | 150x | **73.3 nm** |
| 100x | 1.0x | 100x | **110 nm** |
| 60x | 1.0x | 60x | **183 nm** |
| 40x | 1.0x | 40x | **275 nm** |
| 20x | 1.0x | 20x | **550 nm** |
| 10x | 1.0x | 10x | **1,100 nm** |

`PixelSizeUm` is **0.0** in every file — pixel size calibration was never set in
MM. The values above are all obtained by calculation and have never been
cross-checked against a measured calibration (stage micrometer/grating).
→ [Pitfalls §2](../docs/06-pitfalls.md)

---

## 5. Light path · filters — the biggest gap

| Item | Observed value | Problem |
|---|---|---|
| `FilterTurret1-Label` | `1-DA/FI/TR10Empty` 2,312 records / `1-Empty` 27 records | **Effectively one cube.** The label string is mangled, so the exact part cannot be identified |
| `Wheel-A-Label` | `Filter-0` 2,292 records | **No name attached** to the Sutter Lambda wheel position. Which emission filter it was cannot be recovered from the metadata |
| `LightPath-Label` | `4-L100` 1,728 records / `3-AUX` 564 records | L100 = camera port 100%. AUX = assumed to be the optical tweezers/DMD path |
| `Turret1Shutter-State` | mostly `1` | |

### ⚠ An unresolved contradiction

`DA/FI/TR` is a DAPI/FITC/TRITC 3-band set, yet **764 records were acquired on a
647-Cy5 channel**. Possible explanations:

1. The real cube is 4-band (DA/FI/TR/Cy5) and the label was truncated
2. Emission selection is done by Wheel-A, invisible because its positions have
   no labels
3. The label does not match the physical part

Which of the three it is cannot be determined from metadata alone. **The current
system's `.cfg` + physical inspection are required.** This is the single biggest
gap in the knowledge base right now.

---

## 6. Illumination

### Lines used (Lumencor Spectra X, `Spectra` device)

| Line | Center wavelength (nominal) | Observed levels | Main use |
|---|---|---|---|
| Red | 640 nm | 5, 7, 8, 10, 13, 100 | 647-Cy5 |
| Cyan | 470 nm | 2, 5, 10, 50, 100 | 488-GFP |
| Green | 555 nm | 5, 10 | 555-TRITC |

`LightEngine` (Spectra III) exists in generations B/C, but **not a single
non-zero intensity was observed within the scan window.** That holds even though
42 records have `Core-Shutter = LightEngine`.
→ Meaning either the property names differ, or the actual illumination went
through a different path. Unresolved.

### Transmitted light

`DiaLamp-State = 1` in 130 records, `Intensity` e.g. 1901 (units unknown,
probably DAC counts).
`Core-Shutter = DiaLamp` in 1,186 records — brightfield acquisition is half the
total.

### ⚠ Two illumination devices are configured at once

Generation B has both `Spectra` and `LightEngine` in the config. You have to
judge from which one `Core-Shutter` points at, but the level values of the other,
idle device also persist in the metadata, which is confusing.
A parser **must determine the active illumination from `Core-Shutter`**.

---

## 7. Channels and exposure — the measured operating range

`ChNames` are the preset names of the MM Channel group.

| Channel | Records | Exposure min | Median | P90 | max |
|---|---|---|---|---|---|
| `OFF` (brightfield) | 1,230 | 5 ms | **7 ms** | 30 ms | 50 ms |
| `647-Cy5` | 764 | 10 ms | **500 ms** | 500 ms | 500 ms |
| `488-GFP` | 302 | 5 ms | **50 ms** | 2,000 ms | 2,000 ms |
| `555-TRITC` | 23 | 5 ms | 10 ms | 20 ms | 20 ms |
| `488nm_Blue` | 20 | 20 ms | 30 ms | 30 ms | 30 ms |
| `DMD_Green` | 2 | 30 ms | 30 ms | — | 30 ms |

The existence of a `DMD_Green` channel = **the DMD (pattern illumination) was
(or is) on the system.** That is directly relevant to photo-driven active-matter
experiments, yet no DMD device appears in the config. Needs confirmation.

The 647-Cy5 exposures being piled up at 500 ms means they are effectively
**pinned to the ceiling**, and under those conditions acquisition above 2 Hz is
impossible.

---

## 8. ROI usage patterns

| ROI | Records | Interpretation |
|---|---|---|
| `0-0-1608-1608` | 1,218 | full frame |
| `~90–200 px` square (near sensor center) | many | **crop for fast tracking.** e.g. `726-762-120-108`, `717-750-138-135` |
| `603-603-402-402` | 27 | intermediate size |

The crop center is roughly (780, 810), close to the sensor center (804, 804).
sCMOS reads out row by row, so speed only goes up if you reduce the vertical
size — cutting width alone does nothing.
→ [Decision engine §4](../docs/04-decision-engine.md)

---

## 9. Focus maintenance

`PFS-FocusMaintenance`: `On` 1,033 / `Off` 1,306.
`PFS-PFS in Range` was `Out of Range` in the example file —
sessions may be mixed in where PFS was on but never locked. Record this too when
indexing.

---

## 10. Micro-Manager 1.4 vs 2.0 — the schemas differ

Generation A (2,137 records, 91% of the total) is MM 1.4.23, and its `Summary`
structure differs from 2.0.
**A single parser will miss most of the data.**

| Field | MM 1.4.23 | MM 2.0.3 |
|---|---|---|
| Pixel size | `PixelSize_um` | `PixelSizeUm` |
| ROI | `Summary.ROI` = array `[606,690,357,186]` | FrameKey string `"742-898-160-176"` |
| Start time | **absent** (`UUID` only) | `StartTime` |
| Per-frame camera | **absent** | `Camera` |
| Per-frame binning | **absent** | `Binning` |
| Bit depth | `Summary.BitDepth` | FrameKey `BitDepth` |
| Device key list | absent | `ScopeDataKeys` |
| Other | `PVCAM-TimeStamp`, `ChColors`, `IJType` | `AxisOrder`, `IntendedDimensions`, `UserData` |

Generation A has no `Camera` field, so 1,118 records came out of the scan with an
unknown camera. They have to be traced back via `Prime95B-*` prefixed properties
or `Core-Camera`.

---

## 11. Folder naming convention — in practice the most honest record

Information that did not survive in the metadata survives in the folder names
(e.g. generation C's 1.5x). There are 547 unique folder names.

```
{sample/dye}_{Las<intensity or wavelength>}_{Exp<exposure ms>}_{magnification}_{binning}_{repeat number}
```

Real examples:
```
SA647_Las10_Exp500_100x_1x1_20
OT0.005_Las555_5_exp10_100x_1.5x_1x1_1
dtz1um_g-actin_488_Las5_Exp50_100x_1x1_2
Polar_0deg_Exp30_60x_1x1_1
va5_vr5_BF_Exp10_100x_1x1_1
Focus0.4_OT0.05_str0.1_exp10_100x1.5x_1x1_1
```

Observed label tokens: `SA647`(243), `DEX647`(134), `Atto647`(111), `AO488`(103),
`std488`(76), `Las488`(61), `BF`(31), `AF647`(19), `FITC`(15), `Phal647`(10),
`MQFITC`(10), `TRITC555`(9), `Polar/Pol0/Pol90`(11), `Cy5`(2).

Other tokens: `OT<value>` (optical tweezers output), `str<value>`,
`Focus<value>`, `va5_vr5`, `<n>mM`, `dtz1um`.

**Caution**: `Las10` means intensity 10%, `Las488` means wavelength 488 nm, and
`Las555_5` means the 555 nm line at 5%. The same prefix carries two meanings. If
the number is an integer in 350–800, it must be read as a wavelength.

---

## 12. Top-priority acquisition targets derived from this inventory

1. **The current system's MM `.cfg`** — filter wheel/cube labels, Channel preset definitions
2. **Filter set part numbers** — what `DA/FI/TR10Empty` actually is
3. **Physical objective engravings** — NA, immersion, WD
4. **Measured pixel size calibration** — per magnification
5. **Measured illumination output** — `%` → mW@sample by power meter, per objective
6. **Whether the current system descends from one of the three generations above, or is entirely separate**
